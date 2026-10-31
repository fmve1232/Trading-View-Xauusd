# 09 — Backtest and validation framework (specification, 2026-11-01)

This document governs every **new** strategy or model of the research programme. It does not change the live arms
or the forward test. Amendment 11/13's protocol is the legal frame; this is its technical specification.

## 1. Data partitions (Amendment 13; fixed blind)

| Partition | Dates (UTC) | Use |
|---|---|---|
| Development | 2020-01-24 02:00 → 2023-01-24 01:59 | exploration, feature work, model fitting, purged CV |
| Validation | 2023-01-24 → 2024-06-30 | **one** evaluation per registered variant |
| Sealed holdout | 2024-07-01 → 2025-12-31 | opened **once** per hypothesis that passed validation; final |
| Live | from registration | a new forward arm with its own freeze key |

The data is loaded only through `quantum.research.history.load()` (market-shut bars removed, D-R1). Bars in the
2026 forward window are never used for research.

## 2. Event definitions: one model per event (Part 10 of the brief)

Every target is defined before any fit:

```
E(k, h, side): starting at the close of bar i, does price reach entry + side·k·R before entry − side·1·R
               within h bars?
               R = adaptive ATR(i) × regime SL multiple(i), known at i.
Label: 1 = target first; 0 = stop first; AMBIGUOUS = both touched inside one bar (no ticks), excluded from fitting
       and reported; TIMEOUT = neither within h, reported separately.
```

**Registered grid** (small, on purpose): k ∈ {1, 2}, h ∈ {4, 16} bars, side ∈ {long, short}, TF ∈ {15m, 1h}.
That is 16 event models.

**Directional accuracy:** sign(close[i+h] − close[i]), h ∈ {4, 16}. Reported with the baseline rate of the same
window.

## 3. Validation mechanics

| Item | Specification |
|---|---|
| Walk-forward | expanding window inside development; 6 folds; refit per fold |
| Purging / embargo | drop training samples whose label window [i, i+h] overlaps the test fold; embargo = h bars after each test fold (R23) |
| CPCV | 6 groups, 2 test groups per split (15 paths), for PBO (R8) |
| Costs | session spread + 2 × slippage + commission per profile. **Gross and net reported separately.** News-window ×3 sensitivity. Swap per night held |
| Fills | entry at the signal bar's close; gap fills at the open (Amendment 14); AMBIGUOUS bars counted against the strategy in the net result (conservative) and listed |
| Sizing | separate from the signal: fixed 1R per trade for signal tests; vol-scaled variant reported separately (R4, R19) |
| Multiple testing | every configuration tried is logged (§6). White's Reality Check / SPA over the logged family (R6, R7); Benjamini-Hochberg FDR 10% when screening (R12) |
| Overfitting | PBO < 0.2 (R8); Deflated Sharpe > 0 at 95% (R9); t > 3 for a new family (R11) |
| Sensitivity | each parameter ±1 grid step: the sign of net expectancy must hold |
| Regime robustness | net expectancy reported per volatility tercile and per session; no tercile may be significantly negative |

## 4. Accuracy claims: precision requirements (Part 2 and Part 24 of the brief)

A claimed accuracy must have its 95% Wilson lower bound at or above the stated floor, and its coverage reported.

| Observed accuracy | Floor to claim | Resolved, independent events needed |
|---|---|---|
| 90% | ≥ 85% | **184** |
| 90% | ≥ 80% | 54 |
| 95% | ≥ 90% | 127 |
| 80% | ≥ 70% | 77 |
| 60% | > 50% (better than chance) | 91 |
| 55% | > 50% | 370 |

Small samples prove less than they appear to:

| Observed | Lower bound only |
|---|---|
| 9 / 10 | 59.6% |
| 18 / 20 | 69.9% |
| 45 / 50 | 78.6% |
| 90 / 100 | 82.6% |

**Coverage rule.** Every tier reports:

- n eligible;
- n taken (coverage = taken / eligible);
- accuracy with its interval;
- **net expectancy**;
- max drawdown.

A tier with high accuracy but negative expectancy is rejected.

## 5. Calibration (feeds `08`)

- Fit the calibration map (Platt or isotonic, R18) on the **last development fold only**. Evaluate on validation.
- **Report:** Brier, log loss, ECE (10 bins), maximum calibration error, calibration slope and intercept, a
  reliability diagram with per-bin n and Wilson bars, and AUC.
- **Rule:** a displayed probability must have a calibration slope with a 95% interval containing 1, and ECE < 5
  points, on validation. Otherwise the site shows a score, not a probability.

## 6. Trial registry (reproducibility)

`research/trials.jsonl`, append-only. One line per configuration evaluated, holding:

- time and git commit;
- data partition and hash;
- strategy id and parameters;
- event definition;
- n, gross R, net R, Sharpe, ECE;
- the verdict.

The number of trials enters the DSR and the PBO. **Nothing evaluated is ever deleted from it.**

## 7. Promotion path

```
development (purged CV)
  → registration (written, before validation)
  → one validation run
  → holdout opened once
  → new forward arm with its own freeze key and pre-registered decision rule
  → (after its N) a decision
```

The operator approves at registration and at promotion. **No step may be skipped**, including for a strategy that
"looks great".
