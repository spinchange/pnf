"""Signal pattern classification — the StockCharts 3-box-reversal catalog.

`classify` runs at the moment a column crosses a prior same-kind extreme
(chart.py has already established the breakout/breakdown) and names the
formation. Checks run most-specific first:

Catapult          — the previous signal was a Triple/Quadruple/Spread Triple
                    breakout on the immediately prior same-kind column, the
                    pullback column held (no opposite signal fired), and this
                    breakout completes the pattern.
Quadruple         — the three prior same-kind columns share an equal extreme.
Triple            — the two prior same-kind columns share an equal extreme.
Spread Triple     — an earlier same-kind column matches the broken extreme at
                    least seven columns back, every same-kind column between
                    stayed short of it, and no opposite signal fired within
                    the pattern.
Ascending Triple  — back-to-back Double Top Breakouts with a rising inner
(Descending)        O-column low, and no breakdown inside the formation: the
                    O column between the two breakouts must not itself have
                    fired a signal (mirror: falling inner X-column high).
                    Verified against StockCharts' _LRCX label of 2026-06-11,
                    which stays "Double Top Breakout" because the inner
                    O column had broken down.
Triangle          — converging five-column formation: a lower X-column high
                    and a higher O-column low, resolved by this breakout
                    (Bullish Triangle) or breakdown (Bearish Triangle).
Signal Reversed   — three successively lower O-column lows and two lower
                    X-column highs ended by this Double Top Breakout names it
                    Bearish Signal Reversed (mirror: Bullish Signal Reversed).
Double            — everything else: the column simply crossed the prior
                    same-kind column's extreme.

`check_trap` runs separately, when a reversal completes a column: a
Triple/Quadruple/Spread Triple breakout that exceeded the broken level by
exactly one box and then reversed is renamed Bull Trap (mirror: Bear Trap).
The signal's kind is unchanged — StockCharts likewise keeps the chart on its
buy/sell status and only relabels the pattern. A trap that later resolves
with a fresh breakout completes a Catapult (a one-box initial breakout is
still an initial breakout).

`check_pole` detects the alert patterns — dated warnings, not signals; they
never enter the signal history (which the BPI and the catapult/ascending
lookbacks depend on). High Pole Warning: the prior X column topped the
previous X column by at least 3 boxes (the pole), and the current unsignaled
O column has retraced at least 50% of the pole's rise above that previous
top. Low Pole Reversal is the exact mirror. The 50% is measured in price
above the previous same-kind extreme — not against the whole pole column —
verified against StockCharts' _SPGI "High Pole Warning" of 2026-07-09
(pole 380-448 over a 412 prior top: fired at the 424 box, 24 of 36 points
retraced; the whole-column measure would have needed 412 and never fired).

Sell-side patterns are exact mirrors: levels are negated so "greater" always
means "further in the signal direction" and one code path serves both sides.
"""

_NAMES = {
    "buy": {
        "double": "Double Top Breakout",
        "triple": "Triple Top Breakout",
        "quadruple": "Quadruple Top Breakout",
        "spread": "Spread Triple Top Breakout",
        "ascending": "Ascending Triple Top Breakout",
        "triangle": "Bullish Triangle",
        "reversed": "Bearish Signal Reversed",
        "catapult": "Bullish Catapult",
        "trap": "Bull Trap",
    },
    "sell": {
        "double": "Double Bottom Breakdown",
        "triple": "Triple Bottom Breakdown",
        "quadruple": "Quadruple Bottom Breakdown",
        "spread": "Spread Triple Bottom Breakdown",
        "ascending": "Descending Triple Bottom Breakdown",
        "triangle": "Bearish Triangle",
        "reversed": "Bullish Signal Reversed",
        "catapult": "Bearish Catapult",
        "trap": "Bear Trap",
    },
}


def classify(columns, signals, kind: str) -> str:
    """Name the signal the last column just fired. Columns strictly alternate
    X/O, so same-kind neighbors sit at n-2, n-4, ... from the current column."""
    n = len(columns) - 1
    if kind == "buy":
        edge = lambda c: c.hi     # the extreme being broken
        inner = lambda c: c.lo    # the opposite extreme
    else:
        edge = lambda c: -c.lo
        inner = lambda c: -c.hi
    names = _NAMES[kind]
    level = edge(columns[n - 2])

    last = signals[-1] if signals else None
    prev_here = (last is not None and last.kind == kind
                 and last.col_index == n - 2)

    if prev_here and last.pattern in (names["triple"], names["quadruple"],
                                      names["spread"], names["trap"]):
        return names["catapult"]
    if n >= 6 and edge(columns[n - 4]) == level and edge(columns[n - 6]) == level:
        return names["quadruple"]
    if n >= 4 and edge(columns[n - 4]) == level:
        return names["triple"]
    if n >= 6 and edge(columns[n - 4]) < level:
        for j in range(n - 6, -1, -2):
            e = edge(columns[j])
            if e > level:
                break  # an intervening column pierced the line: no pattern
            if e == level:
                if not any(s.kind != kind and s.col_index > j for s in signals):
                    return names["spread"]
                break
    if prev_here and last.pattern in (names["double"], names["ascending"]) \
            and inner(columns[n - 1]) > inner(columns[n - 3]) \
            and not columns[n - 3].signaled:
        return names["ascending"]
    if n >= 4 and edge(columns[n - 4]) > level \
            and inner(columns[n - 1]) > inner(columns[n - 3]):
        return names["triangle"]
    if n >= 5 and edge(columns[n - 4]) > level \
            and inner(columns[n - 5]) > inner(columns[n - 3]) > inner(columns[n - 1]):
        return names["reversed"]
    return names["double"]


def check_trap(columns, signals, ladder):
    """Called when a reversal has just completed columns[-2]. If that column
    fired a multiple-top/bottom breakout and never extended past its trigger
    box (exceeded the broken level by exactly one box), the reversal makes it
    a trap — relabel the signal in place."""
    if not signals:
        return
    s = signals[-1]
    prev = columns[-2]
    if s.col_index != len(columns) - 2:
        return
    names = _NAMES[s.kind]
    if s.pattern not in (names["triple"], names["quadruple"], names["spread"]):
        return
    edge_idx = prev.hi if s.kind == "buy" else prev.lo
    if ladder[edge_idx] == s.trigger:
        s.pattern = names["trap"]


def check_pole(columns, ladder) -> str | None:
    """Alert-pattern check on the current column (see module docstring).
    Returns the alert name, or None. Never fires on a column that has
    signaled — a real breakout/breakdown supersedes the warning."""
    n = len(columns) - 1
    cur = columns[n]
    if cur.signaled or n < 3:
        return None
    pole, prev = columns[n - 1], columns[n - 3]
    if cur.kind == "O":
        if pole.hi - prev.hi < 3:
            return None
        rise = ladder[pole.hi] - ladder[prev.hi]
        if ladder[pole.hi] - ladder[cur.lo] >= 0.5 * rise:
            return "High Pole Warning"
    else:
        if prev.lo - pole.lo < 3:
            return None
        fall = ladder[prev.lo] - ladder[pole.lo]
        if ladder[cur.hi] - ladder[pole.lo] >= 0.5 * fall:
            return "Low Pole Reversal"
    return None
