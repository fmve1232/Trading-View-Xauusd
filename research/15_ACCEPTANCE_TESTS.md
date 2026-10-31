# 15 — Acceptance tests (2026-11-01)

A strategy, model or displayed number is accepted only when every applicable test passes. **NOT RUN is reported as
NOT RUN.**

## A. Data and leakage

| ID | Test | Pass criterion |
|---|---|---|
| A1 | Source check | 100% of bars from the registered source; fallback bars excluded and counted |
| A2 | Market-shut bars | 0 shut-window bars after `load()` (D-R1 test) |
| A3 | Look-ahead | truncation test: features and labels at i identical with data cut at i+1 (as `test_no_lookahead`) |
| A4 | Label leakage | purge / embargo verified: no training label window overlaps a test fold (unit test on synthetic indices) |
| A5 | Point-in-time cross-assets | every cross-asset value timestamped ≤ the decision time |

## B. Outcome measurement

| ID | Test | Pass criterion |
|---|---|---|
| B1 | Hand-worked trades | exact P&L on long / short, TP / SL / BE / gap paths (as `test_backtest_gaps.py`) |
| B2 | Ambiguous bars | labelled AMBIGUOUS, counted, and charged as losses in the net result |
| B3 | Costs once | gross − net = modelled cost per trade, exactly |
| B4 | Gross and net | both reported for every result |

## C. Statistics

| ID | Test | Pass criterion |
|---|---|---|
| C1 | Sample size | n ≥ the `09` §4 requirement for any accuracy claim; n ≥ 100 trades for an expectancy claim |
| C2 | Expectancy | net mean R > 0 with t > 3 (a new family) on validation |
| C3 | Overfitting | PBO < 0.2; DSR > 0 at 95%; Reality Check p < 0.05 over all logged trials |
| C4 | Robustness | sign stable under ±1 parameter step, 2× costs, a 1-bar delay and each volatility tercile |
| C5 | Calibration | validation ECE < 5 points; calibration slope 95% interval contains 1; Brier skill > 0 |
| C6 | Coverage | each tier reports coverage, accuracy (Wilson), net R and drawdown |

## D. Promotion

| ID | Test | Pass criterion |
|---|---|---|
| D1 | Registration | written and approved before validation |
| D2 | Holdout | opened once; result recorded whatever it is |
| D3 | Forward arm | own freeze key; decision rule pre-registered; paper only |
| D4 | Display | the dashboard shows the numbers from the tests above, with n and intervals |

## E. Current status against these tests (2026-11-01)

| Item | A | B | C | D |
|---|---|---|---|---|
| H4 Playbook | pass | pass (B2 conservative stop first; 8 ambiguous trades) | **fail C2** (net −0.108 R, t −3.99) | forward test running as registered |
| Engine treatment / H5 / H6 | pass | pass | C1 not met (n ≤ 37) | forward running |
| Engine P (`cal_p`) | pass | — | **fail C5** (skill < 0) | displayed as a score only |
| Any new strategy | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
