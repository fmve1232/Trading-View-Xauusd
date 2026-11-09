# Phase D final report

**Status: INSUFFICIENT DATA — RESEARCH INCOMPLETE** (2026-11-09). No Dukascopy, MT5 or broker data has been received, so this document contains **no result**. Every figure will be filled from the committed outputs of the registered run (`registrations/PHASE_D.json`); nothing here is estimated, simulated or assumed. Synthetic data were used only to test the code and are not results.

## Current recommendation

**INSUFFICIENT DATA — RESEARCH INCOMPLETE.** Phase D's question, whether order flow or one-minute resolution adds a defensible edge to the ±$15 benchmark, cannot be answered without the data in `PHASE_D_DATA_REQUIREMENTS.md`.

**Until then:**
- Phase C's verdict stands: **NO QUALIFIED STRATEGY**.
- Quantum continues to report **NO TRADE** with the base rate.

## What has been completed (D0–D2)

**1. Phase C is frozen and unchanged.** 74 files are hash-pinned, and the first 3,808 lines of the trial log are pinned.

**2. Audit of the existing importers:**
- B5c's downloader could not run (critical; fixed in A3);
- B5c fetched sealed hours on one boundary day (fixed);
- twelve MT5-importer defects were fixed (`PHASE_D_PLAN.md` §2).

**3. Registration before any data.** `registrations/PHASE_D.json` fixes the hypotheses, data, alignment gates, ten feature families, labels, models, costs, tests and the C1–C6 acceptance criteria.

**4. Code, tested on synthetic data only:**
- the extractor (sealed-period guard, B5c-compatible);
- the order-flow features (no look-ahead);
- the one-minute bid / ask race (agrees with B26 exactly where 15 minutes is unambiguous);
- the study (finds a planted edge; finds nothing in two nulls);
- the broker validator (refuses assumed values);
- the hash-chained trial log;
- the one-command run.

## The decision rule (registered)

| Outcome | Condition |
|---|---|
| **QUALIFIES FOR FURTHER VALIDATION** | at least one strategy meets all of C1–C6, including 2026. Validation would then be opened once, only by an operator-approved amendment. |
| **NO QUALIFIED STRATEGY** | the data gates pass and nothing meets C1–C6 |
| **INSUFFICIENT DATA — RESEARCH INCOMPLETE** | a data gate fails, or 2026 order flow is unusable (C1 cannot be assessed) |

If no defensible edge exists, the recommendation stays NO TRADE. A profitable-looking backtest is not a substitute for these criteria.
