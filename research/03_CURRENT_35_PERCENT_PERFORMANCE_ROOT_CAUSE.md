# 03 — Why the playbook "won 35% of 986" and lost money (root cause, executed 2026-11-01)

**Status:** audit only. Nothing in the engine, the arms or the forward test was changed.

**Evidence:**

- **Tool:** `audit/tools/h4_outcome_audit.py`, run offline on `market-data` @ `0bb2c8a96` (Twelve Data XAU/USD) with
  the deployed engine web.7.
- **15m window:** 2026-08-05 22:00 → 2026-10-30 20:45 UTC (5,704 bars).
- **Cross-checks:** 5m (2026-09-09 →) and 1h (2026-03-02 →).
- **Counterfactuals** in §5 are diagnostic explanations computed on the same in-sample window. They are not
  candidate rules, and none may be adopted from it.

## 0. Answer in one paragraph

The 35% is real and correctly measured. The losses are a **genuine absence of edge, made worse by churn and
costs**, not a measurement defect:

- **No directional information.** The H4 trigger ("a candle closes beyond the nearest of 15 levels") picks the
  direction of the next 1–48 bars **48.8–50.0% of the time on 15m** (47.7–48.3% on 5m, slightly *worse* than a coin), no better than chance.
- **Negative before costs.** Gross expectancy is already −0.035 R; costs of 0.072 R per trade (0.141 R on 5m) take
  it to −0.108 R.
- **The advertised 2:1 never reaches the trade.**
  - The 2:1 is measured from the trigger level, while the trade enters at the close beyond it. Measured from the
    real entry, the median reward:risk is 1.26:1.
  - Two thirds of trades are then closed early by the next opposite trigger (a "flip", median 3 bars). Winners
    average +0.78 R, not +2 R.
  - At the realised payoff of 1.32 the break-even win rate is **43%**, not 33%.

## 1. What "986" and "35%" are

| Question | Finding |
|---|---|
| Triggers or trades? | **Trades.** There were 1,628 trigger bars (28.5 per 100 bars). 986 closed trades opened; 641 triggers were ignored (same direction while in a trade, or no valid levels). The site's wording "triggers won 35% of 986 times" should say "trades". |
| Which data? | **In-sample**: every closed trade before the web.7 start (31 Oct 17:23 UTC), re-simulated over the whole 15m store, including the period that was web.6's forward test. H4's rule was pre-registered (Amendment 8) and never tuned, but this window is not unseen data. |
| "Win" means? | Final **net R > 0** for the whole trade: the half closed at TP1 plus the rest, after costs. It is not "TP1 hit": TP1 was reached in 28.3% of trades. |
| Partial profits included? | Yes: 50% at TP1, the rest at TP2, breakeven or flip. |
| Stops correct? | Yes: stop first on a bar that touches both; gap fills at the open (Amendment 14, verified by 23 tests and mutation testing). |
| Both levels in one bar? | **8 of 986 trades** had a bar touching both the stop and TP1, resolved stop first (conservative). Without tick data the true order is unknown; at most 8 outcomes (0.8%) could change. |
| Costs? | Spread (0.30 in session, 0.50 off session), 2 × 0.20 slippage and $7 per lot commission are all charged. **Swap / rollover are not**: 56 trades (5.7%) were held across 17:00 New York. Broker costs are unverified (`audit/COST_PROFILES.md`). |
| Overlap / independence | One position at a time, so no overlapping trades. But 834 of 985 next entries happen **on the bar the previous trade exits** (a flip), so the record is close to "always in the market". The lag-1 autocorrelation of R is −0.025, small. |
| Buy / sell, sessions, regimes mixed? | Yes, in the headline. Split in §4. |

## 2. The record, decomposed (15m)

| Metric | Value |
|---|---|
| Trades | 986 (501 long / 485 short) |
| Win rate | **35.1%** (Wilson 95%: 32.2–38.1) |
| Average win / average loss | **+0.776 R / −0.586 R** |
| Median win / median loss | +0.609 R / −0.514 R |
| Realised payoff (average win ÷ average loss) | **1.32** → break-even win rate **43.0%** |
| Gross expectancy (before costs) | **−0.035 R** per trade |
| Cost per trade | **0.072 R** (spread + slippage + commission; about 0.77–0.97 points on a median 8.6-point stop) |
| Net expectancy | **−0.108 R** (bootstrap 95%: −0.159 to −0.054); t = −3.99 |
| Profit factor | 0.674 |
| Max drawdown | 111.4 R (sum −106.2 R) |
| Holding time | median 3 bars (45 min), mean 5.2 |
| MFE / MAE (median, in R) | +0.46 / −0.46; 26.0% of trades ever reached +1 R, 8.6% reached +2 R |

**By exit type:**

| Exit | Share | Win % | Mean R | Note |
|---|---|---|---|---|
| FLIP (opposite trigger) | **65.6%** | 23.3 | −0.175 | closed at the close of the opposite trigger bar |
| SL | 13.6% | 0 | −1.089 | the full stop plus costs |
| TP2 | 13.4% | 99.2 | +1.041 | the only exits near the advertised payoff |
| BE | 6.2% | 95.1 | +0.246 | half at TP1, half at entry |
| BE_GAP | 1.2% | 50.0 | +0.039 | breakeven gapped (web.7 rule) |

**Advertised against realised reward:risk** (all 1,628 triggers):

| Reward:risk | Median | Mean | Share ≥ 2 |
|---|---|---|---|
| As displayed (from the trigger level) | 1.92 | 2.93 | 45% |
| From the actual entry (the candle close) | **1.26** | 2.03 | **27%** |

The close lands a median **0.24 stop distances** (75th percentile 0.46) beyond the trigger. That makes the real stop
farther and the target nearer than the card shows. The screenshot's "2.1:1" is one such trigger-based figure.

## 3. The same on every timeframe

| TF (window) | Trades | Win % | Avg win / loss R | Break-even win % | Gross R | Cost R | Net R [95%] | Flip share | Direction correct, 1–48 bars |
|---|---|---|---|---|---|---|---|---|---|
| 5m (09-09 → 10-30) | 1,731 | 33.4 | +0.78 / −0.66 | 45.6 | −0.035 | 0.141 | **−0.176** [−0.216, −0.135] | 66.8% | **47.7–48.3%** (1, 4 and 16 bars: the whole 95% interval is below 50%; 48 bars: 46.4–50.1) |
| 15m (08-05 → 10-30) | 986 | 35.1 | +0.78 / −0.59 | 43.0 | −0.035 | 0.072 | **−0.108** [−0.159, −0.054] | 65.6% | 48.8–50.0% |
| 1h (03-02 → 10-30) | 729 | 38.8 | +0.74 / −0.54 | 42.0 | −0.012 | 0.029 | −0.041 [−0.100, +0.024] | 64.6% | 48.2–50.6% |

The shorter the timeframe, the larger the cost in R (the stops are smaller), and the worse the result. **The
direction is a coin flip everywhere.**

## 4. Splits (15m; descriptive, exploratory; many groups, so some will look good by chance)

| Group | n | Win % | Gross R | Net R | t |
|---|---|---|---|---|---|
| Long | 501 | 32.9 | −0.053 | −0.126 | −3.29 |
| Short | 485 | 37.3 | −0.017 | −0.088 | −2.34 |
| Asian | 358 | 33.0 | −0.099 | −0.182 | **−4.25** |
| London | 185 | 35.7 | −0.068 | −0.128 | −1.92 |
| NY | 106 | 35.8 | +0.030 | −0.030 | −0.46 |
| NY kill zone | 85 | 35.3 | −0.074 | −0.117 | −1.70 |
| Off session | 117 | 39.3 | +0.157 | +0.047 | +0.49 |
| Regime RANGE | 380 | 37.1 | +0.008 | −0.073 | −1.54 |
| Regime COMPRESS | 121 | 38.8 | −0.107 | −0.208 | −2.80 |
| Regime WEAK TREND | 115 | 29.6 | −0.110 | −0.178 | −2.45 |
| Regime STRONG TREND | 157 | 32.5 | −0.016 | −0.082 | −1.19 |
| Regime EXPANSION | 159 | 33.3 | −0.015 | −0.065 | −1.03 |
| Regime ABNORMAL | 54 | 37.0 | −0.135 | −0.178 | −2.40 |

**No group shows a significant positive edge.**

- The best-looking cell ("off session", +0.047 R, t +0.49) is one of 16 groups. On this window it is noise.
- Selecting it would be exactly the in-sample cherry-picking the brief forbids.
- The Asian session is the clearest negative.

## 5. Diagnostic counterfactuals (same signals and costs; explanation, not rules)

| Variant | Trades | Win % | Avg win / loss R | Gross R | Net R [95%] |
|---|---|---|---|---|---|
| As deployed | 986 | 35.1 | +0.78 / −0.59 | −0.035 | −0.108 [−0.159, −0.054] |
| No flips (ignore opposite triggers while in a trade) | 172 | 45.3 | +1.02 / −1.04 | −0.044 | −0.107 [−0.314, +0.130] |
| Full exit at TP1 (no TP2) | 1,113 | 34.7 | +0.77 / −0.60 | −0.048 | −0.121 [−0.168, −0.075] |
| Zero costs | 986 | 37.5 | +0.80 / −0.54 | −0.035 | −0.035 [−0.086, +0.017] |

**Reading:**

- **Flips are not the cause.** Removing them raises the win rate (to 45%) and lets winners run (to +1.02 R), but the
  expectancy is unchanged: the trades still have no edge.
- **Different exits do not create an edge.**
- **Costs alone do not explain the loss:** with zero costs the result is −0.035 R, with an interval that just
  includes zero. The signal itself carries no information.

## 6. Verdict

| Hypothesis | Verdict | Evidence |
|---|---|---|
| The outcome measurement is defective | **Rejected** | Exits, partials, costs and gap fills are verified; only 8 trades are ambiguous within a bar |
| The 2:1 makes 35% profitable | **Rejected** | The realised payoff is 1.32 (break-even 43%); the 2:1 is measured from the trigger, not the entry, and flips cut winners |
| Costs turn a small edge negative | **Partly**: costs make it significantly negative, but gross is already ≤ 0 | Gross −0.035 R; zero-cost interval −0.086 to +0.017 |
| The trigger has directional information | **Rejected on this data** | 47.7–50.6% correct at 1–48 bars on 5m / 15m / 1h |
| Forward evidence agrees | **Yes** | web.6 forward record: 15m n 171, −0.092 R; 5m n 511, −0.179 R, t −4.75 (`audit/FORWARD_WEB6_FINAL.md`) |

**Consequence:** the playbook levels are useful as **descriptions of where liquidity sits**, which is how the site
already labels them ("levels to watch, not signals"). They are **not** a trading signal. No re-weighting or
filtering of H4 on this window can be trusted, because every filter would be selected on the same data. A
replacement must be researched on the Amendment 13 development data and validated as set out in
`09_BACKTEST_AND_VALIDATION_FRAMEWORK.md`.

## 7. Defects found in the presentation (display; proposed, not changed)

1. **"These triggers won 35% of 986 times"** — they are 986 *trades* from 1,628 triggers, and "won" means final net R > 0. Proposed text: "In past data (in-sample) 986 trades from these triggers: 35% ended positive; average −0.11 R per trade after costs."
2. **The reward:risk tile shows 2.1:1 measured from the trigger.** The trade's own reward:risk from the expected entry is lower (median 1.26). Proposed: show both, or the entry-based figure.
3. **After the web.7 restart the losing verdict disappeared** ("Live record: tracking started"). The archived web.6 forward record (15m: 171 trades, −0.09 R; 5m: 511, t −4.75) should be shown, labelled "previous engine (web.6), archived".
