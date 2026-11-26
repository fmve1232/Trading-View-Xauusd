# Strategy performance report (2026-11-26)

**Finding: trading-performance evidence is INSUFFICIENT, and where it is large enough it is negative.**
- **No arm has a mean R per trade whose 95% interval lies above zero.**
- **Two H4 Playbook ledgers are reliably negative:**
  - 5m: 410 trades, −0.138 R; day-clustered 95% interval −0.209 to −0.064.
  - 1h: 37 trades, −0.308 R; day-clustered interval −0.418 to −0.205.
- **No registered forward look has been reached** (`FORWARD_TEST_STATUS.md`).
- **These are simulated fills at feed prices** under the model cost. No broker fill or account statement has been compared (GA-28).

**Source**
- `audit/tools/forward_report.py` (remediation branch) on `forward-ledger` `c8a99d64e` (2026-11-26 11:04 UTC) and the stored 5m bars (2026-09-09 → 2026-11-26 11:00 UTC).
- Trades are closed ones under the current freeze key, entered after 2026-11-15 11:46:48 UTC.
- Bootstrap: 10,000 resamples, seed 20261126.
- Full output: `evidence/forward_report_2026-11-26.json`.
- Every ledger is a separate test, so with about 10 ledgers of 5 or more trades, one "significant" result in either direction is expected by chance.

## 1. Results per arm and timeframe

- **R:** net points / stop distance; 1 R is the planned loss.
- **Win:** net points > 0.
- **PF:** profit factor.
- **95% (trades):** trade-level bootstrap interval.
- **95% (days):** day-clustered interval, where trades of one UTC day are resampled together.
- **Losing streak:** the longest run of losses.
- Ledgers with fewer than 5 trades get no interval.

| Ledger | Trades | Wins / losses | Win % (Wilson 95%) | Avg win / loss (R) | PF | Mean R | 95% (trades) | 95% (days) | Sum R | Max DD (R) | Losing streak | Worst R | Share < −1 R | Hold (min) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5m_treatment | 17 | 6 / 11 | 35.3 (17.3–58.7) | +1.433 / -1.112 | 0.703 | -0.214 | -0.796 to +0.453 | -0.884 to +0.598 | -3.64 | 6.83 | 5 | -1.181 | 64.7% | 288.2 |
| 15m_treatment | 6 | 3 / 3 | 50.0 (18.8–81.2) | +1.069 / -1.046 | 1.022 | +0.012 | -0.734 to +0.809 | — | +0.07 | 2.30 | 2 | -1.056 | 50.0% | 642.5 |
| 30m_treatment | 3 | 0 / 3 | 0.0 (0.0–56.1) | — / -1.039 | 0.0 | -1.039 | — | — | -3.12 | 3.12 | 3 | -1.061 | 100.0% | 1190.0 |
| 1h_treatment | 4 | 2 / 2 | 50.0 (15.0–85.0) | +1.334 / -1.019 | 1.309 | +0.157 | — | — | +0.63 | 1.03 | 1 | -1.028 | 50.0% | 180.0 |
| 4h_treatment | 1 | 1 / 0 | 100.0 (20.6–100.0) | +1.487 / — | — | +1.487 | — | — | +1.49 | 0.00 | 0 | +1.487 | 0.0% | 1920.0 |
| 5m_challenger | 13 | 6 / 7 | 46.2 (23.2–70.9) | +1.513 / -1.113 | 1.165 | +0.099 | -0.678 to +0.961 | -0.782 to +1.224 | +1.29 | 4.49 | 4 | -1.181 | 53.8% | 380.0 |
| 15m_challenger | 6 | 3 / 3 | 50.0 (18.8–81.2) | +1.069 / -1.046 | 1.022 | +0.012 | -0.733 to +0.836 | — | +0.07 | 2.30 | 2 | -1.056 | 50.0% | 642.5 |
| 30m_challenger | 3 | 0 / 3 | 0.0 (0.0–56.1) | — / -1.039 | 0.0 | -1.039 | — | — | -3.12 | 3.12 | 3 | -1.061 | 100.0% | 1190.0 |
| 1h_challenger | 4 | 2 / 2 | 50.0 (15.0–85.0) | +1.334 / -1.019 | 1.309 | +0.157 | — | — | +0.63 | 1.03 | 1 | -1.028 | 50.0% | 180.0 |
| 4h_challenger | 1 | 1 / 0 | 100.0 (20.6–100.0) | +1.487 / — | — | +1.487 | — | — | +1.49 | 0.00 | 0 | +1.487 | 0.0% | 1920.0 |
| 5m_control | 2 | 1 / 1 | 50.0 (9.4–90.5) | +1.825 / -1.018 | 1.793 | +0.404 | — | — | +0.81 | 1.02 | 1 | -1.018 | 50.0% | 67.5 |
| 15m_control | 1 | 0 / 1 | 0.0 (0.0–79.3) | — / -1.036 | 0.0 | -1.036 | — | — | -1.04 | 1.04 | 1 | -1.036 | 100.0% | 45.0 |
| 30m_control | 2 | 0 / 2 | 0.0 (0.0–65.8) | — / -1.612 | 0.0 | -1.612 | — | — | -3.23 | 3.23 | 2 | -2.183 | 100.0% | 1605.0 |
| 1h_control | 1 | 1 / 0 | 100.0 (20.6–100.0) | +1.385 / — | — | +1.385 | — | — | +1.39 | 0.00 | 0 | +1.385 | 0.0% | 360.0 |
| 5m_h2 | 4 | 1 / 3 | 25.0 (4.6–69.9) | +1.091 / -1.035 | 0.352 | -0.503 | — | — | -2.01 | 2.07 | 2 | -1.053 | 75.0% | 345.0 |
| 30m_h2 | 1 | 0 / 1 | 0.0 (0.0–79.3) | — / -1.040 | 0.0 | -1.040 | — | — | -1.04 | 1.04 | 1 | -1.040 | 100.0% | 360.0 |
| 5m_h3 | 8 | 4 / 4 | 50.0 (21.5–78.5) | +2.896 / -1.166 | 2.485 | +0.865 | -0.645 to +2.677 | -0.624 to +2.756 | +6.92 | 2.36 | 2 | -1.195 | 50.0% | 102.5 |
| 15m_h3 | 3 | 0 / 3 | 0.0 (0.0–56.1) | — / -1.081 | 0.0 | -1.081 | — | — | -3.24 | 3.24 | 3 | -1.099 | 100.0% | 40.0 |
| 30m_h3 | 1 | 0 / 1 | 0.0 (0.0–79.3) | — / -1.048 | 0.0 | -1.048 | — | — | -1.05 | 1.05 | 1 | -1.048 | 100.0% | 120.0 |
| 1h_h3 | 1 | 0 / 1 | 0.0 (0.0–79.3) | — / -1.036 | 0.0 | -1.036 | — | — | -1.04 | 1.04 | 1 | -1.036 | 100.0% | 360.0 |
| 5m_h4 | 410 | 142 / 268 | 34.6 (30.2–39.4) | +0.731 / -0.598 | 0.647 | -0.138 | -0.213 to -0.059 | -0.209 to -0.064 | -56.62 | 59.61 | 14 | -1.251 | 14.6% | 33.0 |
| 15m_h4 | 148 | 60 / 87 | 40.5 (33.0–48.6) | +0.718 / -0.598 | 0.829 | -0.060 | -0.185 to +0.068 | -0.252 to +0.132 | -8.90 | 13.58 | 7 | -1.144 | 14.2% | 97.9 |
| 30m_h4 | 70 | 28 / 42 | 40.0 (29.3–51.7) | +0.910 / -0.560 | 1.084 | +0.028 | -0.177 to +0.247 | -0.204 to +0.402 | +1.97 | 11.57 | 10 | -1.088 | 20.0% | 191.1 |
| 1h_h4 | 37 | 12 / 25 | 32.4 (19.6–48.5) | +0.517 / -0.703 | 0.353 | -0.307 | -0.511 to -0.092 | -0.418 to -0.205 | -11.38 | 11.38 | 5 | -1.051 | 29.7% | 217.3 |
| 4h_h4 | 8 | 5 / 3 | 62.5 (30.6–86.3) | +0.928 / -0.396 | 3.909 | +0.432 | -0.090 to +1.003 | -0.063 to +1.058 | +3.45 | 0.72 | 2 | -0.470 | 0.0% | 1590.0 |
| 5m_h5 | 7 | 1 / 6 | 14.3 (2.6–51.3) | +1.825 / -1.105 | 0.275 | -0.686 | -1.129 to +0.159 | -1.116 to +0.368 | -4.80 | 4.80 | 4 | -1.162 | 85.7% | 54.3 |

## 2. Exits, cost sensitivity, power and the random-entry baseline

**The random-entry baseline**
- **Actual entries:** each trade's entry is raced on the 5m bars from its entry close, asking whether TP1 comes before the stop within 7 days.
- **Random entries:** the same race runs from 50 random bar closes of the same timeframe in the forward window. They use the trade's direction, its stop distance and its TP1 distance.
- **Ambiguous bars:** a bar touching both levels counts as the stop.
- **What it measures:** whether the entry carries information, separately from the arm's exit management (FLIP and break-even exits).

| Ledger | Exits BE / BE_GAP / FLIP / SL / SL_GAP / TP2 | TP1 reached | Mean R at $0.50 / $0.80 spread | Trades for 80% power (+0.10 R) | Entry: TP1 before stop vs random (decided) | One-sided p (better / worse) |
|---|---|---|---|---|---|---|
| 5m_treatment | 1 / 1 / 0 / 11 / 0 / 4 | 6 | -0.242 / -0.285 | 1523 | 35.3% vs 34.7% (17 / 850) | 0.5702 / 0.6287 |
| 15m_treatment | 0 / 1 / 0 / 3 / 0 / 2 | 3 | -0.002 / -0.023 | 1073 | 50.0% vs 37.3% (6 / 300) | 0.4005 / 0.8556 |
| 30m_treatment | 0 / 0 / 0 / 3 / 0 / 0 | 0 | -1.050 / -1.065 | 1 | 0.0% vs 48.0% (3 / 150) | 1.0 / 0.1406 |
| 1h_treatment | 0 / 0 / 0 / 2 / 0 / 2 | 2 | +0.151 / +0.141 | 1451 | 50.0% vs 54.0% (4 / 200) | 0.745 / 0.6252 |
| 4h_treatment | 0 / 0 / 0 / 0 / 0 / 1 | 1 | +1.484 / +1.479 | — | 100.0% vs 68.0% (1 / 50) | 0.68 / 1.0 |
| 5m_challenger | 2 / 1 / 0 / 7 / 0 / 3 | 6 | +0.070 / +0.027 | 1859 | 46.2% vs 37.1% (13 / 650) | 0.341 / 0.8331 |
| 15m_challenger | 0 / 1 / 0 / 3 / 0 / 2 | 3 | -0.002 / -0.023 | 1073 | 50.0% vs 41.0% (6 / 300) | 0.4764 / 0.8067 |
| 30m_challenger | 0 / 0 / 0 / 3 / 0 / 0 | 0 | -1.050 / -1.065 | 1 | 0.0% vs 49.3% (3 / 150) | 1.0 / 0.1301 |
| 1h_challenger | 0 / 0 / 0 / 2 / 0 / 2 | 2 | +0.151 / +0.141 | 1451 | 50.0% vs 61.5% (4 / 200) | 0.8376 / 0.4987 |
| 4h_challenger | 0 / 0 / 0 / 0 / 0 / 1 | 1 | +1.484 / +1.479 | — | 100.0% vs 76.0% (1 / 50) | 0.76 / 1.0 |
| 5m_control | 0 / 0 / 0 / 1 / 0 / 1 | 1 | +0.386 / +0.359 | 3174 | 50.0% vs 51.0% (2 / 100) | 0.7599 / 0.7399 |
| 15m_control | 0 / 0 / 0 / 1 / 0 / 0 | 0 | -1.045 / -1.059 | — | 0.0% vs 42.0% (1 / 50) | 1.0 / 0.58 |
| 30m_control | 0 / 0 / 0 / 1 / 1 / 0 | 0 | -1.621 / -1.634 | 513 | 0.0% vs 49.0% (2 / 100) | 1.0 / 0.2601 |
| 1h_control | 0 / 0 / 0 / 0 / 0 / 1 | 1 | +1.378 / +1.367 | — | 100.0% vs 60.0% (1 / 50) | 0.6 / 1.0 |
| 5m_h2 | 0 / 0 / 0 / 3 / 0 / 1 | 1 | -0.519 / -0.542 | 888 | 25.0% vs 38.0% (4 / 200) | 0.8522 / 0.51 |
| 30m_h2 | 0 / 0 / 0 / 1 / 0 / 0 | 0 | -1.050 / -1.065 | — | 0.0% vs 32.0% (1 / 50) | 1.0 / 0.68 |
| 5m_h3 | 1 / 0 / 0 / 4 / 0 / 3 | 4 | +0.826 / +0.767 | 5124 | 50.0% vs 33.8% (8 / 400) | 0.2672 / 0.9077 |
| 15m_h3 | 0 / 0 / 0 / 3 / 0 / 0 | 0 | -1.101 / -1.130 | 1 | 0.0% vs 24.0% (3 / 150) | 1.0 / 0.439 |
| 30m_h3 | 0 / 0 / 0 / 1 / 0 / 0 | 0 | -1.058 / -1.073 | — | 0.0% vs 54.0% (1 / 50) | 1.0 / 0.46 |
| 1h_h3 | 0 / 0 / 0 / 1 / 0 / 0 | 0 | -1.045 / -1.059 | — | 0.0% vs 46.0% (1 / 50) | 1.0 / 0.54 |
| 5m_h4 | 25 / 3 / 263 / 57 / 0 / 62 | 119 | -0.161 / -0.197 | 484 | 45.7% vs 41.4% (407 / 20500) | 0.0431 / 0.9653 |
| 15m_h4 | 7 / 1 / 91 / 20 / 0 / 29 | 48 | -0.073 / -0.093 | 489 | 51.7% vs 45.7% (145 / 7400) | 0.0852 / 0.9378 |
| 30m_h4 | 5 / 0 / 38 / 14 / 0 / 13 | 20 | +0.019 / +0.005 | 658 | 48.6% vs 47.9% (70 / 3500) | 0.5031 / 0.5913 |
| 1h_h4 | 3 / 0 / 17 / 11 / 0 / 6 | 11 | -0.313 / -0.322 | 354 | 47.2% vs 55.8% (36 / 1850) | 0.8863 / 0.191 |
| 4h_h4 | 0 / 0 / 4 / 0 / 0 / 4 | 4 | +0.429 / +0.425 | 580 | 62.5% vs 56.8% (8 / 400) | 0.518 / 0.7487 |
| 5m_h5 | 0 / 0 / 0 / 6 / 0 / 1 | 1 | -0.714 / -0.755 | 965 | 14.3% vs 35.4% (7 / 350) | 0.9532 / 0.2266 |

**Statistical power.** About 350–480 trades per ledger are needed to detect a true +0.10 R with 80% power. Only 5m H4 is near that.

**Sharpe.** The per-trade ratio of mean R to its standard deviation is in the JSON (`r_per_sd`). It is not annualised: the trades overlap and are not evenly spaced, so an annual Sharpe would be misleading.

## 3. Why the H4 ledgers lose (diagnosis, not tuning)

**5m H4 (410 trades)**
- **Exits:** 263 trades (64%) are closed by an opposite engine signal (FLIP) before reaching TP1 or the stop, at −0.222 R on average (−58.4 R in total). Stop exits: 57 at −1.07 R (−61.2 R). TP2 exits: 62 at +0.91 R (+56.7 R).
- **Gross vs net:** before costs the ledger is −0.039 R per trade. The model cost takes 0.099 R per trade, 9% of the median $9.28 stop.
- **Entries:** TP1 before the stop 45.7% vs 41.4% for random entries with the same geometry (one-sided p 0.043, uncorrected for the 10 ledgers tested). The entries may carry some information, but the arm's frequent FLIP exits and costs more than spend it.
- **Not acted on:** this is a hypothesis for a future registered study, not a finding to act on. Changing H4's exits would need a new amendment and restart its forward test.

**1h H4 (37 trades)**
- **Costs:** only 2% of the median $42.63 stop.
- **Gross result:** −0.284 R before costs; the loss is not a cost effect.
- **Entries:** TP1 before the stop 47.2% vs 55.8% for random entries (one-sided p for "worse" 0.19; not significant).
- **Conclusion:** no evidence that this arm's entries help.

## 4. Benchmarks

| Benchmark | Status |
|---|---|
| Random entries with the same stops, targets, direction and costs | done above, per ledger (TP1-first rate) |
| Buy-and-hold / directional drift | not meaningful in R for a two-week window with long and short trades; the random baseline uses each trade's own direction, which removes the drift's effect on the comparison |
| Existing strategies | the arms are compared with each other above; Treatment = Challenger on 15m–4h (GA-25) |
| Out-of-sample forward results | these ARE the out-of-sample results: the only data no study has seen (`RESEARCH_LINEAGE_REGISTER.md`) |

## 5. What these results do and do not show

**They show:**
- On 11 trading days, the H4 Playbook on 5m and 1h lost money at the model cost, and their intervals exclude zero.
- No arm has shown a positive edge.

**They do not show:**
- A long-run expectancy (two weeks; serial dependence; one market regime).
- Performance at the broker (costs and fills unverified).
- Anything about the alerts on the phone, which are non-directional monitors and carry no entry.

No parameter, stop, target or rule was changed in response to these results. The H4 rules remain frozen under the registered forward test.
