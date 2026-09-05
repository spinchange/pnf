"""Relative strength (Dorsey Wright convention): P&F charts of a price ratio.

The ratio numerator/denominator × 100 is charted close-only on a log-scale
grid (each box `pct` above the one below), 3-box reversal. An X column means
the numerator is outperforming the denominator near term; a buy/sell signal
marks a longer-lived leadership change — RS signals historically persist for
years, which is what makes them useful as a filter on top of the trend chart.
"""
from . import chart as chartmod, data

MARKET = "SPY"
SCALE = 100.0
BOX_PCT = 0.02  # 2% boxes


def sector_of() -> dict[str, str]:
    """ticker -> sector ETF, inverted from the snowball membership CSVs."""
    return {t: etf for etf, ts in data.snowball().items() for t in ts}


def ratio_bars(num, den, scale: float = SCALE):
    """Close-only ratio series from two (date, high, low, close) lists,
    oldest first. Dates present in only one series are dropped."""
    closes = {d: c for d, _h, _l, c in den}
    out = []
    for d, _h, _l, c in num:
        b = closes.get(d)
        if b:
            r = c / b * scale
            out.append((d, r, r, r))
    if not out:
        raise data.DataError("no overlapping dates between the two series")
    return out


def build(num_bars, den_bars, reversal: int = 3,
          pct: float = BOX_PCT) -> chartmod.Chart:
    return chartmod.build(ratio_bars(num_bars, den_bars), reversal, pct=pct)


def verdict(ch: chartmod.Chart) -> tuple[str, str]:
    """(status, reading) of an RS chart. The last signal is the long-term
    view, the current column the short-term one — four combinations."""
    sig = ch.last_signal
    col = ch.columns[-1].kind
    if sig is None:
        return "neutral", f"no RS signal yet ({col} column)"
    if sig.kind == "buy":
        if col == "X":
            return "bullish", "leader - outperforming long- and short-term"
        return "bullish", "leader pausing - RS buy intact, lagging near term"
    if col == "X":
        return "bearish", "laggard bouncing - near-term pop within an RS sell"
    return "bearish", "laggard - underperforming long- and short-term"
