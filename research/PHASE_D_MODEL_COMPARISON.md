# Phase D Workstreams D and E: incremental value of Baseline / A / B / C / D

**Status: PARTIAL.** The price-only family D3-P is done (NO QUALIFIED STRATEGY, below). The order-flow sets (B, D) and intermarket (C) are INSUFFICIENT DATA — RESEARCH INCOMPLETE (2026-11-09). No Dukascopy data has been received, so this document contains **no result**. Every figure will be filled from the committed outputs of the registered run (`registrations/PHASE_D.json`); nothing here is estimated, simulated or assumed. Synthetic data were used only to test the code and are not results.

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

## Results so far: family D3-P (price-only sets, amendment A2; run 2026-11-09 on real data)

**Source:** `results/phase_d/d3p/` (`study.json` SHA-256 `7eeaa0dff07b…`). Full tables: `PHASE_D_APPENDIX_D3P.md`, generated from those files after the D4 audit passed on all eight checks (`results/phase_d/d3p/audit_d4.json`). Every figure below is copied from those files.

**Verdict: NO QUALIFIED STRATEGY** for the price-only sets. None of the 32 strategies passes BH at q = 0.10, and the family's Reality Check gives p = 1.00. Nothing reached the frozen set, so 2026 was not scored. This answers H-D3 only; order flow (H-D1, H-D2) is still untested.

**What the numbers say:**
- Every strategy loses after costs: expectancy -1.38 to -0.22 $/oz, profit factor 0.83–0.97.
- The least bad is BASELINE/LR/Q05: 2275 trades, TP-first 49.8% (95% 47.7–51.9%) against matched random 47.6%, expectancy -0.22 $/oz.
- P(drawdown ≥ 15R within 250 trades) is 52%–94% across the 32 strategies (C6 requires ≤ 5%).
- A higher TP-first rate than random does not make a strategy profitable here. The best p-values (A/GB/EV0 p = 0.011, A/LGBM/EV0 p = 0.015) belong to losing strategies, and neither survives BH.

**Probability quality (out of sample, 94,235 development rows):**

| Set / algorithm | Log-loss | Brier | AUC TP vs rest | AUC TP vs SL (decided) | Mean P(TP) | Observed TP |
|---|---|---|---|---|---|---|
| BASELINE/LR | 0.8440 | 0.5398 | 0.521 | 0.486 | 45.0% | 45.0% |
| BASELINE/RF | 0.8045 | 0.5274 | 0.523 | 0.492 | 45.1% | 45.0% |
| BASELINE/LGBM | 0.7959 | 0.5292 | 0.534 | 0.499 | 45.0% | 45.0% |
| BASELINE/GB | 0.7937 | 0.5277 | 0.534 | 0.498 | 45.0% | 45.0% |
| A/LR | 0.8461 | 0.5478 | 0.514 | 0.479 | 44.7% | 45.0% |
| A/RF | 0.8159 | 0.5354 | 0.521 | 0.491 | 45.2% | 45.0% |
| A/LGBM | 0.8078 | 0.5364 | 0.531 | 0.497 | 45.3% | 45.0% |
| A/GB | 0.8101 | 0.5374 | 0.532 | 0.499 | 45.3% | 45.0% |

- **Calibrated, but no direction.** The probabilities are well calibrated on average (predicted ≈ observed). TP-vs-SL AUC on decided trades is 0.48–0.50, i.e. no directional information.
- **The 0.52–0.53 TP-vs-rest AUC is the calendar effect Phase C found.** Closures and timeouts are predictable; direction is not.

**Incremental value of A over Baseline** (daily log-loss gain, positive = better):

- A/LR: +0.0007 (95% -0.0090 … +0.0104), p (Holm over algorithms) 1.00
- A/RF: -0.0109 (95% -0.0165 … -0.0051), p (Holm over algorithms) 1.00
- A/LGBM: -0.0113 (95% -0.0203 … -0.0022), p (Holm over algorithms) 1.00
- A/GB: -0.0154 (95% -0.0251 … -0.0055), p (Holm over algorithms) 1.00

Volatility and structure features make the tree models' predictions **worse** out of sample (overfitting) and leave LR unchanged.

**Descriptive questions (BASELINE / A, LR / LightGBM):**

- FAV5: base rate 62.4%, AUC 0.613–0.633 (15 minutes (exact: no race))
- FAV10: base rate 37.9%, AUC 0.655–0.679 (15 minutes (exact: no race))
- FAV15: base rate 23.1%, AUC 0.689–0.717 (15 minutes (exact: no race))
- FAV20: base rate 14.3%, AUC 0.712–0.747 (15 minutes (exact: no race))
- ADV_FIRST5: base rate 43.0%, AUC 0.511–0.518 (15 minutes (worst case), AMBIGUOUS 1.5%)
- ADV_FIRST10: base rate 45.3%, AUC 0.508–0.527 (15 minutes (worst case), AMBIGUOUS 0.4%)
- ADV_FIRST15: base rate 45.0%, AUC 0.514–0.534 (15 minutes (worst case), AMBIGUOUS 0.2%)
- ADV_FIRST20: base rate 44.0%, AUC 0.520–0.547 (15 minutes (worst case), AMBIGUOUS 0.1%)

**Reading the FAV results.** A favourable $5–$20 move within 4 hours is predictable (AUC up to 0.75), but the race on the same rows (adverse first vs favourable first) stays at 0.51–0.55. The models know **how far** price will move (volatility: session, recent range), not **which way**. A move of that size is equally likely to come in the trade's favour or against it, so it cannot pay a ±$15 bracket. It is not an edge.

The delay question needs order flow and was not run.
