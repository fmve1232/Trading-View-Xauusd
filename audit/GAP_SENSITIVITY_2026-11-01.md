# Gap-stop and execution sensitivity — HYPOTHETICAL simulation (2026-11-01)

> **Every number in this document is a simulation on stored historical prices.** None is a broker fill, none is
> forward-test evidence, and nothing here changes the official forward record. The frozen web.7 rule is unchanged.

**Setup:**

- **Tool:** `audit/tools/exec_sensitivity.py`. It runs offline on a copy of `market-data` @ `0bb2c8a96`, using
  Twelve Data XAU/USD.
- **Signals:** each arm's own code produces them on the stored window of each timeframe:
  - 5m: 2026-09-09 → 10-30;
  - 15m: 08-05 → 10-30;
  - 1h: 03-02 → 10-30.
- **Costs:** the frozen model (session spread + 2 × 0.20 slippage + $7 per lot) in every scenario. The scenarios
  add only the stated extra.
- **R** is net, per trade.

## 1. Scenarios

| Scenario | Execution assumption |
|---|---|
| web.6 | a stop that the bar opened beyond fills at the stop price (the old, optimistic rule) |
| **web.7** | **the approved rule as deployed**: fills at the open |
| gap +x | web.7, plus x points of extra adverse slippage on each gap exit (`SL_GAP` / `BE_GAP`), on the quantity still open |
| stop +x | web.7, plus x points of extra adverse slippage on every stop exit (SL, BE and gaps); stop orders fill as market orders |
| 5-minute path | 15m / 1h trades re-walked on 5-minute bars with the web.7 rule: finer intrabar order, breakeven live from the next 5-minute bar |
| tick-level | **NOT RUN.** No tick data is available to this project. Dukascopy ticks are restricted from redistribution and blocked from this environment; Twelve Data's free tier has no ticks |

The extra slippage is subtracted from the exit price. It does not move the exit time, so the trade path is unchanged
and the adjustment is exact.

## 2. Results by arm (mean R per trade unless stated)

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

**5-minute path check (15m and 1h trades fully inside the 5-minute store)**

| TF / arm | Covered trades | Exits changed | Chart-bar rule: mean R / sum R | 5-minute path: mean R / sum R |
|---|---|---|---|---|
| 1h/treatment | 5 | 0 | -0.512 / -2.56 | -0.512 / -2.56 |
| 1h/challenger | 4 | 0 | -0.373 / -1.49 | -0.373 / -1.49 |
| 1h/h2 | 2 | 1 | -0.260 / -0.52 | -0.260 / -0.52 |
| 1h/h3 | 7 | 2 | -0.687 / -4.81 | -0.687 / -4.81 |
| 1h/h4 | 171 | 55 | -0.136 / -23.19 | -0.139 / -23.80 |
| 1h/h6 | 8 | 1 | -0.704 / -5.63 | -0.704 / -5.63 |
| 15m/treatment | 7 | 2 | +0.109 / +0.76 | +0.109 / +0.76 |
| 15m/control | 3 | 1 | -0.588 / -1.76 | -0.588 / -1.76 |
| 15m/challenger | 7 | 2 | +0.109 / +0.76 | +0.109 / +0.76 |
| 15m/h2 | 4 | 0 | -1.040 / -4.16 | -1.040 / -4.16 |
| 15m/h3 | 29 | 11 | -0.348 / -10.08 | -0.348 / -10.08 |
| 15m/h4 | 595 | 199 | -0.119 / -70.69 | -0.118 / -70.16 |
| 15m/h5 | 1 | 0 | -1.036 / -1.04 | -1.036 / -1.04 |
| 15m/h6 | 12 | 5 | -0.252 / -3.03 | -0.252 / -3.03 |


## 3. Finer intrabar order: the 5-minute path

Only trades whose whole holding period lies inside the 5-minute store (from 2026-09-09) are compared. Trades are
re-evaluated one at a time, so a different exit is not allowed to change later entries.

| TF / arm | Covered trades | P&L changed (> 0.005 pts) | Label only | Chart-bar rule: mean R / sum R | 5-minute path: mean R / sum R | Difference, sum R |
|---|---|---|---|---|---|---|
| 1h/treatment | 5 | 0 | 0 | -0.512 / -2.56 | -0.512 / -2.56 | +0.00 |
| 1h/challenger | 4 | 0 | 0 | -0.373 / -1.49 | -0.373 / -1.49 | +0.00 |
| 1h/h2 | 2 | 0 | 0 | -0.260 / -0.52 | -0.260 / -0.52 | +0.00 |
| 1h/h3 | 7 | 0 | 0 | -0.687 / -4.81 | -0.687 / -4.81 | +0.00 |
| 1h/h4 | 171 | 4 | 0 | -0.136 / -23.19 | -0.139 / -23.80 | -0.61 |
| 1h/h6 | 8 | 0 | 0 | -0.704 / -5.63 | -0.704 / -5.63 | +0.00 |
| 15m/treatment | 7 | 0 | 0 | +0.109 / +0.76 | +0.109 / +0.76 | +0.00 |
| 15m/control | 3 | 0 | 0 | -0.588 / -1.76 | -0.588 / -1.76 | +0.00 |
| 15m/challenger | 7 | 0 | 0 | +0.109 / +0.76 | +0.109 / +0.76 | +0.00 |
| 15m/h2 | 4 | 0 | 0 | -1.040 / -4.16 | -1.040 / -4.16 | +0.00 |
| 15m/h3 | 29 | 0 | 0 | -0.348 / -10.08 | -0.348 / -10.08 | +0.00 |
| 15m/h4 | 595 | 15 | 0 | -0.119 / -70.69 | -0.118 / -70.16 | +0.53 |
| 15m/h5 | 1 | 0 | 0 | -1.036 / -1.04 | -1.036 / -1.04 | +0.00 |
| 15m/h6 | 12 | 0 | 0 | -0.252 / -3.03 | -0.252 / -3.03 | +0.00 |


## 4. Reading

1. **The gap rule's effect is real but small.**
   - Gap exits occur in **H4** (13 / 12 / 8 on 1h / 15m / 5m), in **H3** on 1h (1) and in **H5** on 15m (1). No
     other arm had one.
   - The engine's own BUY / SELL (treatment, control, challenger) and H2 / H6 had **no gap exits**, so web.6 and
     web.7 are identical for them.
2. **Extra gap slippage barely moves anything**, because gap exits are rare: +2 points on every gap exit changes
   H4's mean by at most 0.002 R.
3. **Extra slippage on every stop exit matters more**, because most exits are stops. +0.5 points per stop exit
   costs:

   | Arm | Mean R change |
   |---|---|
   | 5m treatment | −0.046 |
   | 5m H3 | −0.116 |
   | 15m H4 | −0.008 |

   The smaller the stop distance, the larger the effect in R, so 5m is the most sensitive timeframe.
4. **No conclusion changes under any scenario.**
   - **H4** is negative in every scenario on every timeframe.
   - **Treatment, challenger, H2, H5 and H6** have fewer than 40 trades per timeframe; their sign is not
     established in any scenario.
5. **Finer intrabar order** (5-minute path) changes 4 of 171 (1h H4) and 15 of 595 (15m H4) covered trades, with a
   net −0.61 / +0.53 R. The chart-bar approximation (stop first on a two-way bar) is therefore not a material source
   of error on this sample.

## 5. Limitations

- In-sample windows of 2–8 months. One market regime dominates.
- No tick data. The open is a lower bound on gap damage.
- Reopen opens are rebuilt from 5-minute bars (D-09).
- Slippage values are illustrative, not measured; the broker evidence in `audit/COST_PROFILES.md` §4 E4–E5 would
  measure them.
- The 5-minute check covers only trades after 2026-09-09, and re-evaluates trades independently.

## 6. Recommendation

- **Keep web.7 as deployed.**
- When the operator's MT5 history arrives, compare its real stop fills (E5) with the "stop +x" rows. If real stop
  slippage is consistently above 0.2 points, a cost amendment can be proposed then. It needs written approval, and
  it must not be chosen by looking at forward results.
