"""SPS2 / OGB 深度计算与聚合层测试。

运行：
    python3 -m unittest tests.test_sps_depth -v
或：
    python3 tests/test_sps_depth.py
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from srv.sps_depth import (  # noqa: E402
    SPSDepthCalculator, SPS_SOCKET, SPS_PLUG,
    is_ogb_address, parse_ogb_address, sps_osc_bindings,
    SOCKET_SIGNALS, PLUG_SIGNALS,
)


class AddressParsingTests(unittest.TestCase):

    def test_detects_ogb_namespace(self):
        self.assertTrue(is_ogb_address('/avatar/parameters/OGB/Orf/Hole/PenSelf'))
        self.assertFalse(is_ogb_address('/avatar/parameters/pcs/contact/enterPass'))
        self.assertFalse(is_ogb_address(None))

    def test_parses_socket_and_plug(self):
        self.assertEqual(
            parse_ogb_address('/avatar/parameters/OGB/Orf/Hole/PenSelfNewRoot'),
            (SPS_SOCKET, 'Hole', 'PenSelfNewRoot'),
        )
        self.assertEqual(
            parse_ogb_address('/avatar/parameters/OGB/Pen/Rod/PenOthers'),
            (SPS_PLUG, 'Rod', 'PenOthers'),
        )

    def test_rejects_malformed_and_unknown_signals(self):
        for address in (
            '/avatar/parameters/OGB/Orf/Hole',              # 段数不足
            '/avatar/parameters/OGB/Orf/Hole/A/B',          # 段数过多
            '/avatar/parameters/OGB/Xxx/Hole/PenSelf',      # 未知 kind
            '/avatar/parameters/OGB/Orf/Hole/TouchSelf',    # 非深度信号
            '/avatar/parameters/OGB/Orf/Hole/FrotSelf',     # 非深度信号
            '/avatar/parameters/OGB/Orf//PenSelf',          # 空 zone
        ):
            self.assertIsNone(parse_ogb_address(address), address)

    def test_plug_rejects_socket_only_signals(self):
        # Root/Tip 与门控只属于 socket
        self.assertIsNone(
            parse_ogb_address('/avatar/parameters/OGB/Pen/Rod/PenSelfNewRoot'))
        self.assertIsNone(
            parse_ogb_address('/avatar/parameters/OGB/Pen/Rod/PenOthersClose'))

    def test_bindings_cover_declared_signals(self):
        socket = sps_osc_bindings(SPS_SOCKET, 'Hole')
        self.assertEqual(tuple(s for _a, s in socket), SOCKET_SIGNALS)
        for address, signal in socket:
            self.assertEqual(parse_ogb_address(address), (SPS_SOCKET, 'Hole', signal))

        plug = sps_osc_bindings(SPS_PLUG, 'Rod')
        self.assertEqual(tuple(s for _a, s in plug), PLUG_SIGNALS)

    def test_bindings_validate_zone(self):
        with self.assertRaises(ValueError):
            sps_osc_bindings(SPS_SOCKET, 'a/b')
        with self.assertRaises(ValueError):
            sps_osc_bindings(SPS_SOCKET, '  ')
        with self.assertRaises(ValueError):
            sps_osc_bindings('nope', 'Hole')


class PlugDepthTests(unittest.TestCase):

    def test_takes_max_of_self_and_others(self):
        calc = SPSDepthCalculator(SPS_PLUG)
        self.assertAlmostEqual(calc.update('PenSelf', 0.3), 0.3)
        self.assertAlmostEqual(calc.update('PenOthers', 0.7), 0.7)
        self.assertAlmostEqual(calc.update('PenSelf', 0.9), 0.9)

    def test_clamps_and_rejects_nan(self):
        calc = SPSDepthCalculator(SPS_PLUG)
        self.assertAlmostEqual(calc.update('PenSelf', 5.0), 1.0)
        calc.reset()
        self.assertAlmostEqual(calc.update('PenSelf', -3.0), 0.0)
        calc.reset()
        # NaN 必须失效安全归 0，不能变成最大深度
        self.assertAlmostEqual(calc.update('PenSelf', float('nan')), 0.0)


class SocketLegacyDepthTests(unittest.TestCase):
    """SPS1 / legacy 单值路径。"""

    def test_uses_single_value_when_no_root_tip(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        self.assertAlmostEqual(calc.update('PenSelf', 0.45), 0.45)

    def test_close_gate_blocks_others(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        calc.update('PenOthers', 0.8)
        self.assertAlmostEqual(calc.depth, 0.8)
        # 门控为 0 时 Others 深度被压制
        calc.update('PenOthersClose', 0)
        self.assertAlmostEqual(calc.depth, 0.0)
        # 门控恢复
        calc.update('PenOthersClose', 1)
        self.assertAlmostEqual(calc.depth, 0.8)

    def test_close_gate_does_not_affect_self(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        calc.update('PenSelf', 0.6)
        calc.update('PenOthersClose', 0)
        self.assertAlmostEqual(calc.depth, 0.6)


class SocketSPS2DepthTests(unittest.TestCase):
    """SPS2 的 Root/Tip 推算路径。"""

    @staticmethod
    def _feed_pairs(calc, owner, pairs):
        for root, tip in pairs:
            calc.update(f'Pen{owner}NewRoot', root)
            calc.update(f'Pen{owner}NewTip', tip)

    def test_partial_insertion_gives_zero_until_fully_inserted(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        # tip 未达 0.99，视为尚未完全插入 -> 深度 0
        self._feed_pairs(calc, 'Self', [(0.2, 0.5)])
        self.assertAlmostEqual(calc.depth, 0.0)

    def test_depth_increases_as_root_approaches_center(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        # 先喂足样本让长度估计稳定（length ≈ 0.5）
        self._feed_pairs(calc, 'Self', [
            (0.10, 0.60), (0.11, 0.61), (0.12, 0.62),
            (0.13, 0.63), (0.14, 0.64),
        ])
        # 完全插入，root 越大 -> 露出越少 -> 深度越大
        calc.update('PenSelfNewRoot', 0.30)
        calc.update('PenSelfNewTip', 1.0)
        shallow = calc.depth
        calc.update('PenSelfNewRoot', 0.70)
        deep = calc.depth
        self.assertGreater(deep, shallow)
        self.assertTrue(0.0 <= shallow <= 1.0)
        self.assertTrue(0.0 <= deep <= 1.0)

    def test_detaching_resets_length_estimate(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        self._feed_pairs(calc, 'Self', [
            (0.10, 0.60), (0.11, 0.61), (0.12, 0.62), (0.13, 0.63),
        ])
        self.assertIsNotNone(calc.detectors['Self'].length)
        # proximity 掉到阈值下 = 脱离
        calc.update('PenSelfNewRoot', 0.0)
        calc.update('PenSelfNewTip', 0.0)
        self.assertIsNone(calc.detectors['Self'].length)
        self.assertAlmostEqual(calc.depth, 0.0)

    def test_new_path_wins_over_close_gate(self):
        """门控不能覆盖 Root/Tip 已算出的深度。"""
        calc = SPSDepthCalculator(SPS_SOCKET)
        self._feed_pairs(calc, 'Others', [
            (0.10, 0.60), (0.11, 0.61), (0.12, 0.62), (0.13, 0.63),
        ])
        calc.update('PenOthersNewRoot', 0.60)
        calc.update('PenOthersNewTip', 1.0)
        depth_before = calc.depth
        self.assertGreater(depth_before, 0.0)
        calc.update('PenOthersClose', 0)
        self.assertAlmostEqual(calc.depth, depth_before)

    def test_falls_back_to_legacy_when_pair_absent(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        calc.update('PenSelf', 0.55)
        # 只有 Root 没有 Tip，不构成有效对，应回退 legacy
        calc.update('PenSelfNewRoot', 0.4)
        self.assertAlmostEqual(calc.depth, 0.55)

    def test_forget_drops_one_signal_only(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        calc.update('PenSelf', 0.5)
        calc.update('PenOthers', 0.2)
        calc.forget('PenSelf')
        self.assertAlmostEqual(calc.depth, 0.2)


class LengthDetectorTests(unittest.TestCase):

    def test_ignores_noise_and_invalid_samples(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        d = calc.detectors['Self']
        d.update(0.5, 0.51)        # length 0.01 < 0.02 -> 丢弃
        self.assertEqual(d.recent_samples, [])
        d.update(0.97, 1.0)        # root > 0.95 -> 忽略
        self.assertEqual(d.recent_samples, [])
        d.update(None, 0.5)        # 缺值 -> 忽略
        self.assertEqual(d.recent_samples, [])

    def test_sample_window_is_bounded(self):
        calc = SPSDepthCalculator(SPS_SOCKET)
        d = calc.detectors['Self']
        for i in range(20):
            d.update(0.1, 0.5 + i * 0.001)
        self.assertLessEqual(len(d.recent_samples), d.MAX_SAMPLES)


class HandlerAggregationTests(unittest.TestCase):
    """聚合层接入 ShockHandler 后的行为。"""

    def setUp(self):
        from shocking_vrchat import _default_mode_config
        from srv.handler.shock_handler import ShockHandler

        self.sent = []
        outer = self

        class MockConn:
            async def broadcast_wave(self, ch, wavestr=None):
                outer.sent.append(wavestr)

            async def broadcast_clear_wave(self, ch):
                pass

        self.settings = {
            'sps': {'enabled': True},
            'dglab3': {'channel_a': {
                'mode': 'distance', 'strength_limit': 50,
                'mode_config': _default_mode_config(),
            }},
        }
        self.handler = ShockHandler(self.settings, MockConn(), 'a')
        self.handler.mode_config['trigger_range'] = {'bottom': 0.0, 'top': 1.0}

    def test_non_ogb_address_unchanged(self):
        """普通 PCS 参数不应被 SPS 逻辑干扰。"""
        result = self.handler._aggregate_sps(
            '/avatar/parameters/pcs/contact/enterPass', 0.7)
        self.assertIsNone(result)

    def test_plug_address_aggregates(self):
        depth, tag = self.handler._aggregate_sps(
            '/avatar/parameters/OGB/Pen/Rod/PenSelf', 0.65)
        self.assertAlmostEqual(depth, 0.65)
        self.assertEqual(tag, 'sps_plug/Rod/PenSelf')

    def test_socket_pair_aggregates_into_single_depth(self):
        base = '/avatar/parameters/OGB/Orf/Hole'
        for root, tip in [(0.10, 0.60), (0.11, 0.61), (0.12, 0.62), (0.13, 0.63)]:
            self.handler._aggregate_sps(f'{base}/PenSelfNewRoot', root)
            self.handler._aggregate_sps(f'{base}/PenSelfNewTip', tip)
        self.handler._aggregate_sps(f'{base}/PenSelfNewRoot', 0.6)
        depth, _tag = self.handler._aggregate_sps(f'{base}/PenSelfNewTip', 1.0)
        self.assertGreater(depth, 0.0)
        self.assertLessEqual(depth, 1.0)

    def test_zones_are_tracked_independently(self):
        self.handler._aggregate_sps('/avatar/parameters/OGB/Orf/A/PenSelf', 0.2)
        depth_b, _ = self.handler._aggregate_sps(
            '/avatar/parameters/OGB/Orf/B/PenSelf', 0.9)
        self.assertAlmostEqual(depth_b, 0.9)
        self.assertEqual(len(self.handler.sps_calculators), 2)

    def test_disabled_flag_skips_aggregation(self):
        self.settings['sps']['enabled'] = False
        self.assertFalse(self.handler.sps_enabled)

    def test_reset_clears_depth(self):
        self.handler._aggregate_sps('/avatar/parameters/OGB/Pen/Rod/PenSelf', 0.8)
        self.handler.reset_sps_state()
        for calc in self.handler.sps_calculators.values():
            self.assertAlmostEqual(calc.depth, 0.0)

    def test_osc_handler_feeds_aggregated_depth(self):
        """端到端：osc_handler 应把聚合后的深度交给模式逻辑。"""
        seen = []

        async def fake_handler(val, context=None):
            seen.append((val, context))

        self.handler._handler = fake_handler
        self.handler._command_queue = None

        async def run():
            self.handler.osc_handler(
                '/avatar/parameters/OGB/Pen/Rod/PenSelf', 0.42)
            await asyncio.sleep(0.05)

        asyncio.run(run())
        self.assertEqual(len(seen), 1)
        val, context = seen[0]
        self.assertAlmostEqual(val, 0.42)
        self.assertEqual(context['sps'], 'sps_plug/Rod/PenSelf')


if __name__ == '__main__':
    unittest.main(verbosity=2)
