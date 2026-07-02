"""pnf — Point & Figure signals, objectives, stops, reward/risk.

Usage:
  pnf LRCX                 analyze one ticker
  pnf LRCX --chart         ... with an ASCII chart
  pnf LRCX --json          machine-readable output
  pnf LRCX --explain       pipe the numbers through `claude -p` for a writeup
  pnf scan                 scan the S&P 500, rank by reward/risk
  pnf scan --top 10 --days 5
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, timedelta

from . import analysis, chart as chartmod, data, render

GOLD = "#D4AF37"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].lower() == "scan":
        return _scan(argv[1:])
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


def _scan(argv):
    p = argparse.ArgumentParser(prog="pnf scan")
    p.add_argument("universe", nargs="?", default="sp500",
                   help="'sp500', 'sectors' (SPDR sector ETFs), or a path to "
                        "a file of tickers, one per line")
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

    if a.universe.lower() == "sp500":
        tickers = data.sp500()
    elif a.universe.lower() == "sectors":
        tickers = data.SECTORS
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
