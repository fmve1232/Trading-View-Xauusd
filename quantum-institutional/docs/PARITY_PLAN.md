# Quantum 5.0 → Python parity plan

Master prompt §13, §59, §60. This is the **first implementation gate**. Nothing
downstream — SMC, probability, calibration, ML — is worth building until the
Python engine can reproduce what Pine computed.

## The claim we are trying to establish

> For identical historical XAUUSD bars, the Python engine produces the same
> engine outputs as Quantum 5.0, within a stated tolerance, on every bar.

Three words in that sentence do the work: **identical**, **stated**, **every**.

## What is already done

| Layer | Status | Where |
|---|---|---|
| Pine language semantics | **DONE, tested** | `src/quantum_institutional/pine/semantics.py` |
| Edge-case harness port (72 cases) | **DONE, tested** | `quantum_parity/edge_cases.py`, `tests/test_edge_case_parity.py` |
| Indicator parity | NOT STARTED | Phase 5–6 |
| Engine parity on bar data | NOT STARTED | Phase 6 |

### What the 72-case port actually proves

It proves the Python transcription agrees with the Pine **harness**. It does
**not** prove:

- that the Master is wired to those expressions — the harness says so itself;
- that the harness is right about the Master — F-A17 is exactly a case where it
  was not;
- anything at all about bar data.

It is a prerequisite, not the gate. The gate is below.

## The four Pine/Python divergences the semantics layer closes

Each is demonstrated from both sides in `tests/test_pine_semantics.py`. A direct
transcription that skips this layer is wrong in ways that do not raise.

| # | Expression | Pine | Python | Consequence if unhandled |
|---|---|---|---|---|
| 1 | `round(2.5)` | `3` | `2` (banker's) | Every exact `.5` boundary classifies differently |
| 2 | `max(5, na)` | `na` | `5.0` | A missing value becomes a real number, silently |
| 3 | `exp(250000)` | `inf` → sigmoid `0` | `OverflowError` | Crash on inputs Pine handles |
| 4 | `7 / 2` (ints) | `3` | `3.5` | Cannot be reproduced by transcription; must be explicit |

Divergence 2 is the dangerous one, because Python's `max` gives the *right*
answer for one argument order and the wrong one for the other. There is no
error, no warning, and no NaN downstream to notice later.

## The gate: Phase 6 parity on bar data

### Step 1 — export the reference series

Per `Trading-View-Xauusd/audit/RUNBOOK.md`. Export from the Master, on the exact
build hashed in `reference/quantum_5_0/MANIFEST.sha256`, at minimum:

`regimeCompositeRaw`, `regimeComposite`, `adaptiveATR`, `bullScore`, `bearScore`,
`liqReachScore`, `fEvBase`, calibrated probability, and the pre-filter and
trigger booleans.

Export the **bar timestamps** with them. Everything else depends on alignment.

### Step 2 — pin the input bars

Parity is only meaningful if both engines saw the same bars. TradingView's feed
is a specific broker's; a different XAUUSD feed differs in the fourth decimal and
at session edges. Export the OHLCV that TradingView used, store it with its own
`data_version`, and compute Python parity against **that**, not against a
separately sourced history.

This is the step most likely to be skipped and most likely to invalidate the
result.

### Step 3 — align

- Bar timestamps are UTC, left-aligned to the bar open (enforced by `contracts.py`).
- Compare only bars where **both** engines produce a value. Warm-up differs;
  Pine's `na` prefix is not a mismatch.
- Compare on **confirmed** bars only. `barstate.islast` values are recomputed
  intrabar and are not a stable target.

### Step 4 — tolerance

Declared in `configs/tolerances.yaml`, per output, before the first comparison
is run. Choosing a tolerance after seeing the mismatches is fitting the test to
the result.

| Output kind | Absolute | Relative | Why |
|---|---|---|---|
| Raw composites, scores | `1e-9` | `1e-12` | Pure float arithmetic; should be near-exact |
| ATR and EMA-based | — | `1e-6` | Recursive smoothing accumulates seed differences |
| Rounded ints, categories | `0` | — | Exact or it is a defect |
| Booleans (gates, triggers) | exact | — | Exact or it is a defect |

A recursive indicator never matches exactly unless the seed matches. Where Pine
seeds an EMA with an SMA of the first `n` bars, Python must do the same, and the
first `n` bars are excluded from the comparison.

### Step 5 — report

`QUANTUM_PARITY_REPORT`, generated, not written by hand. Per output:

bars compared · max absolute error · max relative error · first mismatch
timestamp · mismatch count · verdict.

**`NOT RUN` is the honest verdict for anything not executed.** Nothing may be
marked PASS that was not run — carried over from `CLAUDE.md`.

## Known deliberate divergences

These are cases where Python **will** differ from Pine, on purpose. Each must be
measured, not assumed small. See `DIVERGENCE_REGISTER.md`.

## Rule: reproduce first, improve second

Master prompt §1 and §13. Three of the ported expressions encode behaviour the
audit classified as defective or lossy — `safe_div`'s `== 0` guard, the timeout
accounting asymmetry, the `[0.05, 0.95]` probability clamp. They are reproduced
exactly.

Fixing them in Python before parity is established means the first parity run
compares a fixed engine against an unfixed one, and every mismatch has two
possible causes. Establish parity **with** the defects, measure their effect,
then change both arms deliberately.
