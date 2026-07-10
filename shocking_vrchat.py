import asyncio
import collections
import yaml, uuid, os, sys, traceback, time, socket, re, json
from threading import Thread
from loguru import logger
import copy

from fastapi import FastAPI, Request, WebSocket, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from websockets.server import serve as wsserve

import srv
from srv.connector.coyotev3ws import DGWSMessage, DGConnection
from srv.handler.shock_handler import ShockHandler
from srv.command_queue import CommandQueue, CommandPriority

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher


def get_runtime_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


RUNTIME_BASE_DIR = get_runtime_base_dir()
STATIC_DIR = os.path.join(RUNTIME_BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(RUNTIME_BASE_DIR, "templates")

app = FastAPI(docs_url=None, redoc_url=None)

WAVE_HISTORY_SAMPLE_MS = 25

CONFIG_FILE_VERSION  = 'v0.2'
CONFIG_FILENAME = f'settings-advanced-{CONFIG_FILE_VERSION}.yaml'
CONFIG_FILENAME_BASIC = f'settings-{CONFIG_FILE_VERSION}.yaml'
CONFIG_HOT_RELOAD_INTERVAL = 1.0
SETTINGS_BASIC = {
    'dglab3':{
        'channel_a': {
            'avatar_params': [
                {'path': '/avatar/parameters/pcs/contact/enterPass', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaA', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaC', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/wildcard/*', 'mode': 'distance'},
            ],
            'mode': 'distance',
            'strength_limit': 5,
            'overlimit_max': 20,
        },
        'channel_b': {
            'avatar_params': [
                {'path': '/avatar/parameters/pcs/contact/enterPass', 'mode': 'distance'},
                {'path': '/avatar/parameters/lms-penis-proximityA*', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaB', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaC', 'mode': 'distance'},
            ],
            'mode': 'distance',
            'strength_limit': 5,
            'overlimit_max': 20,
        }
    },
    'version': CONFIG_FILE_VERSION,
}

DEFAULT_SHOCK_WAVE = '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]'

def _default_mode_config():
    return {
        'shock': {
            'duration': 2,
            'wave': DEFAULT_SHOCK_WAVE,
            'wave_preset': None,
            'wave_scale': 1.0,
        },
        'distance': {
            'freq_ms': 10,
            'wave_preset': None,
            'wave_scale': 1.0,
        },
        'touch': {
            'wave_preset': None,
            'wave_scale': 1.0,
            'n_derivative': 1,
        },
        'combo': {
            'enabled': False,
            'shock_threshold': 0.9,
            'shock_hold_ms': 200,
        },
        'trigger_range': {
            'bottom': 0.0,
            'top': 0.8,
        },
    }

SETTINGS = {
    'SERVER_IP': None,
    'dglab3': {
        'channel_a': {'mode_config': _default_mode_config()},
        'channel_b': {'mode_config': _default_mode_config()},
    },
    'ws': {
        'master_uuid': None,
        'listen_host': '0.0.0.0',
        'listen_port': 28846,
    },
    'osc': {
        'listen_host': '127.0.0.1',
        'listen_port': 9001,
    },
    'web_server': {
        'listen_host': '127.0.0.1',
        'listen_port': 8800,
    },
    'log_level': 'INFO',
    'version': CONFIG_FILE_VERSION,
    'general': {
        'auto_open_qr_web_page': True,
        'local_ip_detect': {
            'host': '223.5.5.5',
            'port': 80,
        },
    },
}
DEFAULT_SETTINGS_BASIC = copy.deepcopy(SETTINGS_BASIC)
DEFAULT_SETTINGS = copy.deepcopy(SETTINGS)
SERVER_IP = None
CONFIG_MTIMES = {}
handlers = []


def merge_defaults(defaults, current):
    if isinstance(defaults, dict) and isinstance(current, dict):
        merged = copy.deepcopy(current)
        for key, value in defaults.items():
            if key in merged:
                merged[key] = merge_defaults(value, merged[key])
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(current)


def normalize_avatar_param_entries(channel_settings: dict):
    default_mode = channel_settings.get('mode', 'distance')
    normalized = []
    for entry in channel_settings.get('avatar_params', []):
        if isinstance(entry, str):
            normalized.append({'path': entry, 'mode': default_mode, 'enabled': True})
        elif isinstance(entry, dict):
            normalized.append({
                'path': entry.get('path', ''),
                'mode': entry.get('mode', default_mode),
                'enabled': entry.get('enabled', True),
            })
    channel_settings['avatar_params'] = normalized


def load_config_files():
    with open(CONFIG_FILENAME_BASIC, 'r', encoding='utf-8') as f:
        basic = yaml.safe_load(f)
    with open(CONFIG_FILENAME, 'r', encoding='utf-8') as f:
        advanced = yaml.safe_load(f)
    basic = merge_defaults(DEFAULT_SETTINGS_BASIC, basic)
    advanced = merge_defaults(DEFAULT_SETTINGS, advanced)
    # Sync basic params into advanced
    for ch in ['channel_a', 'channel_b']:
        advanced['dglab3'][ch]['avatar_params'] = basic['dglab3'][ch]['avatar_params']
        advanced['dglab3'][ch]['mode'] = basic['dglab3'][ch]['mode']
        advanced['dglab3'][ch]['strength_limit'] = basic['dglab3'][ch]['strength_limit']
        if 'overlimit_max' in basic['dglab3'][ch]:
            advanced['dglab3'][ch]['overlimit_max'] = basic['dglab3'][ch]['overlimit_max']
        normalize_avatar_param_entries(advanced['dglab3'][ch])
    return advanced, basic


def reset_logger():
    logger.remove()
    logger.add(sys.stderr, level=SETTINGS.get('log_level', 'INFO'))


def update_config_mtimes():
    for path in [CONFIG_FILENAME, CONFIG_FILENAME_BASIC]:
        if os.path.exists(path):
            CONFIG_MTIMES[path] = os.path.getmtime(path)


def has_config_file_changed():
    for path, previous_mtime in CONFIG_MTIMES.items():
        current_mtime = os.path.getmtime(path) if os.path.exists(path) else None
        if current_mtime != previous_mtime:
            return True
    return False


def apply_hot_reloadable_settings(new_settings, new_settings_basic):
    global SERVER_IP
    old_settings = copy.deepcopy(SETTINGS)

    engine_restart_needed = False

    if new_settings['osc'] != old_settings['osc']:
        engine_restart_needed = True
    if new_settings['ws'] != old_settings['ws']:
        engine_restart_needed = True
    if new_settings.get('SERVER_IP') != old_settings.get('SERVER_IP'):
        engine_restart_needed = True

    old_basic = copy.deepcopy(SETTINGS_BASIC)
    if new_settings_basic['dglab3'] != old_basic['dglab3']:
        if any(
            new_settings_basic['dglab3'][ch]['avatar_params'] != old_basic['dglab3'][ch]['avatar_params'] or
            new_settings_basic['dglab3'][ch]['mode'] != old_basic['dglab3'][ch]['mode']
            for ch in ['channel_a', 'channel_b']
        ):
            engine_restart_needed = True

    # Web server port/host cannot be changed at runtime
    if new_settings['web_server'] != old_settings['web_server']:
        logger.warning("[hot-reload] web_server config changed. Full program restart required to apply.")
        new_settings['web_server'] = old_settings['web_server']

    SETTINGS.clear()
    SETTINGS.update(new_settings)
    SETTINGS_BASIC.clear()
    SETTINGS_BASIC.update(new_settings_basic)

    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()
    reset_logger()
    DGConnection.refresh_limits_from_settings(SETTINGS)

    if engine_restart_needed:
        logger.info("[hot-reload] OSC/WS/param config changed, restarting engine...")
        _schedule_engine_restart()
    else:
        for handler in handlers:
            if hasattr(handler, 'refresh_settings'):
                handler.refresh_settings()

    logger.success("[hot-reload] Configuration reloaded.")


def hot_reload_configs():
    try:
        new_settings, new_settings_basic = load_config_files()
        apply_hot_reloadable_settings(new_settings, new_settings_basic)
        update_config_mtimes()
    except Exception:
        logger.error(traceback.format_exc())
        logger.error("[hot-reload] Failed to reload configuration.")


async def config_hot_reload_loop():
    while True:
        await asyncio.sleep(CONFIG_HOT_RELOAD_INTERVAL)
        if has_config_file_changed():
            hot_reload_configs()

def get_current_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((SETTINGS['general']['local_ip_detect']['host'], SETTINGS['general']['local_ip_detect']['port']))
    client_ip = s.getsockname()[0]
    s.close()
    return client_ip

def get_qr_content():
    return (
        f'https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://'
        f'{SERVER_IP}:{SETTINGS["ws"]["listen_port"]}/{SETTINGS["ws"]["master_uuid"]}'
    )

def _serve_spa():
    """Serve Vue SPA index.html."""
    spa_index = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(spa_index):
        return FileResponse(spa_index, media_type='text/html')
    return RedirectResponse("/dashboard-legacy")

def _read_template(name, **kwargs):
    """Read a template file and do simple string substitution."""
    path = os.path.join(TEMPLATES_DIR, name)
    if not os.path.exists(path):
        return HTMLResponse("<h1>Template not found</h1>", status_code=404)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    for key, val in kwargs.items():
        content = content.replace('{{ ' + key + ' }}', str(val))
        content = content.replace('{{' + key + '}}', str(val))
    return HTMLResponse(content)


# --- Page routes ---
@app.get("/")
async def web_index():
    return _serve_spa()

@app.get("/get_ip")
async def web_get_ip():
    return get_current_ip()

@app.get("/dashboard-legacy")
async def web_dashboard_legacy():
    return _read_template('dashboard.html')

@app.get("/qr")
async def web_qr():
    return _read_template('tiny-qr.html', content=get_qr_content())


# --- Error handling ---
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})


# --- API Routes ---

@app.get("/api/v1/status")
async def api_v1_status():
    return {
        'healthy': 'ok',
        'engine_running': engine.running,
        'osc_listening': f"{SETTINGS['osc']['listen_host']}:{SETTINGS['osc']['listen_port']}",
        'last_osc_time': _osc_activity[0]['time'] if _osc_activity else None,
        'devices': [
            {
                "type": 'shock',
                'device': 'coyotev3',
                'attr': {
                    'strength': conn.strength,
                    'strength_max': conn.strength_max,
                    'strength_limit': conn.strength_limit,
                    'overlimit_max': conn.overlimit_max,
                    'overlimit_active': conn.overlimit_active,
                    'uuid': conn.uuid,
                }
            } for conn in srv.WS_CONNECTIONS
        ],
    }

@app.get("/api/v1/wave_history")
async def api_v1_wave_history():
    return {'A': _get_wave_history_snapshot('A'), 'B': _get_wave_history_snapshot('B')}

@app.get("/api/v1/wave_history/stream")
async def api_v1_wave_history_stream(channel: str = 'A', since: int = 0):
    """Incremental wave history: return only samples after 'since' seq number."""
    channel = channel.upper()
    history = _wave_history.get(channel, collections.deque())
    new_samples = [s for s in history if s.get('seq', 0) > since]
    latest_seq = _wave_history_seq.get(channel, 0)
    samples = [{'s': s['s'], 'f': s['f']} for s in new_samples]
    return {'samples': samples, 'seq': latest_seq, 'sample_ms': WAVE_HISTORY_SAMPLE_MS}

@app.get("/api/v1/osc_activity")
async def api_v1_osc_activity():
    return {'events': list(_osc_activity)}

@app.get("/api/v1/qr_payload")
async def api_v1_qr_payload():
    return {'content': get_qr_content()}

@app.get("/api/v1/strength/{channel}/{action}/{value}")
async def api_v1_strength(channel: str, action: str, value: int):
    """Adjust device strength. action: set/add/sub. value: 0-200."""
    channel = channel.upper()
    if channel == 'ALL':
        channels = ['A', 'B']
    elif channel in ('A', 'B'):
        channels = [channel]
    else:
        raise HTTPException(400, 'invalid channel')
    mode_map = {'set': '2', 'add': '1', 'sub': '0'}
    mode = mode_map.get(action)
    if mode is None:
        raise HTTPException(400, 'action must be set/add/sub')
    value = max(0, min(200, value))
    for ch in channels:
        for conn in srv.WS_CONNECTIONS:
            await conn.set_strength(ch, mode=mode, value=value, force=True)
    return {'result': 'OK', 'action': action, 'value': value, 'channels': channels}

# --- Strength Boost (temporary +N with auto-revert) ---
_strength_boost = {'A': 0, 'B': 0}
_strength_boost_expire = {'A': 0.0, 'B': 0.0}

@app.get("/api/v1/strength_boost/{channel}/{value}/{duration}")
async def api_v1_strength_boost(channel: str, value: int, duration: float):
    """Temporarily boost strength by value, auto-reverts after duration seconds."""
    channel = channel.upper()
    if channel == 'ALL':
        channels = ['A', 'B']
    elif channel in ('A', 'B'):
        channels = [channel]
    else:
        raise HTTPException(400, 'invalid channel')
    value = max(1, min(100, value))
    duration = max(0.5, min(30.0, duration))
    for ch in channels:
        already_boosted = _strength_boost[ch]
        if already_boosted == 0:
            for conn in srv.WS_CONNECTIONS:
                await conn.set_strength(ch, mode='1', value=value, force=True)
            _strength_boost[ch] = value
        elif already_boosted != value:
            for conn in srv.WS_CONNECTIONS:
                await conn.set_strength(ch, mode='0', value=already_boosted, force=True)
                await conn.set_strength(ch, mode='1', value=value, force=True)
            _strength_boost[ch] = value
        _strength_boost_expire[ch] = time.time() + duration
    return {'result': 'OK', 'boost': value, 'duration': duration, 'channels': channels}

async def _strength_boost_checker(stop_event: asyncio.Event):
    """Background task: revert expired strength boosts."""
    while not stop_event.is_set():
        try:
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        now = time.time()
        for ch in ['A', 'B']:
            if _strength_boost[ch] > 0 and now >= _strength_boost_expire[ch]:
                boost_val = _strength_boost[ch]
                _strength_boost[ch] = 0
                for conn in srv.WS_CONNECTIONS:
                    await conn.set_strength(ch, mode='0', value=boost_val, force=True)
                logger.debug(f"[boost] channel={ch} reverted -{boost_val}")

async def _ws_status_pusher(stop_event: asyncio.Event):
    """Periodically push device status to subscribed WS clients."""
    last_device_count = -1
    while not stop_event.is_set():
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            return
        # Only push if there are subscribers
        has_subs = any('status' in subs for subs in _ws_subscriptions.values())
        if not has_subs:
            continue
        device_count = len(srv.WS_CONNECTIONS)
        # Push on device count change, or every 10s as heartbeat
        if device_count != last_device_count:
            last_device_count = device_count
            devices = []
            for conn in srv.WS_CONNECTIONS:
                devices.append({
                    'strength': conn.strength,
                    'strength_max': conn.strength_max,
                    'strength_limit': conn.strength_limit,
                })
            await _ws_broadcast('status', {'devices': devices, 'engine_running': True})

# --- Strength Limit ---
@app.get("/api/v1/strength_limit")
async def api_v1_strength_limit_get():
    return {
        'channel_a': SETTINGS_BASIC['dglab3']['channel_a']['strength_limit'],
        'channel_b': SETTINGS_BASIC['dglab3']['channel_b']['strength_limit'],
        'overlimit_a': SETTINGS_BASIC['dglab3']['channel_a'].get('overlimit_max', 20),
        'overlimit_b': SETTINGS_BASIC['dglab3']['channel_b'].get('overlimit_max', 20),
    }

@app.post("/api/v1/strength_limit")
async def api_v1_strength_limit_set(request: Request):
    data = await request.json()
    changed = False
    for ch_key, ch_name in [('channel_a', 'A'), ('channel_b', 'B')]:
        if ch_key in data:
            val = max(0, min(200, int(data[ch_key])))
            SETTINGS_BASIC['dglab3'][ch_key]['strength_limit'] = val
            SETTINGS['dglab3'][ch_key]['strength_limit'] = val
            changed = True
        ol_key = f'overlimit_{ch_key[-1]}'
        if ol_key in data:
            val = max(0, min(200, int(data[ol_key])))
            SETTINGS_BASIC['dglab3'][ch_key]['overlimit_max'] = val
            SETTINGS['dglab3'][ch_key]['overlimit_max'] = val
            changed = True
    if changed:
        config_save()
        DGConnection.refresh_limits_from_settings(SETTINGS)
        logger.info(f"[strength_limit] Updated: A={SETTINGS_BASIC['dglab3']['channel_a']['strength_limit']}(+{SETTINGS_BASIC['dglab3']['channel_a'].get('overlimit_max',20)}), B={SETTINGS_BASIC['dglab3']['channel_b']['strength_limit']}(+{SETTINGS_BASIC['dglab3']['channel_b'].get('overlimit_max',20)})")
    return {
        'success': True,
        'channel_a': SETTINGS_BASIC['dglab3']['channel_a']['strength_limit'],
        'channel_b': SETTINGS_BASIC['dglab3']['channel_b']['strength_limit'],
        'overlimit_a': SETTINGS_BASIC['dglab3']['channel_a'].get('overlimit_max', 20),
        'overlimit_b': SETTINGS_BASIC['dglab3']['channel_b'].get('overlimit_max', 20),
    }

# --- Overlimit Rules Engine ---
OVERLIMIT_RULES_FILE = 'overlimit_rules.yaml'
_overlimit_rules = []
_osc_param_state = {}
_overlimit_effective = {'A': 0, 'B': 0}

def _load_overlimit_rules():
    global _overlimit_rules
    if os.path.exists(OVERLIMIT_RULES_FILE):
        with open(OVERLIMIT_RULES_FILE, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        _overlimit_rules = data.get('rules', [])
    else:
        _overlimit_rules = []

def _save_overlimit_rules():
    tmp = OVERLIMIT_RULES_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.safe_dump({'rules': _overlimit_rules}, f, allow_unicode=True)
    os.replace(tmp, OVERLIMIT_RULES_FILE)

def _eval_condition(condition: dict, param_state: dict) -> bool:
    param = condition.get('param', '')
    operator = condition.get('operator', '==')
    threshold = condition.get('value', 0)
    current = param_state.get(param)
    if current is None:
        return False
    try:
        current = float(current)
        threshold = float(threshold)
    except (TypeError, ValueError):
        return False
    ops = {'==': lambda a,b: abs(a-b)<0.001, '!=': lambda a,b: abs(a-b)>=0.001,
           '>': lambda a,b: a>b, '<': lambda a,b: a<b, '>=': lambda a,b: a>=b, '<=': lambda a,b: a<=b}
    return ops.get(operator, lambda a,b: False)(current, threshold)

def _evaluate_overlimit_rules():
    global _overlimit_effective
    max_limit = {'A': 0, 'B': 0}
    for rule in _overlimit_rules:
        if not rule.get('enabled', True):
            continue
        if _eval_condition(rule.get('condition', {}), _osc_param_state):
            limit_val = int(rule.get('limit_value', 0))
            channel = rule.get('channel', 'both')
            if channel in ('a', 'both'):
                max_limit['A'] = max(max_limit['A'], limit_val)
            if channel in ('b', 'both'):
                max_limit['B'] = max(max_limit['B'], limit_val)
    changed = False
    for ch in ['A', 'B']:
        if max_limit[ch] != _overlimit_effective[ch]:
            _overlimit_effective[ch] = max_limit[ch]
            changed = True
    if changed:
        for conn in srv.WS_CONNECTIONS:
            conn.overlimit_active['A'] = max_limit['A'] > 0
            conn.overlimit_active['B'] = max_limit['B'] > 0
            conn.overlimit_max['A'] = max_limit['A'] if max_limit['A'] > 0 else SETTINGS['dglab3']['channel_a'].get('overlimit_max', 20)
            conn.overlimit_max['B'] = max_limit['B'] if max_limit['B'] > 0 else SETTINGS['dglab3']['channel_b'].get('overlimit_max', 20)

def _overlimit_osc_hook(address, *args):
    if args:
        _osc_param_state[address] = args[0]
    if _overlimit_rules:
        _evaluate_overlimit_rules()

@app.get("/api/v1/overlimit_rules")
async def api_v1_overlimit_rules_get():
    return {'rules': _overlimit_rules, 'effective': _overlimit_effective}

@app.post("/api/v1/overlimit_rules")
async def api_v1_overlimit_rules_set(request: Request):
    global _overlimit_rules
    data = await request.json()
    _overlimit_rules = data.get('rules', [])
    _save_overlimit_rules()
    _evaluate_overlimit_rules()
    logger.info(f"[overlimit_rules] Saved {len(_overlimit_rules)} rules")
    return {'success': True, 'rules': _overlimit_rules}

@app.delete("/api/v1/overlimit_rules/{index}")
async def api_v1_overlimit_rules_delete(index: int):
    if 0 <= index < len(_overlimit_rules):
        removed = _overlimit_rules.pop(index)
        _save_overlimit_rules()
        _evaluate_overlimit_rules()
        logger.info(f"[overlimit_rules] Deleted rule: {removed.get('name', index)}")
        return {'success': True, 'rules': _overlimit_rules}
    raise HTTPException(400, 'invalid index')


# --- Shock / Sendwave ---
@app.get("/api/v1/shock/{channel}/{second}")
async def api_v1_shock(channel: str, second: str):
    if channel == 'all':
        channels = ['A', 'B']
    else:
        channels = [channel.upper()]
    try:
        second = float(second)
    except Exception:
        second = 1.0
    second = min(second, 10.0)
    repeat = int(10 * second)
    for _ in range(repeat // 10):
        for chan in channels:
            wavestr = json.dumps(['0A0A0A0A64646464'] * 10, separators=(',', ':'))
            await command_queue.put(CommandPriority.API, chan, 'wave', value=wavestr, source_id='api_shock')
    if repeat % 10 > 0:
        for chan in channels:
            wavestr = json.dumps(['0A0A0A0A64646464'] * (repeat % 10), separators=(',', ':'))
            await command_queue.put(CommandPriority.API, chan, 'wave', value=wavestr, source_id='api_shock')
    return {'result': 'OK'}

@app.get("/api/v1/sendwave/{channel}/{repeat}/{wavedata}")
async def api_v1_sendwave(channel: str, repeat: str, wavedata: str):
    """Send raw wave data. channel: A/B, repeat: 1-100, wavedata: 16 hex chars."""
    try:
        channel = channel.upper()
        if channel not in ['A', 'B']:
            raise Exception
    except:
        channel = 'A'
    try:
        repeat_int = int(repeat)
        if repeat_int > 100 or repeat_int < 1:
            raise Exception
    except:
        repeat_int = 10
    try:
        if not re.match(r'^([0-9A-F]{16})$', wavedata):
            raise Exception
    except:
        wavedata = '0A0A0A0A64646464'
    wavestr = json.dumps([wavedata] * repeat_int, separators=(',', ':'))
    logger.debug(f'[API][sendwave] C:{channel} R:{repeat_int} W:{wavedata}')
    await command_queue.put(CommandPriority.API, channel, 'wave', value=wavestr, source_id='api_sendwave')
    return {'result': 'OK'}

# --- Wave Test ---
_wave_test_state = {
    'active': False,
    'channel': 'A',
    'strength': 50,
    'wave_scale': 1.0,
    'preset': None,
}

@app.post("/api/v1/wave_test/start")
async def api_v1_wave_test_start(request: Request):
    data = await request.json()
    channel = data.get('channel', 'A').upper()
    if channel not in ('A', 'B'):
        raise HTTPException(400, 'channel must be A or B')
    strength = max(0, min(200, int(data.get('strength', 50))))
    wave_scale = max(0.0, min(1.0, float(data.get('wave_scale', 1.0))))
    preset_name = data.get('preset', None)
    _wave_test_state['active'] = True
    _wave_test_state['channel'] = channel
    _wave_test_state['strength'] = strength
    _wave_test_state['wave_scale'] = wave_scale
    _wave_test_state['preset'] = preset_name
    logger.info(f"[wave_test] Started: ch={channel} str={strength} scale={wave_scale} preset={preset_name or 'default'}")
    return {'result': 'OK', 'active': True}

@app.post("/api/v1/wave_test/stop")
async def api_v1_wave_test_stop():
    _wave_test_state['active'] = False
    channel = _wave_test_state['channel']
    for conn in srv.WS_CONNECTIONS:
        await conn.clear_wave(channel)
    logger.info("[wave_test] Stopped")
    return {'result': 'OK', 'active': False}

@app.post("/api/v1/wave_test/update")
async def api_v1_wave_test_update(request: Request):
    if not _wave_test_state['active']:
        raise HTTPException(400, 'test not running')
    data = await request.json()
    if 'strength' in data:
        _wave_test_state['strength'] = max(0, min(200, int(data['strength'])))
    if 'wave_scale' in data:
        _wave_test_state['wave_scale'] = max(0.0, min(1.0, float(data['wave_scale'])))
    if 'preset' in data:
        _wave_test_state['preset'] = data['preset'] or None
    return {'result': 'OK', 'state': {
        'active': True,
        'strength': _wave_test_state['strength'],
        'wave_scale': _wave_test_state['wave_scale'],
        'preset': _wave_test_state['preset'],
    }}

@app.get("/api/v1/wave_test/status")
async def api_v1_wave_test_status():
    return {
        'active': _wave_test_state['active'],
        'channel': _wave_test_state['channel'],
        'strength': _wave_test_state['strength'],
        'wave_scale': _wave_test_state['wave_scale'],
        'preset': _wave_test_state['preset'],
    }

async def _wave_test_loop(stop_event: asyncio.Event):
    """Background loop that sends waves continuously while test is active."""
    from srv.wave_preset import WavePresetLibrary
    wave_position = 0.0
    lib = WavePresetLibrary()
    saved_limits = None
    while not stop_event.is_set():
        try:
            if _wave_test_state['active']:
                channel = _wave_test_state['channel']
                strength = _wave_test_state['strength']
                wave_scale = _wave_test_state['wave_scale']
                preset_name = _wave_test_state['preset']
                if saved_limits is None:
                    saved_limits = {
                        'A': SETTINGS['dglab3']['channel_a']['strength_limit'],
                        'B': SETTINGS['dglab3']['channel_b']['strength_limit'],
                    }
                    DGConnection._suppress_clear = True
                    command_queue.set_enabled(CommandPriority.OSC_INTERACTION, False)
                    command_queue.set_enabled(CommandPriority.OSC_PANEL, False)
                    command_queue.set_enabled(CommandPriority.GAME, False)
                ch_key = f'channel_{channel.lower()}'
                SETTINGS['dglab3'][ch_key]['strength_limit'] = strength
                DGConnection.refresh_limits_from_settings(SETTINGS)
                for conn in srv.WS_CONNECTIONS:
                    await conn.set_strength(channel, mode='2', value=strength, force=True)
                wavestr = None
                if preset_name and lib.get(preset_name):
                    wavestr = lib.build_resampled_window(
                        preset_name, start_position=wave_position,
                        window_ops=10, wave_scale=wave_scale,
                        texture_floor=0.35, sample_step=1.0,
                    )
                    wave_position += 40.0
                if not wavestr:
                    wavestr = ShockHandler.scale_wavestr(DEFAULT_SHOCK_WAVE, wave_scale)
                await command_queue.put(CommandPriority.API, channel, 'wave', value=wavestr, source_id='wave_test_loop')
                await asyncio.sleep(0.9)
            else:
                if saved_limits is not None:
                    SETTINGS['dglab3']['channel_a']['strength_limit'] = saved_limits['A']
                    SETTINGS['dglab3']['channel_b']['strength_limit'] = saved_limits['B']
                    DGConnection.refresh_limits_from_settings(SETTINGS)
                    DGConnection._suppress_clear = False
                    command_queue.set_enabled(CommandPriority.OSC_INTERACTION, True)
                    command_queue.set_enabled(CommandPriority.OSC_PANEL, True)
                    command_queue.set_enabled(CommandPriority.GAME, True)
                    saved_limits = None
                wave_position = 0.0
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[wave_test_loop] error: {e}")
            await asyncio.sleep(0.5)

# --- Settings ---
def strip_basic_settings(settings: dict):
    ret = copy.deepcopy(settings)
    for chann in ['channel_a', 'channel_b']:
        del ret['dglab3'][chann]['avatar_params']
        del ret['dglab3'][chann]['mode']
        del ret['dglab3'][chann]['strength_limit']
    return ret

@app.get("/setup")
async def web_setup_wizard():
    return _read_template('setup_wizard.html')

@app.post("/api/v1/setup")
async def api_v1_setup(request: Request):
    global SETTINGS, SETTINGS_BASIC, SERVER_IP
    try:
        data = await request.json()
        for ch in ['channel_a', 'channel_b']:
            ch_data = data.get(ch, {})
            SETTINGS_BASIC['dglab3'][ch]['mode'] = ch_data.get('mode', 'distance')
            SETTINGS_BASIC['dglab3'][ch]['strength_limit'] = int(ch_data.get('strength_limit', 100))
            SETTINGS_BASIC['dglab3'][ch]['avatar_params'] = [
                {'path': p, 'mode': ch_data.get('mode', 'distance')} for p in ch_data.get('avatar_params', [])
            ]
        if 'osc' in data:
            SETTINGS['osc']['listen_port'] = int(data['osc'].get('listen_port', 9001))
            SETTINGS['osc']['listen_host'] = data['osc'].get('listen_host', '127.0.0.1')
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
        app.state.setup_complete = True
        return {'success': True, 'message': 'Configuration saved.'}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/v1/config")
async def get_config():
    return {
        'basic': SETTINGS_BASIC,
        'advanced': strip_basic_settings(SETTINGS),
    }

@app.post("/api/v1/settings")
async def api_v1_settings_update(request: Request):
    data = await request.json()
    restart_needed = []
    if 'osc' in data:
        osc = data['osc']
        if 'listen_port' in osc:
            SETTINGS['osc']['listen_port'] = int(osc['listen_port'])
            restart_needed.append('osc')
        if 'listen_host' in osc:
            SETTINGS['osc']['listen_host'] = osc['listen_host']
            restart_needed.append('osc')
    if 'ws' in data:
        ws = data['ws']
        if 'listen_port' in ws:
            SETTINGS['ws']['listen_port'] = int(ws['listen_port'])
            restart_needed.append('ws')
    if 'web_server' in data:
        web = data['web_server']
        if 'listen_port' in web:
            SETTINGS['web_server']['listen_port'] = int(web['listen_port'])
            restart_needed.append('web_server')
        if 'listen_host' in web:
            SETTINGS['web_server']['listen_host'] = web['listen_host']
            restart_needed.append('web_server')
    if 'log_level' in data:
        SETTINGS['log_level'] = data['log_level']
        reset_logger()
    config_save()
    if restart_needed:
        web_restart = 'web_server' in restart_needed
        engine_needs_restart = any(r in restart_needed for r in ('osc', 'ws'))
        async def _delayed_restart():
            await asyncio.sleep(0.5)
            if engine_needs_restart:
                logger.info("[settings] Restarting engine due to OSC/WS config change...")
                await engine.restart()
            if web_restart:
                logger.warning("[settings] Web server port/host changed. Full restart required.")
                _restart_program()
        asyncio.create_task(_delayed_restart())
    return {
        'success': True,
        'restart_needed': list(set(restart_needed)),
        'message': '已保存。' + ('引擎正在重启...' if restart_needed else ''),
    }

@app.post("/api/v1/engine/restart")
async def api_v1_engine_restart():
    async def _do_restart():
        await asyncio.sleep(0.3)
        await engine.restart()
    asyncio.create_task(_do_restart())
    return {'success': True, 'message': '引擎正在重启...'}

@app.get("/api/v1/engine/status")
async def api_v1_engine_status():
    return {'running': engine.running}

def _restart_program():
    """Restart the current process. Works on both Windows and Linux."""
    import subprocess
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable] + sys.argv[1:]
    else:
        cmd = [sys.executable] + sys.argv
    if sys.platform == 'win32':
        subprocess.Popen(cmd, close_fds=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        os._exit(0)
    else:
        os.execv(cmd[0], cmd)


# --- Params ---
@app.get("/api/v1/params/{channel}")
async def api_v1_params_get(channel: str):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    ch_key = f'channel_{ch}'
    params = SETTINGS_BASIC['dglab3'][ch_key].get('avatar_params', [])
    default_mode = SETTINGS_BASIC['dglab3'][ch_key].get('mode', 'distance')
    strength_limit = SETTINGS_BASIC['dglab3'][ch_key].get('strength_limit', 100)
    return {'params': params, 'default_mode': default_mode, 'strength_limit': strength_limit}

@app.post("/api/v1/params/{channel}")
async def api_v1_params_set(channel: str, request: Request):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    data = await request.json()
    ch_key = f'channel_{ch}'
    new_params = data.get('params', [])
    validated = []
    for p in new_params:
        if isinstance(p, str):
            validated.append({'path': p, 'mode': data.get('default_mode', 'distance'), 'enabled': True})
        elif isinstance(p, dict) and p.get('path'):
            validated.append({
                'path': p['path'],
                'mode': p.get('mode', 'distance'),
                'enabled': p.get('enabled', True),
            })
    SETTINGS_BASIC['dglab3'][ch_key]['avatar_params'] = validated
    if 'default_mode' in data:
        SETTINGS_BASIC['dglab3'][ch_key]['mode'] = data['default_mode']
    if 'strength_limit' in data:
        SETTINGS_BASIC['dglab3'][ch_key]['strength_limit'] = int(data['strength_limit'])
    SETTINGS['dglab3'][ch_key]['avatar_params'] = validated
    SETTINGS['dglab3'][ch_key]['mode'] = SETTINGS_BASIC['dglab3'][ch_key]['mode']
    SETTINGS['dglab3'][ch_key]['strength_limit'] = SETTINGS_BASIC['dglab3'][ch_key]['strength_limit']
    normalize_avatar_param_entries(SETTINGS['dglab3'][ch_key])
    config_save()
    async def _delayed_restart():
        await asyncio.sleep(0.5)
        logger.info("[params] Restarting engine to apply param changes...")
        await engine.restart()
    asyncio.create_task(_delayed_restart())
    return {'success': True, 'params': validated, 'restarting': True}

# --- Combo ---
@app.get("/api/v1/combo/{channel}")
async def api_v1_combo_get(channel: str):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    return {
        'combo': cfg.get('combo', {}),
        'shock': cfg.get('shock', {}),
        'touch': cfg.get('touch', {}),
        'trigger_range': cfg.get('trigger_range', {}),
    }

@app.post("/api/v1/combo/{channel}")
async def api_v1_combo_set(channel: str, request: Request):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    data = await request.json()
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    if 'combo' in data:
        cfg.setdefault('combo', {}).update(data['combo'])
    if 'shock' in data:
        for key in ('duration', 'wave_preset', 'wave_scale'):
            if key in data['shock']:
                cfg['shock'][key] = data['shock'][key]
    if 'touch' in data:
        for key in ('wave_preset', 'wave_scale', 'n_derivative'):
            if key in data['touch']:
                cfg['touch'][key] = data['touch'][key]
    if 'trigger_range' in data:
        cfg['trigger_range'].update(data['trigger_range'])
    for handler in handlers:
        if hasattr(handler, 'refresh_settings'):
            handler.refresh_settings()
    config_save()
    return {'success': True}

# --- Curve Mapping ---
DEFAULT_CURVE_POINTS = [{'x': 0, 'y': 0}, {'x': 1, 'y': 1}]
_curve_config = {}

def _get_curve_config_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable), 'curve_config.yaml')

def _load_curve_config():
    global _curve_config
    path = _get_curve_config_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            _curve_config = yaml.safe_load(f) or {}

def _save_curve_config():
    path = _get_curve_config_path()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.safe_dump(_curve_config, f, allow_unicode=True)
    os.replace(tmp, path)

def get_curve_points(param_path):
    if param_path and param_path in _curve_config:
        return _curve_config[param_path]
    if param_path and param_path.upper() in ('A', 'B'):
        return _curve_config.get(f'channel_{param_path.lower()}') or DEFAULT_CURVE_POINTS
    return DEFAULT_CURVE_POINTS

def get_curve_keys():
    return list(_curve_config.keys())

def apply_curve(value, points):
    if not points or value <= 0:
        return 0.0
    if value >= 1:
        return min(1.0, points[-1]['y'] if points else 1.0)
    for i in range(len(points) - 1):
        if value >= points[i]['x'] and value <= points[i + 1]['x']:
            dx = points[i + 1]['x'] - points[i]['x']
            if dx <= 0:
                return points[i]['y']
            t = (value - points[i]['x']) / dx
            return points[i]['y'] + t * (points[i + 1]['y'] - points[i]['y'])
    return points[-1]['y'] if points else value

@app.get("/api/v1/curve")
async def api_v1_curve_list():
    result = {}
    for key, pts in _curve_config.items():
        result[key] = pts
    return {'curves': result, 'default': DEFAULT_CURVE_POINTS}

@app.get("/api/v1/curve/{param_key:path}")
async def api_v1_curve_get(param_key: str):
    pts = get_curve_points(param_key)
    return {'key': param_key, 'points': pts}

@app.post("/api/v1/curve/{param_key:path}")
async def api_v1_curve_set(param_key: str, request: Request):
    data = await request.json()
    pts = data.get('points', [])
    validated = []
    for p in pts:
        x = max(0.0, min(1.0, float(p.get('x', 0))))
        y = max(0.0, min(1.0, float(p.get('y', 0))))
        validated.append({'x': round(x, 4), 'y': round(y, 4)})
    validated.sort(key=lambda p: p['x'])
    _curve_config[param_key] = validated
    _save_curve_config()
    return {'success': True, 'key': param_key, 'points': validated}

@app.delete("/api/v1/curve/{param_key:path}")
async def api_v1_curve_delete(param_key: str):
    if param_key in _curve_config:
        del _curve_config[param_key]
        _save_curve_config()
    return {'success': True}

_load_curve_config()
_load_overlimit_rules()

# --- Profile Management ---
PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable), 'profiles')

def _ensure_profiles_dir():
    os.makedirs(PROFILES_DIR, exist_ok=True)

def _safe_profile_name(name):
    return re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name.strip())[:50]

@app.get("/api/v1/profiles")
async def api_v1_profiles_list():
    _ensure_profiles_dir()
    profiles = []
    for f in sorted(os.listdir(PROFILES_DIR)):
        if f.endswith('.yaml'):
            profiles.append(f[:-5])
    return {'profiles': profiles}

@app.put("/api/v1/profiles/{name}")
async def api_v1_profiles_save(name: str):
    _ensure_profiles_dir()
    safe_name = _safe_profile_name(name)
    if not safe_name:
        raise HTTPException(400, 'Invalid name')
    profile_data = {
        'basic': copy.deepcopy(SETTINGS_BASIC),
        'advanced': strip_basic_settings(SETTINGS),
    }
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    with open(path, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(profile_data, fw, allow_unicode=True)
    logger.info(f"[profile] Saved profile: {safe_name}")
    return {'success': True, 'name': safe_name}

@app.post("/api/v1/profiles/{name}")
async def api_v1_profiles_load(name: str):
    safe_name = _safe_profile_name(name)
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    if not os.path.exists(path):
        raise HTTPException(404, 'Profile not found')
    try:
        with open(path, 'r', encoding='utf-8') as fr:
            profile_data = yaml.safe_load(fr)
        new_basic = merge_defaults(DEFAULT_SETTINGS_BASIC, profile_data.get('basic', {}))
        new_advanced = merge_defaults(DEFAULT_SETTINGS, profile_data.get('advanced', {}))
        for ch in ['channel_a', 'channel_b']:
            new_advanced['dglab3'][ch]['avatar_params'] = new_basic['dglab3'][ch]['avatar_params']
            new_advanced['dglab3'][ch]['mode'] = new_basic['dglab3'][ch]['mode']
            new_advanced['dglab3'][ch]['strength_limit'] = new_basic['dglab3'][ch]['strength_limit']
            normalize_avatar_param_entries(new_advanced['dglab3'][ch])
        new_advanced['ws']['master_uuid'] = SETTINGS['ws']['master_uuid']
        apply_hot_reloadable_settings(new_advanced, new_basic)
        config_save()
        logger.success(f"[profile] Loaded profile: {safe_name}")
        return {'success': True, 'name': safe_name}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.delete("/api/v1/profiles/{name}")
async def api_v1_profiles_delete(name: str):
    safe_name = _safe_profile_name(name)
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    if os.path.exists(path):
        os.remove(path)
        return {'success': True}
    raise HTTPException(404, 'Not found')


# --- OSC Recording / Playback ---
RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable), 'recordings')

_recording_state = {
    'active': False,
    'start_time': 0,
    'messages': [],
    'filename': None,
}

_playback_state = {
    'active': False,
    'filename': None,
    'progress': 0,
    'total': 0,
    'speed': 1.0,
    'loop': False,
    'stop_flag': False,
}

def _ensure_recordings_dir():
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

def _osc_record_hook(address, *args):
    """Global OSC handler for recording ALL params."""
    _overlimit_osc_hook(address, *args)
    if _recording_state['active']:
        elapsed_ms = (time.perf_counter() - _recording_state['start_time']) * 1000.0
        _recording_state['messages'].append({
            't': round(elapsed_ms, 3),
            'addr': address,
            'args': list(args),
        })

@app.post("/api/v1/recorder/start")
async def api_v1_recorder_start():
    if _recording_state['active']:
        return {'success': False, 'message': 'Already recording'}
    _ensure_recordings_dir()
    from datetime import datetime
    _recording_state['active'] = True
    _recording_state['start_time'] = time.perf_counter()
    _recording_state['messages'] = []
    _recording_state['filename'] = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    logger.success(f"[recorder] Started recording: {_recording_state['filename']}")
    return {'success': True, 'filename': _recording_state['filename']}

@app.post("/api/v1/recorder/stop")
async def api_v1_recorder_stop():
    if not _recording_state['active']:
        return {'success': False, 'message': 'Not recording'}
    _recording_state['active'] = False
    messages = _recording_state['messages']
    filename = _recording_state['filename']
    duration_ms = messages[-1]['t'] if messages else 0
    data = {
        'version': 1,
        'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'duration_ms': round(duration_ms, 3),
        'message_count': len(messages),
        'messages': messages,
    }
    filepath = os.path.join(RECORDINGS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    _recording_state['messages'] = []
    logger.success(f"[recorder] Stopped. Saved {len(messages)} messages ({duration_ms/1000:.1f}s) to {filename}")
    return {'success': True, 'filename': filename, 'message_count': len(messages), 'duration_ms': duration_ms}

@app.get("/api/v1/recorder/status")
async def api_v1_recorder_status():
    elapsed_ms = 0
    if _recording_state['active']:
        elapsed_ms = (time.perf_counter() - _recording_state['start_time']) * 1000.0
    return {
        'recording': _recording_state['active'],
        'filename': _recording_state['filename'],
        'message_count': len(_recording_state['messages']),
        'elapsed_ms': round(elapsed_ms, 0),
    }

@app.get("/api/v1/recordings")
async def api_v1_recordings_list():
    _ensure_recordings_dir()
    files = []
    for f in sorted(os.listdir(RECORDINGS_DIR), reverse=True):
        if f.endswith('.json'):
            filepath = os.path.join(RECORDINGS_DIR, f)
            try:
                size = os.path.getsize(filepath)
                with open(filepath, 'r', encoding='utf-8') as fp:
                    header = json.load(fp)
                files.append({
                    'name': f,
                    'size_kb': round(size / 1024, 1),
                    'duration_ms': header.get('duration_ms', 0),
                    'message_count': header.get('message_count', 0),
                    'recorded_at': header.get('recorded_at', ''),
                })
            except Exception:
                files.append({'name': f, 'size_kb': 0, 'duration_ms': 0, 'message_count': 0, 'recorded_at': ''})
    return {'recordings': files}

@app.delete("/api/v1/recordings/{filename}")
async def api_v1_recordings_delete(filename: str):
    filepath = os.path.join(RECORDINGS_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return {'success': True}
    raise HTTPException(404, 'Not found')

@app.post("/api/v1/playback/start")
async def api_v1_playback_start(request: Request):
    if _playback_state['active']:
        return {'success': False, 'message': 'Already playing'}
    data = await request.json()
    filename = data.get('filename')
    speed = float(data.get('speed', 1.0))
    loop = bool(data.get('loop', False))
    filepath = os.path.join(RECORDINGS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, 'File not found')
    _playback_state['stop_flag'] = False
    _playback_state['filename'] = filename
    _playback_state['speed'] = speed
    _playback_state['loop'] = loop
    _playback_state['progress'] = 0
    _playback_state['active'] = True
    th = Thread(target=_playback_worker, args=(filepath, speed, loop), daemon=True)
    th.start()
    return {'success': True, 'filename': filename}

@app.post("/api/v1/playback/stop")
async def api_v1_playback_stop():
    _playback_state['stop_flag'] = True
    return {'success': True}

@app.get("/api/v1/playback/status")
async def api_v1_playback_status():
    return {
        'active': _playback_state['active'],
        'filename': _playback_state['filename'],
        'progress': _playback_state['progress'],
        'total': _playback_state['total'],
        'speed': _playback_state['speed'],
        'loop': _playback_state['loop'],
    }

def _playback_worker(filepath, speed, loop):
    """Background thread: replay OSC messages with original timing."""
    from pythonosc.udp_client import SimpleUDPClient
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        messages = data.get('messages', [])
        _playback_state['total'] = len(messages)
        if not messages:
            return
        target_port = SETTINGS['osc']['listen_port']
        client = SimpleUDPClient('127.0.0.1', target_port)
        while True:
            start_time = time.perf_counter()
            for i, msg in enumerate(messages):
                if _playback_state['stop_flag']:
                    return
                target_s = (msg['t'] / speed) / 1000.0
                while True:
                    elapsed = time.perf_counter() - start_time
                    remaining = target_s - elapsed
                    if remaining <= 0:
                        break
                    if remaining > 0.005:
                        time.sleep(remaining * 0.8)
                addr = msg['addr']
                args = msg.get('args', [])
                try:
                    osc_args = []
                    for a in args:
                        if isinstance(a, bool):
                            osc_args.append(a)
                        elif isinstance(a, int):
                            osc_args.append(float(a))
                        else:
                            osc_args.append(a)
                    client.send_message(addr, osc_args if len(osc_args) != 1 else osc_args[0])
                except Exception:
                    pass
                _playback_state['progress'] = i + 1
            if not loop:
                break
            time.sleep(0.5)
    finally:
        _playback_state['active'] = False
        _playback_state['progress'] = 0

# --- Wave Presets ---
@app.get("/api/v1/wave_presets")
async def api_v1_wave_presets():
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    return {'presets': list(lib.presets.keys())}

@app.get("/api/v1/wave_presets/{preset_name}/preview")
async def api_v1_wave_preset_preview(preset_name: str):
    from srv.wave_preset import WavePresetLibrary
    from pulse_to_hex.dglab_pulse_converter import parse_pulse
    import math

    lib = WavePresetLibrary()
    preset = lib.get(preset_name)
    if not preset:
        raise HTTPException(404, 'preset not found')

    pulse_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dg-lab')
    pulse_file = os.path.join(pulse_dir, preset_name + '.pulse')
    if not os.path.exists(pulse_file):
        ops = preset.get('ops', [])
        strengths = []
        for op in ops:
            for i in range(4):
                strengths.append(int(op[8 + i * 2:8 + i * 2 + 2], 16))
        return {
            'name': preset_name,
            'sections': [{'points': [{'strength': s} for s in strengths]}],
        }

    with open(pulse_file, 'r', encoding='utf-8') as f:
        pulse_text = f.read().strip()

    header, sections = parse_pulse(pulse_text)
    speed = header.speed if header else 1

    result_sections = []
    for sec in sections:
        if not sec.enabled:
            continue
        if not sec.points:
            continue
        n_points = len(sec.points)
        duration = max(0, sec.duration)
        repeats = max(1, math.ceil(duration / n_points)) if duration > 0 else 1
        points = []
        for val, flag in sec.points:
            points.append({
                'strength': round(max(0, min(100, val))),
                'anchor': flag == 1,
            })
        result_sections.append({
            'freq_low': sec.freq_low,
            'freq_high': sec.freq_high,
            'freq_mode': sec.freq_mode,
            'duration': duration,
            'n_points': n_points,
            'repeats': repeats,
            'points': points,
        })

    return {
        'name': preset_name,
        'speed': speed,
        'rest_ticks': header.rest_ticks if header else 0,
        'sections': result_sections,
    }

@app.post("/api/v1/wave_presets/import")
async def api_v1_wave_presets_import(file: UploadFile = File(...)):
    """Import a wave preset from uploaded .pulse or .json file."""
    from pulse_to_hex.dglab_pulse_converter import convert_to_ops
    from srv.wave_preset import WavePresetLibrary, PRESET_DIR

    if not file.filename:
        raise HTTPException(400, 'empty filename')

    filename = file.filename
    content_bytes = await file.read()
    content = content_bytes.decode('utf-8', errors='replace').strip()

    if filename.endswith('.pulse'):
        try:
            ops, wavestrs, header, sections = convert_to_ops(content)
        except Exception as e:
            raise HTTPException(400, f'pulse parse failed: {e}')
        if not ops:
            raise HTTPException(400, 'no valid wave data in file')
        preset_name = filename.rsplit('.', 1)[0]
        preset_data = {
            'name': preset_name,
            'source_file': filename,
            'num_ops': len(ops),
            'header': header.__dict__ if header else None,
            'wavestrs': wavestrs,
        }
        out_path = PRESET_DIR / f'{preset_name}.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(preset_data, f, ensure_ascii=False, indent=2)
        dg_lab_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dg-lab')
        os.makedirs(dg_lab_dir, exist_ok=True)
        pulse_path = os.path.join(dg_lab_dir, filename)
        with open(pulse_path, 'w', encoding='utf-8') as f:
            f.write(content)
        lib = WavePresetLibrary()
        lib.reload()
        return {'result': 'OK', 'name': preset_name, 'ops': len(ops)}

    elif filename.endswith('.json'):
        try:
            preset_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f'invalid JSON: {e}')
        if 'wavestrs' not in preset_data and 'ops' not in preset_data:
            raise HTTPException(400, 'JSON must contain "wavestrs" or "ops"')
        preset_name = preset_data.get('name') or filename.rsplit('.', 1)[0]
        preset_data['name'] = preset_name
        out_path = PRESET_DIR / f'{preset_name}.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(preset_data, f, ensure_ascii=False, indent=2)
        lib = WavePresetLibrary()
        lib.reload()
        num_ops = preset_data.get('num_ops', 0)
        return {'result': 'OK', 'name': preset_name, 'ops': num_ops}

    else:
        raise HTTPException(400, 'unsupported format, use .pulse or .json')

@app.get("/api/v1/wave_preset/{channel}/{preset_name}/{duration}")
async def api_v1_wave_preset(channel: str, preset_name: str, duration: int):
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    preset = lib.get(preset_name)
    if not preset:
        raise HTTPException(404, 'preset not found')
    channel = channel.upper()
    if channel not in ['A', 'B']:
        channel = 'A'
    duration = min(max(duration, 1), 10)
    ops = preset['ops']
    ops_needed = duration * 10
    repeated = (ops * ((ops_needed // len(ops)) + 1))[:ops_needed]
    for i in range(0, len(repeated), 80):
        chunk = repeated[i:i+80]
        wavestr = json.dumps(chunk, separators=(',', ':'))
        await command_queue.put(CommandPriority.API, channel, 'wave', value=wavestr, source_id='api_wave_preset')
    return {'result': 'OK', 'ops_sent': len(repeated)}


# --- SPA catch-all routes ---
_SPA_PATHS = ["/dashboard", "/curve", "/combo", "/params", "/recorder",
              "/settings", "/strength", "/overlimit-rules", "/wave-test"]

for _spa_path in _SPA_PATHS:
    async def _spa_handler(_p=_spa_path):
        return _serve_spa()
    app.add_api_route(_spa_path, _spa_handler, methods=["GET"], include_in_schema=False)

# Mount static files for assets only (not root, to avoid interfering with WS/API)
if os.path.exists(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, 'assets')
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static_assets")

# --- Shared state ---
command_queue = CommandQueue()

# --- Frontend WebSocket push ---
_ws_clients: set[WebSocket] = set()
_ws_subscriptions: dict[WebSocket, set] = {}  # ws -> set of topics ('wave_A', 'wave_B', 'osc', 'status')

async def _ws_broadcast(topic: str, data: dict):
    """Send data to all clients subscribed to topic."""
    if not _ws_clients:
        return
    dead = []
    msg = json.dumps({'topic': topic, **data}, separators=(',', ':'))
    for ws in list(_ws_clients):
        if topic in _ws_subscriptions.get(ws, set()):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
        _ws_subscriptions.pop(ws, None)

def _ws_broadcast_sync(topic: str, data: dict):
    """Schedule WS broadcast as a task on the running event loop."""
    if not _ws_clients:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_ws_broadcast(topic, data))
    except RuntimeError:
        pass

@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    """Frontend WebSocket for real-time push.
    
    Client sends JSON to subscribe: {"subscribe": ["wave_A", "wave_B", "osc", "status"]}
    Server pushes: {"topic": "wave_A", "samples": [...]}
    """
    await ws.accept()
    _ws_clients.add(ws)
    _ws_subscriptions[ws] = set()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                if 'subscribe' in msg:
                    _ws_subscriptions[ws] = set(msg['subscribe'])
                if msg.get('ping'):
                    await ws.send_text(json.dumps({'pong': True}))
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(ws)
        _ws_subscriptions.pop(ws, None)

# OSC activity ring buffer
_osc_activity = collections.deque(maxlen=50)

def _record_osc_activity(address, value, channel, mode):
    event = {
        'time': time.time(),
        'address': address,
        'value': round(value, 4),
        'channel': channel,
        'mode': mode,
    }
    _osc_activity.appendleft(event)
    # Push to WS clients
    _ws_broadcast_sync('osc', {'event': event})

# Wave history ring buffer
_wave_history = {'A': collections.deque(maxlen=800), 'B': collections.deque(maxlen=800)}
_wave_history_last_update = {'A': 0.0, 'B': 0.0}
_wave_history_seq = {'A': 0, 'B': 0}

def _record_wave(channel, wavestr):
    try:
        channel = channel.upper()
        ops = json.loads(wavestr)
        samples = []
        for op in ops:
            for i in range(4):
                freq = int(op[i*2:i*2+2], 16)
                strength = int(op[8+i*2:10+i*2], 16)
                _wave_history_seq[channel] += 1
                _wave_history[channel].append({'s': strength, 'f': freq, 'seq': _wave_history_seq[channel]})
                samples.append({'s': strength, 'f': freq})
        _wave_history_last_update[channel] = time.monotonic()
        # Push to WS clients
        _ws_broadcast_sync(f'wave_{channel}', {
            'samples': samples,
            'seq': _wave_history_seq[channel],
        })
    except Exception:
        pass

def _clear_wave_history(channel):
    channel = channel.upper()
    if channel not in _wave_history:
        return
    _wave_history[channel].clear()
    _wave_history_last_update[channel] = 0.0

DGConnection.wave_observer = _record_wave
DGConnection.clear_observer = _clear_wave_history

def _get_wave_history_snapshot(channel):
    history = list(_wave_history[channel])
    if not history:
        return []
    last_update = _wave_history_last_update.get(channel, 0.0)
    zero_sample = {'s': 0, 'f': 10}
    if last_update <= 0.0:
        return history[-200:]
    elapsed_ms = max(0.0, (time.monotonic() - last_update) * 1000.0)
    elapsed_samples = int(elapsed_ms // WAVE_HISTORY_SAMPLE_MS)
    if elapsed_samples <= 0:
        return history[-200:]
    if elapsed_samples >= 200:
        return [zero_sample] * 200
    tail = history[-200:]
    if elapsed_samples >= len(tail):
        return [zero_sample] * len(tail)
    return tail[elapsed_samples:] + [zero_sample] * elapsed_samples

# --- Command Queue Processor ---
async def command_queue_processor(stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            cmd = await asyncio.wait_for(command_queue.get(), timeout=0.5)
            if cmd.action == 'osc_trigger':
                handler_fn = cmd.value['handler']
                await handler_fn(cmd.value['val'], context=cmd.value['context'])
            elif cmd.action == 'wave':
                await DGConnection.broadcast_wave(channel=cmd.channel, wavestr=cmd.value)
            elif cmd.action == 'clear':
                if not _wave_test_state['active']:
                    await DGConnection.broadcast_clear_wave(cmd.channel)
            command_queue.task_done()
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[command_queue] error: {e}")
            await asyncio.sleep(0.01)

# --- DG-LAB WebSocket handler ---
async def wshandler(connection):
    client = DGConnection(connection, SETTINGS=SETTINGS)
    await client.serve()

# --- Engine ---
class Engine:
    """Data processing engine: OSC listener, WebSocket server, command queue, handlers.
    
    Runs as async tasks on the same event loop as Uvicorn (no separate thread).
    """

    def __init__(self):
        self._stop_event: asyncio.Event | None = None
        self._tasks: list[asyncio.Task] = []
        self._transport = None
        self._ws_server = None
        self._running = False
        self.dispatcher: Dispatcher | None = None
        self.handlers: list = []

    @property
    def running(self):
        return self._running

    def _build_dispatcher_and_handlers(self):
        self.dispatcher = Dispatcher()
        self.dispatcher.set_default_handler(_osc_record_hook)
        self.handlers = []

        ShockHandler.set_command_queue(command_queue)
        ShockHandler.osc_activity_observer = _record_osc_activity
        ShockHandler._curve_getter = get_curve_points

        for chann in ['A', 'B']:
            config_chann_name = f'channel_{chann.lower()}'
            channel_handlers = {}
            avatar_params = SETTINGS['dglab3'][config_chann_name].get('avatar_params', [])
            for param_entry in avatar_params:
                if not param_entry.get('enabled', True):
                    logger.info(f"Channel {chann} skipping disabled param: {param_entry['path']}")
                    continue
                param_path = param_entry['path']
                param_mode = param_entry['mode']
                if param_mode not in channel_handlers:
                    channel_handlers[param_mode] = ShockHandler(
                        SETTINGS=SETTINGS,
                        DG_CONN=DGConnection,
                        channel_name=chann,
                        handler_mode=param_mode,
                    )
                    self.handlers.append(channel_handlers[param_mode])
                logger.success(f"Channel {chann} mode {param_mode} listening {param_path}")
                self.dispatcher.map(param_path, channel_handlers[param_mode].osc_handler)

        global handlers
        handlers = self.handlers

    async def start(self):
        """Start the engine as async tasks on the current event loop."""
        if self._running:
            logger.warning("[engine] Already running, stop first.")
            return

        self._build_dispatcher_and_handlers()
        self._stop_event = asyncio.Event()
        command_queue.clear()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(command_queue_processor(self._stop_event)),
            asyncio.create_task(_strength_boost_checker(self._stop_event)),
            asyncio.create_task(_wave_test_loop(self._stop_event)),
            asyncio.create_task(_ws_status_pusher(self._stop_event)),
        ]
        for handler in self.handlers:
            handler.start_background_jobs()

        # Start OSC server
        try:
            server = AsyncIOOSCUDPServer(
                (SETTINGS["osc"]["listen_host"], SETTINGS["osc"]["listen_port"]),
                self.dispatcher, asyncio.get_event_loop()
            )
            self._transport, _ = await server.create_serve_endpoint()
            logger.success(f'OSC Listening: {SETTINGS["osc"]["listen_host"]}:{SETTINGS["osc"]["listen_port"]}')
        except Exception:
            logger.error(traceback.format_exc())
            logger.error("OSC监听失败，可能存在端口冲突")
            await self._cleanup_tasks()
            return

        # Start DG-LAB WebSocket server
        try:
            self._ws_server = await wsserve(wshandler, SETTINGS['ws']["listen_host"], SETTINGS['ws']["listen_port"])
            logger.success(f'WS Listening: {SETTINGS["ws"]["listen_host"]}:{SETTINGS["ws"]["listen_port"]}')
        except Exception:
            logger.error(traceback.format_exc())
            logger.error("WS服务监听失败，可能存在端口冲突")
            if self._transport:
                self._transport.close()
                self._transport = None
            await self._cleanup_tasks()
            return

        self._running = True
        logger.info("[engine] Started.")

    async def stop(self):
        """Stop the engine gracefully."""
        if not self._running:
            return

        # Stop wave test if active
        if _wave_test_state['active']:
            _wave_test_state['active'] = False
            command_queue.set_enabled(CommandPriority.OSC_INTERACTION, True)
            command_queue.set_enabled(CommandPriority.OSC_PANEL, True)
            command_queue.set_enabled(CommandPriority.GAME, True)
            DGConnection._suppress_clear = False
            logger.info("[engine] Wave test stopped due to engine shutdown.")

        # Signal stop
        if self._stop_event:
            self._stop_event.set()

        logger.info("[engine] Stopping...")

        # Close servers
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
            self._ws_server = None
        if self._transport:
            self._transport.close()
            self._transport = None

        # Cancel tasks
        await self._cleanup_tasks()
        self._running = False
        logger.info("[engine] Stopped.")

    async def _cleanup_tasks(self):
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def restart(self):
        """Restart the engine."""
        logger.info("[engine] Restarting...")
        await self.stop()
        await self.start()

engine = Engine()

def _schedule_engine_restart():
    """Schedule engine restart from sync context."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(engine.restart())
    except RuntimeError:
        logger.error("[engine] Cannot schedule restart: no running event loop")

@app.on_event("startup")
async def on_startup():
    """Start the engine and config watcher when Uvicorn's event loop is ready."""
    await engine.start()
    asyncio.create_task(config_hot_reload_loop())

# --- Config save ---
def config_save():
    for path, data in [(CONFIG_FILENAME, SETTINGS), (CONFIG_FILENAME_BASIC, SETTINGS_BASIC)]:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fw:
            yaml.safe_dump(data, fw, allow_unicode=True)
        os.replace(tmp, path)

class ConfigFileInited(Exception):
    pass

def config_init():
    logger.info(f'Loading config: {CONFIG_FILENAME_BASIC}, {CONFIG_FILENAME}')
    global SETTINGS, SETTINGS_BASIC, SERVER_IP
    if not (os.path.exists(CONFIG_FILENAME) and os.path.exists(CONFIG_FILENAME_BASIC)):
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
        raise ConfigFileInited()

    SETTINGS, SETTINGS_BASIC = load_config_files()

    if SETTINGS.get('version', None) != CONFIG_FILE_VERSION or SETTINGS_BASIC.get('version', None) != CONFIG_FILE_VERSION:
        logger.error(f"配置文件版本不匹配！请删除 {CONFIG_FILENAME_BASIC} 和 {CONFIG_FILENAME} 后重启。")
        raise Exception(f'Config version mismatch.')
    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()

    reset_logger()
    update_config_mtimes()
    logger.success("配置加载完成 | Websocket 需要监听外来连接，如弹出防火墙提示请允许")

def main():
    if SETTINGS['general']['auto_open_qr_web_page'] and not os.environ.pop('SHOCKING_SKIP_OPEN', None):
        import webbrowser
        webbrowser.open_new_tab(f"http://127.0.0.1:{SETTINGS['web_server']['listen_port']}")
    else:
        info_ip = SETTINGS['web_server']['listen_host']
        if info_ip == '0.0.0.0':
            info_ip = get_current_ip()
        logger.success(f"请打开浏览器访问 http://{info_ip}:{SETTINGS['web_server']['listen_port']}")

    # Startup summary
    enabled_a = sum(1 for p in SETTINGS['dglab3']['channel_a']['avatar_params'] if p.get('enabled', True))
    enabled_b = sum(1 for p in SETTINGS['dglab3']['channel_b']['avatar_params'] if p.get('enabled', True))
    logger.info(f"Channel A: {enabled_a} params | Channel B: {enabled_b} params")
    logger.info(f"Web: :{SETTINGS['web_server']['listen_port']} | WS: :{SETTINGS['ws']['listen_port']} | OSC: :{SETTINGS['osc']['listen_port']}")

    # Run FastAPI with Uvicorn (engine starts via startup event)
    import uvicorn
    uvicorn.run(
        app,
        host=SETTINGS['web_server']['listen_host'],
        port=SETTINGS['web_server']['listen_port'],
        log_level="warning",
        access_log=False,
    )

if __name__ == "__main__":
    try:
        config_init()
        main()
    except ConfigFileInited:
        logger.success('未找到配置文件，启动配置向导...')
        import webbrowser
        port = SETTINGS['web_server']['listen_port']
        webbrowser.open_new_tab(f"http://127.0.0.1:{port}/setup")
        app.state.setup_complete = False

        @app.get('/api/v1/setup/poll')
        async def setup_poll():
            return {'done': getattr(app.state, 'setup_complete', False)}

        import uvicorn

        def _run_wizard_server():
            uvicorn.run(app, host='127.0.0.1', port=port, log_level="warning", access_log=False)

        wizard_th = Thread(target=_run_wizard_server, daemon=True)
        wizard_th.start()

        # Wait for setup completion then restart
        while not getattr(app.state, 'setup_complete', False):
            time.sleep(0.5)

        logger.success('配置向导完成，正在重启...')
        os.environ['SHOCKING_SKIP_OPEN'] = '1'
        config_save()
        time.sleep(1)
        _restart_program()
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("Unexpected Error.")
    logger.info('正在退出...')
    time.sleep(1)
