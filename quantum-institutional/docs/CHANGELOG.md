# Changelog

## 0.1.0 — Phase 0

Initial repository. Quantum 5.0 becomes the reference layer; Python becomes the
quantitative core.

### Reference

- Vendored all five Quantum 5.0 Pine v6 artefacts (build v12, upstream commit
  `b5fd337`) read-only under `reference/quantum_5_0/`, with a re-derived
  `MANIFEST.sha256`. Hash set verified identical to the upstream audit manifest.
- CI verifies byte-identity before any other job runs.

### Pine parity

- `pine/semantics.py`: Pine v6 language semantics in Python, closing four
  divergences that are silent in a direct transcription — banker's rounding,
  order-dependent NaN in `max`/`min`, `math.exp` overflow, and integer division.
- `quantum_parity/edge_cases.py`: the Master expressions behind the edge-case
  harness, transcribed. Known defects reproduced, not fixed.
- All **72** harness assertions ported (§60).

### Findings raised

- **F-A17** (HIGH, `STAT`) — F-021 applied to regime classification but not to
  the `liqReachScore` bump at Master L2274 / Strategy L2218, which still
  thresholds the rounded composite and reaches expected value at 20% weight.
- **F-A18** (MEDIUM, `PRES`) — EdgeCases A3 and A6 carry pre-F-021 expected
  values; the harness reports `2 FAIL / 72` on TradingView.

Neither fixed here: the vendored Pine is read-only and both are behaviour
changes for the operator to decide. Both are pinned by tests.

### Engine

- Typed contracts with UTC enforced at construction.
- Point-in-time access with a raising lookahead tripwire (§30, §70–72).
- §12 validation; §11 deterministic aggregation refusing partial bars by default;
  §61 chunk planning with timestamp-based resume.
- Provider ABCs, no implementations, no stub data.
- `PAPER` execution mode by default; an unrecognised value raises.
- Version stamping; the git commit is read, never guessed.

### Platform

- FastAPI: `/health`, `/version`, `/system-status` real; the other 14 §46 routes
  return `503 DATA_UNAVAILABLE` naming their phase.
- PostgreSQL schema, 24 tables, versioning on every analytical row.
- GitHub Actions: reference integrity → lint, strict mypy, tests on 3.11/3.12,
  tracked-credential check.

### Tests

**212 passed, 2 xfailed (strict).**

### Not done

Everything from Phase 1. See `ACCEPTANCE.md` — 0 of 27 §86 criteria met.
