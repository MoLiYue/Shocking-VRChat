import asyncio
import collections
import yaml, uuid, os, sys, traceback, time, socket, re, json
from threading import Thread
from loguru import logger
import copy

from flask import Flask, render_template, redirect, request, jsonify
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
app = Flask(__name__,
            template_folder=os.path.join(RUNTIME_BASE_DIR, "templates"),
            static_folder=STATIC_DIR,
            static_url_path='')
WAVE_HISTORY_SAMPLE_MS = 25

CONFIG_FILE_VERSION  = 'v0.2'
CONFIG_FILENAME = f'settings-advanced-{CONFIG_FILE_VERSION}.yaml'
CONFIG_FILENAME_BASIC = f'settings-{CONFIG_FILE_VERSION}.yaml'
CONFIG_HOT_RELOAD_INTERVAL = 1.0
SETTINGS_BASIC = {
    'dglab3':{
        'channel_a': {
            'avatar_params': [
                {
                    'path': '/avatar/parameters/pcs/contact/enterPass',
                    'mode': 'distance',
                },
                {
                    'path': '/avatar/parameters/Shock/TouchAreaA',
                    'mode': 'distance',
                },
                {
                    'path': '/avatar/parameters/Shock/TouchAreaC',
                    'mode': 'distance',
                },
                {
                    'path': '/avatar/parameters/Shock/wildcard/*',
                    'mode': 'distance',
                },
            ],
            'mode': 'distance',
            'strength_limit': 100,
        },
        'channel_b': {
            'avatar_params': [
                {
                    'path': '/avatar/parameters/pcs/contact/enterPass',
                    'mode': 'distance',
                },
                {
                    'path': '/avatar/parameters/lms-penis-proximityA*',
                    'mode': 'distance',
                },
                {
                    'path': '/avatar/parameters/Shock/TouchAreaB',
                    'mode': 'distance',
                },
                {
                    'path': '/avatar/parameters/Shock/TouchAreaC',
                    'mode': 'distance',
                },
            ],
            'mode': 'distance',
            'strength_limit': 100,
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
            'base_strength': 0.18,
            'dynamic_range': 0.30,
            'texture_floor': 0.35,
            'wave_window_ops': 4,
            'wave_sample_step': 1.0,
            'wave_advance_samples': 4.0,
            'wave_envelope_curve': 'smoothstep',
        },
        'trigger_range': {
            'bottom': 0.0,
            'top': 1.0,
        },
        'touch': {
            'freq_ms': 10,
            'wave_preset': 'pulse-搓搓揉揉-9058076',
            'wave_scale': 0.35,
            'base_strength': 0.20,
            'dynamic_range': 0.25,
            'texture_floor': 0.45,
            'wave_window_ops': 4,
            'wave_sample_step': 1.0,
            'wave_advance_samples': 4.0,
            'wave_envelope_curve': 'smoothstep',
            'preset_bands': [
                {'threshold': 0.25, 'wave_preset': 'pulse-摸摸拍拍-9049275', 'wave_scale': 0.25},
                {'threshold': 0.55, 'wave_preset': 'pulse-搓搓揉揉-9058076', 'wave_scale': 0.35},
                {'threshold': 0.8, 'wave_preset': 'pulse-加速揉搓-9113608', 'wave_scale': 0.5},
            ],
            'n_derivative': 1,
            'derivative_params': [
                {'top': 1, 'bottom': 0},
                {'top': 5, 'bottom': 0},
                {'top': 50, 'bottom': 0},
                {'top': 500, 'bottom': 0},
            ],
        },
        'combo': {
            'switch_duration': 0.3,
        },
        'boost': {
            'value': 30,
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
            normalized.append({
                'path': entry,
                'mode': default_mode,
                'enabled': True,
            })
        elif isinstance(entry, dict):
            path = entry.get('path')
            if not path:
                logger.warning(f'Ignoring avatar param config without path: {entry}')
                continue
            normalized.append({
                'path': path,
                'mode': entry.get('mode', default_mode),
                'enabled': entry.get('enabled', True),
            })
        else:
            logger.warning(f'Ignoring invalid avatar param config: {entry}')
    channel_settings['avatar_params'] = normalized
    return channel_settings


def load_config_files():
    with open(CONFIG_FILENAME, 'r', encoding='utf-8') as fr:
        settings = yaml.safe_load(fr)
    with open(CONFIG_FILENAME_BASIC, 'r', encoding='utf-8') as fr:
        settings_basic = yaml.safe_load(fr)

    settings = merge_defaults(DEFAULT_SETTINGS, settings)
    settings_basic = merge_defaults(DEFAULT_SETTINGS_BASIC, settings_basic)

    if settings.get('version', None) != CONFIG_FILE_VERSION or settings_basic.get('version', None) != CONFIG_FILE_VERSION:
        raise Exception(
            f'Configuration file version mismatch: {CONFIG_FILENAME_BASIC} {CONFIG_FILENAME}'
        )

    if settings['ws']['master_uuid'] is None:
        settings['ws']['master_uuid'] = str(uuid.uuid4())

    for chann in ['channel_a', 'channel_b']:
        settings['dglab3'][chann]['avatar_params'] = settings_basic['dglab3'][chann]['avatar_params']
        settings['dglab3'][chann]['mode'] = settings_basic['dglab3'][chann]['mode']
        settings['dglab3'][chann]['strength_limit'] = settings_basic['dglab3'][chann]['strength_limit']
        normalize_avatar_param_entries(settings['dglab3'][chann])

    return settings, settings_basic


def reset_logger():
    logger.remove()
    logger.add(sys.stderr, level=SETTINGS['log_level'])


def update_config_mtimes():
    global CONFIG_MTIMES
    CONFIG_MTIMES = {
        CONFIG_FILENAME: os.path.getmtime(CONFIG_FILENAME) if os.path.exists(CONFIG_FILENAME) else None,
        CONFIG_FILENAME_BASIC: os.path.getmtime(CONFIG_FILENAME_BASIC) if os.path.exists(CONFIG_FILENAME_BASIC) else None,
    }


def has_config_file_changed():
    for path, previous_mtime in CONFIG_MTIMES.items():
        current_mtime = os.path.getmtime(path) if os.path.exists(path) else None
        if current_mtime != previous_mtime:
            return True
    return False


def apply_hot_reloadable_settings(new_settings, new_settings_basic):
    global SERVER_IP
    old_settings = copy.deepcopy(SETTINGS)
    old_settings_basic = copy.deepcopy(SETTINGS_BASIC)

    restart_required_reasons = []

    if new_settings['osc'] != old_settings['osc']:
        restart_required_reasons.append('osc')
        new_settings['osc'] = old_settings['osc']
    if new_settings['ws'] != old_settings['ws']:
        restart_required_reasons.append('ws')
        new_settings['ws'] = old_settings['ws']
    if new_settings['web_server'] != old_settings['web_server']:
        restart_required_reasons.append('web_server')
        new_settings['web_server'] = old_settings['web_server']
    if new_settings.get('SERVER_IP') != old_settings.get('SERVER_IP'):
        restart_required_reasons.append('SERVER_IP')
        new_settings['SERVER_IP'] = old_settings.get('SERVER_IP')
    if new_settings_basic['dglab3'] != old_settings_basic['dglab3']:
        old_basic = old_settings_basic['dglab3']
        new_basic = new_settings_basic['dglab3']
        if any(
            new_basic[ch]['avatar_params'] != old_basic[ch]['avatar_params'] or
            new_basic[ch]['mode'] != old_basic[ch]['mode']
            for ch in ['channel_a', 'channel_b']
        ):
            restart_required_reasons.append('avatar_params/mode')
            for ch in ['channel_a', 'channel_b']:
                new_settings_basic['dglab3'][ch]['avatar_params'] = old_basic[ch]['avatar_params']
                new_settings_basic['dglab3'][ch]['mode'] = old_basic[ch]['mode']
                new_settings['dglab3'][ch]['avatar_params'] = old_settings['dglab3'][ch]['avatar_params']
                new_settings['dglab3'][ch]['mode'] = old_settings['dglab3'][ch]['mode']

    SETTINGS.clear()
    SETTINGS.update(new_settings)
    SETTINGS_BASIC.clear()
    SETTINGS_BASIC.update(new_settings_basic)

    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()
    reset_logger()
    DGConnection.refresh_limits_from_settings(SETTINGS)

    for handler in handlers:
        if hasattr(handler, 'refresh_settings'):
            handler.refresh_settings()

    if restart_required_reasons:
        logger.warning(
            f"[hot-reload] Applied runtime-safe config changes. Restart required for: {', '.join(restart_required_reasons)}"
        )
    logger.success("[hot-reload] Configuration reloaded.")


def hot_reload_configs():
    try:
        new_settings, new_settings_basic = load_config_files()
        apply_hot_reloadable_settings(new_settings, new_settings_basic)
        update_config_mtimes()
    except Exception:
        logger.error(traceback.format_exc())
        logger.error("[hot-reload] Failed to reload configuration.")


def config_hot_reload_loop():
    while True:
        time.sleep(CONFIG_HOT_RELOAD_INTERVAL)
        if has_config_file_changed():
            hot_reload_configs()

def get_current_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((SETTINGS['general']['local_ip_detect']['host'], SETTINGS['general']['local_ip_detect']['port']))
    client_ip = s.getsockname()[0]
    s.close()
    return client_ip

@app.route('/get_ip')
def web_get_ip():
    return get_current_ip()

@app.route("/")
def web_index():
    return _serve_spa()

def _serve_spa():
    """Serve Vue SPA index.html, fallback to legacy templates."""
    spa_index = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(spa_index):
        return app.send_static_file('index.html')
    # Fallback: legacy template-based dashboard
    return redirect("/dashboard-legacy", code=302)

@app.route('/dashboard-legacy')
def web_dashboard_legacy():
    return render_template('dashboard.html')

@app.route("/qr")
def web_qr():
    return render_template('tiny-qr.html', content=get_qr_content())


def get_qr_content():
    return (
        f'https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://'
        f'{SERVER_IP}:{SETTINGS["ws"]["listen_port"]}/{SETTINGS["ws"]["master_uuid"]}'
    )

@app.after_request
async def after_request_hook(response):
    if request.args.get('ret') == 'status' and response.status_code == 200:
        response = jsonify(await api_v1_status())
    return response

class ClientNotAllowed(Exception):
    pass

@app.errorhandler(ClientNotAllowed)
def hendle_ClientNotAllowed(e):
    return {
        "error": "Client not allowed."
    }, 401

@app.errorhandler(Exception)
def handle_Exception(e):
    return {
        "error": str(e)
    } , 500

# Disallow (Video)
# User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.72 Safari/537.36\r\n
# User-Agent: NSPlayer/12.00.26100.2314 WMFSDK/12.00.26100.2314\r\n
# Allow (Text/Image)
# User-Agent: UnityPlayer/2022.3.22f1-DWR (UnityWebRequest/1.0, libcurl/8.5.0-DEV)\r\n
def allow_vrchat_only(func):
    async def wrapper(*args, **kwargs):
        ua = request.headers.get('User-Agent', '')
        if 'UnityPlayer' not in ua:
            raise ClientNotAllowed
        if 'NSPlayer' in ua or 'WMFSDK' in ua:
            raise ClientNotAllowed
        return await func(*args, **kwargs)
    return wrapper

@app.route('/api/v1/status')
async def api_v1_status():
    return {
        'healthy': 'ok',
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
                    'uuid': conn.uuid,
                }
            } for conn in srv.WS_CONNECTIONS
        ],
    }

@app.route('/api/v1/wave_history')
def api_v1_wave_history():
    return {'A': _get_wave_history_snapshot('A'), 'B': _get_wave_history_snapshot('B')}

@app.route('/api/v1/osc_activity')
def api_v1_osc_activity():
    return {'events': list(_osc_activity)}


@app.route('/api/v1/qr_payload')
def api_v1_qr_payload():
    return {'content': get_qr_content()}

@app.route('/api/v1/strength/<channel>/<action>/<int:value>', endpoint='api_v1_strength')
async def api_v1_strength(channel, action, value):
    """Adjust device strength. action: set/add/sub. value: 0-200."""
    channel = channel.upper()
    if channel == 'ALL':
        channels = ['A', 'B']
    elif channel in ('A', 'B'):
        channels = [channel]
    else:
        return {'error': 'invalid channel'}, 400
    mode_map = {'set': '2', 'add': '1', 'sub': '0'}
    mode = mode_map.get(action)
    if mode is None:
        return {'error': 'action must be set/add/sub'}, 400
    value = max(0, min(200, value))
    for ch in channels:
        for conn in srv.WS_CONNECTIONS:
            await conn.set_strength(ch, mode=mode, value=value, force=True)
    return {'result': 'OK', 'action': action, 'value': value, 'channels': channels}

# --- Strength Boost (temporary +N with auto-revert) ---
_strength_boost = {'A': 0, 'B': 0}
_strength_boost_expire = {'A': 0.0, 'B': 0.0}

@app.route('/api/v1/strength_boost/<channel>/<int:value>/<float:duration>', endpoint='api_v1_strength_boost')
@app.route('/api/v1/strength_boost/<channel>/<int:value>/<int:duration>', endpoint='api_v1_strength_boost_int')
async def api_v1_strength_boost(channel, value, duration):
    """Temporarily boost strength by value, auto-reverts after duration seconds."""
    channel = channel.upper()
    if channel == 'ALL':
        channels = ['A', 'B']
    elif channel in ('A', 'B'):
        channels = [channel]
    else:
        return {'error': 'invalid channel'}, 400
    value = max(1, min(100, value))
    duration = max(0.5, min(30.0, float(duration)))
    for ch in channels:
        already_boosted = _strength_boost[ch]
        if already_boosted == 0:
            # Apply new boost
            for conn in srv.WS_CONNECTIONS:
                await conn.set_strength(ch, mode='1', value=value, force=True)
            _strength_boost[ch] = value
        elif already_boosted != value:
            # Adjust to new boost level
            for conn in srv.WS_CONNECTIONS:
                await conn.set_strength(ch, mode='0', value=already_boosted, force=True)
                await conn.set_strength(ch, mode='1', value=value, force=True)
            _strength_boost[ch] = value
        # Reset/extend expiry
        _strength_boost_expire[ch] = time.time() + duration
    return {'result': 'OK', 'boost': value, 'duration': duration, 'channels': channels}

async def _strength_boost_checker():
    """Background task: revert expired strength boosts."""
    while True:
        await asyncio.sleep(0.1)
        now = time.time()
        for ch in ['A', 'B']:
            if _strength_boost[ch] > 0 and now >= _strength_boost_expire[ch]:
                boost_val = _strength_boost[ch]
                _strength_boost[ch] = 0
                for conn in srv.WS_CONNECTIONS:
                    await conn.set_strength(ch, mode='0', value=boost_val, force=True)
                logger.debug(f"[boost] channel={ch} reverted -{boost_val}")

@app.route('/api/v1/shock/<channel>/<second>', endpoint='api_v1_shock')
@allow_vrchat_only
async def api_v1_shock(channel, second):
    if channel == 'all':
        channels = ['A', 'B']
    else:
        channels = [channel]
    try: 
        second = float(second)
    except Exception:
        logger.warning('[API][shock] Invalid second, set to 1.')
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

@app.route('/api/v1/sendwave/<channel>/<repeat>/<wavedata>', endpoint='api_v1_sendwave')
@allow_vrchat_only
async def api_v1_sendwave(channel, repeat, wavedata):
    """API V1 Sendwave.

    Keyword arguments:
    channel -- A or B.
    repeat -- repeat times, 1 for 100ms, 1 to 80. Max 80 for json length limit.
    wavedata -- Coyote v3 wave format, eg. 0A0A0A0A64646464.
    """
    try:
        channel = channel.upper()
        if channel not in ['A', 'B']:
            raise Exception
    except:
        logger.warning('[API][sendwave] Invalid Channel, set to A.')
        channel = 'A'
    try:
        repeat = int(repeat)
        if repeat > 100 or repeat < 1:
            raise Exception
    except:
        logger.warning('[API][sendwave] Invalid repeat times, set to 10.')
        repeat = 10
    try:
        if not re.match(r'^([0-9A-F]{16})$', wavedata):
            raise Exception
    except:
        logger.warning('[API][sendwave] Invalid wave, set to 0A0A0A0A64646464.')
        wavedata = '0A0A0A0A64646464'
    wavestr = json.dumps([wavedata] * repeat, separators=(',', ':'))
    logger.debug(f'[API][sendwave] C:{channel} R:{repeat} W:{wavedata}')
    await command_queue.put(CommandPriority.API, channel, 'wave', value=wavestr, source_id='api_sendwave')
    return {'result': 'OK'}

def strip_basic_settings(settings: dict):
    ret = copy.deepcopy(settings)
    for chann in ['channel_a', 'channel_b']:
        del ret['dglab3'][chann]['avatar_params']
        del ret['dglab3'][chann]['mode'] 
        del ret['dglab3'][chann]['strength_limit'] 
    return ret

@app.route('/setup')
def web_setup_wizard():
    return render_template('setup_wizard.html')

@app.route('/api/v1/setup', methods=['POST'])
def api_v1_setup():
    global SETTINGS, SETTINGS_BASIC, SERVER_IP
    try:
        data = request.get_json()
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
        app.config['SETUP_COMPLETE'] = True
        return jsonify({'success': True, 'message': 'Configuration saved.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/v1/config', methods=['GET', 'HEAD', 'OPTIONS'])
def get_config():
    return {
        'basic': SETTINGS_BASIC,
        'advanced': strip_basic_settings(SETTINGS),
    }

@app.route('/api/v1/settings', methods=['POST'])
def api_v1_settings_update():
    """Update server settings (osc/ws/web_server). Auto-restarts for network changes."""
    data = request.get_json()
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
        # Schedule restart after response is sent
        def _delayed_restart():
            time.sleep(1)
            logger.info("[settings] Restarting due to network config change...")
            _restart_program()
        Thread(target=_delayed_restart, daemon=True).start()
    return jsonify({
        'success': True,
        'restart_needed': list(set(restart_needed)),
        'message': '已保存。' + ('程序正在重启...' if restart_needed else ''),
    })

def _restart_program():
    """Restart the current process. Works on both Windows and Linux."""
    import subprocess
    if getattr(sys, 'frozen', False):
        # PyInstaller bundled exe
        cmd = [sys.executable] + sys.argv[1:]
    else:
        cmd = [sys.executable] + sys.argv

    if sys.platform == 'win32':
        # Windows: os.execv doesn't replace process, use subprocess + exit
        subprocess.Popen(cmd, close_fds=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        os._exit(0)
    else:
        # Linux/Mac: os.execv replaces current process
        os.execv(cmd[0], cmd)

@app.route('/api/v1/params/<channel>', methods=['GET'])
def api_v1_params_get(channel):
    """Get avatar_params for a channel."""
    ch = channel.lower()
    if ch not in ('a', 'b'):
        return jsonify({'error': 'invalid channel'}), 400
    ch_key = f'channel_{ch}'
    params = SETTINGS_BASIC['dglab3'][ch_key].get('avatar_params', [])
    default_mode = SETTINGS_BASIC['dglab3'][ch_key].get('mode', 'distance')
    strength_limit = SETTINGS_BASIC['dglab3'][ch_key].get('strength_limit', 100)
    return jsonify({'params': params, 'default_mode': default_mode, 'strength_limit': strength_limit})

@app.route('/api/v1/params/<channel>', methods=['POST'])
def api_v1_params_set(channel):
    """Replace all avatar_params for a channel. Also update default_mode and strength_limit."""
    ch = channel.lower()
    if ch not in ('a', 'b'):
        return jsonify({'success': False, 'message': 'invalid channel'}), 400
    data = request.get_json()
    ch_key = f'channel_{ch}'
    # Update params (preserve enabled field)
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
    # Update default mode and strength limit if provided
    if 'default_mode' in data:
        SETTINGS_BASIC['dglab3'][ch_key]['mode'] = data['default_mode']
    if 'strength_limit' in data:
        SETTINGS_BASIC['dglab3'][ch_key]['strength_limit'] = int(data['strength_limit'])
    # Sync into SETTINGS (only enabled params are active)
    SETTINGS['dglab3'][ch_key]['avatar_params'] = validated
    SETTINGS['dglab3'][ch_key]['mode'] = SETTINGS_BASIC['dglab3'][ch_key]['mode']
    SETTINGS['dglab3'][ch_key]['strength_limit'] = SETTINGS_BASIC['dglab3'][ch_key]['strength_limit']
    normalize_avatar_param_entries(SETTINGS['dglab3'][ch_key])
    config_save()
    # Auto-restart to apply new param registrations
    def _delayed_restart():
        time.sleep(1)
        logger.info("[params] Restarting to apply param changes...")
        _restart_program()
    Thread(target=_delayed_restart, daemon=True).start()
    return jsonify({'success': True, 'params': validated, 'restarting': True})

@app.route('/api/v1/combo/<channel>', methods=['GET'])
def api_v1_combo_get(channel):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        return jsonify({'error': 'invalid channel'}), 400
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    return jsonify({
        'combo': cfg.get('combo', {}),
        'shock': cfg.get('shock', {}),
        'touch': cfg.get('touch', {}),
        'trigger_range': cfg.get('trigger_range', {}),
    })

@app.route('/api/v1/combo/<channel>', methods=['POST'])
def api_v1_combo_set(channel):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        return jsonify({'success': False, 'message': 'invalid channel'}), 400
    data = request.get_json()
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    # Update combo config
    if 'combo' in data:
        cfg.setdefault('combo', {}).update(data['combo'])
    # Update shock params
    if 'shock' in data:
        for key in ('duration', 'wave_preset', 'wave_scale'):
            if key in data['shock']:
                cfg['shock'][key] = data['shock'][key]
    # Update touch params
    if 'touch' in data:
        for key in ('wave_preset', 'wave_scale', 'n_derivative'):
            if key in data['touch']:
                cfg['touch'][key] = data['touch'][key]
    # Update trigger_range
    if 'trigger_range' in data:
        cfg['trigger_range'].update(data['trigger_range'])
    # Hot reload handlers
    for handler in handlers:
        if hasattr(handler, 'refresh_settings'):
            handler.refresh_settings()
    config_save()
    return jsonify({'success': True})

# --- Curve Mapping ---
DEFAULT_CURVE_POINTS = [{'x': 0, 'y': 0}, {'x': 0.1, 'y': 0}, {'x': 1, 'y': 1}]  # ReLU
_curve_config = {'a': None, 'b': None}  # None means use default

def _load_curve_config():
    global _curve_config
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable), 'curve_config.yaml')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            _curve_config['a'] = data.get('channel_a')
            _curve_config['b'] = data.get('channel_b')

def _save_curve_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable), 'curve_config.yaml')
    data = {'channel_a': _curve_config['a'], 'channel_b': _curve_config['b']}
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True)

def get_curve_points(channel):
    ch = channel.lower()
    return _curve_config.get(ch) or DEFAULT_CURVE_POINTS

def apply_curve(value, points):
    """Linearly interpolate value through control points."""
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
    # value beyond last point
    return points[-1]['y'] if points else value

@app.route('/api/v1/curve/<channel>', methods=['GET'])
def api_v1_curve_get(channel):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        return jsonify({'error': 'invalid channel'}), 400
    pts = _curve_config.get(ch) or DEFAULT_CURVE_POINTS
    return jsonify({'channel': ch, 'points': pts})

@app.route('/api/v1/curve/<channel>', methods=['POST'])
def api_v1_curve_set(channel):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        return jsonify({'success': False, 'message': 'invalid channel'}), 400
    data = request.get_json()
    pts = data.get('points', [])
    # Validate
    validated = []
    for p in pts:
        x = max(0.0, min(1.0, float(p.get('x', 0))))
        y = max(0.0, min(1.0, float(p.get('y', 0))))
        validated.append({'x': round(x, 4), 'y': round(y, 4)})
    validated.sort(key=lambda p: p['x'])
    _curve_config[ch] = validated
    _save_curve_config()
    # Update handlers
    for handler in handlers:
        if hasattr(handler, 'refresh_curve'):
            handler.refresh_curve()
    return jsonify({'success': True, 'points': validated})

_load_curve_config()

# --- Profile Management ---
PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable), 'profiles')

def _ensure_profiles_dir():
    os.makedirs(PROFILES_DIR, exist_ok=True)

def _safe_profile_name(name):
    return re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name.strip())[:50]

@app.route('/api/v1/profiles', methods=['GET'])
def api_v1_profiles_list():
    _ensure_profiles_dir()
    profiles = []
    for f in sorted(os.listdir(PROFILES_DIR)):
        if f.endswith('.yaml'):
            profiles.append(f[:-5])
    return jsonify({'profiles': profiles})

@app.route('/api/v1/profiles/<name>', methods=['PUT'])
def api_v1_profiles_save(name):
    _ensure_profiles_dir()
    safe_name = _safe_profile_name(name)
    if not safe_name:
        return jsonify({'success': False, 'message': 'Invalid name'}), 400
    profile_data = {
        'basic': copy.deepcopy(SETTINGS_BASIC),
        'advanced': strip_basic_settings(SETTINGS),
    }
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    with open(path, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(profile_data, fw, allow_unicode=True)
    logger.info(f"[profile] Saved profile: {safe_name}")
    return jsonify({'success': True, 'name': safe_name})

@app.route('/api/v1/profiles/<name>', methods=['POST'])
def api_v1_profiles_load(name):
    safe_name = _safe_profile_name(name)
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    if not os.path.exists(path):
        return jsonify({'success': False, 'message': 'Profile not found'}), 404
    try:
        with open(path, 'r', encoding='utf-8') as fr:
            profile_data = yaml.safe_load(fr)
        # Write to config files then hot-reload
        new_basic = merge_defaults(DEFAULT_SETTINGS_BASIC, profile_data.get('basic', {}))
        new_advanced = merge_defaults(DEFAULT_SETTINGS, profile_data.get('advanced', {}))
        # Restore basic fields into advanced
        for ch in ['channel_a', 'channel_b']:
            new_advanced['dglab3'][ch]['avatar_params'] = new_basic['dglab3'][ch]['avatar_params']
            new_advanced['dglab3'][ch]['mode'] = new_basic['dglab3'][ch]['mode']
            new_advanced['dglab3'][ch]['strength_limit'] = new_basic['dglab3'][ch]['strength_limit']
            normalize_avatar_param_entries(new_advanced['dglab3'][ch])
        # Preserve ws uuid and non-hot-reloadable network settings
        new_advanced['ws']['master_uuid'] = SETTINGS['ws']['master_uuid']
        apply_hot_reloadable_settings(new_advanced, new_basic)
        config_save()
        logger.success(f"[profile] Loaded profile: {safe_name}")
        return jsonify({'success': True, 'name': safe_name})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/v1/profiles/<name>', methods=['DELETE'])
def api_v1_profiles_delete(name):
    safe_name = _safe_profile_name(name)
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    if os.path.exists(path):
        os.remove(path)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Not found'}), 404

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
    # Record if active
    if _recording_state['active']:
        elapsed_ms = (time.perf_counter() - _recording_state['start_time']) * 1000.0
        _recording_state['messages'].append({
            't': round(elapsed_ms, 3),
            'addr': address,
            'args': list(args),
        })

@app.route('/api/v1/recorder/start', methods=['POST'])
def api_v1_recorder_start():
    if _recording_state['active']:
        return jsonify({'success': False, 'message': 'Already recording'})
    _ensure_recordings_dir()
    from datetime import datetime
    _recording_state['active'] = True
    _recording_state['start_time'] = time.perf_counter()
    _recording_state['messages'] = []
    _recording_state['filename'] = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    logger.success(f"[recorder] Started recording: {_recording_state['filename']}")
    return jsonify({'success': True, 'filename': _recording_state['filename']})

@app.route('/api/v1/recorder/stop', methods=['POST'])
def api_v1_recorder_stop():
    if not _recording_state['active']:
        return jsonify({'success': False, 'message': 'Not recording'})
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
    return jsonify({'success': True, 'filename': filename, 'message_count': len(messages), 'duration_ms': duration_ms})

@app.route('/api/v1/recorder/status')
def api_v1_recorder_status():
    elapsed_ms = 0
    if _recording_state['active']:
        elapsed_ms = (time.perf_counter() - _recording_state['start_time']) * 1000.0
    return jsonify({
        'recording': _recording_state['active'],
        'filename': _recording_state['filename'],
        'message_count': len(_recording_state['messages']),
        'elapsed_ms': round(elapsed_ms, 0),
    })

@app.route('/api/v1/recordings')
def api_v1_recordings_list():
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
    return jsonify({'recordings': files})

@app.route('/api/v1/recordings/<filename>', methods=['DELETE'])
def api_v1_recordings_delete(filename):
    filepath = os.path.join(RECORDINGS_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Not found'}), 404

@app.route('/api/v1/playback/start', methods=['POST'])
def api_v1_playback_start():
    if _playback_state['active']:
        return jsonify({'success': False, 'message': 'Already playing'})
    data = request.get_json()
    filename = data.get('filename')
    speed = float(data.get('speed', 1.0))
    loop = bool(data.get('loop', False))
    filepath = os.path.join(RECORDINGS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File not found'}), 404
    _playback_state['stop_flag'] = False
    _playback_state['filename'] = filename
    _playback_state['speed'] = speed
    _playback_state['loop'] = loop
    _playback_state['progress'] = 0
    _playback_state['active'] = True
    # Start playback in background thread
    th = Thread(target=_playback_worker, args=(filepath, speed, loop), daemon=True)
    th.start()
    return jsonify({'success': True, 'filename': filename})

@app.route('/api/v1/playback/stop', methods=['POST'])
def api_v1_playback_stop():
    _playback_state['stop_flag'] = True
    return jsonify({'success': True})

@app.route('/api/v1/playback/status')
def api_v1_playback_status():
    return jsonify({
        'active': _playback_state['active'],
        'filename': _playback_state['filename'],
        'progress': _playback_state['progress'],
        'total': _playback_state['total'],
        'speed': _playback_state['speed'],
        'loop': _playback_state['loop'],
    })

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

        # Send to our own OSC port so the main program processes it
        target_port = SETTINGS['osc']['listen_port']
        target_host = '127.0.0.1'
        client = SimpleUDPClient(target_host, target_port)

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
                    # Ensure correct types for OSC (JSON may lose float vs int distinction)
                    osc_args = []
                    for a in args:
                        if isinstance(a, bool):
                            osc_args.append(a)
                        elif isinstance(a, int):
                            osc_args.append(float(a))  # VRChat params are typically float
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

@app.route('/api/v1/wave_presets')
def api_v1_wave_presets():
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    return {'presets': list(lib.presets.keys())}

@app.route('/api/v1/wave_presets/<preset_name>/preview')
def api_v1_wave_preset_preview(preset_name):
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    preset = lib.get(preset_name)
    if not preset:
        return {'error': 'preset not found'}, 404
    # Return downsampled data for visualization (max 200 points)
    samples = preset.get('strength_samples', [])
    freq = preset.get('freq_samples', [])
    if len(samples) > 200:
        step = len(samples) / 200
        samples = [samples[int(i * step)] for i in range(200)]
        freq = [freq[int(i * step)] for i in range(200)]
    return {
        'name': preset_name,
        'ops_count': len(preset.get('ops', [])),
        'duration_ms': len(preset.get('ops', [])) * 100,
        'strength_samples': [round(s, 3) for s in samples],
        'freq_samples': [round(f, 1) for f in freq],
    }

@app.route('/api/v1/wave_preset/<channel>/<preset_name>/<int:duration>')
async def api_v1_wave_preset(channel, preset_name, duration):
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    preset = lib.get(preset_name)
    if not preset:
        return {'error': 'preset not found'}, 404
    channel = channel.upper()
    if channel not in ['A', 'B']:
        channel = 'A'
    duration = min(max(duration, 1), 10)
    # Send wave data in chunks to cover duration
    ops = preset['ops']
    ops_needed = duration * 10  # 10 ops per second
    repeated = (ops * ((ops_needed // len(ops)) + 1))[:ops_needed]
    for i in range(0, len(repeated), 80):
        chunk = repeated[i:i+80]
        wavestr = json.dumps(chunk, separators=(',', ':'))
        await command_queue.put(CommandPriority.API, channel, 'wave', value=wavestr, source_id='api_wave_preset')
    return {'result': 'OK', 'ops_sent': len(repeated)}

# SPA catch-all: serve index.html for Vue Router paths
@app.route('/dashboard')
@app.route('/curve')
@app.route('/combo')
@app.route('/params')
@app.route('/recorder')
@app.route('/setup')
@app.route('/settings')
def spa_catch_all():
    return _serve_spa()

command_queue = CommandQueue()

# OSC activity ring buffer for dashboard live feedback
_osc_activity = collections.deque(maxlen=50)

def _record_osc_activity(address, value, channel, mode):
    _osc_activity.appendleft({
        'time': time.time(),
        'address': address,
        'value': round(value, 4),
        'channel': channel,
        'mode': mode,
    })

# Wave history ring buffer for dashboard visualization
_wave_history = {'A': collections.deque(maxlen=800), 'B': collections.deque(maxlen=800)}
_wave_history_last_update = {'A': 0.0, 'B': 0.0}

def _record_wave(channel, wavestr):
    """Parse wavestr and append strength samples to history."""
    try:
        channel = channel.upper()
        ops = json.loads(wavestr)
        for op in ops:
            # Each op is 16 hex chars: 8 freq + 8 strength (4 sub-steps)
            strengths = [int(op[8+i*2:10+i*2], 16) for i in range(4)]
            _wave_history[channel].extend(strengths)
        _wave_history_last_update[channel] = time.monotonic()
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
    if last_update <= 0.0:
        return history[-200:]

    elapsed_ms = max(0.0, (time.monotonic() - last_update) * 1000.0)
    elapsed_samples = int(elapsed_ms // WAVE_HISTORY_SAMPLE_MS)

    # Only pad zeros after data stops arriving (indicates playback ended)
    if elapsed_samples <= 0:
        return history[-200:]
    if elapsed_samples >= 200:
        return [0] * 200

    # Take the most recent samples and pad trailing zeros for elapsed silence
    tail = history[-200:]
    if elapsed_samples >= len(tail):
        return [0] * len(tail)
    return tail[elapsed_samples:] + [0] * elapsed_samples


async def command_queue_processor():
    """Process commands from the priority queue."""
    while True:
        try:
            cmd = await command_queue.get()
            if cmd.action == 'osc_trigger':
                handler_fn = cmd.value['handler']
                await handler_fn(cmd.value['val'], context=cmd.value['context'])
            elif cmd.action == 'wave':
                await DGConnection.broadcast_wave(channel=cmd.channel, wavestr=cmd.value)
            elif cmd.action == 'clear':
                await DGConnection.broadcast_clear_wave(cmd.channel)
            command_queue.task_done()
        except Exception as e:
            logger.error(f"[command_queue] error: {e}")
            await asyncio.sleep(0.01)


async def wshandler(connection):
    client = DGConnection(connection, SETTINGS=SETTINGS)
    await client.serve()

async def async_main():
    asyncio.ensure_future(command_queue_processor())
    asyncio.ensure_future(_strength_boost_checker())
    for handler in handlers:
        handler.start_background_jobs()
    try: 
        server = AsyncIOOSCUDPServer((SETTINGS["osc"]["listen_host"], SETTINGS["osc"]["listen_port"]), dispatcher, asyncio.get_event_loop())
        logger.success(f'OSC Listening: {SETTINGS["osc"]["listen_host"]}:{SETTINGS["osc"]["listen_port"]}')
        transport, protocol = await server.create_serve_endpoint()
        # await wsserve(wshandler, "127.0.0.1", 8765)
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("OSC UDP Recevier listen failed.")
        logger.error("OSC监听失败，可能存在端口冲突")
        return
    try: 
        async with wsserve(wshandler, SETTINGS['ws']["listen_host"], SETTINGS['ws']["listen_port"]):
            await asyncio.Future()  # run forever
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("Websocket server listen failed.")
        logger.error("WS服务监听失败，可能存在端口冲突")
        return

    transport.close()

def async_main_wrapper():
    """Not async Wrapper around async_main to run it as target function of Thread"""
    asyncio.run(async_main())

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
        raise Exception(f'Config version mismatch. Delete {CONFIG_FILENAME_BASIC} and {CONFIG_FILENAME} to regenerate.')
    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()

    reset_logger()
    update_config_mtimes()
    logger.success("配置加载完成 | Websocket 需要监听外来连接，如弹出防火墙提示请允许")

def main():
    global dispatcher, handlers
    dispatcher = Dispatcher()
    # Record ALL OSC messages (not just registered params) when recording is active
    dispatcher.set_default_handler(_osc_record_hook)
    handlers = []

    ShockHandler.set_command_queue(command_queue)
    ShockHandler.osc_activity_observer = _record_osc_activity
    ShockHandler._curve_getter = get_curve_points

    for chann in ['A', 'B']:
        config_chann_name = f'channel_{chann.lower()}'
        channel_handlers = {}
        for param_entry in SETTINGS['dglab3'][config_chann_name]['avatar_params']:
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
                handlers.append(channel_handlers[param_mode])
            logger.success(f"Channel {chann} mode {param_mode} listening {param_path}")
            dispatcher.map(param_path, channel_handlers[param_mode].osc_handler)
    
    th = Thread(target=async_main_wrapper, daemon=True)
    th.start()
    reload_th = Thread(target=config_hot_reload_loop, daemon=True)
    reload_th.start()

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

    app.run(SETTINGS['web_server']['listen_host'], SETTINGS['web_server']['listen_port'], debug=False)

if __name__ == "__main__":
    try:
        config_init()
        main()
    except ConfigFileInited:
        logger.success('未找到配置文件，启动配置向导...')
        import webbrowser
        port = SETTINGS['web_server']['listen_port']
        webbrowser.open_new_tab(f"http://127.0.0.1:{port}/setup")
        app.config['SETUP_COMPLETE'] = False
        # Run wizard web server in a thread so we can detect completion
        from threading import Event
        _setup_done = Event()

        @app.route('/api/v1/setup/poll')
        def setup_poll():
            return jsonify({'done': app.config.get('SETUP_COMPLETE', False)})

        def _run_wizard_server():
            app.run('127.0.0.1', port, debug=False, use_reloader=False)

        wizard_th = Thread(target=_run_wizard_server, daemon=True)
        wizard_th.start()

        # Wait for setup completion then restart into main
        import time as _time
        while not app.config.get('SETUP_COMPLETE', False):
            _time.sleep(0.5)

        logger.success('配置向导完成，正在重启...')
        # Set env var to skip opening browser on this restart only (browser already open)
        os.environ['SHOCKING_SKIP_OPEN'] = '1'
        config_save()
        time.sleep(1)
        _restart_program()
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("Unexpected Error.")
    logger.info('正在退出...')
    time.sleep(1)
