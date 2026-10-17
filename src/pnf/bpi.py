"""Bullish Percent Index — Chartcraft/Dorsey breadth off our own signals.

BPI(day) = percent of the universe whose most recent P&F signal is a buy.
Each ticker's signal history is a dated step function, so the whole series
falls out of one chart build per ticker: merge every ticker's signal events
chronologically, hold per-ticker state, and record the percentage each day
it changes. A ticker joins the denominator at its first signal.

The series is then charted P&F-style the traditional way — 2-point boxes on
the 0-100 scale, 3-box reversal — and read with the six-state vocabulary:

Bull Confirmed  — X column, latest BPI-chart signal is a buy
Bull Alert      — X column reversed up from below 30, no buy signal yet
Bear Correction — X column, latest signal still a sell (not from below 30)
Bear Confirmed  — O column, latest BPI-chart signal is a sell
Bear Alert      — O column reversed down from above 70, no sell signal yet
Bull Correction — O column, latest signal still a buy (not from above 70)

Membership is point-in-time when a dated history is supplied (tape's daily
SPDR holdings): on each day only that day's members count, so an index add
joins and a drop leaves the denominator on the holdings date. Days before
the first snapshot use the first snapshot's members — that stretch still
carries survivorship bias, so don't backtest across it. Without a history,
today's members are backfilled across the whole series.
"""
from bisect import bisect_right
from dataclasses import dataclass, field

from .chart import Chart, build

BOX = 2.0
OVERSOLD = 30.0
OVERBOUGHT = 70.0


@dataclass
class Bpi:
    name: str
    chart: Chart              # P&F chart of the BPI series itself
    pct: float                # latest reading
    status: str               # six-state reading
    members: int              # tickers in the denominator
    bullish: int              # tickers on a buy signal
    series: list[tuple[str, float]] = field(default_factory=list)

    def pct_on(self, day: str) -> float | None:
        """The reading in force at the close on `day`; None before the
        series starts."""
        i = bisect_right([d for d, _ in self.series], day)
        return self.series[i - 1][1] if i else None


Membership = list[tuple[str, set[str]]]   # [(as_of date, members)] oldest first


def _members_on(membership: Membership, day: str) -> set[str]:
    """Members per the latest snapshot on or before `day`; the first
    snapshot before the history starts."""
    i = bisect_right([d for d, _ in membership], day)
    return membership[max(i - 1, 0)][1]


def series(signals_by_ticker: dict[str, list], warmup: float = 0.5,
           membership: Membership | None = None) -> list[tuple[str, float]]:
    """[(date, pct), ...] on every day a signal fires or membership changes.
    Only that day's members count (all tickers, without a membership
    history). Rows are emitted only once `warmup` of the day's members have
    had a first signal — the thin early denominator would otherwise print a
    meaningless giant first column on the BPI chart."""
    signaled = {t for t, sigs in signals_by_ticker.items() if sigs}
    events = sorted(
        (s.date, t, s.kind)
        for t, sigs in signals_by_ticker.items() for s in sigs)
    if membership:
        # Re-read the percentage on each holdings date the membership changes
        events += [(d, "", "") for (_, prev), (d, cur) in
                   zip(membership, membership[1:]) if cur != prev]
        events.sort()
    state: dict[str, str] = {}
    out: list[tuple[str, float]] = []
    i = 0
    while i < len(events):
        day = events[i][0]
        while i < len(events) and events[i][0] == day:
            _, t, kind = events[i]
            if t:
                state[t] = kind
            i += 1
        active = _members_on(membership, day) if membership else signaled
        counted = [k for t, k in state.items() if t in active]
        if counted and len(counted) >= warmup * len(active & signaled):
            pct = 100.0 * sum(k == "buy" for k in counted) / len(counted)
            out.append((day, round(pct, 2)))
    return out


def compute(name: str, signals_by_ticker: dict[str, list],
            membership: Membership | None = None) -> Bpi:
    ser = series(signals_by_ticker, membership=membership)
    if not ser:
        raise ValueError(f"{name}: no signals in the universe")
    chart = build([(d, p, p, p) for d, p in ser], box=BOX)
    current = membership[-1][1] if membership else None
    last: dict[str, str] = {}
    for t, sigs in signals_by_ticker.items():
        if sigs and (current is None or t in current):
            last[t] = sigs[-1].kind
    return Bpi(name, chart, ser[-1][1], classify(chart),
               len(last), sum(k == "buy" for k in last.values()), ser)


def classify(chart: Chart) -> str:
    """Six-state reading of the BPI's own P&F chart. Alerts require the
    reversal to come out of the extreme zone: an X column rising from below
    30 (the prior O column bottomed under 30), an O column falling from
    above 70 (the prior X column topped over 70)."""
    col = chart.columns[-1]
    sig = chart.last_signal
    lad = chart.ladder
    if col.kind == "X":
        if sig and sig.kind == "buy":
            return "Bull Confirmed"
        return "Bull Alert" if lad[col.lo] <= OVERSOLD else "Bear Correction"
    if sig and sig.kind == "sell":
        return "Bear Confirmed"
    return "Bear Alert" if lad[col.hi] >= OVERBOUGHT else "Bull Correction"
