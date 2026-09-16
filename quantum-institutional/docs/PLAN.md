# Quantum Institutional — implementation plan

The §87 deliverable: the plan produced **before** large amounts of code, for
review. Phase 0 (this repository's scaffold) is built; everything from Phase 1
is proposed, not done.

---

## 1. Repository audit

Upstream: `fmve1232/Trading-View-Xauusd`, build **v12**, commit `b5fd337`.

| Artefact | Lines | Role |
|---|---:|---|
| `XAUUSD_Quantum_5_0_Master.pine` | 5 645 | Canonical live indicator. The only file traded from. |
| `XAUUSD_Quantum_5_0_Strategy.pine` | 5 002 | A/B **treatment** arm. Backtest only. |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` | 5 002 | A/B **control** arm. Backtest only. |
| `XAUUSD_Quantum_5_5_Visuals.pine` | 994 | Chart companion to the Master. |
| `XAUUSD_Quantum_5_0_EdgeCases.pine` | 301 | 72-assertion diagnostic. Not on the decision path. |

16 944 lines of Pine. Sixteen findings applied (F-A01…F-A16); **F-A16 open**
(short probability inherits the timeout rate). This repository adds **F-A17**
and **F-A18** — see `FINDINGS.md`.

Constraints inherited from `CLAUDE.md` and `audit/AUDIT_PROMPT.md` §9, and
binding here:

- **No tuning against this price history.** The IS/OOS boundary slides and the
  window already had parameters selected on it. The only real fix is a frozen
  holdout.
- **Strategy twins change identically** or the A/B breaks. The diff must stay at
  its five hunk headers.
- **Never mark PASS what was not executed.** `NOT RUN` is the honest verdict.
- **Static checks are not the compiler.** Three static passes gave false
  confidence in one session, including a syntax error introduced by a fix.

## 2. Quantum 5.0 architecture map

Pipeline as implemented in the Master:

```
inputs ──► regime block (L1891) ──► regimeCompositeRaw ──► strongTrend / moderateTrend
                                          └─ int(round(·)) ──► regimeComposite ──► liqReachScore bump (L2274)   [F-A17]
market structure ──► BOS / CHoCH / displacement ──► bullStructActive / bearStructActive
liquidity ──► pools, sweeps ──► liqDestLabel, liqDestScore ──► liqReachScore (L2278)
volume profile ──► VPOC / VAH / VAL (last-bar-only, marked basis)               [F-A07]
macro votes ──► macroNeed = ceil(pool / 2), pool 6 or 7                         [J-group]
                             │
  evidence composite ──► bullScore / bearScore ──► Platt sigmoid ──► calP ──► GATE   [F-A02, F-A15]
                             │
  analog population ──► SL/TP race ──► outcome ∈ {-1, 0, +1} ──► calibration bins
                             │
  fEvBase (liqReachScore × 0.20 among others, L4441) ──► EV ──► decision
```

Full inventory is Phase 1 output, not this document.

## 3. Proposed Python architecture

Layered, each layer depending only on those above it:

```
contracts + Pine semantics          (no dependencies)
  └─ validation, aggregation, PIT   (pure functions over contracts)
      └─ providers                  (I/O, behind ABCs)
          └─ indicators, SMC, statistics
              └─ features (store)
                  └─ regime, macro, news, fusion
                      └─ probability, calibration
                          └─ ML
                              └─ EV, risk, decision
                                  └─ API, realtime, dashboard
```

No engine imports a vendor SDK, a web framework, or a database driver. That is
what makes §5's "components can migrate" true rather than aspirational.

## 4. Data-source abstraction

`MarketDataProvider`, `NewsProvider`, `MacroProvider` ABCs
(`data/providers/base.py`), resolved by NAME through a registry. Built.

The contract that matters: **empty means "nothing there"; `DataUnavailable`
means "I could not look"**. A provider that conflates them makes an outage
indistinguishable from a quiet market.

No provider implementations ship. A stub returning plausible prices is
fabricated data (§83).

## 5. Database schema

24 tables, `migrations/0001_initial_schema.sql`. Built. See `DATABASE_SCHEMA.md`.

## 6. Formula registry design

Machine-readable, `formula_registry` table plus `FORMULA_REGISTRY.md`. One row
per `(formula_id, version)`, carrying the expression, its Pine reference, its
implementation file and its test status. Populated in Phase 2 by extraction from
the Pine source, reviewed by hand.

## 7. Engine dependency graph

As §3. The rule that makes it enforceable: a module may import only from layers
above it. Phase 21 adds an import-linter check to CI so a cycle fails the build
rather than being discovered during a refactor.

## 8. Quantum-to-Python parity plan

`PARITY_PLAN.md`. Semantics layer and 72-case port done; bar-data parity is the
Phase 6 gate.

## 9. Historical data plan

Chunked, resumable, checkpointed (`data/chunking.py`, built). Store the highest
reliable source resolution — 1m where available — and derive higher timeframes
deterministically (`data/aggregation.py`, built). Never load the full history
into memory.

For parity specifically: the TradingView-exported OHLCV is pinned as its own
`data_version` and is the parity input. See `PARITY_PLAN.md` step 2.

## 10. Live-data plan

Separate **batch compute** from **continuous stream processing** (§4). Scheduled
jobs handle bars and macro. A continuous XAUUSD stream needs a persistent
process; serverless functions are not suitable and the architecture must not
pretend otherwise.

Freshness budgets per feed class (`config.py`). Past budget, the feed is `STALE`
and cannot back a production signal (§41).

## 11. News/macro plan

The whole design is the three timestamps: `event_time`, `publication_time`,
`received_time`. Point-in-time queries filter on `publication_time` alone
(`data/pit.py`, built and tested against the §30 CPI-at-13:30 example).

Revisions are new rows, never updates. An in-place revision silently improves
every historical backtest and cannot be undone.

## 12–14. ML, probability, calibration architecture

Order is fixed and is not negotiable: **empirical → logistic → calibrated →
ensemble**. Start with the simplest model that can be beaten, and require every
increment to earn its place out of sample.

A score is not a probability. `P(TP before SL | features)` must be
distinguishable from "signal score = 72" — different type, different validation,
different failure mode.

Calibration is scored on Brier, log loss, reliability curve, ECE/MCE, slope and
intercept, with the calibration set held apart from the test set. **Never
calibrate on the final test set.**

Note the interaction with D-04: the live engine clamps reported probabilities to
`[0.05, 0.95]`, so calibration metrics must be computed on the **unclamped**
values and the clamp evaluated separately.

## 15. Backtesting architecture

Point-in-time by construction, cost model explicit and stored with every run
(`backtests.cost_model`), walk-forward with stored per-fold results. No
optimisation on the test period.

## 16. Risk architecture

Fixed-fractional and ATR sizing first. Kelly only on **validated, calibrated**
probabilities, fractional by default, never full. A clamped probability (D-04)
is not a calibrated probability for sizing purposes.

## 17. API architecture

FastAPI, §46 route list declared. Three endpoints real; the rest return
`503 DATA_UNAVAILABLE` naming their phase. Built. See `API_SPECIFICATION.md`.

`/trace` (§47) is the one that makes the rest auditable: signal → probability →
model → features → formulas → raw data → source → version. Phase 18.

## 18. Realtime architecture

Engine writes Postgres; Postgres change events drive the dashboard. The
dashboard **never** recomputes financial logic — §42. A number shown on the
dashboard and a number in the database that disagree is a bug with no correct
resolution.

## 19. Dashboard architecture

Information-dense, every value traceable to source/timestamp/formula/version/
quality. Phase 20.

## 20. GitHub CI/CD architecture

Built. Reference-integrity gate runs first and alone: if the vendored bytes
moved, nothing downstream is meaningful. Then lint, strict mypy, tests on 3.11
and 3.12, and a tracked-credential check.

## 21. Testing architecture

`TESTING.md`. Property-style tests over synthetic inputs for pure functions;
golden-dataset regression from Phase 11; parity as its own suite.

## 22. Security architecture

`SECURITY.md`. No secret has a default; no provider key reaches frontend JS;
`.env` is untrackable by CI check, not by convention.

## 23. Deployment architecture

Free-tier-first (§5), with the constraint stated honestly: a continuous market
stream is not free indefinitely. The provider abstraction is what makes a paid
feed a config change rather than a rewrite.

## 24. Phase-by-phase plan

`PHASES.md`.

## 25. Risks and limitations

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Parity is never established** | Everything downstream rests on it | Phase 6 is a hard gate; `NOT RUN` is a permitted verdict |
| **The window is already contaminated** | Parameters were selected on this history | No tuning (§9); a frozen holdout is the only real fix |
| **Feed mismatch invalidates parity** | TradingView's broker feed is not a generic XAUUSD feed | Pin TradingView's exported OHLCV as the parity input (D-08) |
| **Free tier cannot carry live data** | "Everything at zero cost" is not honestly promisable | Provider abstraction; state the cost when it arrives |
| **Static checks give false confidence** | Already happened three times upstream | CI runs tests, not just linters; Pine still needs the TradingView compiler |
| **Scope** | 88 sections is more than one system | Phase gates; nothing starts before its predecessor passes |

## 26. Files created

This repository. See `git log`.

## 27. Files modified

None upstream. `Trading-View-Xauusd` gains one handoff document; no artefact is
touched.

## 28. Files that must remain untouched

`reference/quantum_5_0/*.pine` — all five, byte-identical, enforced by
`scripts/verify_reference.py` in CI. The parity plan, every line citation and
every finding is written against these exact bytes.

## 29. Acceptance criteria

`ACCEPTANCE.md`, per phase, with the §86 final checklist. Honest: everything
unticked except what has actually been executed.
