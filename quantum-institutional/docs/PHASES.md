# Phases and gates

Master prompt §80 and §81. A phase does not start until its predecessor passes
its gate. The gate is *executed tests*, not review.

| Phase | Scope | Status |
|---:|---|---|
| 0 | Repository, architecture, contracts, Pine semantics, CI | **DONE** |
| 1 | Quantum 5.0 code ingestion and full inventory | NOT STARTED |
| 2 | Formula registry, populated | NOT STARTED |
| 3 | Historical data ingestion | NOT STARTED |
| 4 | Data validation at scale | NOT STARTED |
| 5 | Python indicator engine | NOT STARTED |
| 6 | **Quantum 5.0 parity — the gate** | NOT STARTED |
| 7 | SMC / market structure | NOT STARTED |
| 8 | Statistical and regime engines | NOT STARTED |
| 9 | Probability engine | NOT STARTED |
| 10 | Calibration | NOT STARTED |
| 11 | Backtesting, cost model, signal engine | NOT STARTED |
| 12 | Walk-forward validation | NOT STARTED |
| 13 | ML | NOT STARTED |
| 14 | Macro / news pipelines | NOT STARTED |
| 15 | Live data | NOT STARTED |
| 16 | Risk engine | NOT STARTED |
| 17 | API, fully backed | NOT STARTED |
| 18 | Database, audit log, `/trace` | NOT STARTED |
| 19 | Realtime | NOT STARTED |
| 20 | Dashboard | NOT STARTED |
| 21 | CI/CD hardening, golden-dataset regression | NOT STARTED |
| 22 | Paper trading | NOT STARTED |
| 23 | MT5 bridge | NOT STARTED |

## Phase 0 — what was actually executed

Not claimed; run, with output.

| Gate | Result |
|---|---|
| Vendored artefacts match `MANIFEST.sha256` | **PASS** — 5/5, and the hash set is identical to the upstream audit manifest |
| Full test suite | **PASS** — 212 passed, 2 xfailed (strict) |
| 72-case edge harness port | **PASS** — 70 pass, 2 strict-xfail recorded as F-A18 |
| Pine/Python divergences demonstrated | **PASS** — all four, asserted from both sides |
| API returns no fabricated data | **PASS** — 14 pending routes, all `503 DATA_UNAVAILABLE` |
| Ruff lint | **PASS** — `All checks passed!` |
| Ruff format | **PASS** — 79 files already formatted |
| mypy (strict) | **PASS** — no issues in 35 source files |

Every row above was executed and its output recorded. Nothing is marked PASS on
the strength of having been written.

## Phase 6 — the gate that matters

Phase 6 does not pass on "the numbers look close". It passes when:

1. A tolerance was declared **before** the first comparison (`configs/tolerances.yaml`).
2. The parity input bars are TradingView's own exported OHLCV, pinned by `data_version`.
3. Every engine output in `PARITY_PLAN.md` step 1 has a row in the report.
4. Every mismatch is either inside tolerance or has an entry in
   `DIVERGENCE_REGISTER.md` written **before** the run.
5. Outputs that were not compared are marked `NOT RUN`, not omitted.

Phases 7 onward are blocked on this. Building a probability engine on an
unvalidated indicator layer means every later discrepancy has two possible
causes, and no way to separate them.
