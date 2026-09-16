"""Showcase: the showpieces-table parser and the chart-shape score on
hand-built charts. No network — charts come from synthetic close-only bars."""
import tempfile
import unittest
from pathlib import Path

from pnf import analysis, showcase
from pnf.chart import build


def days(*vals, start=1):
    return [(f"2024-{(start + i) // 28 + 1:02d}-{(start + i) % 28 + 1:02d}",
             float(v), float(v), float(v)) for i, v in enumerate(vals)]


COMPARISONS = """# Comparisons

## Provenance

text

## The showpieces — cross-cohort synthesis (the See's Candies class)

*intro*

| # | Ticker | Cohort standing | Why |
|---|---|---|---|
| 1 | **CME** | #1 fee compounders (XLF) | strongest moat |
| 2 | **V** | #1 payments (XLF) | toll bridge |
| 6 | **MCO** (with **SPGI**) | #2–3 fee compounders (XLF) | duopoly |
| 13 | **BRK.B** | #1 whatever | test dotted ticker |

**Cohort winners excluded** ...

## Industrials addendum

| 1 | **TDG** | not a showpiece | must not be parsed |
"""


class TestShowpieces(unittest.TestCase):
    def test_parses_bold_tickers_in_section_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "dossiers").mkdir()
            (root / "dossiers" / "_comparisons.md").write_text(COMPARISONS, encoding="utf-8")
            rows = showcase.showpieces(root)
        self.assertEqual([r[0] for r in rows], ["CME", "V", "MCO", "SPGI", "BRK-B"])
        self.assertEqual(rows[2][1], rows[3][1])  # MCO and SPGI share rank 6
        self.assertEqual(rows[0][2], "#1 fee compounders (XLF)")
        self.assertNotIn("TDG", [r[0] for r in rows])


class TestShape(unittest.TestCase):
    def _shape(self, bars, rs_sector="n/a", rs_market="n/a"):
        ch = build(bars, 3)
        an = analysis.analyze(ch, "T")
        return showcase.shape(ch, an, rs_sector, rs_market)

    def test_staircase_uptrend_scores_high(self):
        # rising columns with shallow pullbacks: 20->30, back to 25, up to 40,
        # back to 35, up to 50, back to 45, up to 60 (box $0.50/$1 bands)
        seq = list(range(20, 31)) + list(range(30, 24, -1)) + list(range(25, 41)) \
            + list(range(40, 34, -1)) + list(range(35, 51)) + list(range(50, 44, -1)) \
            + list(range(45, 61))
        sh = self._shape(days(*seq), "bullish", "bullish")
        self.assertEqual(sh.status, "bullish")
        self.assertTrue(sh.above_support)
        self.assertGreaterEqual(sh.higher_lows, 2)
        self.assertEqual(sh.flips_2y, 0)
        self.assertGreater(sh.score, 60)
        self.assertEqual(sh.components["rs_sector"], 7.0)

    def test_collapse_scores_low(self):
        seq = list(range(60, 40, -1)) + list(range(40, 44)) + list(range(44, 20, -1))
        sh = self._shape(days(*seq), "bearish", "bearish")
        self.assertEqual(sh.status, "bearish")
        self.assertFalse(sh.above_support)
        self.assertGreater(sh.drawdown_pct, 50)
        self.assertLess(sh.score, 20)

    def test_flips_count_direction_changes_not_signals(self):
        # an expanding saw-tooth: each swing makes a higher high then a lower
        # low, so every leg fires a breakout or breakdown (equal tops would not)
        seq = []
        for k in range(4):
            seq += list(range(20 - 2 * k, 32 + 2 * k)) + list(range(32 + 2 * k, 16 - 2 * k, -1))
        seq += list(range(16 - 6, 42))
        sh = self._shape(days(*seq))
        self.assertGreaterEqual(sh.flips_2y, 3)
        self.assertEqual(sh.components["few_whipsaws"],
                         round(max(0.0, 1.0 - max(sh.flips_2y - 1, 0) / 4.0) * 10.0, 1))

    def test_to_dict_serialises_components(self):
        sh = self._shape(days(*range(20, 40)))
        d = sh.to_dict()
        self.assertIsInstance(d["components"], str)
        self.assertIn("bullish", d["components"])


if __name__ == "__main__":
    unittest.main()
