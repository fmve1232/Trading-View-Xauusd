# Current-state audit against the "Cloud Quantitative Brain" specification

Date: 2 Oct 2026. Code audited: branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4` at web.4
(PR #15, not yet merged), engine `Q7.2-web.4`, freeze key `5e4630924d663fc5:3252a9f0d312db75`.

**Method.**
- I read the source of `quantum/`, `site/app.js`, `relay/` and the workflows.
- I searched the repository for every pattern listed in §135 of the specification.
- Each verdict below cites the file and line it rests on.
- Nothing here is marked as passing unless it was executed or read. Where something was not checked, the verdict says **UNKNOWN**.

Verdicts use the specification's vocabulary:

| Verdict | Meaning |
|---|---|
| **KEEP** | Meets the specification. |
| **REFACTOR** | Right idea, wrong form. |
| **REPLACE** | Must be rebuilt. |
| **DELETE** | Must be removed. |
| **UNKNOWN** | Not verified. |

## 0. Two corrections before the detail

1. **The §135 "critical existing problems" describe the uploaded ZIP, not this repository.**

   I searched this repository for every listed pattern: `Math.random`, `Math.sin`, `Math.cos`, `4323`, `2707`, `mock`, `fake`, `demo price`, `fallback price`, and hard-coded probability, calibration, OOS and RR values. The only hits are these:

   | Hit | Where | Can it reach production? |
   |---|---|---|
   | `load_synthetic` (a seeded GBM generator) | `quantum/data/market.py:309` | **No.** It runs only with the `--synthetic` flag, which the workflow never passes (`quantum-site.yml:87`). A synthetic build has no store, so no ledger write (`pipeline.py:74`, `report.py:252`). It shows a red SYNTHETIC banner (`site/app.js:269`), and the alerts skip it (`notify.py:86`). |
   | Seeded bootstrap | `backtest.py:152` (`monte_carlo`) | No. It is labelled "i.i.d. bootstrap of trade R", which the specification allows (§99–100). |
   | `ta.nz(x, fallback=0.0)` | `ta.py:41` | No. This is Pine's `nz()`, a NaN default inside indicator maths, not a price. |

   There is no fabricated OANDA, COMEX, PAXG or XAUT quote. There is no `price ± constant` on any observed price, and no hard-coded calibration bin, win rate, R² or MTF alignment. **Verdict: KEEP.**

2. **The specification asks for things that the frozen forward test forbids.**

   `audit/PREREGISTRATION.md` §7 and Amendments 2–4 freeze the engine until the decision date (31 Mar 2027). The freeze key restarts the test on any change to `holdout.ENGINE_SOURCES` or `config.py`.

   §22–§56 of the specification ask for new models, retraining, new calibration, a new regime engine and new targets. These cannot be built *inside* the engine without restarting the test again. CLAUDE.md also forbids tuning on this history (`AUDIT_PROMPT.md` §9).

   The target architecture therefore keeps the frozen engine as the production forward test and builds the specification's research stack *beside* it (see `TARGET_ARCHITECTURE.md` §2). It does not rewrite the engine.

## 1. Data: sources, provenance, quality

| # | Spec | Finding | Evidence | Verdict |
|---|---|---|---|---|
| D1 | §1 never fabricate | No fabricated prices on any production path; synthetic data is isolated and labelled. | §0 above | KEEP |
| D2 | §4 separate instrument identities | **Partly met.** Spot (Twelve Data), GC=F futures, the gold-api chip and the Finnhub stream are separate series, each labelled with its source (`meta.price_source`, `volume_source`). There is no formal `instrument_id`/`provider_id` schema, and no PAXG, XAUT or MGC series. | `market.py:66-68,224-241`; `app.js:116,155` | REFACTOR |
| D3 | §4/§13 bid, ask, spread per observation | **Gap.** Twelve Data and Yahoo give mid/last OHLC only. The spread is a *modelled* session spread (`F["sess_spread"]`) used as a cost, not an observed one. | `backtest.py:27,57` | REPLACE when a broker feed exists (MT5/OANDA) |
| D4 | §10 timestamps (source / received / processed / precision) | **Gap.** Bars carry one open-time index. The live chip stores the source time (`updatedAt` or the stream's `t`), but no received/processed time and no stated precision. Twelve Data is minute-resolution, gold-api second-resolution, Finnhub millisecond. Nothing claims nanoseconds. | `app.js:131-136,192-195` | REFACTOR |
| D5 | §12 raw data never destroyed; §19 dataset versions | **Gap, the most important one in this section.** `store.merge` keeps the newer download on overlap, and the `market-data` branch is force-pushed as one orphan commit per run. A revised or repaired bar replaces the earlier one, and the earlier one is unrecoverable. The forward *ledger* is append-only on `forward-ledger` and never force-pushed, but the bars behind it are not versioned. | `store.py:38-43`; `quantum-site.yml:103-114` | REFACTOR (see §3 of the target architecture: a content-hash manifest per run, outside the freeze key) |
| D6 | §14 data-quality engine | **Partly met.** Implemented: closed-market bars dropped (`gold_shut`); off-grid snapshot rows dropped; the stale reopen print repaired (D-09/D-10); incomplete bars dropped; a per-series status record. Missing: crossed-quote checks (there are no quotes), duplicate/out-of-order counters, and a numeric quality score. | `sources.py:195-285`; `market.py` `SeriesStatus` | REFACTOR |
| D7 | §15 / §108 no false LIVE | **Met, with one bug fixed in this commit.** The chip goes to "stale" after 10 minutes, on a fetch error, or when the market is closed, and to "bad" when unavailable. The stream counts as live only within 90 s of the last tick. **Bug:** the browser's `marketClosed` still used the old Sunday-17:00 rule with no daily break, so during the 17:00–18:00 NY break the chip showed green on a repeated quote. Fixed here to match `sources.gold_shut`. | `app.js:119-123,154,191` | KEEP (fixed) |
| D8 | §16 / §87 multi-provider divergence; the "2707" guard | **Met for the live chip:** a tick more than 5% from the engine's last close is rejected and the reason is shown, not replaced. **Met offline:** `audit/tools/xcheck_dukascopy.py` compares spot with GC futures (premium removed per day, Spearman correlation, event tags) every week. **Gap:** there is no in-pipeline divergence check between two *spot* feeds, because only one spot bar feed exists. | `app.js:134,193`; `xcheck_dukascopy.py` | KEEP / extend when a second spot feed exists |
| D9 | §25 true order flow vs proxy | **Labelling bug, fixed in this commit.** The Overview card was titled "Order flow" with a "CVD" row. The value is GC futures volume signed by bar direction (`features.py:548`), which is a proxy. The card now reads "Volume (proxy, not order flow)" and names the volume source. The engine maths is unchanged. | `features.py:548`; `app.js` Overview | KEEP (relabelled) |
| D10 | §29 point-in-time macro | **Met for prices:** `market.align` takes the last bar that opened strictly before the chart bar's close. `test_no_lookahead` covers it. **Not applicable:** the engine uses no economic-release values. The calendar is display-only and outside the freeze key. | `market.py:75`; `tests/test_engine.py:191` | KEEP |
| D11 | §66 / §70 credentials server-side | **Met.** The Twelve Data key exists only as a GitHub secret and is redacted from error text. The Finnhub key exists only as a Worker secret, so the browser never sees a provider key. | `sources.py:41` `redact()`; `relay/README.md` | KEEP |

## 2. Engine: features, structure, probability, risk

| # | Spec | Finding | Evidence | Verdict |
|---|---|---|---|---|
| E1 | §21–§23 structure, SMC, liquidity | Implemented as explicit rules ported line for line from Pine v32: swings, BOS/CHOCH, FVG, OB, EQH/EQL, PDH/PDL/PWH/PWL/CDH/CDL on the NY 17:00 day. They are rule-based and testable, but individual events carry no `event_id` or calculation version. | `features.py`, `engine.py` | KEEP (add IDs in the trace layer, not in the engine) |
| E2 | §41–§43 score vs probability; calibration | **Honest, but not a validated calibration.** P is a Platt fit on the analog engine's *in-sample* rolling outcomes. It is clamped to 0.05–0.95 and then scaled by a heuristic regime ratio (`reg_adj`, clamped 0.67–1.5). The UI says "fitted in-sample" and states that the scores did not separate winners from losers (F-A34). A Brier score and reliability bins are computed from the backtest trades (`calibration_test`). There is no out-of-sample calibration, ECE, log loss or confidence interval. | `engine.py:1165-1195`; `backtest.py:164`; `app.js:321-323` | KEEP as the frozen arm's *reported* P; REPLACE for the research track (out-of-sample Platt/isotonic, ECE, log loss, CIs) |
| E3 | §140 no fake probability | **One display defect, fixed in this commit.** With zero matched analogs the engine keeps its placeholders (`wr=50`, `oos_wr=50`, `ev=0`; `analog.default_outputs`). The UI printed "50% · n0" as if it were a measurement. Statistics over zero observations now show "—". | `analog.py:28-33`; `app.js` `pctN` | KEEP (fixed) |
| E4 | §37 TP and SL in the same bar | **Conservative, not labelled.** A same-bar tie is scored as stop-first: the outcome is pessimistic but not flagged AMBIGUOUS. This is stated on the page and in the backtest docstring. Adding an `ambiguous` flag means editing `backtest.py`, which is inside the freeze key. | `backtest.py:4-6,36` | REFACTOR in the research track; leave the frozen arm |
| E5 | §46–§47 EV and costs | EV is charged with spread, slippage and commission; bid/ask-aware execution is impossible without quotes (D3). Swap and news widening are not modelled. | `backtest.py:57`; `engine.py` plan EV | REFACTOR (research) |
| E6 | §49–§50 Kelly | Kelly is used only for dashboard sizing: binary Kelly on the Wilson 95% lower bound at the effective N, halved, then cut for tail and drawdown. It is gated on the P being fitted. It sizes nothing automatically. | `report.py:48-87` | KEEP (display), with a note that P is not validated (E2) |
| E7 | §51 / §91 targets and RR | **Met.** Targets come from a structural hierarchy (PDH/PWH/PMH/EQH/OB/CDH/POC/VAH/mVWAP/round number) inside a distance band. An R-multiple is used only as a labelled fallback ("1R"/"+1R"). RR is computed, never hard-coded. | `engine.py:1600-1670` | KEEP |
| E8 | §38–§45 ML, ensembles | **None, deliberately.** The analog engine is a weighted nearest-neighbour count, not a fitted model. Adding ML to the decision would be a new arm under a new pre-registration. | `analog.py` | Build in the research track only |
| E9 | §40 / §77 walk-forward and significance | Walk-forward *measures* five time folds; it re-fits nothing, because the configuration is frozen. The ledger reports a t-statistic. The §7 decision uses the 95% t-interval and PF. Monte Carlo is an i.i.d. bootstrap, labelled as understating clustered tails. | `backtest.py:131-161`; `PREREGISTRATION.md` §7 | KEEP |
| E10 | §26 / §63 duplicate calculations | Indicators are centralised in `ta.py` and features in `features.py`. `audit/tools/deadcode.py` covers the Pine. **UNKNOWN** for Python: no dead-code pass has been run on `quantum/`. | — | UNKNOWN |

## 3. Platform, operations, traceability

| # | Spec | Finding | Verdict |
|---|---|---|---|
| P1 | §3 / §119 the frontend never computes authoritative numbers | **Met.** Every figure comes from `site/data/*.json` produced by the pipeline. The browser computes only: (1) the live-chip delta and the forming candle (display only, labelled); (2) the user's MT5 offset and account sizing. The offset is an opt-in constant added to *displayed* levels. It is default 0, labelled "(MT5 ±x)", and never applied to the live price. Under §1.1 it is a user conversion, not a fabricated price. | KEEP (keep the label) |
| P2 | §64 / §82 database, FastAPI, REST/WS API | **Not present.** The backend is a GitHub Actions batch job every 15 minutes that writes static JSON to Pages; the storage is CSV on a git branch. This is a cost/hosting decision, not an oversight: it costs nothing and needs no server. A FastAPI + Postgres service requires the operator to choose and pay for a host. | Decision for the operator (target §4) |
| P3 | §60 / §102 traceability | **Partly met.** Every payload carries the engine version, schema build, config hash and freeze key. Every ledger trade carries its price source and freeze key, and archives are kept on a restart (Amendment 4). Missing: a per-signal `signal_id` linked to its feature vector and to the raw bars' content hash (see D5). | REFACTOR |
| P4 | §103 versioning | **Met.** `ENGINE_VERSION`, `SCHEMA_BUILD`, config hash and code hash; the Pine artefacts are pinned in `MANIFEST.sha256`. | KEEP |
| P5 | §104 CI | **Partial.** `pytest` (75 tests, including `test_no_lookahead`) runs in the site workflow before every build (`quantum-site.yml:52`). There is no lint/type-check job, no secret scan in CI, and no randomness gate (§152). | REFACTOR (cheap; outside the freeze key) |
| P6 | §126–§128 execution | **None, by design.** The site produces a plan that the operator copies. Nothing places orders. | KEEP until the target-architecture gates pass |

## 4. Fixed in this commit (display only; the freeze key is unchanged)

1. The browser's market-closed rule now matches the pipeline's (Sunday reopen 18:00 NY, daily 17:00–18:00 break). The LIVE chip no longer shows green on the break's repeated quote. (D7)
2. Statistics over zero observations show "—" instead of the engine's 50% placeholders. (E3)
3. The "Order flow / CVD" card is relabelled as a volume proxy and names its source. (D9)

## 5. Open items, by priority

| Priority | Item | Inside the freeze key? |
|---|---|---|
| 1 | Version the market data (D5): a per-run manifest of month-file SHA-256 values, committed to `forward-ledger` with each ledger update, so every counted trade can be traced to the exact bars it was computed from. | No (workflow only) |
| 2 | CI job: ruff, a pattern gate for `Math.random`/`random(` in `site/` and the data paths, and gitleaks. | No |
| 3 | Research track: out-of-sample calibration (E2), AMBIGUOUS same-bar outcomes (E4), and quality scores (D6), run *beside* the frozen arm on the same bars. | No (new package; the frozen arm is untouched) |
| 4 | Broker or reference quotes with bid/ask (MT5 or OANDA) for D3/D4. This needs operator accounts and a host (target §4). | No, display/reference only until pre-registered |
| 5 | Any change to signals, calibration or data handling of the frozen arm. | **Yes: restarts the forward test.** Only through a pre-registration amendment. |
