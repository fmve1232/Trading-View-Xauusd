# Phase B1 — published-evidence families on development data (executed 2026-11-01)

**Partition:** development only, 2020-01-24 02:00 → 2023-01-24 02:00 UTC (Amendment 13). It is loaded through
`quantum.research.history.load()`, with market-shut bars removed, and `harness.partition()`, which refuses
validation and holdout without an approved registration. **Validation and the sealed holdout were not opened.**

**Harness:** `quantum/research/harness.py`, tested (`tests/test_research_harness.py`). It finds a planted edge
(t > 3), finds none in noise, gets PBO ≈ 0.5 on noise, and the Reality Check finds the planted rule.

**Runner:** `quantum/research/b1.py`. The grid was declared in the code before the run:

- **Event:** stop 1 R, target k R, time stop h bars; R = ATR(14). Entry at the close; gap fills at the open; a bar
  touching both barriers is AMBIGUOUS and charged as a full loss.
- **Costs:** the frozen engine model.

**Trial log:** `research/trials.jsonl`, 124 records (B1: 80 + 16 baselines; B1b: 20 + 8 baselines). The B1
family statistics were recomputed once after a screening bug was fixed: the BH / t screens had been two-sided,
which flagged significantly *negative* trials. That re-run wrote to a scratch log, so no trial is double-counted.

## 1. Verdict

**No tested configuration has positive expectancy after costs. None comes close to the promotion thresholds, and
the family-level tests say the best of them is what chance alone would produce.**

| Set | Trials | Positive net R | Reality Check p | PBO (oos result of IS-best) | FDR passes | Gross t > 2 |
|---|---|---|---|---|---|---|
| B1: 1h and 15m | 80 | **0** | 1.000 | 0.00 (IS-best lost OOS in 100% of splits) | 0 | 1 (of 80) |
| B1b: 4h | 20 | **0** | 0.996 | 0.60 (lost OOS in 99%) | 0 | 0 |

**PBO 0.00 in B1 is not good news.** Every configuration loses, in a stable order set by its cost share, so the
in-sample best keeps its rank and still loses out of sample in every split.

## 2. What the numbers show

1. **Before costs, nothing beats a coin, or simply holding.**
   - Gross expectancy sits between −0.09 and +0.07 R in all 100 trials.
   - Only 1 of 100 has a gross t > 2 (1h TSMOM 24h, k2 h16, +0.060 R), fewer than chance would give.
   - The best 4h trial (TSMOM 60 days, k2 h30: gross +0.070 R) equals the "always long" baseline over the same
     period (+0.075 R). It is gold's 2020–22 drift, not momentum.
2. **Costs decide everything at intraday scale.** With a 1-ATR stop the frozen costs (0.77–0.97 points per oz)
   cost:

   | TF | Cost per trade |
   |---|---|
   | 15m | ≈ 0.42 R |
   | 1h | ≈ 0.18 R |
   | 4h | ≈ 0.09 R |

   An intraday strategy with a 1-ATR stop would need a gross edge larger than that just to break even. None of the
   families shows any gross edge at all.
3. **Volatility regime does not create an edge.** The high-volatility tercile loses less because its ATR is larger,
   so cost is a smaller share of R. Its gross result is still about 0.
4. **Session breakouts** (Asian range → London; London range → New York) are directionless: 47–50% of resolved
   1R trades are won.

## 3. Family statistics

### B1 (1h and 15m, 80 trials)

| Statistic | Value |
|---|---|
| Trials in the family (baselines excluded) | 80 |
| White's Reality Check (stationary bootstrap, B = 1000), best rule | p = **1.000** (best: 1h LON>NY k2 h16) |
| PBO (CSCV, 8 groups, 70 splits) | 0.00 |
| Out-of-sample net R of the in-sample best (mean over splits) | **-0.681** per week-block; it lost in 100% of splits |
| Benjamini-Hochberg FDR 10% (one-sided: net R > 0) | 0 pass |
| Net t > 3 | 0 |
| Gross t > 2 (before costs; chance alone gives about 2.5% of trials) | 1: 1h TSMOM(24h) k2 h16 |
| Deflated Sharpe of the best daily Sharpe (1h ASIA>LON k2 h16: -0.069) | DSR = 0.000 (benchmark SR0 0.927 for 80 trials) |

### B1b (4h, 20 trials)

| Statistic | Value |
|---|---|
| Trials in the family (baselines excluded) | 20 |
| White's Reality Check (stationary bootstrap, B = 1000), best rule | p = **0.996** (best: 4h TSMOM(60d) k2 h30) |
| PBO (CSCV, 8 groups, 70 splits) | 0.60 |
| Out-of-sample net R of the in-sample best (mean over splits) | **-0.356** per week-block; it lost in 99% of splits |
| Benjamini-Hochberg FDR 10% (one-sided: net R > 0) | 0 pass |
| Net t > 3 | 0 |
| Gross t > 2 (before costs; chance alone gives about 2.5% of trials) | 0 |

## 4. All trials

### 1h

| Trial | n | Gross R (t) | Cost R | Net R (t) | Win % of resolved | Ambiguous |
|---|---|---|---|---|---|---|
| 1h TSMOM(24h) k1 h4 | 4830 | +0.003 (+0.25) | 0.185 | -0.182 (-14.28) | 50.8 | 70 |
| 1h TSMOM(24h) k1 h16 | 3680 | +0.010 (+0.58) | 0.178 | -0.168 (-10.12) | 50.5 | 70 |
| 1h TSMOM(24h) k2 h4 | 4219 | +0.010 (+0.60) | 0.187 | -0.177 (-10.96) | 24.4 | 25 |
| 1h TSMOM(24h) k2 h16 | 2501 | +0.060 (+2.17) | 0.175 | -0.115 (-4.17) | 34.1 | 22 |
| 1h TSMOM(72h) k1 h4 | 4816 | -0.011 (-0.87) | 0.185 | -0.196 (-15.37) | 49.0 | 70 |
| 1h TSMOM(72h) k1 h16 | 3668 | -0.020 (-1.20) | 0.178 | -0.198 (-11.84) | 49.1 | 70 |
| 1h TSMOM(72h) k2 h4 | 4237 | -0.003 (-0.19) | 0.186 | -0.190 (-11.73) | 23.5 | 23 |
| 1h TSMOM(72h) k2 h16 | 2536 | +0.016 (+0.58) | 0.175 | -0.159 (-5.82) | 32.5 | 16 |
| 1h TSMOM(240h) k1 h4 | 4769 | -0.011 (-0.87) | 0.185 | -0.196 (-15.28) | 48.9 | 71 |
| 1h TSMOM(240h) k1 h16 | 3627 | -0.021 (-1.23) | 0.177 | -0.198 (-11.80) | 49.0 | 71 |
| 1h TSMOM(240h) k2 h4 | 4196 | -0.009 (-0.57) | 0.185 | -0.195 (-12.04) | 22.8 | 14 |
| 1h TSMOM(240h) k2 h16 | 2507 | -0.003 (-0.12) | 0.174 | -0.178 (-6.55) | 31.6 | 19 |
| 1h DONCHIAN(20) k1 h4 | 1194 | -0.036 (-1.36) | 0.179 | -0.215 (-8.05) | 48.2 | 31 |
| 1h DONCHIAN(20) k1 h16 | 1140 | -0.042 (-1.40) | 0.178 | -0.219 (-7.34) | 47.7 | 34 |
| 1h DONCHIAN(20) k2 h4 | 1138 | -0.046 (-1.39) | 0.179 | -0.225 (-6.80) | 24.7 | 6 |
| 1h DONCHIAN(20) k2 h16 | 992 | -0.033 (-0.77) | 0.176 | -0.209 (-4.83) | 30.9 | 7 |
| 1h DONCHIAN(55) k1 h4 | 677 | -0.011 (-0.30) | 0.174 | -0.185 (-5.19) | 50.0 | 21 |
| 1h DONCHIAN(55) k1 h16 | 637 | +0.004 (+0.11) | 0.173 | -0.168 (-4.17) | 49.8 | 24 |
| 1h DONCHIAN(55) k2 h4 | 652 | -0.050 (-1.17) | 0.175 | -0.225 (-5.24) | 23.1 | 4 |
| 1h DONCHIAN(55) k2 h16 | 561 | -0.034 (-0.59) | 0.170 | -0.204 (-3.52) | 30.4 | 6 |
| 1h ASIA>LON k1 h4 | 700 | -0.020 (-0.55) | 0.179 | -0.199 (-5.41) | 49.4 | 12 |
| 1h ASIA>LON k1 h16 | 700 | -0.010 (-0.25) | 0.179 | -0.189 (-4.85) | 49.9 | 14 |
| 1h ASIA>LON k2 h4 | 700 | +0.020 (+0.42) | 0.179 | -0.159 (-3.39) | 30.2 | 6 |
| 1h ASIA>LON k2 h16 | 694 | +0.064 (+1.18) | 0.179 | -0.115 (-2.11) | 35.3 | 7 |
| 1h LON>NY k1 h4 | 448 | -0.059 (-1.51) | 0.151 | -0.210 (-5.38) | 47.4 | 7 |
| 1h LON>NY k1 h16 | 448 | -0.029 (-0.60) | 0.151 | -0.179 (-3.74) | 48.5 | 8 |
| 1h LON>NY k2 h4 | 448 | -0.054 (-1.22) | 0.151 | -0.205 (-4.63) | 19.3 | 3 |
| 1h LON>NY k2 h16 | 448 | -0.001 (-0.02) | 0.151 | -0.152 (-2.39) | 31.4 | 4 |
| 1h TSMOM(72h)|vol low k1 h4 | 1926 | -0.030 (-1.45) | 0.222 | -0.252 (-12.08) | 48.7 | 31 |
| 1h TSMOM(72h)|vol low k1 h16 | 1584 | -0.043 (-1.67) | 0.216 | -0.259 (-10.10) | 47.8 | 35 |
| 1h TSMOM(72h)|vol low k2 h4 | 1726 | -0.052 (-1.97) | 0.222 | -0.274 (-10.44) | 23.4 | 8 |
| 1h TSMOM(72h)|vol low k2 h16 | 1118 | -0.033 (-0.79) | 0.216 | -0.249 (-5.99) | 31.6 | 9 |
| 1h TSMOM(72h)|vol mid k1 h4 | 1635 | +0.021 (+0.97) | 0.182 | -0.161 (-7.48) | 50.8 | 26 |
| 1h TSMOM(72h)|vol mid k1 h16 | 1472 | -0.000 (-0.00) | 0.180 | -0.180 (-6.88) | 49.9 | 33 |
| 1h TSMOM(72h)|vol mid k2 h4 | 1495 | +0.029 (+1.08) | 0.183 | -0.154 (-5.66) | 24.3 | 9 |
| 1h TSMOM(72h)|vol mid k2 h16 | 1129 | +0.031 (+0.75) | 0.180 | -0.149 (-3.66) | 32.9 | 8 |
| 1h TSMOM(72h)|vol high k1 h4 | 1748 | +0.007 (+0.34) | 0.142 | -0.135 (-6.51) | 50.4 | 12 |
| 1h TSMOM(72h)|vol high k1 h16 | 1454 | +0.009 (+0.36) | 0.140 | -0.130 (-4.90) | 50.9 | 11 |
| 1h TSMOM(72h)|vol high k2 h4 | 1544 | +0.007 (+0.27) | 0.143 | -0.136 (-5.29) | 23.4 | 3 |
| 1h TSMOM(72h)|vol high k2 h16 | 1073 | +0.014 (+0.35) | 0.140 | -0.126 (-3.05) | 31.4 | 2 |
| 1h ALWAYS LONG k1 h4 | 4833 | -0.013 (-1.06) | 0.185 | -0.199 (-15.63) | 48.7 | 70 |
| 1h ALWAYS LONG k1 h16 | 3683 | -0.016 (-0.96) | 0.178 | -0.194 (-11.65) | 49.0 | 70 |
| 1h ALWAYS LONG k2 h4 | 4272 | -0.005 (-0.32) | 0.186 | -0.191 (-12.03) | 22.2 | 10 |
| 1h ALWAYS LONG k2 h16 | 2525 | +0.006 (+0.23) | 0.174 | -0.168 (-6.22) | 31.7 | 9 |
| 1h ALWAYS SHORT k1 h4 | 4833 | -0.016 (-1.22) | 0.185 | -0.201 (-15.73) | 49.2 | 70 |
| 1h ALWAYS SHORT k1 h16 | 3683 | -0.022 (-1.32) | 0.178 | -0.200 (-11.99) | 49.0 | 70 |
| 1h ALWAYS SHORT k2 h4 | 4266 | -0.007 (-0.44) | 0.186 | -0.194 (-11.93) | 24.7 | 27 |
| 1h ALWAYS SHORT k2 h16 | 2552 | -0.029 (-1.07) | 0.176 | -0.205 (-7.57) | 31.0 | 29 |

### 15m

| Trial | n | Gross R (t) | Cost R | Net R (t) | Win % of resolved | Ambiguous |
|---|---|---|---|---|---|---|
| 15min TSMOM(24h) k1 h4 | 19816 | -0.013 (-1.96) | 0.417 | -0.430 (-65.10) | 49.2 | 192 |
| 15min TSMOM(24h) k1 h16 | 15885 | -0.016 (-1.95) | 0.410 | -0.426 (-52.25) | 49.2 | 176 |
| 15min TSMOM(24h) k2 h4 | 17141 | -0.005 (-0.60) | 0.418 | -0.423 (-50.25) | 24.4 | 44 |
| 15min TSMOM(24h) k2 h16 | 10907 | +0.002 (+0.18) | 0.409 | -0.406 (-30.46) | 32.1 | 39 |
| 15min TSMOM(72h) k1 h4 | 19763 | -0.012 (-1.83) | 0.417 | -0.429 (-65.00) | 49.3 | 192 |
| 15min TSMOM(72h) k1 h16 | 15843 | -0.019 (-2.38) | 0.410 | -0.429 (-52.58) | 49.1 | 176 |
| 15min TSMOM(72h) k2 h4 | 17135 | -0.003 (-0.42) | 0.419 | -0.422 (-50.27) | 24.2 | 38 |
| 15min TSMOM(72h) k2 h16 | 10821 | +0.002 (+0.17) | 0.407 | -0.405 (-30.36) | 32.0 | 42 |
| 15min TSMOM(240h) k1 h4 | 19571 | -0.007 (-1.08) | 0.416 | -0.423 (-63.78) | 49.3 | 188 |
| 15min TSMOM(240h) k1 h16 | 15686 | -0.015 (-1.91) | 0.409 | -0.424 (-51.73) | 49.1 | 173 |
| 15min TSMOM(240h) k2 h4 | 16955 | -0.001 (-0.06) | 0.417 | -0.417 (-49.55) | 23.8 | 32 |
| 15min TSMOM(240h) k2 h16 | 10690 | +0.007 (+0.49) | 0.406 | -0.400 (-29.76) | 32.1 | 39 |
| 15min DONCHIAN(20) k1 h4 | 4944 | -0.062 (-4.64) | 0.424 | -0.486 (-35.78) | 46.9 | 60 |
| 15min DONCHIAN(20) k1 h16 | 4731 | -0.071 (-4.88) | 0.421 | -0.492 (-33.35) | 46.4 | 68 |
| 15min DONCHIAN(20) k2 h4 | 4594 | -0.057 (-3.37) | 0.426 | -0.483 (-27.98) | 25.2 | 17 |
| 15min DONCHIAN(20) k2 h16 | 4080 | -0.048 (-2.22) | 0.421 | -0.469 (-21.67) | 30.6 | 19 |
| 15min DONCHIAN(55) k1 h4 | 2795 | -0.059 (-3.32) | 0.375 | -0.434 (-24.03) | 46.8 | 43 |
| 15min DONCHIAN(55) k1 h16 | 2697 | -0.076 (-3.95) | 0.373 | -0.449 (-23.16) | 46.2 | 48 |
| 15min DONCHIAN(55) k2 h4 | 2591 | -0.033 (-1.42) | 0.377 | -0.410 (-17.48) | 26.5 | 11 |
| 15min DONCHIAN(55) k2 h16 | 2342 | -0.030 (-1.06) | 0.376 | -0.406 (-14.15) | 31.3 | 13 |
| 15min ASIA>LON k1 h4 | 736 | -0.047 (-1.33) | 0.389 | -0.436 (-12.07) | 47.8 | 11 |
| 15min ASIA>LON k1 h16 | 736 | -0.056 (-1.53) | 0.389 | -0.445 (-11.94) | 47.2 | 12 |
| 15min ASIA>LON k2 h4 | 736 | -0.051 (-1.13) | 0.389 | -0.439 (-9.75) | 25.2 | 2 |
| 15min ASIA>LON k2 h16 | 736 | -0.066 (-1.29) | 0.389 | -0.454 (-8.88) | 30.7 | 3 |
| 15min LON>NY k1 h4 | 506 | +0.002 (+0.04) | 0.256 | -0.255 (-6.43) | 50.3 | 2 |
| 15min LON>NY k1 h16 | 506 | -0.044 (-1.01) | 0.256 | -0.300 (-6.78) | 47.7 | 3 |
| 15min LON>NY k2 h4 | 506 | -0.003 (-0.07) | 0.256 | -0.260 (-5.48) | 25.2 | 3 |
| 15min LON>NY k2 h16 | 506 | -0.086 (-1.51) | 0.256 | -0.342 (-6.01) | 27.2 | 3 |
| 15min TSMOM(72h)|vol low k1 h4 | 7281 | -0.015 (-1.37) | 0.572 | -0.587 (-53.39) | 49.0 | 62 |
| 15min TSMOM(72h)|vol low k1 h16 | 6049 | -0.018 (-1.35) | 0.562 | -0.580 (-43.75) | 49.1 | 61 |
| 15min TSMOM(72h)|vol low k2 h4 | 6412 | -0.000 (-0.03) | 0.573 | -0.573 (-40.77) | 25.2 | 11 |
| 15min TSMOM(72h)|vol low k2 h16 | 4179 | +0.005 (+0.25) | 0.555 | -0.550 (-25.12) | 32.9 | 12 |
| 15min TSMOM(72h)|vol mid k1 h4 | 6994 | -0.000 (-0.01) | 0.403 | -0.403 (-36.87) | 50.2 | 73 |
| 15min TSMOM(72h)|vol mid k1 h16 | 6042 | -0.012 (-0.89) | 0.399 | -0.411 (-31.23) | 49.4 | 72 |
| 15min TSMOM(72h)|vol mid k2 h4 | 6167 | +0.008 (+0.59) | 0.403 | -0.395 (-28.50) | 25.1 | 17 |
| 15min TSMOM(72h)|vol mid k2 h16 | 4424 | +0.018 (+0.88) | 0.398 | -0.379 (-18.27) | 32.4 | 20 |
| 15min TSMOM(72h)|vol high k1 h4 | 7122 | -0.009 (-0.81) | 0.270 | -0.279 (-26.18) | 49.4 | 71 |
| 15min TSMOM(72h)|vol high k1 h16 | 5950 | -0.004 (-0.32) | 0.268 | -0.272 (-20.88) | 50.0 | 72 |
| 15min TSMOM(72h)|vol high k2 h4 | 6209 | -0.004 (-0.26) | 0.271 | -0.274 (-20.50) | 23.4 | 15 |
| 15min TSMOM(72h)|vol high k2 h16 | 4289 | -0.006 (-0.29) | 0.270 | -0.276 (-13.47) | 30.9 | 13 |
| 15min ALWAYS LONG k1 h4 | 19844 | -0.013 (-2.04) | 0.418 | -0.431 (-65.34) | 48.8 | 192 |
| 15min ALWAYS LONG k1 h16 | 15912 | -0.017 (-2.15) | 0.411 | -0.428 (-52.57) | 49.0 | 176 |
| 15min ALWAYS LONG k2 h4 | 17213 | -0.000 (-0.01) | 0.419 | -0.419 (-50.09) | 23.2 | 36 |
| 15min ALWAYS LONG k2 h16 | 10810 | +0.007 (+0.50) | 0.409 | -0.402 (-30.07) | 32.0 | 46 |
| 15min ALWAYS SHORT k1 h4 | 19844 | -0.006 (-0.96) | 0.418 | -0.424 (-64.36) | 49.9 | 192 |
| 15min ALWAYS SHORT k1 h16 | 15912 | -0.005 (-0.62) | 0.411 | -0.416 (-51.04) | 49.9 | 176 |
| 15min ALWAYS SHORT k2 h4 | 17186 | -0.004 (-0.54) | 0.419 | -0.423 (-50.30) | 24.7 | 43 |
| 15min ALWAYS SHORT k2 h16 | 10850 | -0.001 (-0.08) | 0.407 | -0.408 (-30.65) | 32.1 | 34 |

### 4h (B1b)

| Trial | n | Gross R (t) | Cost R | Net R (t) | Win % of resolved | Ambiguous |
|---|---|---|---|---|---|---|
| 4h TSMOM(5d) k1 h6 | 1094 | -0.034 (-1.17) | 0.087 | -0.121 (-4.16) | 48.4 | 15 |
| 4h TSMOM(5d) k1 h30 | 988 | -0.018 (-0.55) | 0.086 | -0.103 (-3.22) | 49.3 | 19 |
| 4h TSMOM(5d) k2 h6 | 903 | +0.049 (+1.20) | 0.087 | -0.038 (-0.93) | 28.7 | 5 |
| 4h TSMOM(5d) k2 h30 | 655 | +0.033 (+0.59) | 0.085 | -0.052 (-0.92) | 34.4 | 5 |
| 4h TSMOM(20d) k1 h6 | 1069 | -0.007 (-0.25) | 0.085 | -0.093 (-3.16) | 49.8 | 15 |
| 4h TSMOM(20d) k1 h30 | 964 | -0.011 (-0.35) | 0.084 | -0.096 (-2.95) | 49.5 | 19 |
| 4h TSMOM(20d) k2 h6 | 883 | +0.031 (+0.77) | 0.087 | -0.055 (-1.35) | 27.8 | 3 |
| 4h TSMOM(20d) k2 h30 | 634 | -0.019 (-0.34) | 0.084 | -0.103 (-1.83) | 32.8 | 5 |
| 4h TSMOM(60d) k1 h6 | 1012 | -0.005 (-0.15) | 0.087 | -0.092 (-3.03) | 49.7 | 15 |
| 4h TSMOM(60d) k1 h30 | 912 | +0.001 (+0.03) | 0.086 | -0.085 (-2.54) | 50.2 | 18 |
| 4h TSMOM(60d) k2 h6 | 837 | +0.034 (+0.81) | 0.088 | -0.055 (-1.31) | 27.7 | 4 |
| 4h TSMOM(60d) k2 h30 | 577 | +0.070 (+1.16) | 0.085 | -0.016 (-0.26) | 35.7 | 4 |
| 4h DONCHIAN(20) k1 h6 | 312 | -0.071 (-1.27) | 0.088 | -0.159 (-2.87) | 45.9 | 5 |
| 4h DONCHIAN(20) k1 h30 | 309 | -0.074 (-1.28) | 0.089 | -0.162 (-2.82) | 46.3 | 5 |
| 4h DONCHIAN(20) k2 h6 | 273 | +0.019 (+0.24) | 0.090 | -0.071 (-0.93) | 30.8 | 0 |
| 4h DONCHIAN(20) k2 h30 | 250 | -0.008 (-0.09) | 0.088 | -0.097 (-1.08) | 33.3 | 0 |
| 4h DONCHIAN(55) k1 h6 | 184 | -0.013 (-0.18) | 0.090 | -0.103 (-1.43) | 49.1 | 3 |
| 4h DONCHIAN(55) k1 h30 | 182 | -0.036 (-0.49) | 0.090 | -0.126 (-1.69) | 48.4 | 3 |
| 4h DONCHIAN(55) k2 h6 | 165 | +0.005 (+0.05) | 0.090 | -0.085 (-0.86) | 30.2 | 0 |
| 4h DONCHIAN(55) k2 h30 | 155 | -0.017 (-0.15) | 0.090 | -0.107 (-0.94) | 32.9 | 0 |
| 4h ALWAYS LONG k1 h6 | 1096 | +0.010 (+0.35) | 0.087 | -0.077 (-2.64) | 50.2 | 15 |
| 4h ALWAYS LONG k1 h30 | 990 | +0.005 (+0.15) | 0.086 | -0.081 (-2.52) | 50.2 | 19 |
| 4h ALWAYS LONG k2 h6 | 901 | +0.063 (+1.59) | 0.089 | -0.025 (-0.63) | 28.3 | 4 |
| 4h ALWAYS LONG k2 h30 | 626 | +0.075 (+1.29) | 0.086 | -0.011 (-0.20) | 35.5 | 4 |
| 4h ALWAYS SHORT k1 h6 | 1096 | -0.038 (-1.29) | 0.087 | -0.124 (-4.28) | 48.3 | 15 |
| 4h ALWAYS SHORT k1 h30 | 990 | -0.043 (-1.34) | 0.086 | -0.129 (-4.01) | 47.9 | 19 |
| 4h ALWAYS SHORT k2 h6 | 905 | -0.016 (-0.41) | 0.087 | -0.103 (-2.58) | 27.4 | 4 |
| 4h ALWAYS SHORT k2 h30 | 656 | -0.073 (-1.34) | 0.085 | -0.157 (-2.89) | 30.9 | 7 |

## 5. What this means, and what comes next (for the operator's decision)

- **Momentum, Donchian, session breakouts and volatility conditioning, as defined here, are rejected on development
  data.** Under the protocol, nothing is registered for validation from B1. That is the expected honest outcome when
  a published effect (monthly trend following) is moved to intraday gold with realistic costs.
- **The cost arithmetic is a design constraint for everything that follows.** A candidate needs, before costs:

  | TF (1-ATR stop) | Gross edge needed per trade |
  |---|---|
  | 15m | > 0.42 R |
  | 1h | > 0.18 R |
  | 4h | > 0.09 R |

  Unless stops are wider or the broker's real costs (MT5 evidence) are lower than the frozen model.
- **Proposed B2** (development data, declared grid, against **matched random-level baselines**, `04` B):
  - liquidity-sweep reversal at PDH / PDL / PWH / PWL and equal highs / lows;
  - BOS continuation and CHoCH reversal;
  - FVG / OB retests.

  Each is tested at 1h and 4h with stops of 1–2 ATR, so the cost share stays ≤ 0.1 R.
- **Not proposed:** re-running B1 with other lookbacks or thresholds. Searching the same families until something
  passes is exactly the data snooping the Reality Check exists to catch (Sullivan, Timmermann & White 1999).
