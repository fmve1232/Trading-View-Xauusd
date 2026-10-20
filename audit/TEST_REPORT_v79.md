# Pre-deployment test report — build v79 (2026-10-21)

Operator's request: "test everything, every feature, every engine … no variables dead … wired end to end … fully
traceable with perfect sequence". Every checker in `audit/tools/` was run on the v79 files (commit `3ba10fd4`). Each
result below is an **executed** result. Nothing was marked PASS without running it.

## Results

| Area | Tool | Result |
|---|---|---|
| Syntax pre-checks (all 9 files) | `precheck.py` | PASS |
| Undeclared identifiers | `undeclared.py` | 0 in every file |
| Declaration order | `order.py` | 0 violations |
| Compile-error classes (G1-G12) | `pinelimits.py` | 0 issues |
| Dead / unread / write-only values | `deadcode.py --all` | 0 dead, 0 structural in all 9. The arms and the Brief carry 62 / 55 values displayed by Diagnostics (same engine); Strategy_H2 carries 1 displayed by Visuals |
| Independent dead-value scan | `trace.py` | 0 zero-read in Master, Visuals, Diagnostics, EdgeCases. Arms 53, Brief 46, H2 1: **every one is on `deadcode.py`'s checked companion list** (cross-checked, none outside it) |
| Read-before-write sequence | `sequence.py` | Master 61, engine copies 52, H2 / Visuals 4. These are the documented, triaged patterns (previous-bar state, calibration read before this bar's update, the 4-stage score pipeline). Re-checked by hand: `tqVeto` L4840 (the early read already ANDs `riskLock`, which L4848 folds in) and the breakout state (commented "after BOS evaluation"). No new hit since the v25 triage (65 → 61) |
| Statistics engine, executed in all 6 engine copies | `formula_trace.py` | 61 / 61 PASS: Wilson-low + Kelly (\|diff\| ≤ 3e-13), Kelly = log-growth optimum, race-grid interpolation, Platt / WLS calibration = constrained least squares, Murphy decomposition, TQ squash, inverse Cornish-Fisher (Newton vs bisection ≤ 9e-10; non-monotone domain kept correctly), race expectancy, MTF normalisation |
| Mathematics against references | `formula_check.py` | PASS: Murphy exact, Kelly vs numeric argmax 2e-5, Fisher t-quantile expansion |
| Race-probability model | `race_model_check.py` | PASS (60k simulated paths) |
| Expectancy / PF / t-interval / scorecard | `expectancy_check.py` | PASS |
| Volatility regimes, ATR floor | `regime_check.py` | PASS |
| Trend exclusivity, gates, veto, DECISION precedence | `decision_check.py` | PASS (5,000 cases each) |
| Every chart timeframe 1m … 1M, DST vs IANA, sessions | `tf_check.py` | PASS, 0 failures |
| Macro correlations: same-bar pairing, factors counted once | `macro_check.py` | PASS |
| Every input: valid, consistent across copies, = frozen defaults | `inputs_check.py` | PASS |
| Engine parity: Diagnostics / Brief / Master = Treatment | `diag_parity.py` | PASS (3,273 engine lines; 22 DECISION lines) |
| Rebuild of Diagnostics and Brief from their sources | `build_diag.py`, `build_brief.py` | byte-identical to the committed files |
| A/B arms | `diff -U0` | Treatment vs Control 5 hunks, vs Challenger 4 (stamp, title, role, trend gate): as required |
| H2 block parity and rule | `h2_parity.py`, `h2_trace.py` | PASS: byte-identical in 3 files; 3,000 plan cases and 200 × 300-bar sweep paths vs the specification |
| H2 card age / outcome / STALE | `h2_age_check.py` | PASS: 19,565 bars vs reference |
| Market Brief vs the website's own code | `brief_trace.py` | PASS (`arm_h4.py` in Python, `app.js` in Node) |
| Identical-output rewrites | `refactor_check.py` | PASS (Master = transform of the v66 commit, byte for byte) |
| Moved features | `moved_check.py` | PASS |
| Visuals panel and docks = the cards; glance logic | `panel_check.py` | PASS (incl. 6,000 nearest-level and 6,000 ROOM cases executed) |
| EdgeCases anchors | `edgecase_cites.py` | PASS |
| Value traceability table | `value_map.py --check` | current (33 values) |
| Compiled-token estimate | `compile_est.py` | PASS; Visuals ~40 % of the limit; Master = the v72 file that compiled |
| Hashes | `sha256sum -c audit/MANIFEST.sha256` | 9 / 9 OK |

## What these tests prove

- The formulas are implemented as written. They match first-principles references on synthetic data and over
  thousands of random cases.
- Every value is read and displayed somewhere: in its own file, or in a companion running the same engine.
- The decision rules behave as specified on every timeframe and in every volatility regime.
- The copies of each engine and block are identical.

## What they do NOT prove (stated plainly)

- **That the values are "best", or that the strategy is profitable.**
  - No static or synthetic test can show an edge.
  - The engine's own statistics on the operator's charts read WR 22-23 % (95 % CI ±5) with PF 0.8-0.92. That is no
    demonstrated positive expectancy on this history.
  - Changing thresholds to improve those numbers would be tuning on the same data (AUDIT_PROMPT §9). The only real
    test is the frozen forward test on the website (the system of record, A7).
- **The TradingView runtime.**
  - Compiles are confirmed only by the operator's pastes: Master v72, Visuals v78 (v79 NOT RUN yet), Brief v70,
    Diagnostics v68.
  - Rendering rules are invisible to these tools. F-A69 (one table per corner) was found only from a screenshot.
