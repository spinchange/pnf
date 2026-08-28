"""Price objectives, logical stops, reward/risk.

Objective methods:

"sc" (default) — StockCharts' automated Breakout Method, reverse-engineered
and verified to the dollar on ten _TICKER charts (2026-06-11): bullish on
LRCX 439, OXY 77, MSCI 679, IRM 166, CASY 1279, NVR 7299; bearish on BLK
961, BKNG 149, MELI 1441, AZO 2851. The measure column is the first
buy/sell-signal column after the most recent opposite signal (the column
that reversed it). Bullish objective = column_low - 1 + 3 * (high - low +
box); bearish = column_high + 1 - 2 * (high - low + box), box taken at the
anchor end. objective_active mirrors StockCharts' "(Tentative)" label
(measure column still building).

"classic" — Dorsey vertical count on the latest signal column, walked along
the box ladder: 3x the column's box count above its low (bullish), 2x below
its high (bearish).

Stop: the price that would print the opposite signal — one box below the most
recent completed O-column low (bullish) or one box above the most recent
completed X-column high (bearish).
"""
from dataclasses import asdict, dataclass

from .chart import Chart
from .trend import lines as trend_lines


@dataclass
class Analysis:
    ticker: str
    date: str
    close: float
    status: str                     # "bullish" / "bearish" / "no signal"
    pattern: str | None = None
    signal_date: str | None = None
    trigger: float | None = None
    alert: str | None = None       # standing High/Low Pole warning, if any
    alert_date: str | None = None
    objective: float | None = None
    objective_active: bool = False  # count column still building; objective can move
    stop: float | None = None
    reward: float | None = None
    risk: float | None = None
    rr: float | None = None
    note: str | None = None
    trend: str | None = None  # active 45-degree line and its current level
    reversal: float | None = None  # price that flips the current column

    def to_dict(self) -> dict:
        return asdict(self)


def analyze(chart: Chart, ticker: str = "", method: str = "sc") -> Analysis:
    close = round(chart.last_close, 2)
    trend = _trend(chart)
    ri = chart.reversal_idx
    rev = chart.ladder[ri] if ri is not None else None
    al = chart.alert
    alert, alert_date = (al.name, al.date) if al else (None, None)
    sig = chart.last_signal
    if sig is None:
        return Analysis(ticker, chart.last_date, close, "no signal",
                        alert=alert, alert_date=alert_date,
                        note="no breakout or breakdown in the loaded history",
                        trend=trend, reversal=rev)

    lad = chart.ladder
    obj_col = chart.columns[_measure_index(chart, sig.kind)] if method == "sc" \
        else chart.columns[sig.col_index]
    n = obj_col.hi - obj_col.lo + 1

    if sig.kind == "buy":
        if method == "sc":
            lo, hi = lad[obj_col.lo], lad[obj_col.hi]
            box = lad[obj_col.lo + 1] - lo
            objective = round(lo - 1 + 3 * (hi - lo + box), 2)
        else:
            objective = lad[obj_col.lo + 3 * n]
        ref = _last_completed(chart.columns, "O")
        stop = lad[ref.lo - 1] if ref and ref.lo >= 1 else None
        reward = objective - close
        risk = (close - stop) if stop is not None else None
        status = "bullish"
    else:
        if method == "sc":
            lo, hi = lad[obj_col.lo], lad[obj_col.hi]
            box = lad[obj_col.hi + 1] - hi
            objective = max(round(hi + 1 - 2 * (hi - lo + box), 2), 0.0)
        else:
            objective = lad[max(obj_col.hi - 2 * n, 0)]
        ref = _last_completed(chart.columns, "X")
        stop = lad[ref.hi + 1] if ref else None
        reward = close - objective
        risk = (stop - close) if stop is not None else None
        status = "bearish"

    rr = note = None
    if reward <= 0:
        note = "price already past the objective"
    elif risk is None:
        note = "no opposite column yet - no stop reference"
    elif risk <= 0:
        note = "price already through the stop level"
    else:
        rr = round(reward / risk, 2)

    return Analysis(
        ticker, chart.last_date, close, status,
        pattern=sig.pattern, signal_date=sig.date, trigger=sig.trigger,
        alert=alert, alert_date=alert_date,
        objective=objective,
        objective_active=obj_col is chart.columns[-1],
        stop=stop,
        reward=round(reward, 2),
        risk=round(risk, 2) if risk is not None else None,
        rr=rr, note=note, trend=trend, reversal=rev,
    )


def _trend(chart: Chart) -> str | None:
    """The active 45-degree line at the last column. By construction the
    chart sits above an unviolated support line / below a resistance line."""
    tl = trend_lines(chart.columns)
    if not tl:
        return None
    ln = tl[-1]
    v = ln.at(len(chart.columns) - 1)
    if v < 0:  # a falling resistance line ran off the bottom of the scale
        return None
    price = chart.ladder[v]
    return (f"above bullish support line ({price:.2f})" if ln.kind == "support"
            else f"below bearish resistance line ({price:.2f})")


def _measure_index(chart: Chart, kind: str) -> int:
    """Column index of StockCharts' measure column: the first `kind` signal
    after the most recent opposite signal — the column that reversed it."""
    opposite = [s for s in chart.signals if s.kind != kind]
    last_opp = opposite[-1].col_index if opposite else -1
    return next(s.col_index for s in chart.signals
                if s.kind == kind and s.col_index > last_opp)


def _last_completed(columns, kind: str):
    """Most recent column of `kind`, excluding the still-active last column."""
    done = [c for c in columns[:-1] if c.kind == kind]
    return done[-1] if done else None
