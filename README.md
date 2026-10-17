# pnf

Deterministic Point & Figure engine: builds P&F charts from raw daily OHLC,
detects signals, computes vertical-count price objectives and logical stops,
and ranks setups by reward/risk. No LLM, no chart images — pure arithmetic.

```
pip install -e .

pnf LRCX                # analyze one ticker
pnf LRCX --chart        # ASCII P&F chart: green X / red O, month codes
                        # (1-9, A/B/C) in the boxes, 45-degree trend lines,
                        # year markers on the bottom axis
pnf LRCX --txt          # save report + chart to LRCX-pnf-DATE.txt
                        # (or --txt myfile.txt); plain text, no ANSI colors
pnf LRCX --json         # machine-readable
pnf LRCX --explain      # pipe the numbers through `claude -p` for a writeup
pnf scan                # scan the S&P 500: every ticker with a signal,
                        # buys and sells, ranked by R/R
pnf scan --top 10 --days 7 --side buy
pnf scan --csv          # save results to pnf-scan-sp500-DATE.csv
                        # (or --csv myfile.csv); all analysis fields
pnf scan sectors        # rank the 11 SPDR sector ETFs
pnf scan snowball       # scan the SPDR sector-membership universe
pnf scan xle            # scan one sector's components
pnf scan mylist.txt     # custom universe, one ticker per line
pnf bpi                 # S&P 500 bullish percent + all 11 sectors
pnf bpi xle --chart     # one sector's BPI with its own P&F chart
pnf bpi --txt --csv     # save report + BPI chart to pnf-bpi-DATE.txt and
                        # the sector table to pnf-bpi-DATE.csv
pnf bpi --asof friday   # as of last Friday's close (a holiday falls back to
                        # the prior session); or --asof 2026-07-02
pnf rs NVDA             # relative strength: NVDA vs its sector + sector vs SPY
pnf rs NVDA --vs QQQ    # ... vs an explicit benchmark
pnf rs xlv --chart      # one sector's RS vs SPY, with the ratio chart
pnf showcase            # quality businesses (snowball's judgment) ranked by
                        # how good their P&F chart looks; --chart, --csv, --txt
pnf showcase showpieces --sort combined --top 10
```

Example:

```
LRCX  2026-06-11  close 362.52
P&F:        Double Top Breakout on 2026-06-11 (bullish, triggered at 352.00)
Status:     bullish
Trend:      above bullish support line (194.00)
Reversal:   352.00  (low that flips to a new O column)
Objective:  439.00
Stop:       316.00  (one box below last O-column low)
Reward:     76.48
Risk:       46.52
R/R:        1.64
```

## Method (all deterministic)

- **Data**: Yahoo Finance v8 chart API (stdlib urllib, no key). Uses the
  `quote` arrays: split-adjusted, **dividend-unadjusted** — actual traded
  prices, the same series as StockCharts' unadjusted underscore symbols
  (`_LRCX`). Cached per calendar day in `%LOCALAPPDATA%\pnf\cache`.
- **Construction**: high/low method, 3-box reversal (configurable),
  StockCharts traditional box scale — 0.0625 under $0.25, 0.125 to $1,
  0.25 to $5, 0.50 to $20, 1 to $100, 2 to $200, 4 to $500, 5 to $1,000,
  10 to $2,500, 50 to $25,000, 500 above (bands through $50 boxes verified
  against live _TICKER charts). Extension always beats reversal, matching
  StockCharts.
- **Signals**: the StockCharts 3-box pattern catalog, classified
  most-specific-first at the moment a column crosses the prior same-kind
  extreme — Double / Triple / Quadruple Top Breakout, Spread Triple Top
  Breakout (equal tops at least seven columns apart with nothing between at
  the level and no breakdown inside), Ascending Triple Top Breakout
  (back-to-back double-top breakouts, rising inner low, no breakdown inside
  the formation), Bullish Catapult (triple-or-better breakout, pullback that
  holds, double-top breakout), Bearish Signal Reversed (three lower lows and
  two lower highs ended by a double-top breakout) — plus the exact bearish
  mirrors (… Bottom Breakdown, Descending Triple Bottom, Bearish Catapult,
  Bullish Signal Reversed). The ascending "no breakdown inside" constraint
  is verified against StockCharts' _LRCX label of 2026-06-11. Bullish /
  Bearish Triangle: a lower X-column high converging with a higher O-column
  low over five columns, resolved by the breakout. Bull / Bear Trap: a
  triple-or-wider breakout that exceeded the level by exactly one box and
  then reversed three boxes is relabeled in place — the signal's direction
  stands (as on StockCharts) but the pattern warns; a trap that later
  resolves with a fresh breakout completes a Catapult.
- **Alerts**: High Pole Warning / Low Pole Reversal — dated warnings, not
  signals. A pole is a column that beat the previous same-kind extreme by at
  least 3 boxes; the alert fires when the current reversal column has given
  back at least 50% of the pole's run *beyond that extreme* (measured in
  price above/below the broken level, not against the whole pole column —
  the measure that reproduces StockCharts' `_SPGI` High Pole Warning of
  2026-07-09 to the day). Shown as `Alert:` in the report and
  `alert`/`alert_date` in JSON and scan CSVs; superseded by the next signal.
  Alerts never enter the signal history, so patterns, objectives, stops, and
  the BPI are entirely unaffected.
- **Trend lines**: 45-degree lines, one box per column. Bullish support
  starts one box below a significant bottom, bearish resistance one box
  above a significant top; a violation flips to the opposite line anchored
  at the extreme since the broken line began. The active line and its
  current level are reported (`Trend:` / `trend` in JSON) and drawn on the
  chart in blue `/` and red `\`.
- **Objective** (default `sc`): StockCharts' automated Breakout Method,
  reverse-engineered to the dollar. The measure column is the first
  buy/sell-signal column after the most recent opposite signal (the column
  that reversed it). Bullish objective = column low − 1 + 3 × (high − low +
  box); bearish = column high + 1 − 2 × (high − low + box). Verified exact
  against ten published `_TICKER` objectives on 2026-06-11: bullish LRCX
  439, OXY 77, MSCI 679, IRM 166 (measure column crossing the $100 band),
  CASY 1279, NVR 7299 ($50 boxes); bearish BLK 961, BKNG 149, MELI 1441,
  AZO 2851. When the measure column is still building, StockCharts labels
  the objective "(Tentative)" — that is the `objective_active` flag here,
  and the number can extend. `--objective classic` switches to the Dorsey
  vertical count on the latest signal column (3× above its low / 2× below
  its high, walked along the box ladder).
- **Stop**: the price that would print the opposite signal — one box below
  the most recent completed O-column low (bullish) or one box above the most
  recent completed X-column high (bearish).
- **Reversal**: the price that flips the current column — `reversal` boxes
  off its extreme (the nearest chart event, distinct from the stop, which
  flips the *signal*). Reported in the analysis and marked on the chart
  (`<< 3-box reversal`).
- **R/R** = (objective − close) / (close − stop).
- **Bullish percent** (`pnf bpi`): percent of the universe whose latest P&F
  signal is a buy, per sector and for the whole index. Membership comes
  from the tape project's daily snapshots of the SPDR sector-ETF holdings
  (`spx_members` in `tape\db\tape.duckdb`, read-only, needs `duckdb`;
  default is `tape` next to the snowball directory, override with
  `PNF_TAPE_DB`), so index adds, drops and sector moves show up the day
  after they happen. It is **point-in-time**: each day counts only that
  day's members, and former members are fetched and counted for the days
  they belonged. A warning prints if the latest snapshot is over 7 days
  old. If tape can't be read, `pnf` falls back to the snowball project's
  hand-kept CSVs (`xle-components.csv` etc., `PNF_SNOWBALL`), which are
  *not* updated automatically. The report's `Members:` line says which
  source was used. The same membership drives `pnf scan snowball`,
  `pnf scan xle` and the sector lookup in `pnf rs`. Each
  ticker's signal history is a dated step function, so the full BPI series
  falls out of one chart build per ticker; the series is itself charted
  P&F-style (2-point boxes on 0-100, 3-box reversal) and read with the
  Chartcraft/Dorsey six-state vocabulary — Bull/Bear Alert (reversal out of
  the sub-30 / over-70 zone, no signal yet), Bull/Bear Confirmed (the BPI
  chart's own buy/sell signal), Bull/Bear Correction (reversal against the
  confirmed state, mid-zone). A ticker joins the denominator at its first
  signal; the series starts once half the members have joined, so a thin
  early denominator can't fake extreme readings. Caveats: tape's history
  starts 2026-07-09, and days before that use the first snapshot's members
  (survivorship bias over that stretch, so don't backtest across it; the
  CSV fallback backfills today's members across everything); small
  sectors are coarse (21 energy names = 4.76 points per stock).

  `--asof DATE` cuts every price series at DATE's close and uses the
  latest tape snapshot on or before it. The report shows the actual
  session date, so a market-holiday Friday reads as Thursday's close, with
  no holiday calendar needed. Each reading also shows its change from one
  week earlier (`1wk`, also `week_change` in the CSV/JSON).

  **Weekly report**: `ops\weekly_bpi.ps1` runs `pnf bpi --asof <Friday>`.
  It writes `reports\bpi\pnf-bpi-DATE.txt` (with the BPI chart) and
  `.csv`, then sends a one-line-per-sector summary plus the `.txt` to
  Telegram through `hermes send`. Logs go to `reports\bpi\logs`. The
  Windows scheduled task "pnf weekly BPI" runs it Saturdays at 8:00 AM,
  after tape's Friday-evening snapshot. It uses S4U logon ("Do not store
  password"), so it runs whether or not you're logged on and no password
  is stored. If the machine is off at 8:00, the missed run starts once it
  is back on.

- **Relative strength** (`pnf rs`, Dorsey Wright convention): the close
  ratio numerator/denominator × 100, charted close-only with 3-box reversal
  on a **log-scale grid** — each box 2% above the one below (`--box` to
  change), since a ratio has no natural dollar scale. For a stock, the
  sector is looked up in the current sector membership and two charts are
  produced: stock ÷ sector ETF and sector ETF ÷ SPY (`--vs` overrides; a
  sector ETF charts straight against SPY). Read on two clocks: the latest
  P&F signal on the ratio chart is the long-term view (RS signals
  historically persist for years), the current column the short-term one —
  buy + X = leader, buy + O = leader pausing, sell + X = laggard bouncing,
  sell + O = laggard. The reported reversal level is the ratio that flips
  the column.

- **Showcase** (`pnf showcase`): two axes kept separate. *Business
  quality* is read at run time from the snowball vault (`PNF_SNOWBALL`):
  the hand-argued showpieces table in `dossiers/_comparisons.md` and the
  Snowball 30 composite ranking (`reports/snowball30_composite.sql` run
  read-only against `facts/facts.duckdb`, needs `duckdb`). *Chart shape* is
  a 0–100 score from the chart alone: bullish status (20), price above the
  bullish support line (15) and how many years that line has held (10), a
  staircase of rising O-column lows (15), the share of history spent on buy
  signals (10), few buy/sell flips in the last two years (10 — raw signal
  count is useless here, a strong trend re-fires a breakout on nearly every
  column), price near its high (10), RS buy vs the sector (7) and sector vs
  SPY (3). Default history is 10y because shape needs years. Sort by chart
  score, by quality, or by `combined` (mean of quality percentile and chart
  score; showpieces sit at the top of the quality axis). It is a watch-list
  generator, not a signal — a beautiful chart on a great business means the
  market already agrees; the interesting rows are often the quality names
  whose charts are merely repairing.

## Validation

`tests/test_lrcx.py` freezes LRCX history through 2026-06-11 and asserts the
engine reproduces stockcharts.com's chart from that day box-for-box: current
X column 324–364, prior O-column low 320, Double Top Breakout 2026-06-11
triggered at 352, stop 316, objective 456. `tests/test_patterns.py` covers
the full pattern catalog and the pole alerts on hand-traced synthetic charts;
`tests/test_trend_render.py` covers trend-line flips and the chart's month
codes, bottom axis, and year markers. `tests/test_bpi.py` covers the BPI
series aggregation, point-in-time membership (adds and drops moving the
denominator), all six state readings, and the tape and snowball universe
loaders. `tests/test_rs.py` covers the log-scale ladder, ratio-series date
alignment, and all RS verdict states. `tests/test_showcase.py` covers the
showpieces-table parser and the shape score on synthetic staircase,
collapse and saw-tooth charts.

```
python -m unittest discover -s tests
```

## Caveats

- With `--objective classic`, counts that walk across a box-size band
  boundary (e.g. through $1,000, where boxes jump from $5 to $50) project
  in the larger boxes and can look extreme. The default `sc` method works
  in dollars and does not have this artifact.
- Pattern names follow the ChartSchool definitions, but only the labels
  captured on 2026-06-11 (LRCX) are verified against StockCharts' own
  automated labels. Their engine may have undocumented tie-breaks for the
  rarer names (spread widths, catapult feeders); treat exotic labels as
  advisory until more are field-checked.
- A high R/R often means price has pulled back to just above the stop — the
  risk is small but the chart is one box from a sell signal. Pair the scan
  with `--days N` for fresh signals and look at the chart before acting.

- Yahoo includes the in-progress bar during market hours; a signal can
  appear intraday and be gone by the close. Scan after the close for final
  prints.
- The S&P 500 list is scraped from Wikipedia (cached daily) and validated to
  contain 400+ symbols.
- The benchmark is the **unadjusted** chart. StockCharts' default symbols
  (`LRCX`) are dividend-adjusted; compare against the underscore form
  (`_LRCX`) when validating. For low-yield stocks the two are usually
  identical in recent history because dividends are small relative to the
  box size, but high-yield names will diverge further back.
