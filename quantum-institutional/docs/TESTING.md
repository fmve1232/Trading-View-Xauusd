# Testing

`make test`, or `python -m pytest`. CI runs it on 3.11 and 3.12.

Current: **212 passed, 2 xfailed**.

## Layout

| File | Covers |
|---|---|
| `test_pine_semantics.py` | The four Pine/Python divergences, asserted from both sides |
| `test_edge_case_parity.py` | All 72 Quantum 5.0 edge-case assertions, plus F-A17/F-A18 |
| `test_contracts.py` | UTC enforcement, OHLC invariants, quality propagation |
| `test_validation.py` | §12 checks |
| `test_aggregation.py` | §11 determinism, no-lookahead, volume-unit safety |
| `test_point_in_time.py` | §30/§70–72 leakage tripwires |
| `test_chunking.py` | §61 planning and resume |
| `test_safety.py` | Execution mode, version stamping, provider registry |
| `test_api.py` | §46 route list, 503 shape |
| `test_reference_integrity.py` | Vendored Pine still byte-identical |
| `test_packaging.py` | Every source file is tracked by git; no unanchored ignore rules |

## Conventions

**Assert both sides of a divergence.** A test that only asserts what Pine does
leaves the reader unable to tell whether the wrapper is needed, and someone will
delete it. `test_pine_semantics.py` asserts the Python behaviour too.

**`xfail_strict = true`.** A known-broken case that starts passing **fails the
build**. That is how F-A18 stays honest: if the Pine harness is corrected, CI
forces the port and the finding to be updated in the same commit.

**Synthetic fixtures are never parity baselines.** Everything in `conftest.py`
exercises code paths. It does not represent XAUUSD and must never be used to
establish parity — that comes from exported TradingView series
(`PARITY_PLAN.md`).

**Test the defect where the defect is the contract.**
`test_f021_is_not_closed_everywhere_in_the_master` asserts F-A17 **exists**. It
fails the day the Pine source is fixed, which forces the register to be closed
in the same commit instead of drifting.

**Reject, do not approximate.** Where a computation cannot be done correctly —
weekly aggregation without a session calendar, a non-multiple timeframe, a naive
datetime — the code raises and a test asserts the raise.

**Check what git will actually ship.** `.gitignore` carried an unanchored
`data/` rule, which also matched `src/quantum_institutional/data/` and dropped
the whole data package from the first commit. Every test passed locally because
the files were on disk; it would have been `ModuleNotFoundError` on the first
clone. `test_packaging.py` now asserts that every Python file on disk is tracked.

## Not covered yet

- Indicator parity on bar data — Phase 6, the gate.
- Golden-dataset regression — Phase 21; needs a validated engine first.
- Property-based testing — worth adding for `aggregation` and `pit` once
  `hypothesis` is a dependency.
- Load and latency — Phase 15.
