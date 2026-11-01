# Phase B2c — the −$10 stop with +$10, +$15 and +$20 targets (development data only, 2026-11-01)

**Verdict: REJECT.** None of the 54 setup-target pairs makes money after costs, none sits above break-even at 95%, and none beats random entries by 2 standard errors.

The operator asked for "the −$10 stop with +$10, +$15 and +$20 profit".

## 1. What was run

At 0.5 lot (50 oz), $1 of price = $50:

| Target | In account dollars | How it was tested |
|---|---|---|
| +$10 before −$10 | TP $500 / SL $500 | already run in **B2** (T10) |
| **+$15 before −$10** | TP $750 / SL $500 | **new: B2c** (T15) |
| +$20 before −$10 | TP $1,000 / SL $500 | already run in **B2** (T20) |

**Why only +$15 is new.** +$10 and +$20 ran in B2 on the same data with the same code, and the run is deterministic (B2 re-ran identically after the refactor; `B2B_DEVELOPMENT_RESULTS.md` §2). Running them again would reproduce the same numbers and count those 36 trials twice, which would weaken every multiple-testing correction.

**Declaration and method.** B2c's single target was committed in `quantum/research/b2.py` (`17983cc36`) before the run. Everything else is B2's declaration (`B2_DEVELOPMENT_RESULTS.md` §2):
- the nine SMC setups, on 15min and 1h decision bars;
- 15-minute paths over 3 trading days;
- price scaling to $4,000, frozen costs, one position at a time;
- a random baseline in the same long/short mix;
- the five-part pass rule.

**Data:** 2020-01-24 → 2023-01-24 only.

## 2. The three targets side by side

| | +$10 before −$10 (TP $500) | +$15 before −$10 (TP $750) | +$20 before −$10 (TP $1,000) |
|---|---|---|---|
| Break-even after costs | 54.3% | 43.5% | 36.2% |
| Random entries, long / short | 50.5% / 49.1% | 40.7% / 38.9% | 34.0% / 32.5% |
| Best setup | 1h BOS: 51.6% (95% low 47.6), -26 $/trade | 1h SWEEP_EQ: 42.9% (95% low 38.2), -5 $/trade | 1h BOS: 35.8% (95% low 31.9), -6 $/trade |
| Trials net-positive | 0 of 18 | 0 of 18 | 0 of 18 |
| Above break-even at 95% | 0 of 18 | 0 of 18 | 0 of 18 |


"$ / trade" is at 0.5 lot in today's dollars, after costs. Break-even varies by about ±0.1 point across trials with the session mix of costs.

**How a bigger target changes the picture:**
- **The win rate needed falls** from 54% to 36%.
- **The random rate falls with it,** from 50% to 33%.
- **The gap a setup must find stays at about 3–4 points over random,** which is the cost.
- **The best setup's shortfall** is 2.7 points at +$10, 0.4 at +$15 and 0.4 at +$20. In every case it is within the noise of random, and none is significant.

## 3. +$15 before −$10 (B2c), per setup, with the same setup's +$10 and +$20 win rates from B2

| Setup | TF | n (T15) | +$10 win % | +$15 win % | +$20 win % | +$15: random, same mix | +$15: z | +$15: $ / trade at 0.5 lot |
|---|---|---|---|---|---|---|---|---|
| SWEEP_EQ | 1h | 415 | 50.7 | 42.9 | 35.0 | 39.8 | +1.28 | -5 |
| BOS | 1h | 567 | 51.6 | 41.8 | 35.8 | 39.9 | +0.92 | -20 |
| SWEEP_PD | 15min | 659 | 51.4 | 41.9 | 35.0 | 39.8 | +1.11 | -22 |
| FVG_RETEST | 15min | 3314 | 51.1 | 41.2 | 34.4 | 39.8 | +1.58 | -26 |
| FVG_RETEST | 1h | 1436 | 50.9 | 40.5 | 34.7 | 39.9 | +0.49 | -33 |
| BREAK_PD | 1h | 601 | 51.5 | 40.8 | 35.3 | 39.9 | +0.43 | -33 |
| BREAK_PD | 15min | 670 | 49.3 | 40.4 | 34.5 | 39.9 | +0.30 | -36 |
| FAILED_BO | 15min | 2305 | 49.7 | 39.4 | 32.2 | 39.8 | -0.34 | -50 |
| OB_RETEST | 1h | 797 | 48.4 | 39.0 | 32.8 | 39.9 | -0.49 | -51 |
| BOS | 15min | 1693 | 47.2 | 39.0 | 32.4 | 39.8 | -0.66 | -54 |
| CHOCH | 15min | 1776 | 49.7 | 38.8 | 33.3 | 39.8 | -0.87 | -55 |
| SWEEP_PD | 1h | 619 | 48.9 | 39.3 | 33.3 | 39.8 | -0.26 | -56 |
| FAILED_BO | 1h | 739 | 50.7 | 39.0 | 31.5 | 39.7 | -0.40 | -58 |
| OB_RETEST | 15min | 2172 | 49.6 | 38.4 | 31.6 | 39.8 | -1.41 | -62 |
| SWEEP_PW | 15min | 140 | 45.7 | 37.9 | 32.9 | 39.7 | -0.45 | -67 |
| SWEEP_EQ | 15min | 1163 | 47.9 | 38.0 | 32.4 | 39.8 | -1.26 | -69 |
| SWEEP_PW | 1h | 136 | 43.4 | 37.5 | 33.1 | 39.7 | -0.53 | -71 |
| CHOCH | 1h | 588 | 45.8 | 37.2 | 32.0 | 39.8 | -1.27 | -75 |


## 4. B2c family statistics

| Statistic | Value |
|---|---|
| Trials | 18, all in `research/trials.jsonl` (phase B2c; the registry has 214 records) |
| Pass flags, any trial | (1) 0 · (2) 0 · (3) 0 · (4) 0 · (5) 0 |
| Net-positive trials | 0 of 18 |
| Best z against random | +1.58 (15min FVG retest). The chance of at least one this high among 18 by luck is 65%. |
| White's Reality Check | p = 1.000 |
| PBO (CSCV, weekly) | 0.11. The in-sample best (1h SWEEP_EQ) loses out-of-sample in 99% of splits (mean −0.32 R per week). |
| Deflated Sharpe of the best | 0.01 |
| Unscaled sensitivity (same dollars in 2020–22) | best −0.009 R (15min SWEEP_PD, n 499); every trial negative |

## 5. What this means for the trade

- **With a $500 stop at 0.5 lot,** no tested setup gets TP $500, $750 or $1,000 hit first often enough to pay the costs.
- **Every one behaves like a random entry** in the same direction. The closest come within 0.4 points of break-even at +$15 and +$20, and that is still a loss.
- **The research so far.** All on development data only, with validation and the holdout sealed:

| Phase | Trials | Result |
|---|---|---|
| B1 | 100 | no edge |
| B2 | 54 | no edge |
| B2b | 18 | no edge |
| B2c | 18 | no edge |
| **Total** | **190** | **0 pass their declared rules** |

- **The live window can be checked on the site.** In the "Your trade" card, enter SL 500, TP 500 / 750 / 1000 and lot 0.5.
