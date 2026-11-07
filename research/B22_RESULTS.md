# B22 and B23: every confirmation in calibrated machine-learning models; the raw-tail lead (2026-11-07)

**Registrations (committed before code):**
- `research/registrations/B22.json` (`4ec79159d`);
- `research/registrations/B23.json` (`fc77a5f28`).

**Code:**
- `quantum/research/b22.py`, `quantum/research/b23.py`;
- tests `tests/test_research_b22.py` (6) and `tests/test_research_b23.py` (2).

**Results:** `research/results/b22_development_2026-11-07.json`, `research/results/b23_validation_2026-11-07.json`.

**Trials:** 42 (B22) + 6 (B23).

## B22: the design

**Rows:** every 15m close of 2021-01 → 2023-01, out of sample, taken as a BUY and as a SELL.

**55 features from every confirmation family:**
- trend: EMA 20 / 100 / 200 and 1h / 4h / daily on closed bars;
- VWAP and Bollinger;
- RSI, MACD, returns;
- ATR and its rank;
- candle runs and wicks;
- structure recency, sweeps, liquidity grab / break;
- the engine's signal, scores and regime;
- day / week level distances and day-range position;
- time;
- a forward-filtered 3-state HMM regime and a CUSUM change-point statistic.

**Models:** logistic regression, Gaussian naive Bayes (Bayesian), random forest, histogram gradient boosting, XGBoost,
LightGBM and their ensemble. Each is tested raw, isotonic-calibrated and Platt-calibrated.

**Protocol:** quarterly purged walk-forward.

## B22 results at +$15 before −$13 (base rate 46.3%)

| Model (best calibration) | AUC | Log loss vs base | Top 5% success | Top 1% | Top 0.1% | Net / oz, top 5% |
|---|---|---|---|---|---|---|
| HGB + Platt (selected by the registered rule) | 0.498 | 0.6910 vs 0.6904 | 45.1% | 42.8% | 40.4% | −$1.25 |
| XGB + Platt | 0.504 | 0.6910 | 45.5% | 35.2% | 27.0% | −$1.14 |
| LightGBM + Platt | 0.496 | 0.6912 | 44.1% | 36.1% | 21.2% | −$1.54 |
| Ensemble + Platt | 0.498 | 0.6913 | 46.3% | 38.5% | 29.3% | −$0.92 |
| Random forest + Platt | 0.491 | 0.6917 | 43.4% | 37.6% | 36.4% | −$1.73 |
| Naive Bayes + Platt | 0.478 | 0.6922 | 44.5% | 42.8% | 41.1% | −$1.42 |
| Logistic + Platt | 0.489 | 0.6928 | 46.0% | 44.9% | 42.4% | −$1.00 |

**Across all models:**
- All 42 model / calibration combinations had AUC 0.47–0.51.
- **None beat simply quoting the base rate** on out-of-sample log loss.
- At +$20 (base 39.2%) the result is the same: AUC 0.47–0.51.
- **The selected model's top 5%** had a clustered 95% lower bound of 40.8%, against a 49.5% break-even. **FAIL**, so
  validation stays closed for B22.
- **The engine's own SIGNAL rows:** 46.8% of 47 at +$15 (95% 22–72%).

## Why 90% is out of reach: the arithmetic

- **The volatility:** gold's 15-minute volatility in 2020–22 was $4.07 at a $4,000 scale.
- **The required drift:** for a drifting random walk to hit +$15 before −$13 with probability p, price would need a
  **known** drift in the trade's direction of:

| Target success rate | Required drift, per hour | Per day |
|---|---|---|
| 46.4% (none: the geometry) | $0 | $0 |
| 50% | $0.34 | $8 |
| 60% | $1.31 | $31 |
| 70% | $2.37 | $57 |
| 80% | $3.69 | $88 |
| **90%** | **$5.69** | **$137** |

**What this means:**
- A 90% rule would have to know, at entry, a directional push of about $137 a day.
- Nothing in 1,186 recorded tests carries a detectable fraction of that out of sample. The largest effects found
  anywhere were a few tenths of a dollar per hour and did not survive independent data.

## B22 exploratory lead and B23 (its frozen test)

**The lead:**
- In development, the **raw** (uncalibrated) tree models' most confident predictions looked strong. The ensemble's
  top 0.5% reached 62.2% (471 rows), its top 0.1% 75.8% (149 rows), with causal thresholds.
- Calibration fitted on recent training slices reversed that ranking. That is a warning that the relation was unstable.

**B23** froze the rule and opened validation once:

| Ensemble raw, threshold from development | Development (walk-forward) | **Validation 2023-01 → 2024-07** |
|---|---|---|
| Top 0.1% | 75.8% of 149 | **38.1% of 155 (14 days)** |
| Top 0.5% (primary) | 62.2% of 471 | **52.8% of 394 (38 days), 95% 30.1–75.5%, net +$0.88** |
| Top 1% | 54.9% of 892 | **49.0% of 710 (81 days)** |
| Top 0.5% at +$20 | — | 38.4% (base 38.6%) |

**Outcome:**
- **FAIL:** the lower bound of 30.1% is below the 49.5% break-even. The development tail did not carry over.
- The holdout stays sealed, and the lead is closed under the registration.
