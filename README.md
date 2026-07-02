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
pnf LRCX --json         # machine-readable
pnf LRCX --explain      # pipe the numbers through `claude -p` for a writeup
pnf scan                # scan the S&P 500, rank buy signals by R/R
pnf scan --top 10 --days 7 --side both
pnf scan sectors --side both    # rank the 11 SPDR sector ETFs
pnf scan mylist.txt     # custom universe, one ticker per line
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

## Validation

`tests/test_lrcx.py` freezes LRCX history through 2026-06-11 and asserts the
engine reproduces stockcharts.com's chart from that day box-for-box: current
X column 324–364, prior O-column low 320, Double Top Breakout 2026-06-11
triggered at 352, stop 316, objective 456. `tests/test_patterns.py` covers
the full pattern catalog on hand-traced synthetic charts;
`tests/test_trend_render.py` covers trend-line flips and the chart's month
codes, bottom axis, and year markers.

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
