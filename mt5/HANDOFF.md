# MT5 project — handoff (written 2026-11-27, for a new thread)

Paste this into the new thread: *"Read `mt5/HANDOFF.md` on branch `claude/xauusd-developed-files-tmnk9g` of
`fmve1232/trading-view-xauusd` and continue the MT5 line."*

## Why the MT5 line exists
- TradingView's free plan stops a script after 20 s ("Script takes too long to calculate", F-A94). The Pine Master
  and Visuals are at that edge (v105 / v106 cut the bars to 1500 and Visuals' unused 1-minute footprint data).
- The operator chose MetaTrader 5 (free, no calculation limit, the broker's own prices, free push alerts).

## The operator's setup
| Item | Value |
|---|---|
| Platform | MT5 **desktop**, Windows (the phone app cannot run custom indicators; it only receives push alerts) |
| Broker | **Exness** |
| Symbol | **`XAUUSDm`** |
| Decision timeframe | 15m (5m for timing only) |
| Server time | detected at run time (`TimeTradeServer() - TimeGMT()`); input `InpServerGmtOffset` overrides it |
| Install | MetaEditor (F4) -> New Custom Indicator -> paste -> F7; push alerts via the MetaQuotes ID |

## Non-negotiables (carried from the Pine line, see `CLAUDE.md`)
- **A7: the website is the only system of record** (default branch `claude/audit-prompt-real-artefacts-nekqv6`). MT5
  files are DISPLAY ONLY; they copy the website's rules and never count as evidence. Read the website, never edit it.
- **Do not tune** any threshold, weight or gate on price history. Copy rules; do not improve them.
- **Never mark PASS what was not executed.** There is no MetaTrader here: the MQL5 compile is the operator's F7 test,
  always reported as NOT RUN until the operator confirms "0 errors".
- **Do not delete features**; the MT5 line adds them stage by stage.
- No model identifiers in files; commit trailers as the session gives them; push to this branch only; no PR unless asked.

## Done
| Build | Commit | File | What | Verified |
|---|---|---|---|---|
| M1 | `8c1c6f9` | `mt5/XAUUSD_Quantum_H2.mq5` (505 lines, SHA-256 `cca575188cafb1be8963c2ed9c525405374ca611006cc80fa1e1ce3f41bfe777`) | H2 / arm H3 sweep-to-value: trend 1H / 4H / 1D, 5-bar swing sweeps, 100-bar volume profile (40 bins, 70% VA), ATR14 risk window 0.5-5 ATR, arrows, POC / VAH / VAL, plan lines, checklist panel, pop-up + push alerts | `mt5/tools/h2_mt5_check.py`: 53 / 53 website H3 signals on 15m identical (direction, SL, TP1, TP2, swept level). Compile: **NOT RUN** (awaiting the operator's F7 result) |

## What was learned building M1 (keep these)
1. **4H bars** = 1H grouped on New York wall-clock time from 17:00 (17, 21, 01, 05, 09, 13), as the website's
   `sources.resample_ny_session` does. MT5's own H4 (UTC grid) gives different signals (control in the check).
2. **1D bars**: the website's daily bars (Twelve Data's own feed) close with the **NY 17:00 trading day** (median gap
   $0.66 over 192 weekdays), not UTC days ($4.71), although `quantum/data/market.py` says "UTC calendar days" (F-A95,
   open, website project). Label each NY trading day at 00:00 UTC of its date, as the website labels them.
3. **Alignment**: each chart bar reads the last higher bar that OPENED strictly before the chart bar CLOSED, and in it
   `close[1]` and the EMAs of `close[1]` (website `market.align` + `htf_expr`). No look-ahead.
4. **EMA / RMA seeding**: seeded by the SMA of the first n values (website `ta._seeded_recursive`), not MT5's `iMA`.
   ATR14 = RMA of the true range, TR of the first bar = high - low.
5. **Volume profile** starts at bar index 99 (website engine), not 100 (Pine H2 block). Same result after warm-up.
6. **Data differences (not rule differences)**: Exness prices vs Twelve Data; Exness TICK volume vs the website's COMEX
   futures volume, so POC / VAH / VAL and some signals can differ on the terminal.
7. The website has `quantum/mt5.py` (MetaApi, read-only broker feed for display, optional, about USD 9 / month): it
   compares the broker's candles with the engine's. Not used by the MT5 indicator.

## How to verify a stage (method)
- Scratch copies: `git archive origin/claude/audit-prompt-real-artefacts-nekqv6 quantum | tar -x -C <web>` and
  `git archive origin/market-data | tar -x -C <store>`; `pip install numpy pandas requests scipy`.
- Run the website engine read-only on the store (pattern in `mt5/tools/h2_mt5_check.py` / `audit/tools/engine_dump.py`:
  network disabled, `TWELVEDATA_API_KEY=offline-audit`).
- Write a statement-for-statement Python copy of the `.mq5`, run it on the same bars, compare bar by bar; add a control
  that a known wrong variant is detected. Keep the `.mq5` source ASCII only (MetaEditor may misread UTF-8 without BOM).

## Next stages (planned, not started)
1. **M1 follow-up**: the operator's F7 result and an `XAUUSDm` M15 screenshot; fix compile errors if any.
2. **M2 — the Master's engine and dashboard** (the website's `quantum/engine.py` treatment arm is the reference; the
   Pine Master is its display copy): regime, trend gates, structure (BOS / CHoCH / MSS, order blocks, FVG), liquidity
   pools (PDH / PDL / PWH / PWL / CDH / CDL on the NY trading-day key, F-A87; F-A88 open), macro chain (MT5 symbols
   for DXY / US10Y / silver / EURUSD / SPX depend on what Exness offers: ask the operator), plan (SL / TP / lots incl.
   cost, Exness XAUUSDm contract size to be confirmed from the symbol specification), DECISION, alerts.
   Stage it: engine values first, checked against the website value by value, then the dashboard.
3. **M3 — Visuals' strip** (one row under the dashboard: regime, trend, H2, sweep, room, value, macro, checks, record).

## Pine line status at handoff
- Build v106 (`c7954ef`): Visuals runs on the free plan (operator's screenshot 2026-11-27). The Master's v106 paste
  showed "Failed to fetch" in the Pine Editor: a connection error between the browser and TradingView's compiler, not a
  code error (v106 changed only `calc_bars_count` 3000 -> 1500 and the stamp vs v105, which compiled the same day).
