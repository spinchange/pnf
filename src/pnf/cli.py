"""pnf — Point & Figure signals, objectives, stops, reward/risk.

Usage:
  pnf LRCX                 analyze one ticker
  pnf LRCX --chart         ... with an ASCII chart
  pnf LRCX --txt           ... and save report + chart to a plain-text file
  pnf LRCX --json          machine-readable output
  pnf LRCX --explain       pipe the numbers through `claude -p` for a writeup
  pnf scan                 scan the S&P 500: every ticker, ranked by R/R
  pnf scan --top 10 --days 5 --side buy
  pnf scan --csv           ... and save the table to a CSV file
  pnf scan snowball        scan the snowball sector-membership universe
  pnf scan xle             scan one sector's components
  pnf bpi                  S&P 500 bullish percent + all 11 sectors
  pnf bpi xle --chart      one sector's BPI with its P&F chart
  pnf bpi --txt --csv      save BPI report/chart (.txt) and sector table (.csv)
  pnf rs NVDA              relative strength: NVDA vs its sector, sector vs SPY
  pnf rs NVDA --vs QQQ     ... vs an explicit benchmark
  pnf rs xlv --chart       one sector's RS vs SPY, with the ratio chart
"""
import argparse
import contextlib
import csv
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from . import analysis, bpi as bpimod, chart as chartmod, data, render, rs

GOLD = "#D4AF37"


def _capture(fn) -> str:
    """fn()'s stdout as a string. The buffer is not a TTY, so every
    color_enabled() check inside comes back False — plain text, file-safe."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


def _write_file(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {path}", file=sys.stderr)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].lower() == "scan":
        return _scan(argv[1:])
    if argv and argv[0].lower() == "bpi":
        return _bpi(argv[1:])
    if argv and argv[0].lower() == "rs":
        return _rs(argv[1:])
    if argv and argv[0].lower() == "showcase":
        from . import showcase
        return showcase.main(argv[1:])
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
    p.add_argument("--txt", nargs="?", const=True, metavar="FILE",
                   help="write the report and chart to a plain-text file "
                        "(default name TICKER-pnf-DATE.txt)")
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
    if a.txt:
        path = a.txt if isinstance(a.txt, str) \
            else f"{an.ticker}-pnf-{an.date}.txt"

        def _plain():
            _report(ch, an)
            print()
            print(render.render(ch, color=False))
        _write_file(path, _capture(_plain))
    if a.explain:
        _explain(
            "You are reviewing a Point & Figure setup. The numbers below were "
            "computed deterministically (traditional scale, 3-box reversal, "
            "vertical-count objective, stop = opposite-signal box). In a short "
            "paragraph, assess the setup: entry vs trigger box, whether the "
            "objective is still active, stop distance, and what would "
            "invalidate it. No preamble.", an.to_dict())
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
    if an.alert:
        side = "bearish" if an.alert.startswith("High Pole") else "bullish"
        warn = _paint(an.alert, side, render.color_enabled())
        print(f"Alert:      {warn} on {an.alert_date}")
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


def _explain(intro: str, payload) -> None:
    exe = shutil.which("claude")
    if not exe:
        print("--explain needs the `claude` CLI on PATH", file=sys.stderr)
        return
    prompt = intro + "\n\n" + json.dumps(payload, indent=2)
    # Strip API-key auth so `claude` uses the claude.ai login (subscription
    # billing, no connectors warning).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    subprocess.run([exe, "-p", prompt], env=env)


def _rs(argv):
    p = argparse.ArgumentParser(prog="pnf rs")
    p.add_argument("ticker", help="stock or sector ETF")
    p.add_argument("--vs", help="benchmark ticker; default: the stock's "
                                "sector ETF plus that ETF vs SPY, or SPY "
                                "for a sector ETF")
    p.add_argument("--range", default="5y")
    p.add_argument("--box", type=float, default=rs.BOX_PCT * 100,
                   help="box size in percent (default 2)")
    p.add_argument("--reversal", type=int, default=3)
    p.add_argument("--chart", action="store_true",
                   help="print the ratio's P&F chart")
    p.add_argument("--json", action="store_true")
    p.add_argument("--explain", action="store_true",
                   help="send the RS readings to `claude -p` for analysis")
    a = p.parse_args(argv)

    t = a.ticker.upper()
    note = None
    if a.vs:
        pairs = [(t, a.vs.upper())]
    elif t in data.SECTOR_ETFS:
        pairs = [(t, rs.MARKET)]
    else:
        try:
            etf = rs.sector_of().get(t)
        except data.DataError:
            etf = None
        if etf:
            pairs = [(t, etf), (etf, rs.MARKET)]
        else:
            note = f"{t} not in any SPDR sector - comparing to {rs.MARKET}"
            pairs = [(t, rs.MARKET)]

    results = []
    for num, den in pairs:
        try:
            ch = rs.build(data.fetch_daily(num, a.range),
                          data.fetch_daily(den, a.range),
                          a.reversal, a.box / 100)
        except data.DataError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        results.append((num, den, ch))

    if a.json:
        print(json.dumps([_rs_dict(n, d, ch) for n, d, ch in results],
                         indent=2))
    else:
        for i, (num, den, ch) in enumerate(results):
            if i:
                print()
            _rs_report(num, den, ch)
            if a.chart:
                print()
                print(render.render(ch))
    if note:
        print(f"({note})", file=sys.stderr)
    if a.explain:
        _explain(
            "You are reading Point & Figure relative-strength charts "
            "(Dorsey Wright convention: close ratio x 100, log-scale boxes, "
            "3-box reversal; the last signal is the long-term RS view, the "
            "current column the short-term one, and RS signals typically "
            "persist for years). In a short paragraph, read the leadership "
            "picture across the pairs below: who is leading whom, whether "
            "the reading is fresh or extended, and what ratio level would "
            "change it. No preamble.",
            [_rs_dict(n, d, ch) for n, d, ch in results])
    return 0


def _rs_dict(num, den, ch):
    sig = ch.last_signal
    status, reading = rs.verdict(ch)
    col = ch.columns[-1]
    ridx = ch.reversal_idx
    return {
        "pair": f"{num}/{den}",
        "date": ch.last_date,
        "ratio": round(ch.last_close, 2),
        "status": status,
        "signal": sig.kind if sig else None,
        "pattern": sig.pattern if sig else None,
        "signal_date": sig.date if sig else None,
        "column": col.kind,
        "column_since": col.start,
        "reading": reading,
        "reversal": ch.ladder[ridx] if ridx is not None else None,
    }


def _rs_report(num, den, ch):
    d = _rs_dict(num, den, ch)
    color = render.color_enabled()
    print(f"{num} / {den}   RS {d['ratio']:.2f}  as of {d['date']}")
    if d["pattern"]:
        pat = _paint(f"RS {d['signal']} - {d['pattern']}", d["status"], color)
        print(f"Signal:     {pat} on {d['signal_date']}")
    else:
        print("Signal:     none yet")
    side = "outperforming" if d["column"] == "X" else "underperforming"
    print(f"Column:     {d['column']} since {d['column_since']}  "
          f"({side} {den} near term)")
    print(f"Verdict:    {_paint(d['reading'], d['status'], color)}")
    if d["reversal"] is not None:
        print(f"Reversal:   {d['reversal']:.2f} flips the column")


def _bpi(argv):
    p = argparse.ArgumentParser(prog="pnf bpi")
    p.add_argument("sector", nargs="?",
                   help="one sector ETF (e.g. XLE); default: overall S&P "
                        "500 plus all 11 sectors")
    p.add_argument("--range", default="5y")
    p.add_argument("--chart", action="store_true",
                   help="print the BPI's own P&F chart")
    p.add_argument("--limit", type=int, help="only scan the first N tickers")
    p.add_argument("--txt", nargs="?", const=True, metavar="FILE",
                   help="write the BPI report and its P&F chart to a "
                        "plain-text file (default name pnf-bpi-DATE.txt)")
    p.add_argument("--csv", nargs="?", const=True, metavar="FILE",
                   help="write the sector table to a CSV file "
                        "(default name pnf-bpi-DATE.csv)")
    p.add_argument("--asof", metavar="DATE",
                   help="as of the close on DATE (YYYY-MM-DD), or 'friday' "
                        "for the most recent Friday; a holiday falls back to "
                        "the last trading day before it")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    asof = None
    if a.asof:
        try:
            asof = _asof_date(a.asof)
        except ValueError:
            print(f"error: --asof {a.asof!r}: expected YYYY-MM-DD or 'friday'",
                  file=sys.stderr)
            return 1
    try:
        mem = data.membership(asof)
    except data.DataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if mem.stale(asof):
        print(f"warning: tape membership is from {mem.as_of}, over "
              f"{data.TAPE_STALE_DAYS} days before {asof or 'today'}",
              file=sys.stderr)
    members = mem.sectors
    if a.sector:
        etf = a.sector.upper()
        if etf not in members:
            print(f"error: no members for {etf} "
                  f"(have: {', '.join(members)})", file=sys.stderr)
            return 1
        members = {etf: members[etf]}

    def history(etfs):
        """Point-in-time membership restricted to these sectors, or None."""
        if not mem.history:
            return None
        return [(d, {t for t, e in m.items() if e in etfs}) for d, m in mem.history]

    scope = history(members)
    current = {t for ts in members.values() for t in ts}
    # Former members are fetched too: they count on the days they belonged
    tickers = sorted(current | (set().union(*(m for _, m in scope)) if scope else set()))
    if a.limit:
        tickers = tickers[: a.limit]
    sigs, failed, former_failed = {}, [], []
    day = ""  # the session the report is as of: latest bar across the universe
    for i, t in enumerate(tickers, 1):
        if i % 25 == 0:
            print(f"  ... {i}/{len(tickers)}", file=sys.stderr)
        try:
            bars = data.fetch_daily(t, a.range)
            if asof:
                bars = [b for b in bars if b[0] <= asof]
            if not bars:
                raise data.DataError(f"{t}: no bars on or before {asof}")
            sigs[t] = chartmod.build(bars).signals
            day = max(day, bars[-1][0])
        except (data.DataError, OSError, ValueError):
            (failed if t in current else former_failed).append(t)
    if not sigs:
        print("error: no price data for any member", file=sys.stderr)
        return 1
    week_ago = str(date.fromisoformat(day) - timedelta(days=7))

    sectors = []
    for etf in members:
        sh = history({etf})
        ever = set().union(*(m for _, m in sh)) if sh else set(members[etf])
        sub = {t: sigs[t] for t in ever if t in sigs}
        if sub:
            sectors.append((etf, bpimod.compute(data.SECTOR_ETFS[etf][0], sub, sh)))
    sectors.sort(key=lambda x: x[1].pct, reverse=True)
    if a.sector:
        top = sectors[0][1]
    else:
        top = bpimod.compute("S&P 500", sigs, scope)

    def wk(b):
        prior = b.pct_on(week_ago)
        return None if prior is None else round(b.pct - prior, 2)

    if a.json:
        out = {"date": day, "name": top.name,
               "bpi": top.pct, "week_change": wk(top), "status": top.status,
               "bullish": top.bullish, "members": top.members,
               "membership": mem.source}
        if not a.sector:
            out["sectors"] = [
                {"etf": etf, "name": b.name, "bpi": b.pct,
                 "week_change": wk(b), "status": b.status,
                 "bullish": b.bullish, "members": b.members}
                for etf, b in sectors]
        print(json.dumps(out, indent=2))
    else:
        _bpi_report(top, sectors, day, week_ago, mem.source,
                    show_table=not a.sector, show_chart=a.chart)
    if a.txt:
        etf = f"-{a.sector.lower()}" if a.sector else ""
        path = a.txt if isinstance(a.txt, str) \
            else f"pnf-bpi{etf}-{day}.txt"
        _write_file(path, _capture(lambda: _bpi_report(
            top, sectors, day, week_ago, mem.source,
            show_table=not a.sector, show_chart=True)))
    if a.csv:
        path = a.csv if isinstance(a.csv, str) \
            else f"pnf-bpi-{day}.csv"
        rows = [("", top.name, top)] if not a.sector else []
        rows += [(etf, data.SECTOR_ETFS[etf][0], b) for etf, b in sectors]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["etf", "name", "date", "bpi", "week_change", "column",
                        "status", "bullish", "members"])
            for etf, name, b in rows:
                w.writerow([etf, name, day, b.pct, wk(b),
                            b.chart.columns[-1].kind, b.status,
                            b.bullish, b.members])
        print(f"wrote {path}", file=sys.stderr)
    if failed:
        print(f"({len(failed)} tickers failed: {', '.join(failed[:10])}"
              f"{'...' if len(failed) > 10 else ''})", file=sys.stderr)
    if former_failed:
        print(f"({len(former_failed)} former members have no price data, "
              f"left out of their member days: {', '.join(former_failed[:10])}"
              f"{'...' if len(former_failed) > 10 else ''})", file=sys.stderr)
    return 0


def _week_change(b, week_ago: str) -> str:
    prior = b.pct_on(week_ago)
    return "n/a" if prior is None else f"{b.pct - prior:+.1f}"


def _bpi_report(top, sectors, day: str, week_ago: str, source: str,
                show_table: bool, show_chart: bool) -> None:
    color = render.color_enabled()
    col = top.chart.columns[-1].kind
    print(f"{top.name} Bullish Percent  as of {day} close")
    print(f"BPI:     {top.pct:.1f}%  ({top.bullish}/{top.members} "
          f"on buy signals)  {_week_change(top, week_ago)} vs {week_ago}")
    print(f"Status:  {_paint_bpi(top.status, color)}  ({col} column)")
    print(f"Members: {source}")
    if show_table:
        print()
        header = (f"{'Sector':<23} {'  ' if color else ''}{'BPI':>6} "
                  f"{'1wk':>6} {'Col':^4} {'Status':<16} {'Bulls':>8}")
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
                  f"{_week_change(b, week_ago):>6} "
                  f"{b.chart.columns[-1].kind:^4} "
                  f"{_paint_bpi(f'{b.status:<16}', color)} "
                  f"{f'{b.bullish}/{b.members}':>8}")
    if show_chart:
        print()
        print(render.render(top.chart))


def _asof_date(text: str) -> str:
    """'YYYY-MM-DD' or 'friday' (the most recent Friday, today included)."""
    if text.lower() == "friday":
        today = date.today()
        return str(today - timedelta(days=(today.weekday() - 4) % 7))
    return str(date.fromisoformat(text))


def _paint_bpi(status: str, enabled: bool) -> str:
    if not enabled:
        return status
    code = render.GREEN if status.lstrip().startswith("Bull") else render.RED
    return f"{code}{status}{render.RESET}"


def _scan(argv):
    p = argparse.ArgumentParser(prog="pnf scan")
    p.add_argument("universe", nargs="?", default="sp500",
                   help="'sp500' (Wikipedia), 'sectors' (SPDR sector ETFs), "
                        "'snowball' (SPDR sector membership: tape, else the "
                        "snowball CSVs), a sector ETF "
                        "(e.g. xle), or a path to a file of tickers")
    p.add_argument("--top", type=int,
                   help="show only the best N by R/R (default: every ticker)")
    p.add_argument("--limit", type=int, help="only scan the first N tickers")
    p.add_argument("--days", type=int,
                   help="only signals fired within the last N calendar days")
    p.add_argument("--side", choices=["buy", "sell", "both"], default="both")
    p.add_argument("--range", default="5y")
    p.add_argument("--reversal", type=int, default=3)
    p.add_argument("--objective", choices=["sc", "classic"], default="sc")
    p.add_argument("--csv", nargs="?", const=True, metavar="FILE",
                   help="write the results to a CSV file "
                        "(default name pnf-scan-UNIVERSE-DATE.csv)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    u = a.universe.lower()
    try:
        if u == "sp500":
            tickers = data.sp500()
        elif u == "sectors":
            tickers = data.SECTORS
        elif u == "snowball":
            tickers = sorted({t for ts in data.membership().sectors.values()
                              for t in ts})
        elif u.upper() in data.SECTOR_ETFS:
            tickers = data.membership().sectors.get(u.upper())
            if not tickers:
                raise data.DataError(f"no members for {u.upper()}")
        else:
            with open(a.universe) as f:
                tickers = [t.strip().upper() for t in f if t.strip()]
    except (data.DataError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
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
        if cutoff and an.signal_date < cutoff:
            continue
        rows.append(an)

    # rankable setups first (R/R descending), then rows with no R/R
    # (already past the objective / through the stop / no stop reference)
    rows.sort(key=lambda r: (r.rr is None, -(r.rr or 0.0)))
    if a.top:
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
                      _num(r.objective, 9), _num(r.stop, 9),
                      _num(r.rr, 6)]
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
    if a.csv:
        path = a.csv if isinstance(a.csv, str) \
            else f"pnf-scan-{Path(a.universe).stem.lower()}-{date.today()}.csv"
        fieldnames = list(analysis.Analysis.__dataclass_fields__)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(r.to_dict() for r in rows)
        print(f"wrote {path}", file=sys.stderr)
    if failed:
        print(f"({len(failed)} tickers failed: {', '.join(failed[:10])}"
              f"{'...' if len(failed) > 10 else ''})", file=sys.stderr)
    return 0


def _num(v, width: int) -> str:
    return f"{v:>{width}.2f}" if v is not None else " " * width


if __name__ == "__main__":
    sys.exit(main())
