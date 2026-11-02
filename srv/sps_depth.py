"""SPS2 / OGB 插入深度计算。

SPS1 与 SPS2 在 OSC 层面的关键区别：

- SPS1 / legacy：socket 直接给出 ``PenSelf`` / ``PenOthers`` 单个 0~1 深度值
- SPS2：socket 给出 ``PenSelfNewRoot`` + ``PenSelfNewTip`` 一对 proximity，
  必须自行推算插入深度

本模块负责把这两种形态统一成单个 0~1 深度，供现有 distance / touch / shock /
combo 模式直接消费。

深度推算算法移植自 Neko-VRC 的 ``srv/sps_depth.py``（其注释标明来源为 OGB 的
稳定长度估计器）。详见 ``doc/neko_vrc_sps2_research.md``。
"""

from __future__ import annotations

AVATAR_PARAMETER_PREFIX = '/avatar/parameters/'
OGB_PARAMETER_PREFIX = f'{AVATAR_PARAMETER_PREFIX}OGB/'

SPS_SOCKET = 'sps_socket'
SPS_PLUG = 'sps_plug'
SPS_TRIGGER_TYPES = (SPS_SOCKET, SPS_PLUG)

# OGB 地址第 4 段 -> 触发类型
_OGB_KIND_TO_TRIGGER = {'Orf': SPS_SOCKET, 'Pen': SPS_PLUG}

# SPS2 的 Root/Tip 对
_SOCKET_PAIR_SIGNALS = frozenset({
    'PenSelfNewRoot', 'PenSelfNewTip',
    'PenOthersNewRoot', 'PenOthersNewTip',
})
# legacy 单值深度
_DEPTH_SIGNALS = frozenset({'PenSelf', 'PenOthers'})
# 接近门控（仅作用于 legacy 路径）
_CLOSE_GATE_SIGNAL = 'PenOthersClose'

#: socket 需要订阅的全部 signal。Touch/Frot 不是插入深度，故不在此列。
SOCKET_SIGNALS = (
    'PenSelfNewRoot', 'PenSelfNewTip',
    'PenOthersNewRoot', 'PenOthersNewTip',
    'PenSelf', 'PenOthers',
    _CLOSE_GATE_SIGNAL,
)
#: plug 需要订阅的 signal
PLUG_SIGNALS = ('PenSelf', 'PenOthers')

_VALID_SIGNALS = frozenset(SOCKET_SIGNALS) | frozenset(PLUG_SIGNALS)


def is_ogb_address(address):
    """该 OSC 地址是否属于 OGB 命名空间。"""
    return isinstance(address, str) and address.startswith(OGB_PARAMETER_PREFIX)


def parse_ogb_address(address):
    """解析 OGB 地址。

    返回 ``(trigger_type, zone_id, signal)``，无法识别时返回 ``None``。

    预期形如 ``/avatar/parameters/OGB/Orf/<zone>/<signal>``，
    即去掉首尾斜杠后正好 6 段。
    """
    if not is_ogb_address(address):
        return None
    parts = address.strip('/').split('/')
    if len(parts) != 6:
        return None
    if parts[:3] != ['avatar', 'parameters', 'OGB']:
        return None
    trigger_type = _OGB_KIND_TO_TRIGGER.get(parts[3])
    if trigger_type is None:
        return None
    zone_id, signal = parts[4], parts[5]
    if not zone_id or signal not in _VALID_SIGNALS:
        return None
    # Plug 只有单值深度，不存在 Root/Tip 对与门控
    if trigger_type == SPS_PLUG and signal not in PLUG_SIGNALS:
        return None
    return trigger_type, zone_id, signal


def sps_osc_bindings(trigger_type, zone_id):
    """返回某个 SPS 部位需要订阅的 ``(OSC 地址, signal)`` 列表。"""
    if trigger_type not in SPS_TRIGGER_TYPES:
        raise ValueError(f'不支持的 SPS 触发类型：{trigger_type}')
    zone_id = str(zone_id).strip()
    if not zone_id or '/' in zone_id:
        raise ValueError('SPS 部位 ID 无效。')
    ogb_kind = 'Orf' if trigger_type == SPS_SOCKET else 'Pen'
    base = f'{OGB_PARAMETER_PREFIX}{ogb_kind}/{zone_id}'
    signals = SOCKET_SIGNALS if trigger_type == SPS_SOCKET else PLUG_SIGNALS
    return tuple((f'{base}/{signal}', signal) for signal in signals)


def _clamp_unit(value):
    """钳制到 [0,1]，并把 NaN / 非数值失效安全地归 0。"""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    return min(1.0, max(0.0, value))


class _PenetratorLengthDetector:
    """动态估算 plug 长度。

    Root/Tip 只是两个 proximity，要还原插入深度必须知道 plug 长度，而长度因
    avatar 而异且未知，只能从样本里估。移植自 OGB 的稳定长度估计器。
    """

    MAX_SAMPLES = 8

    def __init__(self):
        self.length = None
        self.recent_samples = []
        self.penetrating_sample = None

    def _recalculate(self):
        if len(self.recent_samples) < 4:
            self.length = self.penetrating_sample
            return
        # 取「相邻差值最小」处的样本，即最密集聚集点。
        # 比平均数对离群值稳健得多。
        samples = sorted(self.recent_samples)
        closest_index = min(
            range(1, len(samples)),
            key=lambda index: abs(samples[index] - samples[index - 1]),
        )
        self.length = samples[closest_index]

    def reset(self):
        self.length = None
        self.recent_samples.clear()
        self.penetrating_sample = None

    def update(self, root_proximity, tip_proximity):
        if root_proximity is None or tip_proximity is None:
            return
        if root_proximity < 0.01 or tip_proximity < 0.01:
            # 已脱离，历史样本全部失效
            self.reset()
            return
        if root_proximity > 0.95:
            # 根部已抵达中心，此时长度不可信
            return
        length = tip_proximity - root_proximity
        if length < 0.02:
            # 过小，当噪声丢弃
            return
        if tip_proximity > 0.99:
            # 完全插入状态，只保留最大长度
            if self.penetrating_sample is None or length > self.penetrating_sample:
                self.penetrating_sample = length
                self._recalculate()
            return
        self.recent_samples.insert(0, length)
        del self.recent_samples[self.MAX_SAMPLES:]
        self._recalculate()


class SPSDepthCalculator:
    """汇总一个 OGB 部位的各路 signal，输出单个 0~1 深度。"""

    def __init__(self, trigger_type):
        if trigger_type not in SPS_TRIGGER_TYPES:
            raise ValueError(f'不支持的 SPS 触发类型：{trigger_type}')
        self.trigger_type = trigger_type
        self.values = {}
        self.has_close_gate = False
        self.detectors = {
            'Self': _PenetratorLengthDetector(),
            'Others': _PenetratorLengthDetector(),
        }

    def update(self, signal, value):
        """喂入一路 signal，返回更新后的深度。"""
        if signal == _CLOSE_GATE_SIGNAL:
            self.has_close_gate = True
        self.values[signal] = _clamp_unit(value)
        if self.trigger_type == SPS_SOCKET and signal in _SOCKET_PAIR_SIGNALS:
            for owner in ('Self', 'Others'):
                if signal in (f'Pen{owner}NewRoot', f'Pen{owner}NewTip'):
                    self.detectors[owner].update(
                        self.values.get(f'Pen{owner}NewRoot'),
                        self.values.get(f'Pen{owner}NewTip'),
                    )
        return self.depth

    def forget(self, signal):
        """丢弃某路 signal，不影响其他仍然有效的 signal。"""
        self.values.pop(signal, None)
        for owner in ('Self', 'Others'):
            if signal in (f'Pen{owner}NewRoot', f'Pen{owner}NewTip'):
                self.detectors[owner].reset()

    def reset(self):
        self.values.clear()
        self.has_close_gate = False
        for detector in self.detectors.values():
            detector.reset()

    def _new_socket_depth(self, owner):
        """SPS2 的 Root/Tip 推算。不可用时返回 None 以便回退。"""
        root = self.values.get(f'Pen{owner}NewRoot')
        tip = self.values.get(f'Pen{owner}NewTip')
        if root is None or tip is None or (root <= 0 and tip <= 0):
            return None
        length = self.detectors[owner].length
        if length and tip > 0.99:
            exposed_ratio = (1 - root) / length
            return _clamp_unit(1 - exposed_ratio)
        return 0.0

    def _socket_depth(self, owner):
        new_depth = self._new_socket_depth(owner)
        if new_depth is not None:
            return new_depth
        # 回退到 legacy 单值路径。门控只在这条路径生效，
        # 不能覆盖 Root/Tip 已经算出的深度。
        if (owner == 'Others' and self.has_close_gate
                and not self.values.get(_CLOSE_GATE_SIGNAL, 0)):
            return 0.0
        return self.values.get(f'Pen{owner}', 0.0)

    @property
    def depth(self):
        """Self 与 Others 取最大值，不区分由谁触发。"""
        if self.trigger_type == SPS_SOCKET:
            return max(self._socket_depth('Self'), self._socket_depth('Others'))
        return max(
            self.values.get('PenSelf', 0.0),
            self.values.get('PenOthers', 0.0),
        )
