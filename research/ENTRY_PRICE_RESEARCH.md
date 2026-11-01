# Entry-price research: can an entry price confirm a +$10 move? (2026-11-01)

The operator's request: "an alert on the entry price where I can guarantee +$10 price movement … do deep research to
find the way to calculate the exact market entry price in which the next $10 movement is confirmed or has a higher
probability to hit +$10".

**Short answer**
- **No entry price can guarantee +$10 first.** Probability theory rules it out for any price without predictable
  drift (§1), and gold's measured volatility shows how much prediction a high hit rate would need.
- **The literature names three places where a small, real drift might sit.** All three were tested on 2020–2023 data
  as Phase B4, declared in code before running (§3):
  - **Session-open momentum:** nothing.
  - **Limit entries at a "better" price:** no benefit (−1.2 to +0.8 points against market entry).
  - **Round-number crossings (Osler 2003):** the only consistent lead in 448 trials. Even this lead reaches 47.6%
    against a 43.3% break-even at +$15, about +$54 a trade, and it is **not statistically confirmed**. Nothing comes
    near 90%.

## 1. The mathematics: why the entry price alone cannot confirm a move

**The theorem.** For a price that has no predictable drift (a martingale), the optional stopping theorem gives, from
**any** entry price:

> P(+a before −b) = b ÷ (a + b)

For +$10 before −$10 that is 50%, wherever you enter.

**What it means for an entry price.** An entry price helps only when it coincides with information that predicts
drift: the price must be expected to move your way during the trade.

**How much drift is needed.** Model the price as a Brownian motion with drift μ and volatility σ. Then:

> P(+a before −b) = (1 − e^{θb}) ÷ (e^{−θa} − e^{θb}), where θ = 2μ ÷ σ²

Gold's measured volatility (XAU/USD 5-minute bars, last 20 trading days):
- about **$48 a day**;
- about **$10 an hour**, so +$10 is roughly one hour's typical move.

Drift needed to reach each success rate:

| Success rate wanted | +$10 / −$10 (random 50%) | +$15 / −$10 (random 40%) | +$20 / −$10 (random 33%) |
|---|---|---|---|
| 55% | $23 / day (≈ $1.0 / h) | $56 / day | $71 / day |
| 60% | $46 / day (≈ $2.0 / h) | $76 / day | $89 / day |
| 70% | $96 / day (≈ $4.2 / h) | $119 / day | $128 / day |
| 80% | $157 / day (≈ $6.8 / h) | $173 / day | $178 / day |
| **90%** | **$249 / day (≈ $10.8 / h)** | $257 / day | $260 / day |
| 99% | $521 / day | $522 / day | $522 / day |
| 100% | infinite: certainty | | |

**Reading the table.** 90% at +$10 / −$10 needs a predicted drift of about **$11 an hour** your way, which is as large
as gold's entire typical hourly move. In effect, you would need to know the next hour's direction. Even 60% needs a
reliably predicted $2 an hour.

**Broker offset.** The operator's MT5 close of 3872.90 (Friday 2026-10-30) is **$2.61 below** the site's Twelve Data
close (3875.51). Entering −2.61 in the page's "MT5 offset" box aligns the displayed levels with the broker's prices.
Offsets drift a little, so re-check against MT5 now and then.

## 2. What the literature says (searched 2026-11-01)

| Source | Finding | Usable here? |
|---|---|---|
| Osler, *Currency orders and exchange rate dynamics*, J. Finance 58 (2003); NY Fed Staff Reports 125 and 150 | Take-profit orders cluster **at** round numbers, so trends tend to reverse there. Stop-loss orders cluster **just beyond** them, so trends accelerate after a crossing. Data: about 9,700 orders at one dealing bank, 1999–2000, FX | **Tested (H1).** No peer-reviewed gold study was found. One practitioner test of gold's $20 levels found an effect roughly at break-even after slippage |
| Gao, Han, Li & Zhou, *Market intraday momentum*, J. Financial Economics 129 (2018) | In SPY, the first half-hour return predicts the last half-hour (R² ≈ 1.6%). Extensions find similar effects in commodity futures (including Chinese gold futures) and in FX (Elaut, Frömmel & Lampaert, J. Financial Markets 37, 2018) | **Tested (H2),** as session-open momentum. Note the size: R² of 1–3% means a few points of hit rate at most |
| Cont, Kukanov & Stoikov, *The price impact of order book events*, J. Financial Econometrics 12 (2014) | Short-horizon price changes are driven by order-flow imbalance at the best bid/ask, but the relation is contemporaneous | **Not testable:** spot gold is over-the-counter; there is no order book in our feeds |
| Elder, Miao & Ramchander, J. Banking & Finance (2012) | Gold reacts to US macro surprises (NFP, durable goods) **swiftly**, within minutes, and volatility rises | **Not testable:** needs consensus forecasts and the actual numbers. The move is mostly over before a retail order fills |
| Limit-order adverse selection (Hollifield, Miller & Sandås 2001; later market-making papers) | Passive limit orders fill more often just before adverse moves (the "winner's curse") | **Tested (H3):** "a better entry price" via a limit order |
| López de Prado, *Advances in Financial Machine Learning* (2018) | Triple-barrier labels and **meta-labeling**: a second model estimates whether a primary signal's TP comes first, trading recall for precision | The right framework (Step B). It raises precision only if its inputs carry information |

## 3. Phase B4 results

**Declaration.** `quantum/research/b4.py`, committed `4b39ba783` before the run.

**Data and method.**
- Development data only, 2020-01-24 → 2023-01-24.
- B2's paths, costs, fills and one-position rule.
- Every trial is in `research/trials.jsonl` (472 records).

**The three hypotheses:**
- **H1, round numbers:** closes crossing a multiple of $10 / $50 / $100 (continuation), and first rejections at one (reversal), on 15min and 1h decisions.
- **H2, session-open momentum:** the sign of the first 30 minutes after 08:00 London and 08:30 New York.
- **H3, limit entries:** an order $2 or $5 better than the decision price, valid 1 hour, against market entry from the same decisions.

All 48 trials, sorted by z against random entries in the same direction mix:

| Trial | n | Success | 95% range | Random, same mix | z | Net R | $ / trade at 0.5 lot |
|---|---|---|---|---|---|---|---|
| 1h RN_REJECT_100 T20 | 264 | 40.2% | 34–46% | 33.3% | +2.38 | +0.120 | +60 |
| 15min RN_CROSS_100 T15 | 212 | 47.6% | 41–54% | 39.7% | +2.35 | +0.108 | +54 |
| 15min RN_CROSS_100 T20 | 212 | 40.6% | 34–47% | 33.2% | +2.28 | +0.133 | +66 |
| 1h RN_CROSS_100 T20 | 125 | 42.4% | 34–51% | 33.2% | +2.18 | +0.189 | +94 |
| 1h RN_CROSS_50 T20 | 225 | 39.6% | 33–46% | 33.2% | +2.01 | +0.105 | +52 |
| 15min RN_CROSS_50 T15 | 400 | 44.2% | 39–49% | 39.8% | +1.83 | +0.023 | +12 |
| 15min RN_CROSS_50 T20 | 395 | 37.0% | 32–42% | 33.2% | +1.59 | +0.020 | +10 |
| 1h RN_REJECT_50 T20 | 518 | 36.5% | 32–41% | 33.2% | +1.56 | +0.011 | +5 |
| 1h RN_CROSS_10 T20 | 876 | 35.5% | 32–39% | 33.3% | +1.39 | -0.010 | -5 |
| 1h RN_CROSS_100 T15 | 125 | 45.6% | 37–54% | 39.8% | +1.33 | +0.057 | +28 |
| 1h RN_CROSS_50 T15 | 225 | 44.0% | 38–51% | 39.8% | +1.28 | +0.018 | +9 |
| 15min RN_CROSS_100 T10 | 215 | 54.0% | 47–60% | 49.7% | +1.24 | -0.005 | -3 |
| 1h RN_REJECT_100 T15 | 273 | 42.9% | 37–49% | 39.8% | +1.02 | -0.012 | -6 |
| 15min RN_CROSS_50 T10 | 406 | 51.7% | 47–57% | 49.7% | +0.80 | -0.049 | -24 |
| 15min NY_OPEN T20 | 752 | 34.6% | 31–38% | 33.3% | +0.77 | -0.045 | -22 |
| 1h RN_CROSS_10 T15 | 924 | 41.0% | 38–44% | 39.9% | +0.71 | -0.052 | -26 |
| 15min NY_OPEN T15 | 765 | 40.9% | 37–44% | 39.8% | +0.61 | -0.058 | -29 |
| 1h RN_CROSS_50 T10 | 225 | 51.6% | 45–58% | 49.8% | +0.53 | -0.051 | -25 |
| 1h RN_CROSS_100 T10 | 125 | 52.0% | 43–61% | 49.8% | +0.50 | -0.042 | -21 |
| 1h RN_REJECT_100 T10 | 294 | 51.0% | 45–57% | 49.8% | +0.41 | -0.062 | -31 |
| 1h RN_CROSS_10 T10 | 939 | 50.5% | 47–54% | 49.8% | +0.40 | -0.067 | -34 |
| 1h RN_REJECT_50 T15 | 547 | 40.6% | 37–45% | 39.8% | +0.37 | -0.067 | -34 |
| 15min RN_CROSS_10 T15 | 1821 | 39.9% | 38–42% | 39.8% | +0.09 | -0.084 | -42 |
| 15min LONDON_OPEN T15 | 762 | 39.9% | 36–43% | 39.9% | +0.02 | -0.079 | -39 |
| 15min LONDON_OPEN T20 | 754 | 33.3% | 30–37% | 33.3% | +0.01 | -0.071 | -35 |
| 1h RN_REJECT_50 T10 | 589 | 49.7% | 46–54% | 49.8% | -0.03 | -0.087 | -44 |
| 1h RN_REJECT_10 T20 | 2197 | 33.2% | 31–35% | 33.3% | -0.06 | -0.086 | -43 |
| 15min RN_CROSS_10 T20 | 1709 | 33.1% | 31–35% | 33.2% | -0.16 | -0.091 | -46 |
| 15min LONDON_OPEN T10 | 765 | 49.3% | 46–53% | 49.8% | -0.29 | -0.092 | -46 |
| 15min NY_OPEN T10 | 769 | 49.0% | 46–53% | 49.8% | -0.43 | -0.095 | -48 |
| 15min RN_CROSS_10 T10 | 1900 | 49.3% | 47–52% | 49.8% | -0.45 | -0.098 | -49 |
| 15min RN_REJECT_100 T20 | 323 | 31.6% | 27–37% | 33.3% | -0.64 | -0.138 | -69 |
| 15min RN_REJECT_50 T20 | 626 | 31.8% | 28–36% | 33.3% | -0.78 | -0.130 | -65 |
| 15min LIMIT_2 T20 | 24647 | 32.9% | 32–33% | 33.2% | -1.07 | -0.097 | -48 |
| 15min RN_REJECT_50 T15 | 653 | 37.5% | 34–41% | 39.8% | -1.21 | -0.145 | -72 |
| 1h RN_REJECT_10 T15 | 2425 | 38.5% | 37–40% | 39.9% | -1.34 | -0.120 | -60 |
| 15min RN_REJECT_100 T15 | 335 | 36.1% | 31–41% | 39.8% | -1.39 | -0.180 | -90 |
| 15min RN_REJECT_100 T10 | 362 | 46.1% | 41–51% | 49.8% | -1.40 | -0.160 | -80 |
| 15min RN_REJECT_50 T10 | 713 | 47.0% | 43–51% | 49.8% | -1.50 | -0.143 | -71 |
| 15min RN_REJECT_10 T20 | 2945 | 31.9% | 30–34% | 33.3% | -1.54 | -0.127 | -63 |
| 15min LIMIT_2 T15 | 24647 | 39.3% | 39–40% | 39.8% | -1.55 | -0.098 | -49 |
| 1h RN_REJECT_10 T10 | 2701 | 48.3% | 46–50% | 49.8% | -1.59 | -0.113 | -57 |
| 15min LIMIT_2 T10 | 24647 | 49.2% | 49–50% | 49.8% | -1.69 | -0.093 | -46 |
| 15min LIMIT_5 T15 | 13381 | 39.1% | 38–40% | 39.8% | -1.72 | -0.109 | -54 |
| 15min RN_REJECT_10 T15 | 3264 | 38.3% | 37–40% | 39.8% | -1.80 | -0.126 | -63 |
| 15min LIMIT_5 T10 | 13381 | 48.9% | 48–50% | 49.8% | -1.99 | -0.102 | -51 |
| 15min LIMIT_5 T20 | 13381 | 32.4% | 32–33% | 33.2% | -2.04 | -0.118 | -59 |
| 15min RN_REJECT_10 T10 | 3659 | 48.0% | 46–50% | 49.8% | -2.18 | -0.122 | -61 |

### Family statistics

| Statistic | Value |
|---|---|
| Pass flags | (1) Wilson lower bound above break-even: **0** · (2) t > 3: **0** · (3) z > 2 against random: **5** · (4) Benjamini-Hochberg q = 0.10: **0** · (5) Reality Check p < 0.05: **0** (p = 0.984) |
| Trials reaching 90% | **0**, by point estimate or by lower bound |
| PBO | 0.09 (in-sample ranks fairly stable). The in-sample best loses out-of-sample in 46% of splits, with a mean of −0.07 R per week |

### H1 — round numbers: the only consistent lead in 448 trials

**Crossings lean toward continuation, as Osler's stop-loss mechanism predicts.** Every $50 and $100 crossing trial
beats random, on both timeframes and at all three targets:

| Trial | n | Success | 95% range | Break-even | Random | z | Net R | $ / trade | t |
|---|---|---|---|---|---|---|---|---|---|
| 15m $100 cross, +$10 | 215 | 54.0% | 47–61% | 54.1% | 49.7% | +1.24 | −0.005 | −$3 | −0.08 |
| 15m $100 cross, +$15 | 212 | **47.6%** | 41–54% | 43.3% | 39.7% | **+2.35** | +0.108 | **+$54** | +1.25 |
| 15m $100 cross, +$20 | 212 | 40.6% | 34–47% | 36.1% | 33.2% | +2.28 | +0.133 | +$66 | +1.31 |
| 1h $100 cross, +$20 | 125 | 42.4% | 34–51% | 36.1% | 33.2% | +2.18 | +0.189 | +$94 | +1.42 |
| 1h $50 cross, +$20 | 225 | 39.6% | 33–46% | 36.1% | 33.2% | +2.01 | +0.105 | +$52 | +1.07 |

**Stability check** (descriptive only; nothing new was logged). 15m $100 cross at +$15, by year:

| Year | Success | Trades |
|---|---|---|
| 2020 | 49% | 80 |
| 2021 | 52% | 66 |
| 2022 | 44% | 64 |

- Each year is above the roughly 40% random rate.
- Buy crosses scored **55%** against a random 41%. Sell crosses scored only **42%** against 39%.

**Why this is not confirmed:**
- No net t-statistic reaches 3; the largest is 1.42.
- The Benjamini-Hochberg screen passes nothing.
- Luck alone gives a z above 2 about once in 48 trials. Five trials exceeded 2, but they share the same events, so they are closer to two independent results than five.
- The effect is mostly on the buy side, and gold trended up in 2020, so part of it may be drift.

**Size, even if it is real.** About +8 points over random at +$15, roughly +$54 a trade at 0.5 lot, and about 70
trades a year on 15m. **At +$10 it is exactly break-even.** It is a small edge, not a confirmation, and far from 90%.

**Round-number *rejections* (reversal) do not work** on 15m. At $10 they scored *below* random (z −2.18). A touched
round level tends to break, not hold.

### H2 — session-open momentum: nothing

London and New York first-30-minute direction gave 49% at +$10, against 50% random (z −0.3 to −0.4). The momentum
effect reported for equities, and for Chinese commodity futures, is not visible in spot gold at these targets.

### H3 — limit entries at a better price: no benefit

The same decisions entered at market, or by a limit order $2 or $5 better (filled 70% and 38% of the time):

| Target | Market entry (long / short) | Limit $2 (conservative / optimistic) | Limit $5 (conservative / optimistic) |
|---|---|---|---|
| +$10 | 50.2 / 49.3% | 50.0 / 48.4% · 50.9 / 49.1% | 49.7 / 48.1% · 50.7 / 48.8% |
| +$15 | 40.6 / 39.0% | 40.5 / 38.1% · 41.2 / 38.7% | 39.7 / 38.5% · 40.4 / 39.1% |
| +$20 | 33.7 / 32.6% | 33.9 / 31.8% · 34.6 / 32.2% | 33.1 / 31.6% · 33.8 / 32.2% |

**A "calculated" entry price via a limit order changes the success rate by −1.2 to +0.8 points**, depending on the
unknown order of prices inside the fill bar. And a $5 limit misses 62% of the trades. This is the adverse selection
the literature describes: limit orders fill when price is coming against you, which cancels the better price.

## 4. What this means for the operator's request

1. **No guaranteed entry price.** With measured gold volatility, 90% at +$10 / −$10 would need about $11 an hour of
   *predicted* drift. No method tested here, and none in the literature found, supplies it.
2. **The "exact" entry price is not the lever.** Limit orders at better prices don't help. Session-open direction
   doesn't help. Waiting for confirmation didn't help in B3.
3. **One genuine lead: round-number crossings (continuation).** It has a published mechanism (stop-loss clustering
   beyond round numbers) and is consistent across years. It is unconfirmed and small, with about +8 points at +$15.
   The right next step is **one** test of exactly this rule on the sealed 2023–2024 validation data, written down
   before that data is opened. If it fails, it is dropped.
4. **Alerts.** An honest alert can fire when price closes through a $50 / $100 level, carrying its measured rate and
   the label "NOT VALIDATED". It cannot carry a guarantee. Building it before validation would encourage trading an
   unconfirmed rule, so the recommendation is to validate first.

**Research to date:**

| Phase | Trials |
|---|---|
| B1 | 100 |
| B2 | 54 |
| B2b | 18 |
| B2c | 18 |
| B3 | 210 |
| B4 | 48 |
| **Total** | **448**, development data only; **none passes**; one consistent lead (round-number continuation) |

## Sources

- Osler, C. (2003), *Currency orders and exchange rate dynamics: an explanation for the predictive success of technical analysis*, J. Finance 58, 1791–1819 — https://academicnewsletter.sufe.edu.cn/info/361290 ; NY Fed Staff Report 125 — https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf ; Staff Report 150 — https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf
- Practitioner test of XAUUSD $20 levels (vendor blog) — https://www.mql5.com/en/blogs/post/775454
- Gao, Han, Li & Zhou (2018), *Market intraday momentum*, J. Financial Economics 129, 394–414 — https://ideas.repec.org/a/eee/jfinec/v129y2018i2p394-414.html
- Elaut, Frömmel & Lampaert (2018), *Intraday momentum in FX markets*, J. Financial Markets 37 — https://ideas.repec.org:443/a/eee/finmar/v37y2018icp35-51.html
- Intraday momentum in commodity futures — https://hull-repository.worktribe.com/OutputFile/3303156 ; gold, silver and base metals in China — https://acfr.aut.ac.nz/__data/assets/pdf_file/0008/686816/4a-Z-Ivy-Zhou.pdf
- Cont, Kukanov & Stoikov (2014), *The price impact of order book events*, J. Financial Econometrics 12 — https://arxiv.org/abs/1011.6402
- Elder, Miao & Ramchander (2012), macroeconomic news and metal futures — https://mountainscholar.org/handle/10217/206884
- Limit-order adverse selection — https://arxiv.org/pdf/1409.1442 ; https://arxiv.org/html/2502.18625v2 ; https://arxiv.org/pdf/2409.12721
- Meta-labeling and triple-barrier labels (summaries of López de Prado 2018) — https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy/

## 5. Validation of the one lead: registration B4-RN-V1 — FAIL (2026-11-01)

**Procedure.**
- The registration (`research/registrations/B4-RN-V1.json`) was committed **before** the data was read (`7a5e621d9`).
- The operator's approval ("approve B4-RN-V1 and merge") was recorded and committed (`c2c8664c6`).
- The sealed validation partition (2023-01-24 → 2024-06-30) was then read **once** by `quantum/research/validate_rn.py`.
- The runner now refuses a second run, enforced by the trial registry (tested).

**Primary test.** A 15-minute close through a $100 level, entering in the direction of the cross, at +$15 / −$10:

| | Validation (unseen) | Development (where the lead came from) |
|---|---|---|
| Trades | 65 | 212 |
| Success | **41.5%** (95% 30–54%) | 47.6% (95% 41–54%) |
| Random entries, same direction mix | 40.3% | 39.7% |
| Edge over random | **+1.2 points** (z +0.20, p 0.42) | +7.9 points (z +2.35) |
| Break-even after costs | 43.3% | 43.3% |
| Net per trade | **−0.044 R ≈ −$22** at 0.5 lot (t −0.29) | +0.108 R ≈ +$54 (t +1.25) |
| P1 (beat random, z ≥ 1.645) | **fail** | — |
| P2 (net > 0, t ≥ 1.645) | **fail** | — |

**Verdict: FAIL. As registered, the round-number continuation lead is closed.** No re-run with changed parameters.

**How the primary result broke down:**
- By half-year: 46% (2023 H1), 41% (2023 H2), 38% (2024 H1).
- By direction: buys 36%, sells 50%. This is the reverse of development, where buys carried the effect.

**Secondary results** (reported, **not deciding**: using them to rescue the hypothesis would be cherry-picking):

| Variant | n | Success | Random | z | Net per trade |
|---|---|---|---|---|---|
| $100 cross, +$10 | 67 | 50.7% | 49.8% | +0.15 | −$32 |
| $100 cross, +$20 | 61 | 39.3% | 33.6% | +0.95 | +$49 |
| $50 cross, +$15 | 148 | 46.6% | 40.2% | +1.59 | +$38 |
| 1h $100 cross, +$20 | 41 | 31.7% | 33.7% | −0.28 | −$73 |

**What it means.** The development edge shrank from +7.9 to +1.2 points on unseen data. That is the usual fate of the
best of many tries: a selection effect, not a market property. The validation step exists to catch exactly this.

**Totals:**
- **448 development trials and 1 validation test.**
- **No setup, filter, confirmation, entry-price method or round-number rule has shown a TP-first rate reliably above
  random entries, let alone 90%.**
