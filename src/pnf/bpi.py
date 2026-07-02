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

Caveat: the history is computed from *today's* membership backfilled, so the
current reading is right but deep history carries survivorship bias — don't
backtest on it.
"""
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


def series(signals_by_ticker: dict[str, list],
           warmup: float = 0.5) -> list[tuple[str, float]]:
    """[(date, pct), ...] on every day the percentage changes. Rows are
    emitted only once `warmup` of the eventual members have had a first
    signal — the thin early denominator would otherwise print a meaningless
    giant first column on the BPI chart."""
    members = sum(1 for sigs in signals_by_ticker.values() if sigs)
    events = sorted(
        (s.date, t, s.kind)
        for t, sigs in signals_by_ticker.items() for s in sigs)
    state: dict[str, str] = {}
    out: list[tuple[str, float]] = []
    i = 0
    while i < len(events):
        day = events[i][0]
        while i < len(events) and events[i][0] == day:
            _, t, kind = events[i]
            state[t] = kind
            i += 1
        if len(state) >= warmup * members:
            pct = 100.0 * sum(k == "buy" for k in state.values()) / len(state)
            out.append((day, round(pct, 2)))
    return out


def compute(name: str, signals_by_ticker: dict[str, list]) -> Bpi:
    ser = series(signals_by_ticker)
    if not ser:
        raise ValueError(f"{name}: no signals in the universe")
    chart = build([(d, p, p, p) for d, p in ser], box=BOX)
    last: dict[str, str] = {}
    for t, sigs in signals_by_ticker.items():
        if sigs:
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
