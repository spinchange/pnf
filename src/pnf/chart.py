"""P&F chart construction (high/low method, n-box reversal) and signal detection.

Matches the StockCharts daily P&F convention: an X column extends if the day's
high reaches the next box; only if it does not is the day's low checked for a
reversal. Mirror logic for O columns. Extension always beats reversal.
"""
from dataclasses import dataclass, field

from .boxes import Ladder
from .patterns import check_pole, check_trap, classify

MONTH_CODES = "123456789ABC"  # Jan-Sep, A=Oct B=Nov C=Dec (traditional)


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
class Alert:
    """A dated warning pattern (High/Low Pole) — not a signal: it never
    changes the chart's buy/sell status and stays out of Chart.signals."""
    name: str        # "High Pole Warning" or "Low Pole Reversal"
    date: str
    col_index: int   # column whose retracement fired the alert


@dataclass
class Chart:
    ladder: Ladder
    columns: list[Column]
    signals: list[Signal]
    last_date: str
    last_close: float
    # (column index, ladder index) -> month code: the first box printed in a
    # new month shows the month instead of X/O (traditional convention)
    marks: dict[tuple[int, int], str] = field(default_factory=dict)
    # column index -> "YYYY" where a new year first printed a box
    years: dict[int, str] = field(default_factory=dict)
    alerts: list[Alert] = field(default_factory=list)
    reversal: int = 3

    @property
    def last_signal(self) -> Signal | None:
        return self.signals[-1] if self.signals else None

    @property
    def alert(self) -> Alert | None:
        """The standing alert: the most recent High/Low Pole event, unless a
        signal has fired since (same column and later, or any later column) —
        a real breakout/breakdown supersedes the warning."""
        if not self.alerts:
            return None
        al = self.alerts[-1]
        s = self.last_signal
        if s and (s.col_index, s.date) >= (al.col_index, al.date):
            return None
        return al

    @property
    def reversal_idx(self) -> int | None:
        """Ladder index of the price that would flip the current column —
        `reversal` boxes off its extreme. None if it falls off the scale."""
        col = self.columns[-1]
        idx = (col.hi - self.reversal if col.kind == "X"
               else col.lo + self.reversal)
        return idx if idx >= 0 else None


def build(bars, reversal: int = 3, box: float | None = None) -> Chart:
    """bars: iterable of (date, high, low, close), oldest first.
    `box` switches to a fixed box size (see Ladder)."""
    bars = list(bars)
    if not bars:
        raise ValueError("no price data")
    ladder = Ladder(max(b[1] for b in bars), box)

    d0, h0, l0, c0 = bars[0]
    hi, lo = ladder.floor(h0), ladder.ceil(l0)
    if hi < lo:  # first day's range sat inside a single box
        hi = lo = ladder.floor(c0)
    kind = "X" if c0 >= (h0 + l0) / 2 else "O"
    columns = [Column(kind, hi, lo, d0, d0)]
    signals: list[Signal] = []
    alerts: list[Alert] = []
    marks: dict[tuple[int, int], str] = {}
    years: dict[int, str] = {}
    last_ym = d0[:7]  # "YYYY-MM" of the last printed box

    def stamp(date, box_idx):
        """The first box printed in a new month carries the month code; the
        first in a new year also marks the column for the year axis."""
        nonlocal last_ym
        if date[:7] == last_ym:
            return
        if date[:4] != last_ym[:4]:
            years[len(columns) - 1] = date[:4]
        marks[(len(columns) - 1, box_idx)] = MONTH_CODES[int(date[5:7]) - 1]
        last_ym = date[:7]

    for date, h, l, _c in bars[1:]:
        col = columns[-1]
        if col.kind == "X":
            nh = ladder.floor(h)
            if nh > col.hi:
                first = col.hi + 1
                col.hi, col.end = nh, date
                stamp(date, first)
                _check_buy(columns, signals, ladder, date)
                _check_pole(columns, alerts, ladder, date)
            else:
                nl = ladder.ceil(l)
                if col.hi - nl >= reversal:
                    columns.append(Column("O", col.hi - 1, nl, date, date))
                    stamp(date, col.hi - 1)
                    check_trap(columns, signals, ladder)
                    _check_sell(columns, signals, ladder, date)
                    _check_pole(columns, alerts, ladder, date)
        else:
            nl = ladder.ceil(l)
            if nl < col.lo:
                first = col.lo - 1
                col.lo, col.end = nl, date
                stamp(date, first)
                _check_sell(columns, signals, ladder, date)
                _check_pole(columns, alerts, ladder, date)
            else:
                nh = ladder.floor(h)
                if nh - col.lo >= reversal:
                    columns.append(Column("X", nh, col.lo + 1, date, date))
                    stamp(date, col.lo + 1)
                    check_trap(columns, signals, ladder)
                    _check_buy(columns, signals, ladder, date)
                    _check_pole(columns, alerts, ladder, date)

    return Chart(ladder, columns, signals, bars[-1][0], bars[-1][3],
                 marks, years, alerts, reversal)


def _check_buy(columns, signals, ladder, date):
    cur = columns[-1]
    n = len(columns) - 1
    if cur.signaled or n < 2 or cur.hi <= columns[n - 2].hi:
        return
    cur.signaled = True
    signals.append(Signal("buy", classify(columns, signals, "buy"), date,
                          ladder[columns[n - 2].hi + 1], n))


def _check_pole(columns, alerts, ladder, date):
    n = len(columns) - 1
    if alerts and alerts[-1].col_index == n:
        return  # this column already alerted
    name = check_pole(columns, ladder)
    if name:
        alerts.append(Alert(name, date, n))


def _check_sell(columns, signals, ladder, date):
    cur = columns[-1]
    n = len(columns) - 1
    if cur.signaled or n < 2 or cur.lo >= columns[n - 2].lo:
        return
    cur.signaled = True
    signals.append(Signal("sell", classify(columns, signals, "sell"), date,
                          ladder[columns[n - 2].lo - 1], n))
