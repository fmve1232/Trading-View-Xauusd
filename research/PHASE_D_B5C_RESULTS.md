# Phase D Workstream A: order flow on Dukascopy top of book (B5c data)

**Status: INSUFFICIENT DATA — RESEARCH INCOMPLETE** (2026-11-09). No Dukascopy data has been received, so this document contains **no result**. Every figure will be filled from the committed outputs of the registered run (`registrations/PHASE_D.json`); nothing here is estimated, simulated or assumed. Synthetic data were used only to test the code and are not results.

## What will be here

**1. Data integrity, per period.** From `data_report.json`, for development and 2026 separately:
- the price scale and basis;
- the lag correlations at −2..+2 bars, overall, by session and by year, with the best lag;
- weekly open / close edges;
- missing, duplicate-ms, crossed, out-of-hour and stale ticks;
- quarantined days;
- the order-flow coverage of the scored bars;
- Phase D amendment A1: lags per ISO week, the minute-offset check, the MT5 cross-check if supplied, and ticks with backwards timestamps.

Any gate failure is reported here and stops the study.

**2. B5c as registered** (`registrations/B5C.json`, 33 trials, the −$10 stop). Run by `py -m quantum.research.b5c_dukascopy` on the same cache and reported separately.

**3. The ten order-flow families.** Per family:
- the out-of-sample information each adds over Baseline on the ±$15 benchmark;
- incremental log-loss per New York day with a 95% interval;
- AUC (TP vs rest, and TP vs SL on decided trades only);
- Brier and ECE.

Each family's feature list is in `d_features.FAMILIES_OF`.

**4. The predictive questions:**
- P(BUY TP first) and P(SELL TP first);
- P(neither);
- P(favourable $5 / $10 / $15 / $20 within 4 h);
- P(adverse $X before favourable $X);
- the time to TP / SL by quintile of P(TP);
- the value of delaying an entry by one bar, with or against the order flow.

All of these are descriptive.

**5. The order-flow-informed ±$15 strategies** (sets B and D) and their C1–C6 status. Summary only; the full table is in `PHASE_D_MODEL_COMPARISON.md`.

## What the source can and cannot show

**What it is.** Dukascopy SWFX best bid / best offer and the volume displayed at each, at every change.

**What it is not:**
- order-book depth;
- traded volume;
- the side of a trade;
- COMEX.

A Dukascopy quote imbalance is one venue's displayed liquidity, so a positive result would still need an independent venue before any claim about "institutional" flow.
