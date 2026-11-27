# Operator record: requirements, rules and development so far (saved 2026-11-27)

This file keeps the operator's requirements and the project's rules in one place, so that every later session (MT5,
website or Pine) starts from them. The sources are named in each section. Where a source and this file disagree, the
source wins: `CLAUDE.md` and `audit/PREREGISTRATION.md` on the website line.

## 1. The target (operator instruction, 2026-11-15; `CLAUDE.md`)
- **Phone alerts that give the best XAUUSD entry price.** From the alert, price moves at least **$10**, preferably
  **$15-$20**, in the alert's direction before the stop.
- The entry weighs market bias and trend, macro and micro indicators, volume, order blocks, liquidity sweeps,
  reversals, pullbacks and breakouts, with historical probability and the major liquidity areas.
- **Maximum planned loss per trade: $650 including costs.**
- Alerts must be **accurate, validated and calibrated**.

## 2. The working rule (operator, 2026-11-15)
- "Do not deviate from the instructions which I have given to you, and do not suggest an alternative ... put your
  best effort to achieve my target."
- Work to the target and the instructions as given. No different objective, no substitute rule, no list of options.
- When an instructed step is finished, go on to the next instructed step.
- Report what was measured, as measured.

## 3. Limits the operator set, in force
- No signal without sufficient evidence.
- No artificial signals to raise the frequency.
- No stop or target moved to improve a hit rate.
- **B24 OFF.**

## 4. Non-negotiables (`CLAUDE.md`, the audit)
- **One system of record (Amendment 6, 2026-10-06):** only the website's forward tests count (`quantum/`, `site/`;
  the section 7 arms on 1H and the Amendment 5 H2). The Pine line on `claude/xauusd-developed-files-tmnk9g` and these MT5
  files are **display only**. Never cite them as evidence.
- **Holdout freeze** from 2026-09-28 00:00 UTC. Any change to `holdout.ENGINE_SOURCES` or `quantum/config.py` restarts
  it. The Pine reference files stay at the hashes in `audit/PREREGISTRATION.md` section 2.
- **Do not tune** thresholds, weights or gates on this price history. Diagnose instead. The only real fix is a
  frozen holdout.
- **Never mark PASS what was not executed.** `NOT RUN` is the honest verdict.
- **Do not delete features** (2026-09-26). Wire them in, or move them to a companion that runs the same engine.
- Checkers narrow the search. **They do not replace the compiler.** For MT5, the compiler is the operator's F7.
- Do not reconstruct `cost_invariant.py` or `validate.py` from the comments describing them.
- No model identifiers in repository files.

## 5. Decisions on platforms
| Date | Decision |
|---|---|
| 2026-09-09 | Delivery: after every `.pine` change, send all artefacts together with the build record (hashes, checker results). |
| 2026-09-27 | The Python website is the production system and the primary forward test. TradingView is not a dependency. |
| 2026-10-06 | Amendment 6: one system of record (the website). |
| 2026-11-27 | **MT5 line started.** TradingView's free plan stops scripts after 20 s (F-A94). MT5 desktop is free, has no calculation limit and shows the broker's own prices. |

## 6. The operator's MT5 setup (`mt5/HANDOFF.md`)
| Item | Value |
|---|---|
| Platform | MT5 desktop on Windows. The phone app cannot run custom indicators; it only receives push alerts. |
| Broker / symbol | Exness, `XAUUSDm` |
| Decision timeframe | 15m (5m for timing only) |
| Server time | detected at run time; `InpServerGmtOffset` overrides it |
| Phone alerts | MetaQuotes ID from the phone app, entered in desktop Tools -> Options -> Notifications. Alerts fire only while the desktop MT5 runs. |

## 7. MT5 development so far
| Build | Date | What | Verified |
|---|---|---|---|
| M1 | 2026-11-27 | `XAUUSD_Quantum_H2.mq5`: the website's arm H3 / Pine H2 sweep-to-value rule. 1H / 4H / 1D trend, 5-bar swing sweeps, 100-bar volume profile, arrows, POC / VAH / VAL, plan lines, checklist panel, pop-up and push alerts. 505 lines, SHA-256 `cca575188cafb1be8963c2ed9c525405374ca611006cc80fa1e1ce3f41bfe777`. | Rule transliteration vs website: see section 8. Compile: **NOT RUN**. |
| M1.1 | 2026-11-27 | The same rule (no rule line changed). Fixes alert delivery and runtime handling found in the audit below. 542 lines, SHA-256 `8379e5fac1fa34ca469d0c442e51fa2ba6a0f9852cf1fad1a8e5edcb33baebfa`. | Same rule check. Control-flow model of the alert / progress logic: PASS. Compile: **NOT RUN**, waiting for the operator's F7 result. |

## 8. Audit of the MT5 code (2026-11-27)
**Re-executed here.** `mt5/tools/h2_mt5_check.py` was run on the website's store (`market-data` @ `d73c26be`, 7,497 15m
bars, 2026-08-05 to 2026-11-27) against the website's own `quantum/` (`claude/audit-prompt-real-artefacts-nekqv6` @
`8580006`). All four checks passed.
1. All 55 website H3 signals match the `.mq5` rule: direction, SL, TP1, TP2 and swept level, with 0 differences.
2. 1D closes built from H1 on the NY 17:00 day are $0.66 from the website's daily closes (median, 193 weekdays). On UTC
   days the gap is $4.71.
3. The H4-on-UTC-grid control was detected, with 1 difference.
4. VP start at bar 100 versus 99: 0 differences.

**Finding A1: check 1 is narrower than the M1 handoff says.** Check 1 replaces the `.mq5`'s own 1D bars with the
website's daily bars. Run on its own 1D path (H1 grouped on the NY day), the rule gives **7 differences on 55 signals**.
All 7 fall before 2026-09-10. This store's H1 starts on 2026-03-02, so the 1D EMA200 has not seeded yet when they occur.
There are 0 differences after that date. This is a warm-up effect, not a rule difference. On the terminal the H1
history is years long. The match on Exness data is **NOT RUN**. M1.1 shows the H1 start date and the 1D bar count on
the panel, flagged when EMA200 is not seeded.

**Finding A2 (fixed in M1.1): missed alerts after a full recalculation.** M1 alerted only when
`prev_calculated != 0`. MT5 recalculates from zero after a history update, a reconnect or an H1 load retry. In M1, a
signal bar closing at that moment gave no pop-up and no push. M1.1 alerts when the signal bar closed less than one bar
period ago, whatever the recalculation state.

**Finding A3 (fixed in M1.1): duplicate alerts on re-attach.** In M1 the "already alerted" bar was lost on re-attach,
on an input change or on a terminal restart. M1.1 keeps it in a terminal global variable per symbol and timeframe
(`QH2_<symbol>_<seconds>`). Two charts with the same symbol and timeframe also share it, so you get one push, not two.

**Finding A4 (fixed in M1.1): progress tracked by index.** When the chart reaches its "Max bars in chart" limit, MT5
drops old bars and indexes shift. M1's `g_done` index could then skip a new bar. M1.1 tracks the last processed bar by
its open time. If that bar is not found, it recalculates everything.

**Finding A5 (fixed in M1.1): partial H1 download.** M1 could read the trend from an H1 series that was still
downloading. Arrows on history were then computed on short EMAs and not redrawn. M1.1 waits up to 50 calls for
`SERIES_SYNCHRONIZED` and otherwise shows "H1 not synchronised".

**Finding A6 (fixed in M1.1): alert text.** The push now ends with "display copy, not validated". This is true: H3's
forward test has not met its decision rule. H3 is decided on the **1H** record (N >= 50, 95% t-interval of mean R
above 0, PF >= 1.2, by 2027-03-31; `PREREGISTRATION.md` Amendment 7 section 3). The 15m record is not the deciding one.

**Finding A7 (open): fixed GMT offset.** The server offset is detected once and applied to all history. Exness MT5
servers run at GMT+0 all year, so this has no effect there. On a broker whose server time follows DST, half the
history would be off by 1 h.

**Finding A8 (open, M2 scope): no lot size and no $ risk.** The `.mq5` shows price levels but no lot size, $ risk or
cost. On the website's 55 H3 signals the plan geometry is as follows. These are distances, not outcomes.
- R (entry to stop): $2.70 / $7.09 / $25.44 (min / median / max).
- TP1 distance: $2.70 / $18.63 / $120.45. TP1 is at least $10 on 39 of 55 signals.
- TP2 distance: at least $10 on 54 of 55 signals, at least $15 on 51.

At a fixed 0.5 lot (50 oz on a 100 oz contract), 10 of 55 stops would exceed $650. The $650 limit therefore needs lots
sized per signal, including the spread and commission. Use the terminal's own `SYMBOL_TRADE_CONTRACT_SIZE`, which needs
the Exness `XAUUSDm` specification confirmed. This is the plan item of stage M2 in `mt5/HANDOFF.md`.

**Compile review (by reading; not a compile).** No undeclared names were found. The struct with dynamic arrays,
calls to functions defined later, `LONG_MIN`, `SeriesInfoInteger`, `GlobalVariable*`, `ObjectsDeleteAll(0, prefix)`
and the arrow properties are all standard MQL5. The source is ASCII only. The verdict stays **NOT RUN** until the
operator reports F7 "0 errors".

## 9. Next instructed stages (`mt5/HANDOFF.md`)
1. M1.1: the operator's F7 result and an `XAUUSDm` M15 screenshot. Fix compile errors if any.
2. M2: the Master's engine and dashboard (website `quantum/engine.py` treatment arm as reference). Includes the plan
   with lots sized to the $650 limit including costs, the macro chain (MT5 symbols for DXY / US10Y / silver / EURUSD
   / SPX, to be confirmed with the operator), DECISION and alerts. Staged: engine values first, checked against the
   website value by value.
3. M3: Visuals' strip.
