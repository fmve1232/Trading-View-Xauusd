# End-to-end feature verification — the files on the chart (Master = v83 file, Visuals v85), 2026-10-21

**"Executed"** means the Pine text itself was run in Python against a reference. **"Static"** means a read of the code.
**"On chart"** means the operator's screenshot showed it working. TradingView's runtime is never run here.

## Master (`dad15e89…`, compiled)

| Feature | Verified by | Result | On chart |
|---|---|---|---|
| Trend engine (EMA stack, trend score), 5M-1D MTF confluence | `decision_check` (exclusivity), `formula_trace` (MTF normalisation, 5 TFs) | PASS, executed | yes (MARKET / BIAS cells) |
| Structure: BOS / CHoCH / MSS (internal + swing) | `decision_check`, `sequence` triage (breakout state) | PASS | yes (STRUCTURE cell) |
| Liquidity pools, reach scores, sweeps | `diag_parity` (engine = Treatment), `decision_check` (sweep flags) | PASS | yes (LIQUIDITY cell) |
| Regime engine (5 regimes + abnormal), adaptive ATR, SL multiples, size haircut | `regime_check` (every percentile, ATR floor) | PASS, executed | yes (RISK / RANGE) |
| Macro: DXY, US10Y, real yield, XAG, SPX, EUR; correlations | `macro_check` (same-bar pairing, each factor once, known-r model) | PASS, 45 checks | yes (MACRO cell) |
| Probability: Platt / WLS calibration, Brier / Murphy, race grid, race expectancy, Cornish-Fisher | `formula_trace` (61 / 61 over 6 engine copies), `formula_check`, `race_model_check` | PASS, executed | yes (SIGNAL cell L / S / R %, EV) |
| Trade quality, gates, vetoes, DECISION precedence (RISK LOCK > NO TRADE > BUY > SELL > WARMUP > WAIT) | `decision_check` (5,000 cases each) | PASS, executed | yes (DECISION WAIT TQ38D) |
| Trade plan: entry, SL, TP1-3, RR, MT5 offset, lots, Kelly (Wilson-low) | `formula_trace` (Kelly + Wilson), `refactor_check` (plan rows), `expectancy_check` | PASS | yes (plan strip) |
| Risk controls: daily loss / trades / streak lock | `decision_check` (veto / lock), `sequence` triage | PASS | not triggered |
| News window (New York time, F-A71) | static (`bug_scan` T1, triaged) | label fixed | off by default |
| H2 SETUP line (byte-identical H2 block) | `h2_parity`, `h2_trace` | PASS, executed | yes (DECISION column) |
| Alerts (one `alert()` channel): confirmed BUY / SELL + plan, DECISION changes, BOS / CHoCH / MSS, pool sweeps, H2 SETUP, risk lock | `decision_check` (first-bar firing, 300 sequences; 8 flags), `bug_scan` A1 (0 hits) | PASS | needs a live event |
| Every input valid, = the frozen defaults; every TF 1m-1M | `inputs_check`, `tf_check` (re-run 2026-10-21: 0 failures) | PASS | — |
| Size limits | `compile_est` (capped at the compiled v72 estimate; real ≈ 100,170-100,212, measured) | PASS | compiled |

## Visuals (v85 `d052ab58…`, compiled)

| Feature | Verified by | Result | On chart |
|---|---|---|---|
| EMAs, VWAPs, BB, level tags (PDH / PDL, PWH / PWL, PMH / PML, CDH / CDL), sweeps ✕, BOS / CHoCH labels | static suite; `tf_check` | PASS | yes |
| Session shading = the engine's sessions, DST | `tf_check` (98,136 1H bars), `h2_parity` (SESSIntel = engine) | PASS, executed | off by default since v81 |
| H2 sweep-to-value signals + card, age / outcome / LIVE-STALE | `h2_parity`, `h2_trace`, `h2_age_check` (19,565 bars) | PASS, executed | yes (STALE · stopped) |
| Gold drivers (USDJPY, oil, real yield, breakeven, US 2Y) | `macro_check` D / E (executed, byte-identical with the Brief) | PASS | yes |
| Terminal panel / docks under the Master / bottom ticker / gauges / glance | `panel_check` 1-9 (executed nearest-level, ROOM, gauges, 33,000 no-NaN evaluations) | PASS | dock band + ticker shown (v77-v84 screenshots) |
| Alerts: H2 swing sweeps, ✕ pivot sweeps, touches, H2 signals | `panel_check` 10 (3,438 executed), `bug_scan` A1 (remaining = intrabar-by-design touches) | PASS | needs a live event |

## Brief / Diagnostics (v83, compiled at v70 / v68 sizes; text-only changes since)

| Feature | Verified by | Result |
|---|---|---|
| Engine = Treatment, verbatim | `diag_parity`, rebuild byte-identical | PASS |
| Brief: trend, heading, liquidity taken, target, DO NOW, playbook (arm H4), gates, ENGINE / DATA / STATS rows | `brief_trace` (executed against the website's `arm_h4.py` and `app.js`) | PASS |
| Diagnostics: reliability buckets, rolling CI, gate funnel, vetoes, analog evidence, missed moves | `formula_trace`, `diag_parity`, `deadcode` (wired) | PASS |

## Integrity across all files

| Property | Result |
|---|---|
| Dead or unwired values | 0 (`deadcode`); `trace.py` zero-reads all on the checked companion list (0 outside) |
| Read-before-write order | the triaged counts, unchanged (Master 61, engine copies 52, H2 / Visuals 4) |
| Look-ahead / repaint / `varip` / `timenow` | 0 / 1 by design (forming-4H option) / 0 / 0 |
| Divisions | all ~80 engine sites guarded (hand triage, v83) |
| A/B arms | 5 / 4 hunks as pre-registered |
| Rebuilds (Diagnostics, Brief) | byte-identical |
| Hashes | 9 / 9 |

## Open items (not verifiable here)

- **Edge Case Harness:** "Runtime error: Unknown error" on the operator's chart (2026-10-21). It is a run-once diagnostic
  in its own pane, not part of any decision or alert. It passes every static check (0 issues), but TradingView's
  "Unknown error" gives no line, so it cannot be reproduced here. Recommended: remove it from the chart. If it is needed
  again, the operator's screenshot of the error tooltip identifies the line.
- **Alerts** fire only on live bars, so confirming one needs a real event on the chart.
- **No strategy has a demonstrated edge** (WR 22-25 %, PF 0.85-0.92 on the engine's own statistics). The website's
  frozen forward test decides.
