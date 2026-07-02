"""pnf — Point & Figure signals, objectives, stops, reward/risk.

Usage:
  pnf LRCX                 analyze one ticker
  pnf LRCX --chart         ... with an ASCII chart
  pnf LRCX --json          machine-readable output
  pnf LRCX --explain       pipe the numbers through `claude -p` for a writeup
  pnf scan                 scan the S&P 500, rank by reward/risk
  pnf scan --top 10 --days 5
  pnf scan snowball        scan the snowball sector-membership universe
  pnf scan xle             scan one sector's components
  pnf bpi                  S&P 500 bullish percent + all 11 sectors
  pnf bpi xle --chart      one sector's BPI with its P&F chart
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, timedelta

from . import analysis, bpi as bpimod, chart as chartmod, data, render

GOLD = "#D4AF37"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].lower() == "scan":
        return _scan(argv[1:])
    if argv and argv[0].lower() == "bpi":
        return _bpi(argv[1:])
    return _ticker(argv)


def _build(ticker: str, range_: str, reversal: int, method: str = "sc"):
    bars = data.fetch_daily(ticker, range_)
    ch = chartmod.build(bars, reversal)
    return ch, analysis.analyze(ch, ticker.upper(), method)


def _ticker(argv):
    p = argparse.ArgumentParser(prog="pnf", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker")
    p.add_argument("--range", default="5y", help="history window (default 5y)")
    p.add_argument("--reversal", type=int, default=3)
    p.add_argument("--objective", choices=["sc", "classic"], default="sc",
                   help="price objective method: sc = StockCharts breakout "
                        "method (default), classic = Dorsey vertical count")
    p.add_argument("--chart", action="store_true", help="print ASCII P&F chart")
    p.add_argument("--json", action="store_true")
    p.add_argument("--explain", action="store_true",
                   help="send the computed numbers to `claude -p` for analysis")
    a = p.parse_args(argv)

    try:
        ch, an = _build(a.ticker, a.range, a.reversal, a.objective)
    except data.DataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(an.to_dict(), indent=2))
    else:
        _report(ch, an)
        if a.chart:
            print()
            print(render.render(ch))
    if a.explain:
        _explain(an)
    return 0


def _paint(text: str, status: str, enabled: bool) -> str:
    """Color text green/red by signal status (bullish/bearish)."""
    if not enabled:
        return text
    code = {"bullish": render.GREEN, "bearish": render.RED}.get(status)
    return f"{code}{text}{render.RESET}" if code else text


def _report(ch, an):
    head = f"{an.ticker}  {an.date}  close {an.close:.2f}"
    info = data.SECTOR_ETFS.get(an.ticker)
    if info:
        name, hexcode = info
        if render.color_enabled():
            head = (render.highlight(f" {an.ticker} ", hexcode)
                    + f" {an.date}  close {an.close:.2f}  "
                    + render.paint_hex(name, hexcode))
        else:
            head += f"  ({name})"
    print(head)
    if an.pattern:
        pat = _paint(an.pattern, an.status, render.color_enabled())
        print(f"P&F:        {pat} on {an.signal_date} "
              f"({an.status}, triggered at {an.trigger:.2f})")
    print(f"Status:     {an.status}")
    if an.trend:
        print(f"Trend:      {an.trend}")
    if an.reversal is not None:
        flip = "low that flips to a new O column" \
            if ch.columns[-1].kind == "X" else "high that flips to a new X column"
        print(f"Reversal:   {an.reversal:.2f}  ({flip})")
    if an.objective is not None:
        active = "  (count column still active - objective may extend)" \
            if an.objective_active else ""
        print(f"Objective:  {an.objective:.2f}{active}")
    if an.stop is not None:
        side = "below last O-column low" if an.status == "bullish" \
            else "above last X-column high"
        print(f"Stop:       {an.stop:.2f}  (one box {side})")
    if an.rr is not None:
        side = " (short side)" if an.status == "bearish" else ""
        print(f"Reward:     {an.reward:.2f}{side}")
        print(f"Risk:       {an.risk:.2f}{side}")
        print(f"R/R:        {an.rr:.2f}{side}")
    if an.note:
        print(f"Note:       {an.note}")


def _explain(an):
    exe = shutil.which("claude")
    if not exe:
        print("--explain needs the `claude` CLI on PATH", file=sys.stderr)
        return
    prompt = (
        "You are reviewing a Point & Figure setup. The numbers below were "
        "computed deterministically (traditional scale, 3-box reversal, "
        "vertical-count objective, stop = opposite-signal box). In a short "
        "paragraph, assess the setup: entry vs trigger box, whether the "
        "objective is still active, stop distance, and what would invalidate "
        "it. No preamble.\n\n" + json.dumps(an.to_dict(), indent=2)
    )
    subprocess.run([exe, "-p", prompt])


def _bpi(argv):
    p = argparse.ArgumentParser(prog="pnf bpi")
    p.add_argument("sector", nargs="?",
                   help="one sector ETF (e.g. XLE); default: overall S&P "
                        "500 plus all 11 sectors")
    p.add_argument("--range", default="5y")
    p.add_argument("--chart", action="store_true",
                   help="print the BPI's own P&F chart")
    p.add_argument("--limit", type=int, help="only scan the first N tickers")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    members = data.snowball()
    if a.sector:
        etf = a.sector.upper()
        if etf not in members:
            print(f"error: no components file for {etf} "
                  f"(have: {', '.join(members)})", file=sys.stderr)
            return 1
        members = {etf: members[etf]}

    tickers = sorted({t for ts in members.values() for t in ts})
    if a.limit:
        tickers = tickers[: a.limit]
    sigs, failed = {}, []
    for i, t in enumerate(tickers, 1):
        if i % 25 == 0:
            print(f"  ... {i}/{len(tickers)}", file=sys.stderr)
        try:
            sigs[t] = chartmod.build(data.fetch_daily(t, a.range)).signals
        except (data.DataError, OSError):
            failed.append(t)

    sectors = []
    for etf, ts in members.items():
        sub = {t: sigs[t] for t in ts if t in sigs}
        if sub:
            sectors.append((etf, bpimod.compute(data.SECTOR_ETFS[etf][0], sub)))
    sectors.sort(key=lambda x: x[1].pct, reverse=True)
    if a.sector:
        top = sectors[0][1]
    else:
        top = bpimod.compute("S&P 500", sigs)

    if a.json:
        out = {"date": top.chart.last_date, "name": top.name,
               "bpi": top.pct, "status": top.status,
               "bullish": top.bullish, "members": top.members}
        if not a.sector:
            out["sectors"] = [
                {"etf": etf, "name": b.name, "bpi": b.pct, "status": b.status,
                 "bullish": b.bullish, "members": b.members}
                for etf, b in sectors]
        print(json.dumps(out, indent=2))
    else:
        color = render.color_enabled()
        col = top.chart.columns[-1].kind
        print(f"{top.name} Bullish Percent  as of {top.chart.last_date}")
        print(f"BPI:     {top.pct:.1f}%  ({top.bullish}/{top.members} "
              "on buy signals)")
        print(f"Status:  {_paint_bpi(top.status, color)}  ({col} column)")
        if not a.sector:
            print()
            header = (f"{'Sector':<23} {'  ' if color else ''}{'BPI':>6} "
                      f"{'Col':^4} {'Status':<16} {'Bulls':>8}")
            print(header)
            for etf, b in sectors:
                name, hexcode = data.SECTOR_ETFS[etf]
                sec = f"{name:<23}"
                if color:
                    sec = render.paint_hex(sec, hexcode)
                    tri = "▲ " if b.status.startswith("Bull") else "▼ "
                else:
                    tri = ""
                print(f"{sec} {tri}{b.pct:>6.1f} "
                      f"{b.chart.columns[-1].kind:^4} "
                      f"{_paint_bpi(f'{b.status:<16}', color)} "
                      f"{f'{b.bullish}/{b.members}':>8}")
        if a.chart:
            print()
            print(render.render(top.chart))
    if failed:
        print(f"({len(failed)} tickers failed: {', '.join(failed[:10])}"
              f"{'...' if len(failed) > 10 else ''})", file=sys.stderr)
    return 0


def _paint_bpi(status: str, enabled: bool) -> str:
    if not enabled:
        return status
    code = render.GREEN if status.lstrip().startswith("Bull") else render.RED
    return f"{code}{status}{render.RESET}"


def _scan(argv):
    p = argparse.ArgumentParser(prog="pnf scan")
    p.add_argument("universe", nargs="?", default="sp500",
                   help="'sp500' (Wikipedia), 'sectors' (SPDR sector ETFs), "
                        "'snowball' (sector-membership CSVs), a sector ETF "
                        "(e.g. xle), or a path to a file of tickers")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--limit", type=int, help="only scan the first N tickers")
    p.add_argument("--days", type=int,
                   help="only signals fired within the last N calendar days")
    p.add_argument("--side", choices=["buy", "sell", "both"], default="buy")
    p.add_argument("--range", default="5y")
    p.add_argument("--reversal", type=int, default=3)
    p.add_argument("--objective", choices=["sc", "classic"], default="sc")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    u = a.universe.lower()
    if u == "sp500":
        tickers = data.sp500()
    elif u == "sectors":
        tickers = data.SECTORS
    elif u == "snowball":
        tickers = sorted({t for ts in data.snowball().values() for t in ts})
    elif u.upper() in data.SECTOR_ETFS:
        tickers = data.sector_components(u)
    else:
        with open(a.universe) as f:
            tickers = [t.strip().upper() for t in f if t.strip()]
    if a.limit:
        tickers = tickers[: a.limit]

    cutoff = str(date.today() - timedelta(days=a.days)) if a.days else None
    rows, failed = [], []
    for i, t in enumerate(tickers, 1):
        if i % 25 == 0:
            print(f"  ... {i}/{len(tickers)}", file=sys.stderr)
        try:
            _, an = _build(t, a.range, a.reversal, a.objective)
        except (data.DataError, OSError):
            failed.append(t)
            continue
        want = {"buy": "bullish", "sell": "bearish"}.get(a.side)
        if want and an.status != want:
            continue
        if a.side == "both" and an.status not in ("bullish", "bearish"):
            continue
        if an.rr is None:
            continue
        if cutoff and an.signal_date < cutoff:
            continue
        rows.append(an)

    rows.sort(key=lambda r: r.rr, reverse=True)
    rows = rows[: a.top]

    if a.json:
        print(json.dumps([r.to_dict() for r in rows], indent=2))
    else:
        color = render.color_enabled()
        with_sector = any(r.ticker in data.SECTOR_ETFS for r in rows)
        # pad every cell before painting: ANSI codes would count toward
        # a format width and break column alignment
        header = " ".join(
            [f"{'Ticker':<6}"]
            + ([f"{'Sector':<23}"] if with_sector else [])
            + (["  "] if color else [])
            + [f"{'Close':>9}", f"{'Pattern':<34}", f"{'Signal':<11}",
               f"{'Objectv':>9}", f"{'Stop':>9}", f"{'R/R':>6}"])
        lines = [header]
        for r in rows:
            name, hexcode = data.SECTOR_ETFS.get(r.ticker, ("", None))
            tick = f"{r.ticker:<6}"
            if color and hexcode:
                tick = render.highlight(tick, hexcode)
            cells = [tick]
            if with_sector:
                sec = f"{name:<23}"
                cells.append(render.paint_hex(sec, hexcode)
                             if color and hexcode else sec)
            if color:
                tri = "▲" if r.status == "bullish" else "▼"
                cells.append(_paint(f"{tri} ", r.status, color))
            cells += [f"{r.close:>9.2f}",
                      _paint(f"{r.pattern:<34}", r.status, color),
                      f"{r.signal_date:<11}",
                      f"{r.objective:>9.2f}", f"{r.stop:>9.2f}",
                      f"{r.rr:>6.2f}"]
            lines.append(" ".join(cells))
        if color:
            # gold frame; plain (piped/NO_COLOR) output stays bare so it
            # remains grep/parse-friendly and codepage-safe
            gold = lambda s: render.paint_hex(s, GOLD)
            inner = len(header) + 2
            print(gold("┌" + "─" * inner + "┐"))
            for ln in lines:
                print(gold("│ ") + ln + gold(" │"))
            print(gold("└" + "─" * inner + "┘"))
        else:
            for ln in lines:
                print(ln)
    if failed:
        print(f"({len(failed)} tickers failed: {', '.join(failed[:10])}"
              f"{'...' if len(failed) > 10 else ''})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
