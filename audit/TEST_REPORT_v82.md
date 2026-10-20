# Pre-deployment test report — build v82 (2026-10-21)

Operator: "before applying test everything". The full suite was run on the files as they will be pasted (Visuals v82;
Master, Brief, Diagnostics and the arms unchanged). This report supersedes `TEST_REPORT_v79.md` for the current files.

## One defect found and fixed before deployment (F-A70)

- A new execution test ran every ticker tile and every H2 TREND row with missing data.
- It found the trend scores printed as **"NaN"** whenever a 1H / 4H / 1D score was missing. This was in the H2 card
  since before v81.
- Fixed in v82 (`f_sc()` → "—"). The test is now permanent (`panel_check.py` 9) and mutation-tested.

## Results on v82 (every result executed)

| Area | Tool | Result |
|---|---|---|
| Syntax, identifiers, declaration order, compile-error classes | `precheck`, `undeclared`, `order`, `pinelimits` | 0 problems, all 9 files |
| Dead values | `deadcode.py --all` | 0 dead, 0 structural, all 9 |
| Independent dead scan | `trace.py` | 0 zero-read in Master, Visuals, Diagnostics, EdgeCases. Arms 53, Brief 46, H2 1: **all on the checked companion list**, none outside |
| Read-before-write order | `sequence.py` | Unchanged from the triaged counts (Master 61, engine copies 52, H2 / Visuals 4). v81 / v82 added none. Visuals' 4 are the H2 swing state machine, verified by `h2_trace.py` |
| Statistics engine in all 6 engine copies | `formula_trace.py` | 61 / 61 PASS |
| Mathematics, race model | `formula_check.py`, `race_model_check.py` | PASS |
| Expectancy, regimes, decisions | `expectancy_check`, `regime_check`, `decision_check` | PASS |
| Every timeframe 1m … 1M, DST, sessions | `tf_check.py` | PASS, 0 failures (run on the final v82 file) |
| Macro, inputs, engine parity | `macro_check`, `inputs_check`, `diag_parity` | PASS (`showFVG` / `showOB` defaults differ by design: Visuals draws, the Master's are engine inputs; recorded KNOWN) |
| H2 rule and card | `h2_parity`, `h2_trace`, `h2_age_check` | PASS |
| Brief vs the website's code; rewrites; moved features | `brief_trace`, `refactor_check`, `moved_check`, `edgecase_cites` | PASS |
| Visuals panel, docks, glance, gauges, ticker, no-NaN | `panel_check.py` 1-9 | PASS (incl. 33,000 executed tile / TREND evaluations with missing data) |
| A/B arms | `diff -U0` | 5 / 4 hunks, as required |
| Diagnostics and Brief rebuilt from source | `build_diag`, `build_brief` | byte-identical |
| Traceability table, compile estimate, hashes | `value_map --check`, `compile_est`, `MANIFEST` | current; Visuals ~46 % of the limit; 9 / 9 OK |

## Not provable by these tests

- **Profitability or "best values".** The engine's own statistics on the operator's charts show WR 22-23 % and PF
  0.8-0.92. That is no demonstrated edge, and thresholds must not be tuned on this history. The website's frozen
  forward test is the judge.
- **The TradingView runtime and rendering.** Visuals v82 is NOT RUN until it is pasted. The table rules, the ticker's
  position above the plan strip and the visual order are confirmed only by a screenshot.
