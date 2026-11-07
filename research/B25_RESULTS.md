# B25: execution timing after a $15 confirmation (2026-11-07)

**Registration:** `research/registrations/B25.json`, committed before the code (`fa20f3bc9`). Code and tests:
`9dfc11ce1`. Results: `research/results/b25_2026-11-07.json`.

**The question (operator, 2026-11-07):**
- Does the price you can actually get after a confirmation keep the odds?
- Does an earlier executable entry beat the 15-minute close?

## The answer

| Question | Answer |
|---|---|
| Does the site's delay hurt? | **No.** Entering 15, 30 or 60 minutes after the confirming close scores the same as, or slightly better than, the close (all four alert types pooled: 46.4% at the close; 47.5% / 48.9% / 47.9% later; 2,486 trades). On the 5m bars, the site's real median delay (B10) scored 46.6% against 39.8% at the close. |
| The engine's 60% → 30% drop at +15 minutes | **Noise of 20 trades.** The same trades score 50% at +30 and +60 minutes. In 2026, +15 minutes gives exactly the close's rate (52.4% of 21). |
| Does a retest entry help? | **No.** It fills 80% of the time. Of the 495 trades it misses, 406 would have won. Per confirmed trigger it nets −$0.86 against −$0.78 for the close (2026: −$1.17 against −$0.70). |
| Does an earlier entry help (a stop order at the $15 level, or a 5m close)? | **No.** The 15m stop order wins 39.9% (the close 46.4%), and 15% of its fills are moves that never confirmed. On 5m bars the stop order is 41.7% against 39.8%, and the 5m close 40.2%: no gain. |
| What sets the odds? | The geometry of +$15 before −$13 (about 46%). Entry timing within an hour does not change it. |

## The site's real delay (the "first executable price")

From the site workflow's run history (500 runs, 1–7 Nov 2026, 476 bar closes in market hours):

- the site publishes a median **7.0 minutes** after a 15m close;
- 90% within 8.4, 95% within 22.4, worst 67.7;
- 6.5% of closes wait more than 15 minutes.

On the store's 5m bars, B10 (the 5m close 10 minutes after the confirmation) stands for the median delay and B25 for the 95th percentile.

## Data

| | Period | Bars | Notes |
|---|---|---|---|
| P1 (primary) | 2020-04-01 → 2023-01-24 | 15m | Development; distances scaled to price / 4000, as all studies |
| P2 | 2026-03-01 → 2026-11-02 | 15m | After the holdout, never used to choose a rule; literal $ (gold $3,873–5,414) |
| P3 | 2026-09-09 → 2026-11-02 | 5m (live store) | Its 15m resample matches the research 15m closes on 3,505 bars: median difference $0.00, 0.06% above $0.10 |

No validation or holdout bar was read.

## Primary test (as registered): paired net difference against A, all alert types (P1), Holm

| Model | Pairs (days) | Net difference, $ / oz | Holm p | Same sign in 2026? | Registered verdict |
|---|---|---|---|---|---|
| B0: the next bar's open | 2,486 (689) | −0.03 | 0.63 | no (+0.17) | no difference |
| B15: 15 minutes later | 2,486 (689) | +0.31 | 0.29 | yes (+0.88) | no difference |
| C: retest limit | 1,991 (674) | +2.18 | < 0.001 | yes (+2.27) | "differs" (see the erratum) |
| E: stop order at +$15 | 2,486 (689) | +0.09 | 0.63 | no (−2.52) | no difference |

**Erratum: the registered comparison for C is biased, and the "differs" verdict does not mean C is better.**

- I registered the comparison "on the triggers both entered". For C those are the triggers whose price came back to the confirmation level within 2 hours.
- That condition is in the future of the entry, and it selects the close's worst trades: on that subset A wins only 37.5%, against 46.4% overall.
- The fair comparison counts C's missed trades as zero, per confirmed trigger. On that basis C is worse: −$0.86 against −$0.78 (2026: −$1.17 against −$0.70).
- The design error is mine. The registration is not changed after the fact; this erratum is appended here and in `research/trials.jsonl`.

## Every model (all alert types pooled; +$15 before −$13; expectancy after the model cost)

### 2020–22 (P1, 15m bars)

| Model | Trades | +$15 (95%) | +$20 | Expectancy | MFE / MAE | Latency vs A | Entry vs A (+ = worse) | Notes |
|---|---|---|---|---|---|---|---|---|
| A: the confirming close | 2,486 | 46.4% (44–48) | 38.9% | −$0.78 | 9.9 / 9.4 | — | — | 7,446 triggers: 33% confirmed, 66% invalidated |
| B0: the next open | 2,486 | 46.3% | 38.9% | −$0.82 | 9.9 / 9.4 | +0 min | +$0.03 | |
| B15 | 2,486 | 47.5% (46–49) | 40.7% | −$0.47 | 10.2 / 9.2 | +15 min | −$0.56 | |
| B30 | 2,486 | 48.9% (47–51) | 40.3% | −$0.07 | 10.2 / 9.0 | +30 min | −$0.58 | |
| B60 | 2,486 | 47.9% | 41.0% | −$0.35 | 10.2 / 9.1 | +60 min | −$0.60 | |
| C: retest | 1,991 | 45.2% | 38.9% | −$1.08 | 9.5 / 9.5 | +7.5 min (median) | −$2.83 | Fill rate 80%; missed 495, of which 406 A winners |
| E: stop order | 2,929 | 39.9% (38–42) | 33.9% | −$2.43 | 8.5 / 10.8 | −7.5 min (median) | −$3.81 | 443 false confirmations (filled, never confirmed) |

### 2026 (P2, 15m bars, literal $)

| Model | Trades | +$15 (95%) | +$20 | Expectancy |
|---|---|---|---|---|
| A | 668 | 47.0% (43–51) | 41.5% | −$0.70 |
| B0 | 668 | 47.6% | 42.2% | −$0.54 |
| B15 | 668 | 50.1% (46–54) | 43.9% | +$0.18 |
| B30 / B60 | 668 | 48.1% / 47.9% | 41.6% / 41.3% | −$0.41 / −$0.45 |
| C | 519 | 43.5% | 37.6% | −$1.50 |
| E | 814 | 31.0% | 26.2% | −$5.06 |

The 2026 15m bars are wide against a literal $13 stop, so the worst-case rule for a bar touching both levels probably costs E heavily (likely, not proven). The 5m bars below are the fairer test of E.

### Sep–Nov 2026 on 5m bars (P3; 118–144 trades; descriptive)

| Model | Trades | +$15 | Latency vs A5 | Entry vs A5 | False confirmations |
|---|---|---|---|---|---|
| A5: the 15m close, exits on 5m | 118 | 39.8% (31–49) | — | — | — |
| B5 | 118 | 42.4% | +5 min | −$0.15 | — |
| **B10: the site's median delay** | 118 | **46.6%** (38–56) | +10 min | −$1.33 | — |
| B25: the 95th percentile | 118 | 44.9% | +25 min | −$1.12 | — |
| D: the first 5m close $15 beyond | 127 | 40.2% | −5 min | −$1.30 | 9 |
| E5: the stop order on 5m | 144 | 41.7% | −12.5 min | −$3.87 | 26 |

## The engine stream alone (small; not decisive)

| | A | B15 | B30 / B60 | C | E |
|---|---|---|---|---|---|
| 2020–22 (20 confirmed) | 60.0% | 30.0% | 50.0% / 50.0% | 50.0% of 14 | 37.5% of 24 |
| 2026 (21 confirmed) | 52.4% | 52.4% | 38.1% / 47.6% | 58.8% of 17 | 31.8% of 22 |

## What this means for the operator

- **Executable prices.** The first price the site can act on (7 minutes after the close, median) gives the same odds as the close. The 15-minute close approach is not losing a hidden edge to latency, because there is no edge to lose.
- **No timing variant beats the close.** Retest, earlier stop entry and 5m confirmation were each measured with missed trades and false confirmations counted. None beat the close.
- **The forward test measures from the executable price.** B24-CONFIRM-FWD's primary entry is the price the site had when it first saw the confirmation, so real latency is in the test from day one.
- **Other entry ideas were already measured.** Liquidity expansion, structure shifts, displacement and retest, momentum, volatility, sessions, multi-timeframe and regimes: B1–B23 (`STRATEGY_CATALOGUE.md`), none above random out of sample. No new indicator was added: none has shown predictive value.
