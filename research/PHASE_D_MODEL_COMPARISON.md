# Phase D Workstreams D and E: incremental value of Baseline / A / B / C / D

**Status: INSUFFICIENT DATA — RESEARCH INCOMPLETE** (2026-11-09). No Dukascopy data has been received, so this document contains **no result**. Every figure will be filled from the committed outputs of the registered run (`registrations/PHASE_D.json`); nothing here is estimated, simulated or assumed. Synthetic data were used only to test the code and are not results.

## Registered design (fixed before data)

**Sets:**

| Set | Inputs |
|---|---|
| Baseline | B27 TIME_NEWS + MOMENTUM features |
| A | Baseline + VOLATILITY, TREND, STRUCTURE_SMC, LIQUIDITY |
| B | Baseline + the ten order-flow families |
| C | Baseline + intermarket (only if Dukascopy serves the instruments; otherwise NOT RUN) |
| D | A + B + C |

**Algorithms:** LR, RF, LightGBM and GB (sklearn HistGradientBoosting), with b22's settings and no search.

**Output:** multinomial P(TP), P(SL), P(neither), summing to 1. A per-fit temperature comes from the training window's own last 20%.

**Walk-forward:** quarterly from 2021-01-01, with a one-day exit purge. The folds and rows are identical across sets and algorithms. Final models are refit once and applied once to 2026.

**Rules:**
- EV0: E[net] > 0;
- top 10 / 5 / 2% of E[net] (thresholds from the training window);
- one position per direction.

## Tables that will be here

**1. Probability quality.** Per set × algorithm:
- rows;
- log-loss and Brier;
- AUC TP-vs-rest and TP-vs-SL (decided);
- ECE per class;
- mean predicted vs observed;
- the reliability of P(TP) with Wilson intervals.

**2. Incremental value.** Per set vs Baseline (same algorithm):
- the daily log-loss gain and its 95% interval;
- the one-sided p;
- the AUCs side by side.

A higher AUC alone is **not** reported as value.

**3. Strategies.** Every (set, algorithm, rule):
- independent trades;
- decided TP-first with a 95% interval, against matched random and break-even;
- net expectancy $ / oz (ENG);
- PF and max drawdown;
- trades per week;
- p against random, BH (q = 0.10), the family's Reality Check;
- by year, volatility tercile and trend;
- minutes to TP / SL;
- P(drawdown ≥ 15R in 250).

**4. The frozen set on 2026.** Every development-frozen strategy applied once to 2026, with Holm p.

**5. C1–C6 per strategy and the verdict.**

**6. The dynamic TP / SL family** (ATR 1.0 / 1.0, 1.5 / 1.0, 1.0 / 1.5), in its own table and family.

## Prior evidence

Phase C's models reached AUC 0.52–0.53, and that came from weekday / hour (weekend closures), not direction. The synthetic null tests reproduce this effect: time-of-week inflates TP-vs-rest AUC while TP-vs-SL stays near 0.5. That is why both are reported.
