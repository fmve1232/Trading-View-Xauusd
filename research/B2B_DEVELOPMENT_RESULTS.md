# Phase B2b — +$20 before −$20 (SL $1,000 / TP $1,000 at 0.5 lot), development data only (2026-11-01)

**Verdict: REJECT all 18 trials.**
- No setup's 95% range sits above break-even.
- None beats random entries by 2 standard errors.
- Benjamini-Hochberg at q = 0.10 passes 0, and White's Reality Check p = 0.996.
- One trial has a small positive point estimate. It is consistent with chance (§3).
- Nothing is proposed for registration; validation and the holdout stay sealed.

## 1. The question

The operator asked for the test after B2: "−$20 stop and +$20 profit". At 0.5 lot that means:

| | |
|---|---|
| Stop loss | $1,000 = −$20 of price (200 pips) |
| Take profit | $1,000 = +$20 of price |
| Shape | 1:1 |
| Break-even win rate | (20 + c) ÷ 40 = **52.1%**, with c the frozen cost of ≈ $0.85 per oz |
| Random entries | ≈ 50% (b ÷ (a + b)) |

So a setup needs **about 2 points over random**.

## 2. Method

**B2's declaration was reused unchanged.** It was declared in `quantum/research/b2.py`, B2b's single target was committed (`0722717f5`) before the run, and the method is in `B2_DEVELOPMENT_RESULTS.md` §2:
- the same nine setups;
- 15min and 1h decision bars;
- 15-minute paths over 3 trading days (at most 1 path per trial was still open at the horizon);
- price scaling to $4,000, with the unscaled reading logged as a sensitivity;
- frozen costs, with fills at the level or a gapping open;
- one position at a time;
- a random baseline in the same long/short mix;
- the same five-part pass rule.

**Data:** the development partition only, 2020-01-24 → 2023-01-24.

**Random entries** (every 15-minute close, 69,877 each way):

| | Win rate | Net |
|---|---|---|
| Long | 51.4% | −0.012 R |
| Short | 48.5% | −0.076 R |

Gold drifted up slightly over 2020–22.

**Refactor check.** `run()` now takes the target set as a parameter. B2 was re-run after that change into a scratch registry: all 54 trials and the baseline are **identical**.

## 3. Results

Sorted by net result. "Net R" is in units of the stop ($20). "$ / trade" is at 0.5 lot in today's dollars (net R × $1,000).

| Setup | TF | n | Win % | 95% low | Random, same mix | z vs random | Net R | $ / trade at 0.5 lot | t |
|---|---|---|---|---|---|---|---|---|---|
| FVG_RETEST | 1h | 1045 | 52.6 | 49.6 | 50.0 | +1.69 | +0.014 | +14 | +0.44 |
| SWEEP_EQ | 1h | 357 | 51.3 | 46.1 | 49.9 | +0.52 | -0.017 | -17 | -0.33 |
| SWEEP_PD | 15min | 595 | 51.3 | 47.2 | 49.8 | +0.70 | -0.019 | -19 | -0.45 |
| BOS | 1h | 507 | 51.1 | 46.7 | 50.0 | +0.47 | -0.020 | -20 | -0.44 |
| CHOCH | 1h | 498 | 50.8 | 46.4 | 49.9 | +0.42 | -0.025 | -25 | -0.54 |
| FVG_RETEST | 15min | 1832 | 50.7 | 48.4 | 50.0 | +0.58 | -0.025 | -25 | -1.04 |
| FAILED_BO | 15min | 1424 | 50.3 | 47.7 | 49.9 | +0.31 | -0.036 | -36 | -1.33 |
| OB_RETEST | 15min | 1307 | 49.6 | 46.9 | 49.9 | -0.26 | -0.048 | -48 | -1.70 |
| SWEEP_PD | 1h | 560 | 49.5 | 45.3 | 49.8 | -0.18 | -0.050 | -50 | -1.18 |
| OB_RETEST | 1h | 663 | 49.2 | 45.4 | 50.0 | -0.42 | -0.057 | -57 | -1.46 |
| BOS | 15min | 1185 | 49.2 | 46.4 | 49.9 | -0.50 | -0.062 | -62 | -2.11 |
| BREAK_PD | 1h | 561 | 48.8 | 44.7 | 50.0 | -0.57 | -0.062 | -62 | -1.46 |
| SWEEP_PW | 1h | 134 | 48.5 | 40.2 | 49.8 | -0.30 | -0.065 | -65 | -0.74 |
| CHOCH | 15min | 1140 | 48.8 | 45.9 | 49.9 | -0.73 | -0.065 | -65 | -2.16 |
| SWEEP_PW | 15min | 138 | 48.6 | 40.4 | 49.8 | -0.29 | -0.067 | -67 | -0.77 |
| BREAK_PD | 15min | 615 | 48.6 | 44.7 | 50.0 | -0.69 | -0.068 | -68 | -1.66 |
| SWEEP_EQ | 15min | 800 | 48.8 | 45.3 | 49.9 | -0.64 | -0.069 | -69 | -1.94 |
| FAILED_BO | 1h | 653 | 45.8 | 42.0 | 49.8 | -2.03 | -0.128 | -128 | -3.25 |

**The one positive trial is 1h FVG retest**, at 52.6% against a 52.1% break-even (+0.014 R, about +$14 per trade). It is not evidence of an edge:

1. **Its 95% range runs 49.6–55.6%** and includes both break-even and random.
2. **It fails four of the five rules:**
   - t = +0.44 (needs above 3);
   - z = +1.69 against random (needs above 2);
   - the Benjamini-Hochberg screen (passes 0);
   - Reality Check p = 0.996 (needs below 0.05).
3. **Luck explains it.** With 18 trials, the chance that at least one shows z ≥ 1.69 by luck alone is **57%**.
4. **The out-of-sample split test shows no rank stability.**
   - PBO is 0.43.
   - The best in-sample trial has a mean of −0.18 R per week out-of-sample, and loses out-of-sample in 80% of splits.
   - Deflated Sharpe is 0.12.
5. **Its 15-minute twin is negative** (50.7%, −0.025 R).

The declared rule needs all five parts. **Changing the rule after seeing a result is exactly the overfitting the rules exist to prevent**, so this trial is not proposed.

## 4. Family statistics

| Statistic | Value |
|---|---|
| Trials | 18 (9 setups × 2 timeframes × 1 target), all in `research/trials.jsonl` (phase B2b) |
| Pass flags, any trial | (1) 0 · (2) 0 · (3) 0 · (4) 0 · (5) 0 |
| White's Reality Check | p = 0.996; in-sample best "1h FVG_RETEST T20S20" |
| PBO (CSCV, weekly) | 0.43; the in-sample best's out-of-sample mean is −0.18 R per week, losing out-of-sample in 80% of splits |
| Deflated Sharpe of the best | 0.12 |
| Unscaled sensitivity (same dollars in 2020–22) | best +0.047 R (1h BOS, n 315, t +0.88); not used for selection |
| Lowest | 1h failed breakout: 45.8% against random 49.8% (z −2.03, −0.128 R) |

## 5. What this means for the trade

- **A 1:1 trade at ±$20 is close to a coin toss.**
  - Random entries win about 50% of the time, and lose only the cost (−$12 to −$76 per trade at 0.5 lot).
  - The best of the nine setups adds 2.6 points at most, and that much is expected from luck across 18 tries.
- **The research so far.** Every trial ran on development data only, with validation and the holdout sealed:

| Phase | Trials | Result |
|---|---|---|
| B1 | 100 | no edge |
| B2 | 54 | no edge |
| B2b | 18 | no edge |
| **Total** | **172** | **0 pass their declared rules** |

- **The live window agrees.** The "Your trade" panel on the site reads SL $1,000 / TP $1,000 directly: enter 1000 / 1000 / 0.5.
