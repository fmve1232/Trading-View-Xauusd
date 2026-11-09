# Phase D final report

**Status: INSUFFICIENT DATA — RESEARCH INCOMPLETE** (2026-11-09). No Dukascopy, MT5 or broker data has been received, so this document contains **no result**. Every figure will be filled from the committed outputs of the registered run (`registrations/PHASE_D.json`); nothing here is estimated, simulated or assumed. Synthetic data were used only to test the code and are not results.

## Current recommendation

**INSUFFICIENT DATA — RESEARCH INCOMPLETE.** Phase D's question, whether order flow or one-minute resolution adds a defensible edge to the ±$15 benchmark, cannot be answered without the data in `PHASE_D_DATA_REQUIREMENTS.md`.

**Until then:**
- Phase C's verdict stands: **NO QUALIFIED STRATEGY**.
- Quantum continues to report **NO TRADE** with the base rate.

## What has been run on real data (2026-11-09)

**Family D3-P (amendment A2): the price-only sets on Phase C's populations.**
- **Result: NO QUALIFIED STRATEGY.**
  - 0 of 32 strategies pass BH; the Reality Check gives p = 1.00.
  - Every strategy loses after costs: −$0.22 to −$1.38 per oz.
  - P(drawdown ≥ 15R in 250 trades) is 52–94%.
- **The probabilities are calibrated but carry no direction:** TP-vs-SL AUC is 0.48–0.50.
- **Volatility and structure make the tree models worse.**
- **The size of the next move is predictable, its direction is not.**
- **Audit:** the D4 audit passed all eight checks.
- **Details:** `PHASE_D_MODEL_COMPARISON.md`, `PHASE_D_APPENDIX_D3P.md`, `results/phase_d/d3p/`.

**Still not run:** order flow (B, D), intermarket (C), the one-minute measurements and the dynamic track. The order-flow and one-minute data are not reachable from this project's cloud environments:
- the session's network policy denies Dukascopy;
- Dukascopy refuses GitHub's runners.

The development period also has no intraday intermarket history.

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
- the one-command run;
- trade-level files for every strategy, the D4 audit tool and the generated appendix (amendment A1);
- timestamp verification beyond lag 0 (amendment A1).

## The decision rule (registered)

| Outcome | Condition |
|---|---|
| **QUALIFIES FOR FURTHER VALIDATION** | at least one strategy meets all of C1–C6, including 2026. Validation would then be opened once, only by an operator-approved amendment. |
| **NO QUALIFIED STRATEGY** | the data gates pass and nothing meets C1–C6 |
| **INSUFFICIENT DATA — RESEARCH INCOMPLETE** | a data gate fails, or 2026 order flow is unusable (C1 cannot be assessed) |

If no defensible edge exists, the recommendation stays NO TRADE. A profitable-looking backtest is not a substitute for these criteria.
