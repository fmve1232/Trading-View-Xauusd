# Target architecture

Companion to `CURRENT_STATE_AUDIT.md`. This document takes the "Cloud Quantitative Brain"
specification and fits it to two fixed constraints:

1. **The forward test must survive** until its decision date (`PREREGISTRATION.md` §7: 1H decides, N ≥ 50, decision by 2027-03-31).
2. **Nothing is tuned on this price history** (`AUDIT_PROMPT.md` §9).

## 1. What "nanosecond" means here

Every observation will carry `source_ts`, `received_ts`, `processed_ts` and `published_ts` as integer epoch nanoseconds. It will also carry `timestamp_precision`, which records what the *source* actually gave.

| Source | Actual precision | Actual update rate |
|---|---|---|
| Twelve Data bars | MINUTE (bar open) | one REST pull per 15-minute run |
| gold-api.com | as delivered in `updatedAt` | browser poll every 60 s |
| Finnhub via the relay | MILLISECOND | at most 4 messages/s (relay throttle) |
| OANDA stream (if connected) | as delivered in the RFC 3339 `time` (recorded, not assumed) | at most 4 prices/s per instrument (OANDA documentation) |
| MT5 `copy_ticks_*` (if connected) | MILLISECOND (`time_msc`) | every broker tick |

Zeros are never padded on to claim more precision. The dashboard shows the source precision, the measured latency (`received − source`) and the update rate as separate figures.

## 2. Two tracks over one data layer

```
                 ┌──────────────── DATA LAYER (shared, append-only, hashed) ────────────────┐
providers ──►  raw (as received) ──► validated (quality state per row) ──► canonical bars/ticks
                 └──────────────────────────────┬───────────────────────────────────────────┘
                                                │ the same bars, identified by content hash
                 ┌──────────────────────────────┴───────────────────────────────┐
     FROZEN ARM (quantum/, freeze key)                         RESEARCH TRACK (research/, no decisions)
     Treatment / Control / Challenger                          features registry · OOS calibration
     = the pre-registered forward test                         · AMBIGUOUS outcomes · ML candidates
     unchanged until 2027-03-31                                · regime/vol models · drift monitors
                 │                                                          │
                 └───────────────► report / site (labels which track every number came from)
```

- **The frozen arm keeps deciding.** The research track only *measures*.
- **A research model becomes a decision-maker only through a new pre-registration.** That means a frozen hash, a stated start date and a stated decision rule, the same path the Challenger took (hypothesis H1, pre-registered before the start).
- This is the champion/challenger governance of §80–81 and §117–118, applied to the one champion we already have.

## 3. Phases (ordered so that each one is useful alone)

| Phase | Deliverable | Spec | Touches the freeze key? | Needs from the operator |
|---|---|---|---|---|
| 1 | **Data versioning.** The workflow writes `manifest/<run>.json` (SHA-256 per store month file plus the row counts) to `forward-ledger` next to the ledger. A counted trade becomes traceable to its exact bars, and silent revisions become visible as hash changes. | §12, §19, §60 | No | — |
| 2 | **CI gates.** ruff; a forbidden-pattern test (no `Math.random`/`random` in `site/` or `quantum/data`, no literal prices); gitleaks; `pytest`. Any failure blocks the Pages deploy. | §104, §123, §152 | No | — |
| 3 | **Observation schema** (`research/schema.py`): `CanonicalTick` and `CanonicalBar` with `instrument_id`, `provider_id`, `market_type` (BROKER_CFD / REFERENCE / EXCHANGE_FUTURES / PROXY), the four timestamps plus precision, and a quality state. Adapters wrap the *existing* fetchers; nothing is re-downloaded differently. | §4, §5, §10, §13, §14 | No (it reads the store) | — |
| 4 | **Quality engine.** A numeric `DATA_QUALITY_SCORE` from freshness, completeness, duplicates/out-of-order, divergence against GC (premium-adjusted) and the reopen repairs applied. Published on the site's status bar. | §14, §58, §59 | No | — |
| 5 | **Research outcomes.** Re-score every frozen-arm signal with an explicit triple barrier, an AMBIGUOUS same-bar flag (resolved from 5m bars where they exist, else left AMBIGUOUS), MFE and MAE. The same-bar case is then reported as a count, not assumed. | §36, §37 | No (reads the frozen arm's signals) | — |
| 6 | **Out-of-sample calibration study.** Walk-forward Platt and isotonic fits on the analog score, with purge and embargo. Reported metrics: Brier, log loss, ECE/MCE, a reliability curve with bootstrap CIs, and the slope and intercept. *Measured* on history and *judged* only on post-freeze data. Nothing is tuned. | §41–§44 | No | — |
| 7 | **Volatility and regime study.** ATR vs EWMA vs GARCH(1,1), compared on out-of-sample forecast loss with `arch`. The regime labels are evaluated, not used. | §27, §34 | No | — |
| 8 | **Reference quotes with bid/ask.** *Either* OANDA v20 (an account token as a GitHub/Worker secret, pricing stream) *or* MT5 (`MetaTrader5` is a Windows-only package with the terminal running, so it needs the operator's PC or a Windows VPS pushing to the relay). This provides the observed spread, the divergence panel (§86) and the execution reference (§110). | §7, §8, §16, §86, §110 | No, while display/reference only | An account and a host |
| 9 | **Service layer.** FastAPI + Postgres (or Supabase) + WebSocket fan-out, *only if* phases 3–8 outgrow static JSON. Until then the Pages + Actions + Worker set-up is the cheapest design that meets §3 and §119. | §64, §65, §82 | No | A host and its cost |
| 10 | **ML candidate.** Only after phases 5–6 show what an honest target and calibration look like: a logistic baseline first, then gradient boosting only if it beats the baseline out of sample after costs. It goes in as a *new pre-registered arm*. | §38–§45, §117 | It becomes its own frozen arm | A pre-registration amendment |
| 11 | **Paper execution, then manual confirmation.** MT5 bridge with a kill switch and the §127 limits. Live execution only after the frozen-arm decision passes §7 *and* the paper results agree with the ledger. | §126–§128 | No | Broker account; written go-ahead |

## 4. Decisions only the operator can make

1. **The host for phases 8–9.** The options are: keep everything free (Actions + Pages + Cloudflare Worker, as now), add a small VPS, or use a managed Supabase/Fly.io.
2. **The execution broker.** Its contract specification (contract size, tick value, lot step, stop and freeze levels) drives the sizing in §111. No broker is assumed.
3. **Whether to connect OANDA and/or MT5.** Each needs an account and a credential that must be held only as a secret.

## 5. What will not be built, and why

- **Tick-by-tick "true CVD" for spot gold.** OTC spot has no central tape. True delta needs CME GC/MGC trade data with an aggressor side, which is a paid licence (§25, §109: REQUIRED PAID DATA).
- **Any claim of nanosecond market-data latency.** See §1.
- **Re-fitting thresholds, weights or the calibration of the frozen arm before 2027-03-31.**
