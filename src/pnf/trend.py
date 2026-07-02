"""45-degree P&F trend lines (bullish support / bearish resistance).

StockCharts convention: trend lines rise or fall exactly one box per column.
A bullish support line starts one box below a significant bottom and rises;
it is violated when a column prints at or below it. A bearish resistance
line starts one box above a significant top and falls; violated when a
column prints at or on it. On violation the opposite line begins: bearish
resistance one box above the highest top since the broken line's anchor,
bullish support one box below the lowest low since the broken line's anchor
(ties resolve to the most recent column). When a long slide leaves that
anchor's line already pierced at the violating column, the new line restarts
from the violating column itself.

The chart is seeded with a support line one box below the first column's
low; an initial downtrend violates it immediately and flips, so the seed
choice washes out.
"""
from dataclasses import dataclass


@dataclass
class Line:
    kind: str               # "support" or "resistance"
    col: int                # anchor column index
    idx: int                # ladder index of the line at the anchor column
    end: int | None = None  # column index where violated; None = still active

    def at(self, col: int) -> int:
        """Ladder index of the line at a given column (may be negative once a
        falling resistance line runs off the bottom of the scale)."""
        step = col - self.col
        return self.idx + step if self.kind == "support" else self.idx - step


def lines(columns) -> list["Line"]:
    if not columns:
        return []
    out = [Line("support", 0, max(columns[0].lo - 1, 0))]
    for i in range(1, len(columns)):
        ln = out[-1]
        c = columns[i]
        if ln.kind == "support" and c.lo <= ln.at(i):
            ln.end = i
            j = max(range(ln.col, i), key=lambda k: (columns[k].hi, k))
            new = Line("resistance", j, columns[j].hi + 1)
            if c.hi >= new.at(i):
                new = Line("resistance", i, c.hi + 1)
            out.append(new)
        elif ln.kind == "resistance" and c.hi >= ln.at(i):
            ln.end = i
            j = min(range(ln.col, i), key=lambda k: (columns[k].lo, -k))
            new = Line("support", j, max(columns[j].lo - 1, 0))
            if c.lo <= new.at(i):
                new = Line("support", i, max(c.lo - 1, 0))
            out.append(new)
    return out
