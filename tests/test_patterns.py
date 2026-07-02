"""Pattern classification on synthetic charts.

Each case is a price path on the $1 box band ($20-$100): one bar per swing,
high = low = close, so the resulting columns are exact and easy to trace by
hand. A leading one-box X column appears when the path opens with a decline;
the classifier only reads relative structure, so it is harmless.
"""
import unittest

from pnf.chart import build


def chart(*prices):
    bars = [(f"2026-01-{i + 1:02d}", float(p), float(p), float(p))
            for i, p in enumerate(prices)]
    return build(bars)


class TestBuyPatterns(unittest.TestCase):
    def test_double_top(self):
        c = chart(50, 55, 52, 56)
        self.assertEqual([s.pattern for s in c.signals], ["Double Top Breakout"])
        self.assertEqual(c.signals[0].trigger, 56.0)

    def test_triple_top(self):
        c = chart(50, 55, 52, 55, 52, 56)
        self.assertEqual([s.pattern for s in c.signals], ["Triple Top Breakout"])

    def test_quadruple_top(self):
        c = chart(50, 55, 52, 55, 52, 55, 52, 56)
        self.assertEqual([s.pattern for s in c.signals], ["Quadruple Top Breakout"])

    def test_ascending_triple_top(self):
        # back-to-back double top breakouts with a rising inner low
        c = chart(50, 54, 51, 55, 52, 56)
        self.assertEqual([s.pattern for s in c.signals],
                         ["Double Top Breakout", "Ascending Triple Top Breakout"])

    def test_bullish_catapult(self):
        # triple top breakout, pullback that holds, double top breakout
        c = chart(50, 55, 52, 55, 52, 57, 54, 58)
        self.assertEqual([s.pattern for s in c.signals],
                         ["Triple Top Breakout", "Bullish Catapult"])

    def test_spread_triple_top(self):
        # equal tops at 60 separated by a lower X column (58), 7 columns wide
        c = chart(50, 57, 54, 60, 55, 58, 55, 60, 57, 61)
        self.assertEqual([s.pattern for s in c.signals],
                         ["Double Top Breakout", "Double Top Breakout",
                          "Spread Triple Top Breakout"])

    def test_bearish_signal_reversed(self):
        # lower lows and lower highs ended by a double top breakout
        c = chart(60, 50, 55, 47, 52, 44, 54)
        self.assertEqual(c.signals[-1].pattern, "Bearish Signal Reversed")
        self.assertEqual(c.signals[-1].kind, "buy")


class TestSellPatterns(unittest.TestCase):
    def test_double_bottom(self):
        c = chart(60, 55, 58, 54)
        self.assertEqual([s.pattern for s in c.signals], ["Double Bottom Breakdown"])
        self.assertEqual(c.signals[0].trigger, 54.0)

    def test_triple_bottom(self):
        c = chart(60, 55, 58, 55, 58, 54)
        self.assertEqual([s.pattern for s in c.signals], ["Triple Bottom Breakdown"])

    def test_quadruple_bottom(self):
        c = chart(60, 55, 58, 55, 58, 55, 58, 54)
        self.assertEqual([s.pattern for s in c.signals], ["Quadruple Bottom Breakdown"])

    def test_descending_triple_bottom(self):
        c = chart(60, 56, 59, 55, 58, 54)
        self.assertEqual([s.pattern for s in c.signals],
                         ["Double Bottom Breakdown",
                          "Descending Triple Bottom Breakdown"])

    def test_bearish_catapult(self):
        c = chart(60, 55, 58, 55, 58, 53, 56, 52)
        self.assertEqual([s.pattern for s in c.signals],
                         ["Triple Bottom Breakdown", "Bearish Catapult"])

    def test_spread_triple_bottom(self):
        c = chart(60, 53, 56, 50, 55, 52, 55, 50, 53, 49)
        self.assertEqual([s.pattern for s in c.signals],
                         ["Double Bottom Breakdown", "Double Bottom Breakdown",
                          "Spread Triple Bottom Breakdown"])

    def test_bullish_signal_reversed(self):
        # higher highs and higher lows ended by a double bottom breakdown
        c = chart(40, 50, 45, 53, 48, 56, 46)
        self.assertEqual(c.signals[-1].pattern, "Bullish Signal Reversed")
        self.assertEqual(c.signals[-1].kind, "sell")


class TestNonPatterns(unittest.TestCase):
    def test_pullback_breaking_down_voids_catapult(self):
        # triple top breakout, but the pullback breaks the prior O low: the
        # later upside breakout is a plain double top, not a catapult
        c = chart(50, 55, 51, 55, 52, 57, 49, 58)
        self.assertEqual([(s.kind, s.pattern) for s in c.signals],
                         [("buy", "Triple Top Breakout"),
                          ("sell", "Double Bottom Breakdown"),
                          ("buy", "Double Top Breakout")])

    def test_breakdown_inside_formation_voids_ascending(self):
        # rising highs and rising inner low, but the inner O column fired a
        # sell on the way down — StockCharts keeps this a Double Top Breakout
        # (the LRCX 2026-06-11 chart is the real-world regression for this)
        c = chart(50, 55, 51, 56, 48, 57, 52, 58)
        self.assertEqual(c.signals[-1].kind, "buy")
        self.assertEqual(c.signals[-1].pattern, "Double Top Breakout")

    def test_intervening_breakdown_voids_spread(self):
        # equal tops at 60 but a sell signal fired inside the pattern
        c = chart(50, 57, 54, 60, 55, 58, 53, 60, 57, 61)
        self.assertEqual(c.signals[-1].kind, "buy")
        self.assertNotEqual(c.signals[-1].pattern, "Spread Triple Top Breakout")


if __name__ == "__main__":
    unittest.main()
