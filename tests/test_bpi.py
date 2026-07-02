"""Bullish Percent Index: series aggregation, six-state readings, universe
loading. BPI charts are built from synthetic percent series on the fixed
2-point ladder, one bar per swing (same style as the pattern tests)."""
import tempfile
import unittest
from pathlib import Path

from pnf import bpi, data
from pnf.chart import Signal, build


def sig(kind, day):
    return Signal(kind, "Double Top Breakout" if kind == "buy"
                  else "Double Bottom Breakdown", day, 50.0, 0)


def bpi_chart(*pcts):
    bars = [(f"2026-01-{i + 1:02d}", float(p), float(p), float(p))
            for i, p in enumerate(pcts)]
    return build(bars, box=bpi.BOX)


class TestSeries(unittest.TestCase):
    def test_percentages_on_change_days(self):
        sigs = {"A": [sig("buy", "2026-01-05"), sig("sell", "2026-01-20")],
                "B": [sig("sell", "2026-01-05")],
                "C": [sig("buy", "2026-01-12")]}
        # 01-05: A buy, B sell -> 50%; 01-12: C joins on a buy -> 66.67%;
        # 01-20: A flips to sell -> 33.33%
        self.assertEqual(bpi.series(sigs),
                         [("2026-01-05", 50.0), ("2026-01-12", 66.67),
                          ("2026-01-20", 33.33)])

    def test_compute_counts(self):
        sigs = {"A": [sig("buy", "2026-01-05")],
                "B": [sig("sell", "2026-01-06")],
                "C": []}  # never signaled: not in the denominator
        b = bpi.compute("TEST", sigs)
        self.assertEqual((b.members, b.bullish, b.pct), (2, 1, 50.0))


class TestSixStates(unittest.TestCase):
    def test_bull_confirmed(self):
        c = bpi_chart(40, 52, 46, 54)  # X column broke the prior top
        self.assertEqual(bpi.classify(c), "Bull Confirmed")

    def test_bear_confirmed(self):
        c = bpi_chart(60, 48, 54, 46)
        self.assertEqual(bpi.classify(c), "Bear Confirmed")

    def test_bull_alert(self):
        c = bpi_chart(40, 26, 34)  # reversed up from below 30, no buy yet
        self.assertEqual(bpi.classify(c), "Bull Alert")

    def test_bear_alert(self):
        c = bpi_chart(60, 74, 66)  # reversed down from above 70, no sell yet
        self.assertEqual(bpi.classify(c), "Bear Alert")

    def test_bull_correction(self):
        c = bpi_chart(40, 52, 46, 54, 48)  # buy signal, then a mid-zone dip
        self.assertEqual(bpi.classify(c), "Bull Correction")

    def test_bear_correction(self):
        c = bpi_chart(60, 48, 54, 46, 52)  # sell signal, then a mid-zone pop
        self.assertEqual(bpi.classify(c), "Bear Correction")


class TestSnowballUniverse(unittest.TestCase):
    def setUp(self):
        self._saved = data.SNOWBALL
        self.tmp = tempfile.TemporaryDirectory()
        data.SNOWBALL = Path(self.tmp.name)

    def tearDown(self):
        data.SNOWBALL = self._saved
        self.tmp.cleanup()

    def test_symbols_normalized_to_yahoo_form(self):
        (data.SNOWBALL / "xlf-components.csv").write_text(
            "symbol,name\nBRK.B,Berkshire Hathaway\nJPM,JPMorgan\n")
        self.assertEqual(data.sector_components("XLF"), ["BRK-B", "JPM"])

    def test_snowball_collects_present_sectors(self):
        (data.SNOWBALL / "xle-components.csv").write_text(
            "symbol,name\nXOM,Exxon\n")
        self.assertEqual(data.snowball(), {"XLE": ["XOM"]})

    def test_missing_file_raises(self):
        with self.assertRaises(data.DataError):
            data.sector_components("XLK")


if __name__ == "__main__":
    unittest.main()
