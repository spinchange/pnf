"""Daily OHLC via the Yahoo Finance v8 chart API (stdlib only), plus the
S&P 500 universe from Wikipedia. Responses are cached per calendar day under
%LOCALAPPDATA%\\pnf\\cache; stale days are pruned automatically.
"""
import json
import os
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "pnf" / "cache"
WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class DataError(RuntimeError):
    pass


# SPDR S&P 500 sector ETFs: ticker -> (sector name, palette color)
SECTOR_ETFS = {
    "XLB": ("Materials", "#9999FF"),
    "XLC": ("Communication Services", "#9900CC"),
    "XLE": ("Energy", "#FFCC00"),
    "XLF": ("Financials", "#A3E635"),
    "XLI": ("Industrials", "#0066FF"),
    "XLK": ("Technology", "#FF00FF"),
    "XLP": ("Consumer Staples", "#00CC99"),
    "XLRE": ("Real Estate", "#E11D48"),
    "XLU": ("Utilities", "#FF6600"),
    "XLV": ("Health Care", "#00E5FF"),
    "XLY": ("Consumer Discretionary", "#22C55E"),
}
SECTORS = list(SECTOR_ETFS)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _cached(name: str, fetch) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    today = str(date.today())
    path = CACHE / f"{name}_{today}"
    if path.exists():
        return path.read_bytes()
    for old in CACHE.glob(f"{name}_*"):
        old.unlink(missing_ok=True)
    raw = fetch()
    path.write_bytes(raw)
    return raw


def fetch_daily(ticker: str, range_: str = "5y"):
    """Return [(date, high, low, close), ...] oldest first.

    Uses Yahoo's `quote` arrays: split-adjusted but NOT dividend-adjusted,
    i.e. actual traded prices — the same series as StockCharts' unadjusted
    underscore symbols (_LRCX). Yahoo's `adjclose` (dividend-adjusted) is
    deliberately not used.
    """
    sym = ticker.upper().replace(".", "-")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range={range_}&interval=1d")
    raw = _cached(f"{sym}_{range_}.json", lambda: _get(url))
    j = json.loads(raw)
    result = (j.get("chart") or {}).get("result")
    if not result:
        err = (j.get("chart") or {}).get("error") or {}
        raise DataError(f"{ticker}: {err.get('description') or 'no data'}")
    res = result[0]
    ts = res.get("timestamp") or []
    quote = res["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        h, l, c = quote["high"][i], quote["low"][i], quote["close"][i]
        if h is None or l is None or c is None:
            continue
        bars.append((time.strftime("%Y-%m-%d", time.gmtime(t)), h, l, c))
    if not bars:
        raise DataError(f"{ticker}: empty history")
    return bars


def sp500() -> list[str]:
    """Current S&P 500 tickers, Yahoo-style symbols (BRK.B -> BRK-B)."""
    html = _cached("sp500.html", lambda: _get(WIKI_SP500)).decode("utf-8", "replace")
    # Only the constituents table (the historical-changes table comes after id="changes")
    cut = html.find('id="changes"')
    if cut > 0:
        html = html[:cut]
    raw = re.findall(
        r'(?:/quote/|market-activity/stocks/|markets/[^"]*symbol=)[^"]*"[^>]*>'
        r'([A-Z][A-Z.\-]{0,6})</a>', html)
    seen, out = set(), []
    for s in raw:
        if s not in seen:
            seen.add(s)
            out.append(s.replace(".", "-"))
    if len(out) < 400:
        raise DataError(f"S&P 500 list looks wrong ({len(out)} symbols) - "
                        "Wikipedia layout may have changed")
    return out
