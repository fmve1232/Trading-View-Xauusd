# Formula registry

Master prompt §14. The mathematical source of truth: one row per
`(formula_id, version)`, machine-readable, in the `formula_registry` table.

**Status: designed, empty.** Population is Phase 2 — mechanical extraction from
the Pine source, reviewed by hand. It is not populated now because a registry
written from memory is a description of what someone believes the engine does.

## Fields

| Field | Why |
|---|---|
| `formula_id`, `version` | identity; a formula change is a new version, never an edit |
| `name`, `description` | |
| `expression` | the mathematics, as written |
| `source_variables`, `output_variable` | the dependency graph |
| `units`, `timeframe`, `lookback` | |
| `assumptions` | stated, never implied (§34) |
| `implementation` | the Python file and function |
| `pine_reference` | `file:line` in `reference/quantum_5_0/`, re-derived on every Quantum 5.0 rebuild |
| `test_status` | `NOT RUN` \| `PASS` \| `FAIL` \| `PARITY_PENDING`, defaulting to `NOT RUN` |

`test_status` defaults to `NOT RUN`, not `PASS`. Carried from `CLAUDE.md`:
never mark PASS what was not executed.

## Line citations go stale

The upstream audit already lost a full set of citations this way (F-A09: every
pointer wrong by +7 to +143 lines, while the expressions still matched). That is
the failure mode the harness's "verified by eye, not by the compiler" caveat
predicts.

So `pine_reference` is **derived**, never hand-maintained. `audit/tools/trace.py`
upstream exists for this. Any re-vendoring of Quantum 5.0 re-derives every
citation in the same commit, and `test_reference_integrity.py` fails until it
happens.

## Already transcribed, pending registry entries

In `quantum_parity/edge_cases.py`, with harness citations:

`regime_category` · `resolve_race` · `bayes_rate` · `slope_clamp` ·
`intercept_clamp` · `fit_accepted` · `prob_clamp` · `macro_regime` ·
`safe_div` · `macro_need` · `cal_bin_*` · `cost_charged`

Three encode behaviour the audit classified as defective or lossy and are
reproduced deliberately — `safe_div`, `cost_charged`, `prob_clamp`. Their
registry entries must carry that in `assumptions`, cross-referenced to
`DIVERGENCE_REGISTER.md`.
