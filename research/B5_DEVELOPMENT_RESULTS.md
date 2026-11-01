# Phase B5 — real COMEX order flow, on the −$10 stop with +$10 / +$15 / +$20 (development data only, 2026-11-01)

**Verdict: REJECT all 18 trials. Real exchange order flow does not predict which barrier price hits first.**
- No rule or model beats random entries by 2 standard errors in the useful direction.
- Every trial loses money after costs, between −$21 and −$93 per trade at 0.5 lot.
- Both models score an out-of-fold AUC of **0.50** on 110,858 decisions: the order-flow features carry no information
  about the outcome.
- The highest success rate was **52.0%** at +$10, against 49.8% random and a 54.4% break-even.
- What order flow does show is a small **reversal**. After the strongest hour of buying, price drifts down slightly
  over the next hour (and the reverse after selling). The drift is about $0.3, less than a fifth of the trading cost.
- Nothing is proposed for registration; validation and the holdout stay sealed.

## 1. The request and the data

**The operator's request.**
- Their goal: entries where +$10 to +$20 comes before −$10 at 90%.
- On 2026-11-01 they asked for order-flow research, then approved this study: "approve B5 order flow study".

**The data.** Real trades from the CME, bought through Databento:
- COMEX gold futures, most-traded contract (`GC.v.0`), schema `trades`. Every trade carries its **aggressor side**:
  the buyer lifted the offer, or the seller hit the bid.
- **74,514,416 trades**, 2020-01-24 → 2023-01-24 (the development partition), in 157 weekly pieces.
- Reduced to 70,634 fifteen-minute bars; 67,829 of the 70,173 spot bars had matching flow.
- 2,014 bars on contract-roll days were blanked.
- **Cost: $93.27** (Databento's quote), paid from the account's $125 sign-up credit, so nothing was charged.
- Raw trades were never stored. Only the aggregate figures below were kept: `research/results/b5_development_2026-11-01.json`
  and 18 records in `research/trials.jsonl`.

## 2. Declared before the data

The study was declared and committed before any order-flow data was obtained:
- `quantum/research/b5_orderflow.py`, first at `d7d097c0e`;
- amendment A1 at `625d3782a`, 21:40 UTC;
- the run started at 21:41 UTC.

**Amendment A1 (cost, approved before any data).**
- The first declaration used `tbbo` (trades plus the book). Its quote was $155.45, above the $100 budget and the credit.
- The operator approved `trades` ($93.27): "approve B5 trades version and merge".
- This dropped the book measures: OFI, queue imbalance and spread.

**Features** (per 15-minute bar, known at its close):
- aggressor imbalance (buy − sell volume) ÷ total over the bar's last 1 and 5 minutes, the whole bar, and the last hour;
- the trade-count z-score.

**Trials**
- **12 rules:** imbalance over 15 or 60 minutes at its trailing 90th percentile × follow (CONT) or fade (REV) ×
  +$10 / +$15 / +$20 against −$10.
- **6 model trials:** logistic regression and gradient-boosted trees, 6-block purged walk-forward. Each trades its top
  decile, one position at a time.

**Everything else is B2's:**
- spot 15-minute paths over 3 trading days;
- fills at the level or a gapping open;
- the frozen cost model, scaled to $4,000;
- a random-entry baseline matched to each trial's long / short mix;
- the five-part pass rule.

## 3. Results

**Random entries:** +$10 / +$15 / +$20 before −$10 were hit 50.5% / 40.7% / 34.0% of the time long, and 49.1% / 38.9% /
32.5% short.

| Trial | n | Success | Random, same mix | z | Break-even | Net R | $ per trade, 0.5 lot |
|---|---|---|---|---|---|---|---|
| Follow 15-min flow, +$10 | 2,147 | 49.0% | 49.8% | −0.75 | 54.4% | −0.099 | −$50 |
| Follow 15-min flow, +$15 | 1,812 | 38.4% | 39.9% | −1.26 | 43.5% | −0.121 | −$61 |
| Follow 15-min flow, +$20 | 1,616 | 31.6% | 33.3% | −1.41 | 36.3% | −0.133 | −$67 |
| Fade 15-min flow, +$10 | 2,147 | 50.6% | 49.7% | +0.77 | 54.4% | −0.085 | −$42 |
| Fade 15-min flow, +$15 | 1,814 | 40.4% | 39.8% | +0.53 | 43.5% | −0.089 | −$44 |
| Fade 15-min flow, +$20 | 1,570 | 33.0% | 33.2% | −0.18 | 36.2% | −0.106 | −$53 |
| Follow 1-hour flow, +$10 | 1,939 | 47.3% | 49.8% | **−2.20** | 54.4% | −0.136 | −$68 |
| Follow 1-hour flow, +$15 | 1,622 | 36.7% | 39.8% | **−2.58** | 43.5% | −0.168 | −$84 |
| Follow 1-hour flow, +$20 | 1,472 | 30.1% | 33.3% | **−2.58** | 36.3% | −0.186 | −$93 |
| Fade 1-hour flow, +$10 | 1,939 | **52.0%** | 49.8% | +1.95 | 54.4% | −0.055 | −$28 |
| Fade 1-hour flow, +$15 | 1,642 | 41.9% | 39.8% | +1.75 | 43.5% | −0.048 | −$24 |
| Fade 1-hour flow, +$20 | 1,443 | 34.2% | 33.2% | +0.82 | 36.3% | −0.068 | −$34 |
| Logistic model, +$10 | 2,679 | 49.3% | 49.8% | −0.44 | 54.3% | −0.101 | −$51 |
| Boosted trees, +$10 | 3,435 | 50.4% | 49.8% | +0.78 | 54.2% | −0.071 | −$36 |
| Logistic model, +$15 | 3,678 | 40.1% | 39.9% | +0.23 | 43.3% | −0.082 | −$41 |
| Boosted trees, +$15 | 3,138 | 40.5% | 39.8% | +0.82 | 43.3% | −0.072 | −$36 |
| Logistic model, +$20 | 2,935 | 34.7% | 33.4% | +1.40 | 36.0% | −0.043 | −$21 |
| Boosted trees, +$20 | 2,660 | 33.6% | 33.2% | +0.37 | 36.1% | −0.075 | −$37 |

**The five-part rule.**
- (1) Wilson lower bound above break-even: 0 of 18.
- (2) t > 3 with net > 0: 0 of 18. All net results are negative, 14 of them with t below −2.5.
- (3) z > 2 against random: 0 of 18.
- (4) Benjamini-Hochberg: 0 of 18.
- (5) Reality Check: p = 1.000.

**The operator's 90% target.** The best Wilson upper bound was 54.2%.

**Models (out of fold, 110,858 decisions per target).**

| Target | Model | AUC | Brier | Brier of the base rate | ECE | Calibration slope |
|---|---|---|---|---|---|---|
| +$10 | Logistic | 0.500 | 0.2501 | 0.2500 | 0.006 | −0.18 |
| +$10 | Trees | 0.500 | 0.2511 | 0.2500 | 0.025 | −0.02 |
| +$15 | Logistic | 0.500 | 0.2397 | 0.2396 | 0.006 | −0.07 |
| +$15 | Trees | 0.503 | 0.2405 | 0.2396 | 0.021 | +0.05 |
| +$20 | Logistic | 0.500 | 0.2218 | 0.2217 | 0.003 | +0.06 |
| +$20 | Trees | 0.499 | 0.2227 | 0.2217 | 0.012 | −0.05 |

- An AUC of 0.50 is a coin toss.
- The Brier scores are no better than always predicting the base rate.
- Calibration slopes near zero mean the predictions do not track outcomes at all.

## 4. Order flow and entry timing (Q2, descriptive)

The mean spot move after each bar, scaled to $4,000, by that bar's buy/sell imbalance (deciles of 6,475 bars each):

| Imbalance decile | Mean imbalance | Next 15 minutes | Next 60 minutes |
|---|---|---|---|
| 1 (heaviest selling) | −0.235 | +$0.10 | +$0.26 |
| 2 | −0.101 | +$0.12 | +$0.15 |
| 3 | −0.063 | +$0.09 | +$0.01 |
| 4 | −0.035 | −$0.02 | −$0.07 |
| 5 | −0.011 | −$0.07 | −$0.09 |
| 6 | +0.012 | +$0.02 | +$0.10 |
| 7 | +0.036 | −$0.04 | +$0.02 |
| 8 | +0.065 | −$0.01 | +$0.04 |
| 9 | +0.104 | −$0.11 | −$0.05 |
| 10 (heaviest buying) | +0.229 | −$0.11 | −$0.34 |

**What this means**
- Order flow moves price **while it happens**: the bar's own close already contains the push.
- Afterwards, a little of the push **reverses**: about $0.1 over 15 minutes and $0.3 over an hour at the extremes.
- At the two extreme deciles the 60-minute drift is 2.4 and 3.2 standard errors from zero (z −2.0 and +1.8 at
  15 minutes). The standard errors use the development data's own volatility: $4.33 per 15 minutes and $8.56 per hour
  at $4,000. This table is descriptive, not a pre-registered test.
- This matches the literature: order-flow impact is contemporaneous and partly transient (`ORDER_FLOW_RESEARCH.md`
  §2).
- The reversal is why "follow the 1-hour flow" did worse than random (z −2.2 to −2.6), and why "fade" leaned the
  other way.
- It is far too small to trade. The average round-trip cost is about $1.91 at $4,000, 5.6 times the largest drift.
- Following the flow, the mean next 15-minute move was −$0.05.

## 5. What it means for the operator

1. **A confirmed +$10 before −$10 is not available from order flow either.** That holds for real COMEX trades with
   the buyer or seller identified, the best data that exists for this question.
2. **The research's expectation held.** Order flow explains price as it moves and fades within minutes. It does not
   say where gold will be an hour later.
3. **One practical lesson.** Do not chase a strong hour of one-sided buying or selling. On average the price gives a
   little back afterwards, which makes a +$10 target slightly harder to reach first.
4. **Totals so far.** Across B1–B5 there are 497 recorded trials and one validation run. None found an entry that
   reaches +$10 to +$20 before −$10 reliably above break-even, let alone 90%.

## 6. Reproducibility

- **Code:** `quantum/research/b5_orderflow.py` at `625d3782a`.
- **Workflow:** `.github/workflows/research-orderflow.yml`, run 7 (GitHub run 41353292269, 14.5 minutes).
- **Spot data hash:** `f113f97ad2105ff9`. Databento client 0.89.0.
- **Results:** `research/results/b5_development_2026-11-01.json`, also on the `research-orderflow` branch.
- **Trial records:** 18 lines appended to `research/trials.jsonl` (now 497).
- **Cache:** the run's 15-minute sums sit in the repository's private Actions cache, AES-encrypted with the API key,
  for a repeat after a failure. The run succeeded, so the cache can be deleted under Actions → Caches.
