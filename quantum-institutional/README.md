# Quantum Institutional

Python quantitative research platform for XAUUSD.

**Quantum 5.0 (Pine v6) is the reference layer, not the thing being replaced.**
Python becomes the quantitative source of truth only once it can reproduce what
Pine computed. That is a gate, not a formality — see
[`docs/PARITY_PLAN.md`](docs/PARITY_PLAN.md).

---

## Status: Phase 0 of 23

What exists is a scaffold with real, tested foundations and **no quant engine
yet**. Nothing here produces a trading signal, and nothing is connected to a
market.

| | |
|---|---|
| Tests | **212 passed, 2 xfailed (strict)** |
| §86 acceptance | **0 of 27** — [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) |
| API | 3 of 17 endpoints real; 14 return `503 DATA_UNAVAILABLE` |
| Quantum 5.0 parity | **NOT ESTABLISHED** — Phase 6 |

That table is the point. Every unticked box is the honest state.

## What is actually built

**The Pine semantics layer.** Pine v6 and Python disagree in four ways that are
silent — both return a number, the numbers differ, nothing raises:

| Expression | Pine | Python | If unhandled |
|---|---|---|---|
| `round(2.5)` | `3` | `2` (banker's) | every exact `.5` boundary classifies differently |
| `max(5, na)` | `na` | `5.0` | a missing value becomes a real number |
| `exp(250000)` | `inf` → sigmoid `0` | `OverflowError` | crash on input Pine handles |
| `7 / 2` (ints) | `3` | `3.5` | cannot be reproduced by transcription at all |

The second is the dangerous one: Python's `max` is right for one argument order
and wrong for the other. Each is demonstrated from both sides in
`tests/test_pine_semantics.py`.

**All 72 Quantum 5.0 edge-case assertions, ported** (§60). Known defects are
reproduced, not fixed — see [`docs/DIVERGENCE_REGISTER.md`](docs/DIVERGENCE_REGISTER.md).

**Point-in-time access** with a raising lookahead tripwire, tested against the
§30 CPI-at-13:30-UTC example. Revisions are new records; the original release is
what a historical query returns.

**Typed contracts** enforcing UTC at construction, `Quality` that takes the worst
of its inputs, and volume that carries its type so tick counts are never summed
with exchange contracts.

**Deterministic aggregation** that drops partial buckets by default and refuses
weekly aggregation rather than silently anchoring the week to a Thursday.

**24-table PostgreSQL schema** with version stamping on every analytical row, and
`CHECK` constraints for the invariants that matter — including
`p_win IS NOT NULL OR unavailable_reason IS NOT NULL`.

## Two findings this work produced

Porting the harness faithfully turned the suite red, which is the port earning
its place.

- **F-A17** (HIGH) — F-021 moved regime *classification* onto the unrounded
  composite but left the liquidity-reach score bump at Master L2274 thresholding
  the **rounded** one. A raw composite of `69.50` is moderate for classification
  and strong for scoring, in the same bar. It reaches expected value at 20%
  weight, in all three arms.
- **F-A18** (MEDIUM) — EdgeCases A3 and A6 still carry pre-F-021 expected values,
  so the harness reports `2 FAIL / 72` on TradingView.

Neither is fixed here: the vendored Pine is read-only, and both are behaviour
changes to a live trading script. Both are pinned by tests that fail if the
source is fixed without closing the finding. Detail and proposed patches:
[`docs/FINDINGS.md`](docs/FINDINGS.md).

## Quick start

```sh
make install
make verify     # vendored Quantum 5.0 artefacts are byte-identical
make all        # verify + lint + typecheck + test
make api        # http://localhost:8000/docs
```

## Layout

| Path | What |
|---|---|
| `src/quantum_institutional/` | The package. Engine layers are empty until their phase. |
| `quantum_parity/` | Quantum 5.0 expressions transcribed for parity |
| `reference/quantum_5_0/` | The five Pine artefacts, **read-only**, hash-pinned |
| `migrations/` | PostgreSQL schema |
| `data_contracts/` | JSON Schema for records crossing a boundary |
| `docs/` | Plan, architecture, specifications, findings |
| `tests/` | 212 tests |

## Rules carried from the audit

Binding here, not aspirational:

- **No tuning against this price history.** Parameters were already selected on
  this window and the IS/OOS boundary slides. The only real fix is a frozen
  holdout.
- **Reproduce before improving.** A Python "fix" applied before parity means the
  first parity run compares a fixed engine to an unfixed one, and every mismatch
  has two possible causes.
- **Never mark PASS what was not executed.** `NOT RUN` is the honest verdict.
- **Never fabricate.** No stub providers, no placeholder prices, no default
  substituted for a missing value. Unavailable data returns
  `DATA_UNAVAILABLE` with a reason.
- **Static checks are not the compiler.** CI runs tests, not just linters. Pine
  still needs TradingView.

## Reading order

1. [`docs/PLAN.md`](docs/PLAN.md) — the §87 plan
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
3. [`docs/PARITY_PLAN.md`](docs/PARITY_PLAN.md) — the Phase 6 gate
4. [`docs/FINDINGS.md`](docs/FINDINGS.md)
5. [`docs/PHASES.md`](docs/PHASES.md) and [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)

## Upstream

[`fmve1232/Trading-View-Xauusd`](https://github.com/fmve1232/Trading-View-Xauusd)
— the Pine artefacts and their audit (F-A01…F-A16).
