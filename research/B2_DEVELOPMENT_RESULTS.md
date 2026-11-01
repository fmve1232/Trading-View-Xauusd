# Phase B2 — SMC setups against the operator's trade (development data only, 2026-11-01)

**Verdict: REJECT all 54 trials.**
- No setup clears break-even after costs on any of the three targets.
- None beats random entries in the same direction by 2 standard errors.
- None survives the family screens: Benjamini-Hochberg at q = 0.10 passes 0; White's Reality Check p = 1.000; Deflated Sharpe of the best is 0.
- Nothing is proposed for registration, and validation and the holdout stay sealed.

## 1. The question

The operator's trade (stated 2026-11-01):

- **SL $500 / TP $1,000 at 0.5 lot.** At 0.5 lot (50 oz), $1 of price = $50, so this is **−$10 / +$20 of price** from the decision price.
- In the operator's words, "the market should move $10 to $20 my way without hitting my SL."

Three targets were declared in code and committed (`5d29a6394`) before the first run:

| Target | Event | Why | Break-even after costs |
|---|---|---|---|
| **T20** | +$20 before −$10 | the operator's trade (primary) | **36.2%** |
| T10 | +$10 before −$10 | the lower end of "$10 to $20" | 54.2% |
| T2 | +$2 before −$10 | the earlier statement (SL $500 / TP $100) | 90.4% |

- **Break-even** = (SL + cost) ÷ (TP + SL), with the frozen engine cost (≈ $0.77–0.97 per oz, ≈ $40–48 per trade at 0.5 lot).
- **Random entries** reach T20 about **33.3%** of the time. That is coin-flip arithmetic: $10 ÷ ($20 + $10).

So the trade needs a setup that wins **about 3 points more often than random**.

That is a much smaller gap than the +$2 / −$10 trade needs (about 8 points). The 2:1 structure is sound. The obstacle is cost, and finding 3 real points.

## 2. Method (declared in `quantum/research/b2.py` before running)

**Data**
- Development partition only: 2020-01-24 → 2023-01-24, Twelve Data XAU/USD.
- Decision bars are 15min and 1h. Paths are walked on 15-minute bars.

**Scaling**
- Gold traded at ~$1,450–2,070 then and ~$4,000 now.
- Distances and costs are both scaled by price ÷ 4,000, so T20 means +0.50% before −0.25% at the same relative cost.
- The unscaled reading (the same dollars in 2020–22, a relatively larger move) is logged as a sensitivity. It is never used for selection.

**Setups** (decided at the bar close from past bars only; no look-ahead, tested in `tests/test_research_b2.py`)
- Liquidity sweeps of the prior day's high/low, the prior week's high/low, and equal highs/lows.
- First close beyond the prior day's high/low.
- BOS (break of structure, continuation).
- CHoCH (change of character, reversal).
- FVG retest (fair value gap).
- Order-block retest.
- Failed breakout.
- Market-profile acceptance (matrix row 29) is **NOT TESTED**: the series has no volume.

**Execution**
- Horizon: 3 trading days. No path was left open at the horizon.
- A bar touching both levels counts as a loss unless it opened beyond the target.
- Fills are at the level, or at a gapping open.
- One position at a time, so outcomes do not overlap.
- Frozen engine costs, charged once.

**Baseline**
- Every 15-minute close of the partition, taken long and short (69,877 each).
- Weighted by each setup's own long/short mix.

| Random entries | Long | Short | Driftless theory |
|---|---|---|---|
| T20 | 34.0% | 32.5% | 33.3% |
| T10 | 50.5% | 49.1% | 50% |
| T2 | 81.9% | 82.0% | 83.3% |

## 3. Results

Each table is sorted by net result. "Net R" is in units of the stop. "$ / trade" is at 0.5 lot in today's dollars. The pass rule needs **all five** of:
1. the 95% lower bound above break-even;
2. t > 3;
3. z > 2 against random;
4. the Benjamini-Hochberg screen at q = 0.10;
5. Reality Check p < 0.05.

### T20: +$20 before −$10 (your trade). Break-even ≈ 36.2%

| Setup | TF | n | Win % | 95% low | Random, same mix | z vs random | Net R | $ / trade at 0.5 lot | t |
|---|---|---|---|---|---|---|---|---|---|
| BOS | 1h | 553 | 35.8 | 31.9 | 33.3 | +1.24 | -0.011 | -6 | -0.18 |
| BREAK_PD | 1h | 590 | 35.3 | 31.5 | 33.3 | +1.00 | -0.021 | -11 | -0.36 |
| SWEEP_EQ | 1h | 397 | 35.0 | 30.5 | 33.2 | +0.76 | -0.033 | -16 | -0.46 |
| FVG_RETEST | 1h | 1341 | 34.7 | 32.2 | 33.3 | +1.07 | -0.040 | -20 | -1.00 |
| SWEEP_PD | 15min | 649 | 35.0 | 31.4 | 33.2 | +0.96 | -0.043 | -21 | -0.75 |
| BREAK_PD | 15min | 656 | 34.5 | 30.9 | 33.3 | +0.63 | -0.047 | -24 | -0.84 |
| FVG_RETEST | 15min | 2836 | 34.4 | 32.7 | 33.3 | +1.30 | -0.050 | -25 | -1.85 |
| CHOCH | 15min | 1644 | 33.3 | 31.1 | 33.2 | +0.10 | -0.079 | -40 | -2.21 |
| SWEEP_PD | 1h | 606 | 33.3 | 29.7 | 33.2 | +0.07 | -0.093 | -47 | -1.61 |
| SWEEP_PW | 1h | 136 | 33.1 | 25.7 | 33.2 | -0.02 | -0.095 | -47 | -0.77 |
| OB_RETEST | 1h | 766 | 32.8 | 29.5 | 33.3 | -0.31 | -0.096 | -48 | -1.88 |
| SWEEP_PW | 15min | 140 | 32.9 | 25.6 | 33.1 | -0.07 | -0.099 | -49 | -0.81 |
| SWEEP_EQ | 15min | 1041 | 32.4 | 29.6 | 33.2 | -0.59 | -0.116 | -58 | -2.64 |
| BOS | 15min | 1551 | 32.4 | 30.1 | 33.2 | -0.73 | -0.116 | -58 | -3.23 |
| FAILED_BO | 15min | 2032 | 32.2 | 30.2 | 33.2 | -0.92 | -0.121 | -60 | -3.82 |
| CHOCH | 1h | 578 | 32.0 | 28.3 | 33.2 | -0.63 | -0.123 | -61 | -2.11 |
| OB_RETEST | 15min | 1928 | 31.6 | 29.6 | 33.3 | -1.55 | -0.134 | -67 | -4.17 |
| FAILED_BO | 1h | 723 | 31.5 | 28.3 | 33.1 | -0.91 | -0.146 | -73 | -2.78 |

### T10: +$10 before −$10. Break-even ≈ 54.2%

| Setup | TF | n | Win % | 95% low | Random, same mix | z vs random | Net R | $ / trade at 0.5 lot | t |
|---|---|---|---|---|---|---|---|---|---|
| BOS | 1h | 583 | 51.6 | 47.6 | 49.9 | +0.86 | -0.053 | -26 | -1.27 |
| BREAK_PD | 1h | 610 | 51.5 | 47.5 | 49.9 | +0.80 | -0.056 | -28 | -1.38 |
| SWEEP_PD | 15min | 665 | 51.4 | 47.6 | 49.7 | +0.87 | -0.059 | -30 | -1.52 |
| FVG_RETEST | 1h | 1526 | 50.9 | 48.3 | 49.8 | +0.79 | -0.063 | -31 | -2.41 |
| FVG_RETEST | 15min | 4016 | 51.1 | 49.6 | 49.8 | +1.71 | -0.063 | -32 | -3.93 |
| SWEEP_EQ | 1h | 430 | 50.7 | 46.0 | 49.8 | +0.38 | -0.069 | -35 | -1.43 |
| FAILED_BO | 1h | 751 | 50.7 | 47.2 | 49.7 | +0.58 | -0.077 | -39 | -2.07 |
| CHOCH | 15min | 1994 | 49.7 | 47.5 | 49.8 | -0.07 | -0.085 | -42 | -3.62 |
| FAILED_BO | 15min | 2623 | 49.7 | 47.8 | 49.8 | -0.04 | -0.091 | -45 | -4.53 |
| OB_RETEST | 15min | 2561 | 49.6 | 47.7 | 49.8 | -0.16 | -0.091 | -46 | -4.58 |
| BREAK_PD | 15min | 676 | 49.3 | 45.5 | 49.8 | -0.30 | -0.101 | -50 | -2.61 |
| OB_RETEST | 1h | 823 | 48.4 | 45.0 | 49.8 | -0.84 | -0.110 | -55 | -3.10 |
| SWEEP_PD | 1h | 626 | 48.9 | 45.0 | 49.7 | -0.43 | -0.115 | -58 | -2.84 |
| SWEEP_EQ | 15min | 1320 | 47.9 | 45.2 | 49.8 | -1.37 | -0.125 | -63 | -4.54 |
| BOS | 15min | 1896 | 47.2 | 44.9 | 49.8 | -2.31 | -0.143 | -72 | -6.13 |
| SWEEP_PW | 15min | 140 | 45.7 | 37.7 | 49.7 | -0.94 | -0.163 | -82 | -1.84 |
| CHOCH | 1h | 592 | 45.8 | 41.8 | 49.8 | -1.95 | -0.164 | -82 | -3.99 |
| SWEEP_PW | 1h | 136 | 43.4 | 35.3 | 49.7 | -1.48 | -0.205 | -102 | -2.27 |

### T2: +$2 before −$10. Break-even ≈ 90.5%

| Setup | TF | n | Win % | 95% low | Random, same mix | z vs random | Net R | $ / trade at 0.5 lot | t |
|---|---|---|---|---|---|---|---|---|---|
| BREAK_PD | 1h | 615 | 83.1 | 79.9 | 82.0 | +0.72 | -0.086 | -43 | -4.71 |
| FVG_RETEST | 1h | 1733 | 82.9 | 81.1 | 82.0 | +1.02 | -0.088 | -44 | -8.09 |
| FVG_RETEST | 15min | 6421 | 82.6 | 81.6 | 82.0 | +1.23 | -0.094 | -47 | -15.70 |
| FAILED_BO | 15min | 3186 | 81.7 | 80.3 | 82.0 | -0.42 | -0.101 | -50 | -11.81 |
| OB_RETEST | 15min | 3444 | 81.6 | 80.3 | 82.0 | -0.56 | -0.104 | -52 | -12.92 |
| CHOCH | 15min | 2388 | 81.5 | 79.9 | 82.0 | -0.58 | -0.107 | -54 | -10.99 |
| SWEEP_PD | 15min | 670 | 81.0 | 77.9 | 82.0 | -0.64 | -0.112 | -56 | -6.13 |
| BOS | 1h | 599 | 80.8 | 77.5 | 82.0 | -0.75 | -0.113 | -57 | -5.80 |
| SWEEP_EQ | 1h | 448 | 80.8 | 76.9 | 82.0 | -0.65 | -0.113 | -57 | -5.07 |
| OB_RETEST | 1h | 859 | 80.4 | 77.7 | 82.0 | -1.17 | -0.113 | -57 | -6.85 |
| SWEEP_EQ | 15min | 1651 | 79.8 | 77.8 | 82.0 | -2.28 | -0.123 | -61 | -10.20 |
| FAILED_BO | 1h | 768 | 79.3 | 76.3 | 82.0 | -1.95 | -0.131 | -66 | -7.42 |
| BOS | 15min | 2383 | 78.9 | 77.3 | 82.0 | -3.87 | -0.136 | -68 | -13.32 |
| CHOCH | 1h | 599 | 78.8 | 75.3 | 82.0 | -2.03 | -0.137 | -68 | -6.81 |
| SWEEP_PW | 15min | 140 | 78.6 | 71.1 | 82.0 | -1.05 | -0.139 | -70 | -3.32 |
| SWEEP_PD | 1h | 629 | 78.4 | 75.0 | 82.0 | -2.36 | -0.144 | -72 | -7.31 |
| SWEEP_PW | 1h | 136 | 75.7 | 67.9 | 82.0 | -1.90 | -0.150 | -75 | -2.97 |
| BREAK_PD | 15min | 685 | 76.9 | 73.6 | 82.0 | -3.44 | -0.163 | -81 | -8.43 |

## 4. Family statistics

| Statistic | Value |
|---|---|
| Trials | 54 (9 setups × 2 timeframes × 3 targets), all in `research/trials.jsonl` (phase B2) |
| Pass flags, any trial | (1) 0 · (2) 0 · (3) 0 · (4) 0 · (5) 0 |
| Best z against random | +1.71 (15min FVG retest, T10). With 54 trials, about 6 are expected above +1.24 by chance alone. |
| White's Reality Check (benchmark: no trade) | p = 1.000; in-sample best "1h BOS T20" |
| PBO (CSCV, 8 groups, weekly) | 0.21. The in-sample best's out-of-sample mean is −0.36 R per week, and it lost out-of-sample in 100% of splits |
| Deflated Sharpe of the best | 0.00 |
| Unscaled sensitivity (same dollars in 2020–22) | best net +0.024 R (15min SWEEP_PW T20, n 136, t +0.20); not used for selection |

## 5. What this means for the trade

1. **On 2020–22 data, every SMC setup tested here behaves like a random entry** in the same direction:
   - win rates sit within about ±2 points of the random rate;
   - the differences go both ways;
   - their spread matches chance.
2. **Your 2:1 trade is the right shape.**
   - At random, T20 loses only the cost: about −0.06 to −0.12 R, or roughly −$30 to −$60 per trade at 0.5 lot.
   - The +$2 / −$10 trade, by contrast, loses about −$50 per trade, and needs a 90% win rate.
   - A real edge of about +3 to +4 points over random would make T20 profitable.
3. **Proving such an edge takes many trades.**
   - To show +3 points over a 33% base at z = 3 takes about 2,200 trades.
   - That is years of 1h decisions, which is why "it worked last month" is not evidence.
4. **The live window agrees.**
   - The site's "Your trade" panel measures T20 on Sep–Oct 2026 (in-sample, 15m chart): H4 playbook 31.0%, recorded forward trades 26.1% (n = 161), random 33%, against a 36.6% break-even.

## 6. What next (needs the operator's decision)

- **Nothing here goes forward.** No registration is proposed; validation (2023-01 → 2024-06) and the holdout stay sealed.
- **Options:**
  - (a) Stop the setup search for this trade, keep the site saying WAIT, and use the "Your trade" panel to check any idea before trading it.
  - (b) A B3 study of whether combining features that were individually directionless can add up. The prior is weak, and it costs more trials.
  - (c) Change the question to one where a tested edge exists in the literature: daily-horizon trend (B1b found only the always-long drift). Expectations there are small.
- Each option would be declared in code before it runs, as B1 and B2 were.

**Reproduce:** `PYTHONPATH=. python -m quantum.research.b2 <research-data checkout> out.json --registry <scratch registry>`. Results: `research/results/b2_development_2026-11-01.json`.
