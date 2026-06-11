"""StockCharts breakout-method objectives, verified against published charts.

Each ticker's history is frozen through 2026-06-11; the expected objective is
the exact "Bullish/Bearish Price Objective" StockCharts displayed on the
unadjusted (_TICKER) P&F chart that day. Coverage: both formula sides, six
box-size bands ($1/$2/$4/$5/$10/$50), a measure column crossing the $100
band (IRM), and StockCharts' "(Tentative)" flag, which corresponds to our
objective_active (measure column still building).
"""
import csv
import unittest
from pathlib import Path

from pnf.analysis import analyze
from pnf.chart import build

DATA = Path(__file__).parent / "data"

# ticker -> (objective on the _TICKER chart, side, shown as "(Tentative)")
EXPECTED = {
    "LRCX": (439.0, "bullish", False),
    "OXY": (77.0, "bullish", False),
    "MSCI": (679.0, "bullish", False),
    "IRM": (166.0, "bullish", False),
    "CASY": (1279.0, "bullish", True),
    "NVR": (7299.0, "bullish", True),
    "BLK": (961.0, "bearish", False),
    "BKNG": (149.0, "bearish", True),
    "MELI": (1441.0, "bearish", False),
    "AZO": (2851.0, "bearish", False),
}


def load_bars(ticker):
    with (DATA / f"{ticker.lower()}_2026-06-11.csv").open() as f:
        return [(r["date"], float(r["high"]), float(r["low"]), float(r["close"]))
                for r in csv.DictReader(f)]


class TestStockchartsObjectives(unittest.TestCase):
    def test_published_objectives(self):
        for ticker, (objective, status, tentative) in EXPECTED.items():
            with self.subTest(ticker=ticker):
                an = analyze(build(load_bars(ticker)), ticker, method="sc")
                self.assertEqual(an.objective, objective)
                self.assertEqual(an.status, status)
                self.assertEqual(an.objective_active, tentative)


if __name__ == "__main__":
    unittest.main()
