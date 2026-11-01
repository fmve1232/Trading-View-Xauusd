# Phase B3 — trend + confirmation + SMC sequences, on the −$10 stop with +$10 / +$15 / +$20 (development data only, 2026-11-01)

**Verdict: REJECT all 210 trials. No combination comes near 90%.**
- The highest success rates were 57.1%, 48.6% and 43.5%, on 84, 37 and 23 trades.
- Trend alignment, confirmation entries and the SMC sequence each move the success rate by about ±1 point against random entries treated the same way.
- No trial passes the declared rule.
- The family checks say the best results are luck: Reality Check p = 1.000; PBO 0.73, with the best in-sample trial losing out-of-sample in 99% of splits.
- Nothing is proposed for registration; validation and the holdout stay sealed.

## 1. The request

The operator, 2026-11-01:

> "−$10 stop with +$10, +$15 and +$20 profit with success rate more than 90% … improving the code structure, API, sequence, trend / confirmation."

At 0.5 lot that is SL $500 with TP $500, $750 or $1,000.

**What can and cannot be tested.**
- **Not testable:** the code structure and the data API do not decide where price goes, so they cannot raise a success rate. The Twelve Data series is cross-checked against Dukascopy (`audit/tools/xcheck_dukascopy.py`).
- **Testable:** what decides a trade, namely **trend alignment, a confirmation entry, and the sequence of SMC events**. B3 tests those, in combination.
- **Departure from the roadmap.** It planned B3 only for components that had passed alone (`04`). None had, and these combinations were run at the operator's request.

## 2. Declared before the run

Everything was declared in `quantum/research/b3.py` and committed (`808bc31b3`) before the first run. Anything not listed is B2's declaration.

**Setups**
- B2's nine setups.
- Two SMC sequences:
  - **liquidity sweep → structure break** in the trade's direction within 12 bars;
  - **then the first FVG retest** within 20 bars.

**Trend filter**
- Trade only with the 1h trend: close, EMA50 and EMA200 in order.
- Read from the last *completed* 1h bar, so there is no look-ahead (tested).

**Confirmation entry**
- After the signal, wait up to 2 hours for a 15-minute close $3 (scaled) in the trade's direction, before one $3 against.
- Enter at that close; the stop and the targets are measured from the new entry.
- Otherwise, no trade.

**Grid** (210 trials)
- The nine setups × {confirmation only, trend only, trend + confirmation}.
- The two sequences × all four combinations.
- × 15min / 1h × 3 targets.
- B2's unfiltered runs are not repeated.

**Baseline.** Random decisions at every 2nd 15-minute close, passed through **the same filter and confirmation**, so each ingredient is measured against itself without a setup.

**Rule.** B2's five-part pass rule. The 90% target is reported beside it.

**Run note.**
- The first run logged all 210 trials, then stopped while computing the family statistics: a trial with no trades produced an empty series with no date index.
- Only that aggregation step was fixed.
- The re-run went to a scratch registry. **All 210 trial records match the logged ones exactly**, so the official log holds each trial once.

## 3. Success rates against your 90% target

| −$10 stop at 0.5 lot | +$10 (TP $500) | +$15 (TP $750) | +$20 (TP $1,000) |
|---|---|---|---|
| **Your target** | 90% | 90% | 90% |
| Break-even after costs | 54.3% | 43.4% | 36.2% |
| Random entries (same filter / confirmation), average | 49.5% | 39.7% | 33.5% |
| Median success rate of the trials | 49.0% | 39.7% | 33.3% |
| Highest, any sample size | 57.1% (n 84; 95% 46–67%) | 48.6% (n 37; 95% 33–64%) | 43.5% (n 23; 95% 26–63%) |
| Highest with 100+ trades | 56.5% (n 108; 1h SEQ_SWEEP_MSS_FVG · none + confirm) | 45.9% (n 172; 15min SEQ_SWEEP_MSS · trend) | 38.6% (n 171; 15min SEQ_SWEEP_MSS · trend) |
| Trials reaching 90% | 0 of 70 | 0 of 70 | 0 of 70 |
| Trials net-positive (point estimate) | 6 of 67 | 6 of 67 | 14 of 67 |


**The best rows are small samples.**
- 57.1% on 84 trades has a 95% range of 46–67%, and 43.5% on 23 trades has 26–63%. Both include the random rate.
- With 100+ trades, the best are 56.5% (+$10), 45.9% (+$15) and 38.6% (+$20).
- Even the top of those ranges is far below 90%.

## 4. The best trials per target

**+$10 before −$10** (top 6 by success rate, n ≥ 30)

| Setup · filter | TF | n | Success | 95% range | Random, same treatment | z | $ / trade at 0.5 lot |
|---|---|---|---|---|---|---|---|
| SEQ_SWEEP_MSS_FVG · trend | 1h | 84 | 57.1% | 46–67% | 50.4% | +1.23 | +41 |
| SEQ_SWEEP_MSS_FVG · none + confirm | 1h | 108 | 56.5% | 47–65% | 48.4% | +1.67 | +22 |
| FAILED_BO · trend | 1h | 75 | 56.0% | 45–67% | 50.5% | +0.96 | +18 |
| SEQ_SWEEP_MSS · trend | 15min | 177 | 55.9% | 49–63% | 50.4% | +1.47 | +18 |
| CHOCH · trend + confirm | 1h | 94 | 54.3% | 44–64% | 49.3% | +0.97 | +3 |
| FAILED_BO · trend + confirm | 1h | 37 | 54.1% | 38–69% | 49.3% | +0.58 | +5 |

**+$15 before −$10** (top 6 by success rate, n ≥ 30)

| Setup · filter | TF | n | Success | 95% range | Random, same treatment | z | $ / trade at 0.5 lot |
|---|---|---|---|---|---|---|---|
| SEQ_SWEEP_MSS_FVG · trend + confirm | 1h | 37 | 48.6% | 33–64% | 39.4% | +1.15 | +66 |
| SEQ_SWEEP_MSS · trend | 15min | 172 | 45.9% | 39–53% | 40.8% | +1.37 | +33 |
| SEQ_SWEEP_MSS_FVG · none + confirm | 1h | 106 | 45.3% | 36–55% | 38.7% | +1.40 | +23 |
| SWEEP_EQ · none + confirm | 1h | 190 | 44.7% | 38–52% | 38.7% | +1.71 | +18 |
| CHOCH · trend + confirm | 1h | 94 | 44.7% | 35–55% | 39.4% | +1.04 | +18 |
| SEQ_SWEEP_MSS_FVG · trend | 15min | 189 | 42.9% | 36–50% | 40.8% | +0.58 | -13 |

**+$20 before −$10** (top 6 by success rate, n ≥ 30)

| Setup · filter | TF | n | Success | 95% range | Random, same treatment | z | $ / trade at 0.5 lot |
|---|---|---|---|---|---|---|---|
| CHOCH · trend + confirm | 1h | 94 | 41.5% | 32–52% | 33.6% | +1.62 | +82 |
| SWEEP_PW · none + confirm | 15min | 67 | 38.8% | 28–51% | 32.6% | +1.08 | +28 |
| SEQ_SWEEP_MSS · trend | 15min | 171 | 38.6% | 32–46% | 34.5% | +1.14 | +37 |
| SWEEP_PW · none + confirm | 1h | 52 | 38.5% | 26–52% | 32.6% | +0.91 | +34 |
| SWEEP_EQ · none + confirm | 1h | 187 | 38.0% | 31–45% | 32.6% | +1.56 | +28 |
| CHOCH · trend | 1h | 222 | 37.8% | 32–44% | 34.4% | +1.06 | +27 |


**These look better than they are.**
- No z reaches 2; the highest of all 210 is +1.89.
- If 210 trials had no edge at all, the luckiest one would typically show z ≈ 2.8. These trials overlap, so the luck figure is somewhat lower, but the best result still sits inside it.
- The positive "$ / trade" figures (26 of 201 trials with trades) are point estimates on small samples. Their t-statistics are at most 1.07, against the 3 required.

## 5. What each ingredient does

Average success rate minus random decisions given the same treatment (trials with n ≥ 30):

| Ingredient | Trials (n ≥ 30) | Success minus random, average | Read |
|---|---|---|---|
| 1h trend filter only | 60 | -1.19 points | slightly worse |
| Confirmation entry only | 66 | +0.53 points | no help |
| Trend filter + confirmation | 51 | -0.03 points | no help |
| Sequences, no filter, no confirmation | 12 | -0.37 points | no help |
| SMC sequences (sweep → MSS → FVG), all treatments | 48 | +0.84 points | noise-level |

**Trend alignment**
- Random entries taken with the 1h trend win 50.2–50.7% at +$10, about the same as without the filter (49.1–50.5%).
- At these distances (+$10 before −$10 is about ±0.25% of price), the trend direction tells nothing about the next $10.

**Confirmation**
- Waiting for +$3 before entering does not raise the chance of the *next* +$10 coming before −$10. Random confirmed entries reach 47.7–49.3%.
- It shifts the entry by $3 and skips about half the trades.

**SMC sequences**
- They are within ±1 point of random.

## 6. Family statistics

| Statistic | Value |
|---|---|
| Trials | 210 (9 had no trades), all in `research/trials.jsonl` (phase B3; 424 records in total) |
| Pass flags, any trial | (1) 0 · (2) 0 · (3) 0 · (4) 0 · (5) 0 |
| Operator target (≥ 90%) | 0 trials, by point estimate or by 95% lower bound |
| White's Reality Check | p = 1.000 |
| PBO (CSCV, weekly) | 0.73 (high: in-sample ranks do not hold out-of-sample). The in-sample best loses out-of-sample in 99% of splits. |
| Deflated Sharpe of the best | 0.004 |

## 7. What this means

- **No setup, trend filter or confirmation tested here delivers 90%**, or even a reliable +3 points over random, for a −$10 stop with a +$10 to +$20 target.
- **Across every phase:**

| Phase | Trials |
|---|---|
| B1 | 100 |
| B2 | 54 |
| B2b | 18 |
| B2c | 18 |
| B3 | 210 |
| **Total** | **400**, on development data, **0 pass**, and none comes near 90% |

- **A trade that succeeds 90% of the time at a −$10 stop exists only with a small target.** +$2 before −$10 succeeds about 82% of the time even at random, and it still loses money because it needs 90.4%.
- **No change to code, API or entry rules changes that arithmetic.** It is fixed by where the stop and target sit relative to how gold moves.

**What is honestly left** (each needs the operator's decision and its own declaration):
- **Different information.** Order flow / depth, options positioning, or news timing. This needs data the project does not have.
- **Longer horizons**, where the literature finds trend premia. Expect small edges, not 90%.
- **Using the site as a filter, not a signal source:** it says WAIT, and the "Your trade" card shows the measured odds before any trade.
