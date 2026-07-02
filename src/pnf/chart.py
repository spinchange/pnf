"""P&F chart construction (high/low method, n-box reversal) and signal detection.

Matches the StockCharts daily P&F convention: an X column extends if the day's
high reaches the next box; only if it does not is the day's low checked for a
reversal. Mirror logic for O columns. Extension always beats reversal.
"""
from dataclasses import dataclass

from .boxes import Ladder
from .patterns import classify


@dataclass
class Column:
    kind: str            # "X" or "O"
    hi: int              # ladder index of the top filled box
    lo: int              # ladder index of the bottom filled box
    start: str           # date the column began
    end: str             # date of the last box added
    signaled: bool = False  # this column has already fired a breakout/breakdown


@dataclass
class Signal:
    kind: str        # "buy" or "sell"
    pattern: str     # e.g. "Double Top Breakout"
    date: str
    trigger: float   # price of the box that completed the signal
    col_index: int   # index into Chart.columns of the column that fired


@dataclass
class Chart:
    ladder: Ladder
    columns: list[Column]
    signals: list[Signal]
    last_date: str
    last_close: float

    @property
    def last_signal(self) -> Signal | None:
        return self.signals[-1] if self.signals else None


def build(bars, reversal: int = 3) -> Chart:
    """bars: iterable of (date, high, low, close), oldest first."""
    bars = list(bars)
    if not bars:
        raise ValueError("no price data")
    ladder = Ladder(max(b[1] for b in bars))

    d0, h0, l0, c0 = bars[0]
    hi, lo = ladder.floor(h0), ladder.ceil(l0)
    if hi < lo:  # first day's range sat inside a single box
        hi = lo = ladder.floor(c0)
    kind = "X" if c0 >= (h0 + l0) / 2 else "O"
    columns = [Column(kind, hi, lo, d0, d0)]
    signals: list[Signal] = []

    for date, h, l, _c in bars[1:]:
        col = columns[-1]
        if col.kind == "X":
            nh = ladder.floor(h)
            if nh > col.hi:
                col.hi, col.end = nh, date
                _check_buy(columns, signals, ladder, date)
            else:
                nl = ladder.ceil(l)
                if col.hi - nl >= reversal:
                    columns.append(Column("O", col.hi - 1, nl, date, date))
                    _check_sell(columns, signals, ladder, date)
        else:
            nl = ladder.ceil(l)
            if nl < col.lo:
                col.lo, col.end = nl, date
                _check_sell(columns, signals, ladder, date)
            else:
                nh = ladder.floor(h)
                if nh - col.lo >= reversal:
                    columns.append(Column("X", nh, col.lo + 1, date, date))
                    _check_buy(columns, signals, ladder, date)

    return Chart(ladder, columns, signals, bars[-1][0], bars[-1][3])


def _check_buy(columns, signals, ladder, date):
    cur = columns[-1]
    n = len(columns) - 1
    if cur.signaled or n < 2 or cur.hi <= columns[n - 2].hi:
        return
    cur.signaled = True
    signals.append(Signal("buy", classify(columns, signals, "buy"), date,
                          ladder[columns[n - 2].hi + 1], n))


def _check_sell(columns, signals, ladder, date):
    cur = columns[-1]
    n = len(columns) - 1
    if cur.signaled or n < 2 or cur.lo >= columns[n - 2].lo:
        return
    cur.signaled = True
    signals.append(Signal("sell", classify(columns, signals, "sell"), date,
                          ladder[columns[n - 2].lo - 1], n))
