"""pnf showcase — quality businesses whose P&F charts look the part.

Two independent axes, kept separate on purpose:

* **Business quality** comes from the snowball vault's judgment layer, read at
  run time (never embedded here): the hand-argued *showpieces* table in
  `dossiers/_comparisons.md` (the See's Candies class) and the mechanical
  *Snowball 30* composite ranking (`reports/snowball30_composite.sql` against
  `facts/facts.duckdb`, five Buffett-lens pillars). `PNF_SNOWBALL` points at
  the vault. Either source can be used alone (`--universe showpieces` /
  `snowball30`), or a plain ticker file.

* **Chart shape** is scored from the P&F chart itself (0–100), from things a
  chartist actually looks for in a "great-looking" long-term chart:
  bullish status, price above the bullish support line and for how long,
  a staircase of rising O-column lows, a history dominated by buy signals
  with few whipsaws, price near its high without being parabolic, and
  Dorsey-Wright relative strength versus the sector and the sector versus
  the market. Every component is arithmetic on the chart; nothing is fitted.

The table ranks by chart score inside the quality universe (or by
`--sort combined`, the mean of the quality percentile and the chart score).
It is a *watch list generator*, not a signal: a beautiful chart on a great
business says the market already agrees — the interesting rows are often
the quality names whose charts are merely repairing.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import analysis, chart as chartmod, data, render, rs
from .trend import lines as trend_lines

QUALITY_SOURCES = ("showpieces", "snowball30")


# ----------------------------------------------------------------- universe
def showpieces(snowball: Path = data.SNOWBALL) -> list[tuple[str, int, str]]:
    """[(ticker, rank, cohort standing)] from the showpieces table in
    dossiers/_comparisons.md — every bold ticker in the row's ticker cell
    (so 'MCO (with SPGI)' yields both, same rank)."""
    path = snowball / "dossiers" / "_comparisons.md"
    if not path.exists():
        raise data.DataError(f"{path} not found - set PNF_SNOWBALL")
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## The showpieces.*?(?=^## )", text, re.M | re.S)
    if not m:
        raise data.DataError("no '## The showpieces' section in _comparisons.md")
    out = []
    for row in re.finditer(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|", m.group(0), re.M):
        rank, cell, standing = int(row.group(1)), row.group(2), row.group(3).strip()
        for t in re.findall(r"\*\*([A-Z][A-Z.\-]{0,6})\*\*", cell):
            out.append((t.replace(".", "-"), rank, standing))
    if not out:
        raise data.DataError("showpieces table parsed to zero tickers")
    return out


def snowball30(snowball: Path = data.SNOWBALL, top: int | None = None) -> list[dict]:
    """Rows of reports/snowball30_composite.sql run read-only against the
    vault's facts.duckdb: ticker, rank, score, company (+ the pillars)."""
    try:
        import duckdb
    except ImportError as e:  # pragma: no cover
        raise data.DataError("duckdb is required for --universe snowball30 "
                             "(pip install duckdb)") from e
    sql_path = snowball / "reports" / "snowball30_composite.sql"
    db = snowball / "facts" / "facts.duckdb"
    for p in (sql_path, db):
        if not p.exists():
            raise data.DataError(f"{p} not found - set PNF_SNOWBALL")
    con = duckdb.connect(str(db), read_only=True)
    cur = con.execute(sql_path.read_text(encoding="utf-8"))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    rows = [r for r in rows if r.get("ticker")]
    rows.sort(key=lambda r: (r.get("rank") is None, r.get("rank") or 0))
    return rows[:top] if top else rows


# ------------------------------------------------------------------ scoring
@dataclass
class Shape:
    """Chart-shape facts and the 0-100 score built from them."""
    ticker: str
    date: str
    close: float
    status: str
    pattern: str | None
    signal_date: str | None
    rr: float | None
    objective: float | None
    stop: float | None
    trend: str | None
    above_support: bool
    support_since: str | None      # date the active support line's anchor column began
    support_years: float | None
    higher_lows: int               # consecutive rising O-column lows (staircase length)
    higher_highs: int              # consecutive rising X-column highs
    buy_share: float | None        # buys / all signals in the loaded history
    flips_2y: int                  # buy<->sell direction changes in the last ~2 years (whipsaws)
    drawdown_pct: float            # % below the highest box printed
    gain_pct: float | None         # % from the first column's price to the close
    rs_sector: str                 # bullish / bearish / neutral / n/a
    rs_market: str
    sector: str | None
    score: int = 0
    components: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["components"] = json.dumps(self.components)
        return d


def _staircase(columns, kind: str, key) -> int:
    """Length of the run of consecutive completed columns of `kind` whose
    extreme (key) rises each time, ending at the most recent completed one."""
    cols = [c for c in columns[:-1] if c.kind == kind]  # last column still building
    n = 0
    for prev, cur in zip(cols[:-1], cols[1:]):
        if key(cur) > key(prev):
            n += 1
        else:
            n = 0
    return n + 1 if cols and n else (1 if len(cols) == 1 else 0)


def _years_between(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days / 365.25


def shape(ch: chartmod.Chart, an: analysis.Analysis, rs_sector: str = "n/a",
          rs_market: str = "n/a", sector: str | None = None) -> Shape:
    cols = ch.columns
    lad = ch.ladder
    active = trend_lines(cols)[-1]
    above = active.kind == "support" and cols[-1].lo > active.at(len(cols) - 1)
    support_since = cols[active.col].start if active.kind == "support" else None
    support_years = (_years_between(support_since, ch.last_date)
                     if support_since else None)
    hl = _staircase(cols, "O", lambda c: c.lo)
    hh = _staircase(cols, "X", lambda c: c.hi)
    n_sig = len(ch.signals)
    buy_share = (sum(1 for s in ch.signals if s.kind == "buy") / n_sig) if n_sig else None
    two_years_ago = str(date.fromisoformat(ch.last_date).replace(
        year=date.fromisoformat(ch.last_date).year - 2))
    # in a strong trend nearly every new column re-fires a same-side breakout, so the
    # raw signal count says nothing; whipsaws are direction changes
    recent = [s for s in ch.signals if s.date >= two_years_ago]
    flips_2y = sum(1 for a_, b_ in zip(recent[:-1], recent[1:]) if a_.kind != b_.kind)
    top_idx = max(c.hi for c in cols)
    drawdown = (lad[top_idx] - ch.last_close) / lad[top_idx] * 100 if lad[top_idx] else 0.0
    first = lad[cols[0].lo if cols[0].kind == "X" else cols[0].hi]
    gain = (ch.last_close / first - 1) * 100 if first else None

    comp: dict[str, float] = {}
    comp["bullish"] = 20.0 if an.status == "bullish" else 0.0
    comp["above_support"] = 15.0 if above else 0.0
    # a long-standing support line is the signature of a great long-term chart
    comp["support_age"] = round(min(support_years or 0.0, 3.0) / 3.0 * 10.0, 1)
    comp["staircase"] = round(min(hl, 4) / 4.0 * 15.0, 1)
    comp["buy_share"] = round(((buy_share or 0.0) - 0.5) / 0.5 * 10.0, 1) if (buy_share or 0) > 0.5 else 0.0
    comp["few_whipsaws"] = round(max(0.0, 1.0 - max(flips_2y - 1, 0) / 4.0) * 10.0, 1)
    comp["near_high"] = round(max(0.0, 1.0 - drawdown / 20.0) * 10.0, 1)
    comp["rs_sector"] = {"bullish": 7.0, "neutral": 2.0}.get(rs_sector, 0.0)
    comp["rs_market"] = {"bullish": 3.0, "neutral": 1.0}.get(rs_market, 0.0)
    score = int(round(sum(comp.values())))

    return Shape(
        ticker=an.ticker, date=ch.last_date, close=round(ch.last_close, 2),
        status=an.status, pattern=an.pattern, signal_date=an.signal_date,
        rr=an.rr, objective=an.objective, stop=an.stop, trend=an.trend,
        above_support=above, support_since=support_since,
        support_years=round(support_years, 1) if support_years is not None else None,
        higher_lows=hl, higher_highs=hh,
        buy_share=round(buy_share, 2) if buy_share is not None else None,
        flips_2y=flips_2y, drawdown_pct=round(drawdown, 1),
        gain_pct=round(gain, 0) if gain is not None else None,
        rs_sector=rs_sector, rs_market=rs_market, sector=sector,
        score=score, components=comp,
    )


# --------------------------------------------------------------------- run
def _rs_status(num_bars, den_bars, reversal: int) -> str:
    try:
        ch = rs.build(num_bars, den_bars, reversal)
    except data.DataError:
        return "n/a"
    return rs.verdict(ch)[0]


def evaluate(ticker: str, range_: str = "10y", reversal: int = 3,
             sector_of: dict[str, str] | None = None,
             cache: dict[str, list] | None = None) -> Shape:
    """Build the chart, the analysis and both RS charts for one ticker."""
    cache = cache if cache is not None else {}

    def bars(t: str):
        if t not in cache:
            cache[t] = data.fetch_daily(t, range_)
        return cache[t]

    b = bars(ticker)
    ch = chartmod.build(b, reversal)
    an = analysis.analyze(ch, ticker)
    etf = (sector_of or {}).get(ticker)
    rs_sec = rs_mkt = "n/a"
    if etf:
        rs_sec = _rs_status(b, bars(etf), reversal)
        rs_mkt = _rs_status(bars(etf), bars(rs.MARKET), reversal)
    else:
        rs_sec = _rs_status(b, bars(rs.MARKET), reversal)
    return shape(ch, an, rs_sec, rs_mkt, etf), ch


def main(argv) -> int:
    p = argparse.ArgumentParser(
        prog="pnf showcase",
        description="quality businesses (snowball's judgment) ranked by how "
                    "good their P&F chart looks")
    p.add_argument("universe", nargs="?", default="quality",
                   help="'quality' (showpieces + Snowball 30 composite, the "
                        "default), 'showpieces', 'snowball30', or a ticker file")
    p.add_argument("--top", type=int, help="show only the best N")
    p.add_argument("--range", default="10y",
                   help="price history to chart (default 10y - shape needs years)")
    p.add_argument("--reversal", type=int, default=3)
    p.add_argument("--sort", choices=["chart", "combined", "quality"], default="chart")
    p.add_argument("--min-score", type=int, default=0,
                   help="hide charts scoring below this")
    p.add_argument("--chart", action="store_true",
                   help="print the ASCII P&F chart under each row shown")
    p.add_argument("--csv", nargs="?", const=True, metavar="FILE")
    p.add_argument("--json", action="store_true")
    p.add_argument("--txt", nargs="?", const=True, metavar="FILE",
                   help="save the table (and charts if --chart) to a text file")
    a = p.parse_args(argv)

    # ---- universe with quality annotations
    quality: dict[str, dict] = {}
    u = a.universe.lower()
    try:
        if u in ("quality", "showpieces"):
            for t, rank, standing in showpieces():
                quality.setdefault(t, {})
                quality[t].update(showpiece_rank=rank, standing=standing)
        if u in ("quality", "snowball30"):
            rows = snowball30()
            n = len(rows)
            for r in rows:
                q = quality.setdefault(r["ticker"], {})
                q.update(s30_rank=r.get("rank"), s30_score=r.get("score"),
                         company=r.get("company"),
                         s30_pct=round(1 - (r.get("rank") - 1) / max(n - 1, 1), 2)
                         if r.get("rank") else None)
        if u not in ("quality", "showpieces", "snowball30"):
            with open(a.universe) as f:
                for t in (x.strip().upper() for x in f):
                    if t:
                        quality.setdefault(t, {})
    except (data.DataError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    tickers = sorted(quality)

    try:
        sector_of = rs.sector_of()
    except data.DataError:
        sector_of = {}

    cache: dict[str, list] = {}
    results: list[tuple[Shape, chartmod.Chart]] = []
    failed = []
    for i, t in enumerate(tickers, 1):
        if i % 10 == 0:
            print(f"  ... {i}/{len(tickers)}", file=sys.stderr)
        try:
            sh, ch = evaluate(t, a.range, a.reversal, sector_of, cache)
        except (data.DataError, OSError) as e:
            failed.append(f"{t} ({e})")
            continue
        results.append((sh, ch))

    def quality_pct(t: str) -> float | None:
        q = quality.get(t, {})
        if q.get("showpiece_rank"):
            return 1.0  # hand-argued class: top of the quality axis
        return q.get("s30_pct")

    def combined(sh: Shape) -> float:
        qp = quality_pct(sh.ticker)
        return (qp + sh.score / 100) / 2 if qp is not None else sh.score / 200

    keyf = {"chart": lambda r: -r[0].score,
            "combined": lambda r: -combined(r[0]),
            "quality": lambda r: (-(quality_pct(r[0].ticker) or 0), -r[0].score)}[a.sort]
    results.sort(key=keyf)
    results = [r for r in results if r[0].score >= a.min_score]
    if a.top:
        results = results[: a.top]

    def row_dict(sh: Shape) -> dict:
        d = sh.to_dict()
        q = quality.get(sh.ticker, {})
        d.update(showpiece_rank=q.get("showpiece_rank"), standing=q.get("standing"),
                 s30_rank=q.get("s30_rank"), s30_score=q.get("s30_score"),
                 company=q.get("company"), combined=round(combined(sh), 3))
        return d

    if a.json:
        print(json.dumps([row_dict(sh) for sh, _ in results], indent=2))
    else:
        text = _table(results, quality, combined, a.chart)
        print(text)
        if a.txt:
            path = a.txt if isinstance(a.txt, str) else f"pnf-showcase-{date.today()}.txt"
            Path(path).write_text(text + "\n", encoding="utf-8")
            print(f"wrote {path}", file=sys.stderr)
    if a.csv:
        path = a.csv if isinstance(a.csv, str) else f"pnf-showcase-{date.today()}.csv"
        rows = [row_dict(sh) for sh, _ in results]
        if rows:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        print(f"wrote {path}", file=sys.stderr)
    if failed:
        print(f"({len(failed)} failed: {'; '.join(failed[:6])}"
              f"{' ...' if len(failed) > 6 else ''})", file=sys.stderr)
    return 0


def _table(results, quality, combined, with_charts: bool) -> str:
    hdr = (f"{'Ticker':<6} {'Qual':<9} {'Score':>5} {'Comb':>5} {'Close':>9} "
           f"{'Status':<8} {'Supp':>5} {'HL':>3} {'Buy%':>5} {'Flips':>5} {'DD%':>5} "
           f"{'RS-sec':<8} {'RS-mkt':<8} {'Pattern':<30} {'Signal':<10} {'R/R':>5}")
    out = [hdr, "-" * len(hdr)]
    for sh, ch in results:
        q = quality.get(sh.ticker, {})
        qual = (f"SP#{q['showpiece_rank']}" if q.get("showpiece_rank") else "") + \
               (f"/S30#{q['s30_rank']}" if q.get("s30_rank") else "")
        qual = qual.lstrip("/") or "-"
        out.append(
            f"{sh.ticker:<6} {qual:<9} {sh.score:>5} {combined(sh)*100:>5.0f} {sh.close:>9.2f} "
            f"{sh.status:<8} {(f'{sh.support_years:.1f}y' if sh.above_support and sh.support_years is not None else '-'):>5} "
            f"{sh.higher_lows:>3} {(f'{sh.buy_share*100:.0f}' if sh.buy_share is not None else '-'):>5} "
            f"{sh.flips_2y:>5} {sh.drawdown_pct:>5.1f} {sh.rs_sector:<8} {sh.rs_market:<8} "
            f"{(sh.pattern or '-')[:30]:<30} {(sh.signal_date or '-'):<10} "
            f"{(f'{sh.rr:.2f}' if sh.rr is not None else '-'):>5}")
        if with_charts:
            out.append("")
            out.append(render.render(ch, color=False))
            out.append("")
    out.append("")
    out.append("Qual: SP#n = showpieces rank (dossiers/_comparisons.md), S30#n = Snowball 30 "
               "composite rank. Score = chart shape 0-100 (bullish 20, above support 15, "
               "support age 10, rising-lows staircase 15, buy share 10, few whipsaws 10, "
               "near high 10, RS vs sector 7, sector vs market 3). Comb = mean of quality "
               "percentile and chart score. Supp = years the active bullish support line has "
               "held; HL = consecutive rising O-column lows; Flips = buy/sell direction changes "
               "in the last two years; DD% = below the highest box printed. Not advice, not a signal.")
    return "\n".join(out)
