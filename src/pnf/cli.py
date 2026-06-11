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


def _report(ch, an):
    print(f"{an.ticker}  {an.date}  close {an.close:.2f}")
    if an.pattern:
        print(f"P&F:        {an.pattern} on {an.signal_date} "
              f"({an.status}, triggered at {an.trigger:.2f})")
    print(f"Status:     {an.status}")
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
                   help="'sp500' or a path to a file of tickers, one per line")
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
        fmt = "{:<7} {:>9} {:<24} {:<11} {:>9} {:>9} {:>6}"
        print(fmt.format("Ticker", "Close", "Pattern", "Signal", "Objectv",
                         "Stop", "R/R"))
        for r in rows:
            print(fmt.format(r.ticker, f"{r.close:.2f}", r.pattern,
                             r.signal_date, f"{r.objective:.2f}",
                             f"{r.stop:.2f}", f"{r.rr:.2f}"))
    if failed:
        print(f"({len(failed)} tickers failed: {', '.join(failed[:10])}"
              f"{'...' if len(failed) > 10 else ''})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
