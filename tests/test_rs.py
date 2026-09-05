"""Relative strength: log-scale ladder, ratio alignment, RS chart verdicts.
RS charts are built from synthetic ratio series (close-only, like the BPI
tests) on the 2% multiplicative grid."""
import unittest

from pnf import data, rs
from pnf.boxes import Ladder
from pnf.chart import build


def days(*vals, start=1):
    """Close-only bars from a list of values, one per synthetic day."""
    return [(f"2026-{(start + i) // 28 + 1:02d}-{(start + i) % 28 + 1:02d}",
             float(v), float(v), float(v)) for i, v in enumerate(vals)]


class TestPctLadder(unittest.TestCase):
    def test_grid_is_multiplicative(self):
        lad = Ladder(100.0, pct=0.02)
        self.assertEqual(lad.vals[0], 0.01)
        i = lad.floor(50.0)
        self.assertAlmostEqual(lad[i + 1] / lad[i], 1.02, places=3)

    def test_floor_ceil_bracket_price(self):
        lad = Ladder(100.0, pct=0.02)
        i, j = lad.floor(50.0), lad.ceil(50.0)
        self.assertLessEqual(lad[i], 50.0)
        self.assertGreater(lad[i + 1], 50.0)
        self.assertGreaterEqual(lad[j], 50.0)
        self.assertLess(lad[j - 1], 50.0)

    def test_extends_multiplicatively_above_init_limit(self):
        lad = Ladder(10.0, pct=0.02)
        i = lad.floor(500.0)  # far beyond the constructor limit
        self.assertAlmostEqual(lad[i + 1] / lad[i], 1.02, places=3)


class TestRatioBars(unittest.TestCase):
    def test_aligns_on_common_dates(self):
        num = days(10, 12, 11)
        d3 = days(100, 100, 110)
        den = [d3[0], d3[2]]  # benchmark missing day 2
        bars = rs.ratio_bars(num, den)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0][3], 10.0)   # 10/100 * 100
        self.assertAlmostEqual(bars[1][3], 10.0)  # 11/110 * 100

    def test_no_overlap_raises(self):
        with self.assertRaises(data.DataError):
            rs.ratio_bars(days(10), days(100, start=100))


class TestVerdict(unittest.TestCase):
    def _chart(self, *vals):
        return build(days(*vals), pct=0.02)

    def test_no_signal_yet(self):
        ch = self._chart(100, 110, 121)  # one X column, no signal possible
        status, reading = rs.verdict(ch)
        self.assertEqual(status, "neutral")
        self.assertEqual(ch.columns[-1].kind, "X")

    def test_leader_buy_and_x(self):
        # up, 3-box pullback, then out above the prior top: double top breakout
        ch = self._chart(100, 110, 101, 104, 115)
        status, reading = rs.verdict(ch)
        self.assertEqual(ch.last_signal.kind, "buy")
        self.assertEqual((status, ch.columns[-1].kind), ("bullish", "X"))
        self.assertIn("leader", reading)

    def test_laggard_sell_and_o(self):
        ch = self._chart(100, 90, 97, 96, 85)
        status, reading = rs.verdict(ch)
        self.assertEqual(ch.last_signal.kind, "sell")
        self.assertEqual((status, ch.columns[-1].kind), ("bearish", "O"))
        self.assertIn("laggard", reading)


if __name__ == "__main__":
    unittest.main()
