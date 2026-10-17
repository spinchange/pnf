"""Daily OHLC via the Yahoo Finance v8 chart API (stdlib only), plus S&P 500
universes: Wikipedia (flat list) and SPDR sector membership (which adds the
sector structure required for sector bullish percent). Sector membership
comes from the tape project's daily `spx_members` snapshots of the SPDR
holdings (point-in-time, needs duckdb), falling back to the snowball
project's hand-kept CSVs (xle-components.csv etc.). Responses are cached per
calendar day under %LOCALAPPDATA%\\pnf\\cache; stale days are pruned
automatically.
"""
import csv
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "pnf" / "cache"
WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SNOWBALL = Path(os.environ.get("PNF_SNOWBALL",
                               str(Path.home() / "Documents" / "snowball")))
TAPE_DB = Path(os.environ.get("PNF_TAPE_DB",
                              str(SNOWBALL.parent / "tape" / "db" / "tape.duckdb")))
TAPE_STALE_DAYS = 7


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


def _yahoo(sym: str) -> str:
    return sym.strip().upper().replace(".", "-").replace("/", "-")


def sector_components(etf: str) -> list[str]:
    """Symbols from <snowball>/<etf>-components.csv (symbol,name header),
    normalized to Yahoo form (BRK.B -> BRK-B)."""
    path = SNOWBALL / f"{etf.lower()}-components.csv"
    if not path.exists():
        raise DataError(f"{path} not found - set PNF_SNOWBALL to the "
                        "snowball project directory")
    with path.open(newline="") as f:
        out = [_yahoo(r["symbol"])
               for r in csv.DictReader(f) if r.get("symbol", "").strip()]
    if not out:
        raise DataError(f"{path}: no symbols")
    return out


def snowball() -> dict[str, list[str]]:
    """sector ETF -> component symbols, for every sector CSV present."""
    out = {etf: sector_components(etf) for etf in SECTORS
           if (SNOWBALL / f"{etf.lower()}-components.csv").exists()}
    if not out:
        raise DataError(f"no *-components.csv files under {SNOWBALL} - "
                        "set PNF_SNOWBALL to the snowball project directory")
    return out


def tape_history(path: Path | None = None) -> list[tuple[str, dict[str, str]]]:
    """[(as_of, {ticker: sector ETF}), ...] oldest first, one entry per
    holdings date in tape's `spx_members`, read-only. Symbols in Yahoo form;
    warrants and units ("SKYD/WS") are skipped — they are not common stock."""
    path = path or TAPE_DB
    if not path.exists():
        raise DataError(f"{path} not found - set PNF_TAPE_DB to tape's "
                        "db/tape.duckdb")
    try:
        import duckdb
    except ImportError:
        raise DataError("duckdb is required to read tape membership "
                        "(pip install duckdb)") from None
    try:
        con = duckdb.connect(str(path), read_only=True)
        try:
            rows = con.execute("SELECT as_of, sector_etf, ticker FROM spx_members "
                               "ORDER BY as_of").fetchall()
        finally:
            con.close()
    except duckdb.Error as e:
        raise DataError(f"{path}: {' '.join(str(e).split())[:200]}") from None
    hist: dict[str, dict[str, str]] = {}
    for d, etf, t in rows:
        if not t or "/" in t or etf not in SECTOR_ETFS:
            continue
        hist.setdefault(str(d), {})[_yahoo(t)] = etf
    if not hist:
        raise DataError(f"{path}: spx_members is empty")
    return sorted(hist.items())


@dataclass
class Membership:
    sectors: dict[str, list[str]]   # current: sector ETF -> tickers
    source: str                     # human-readable provenance
    as_of: str | None = None        # tape's latest holdings date
    # Point-in-time membership (tape only): [(as_of, {ticker: etf})] oldest first
    history: list[tuple[str, dict[str, str]]] | None = None

    def stale(self, asof: str | None = None) -> bool:
        """Latest snapshot more than TAPE_STALE_DAYS before `asof` (today)."""
        ref = date.fromisoformat(asof) if asof else date.today()
        return (self.as_of is not None and
                (ref - date.fromisoformat(self.as_of)).days > TAPE_STALE_DAYS)


def membership(asof: str | None = None) -> Membership:
    """S&P 500 sector membership: tape's latest SPDR holdings snapshot (the
    latest on or before `asof`; the first one if `asof` predates tape), or
    the snowball CSVs when tape can't be read (the reason is in .source)."""
    try:
        hist = tape_history()
        if asof:
            hist = [h for h in hist if h[0] <= asof] or hist[:1]
    except DataError as tape_err:
        try:
            sectors = snowball()
        except DataError as csv_err:
            raise DataError(f"no sector membership: {tape_err}; {csv_err}") from None
        return Membership(sectors, f"snowball CSVs (tape unavailable: {tape_err})")
    as_of, latest = hist[-1]
    sectors: dict[str, list[str]] = {}
    for t, etf in sorted(latest.items()):
        sectors.setdefault(etf, []).append(t)
    sectors = {etf: sectors[etf] for etf in SECTORS if etf in sectors}
    if asof and asof < as_of:
        note = f"earliest snapshot, after {asof}: survivorship bias"
    else:
        note = f"point-in-time since {hist[0][0]}"
    return Membership(sectors, f"tape {as_of} ({note})", as_of, hist)


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


