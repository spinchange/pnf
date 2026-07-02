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
Signal Reversed   — three successively lower O-column lows and two lower
                    X-column highs ended by this Double Top Breakout names it
                    Bearish Signal Reversed (mirror: Bullish Signal Reversed).
Double            — everything else: the column simply crossed the prior
                    same-kind column's extreme.

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
        "reversed": "Bearish Signal Reversed",
        "catapult": "Bullish Catapult",
    },
    "sell": {
        "double": "Double Bottom Breakdown",
        "triple": "Triple Bottom Breakdown",
        "quadruple": "Quadruple Bottom Breakdown",
        "spread": "Spread Triple Bottom Breakdown",
        "ascending": "Descending Triple Bottom Breakdown",
        "reversed": "Bullish Signal Reversed",
        "catapult": "Bearish Catapult",
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
                                      names["spread"]):
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
    if n >= 5 and edge(columns[n - 4]) > level \
            and inner(columns[n - 5]) > inner(columns[n - 3]) > inner(columns[n - 1]):
        return names["reversed"]
    return names["double"]
