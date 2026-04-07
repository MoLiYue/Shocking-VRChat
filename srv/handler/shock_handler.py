import numpy as np
import collections
from .base_handler import BaseHandler
from loguru import logger
import time, asyncio, math, json

from ..connector.coyotev3ws import DGConnection
from ..wave_preset import WavePresetLibrary


class ShockHandler(BaseHandler):
    _wave_library = WavePresetLibrary()

    def __init__(self, SETTINGS: dict, DG_CONN: DGConnection, channel_name: str, handler_mode: str = None) -> None:
        self.SETTINGS = SETTINGS
        self.DG_CONN = DG_CONN
        self.channel = channel_name.upper()
        self.shock_settings = SETTINGS['dglab3'][f'channel_{channel_name.lower()}']
        self.mode_config    = self.shock_settings['mode_config']

        self.shock_mode = handler_mode or self.shock_settings['mode']
        
        if self.shock_mode == 'distance':
            self._handler = self.handler_distance
        elif self.shock_mode == 'shock':
            self._handler = self.handler_shock
        elif self.shock_mode == 'touch':
            self._handler = self.handler_touch
        else:
            raise ValueError(f"Not supported mode: {self.shock_mode}")
        
        self.bg_wave_update_time_window = 0.1
        self.bg_wave_current_strength = 0

        self.touch_dist_arr = collections.deque(maxlen=20)
        self.dynamic_wave_index = 0
        self.active_dynamic_preset = None

        self.to_clear_time    = 0
        self.is_cleared       = True
    
    def start_background_jobs(self):
        # logger.info(f"Channel: {self.channel}, background job started.")
        asyncio.ensure_future(self.clear_check())
        # if self.shock_mode == 'shock':
        #     asyncio.ensure_future(self.feed_wave())
        if self.shock_mode == 'distance':
            asyncio.ensure_future(self.distance_background_wave_feeder())
        elif self.shock_mode == 'touch':
            asyncio.ensure_future(self.touch_background_wave_feeder())

    def osc_handler(self, address, *args):
        val = self.param_sanitizer(args)
        context = {
            'address': address,
            'raw_args': list(args),
            'sanitized_value': val,
            'mode': self.shock_mode,
            'channel': self.channel,
        }
        asyncio.ensure_future(self._handler(val, context=context))
        return None

    @staticmethod
    def summarize_wave(wavestr):
        try:
            ops = json.loads(wavestr)
            if not ops:
                return 'ops=0'
            return f"ops={len(ops)} first={ops[0]} last={ops[-1]}"
        except Exception:
            return f"wavestr={str(wavestr)[:48]}"

    def log_trigger(self, context, *, value, normalized=None, extra=''):
        param = context.get('address') if context else '-'
        raw = context.get('raw_args') if context else [value]
        msg = (
            f"[trigger] channel={self.channel} mode={self.shock_mode} "
            f"param={param} raw={raw} value={value:.3f}"
        )
        if normalized is not None:
            msg += f" normalized={normalized:.3f}"
        if extra:
            msg += f" {extra}"
        logger.info(msg)

    def log_output(self, *, source, strength=None, wave=None, extra=''):
        msg = f"[output] channel={self.channel} mode={self.shock_mode} source={source}"
        if strength is not None:
            msg += f" strength={strength:.3f}"
        if wave is not None:
            msg += f" {self.summarize_wave(wave)}"
        if extra:
            msg += f" {extra}"
        logger.info(msg)

    async def clear_check(self):
        # logger.info(f'Channel {self.channel} started clear check.')
        sleep_time = 0.05
        while 1:
            await asyncio.sleep(sleep_time)
            current_time = time.time()
            # logger.debug(f"{str(self.is_cleared)}, {current_time}, {self.to_clear_time}")
            if not self.is_cleared and current_time > self.to_clear_time:
                self.is_cleared = True
                self.bg_wave_current_strength = 0
                self.touch_dist_arr.clear()
                self.dynamic_wave_index = 0
                self.active_dynamic_preset = None
                await self.DG_CONN.broadcast_clear_wave(self.channel)
                logger.info(f"[clear] channel={self.channel} mode={self.shock_mode} reason=timeout")
    
    async def feed_wave(self):
        raise NotImplemented
        logger.info(f'Channel {self.channel} started wave feeding.')
        sleep_time = 1
        while 1:
            await asyncio.sleep(sleep_time)
            await self.DG_CONN.broadcast_wave(channel=self.channel, wavestr=self.shock_settings['shock_wave'])

    async def set_clear_after(self, val):
        self.is_cleared = False
        self.to_clear_time = time.time() + val

    @staticmethod
    def generate_wave_100ms(freq, from_, to_):
        assert 0 <= from_ <= 1, "Invalid wave generate."
        assert 0 <= to_   <= 1, "Invalid wave generate."
        from_ = int(100*from_)
        to_   = int(100*to_)
        ret = ["{:02X}".format(freq)]*4
        delta = (to_ - from_) // 4
        ret += ["{:02X}".format(min(max(from_ + delta*i, 0),100)) for i in range(1,5,1)]
        ret = ''.join(ret)
        return json.dumps([ret],separators=(',', ':'))

    @staticmethod
    def generate_wave_100ms_improved(freq, from_, to_, *, steps=4, curve="smoothstep"):
        """
        Generate a 100ms DG wave (4x25ms sub-steps by default).
        Returns wavestr: JSON string like ["0A0A0A0A14191E23"]

        freq: int (0-255, but DG commonly 10..240)
        from_, to_: float in [0,1]
        steps: number of sub-steps in 100ms (DG commonly 4)
        curve: "linear" | "smoothstep" | "ease_in_out_sine"
        """
        if not (0 <= from_ <= 1) or not (0 <= to_ <= 1):
            raise ValueError("from_ and to_ must be in [0,1]")
        if steps <= 0:
            raise ValueError("steps must be > 0")

        # clamp freq to byte
        freq = int(freq)
        freq = max(0, min(255, freq))

        from_i = int(round(from_ * 100))
        to_i   = int(round(to_   * 100))

        def apply_curve(t: float) -> float:
            t = max(0.0, min(1.0, t))
            if curve == "linear":
                return t
            if curve == "smoothstep":
                # 3t^2 - 2t^3
                return t * t * (3.0 - 2.0 * t)
            if curve == "ease_in_out_sine":
                # 0.5 - 0.5*cos(pi*t)
                return 0.5 - 0.5 * math.cos(math.pi * t)
            raise ValueError(f"unknown curve: {curve}")

        # Build strengths for each 25ms slice: i=1..steps
        strengths = []
        for i in range(1, steps + 1):
            t = apply_curve(i / steps)
            v = from_ + (to_ - from_) * t
            si = int(round(v * 100))
            si = max(0, min(100, si))
            strengths.append(si)

        # Guarantee last sample hits to_i exactly (avoid accumulated rounding error)
        strengths[-1] = max(0, min(100, to_i))

        # Pack: 4 freq bytes + 4 strength bytes (if steps!=4, we still pack exactly `steps` strength bytes)
        # DG 的 100ms 帧通常要求 4 个 strength 字节；如果你要保持协议一致，建议 steps=4。
        freq_hex = f"{freq:02X}" * 4
        strength_hex = "".join(f"{s:02X}" for s in strengths)

        # If steps != 4, the hex length won't be 16 (8 bytes). Keep steps=4 for DG 100ms op.
        if steps != 4:
            raise ValueError("DG 100ms op expects 4 strength bytes; please keep steps=4.")

        ret = freq_hex + strength_hex
        return json.dumps([ret], separators=(",", ":"))
    
    def normalize_distance(self, distance):
        out_distance = 0
        trigger_bottom = self.mode_config['trigger_range']['bottom']
        trigger_top = self.mode_config['trigger_range']['top']
        if distance > self.mode_config['trigger_range']['bottom']:
            out_distance = (
                    distance - trigger_bottom
                ) / (
                    trigger_top - trigger_bottom
                )
            out_distance = 1 if out_distance > 1 else out_distance
        return out_distance

    @staticmethod
    def normalize_between(value, bottom, top):
        if top <= bottom:
            logger.warning(f'Invalid normalize range: bottom={bottom}, top={top}.')
            return 0
        clamped = min(max(value, bottom), top)
        return (clamped - bottom) / (top - bottom)

    def get_mode_conf(self, mode_name):
        return self.mode_config.get(mode_name, {})

    def build_dynamic_wave(self, mode_name, from_strength, to_strength, *, preset_name=None, wave_scale=None):
        mode_conf = self.get_mode_conf(mode_name)
        preset_name = preset_name if preset_name is not None else mode_conf.get('wave_preset')
        wave_scale = mode_conf.get('wave_scale', 1.0) if wave_scale is None else wave_scale
        wave_scale = max(0.0, min(1.0, wave_scale))
        if preset_name:
            if preset_name != self.active_dynamic_preset:
                self.dynamic_wave_index = 0
                self.active_dynamic_preset = preset_name
            self.dynamic_wave_index += 1
            scaled_strength = to_strength * wave_scale
            preset_wave = self._wave_library.build_scaled_single_op(
                preset_name,
                self.dynamic_wave_index - 1,
                scaled_strength,
            )
            if preset_wave:
                return preset_wave
        self.active_dynamic_preset = None
        return self.generate_wave_100ms_improved(
            mode_conf['freq_ms'],
            from_strength,
            to_strength,
        )

    def resolve_touch_profile(self, current_strength):
        touch_conf = self.get_mode_conf('touch')
        selected_profile = None
        for profile in touch_conf.get('preset_bands', []):
            try:
                threshold = float(profile.get('threshold', 0))
            except (TypeError, ValueError):
                logger.warning(f'Channel {self.channel}, invalid touch preset threshold: {profile}')
                continue
            if current_strength >= threshold:
                if selected_profile is None or threshold >= selected_profile['threshold']:
                    selected_profile = {
                        'threshold': threshold,
                        'wave_preset': profile.get('wave_preset'),
                        'wave_scale': profile.get('wave_scale'),
                    }
        if selected_profile is None:
            return touch_conf.get('wave_preset'), touch_conf.get('wave_scale', 1.0)
        wave_preset = selected_profile.get('wave_preset') or touch_conf.get('wave_preset')
        wave_scale = selected_profile.get('wave_scale')
        if wave_scale is None:
            wave_scale = touch_conf.get('wave_scale', 1.0)
        return wave_preset, wave_scale

    async def handler_distance(self, distance, context=None):
        await self.set_clear_after(0.5)
        normalized = self.normalize_distance(distance)
        self.bg_wave_current_strength = normalized
        self.log_trigger(context, value=distance, normalized=normalized)

    async def distance_background_wave_feeder(self):
        tick_time_window = self.bg_wave_update_time_window / 20
        next_tick_time   = 0
        last_strength    = 0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.bg_wave_update_time_window
            current_strength = self.bg_wave_current_strength
            if current_strength == last_strength == 0:
                continue
            wave = self.build_dynamic_wave('distance', last_strength, current_strength)
            self.log_output(
                source='distance',
                strength=current_strength,
                wave=wave,
                extra=f"from={last_strength:.3f} to={current_strength:.3f} preset={self.active_dynamic_preset or '-'}",
            )
            last_strength = current_strength
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)
    
    async def send_shock_wave(self, shock_time, shockwave: str):
        shockwave_duration = max(0.1, (shockwave.count(',') + 1) * 0.1)
        loop_end_time = time.time() + shock_time
        while time.time() < loop_end_time:
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=shockwave)
            await asyncio.sleep(shockwave_duration)

    def get_shock_wavestrs(self):
        shock_conf = self.get_mode_conf('shock')
        preset_name = shock_conf.get('wave_preset')
        wave_scale = max(0.0, min(1.0, shock_conf.get('wave_scale', 1.0)))
        preset_wavestrs = self._wave_library.build_scaled_wavestrs(preset_name, wave_scale)
        if preset_wavestrs:
            return preset_wavestrs
        return [shock_conf['wave']]

    async def send_shock_wavestrs(self, shock_time):
        wavestrs = self.get_shock_wavestrs()
        loop_end_time = time.time() + shock_time
        while time.time() < loop_end_time:
            for wavestr in wavestrs:
                if time.time() >= loop_end_time:
                    break
                duration = max(0.1, (wavestr.count(',') + 1) * 0.1)
                self.log_output(
                    source='shock',
                    wave=wavestr,
                    extra=f"duration={duration:.2f}s preset={self.get_mode_conf('shock').get('wave_preset') or '-'}",
                )
                await self.DG_CONN.broadcast_wave(self.channel, wavestr=wavestr)
                await asyncio.sleep(duration)
    
    async def handler_shock(self, distance, context=None):
        current_time = time.time()
        if distance > self.mode_config['trigger_range']['bottom'] and current_time > self.to_clear_time:
            shock_duration = self.mode_config['shock']['duration']
            await self.set_clear_after(shock_duration)
            preset_names = self.get_mode_conf('shock').get('wave_preset') or '-'
            self.log_trigger(context, value=distance, extra=f"duration={shock_duration:.2f}s preset={preset_names}")
            asyncio.create_task(self.send_shock_wavestrs(shock_duration))

    async def handler_touch(self, distance, context=None):
        await self.set_clear_after(0.5)
        out_distance = self.normalize_distance(distance)
        self.log_trigger(context, value=distance, normalized=out_distance)
        if out_distance == 0:
            return
        t = time.time()
        self.touch_dist_arr.append([t,out_distance])
    
    def compute_derivative(self):
        data = self.touch_dist_arr
        if len(data) < 4:
            # logger.warning('At least 4 samples are required to calculate acc and jerk.')
            return 0, 0, 0, 0

        time_ = np.array([point[0] for point in data])
        distance = np.array([point[1] for point in data])

        window_size = 3
        distance = np.convolve(distance, np.ones(window_size) / window_size, mode='valid')
        time_ = time_[:len(distance)]

        velocity = np.gradient(distance, time_)
        acceleration = np.gradient(velocity, time_)
        jerk = np.gradient(acceleration, time_)
        # logger.success(f"{distance[-1]:9.4f} {velocity[-1]:9.4f} {acceleration[-1]:9.4f} {jerk[-1]:9.4f}")
        return distance[-1], velocity[-1], acceleration[-1], jerk[-1]

    async def touch_background_wave_feeder(self):
        tick_time_window = self.bg_wave_update_time_window / 20
        next_tick_time   = 0
        last_strength    = 0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.bg_wave_update_time_window
            n_derivative = self.mode_config['touch']['n_derivative']
            derivative_values = self.compute_derivative()
            if n_derivative < 0 or n_derivative >= len(derivative_values):
                logger.warning(f'Channel {self.channel}, invalid n_derivative {n_derivative}, fallback to 1.')
                n_derivative = 1
            current_strength = derivative_values[n_derivative]
            derivative_params = self.mode_config['touch']['derivative_params'][n_derivative]
            current_strength = self.normalize_between(
                abs(current_strength),
                derivative_params['bottom'],
                derivative_params['top'],
            )

            self.bg_wave_current_strength = current_strength
            if current_strength == last_strength == 0:
                continue
            touch_preset, touch_scale = self.resolve_touch_profile(current_strength)
            wave = self.build_dynamic_wave(
                'touch',
                last_strength,
                current_strength,
                preset_name=touch_preset,
                wave_scale=touch_scale,
            )
            derivative_name = ['distance', 'velocity', 'acceleration', 'jerk'][n_derivative]
            self.log_output(
                source='touch',
                strength=current_strength,
                wave=wave,
                extra=(
                    f"from={last_strength:.3f} to={current_strength:.3f} "
                    f"derivative={derivative_name} preset={touch_preset or '-'} scale={touch_scale:.2f}"
                ),
            )
            last_strength = current_strength
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)

