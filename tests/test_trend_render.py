"""45-degree trend lines and chart rendering (months, years, bottom axis).

Same synthetic-bar approach as test_patterns: integer prices on the $1 box
band so every column is exact.
"""
import unittest

from pnf.analysis import analyze
from pnf.chart import build
from pnf.render import render
from pnf.trend import lines


def bars(*days):
    """days: (date, price) pairs; high = low = close = price."""
    return [(d, float(p), float(p), float(p)) for d, p in days]


def chart(*prices):
    return build(bars(*((f"2026-01-{i + 1:02d}", p)
                        for i, p in enumerate(prices))))


class TestTrendLines(unittest.TestCase):
    def test_uptrend_keeps_the_seed_support_line(self):
        c = chart(50, 55, 52, 56, 53, 57)
        tl = lines(c.columns)
        self.assertEqual(len(tl), 1)
        self.assertEqual(tl[0].kind, "support")
        self.assertIsNone(tl[0].end)

    def test_support_break_flips_to_resistance_from_the_top(self):
        # support seeded one box below 50 rises to 52 by column 3;
        # the slide to 45 violates it and a resistance line starts one
        # box above the 56 top, putting the line at 56 on the last column
        c = chart(50, 55, 52, 56, 45)
        tl = lines(c.columns)
        self.assertEqual([(ln.kind, ln.end) for ln in tl],
                         [("support", 3), ("resistance", None)])
        an = analyze(c, "TEST")
        self.assertEqual(an.trend, "below bearish resistance line (56.00)")

    def test_resistance_break_flips_back_to_support(self):
        c = chart(50, 55, 52, 56, 45, 58)
        tl = lines(c.columns)
        self.assertEqual(tl[-1].kind, "support")
        self.assertIsNone(tl[-1].end)
        self.assertTrue(analyze(c, "TEST").trend.startswith(
            "above bullish support line"))


class TestReversal(unittest.TestCase):
    def test_x_column_reversal_is_three_boxes_off_the_high(self):
        c = chart(50, 55, 52, 56)  # current column X(53-56)
        self.assertEqual(analyze(c, "TEST").reversal, 53.0)

    def test_o_column_reversal_is_three_boxes_off_the_low(self):
        c = chart(60, 55, 58, 54)  # current column O(57-54)
        self.assertEqual(analyze(c, "TEST").reversal, 57.0)

    def test_reversal_marker_on_the_chart(self):
        out = render(chart(50, 55, 52, 56), color=False)
        row = next(r for r in out.splitlines() if "3-box reversal" in r)
        self.assertIn("53.00", row)


class TestRender(unittest.TestCase):
    def test_month_code_replaces_the_box_mark(self):
        c = build(bars(("2026-01-05", 50), ("2026-01-20", 55),
                       ("2026-02-03", 52), ("2026-03-10", 56)))
        out = render(c, color=False)
        # three columns -> the cell area is the first 5 chars of each row
        # (price labels, which also contain digits, start after that)
        cells = "\n".join(r[:5] for r in out.splitlines())
        self.assertIn("2", cells)  # O column's first box printed in February
        self.assertIn("3", cells)  # breakout column's first box in March

    def test_bottom_axis_and_year_marker(self):
        c = build(bars(("2025-12-05", 50), ("2025-12-20", 55),
                       ("2025-12-28", 52), ("2026-01-06", 56)))
        out = render(c, color=False)
        rows = out.splitlines()
        self.assertTrue(set(rows[-2]) == {"-"})   # bottom axis line
        self.assertIn("2026", rows[-1])           # year under the new column
        # January's first box shows "1" in place of the X
        self.assertIn("1", "".join(r[:5] for r in rows[:-2]))

    def test_no_year_row_when_single_year(self):
        c = chart(50, 55, 52, 56)
        rows = render(c, color=False).splitlines()
        self.assertTrue(set(rows[-1]) == {"-"})   # axis is the last row


if __name__ == "__main__":
    unittest.main()
