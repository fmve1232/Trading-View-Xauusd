# Pine files: audit and validation addendum (build v90, 2026-10-31)

This is the Pine-specific part of the 17-phase audit, run again after website PR #49 (Amendments 12 and 13) merged.
The website is the system of record (A7). Every file here is display only, and nothing below is a trading verdict.
Companion to `INSTITUTIONAL_AUDIT_v90.md`. Each claim below is labelled with how it was established:

| Label | Meaning |
|---|---|
| EXECUTED | The Pine text itself was run in Python (`pine_exec`) and compared with an independent reference. |
| STATIC | The Pine text was read, not run. |
| BLOCKED | It cannot be done from here. The reason is given. |

## 1. Question asked: "Have you audited the Pine files?"

**Yes, all nine files, against the code as written.** One gap remained after the v90 audit: the central statistical
finding F-A78 (the engine's calibrated P has no skill) was measured on the **website's Python port** of the engine,
not on the Pine engine. This addendum closes that gap as far as it can be closed without TradingView.

`pine_web_parity.py` (new) **executes** the Pine blocks that define the probability and runs them against the
website's own functions, imported read-only from the default branch @ `6fca44dcf`:

| # | Block | Cases | Mismatches |
|---|---|---:|---:|
| 1 | L / S / R score normalisation: Pine `normalizeScores` vs `normalize_scores`. Pine's half-away-from-zero rounding is matched by the port's `pround`. | 20,000 | 0 |
| 2 | Race-probability grid interpolation: `f_gridInterp` vs `f_grid_interp` | 20,000 | 0 |
| 3 | The outcome event the probability is fitted to: the Master's race loop as written vs `label_outcome`, on random paths with N = 3, 4, 12 and 70, including na ATR and na multipliers | 71,398 races | 0 |

Positive controls:

- **1c:** the controls confirm the rounding case is actually present in the test.
- **3c:** a copy of the loop with the tie order flipped (target checked first) **is** caught, with 331 mismatches. A
  checker that could not fail would prove nothing.

**What this establishes.** The Pine engine and the website score the **same event**, with the **same normalisation and
interpolation**. F-A78 therefore applies to the Pine `mP` by inference, plus the Diagnostics reliability table on the
chart, which is consistent with it.

**What it does not establish.** It does not show that the Pine `mP` values equal the port's values bar for bar. The
documented port differences remain:

- D-03: the analog scan runs in chunks;
- D-04: the 0.7 decay.

A direct measurement would need the Pine runtime's history of `mP`. That is **BLOCKED**: TradingView cannot be run
here, and an export would need the operator (RUNBOOK).

## 2. Fresh validation run (2026-10-31, after PR #49)

Static checks:

| Tool | Result |
|---|---|
| precheck · undeclared · order · deadcode · pinelimits · sequence | 0 issues, 9 files |
| bug_scan | look-ahead 0; every other hit triaged (catalogue §2–3) |

Executed checks (exit 0, 0 FAIL): diag_parity, regime_check, decision_check, expectancy_check, value_map --check,
edgecase_cites, moved_check, refactor_check, inputs_check, macro_check, compile_est, panel_check, h2_age_check,
h2_parity, h2_trace, formula_trace, v86_check, v88_check, brief_trace, race_model_check, formula_check,
**pine_web_parity (new)**, **tf_check** (every chart timeframe 1m–1M, DST vs IANA, session shading on 98,136 1H bars).

| Check | Result |
|---|---|
| `brief_trace` (re-run against the **merged** website) | PASS: the Brief still equals the site's `arm_h4.py` / `app.js` |
| `MANIFEST.sha256` | 9 / 9 OK |

Since PR #49 the H6 ledger (`h6` in `ledger_stats.py`) exists in the website's pipeline but has N = 0. Its first
records come with the next pipeline run.

## 3. Per-file review

| File | Role | Verified | Open / blocked |
|---|---|---|---|
| Master | Engine, DECISION, dashboard, alerts | EXECUTED:<br>• decision precedence, gates, veto<br>• regime; expectancy and t / Wilson intervals<br>• formulas; H2 block<br>• every timeframe; inputs<br>• probability blocks == website (§1)<br>STATIC: 0 dead values, no look-ahead | • Compile NOT RUN since v83: about 45–85 tokens free (F-A72)<br>• `mP` has no skill (F-A78; labelled "score" plus the measured AUC, not fixed: A7) |
| Visuals | Drawings, terminal panel, ticker, MACRO copy, checks / risk | EXECUTED:<br>• panel == cards; ticker tiles<br>• no "NaN" reaches the screen<br>• calendar; MX block == Master<br>• H2 card ages; cost, risk and Wilson arithmetic<br>• session shading on every timeframe | • Compile NOT RUN<br>• the typed ledger records go stale; refresh them when re-sent<br>• the calendar list ends 2027-12-10 |
| Brief | The website's Market Brief on the chart | EXECUTED against the merged site's own Python and JS (1,080 `h4Losing` × `doNow` states) | Compile NOT RUN (estimate 98.8–99.4% of the limit) |
| Diagnostics | Features over the Master's limit, Treatment engine verbatim | `diag_parity`: engine == Treatment | Compile NOT RUN |
| Strategy / OLDGATES / CHALLENGER | A/B twins (repo set) | `diag_parity` hunk counts (5 / 4) and an identical scorecard | Display only under A7 |
| Strategy_H2 | Arm H2 | `h2_parity` byte-identical; `h2_trace` vs its specification | Display only |
| EdgeCases | Run-once diagnostic | `edgecase_cites`: every anchor is exactly one Master line | F-A75: the chart run is NOT RUN since v86 |

## 4. Pine-specific defects

Since v90 no new defect was found in the Pine code. Open items:

| ID | Severity | Item | Status |
|---|---|---|---|
| F-A78 | Critical (analytical) | `mP` / `cal_veto` have no out-of-sample skill | Labelled on the chart. The website now runs arm H6 (no score veto) to measure the veto's effect (A12) |
| F-A74 | Medium | The engine's `newsWindow` guesses release dates | Visuals shows the official calendar. An engine fix needs the website |
| F-A75 | Low | EdgeCases runtime error on the chart (2026-10-21) | Mitigated v86; needs a chart run |
| — | Process | v86–v90 have not been compiled in TradingView | **BLOCKED (operator).** The checkers narrow the search; they do not replace the compiler |

## 5. What is needed for final acceptance

All four items are blocked on the operator; none can be done from here.

1. Paste the chart set into TradingView and report any compile error or token count. This calibrates `compile_est`.
2. Run EdgeCases once and send its table (F-A75).
3. Provide broker specifications: spread, commission, contract size and the MT5 offset.
4. Optionally, export the Diagnostics reliability table or the `mP` history. This would turn the F-A78 inference in §1
   into a measurement on the Pine engine itself.

Until these are done, the honest status is: **code verified as written; the runtime is unverified; the probability has
no demonstrated skill.**
