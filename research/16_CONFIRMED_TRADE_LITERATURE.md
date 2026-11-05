# 16 — Literature: what can raise the chance that a trade reaches its target first? (2026-11-05)

**The operator's question:** "Do deep research on literature: what we can do to achieve our targeted confirmed
trades." The target is 90 of 100 trades reaching +$13 before −$13 ($650 / $650 at 0.5 lot).

This review extends `01_RESEARCH_LITERATURE_REVIEW.md` with the literature found on 2026-11-05 and with what B1–B10
(648 recorded trials) have already tested.

**Verification marks:**

- **V-search:** title, authors, venue and year were seen in a source this session.
- **secondary:** the claim comes from a summary, not the paper itself.

Nothing here claims that a method works on XAUUSD until our own out-of-sample test says so.

## 1. Bottom line

1. **No peer-reviewed study we found shows a public, repeatable way to make 90% of 1:1 trades win at intraday
   horizons.** The documented effects in gold are real but small. They move the odds of +$13 before −$13 by fractions
   of a percentage point, not by 40 points.
2. **"Confirmation" methods can only sharpen a signal that already has skill.** Meta-labeling and agreement filters
   are examples. Here the primary signals have measured AUC ≈ 0.50, and timeframe agreement tested worse than random
   (B5, B6).
3. **High win rates are available only by moving the stop away from the target.** The cost is larger losses, a
   negative expectancy after costs, and fast prop-account failure.
4. **The evidence that does exist supports a different goal:** positive expectancy and survival. That means fewer,
   independent trades; volatility-aware sizing; not trading against strong trends; and testing the few documented
   gold effects honestly.

## 2. Why 90% at 1:1 means knowing the direction almost exactly

Model price as a random walk with drift μ and volatility σ. The chance of reaching +a before −a is
1 / (1 + e^(−2μa/σ²)).

For +$13 / −$13 and gold's daily volatility of about $60–80 (1.5–2% of the price), the drift a trader would need to
know in advance is:

| Wanted: +$13 before −$13 | Known drift needed (σ $60 / day) | (σ $80 / day) |
|---|---|---|
| 55% | $28 per day | $49 |
| 60% | $56 | $100 |
| 70% | $117 | $209 |
| 80% | $192 | $341 |
| **90%** | **$304** | **$541** |

**What documented effects are worth.** A very strong bull year (+$1,250 over about 250 trading days) is about $5 a
day, which gives 50.9%. A $1–2 a day anomaly gives 50.2–50.4%. Real prices have jumps, intraday seasonality and mean
reversion, so this is a guide, not a law. But it explains every B-phase result: published edges are too small to
change a short barrier race by much.

## 3. What the literature says, family by family

| Family | Key evidence | What it means here | Tested here? |
|---|---|---|---|
| **Technical rules on commodity futures** | Marshall, Cahan & Cahan (2008, *J. Banking & Finance*; secondary): 7,846 rules on 15 commodities including gold, 1984–2005; data-snooping control removes reliable profits in 14 of 15. Park & Irwin (*J. Futures Markets*; secondary): Reality Check / SPA over 1985–2004, profits in only 2 of 17 US futures | The same pattern as B1–B4 (rules rejected after Reality Check) | Yes: B1–B4, B10 |
| **Overnight vs daytime returns in gold** | Blose, Gondhalekar & Kort (2018, *Journal of Economics and Finance*; V-search): overnight returns significantly positive and day returns significantly negative in COMEX futures, the London fix, miners and ETFs (1985–2012); the authors report it survives costs. Equity analogue: Lou, Polk & Skouras (2019, *JFE*; V-search) | **The one documented, gold-specific direction effect.** Probably small per day (§2) and possibly weaker since 2012 | **No**: candidate B11-a |
| **Intraday momentum** | Gao, Han, Li & Zhou (2018, *JFE*; V-search): the S&P 500 ETF's first half-hour return predicts its last half-hour, R² ≈ 1.6%, stronger with volatility and volume. Jin, Kearney, Li & Yang (2020, *J. Futures Markets*; V-search): the same in Chinese copper, rebar and soy futures | Not yet shown for gold. An R² of 1.6% is a small edge | **No**: candidate B11-b |
| **London fix window** | Caminschi & Heaney (2014, *J. Futures Markets* 34(11); V-search): volume and volatility jump at the PM fix start, before the price is published ("information leakage"; disputed by Fertig in LBMA *Alchemist*) | The fix became an ICE auction in March 2015. A pre-2015 effect may not survive | No; low priority |
| **Intraday seasonality in gold** | Iwatsubo, Watkins & Xu (2018, *J. Commodity Markets*; V-search): efficiency, liquidity and volatility differ by session (Tokyo uninformed, New York informed); a CBS thesis (2019, not peer reviewed) reports hat-shaped seasonality and moves around the fixes | Volatility and liquidity by session are predictable; direction weakly at best | Sessions: B1 (breakouts rejected) |
| **Meta-labeling / confirmation** | López de Prado (2018, book; R23); Joubert (2022, *J. Financial Data Science*; cited, not read): a second model filters a high-recall primary model to raise precision; it adds no new signal | Useful only after a primary signal shows skill; it can trade coverage for precision | Agreement filters: B6 (worse than random) |
| **News reactions** | Andersen et al.: prices adjust within minutes | After a closed 15m bar, the next $13 is a coin flip | Yes: B8 (rejected) |
| **Order flow** | Cont, Kukanov & Stoikov (2014; R20): order-book imbalance explains seconds-to-minutes price changes | The horizon is far shorter than a $13 race | Yes: B5 (AUC 0.50) |
| **Trend following** | Moskowitz, Ooi & Pedersen (2012); Hurst, Ooi & Pedersen (2017) (R3, R5): robust over 1–12 months, with **low win rates** and large winners | The opposite profile to a 90% hit rate; works through payoff, not accuracy | Intraday TSMOM: B1 (rejected) |
| **Volatility forecasting** | Bollerslev (1986); Andersen & Bollerslev (1997) (R13, R14); Moreira & Muir (2017; R19) | Volatility is forecastable; direction is not. Use it for stops and sizing | Mechanics in the engine |

## 4. What the evidence says about traders and the 90% goal

- **Retail outcomes.** ESMA's 2018 intervention found that 74–89% of retail CFD accounts lost money (secondary
  reporting of the ESMA decision).
- **Day traders.** In Taiwan, fewer than 1% of day traders earned predictable positive returns net of fees (Barber,
  Lee, Liu & Odean, 2014, *J. Financial Markets*). 97% of day traders are likely to lose (Barber, Lee, Liu, Odean &
  Zhang, 2020, *Review of Asset Pricing Studies*; secondary).
- **Prop firms.** Self-reported industry data, not audited: about 5–14% of challenges pass, and only about 7% of
  buyers are ever paid.
- **The win-rate trap.** Investors prefer realising winners to losers, and the winners they sell go on to outperform
  the losers they keep (Odean, 1998, *J. Finance*; V-search). Chasing a high hit rate usually means small wins and
  large losses: the payoff of selling options, "picking up coins in front of a steamroller".
- **Proof size.** To prove 90% with a 95% lower bound of 85% takes about 184 independent results (`01` §3). A run of
  9 out of 10 proves only "more than 60%".

## 5. What we can still do (each needs a registration and the operator's approval)

| ID | Test | Source | Data and rule (to be fixed in the registration) | Honest expectation |
|---|---|---|---|---|
| **B11-a** | Gold overnight-up / daytime-down | Blose et al. (2018) | Development 2020–2023: BUY at the COMEX day close (13:30 New York) and SELL at its open (08:20 New York); +13 / −13 scaled, first passage inside the window; also the raw drift and its t-statistic | If real: a small positive drift and a TP-first rate a point or two above random. The value is knowing whether to lean with or against the clock |
| **B11-b** | Intraday momentum | Gao et al. (2018); Jin et al. (2020) | Development: the direction of the first 30 minutes after the COMEX open → trade to the COMEX close at +13 / −13 scaled, and the last half-hour return | R² of 1–2% at best: a few points of hit rate, not 90% |
| **B11-c** | The B10 lead: the engine's own 15m signals | B10 secondary (64.3%, n 70, development) | Opens the **sealed validation** partition (2023-01 → 2024-07) once, for this one stream, unchanged | It is likely to regress toward 50%: one of 18 comparisons, and 1h was 40%. Only a pass there earns a forward test |
| B11-d (later) | Meta-label a stream that passed B11-c | López de Prado; Joubert | Purged CV on development, then the validation result | Only if B11-c passes |

**What we will not do, as the literature warns:**

- tune many variants on the same data (Sullivan, Timmermann & White, 1999; Bailey et al., 2017);
- widen the stop to manufacture a hit rate;
- claim a probability we have not measured out of sample.

## 6. What helps a prop account now (literature-consistent, no new claims)

1. **One idea, one trade.** This is now in the alerts (REPEAT). Correlated losses kill accounts (§4).
2. **Do not fight a trend-change warning.** Breaks continued in the November rally. The 3-year data says breaks are
   not an edge, so this is risk avoidance, not a signal.
3. **Size for streaks.** At about 50% odds, 4–5 losses in a row are normal over 100 trades. With a 5% daily limit on
   $25k, 0.5 lot allows one loss a day; 0.25 lot allows three. This is volatility-aware sizing (Moreira & Muir).
4. **Measure, then trust.** The live validation marks a group STRONG only with 30+ results and a 95% range above
   break-even. The B9 grab test reports at 30, 40 … 100 results.

## 7. Sources (seen this session)

- Blose, Gondhalekar & Kort (2018), "Overnight versus day returns in gold and gold related assets", *Journal of Economics and Finance*: https://link.springer.com/article/10.1007/s12197-017-9403-0
- Lou, Polk & Skouras (2019), "A tug of war: Overnight versus intraday expected returns", *JFE*: https://www.sciencedirect.com/science/article/abs/pii/S0304405X19300650
- Gao, Han, Li & Zhou, "Market intraday momentum" (working-paper PDF): https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf
- Jin, Kearney, Li & Yang (2020), "Intraday time-series momentum: Evidence from China", *J. Futures Markets*: https://econpapers.repec.org/RePEc:wly:jfutmk:v:40:y:2020:i:4:p:632-650
- Caminschi & Heaney (2014), "Fixing a leaky fixing", *J. Futures Markets* 34(11): https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html
- LBMA *Alchemist*, "Has there been a decade of London PM gold fixing manipulation?": https://www.lbma.org.uk/alchemist/issue-73/has-there-been-a-decade-of-london-pm-gold-fixing-manipulation
- Iwatsubo, Watkins & Xu, intraday seasonality in gold and platinum futures (RIETI DP): https://www.rieti.go.jp/en/publications/summary/17110007.html
- Odean (1998), "Are investors reluctant to realize their losses?", *J. Finance*: https://zendy.io/title/10.1111/0022-1082.00072
- Barber, Lee, Liu & Odean (2014), *J. Financial Markets* 18, 1–24: https://econpapers.repec.org/RePEc:eee:finmar:v:18:y:2014:i:c:p:1-24
- Barber, Lee, Liu, Odean & Zhang (2020), "Learning, fast or slow", *Review of Asset Pricing Studies*: https://ideas.repec.org/a/oup/rasset/v10y2020i1p61-93..html
- ESMA (2018), binary options prohibited and CFDs restricted: https://www.esma.europa.eu/node/84933
- Commodity-futures technical rules after data-snooping control (summary): https://www.cxoadvisory.com/technical-trading/does-technical-trading-work-with-commodity-futures/
- Meta-labeling overview: https://en.wikipedia.org/wiki/Meta-Labeling
- Prop-firm pass rates (industry, self-reported): https://www.financemagnates.com/forex/only-1-in-20-traders-pass-prop-firm-challenges-reports-the-funded-trader/ and https://track360.io/blog/prop-trading-industry-statistics-2026
