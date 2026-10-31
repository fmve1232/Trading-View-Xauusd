# Current performance audit — every arm, three kinds of evidence (2026-11-01)

The three kinds of evidence are never mixed:

- **in-sample backtest** on the stored history;
- the **recorded forward test** (web.6, archived);
- **web.7**, which has no trades yet.

R is net of modelled costs. Win % alone is never a verdict.

## 1. In-sample backtest, web.7 rules (stored windows: 5m from 09-09, 15m from 08-05, 1h from 03-02; to 10-30)

Source: `audit/tools/exec_sensitivity.py`. The web.7 column is the deployed rule; other columns are execution
scenarios. **This is a historical simulation on data the operator has seen: it is not evidence of edge.**

Price source twelvedata:XAU/USD; 5-minute store from 2026-09-09 14:25 UTC.

| TF / arm | n | Gap exits | Stop exits | web.6 mean R / PF / max DD | **web.7 (approved)** mean R / PF / max DD | gap +0.5 | gap +1.0 | gap +2.0 | stop +0.2 | stop +0.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1h/treatment | 30 | 0 | 23 | +0.052 / 1.482 / 5.5 | **+0.052 / 1.482 / 5.5** | +0.052 | +0.052 | +0.052 | +0.045 | +0.036 |
| 1h/control | 2 | 0 | 2 | -1.023 / 0.0 / 2.0 | **-1.023 / 0.0 / 2.0** | -1.023 | -1.023 | -1.023 | -1.029 | -1.038 |
| 1h/challenger | 32 | 0 | 23 | +0.164 / 1.449 / 5.2 | **+0.164 / 1.449 / 5.2** | +0.164 | +0.164 | +0.164 | +0.158 | +0.150 |
| 1h/h2 | 8 | 0 | 5 | +0.327 / 1.37 / 2.0 | **+0.327 / 1.37 / 2.0** | +0.327 | +0.327 | +0.327 | +0.325 | +0.322 |
| 1h/h3 | 24 | 1 | 20 | -0.373 / 0.652 / 12.2 | **-0.385 / 0.689 / 13.9** | -0.386 | -0.387 | -0.388 | -0.396 | -0.413 |
| 1h/h4 | 729 | 13 | 145 | -0.039 / 0.896 / 40.8 | **-0.041 / 0.892 / 44.2** | -0.041 | -0.041 | -0.041 | -0.042 | -0.044 |
| 1h/h5 | 3 | 0 | 1 | +0.831 / 3.732 / 1.0 | **+0.831 / 3.732 / 1.0** | +0.831 | +0.831 | +0.831 | +0.829 | +0.825 |
| 1h/h6 | 36 | 0 | 29 | -0.125 / 0.881 / 11.6 | **-0.125 / 0.881 / 11.6** | -0.125 | -0.125 | -0.125 | -0.131 | -0.141 |
| 15m/treatment | 12 | 0 | 7 | +0.589 / 2.549 / 3.1 | **+0.589 / 2.549 / 3.1** | +0.589 | +0.589 | +0.589 | +0.583 | +0.573 |
| 15m/control | 6 | 0 | 5 | +0.074 / 0.74 / 2.8 | **+0.074 / 0.74 / 2.8** | +0.074 | +0.074 | +0.074 | +0.065 | +0.052 |
| 15m/challenger | 12 | 0 | 7 | +0.589 / 2.549 / 3.1 | **+0.589 / 2.549 / 3.1** | +0.589 | +0.589 | +0.589 | +0.583 | +0.573 |
| 15m/h2 | 8 | 0 | 7 | -0.725 / 0.558 / 5.8 | **-0.725 / 0.558 / 5.8** | -0.725 | -0.725 | -0.725 | -0.734 | -0.748 |
| 15m/h3 | 44 | 0 | 38 | -0.167 / 0.882 / 15.8 | **-0.167 / 0.882 / 15.8** | -0.167 | -0.167 | -0.167 | -0.191 | -0.227 |
| 15m/h4 | 986 | 12 | 207 | -0.107 / 0.675 / 111.1 | **-0.108 / 0.674 / 111.4** | -0.108 | -0.108 | -0.109 | -0.111 | -0.116 |
| 15m/h5 | 3 | 1 | 3 | -0.489 / 0.185 / 2.1 | **-0.497 / 0.178 / 2.1** | -0.504 | -0.510 | -0.524 | -0.506 | -0.521 |
| 15m/h6 | 17 | 0 | 12 | +0.193 / 1.394 / 6.3 | **+0.193 / 1.394 / 6.3** | +0.193 | +0.193 | +0.193 | +0.185 | +0.173 |
| 5m/treatment | 37 | 0 | 30 | +0.189 / 1.299 / 8.6 | **+0.189 / 1.299 / 8.6** | +0.189 | +0.189 | +0.189 | +0.171 | +0.143 |
| 5m/control | 14 | 0 | 11 | -0.213 / 0.889 / 8.9 | **-0.213 / 0.889 / 8.9** | -0.213 | -0.213 | -0.213 | -0.236 | -0.270 |
| 5m/challenger | 35 | 0 | 28 | +0.216 / 1.303 / 8.2 | **+0.216 / 1.303 / 8.2** | +0.216 | +0.216 | +0.216 | +0.199 | +0.173 |
| 5m/h2 | 14 | 0 | 10 | -0.401 / 0.588 / 8.4 | **-0.401 / 0.588 / 8.4** | -0.401 | -0.401 | -0.401 | -0.422 | -0.453 |
| 5m/h3 | 67 | 0 | 53 | -0.240 / 0.746 / 26.9 | **-0.240 / 0.746 / 26.9** | -0.240 | -0.240 | -0.240 | -0.287 | -0.356 |
| 5m/h4 | 1731 | 8 | 369 | -0.176 / 0.613 / 314.6 | **-0.176 / 0.613 / 314.8** | -0.176 | -0.176 | -0.177 | -0.183 | -0.194 |
| 5m/h5 | 19 | 0 | 15 | -0.119 / 0.782 / 7.3 | **-0.119 / 0.782 / 7.3** | -0.119 | -0.119 | -0.119 | -0.136 | -0.161 |
| 5m/h6 | 37 | 0 | 30 | +0.189 / 1.299 / 8.6 | **+0.189 / 1.299 / 8.6** | +0.189 | +0.189 | +0.189 | +0.171 | +0.143 |

(The 5-minute path check is in `audit/GAP_SENSITIVITY_2026-11-01.md` §3.)

**Reading:**

- **Only H4 has a large sample.** It is negative on every timeframe (5m t −8.4, 15m t −4.0, 1h t −1.3).
- The treatment, challenger, H2, H5 and H6 have **at most 37 trades per timeframe**. Their means (−1.0 to +0.8 R)
  are not distinguishable from zero.
- **H3** is negative on all three timeframes (5m 67 trades, −0.24 R).
- The **control** is the treatment with stricter gates and takes 2–14 trades.

## 2. Recorded forward test, engine web.6 (2026-10-17 21:26 → 10-31 17:23 UTC, archived)

Source: `audit/tools/forward_stats.py --archive`; bootstrap seed 7.

| Ledger | n | Win % [Wilson 95%] | Mean R [bootstrap 95%] | t | PF [bootstrap 95%] | Sum R | Max DD (R) |
|---|---|---|---|---|---|---|---|
| 15m_challenger | 1 | 0.0 [0.0, 79.3] | -1.044 | — | 0.00 | -1.04 | 1.04 |
| 15m_h2 | 1 | 0.0 [0.0, 79.3] | -1.028 | — | 0.00 | -1.03 | 1.03 |
| 15m_h3 | 8 | 50.0 [21.5, 78.5] | +0.053 [-0.831, +0.998] | +0.11 | 1.14 [0.10, 7.57] | +0.42 | 3.55 |
| 15m_h4 | 171 | 38.6 [31.6, 46.1] | -0.092 [-0.210, +0.033] | -1.50 | 0.76 [0.50, 1.13] | -15.74 | 19.88 |
| 15m_treatment | 1 | 0.0 [0.0, 79.3] | -1.044 | — | 0.00 | -1.04 | 1.04 |
| 1h_challenger | 2 | 50.0 [9.5, 90.5] | +0.289 | +0.22 | 2.68 | +0.58 | 1.05 |
| 1h_h3 | 3 | 33.3 [6.1, 79.2] | -0.164 | -0.18 | 1.38 | -0.49 | 2.20 |
| 1h_h4 | 49 | 32.7 [21.2, 46.6] | -0.187 [-0.360, -0.004] | -2.06 | 0.55 [0.20, 1.15] | -9.15 | 11.05 |
| 1h_treatment | 3 | 33.3 [6.1, 79.2] | -0.163 | -0.18 | 1.47 | -0.49 | 2.12 |
| 4h_h4 | 12 | 25.0 [8.9, 53.2] | -0.107 [-0.557, +0.392] | -0.42 | 0.71 [0.00, 2.33] | -1.28 | 4.39 |
| 5m_challenger | 8 | 50.0 [21.5, 78.5] | +0.904 [-0.599, +2.558] | +1.04 | 3.29 [0.34, 20.48] | +7.23 | 2.20 |
| 5m_control | 1 | 100.0 [20.7, 100.0] | +1.965 | — | — | +1.97 | 0.00 |
| 5m_h2 | 3 | 33.3 [6.1, 79.2] | -0.313 | -0.43 | 0.19 | -0.94 | 2.08 |
| 5m_h3 | 14 | 64.3 [38.8, 83.7] | +0.553 [-0.330, +1.520] | +1.11 | 3.69 [1.10, 16.24] | +7.75 | 4.16 |
| 5m_h4 | 511 | 33.5 [29.5, 37.7] | -0.179 [-0.251, -0.104] | -4.75 | 0.58 [0.46, 0.74] | -91.39 | 99.23 |
| 5m_h5 | 2 | 50.0 [9.5, 90.5] | +0.452 | +0.30 | 1.59 | +0.90 | 1.06 |
| 5m_treatment | 8 | 50.0 [21.5, 78.5] | +0.938 [-0.551, +2.676] | +1.05 | 3.17 [0.38, 21.34] | +7.50 | 2.20 |


**Reading:**

- **H4 lost** on 5m (interval entirely below 0) and on 1h. On its deciding 15m timeframe the interval includes 0,
  so its formal verdict is **not shown**.
- **Every other arm has n ≤ 14.** No pre-registered verdict was reached.

## 3. Engine web.7 (from 2026-10-31 17:23 UTC)

**0 trades** (the market was shut). The first count comes at the 7 Nov check.
`audit/STATISTICAL_VALIDATION_2026-11-01.md` §3 has the evaluation design and power.

## 4. Probability calibration (all evidence)

| Output | In-sample | Forward |
|---|---|---|
| Engine `cal_p` (TP1 before SL) | Brier skill −0.03 / −0.10 / −0.31 (15m / 5m / 1h); AUC 0.38–0.52 | not assessable (no ledger has ≥ 10 trades carrying P) |
| Engine score vs its own event (Amendment 12) | AUC 0.484 (15m), 0.515 (1h); skill −0.056 / −0.042 | — |

**No probability displayed by the system is calibrated today.**

## 5. Conclusion

- There is **no arm with demonstrated positive expectancy**, in-sample or forward.
- The single well-measured arm (H4) is negative, and its signals are directionless (`03`).
- **No selective or "high-confidence" tier can be claimed.** The scores that would rank trades have no measured
  skill (Part 2 G of the brief: **NOT ESTABLISHED**).
