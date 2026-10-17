"""Bullish Percent Index: series aggregation, six-state readings, universe
loading. BPI charts are built from synthetic percent series on the fixed
2-point ladder, one bar per swing (same style as the pattern tests)."""
import tempfile
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None

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


class TestPointInTime(unittest.TestCase):
    SIGS = {"A": [sig("buy", "2026-01-05")],
            "B": [sig("sell", "2026-01-05")],
            "C": [sig("buy", "2026-01-05")]}

    def test_drop_and_add_move_the_denominator(self):
        # A, B members from the start; B dropped 01-10; C added 01-15
        mem = [("2026-01-08", {"A", "B"}), ("2026-01-10", {"A"}),
               ("2026-01-15", {"A", "C"})]
        # 01-05 is before the first snapshot: the first snapshot's members
        self.assertEqual(bpi.series(self.SIGS, membership=mem),
                         [("2026-01-05", 50.0), ("2026-01-10", 100.0),
                          ("2026-01-15", 100.0)])

    def test_unchanged_snapshots_add_no_rows(self):
        mem = [("2026-01-08", {"A", "B"}), ("2026-01-09", {"A", "B"})]
        self.assertEqual(bpi.series(self.SIGS, membership=mem),
                         [("2026-01-05", 50.0)])

    def test_pct_on_is_the_reading_in_force(self):
        b = bpi.compute("TEST", {"A": [sig("buy", "2026-01-05"), sig("sell", "2026-01-20")],
                                 "B": [sig("sell", "2026-01-05")]})
        self.assertEqual([b.pct_on(d) for d in ("2026-01-04", "2026-01-10", "2026-01-31")],
                         [None, 50.0, 0.0])

    def test_compute_counts_only_current_members(self):
        mem = [("2026-01-08", {"A", "B", "C"}), ("2026-01-10", {"B", "C"})]
        b = bpi.compute("TEST", self.SIGS, mem)
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


@unittest.skipIf(duckdb is None, "duckdb not installed")
class TestTapeUniverse(unittest.TestCase):
    def setUp(self):
        self._saved = data.SNOWBALL, data.TAPE_DB
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        data.SNOWBALL, data.TAPE_DB = root, root / "tape.duckdb"
        con = duckdb.connect(str(data.TAPE_DB))
        con.execute("CREATE TABLE spx_members (snapshot_date DATE, "
                    "sector_etf VARCHAR, as_of DATE, ticker VARCHAR, name VARCHAR)")
        con.executemany("INSERT INTO spx_members VALUES (?, ?, ?, ?, '')", [
            ("2026-07-11", "XLF", "2026-07-10", "BRK.B"),
            ("2026-07-11", "XLK", "2026-07-10", "APP"),
            ("2026-07-11", "XLC", "2026-07-10", "WBD"),
            ("2026-10-16", "XLF", "2026-10-15", "BRK.B"),
            ("2026-10-16", "XLC", "2026-10-15", "APP"),
            ("2026-10-16", "XLC", "2026-10-15", "SKYD/WS")])
        con.close()

    def tearDown(self):
        data.SNOWBALL, data.TAPE_DB = self._saved
        self.tmp.cleanup()

    def test_history_by_holdings_date(self):
        self.assertEqual(data.tape_history(), [
            ("2026-07-10", {"BRK-B": "XLF", "APP": "XLK", "WBD": "XLC"}),
            ("2026-10-15", {"BRK-B": "XLF", "APP": "XLC"})])  # warrant skipped

    def test_membership_is_latest_snapshot(self):
        m = data.membership()
        self.assertEqual(m.sectors, {"XLC": ["APP"], "XLF": ["BRK-B"]})
        self.assertEqual(m.as_of, "2026-10-15")
        self.assertTrue(m.source.startswith("tape 2026-10-15"))

    def test_membership_asof_uses_snapshot_on_or_before(self):
        m = data.membership("2026-10-14")
        self.assertEqual((m.as_of, m.sectors["XLK"]), ("2026-07-10", ["APP"]))
        self.assertEqual(len(m.history), 1)
        # Before tape starts: the first snapshot, not an error
        self.assertEqual(data.membership("2026-01-02").as_of, "2026-07-10")
        self.assertTrue(m.stale("2026-10-14"))
        self.assertFalse(m.stale("2026-07-12"))

    def test_falls_back_to_csvs_without_tape(self):
        data.TAPE_DB = data.SNOWBALL / "missing.duckdb"
        (data.SNOWBALL / "xle-components.csv").write_text("symbol,name\nXOM,Exxon\n")
        m = data.membership()
        self.assertEqual((m.sectors, m.history), ({"XLE": ["XOM"]}, None))
        self.assertIn("tape unavailable", m.source)


class TestAsofDate(unittest.TestCase):
    def test_friday_is_most_recent_friday(self):
        from datetime import date
        from unittest import mock
        from pnf import cli
        for today, want in (("2026-10-17", "2026-10-16"),   # Saturday
                            ("2026-10-16", "2026-10-16"),   # Friday itself
                            ("2026-10-15", "2026-10-09")):  # Thursday
            with mock.patch.object(cli, "date", wraps=date) as d:
                d.today.return_value = date.fromisoformat(today)
                self.assertEqual(cli._asof_date("friday"), want)

    def test_explicit_date_validated(self):
        from pnf import cli
        self.assertEqual(cli._asof_date("2026-07-03"), "2026-07-03")
        with self.assertRaises(ValueError):
            cli._asof_date("July 3")


if __name__ == "__main__":
    unittest.main()
