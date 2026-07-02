"""Regression test against a known-good chart.

LRCX daily history frozen through 2026-06-11. Expected values were read off
stockcharts.com's traditional-scale 3-box P&F chart of _LRCX (UNADJUSTED —
the engine's spec; Yahoo quote arrays are dividend-unadjusted to match) the
same day: current X column 324-364, prior O column low 320, Double Top
Breakout on 2026-06-11 triggered at 352, logical stop 316. Every column from
Dec 2025 onward was verified to match the _LRCX chart box-for-box.
"""
import csv
import unittest
from pathlib import Path

from pnf.analysis import analyze
from pnf.chart import build

DATA = Path(__file__).parent / "data" / "lrcx_2026-06-11.csv"


def load_bars():
    with DATA.open() as f:
        return [(r["date"], float(r["high"]), float(r["low"]), float(r["close"]))
                for r in csv.DictReader(f)]


class TestLrcxAgainstStockCharts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chart = build(load_bars())
        cls.an = analyze(cls.chart, "LRCX")

    def test_close(self):
        self.assertAlmostEqual(self.chart.last_close, 362.52, places=2)

    def test_current_column(self):
        col = self.chart.columns[-1]
        lad = self.chart.ladder
        self.assertEqual(col.kind, "X")
        self.assertEqual(lad[col.hi], 364.0)
        self.assertEqual(lad[col.lo], 324.0)

    def test_last_o_column_low(self):
        o_cols = [c for c in self.chart.columns if c.kind == "O"]
        self.assertEqual(self.chart.ladder[o_cols[-1].lo], 320.0)

    def test_signal(self):
        sig = self.chart.last_signal
        self.assertEqual(sig.kind, "buy")
        self.assertEqual(sig.pattern, "Double Top Breakout")
        self.assertEqual(sig.date, "2026-06-11")
        self.assertEqual(sig.trigger, 352.0)

    def test_reversal_level(self):
        # current X column tops at 364 on $4 boxes: 3-box flip at 352
        self.assertEqual(self.an.reversal, 352.0)

    def test_stop_objective_rr(self):
        an = self.an
        self.assertEqual(an.status, "bullish")
        self.assertEqual(an.stop, 316.0)
        # StockCharts breakout method: measure column 308-348 (reversed the
        # prior sell signal) -> 308 - 1 + 3*(348-308+4) = 439, the exact
        # "Bullish Price Objective" published on the _LRCX chart that day
        self.assertEqual(an.objective, 439.0)
        self.assertFalse(an.objective_active)
        self.assertAlmostEqual(an.rr, round((439 - an.close) / (an.close - 316), 2))

    def test_classic_objective(self):
        # Dorsey vertical count on the 11-box breakout column: 324 + 33*$4
        an = analyze(self.chart, "LRCX", method="classic")
        self.assertEqual(an.objective, 456.0)
        self.assertTrue(an.objective_active)


if __name__ == "__main__":
    unittest.main()
