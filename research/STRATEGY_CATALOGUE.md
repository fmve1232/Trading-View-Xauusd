# Strategy catalogue: everything tested for "+$15 / +$20 in the same direction before −$13" (2026-11-07)

**Request (operator, 2026-11-07):** "Just give me the confirm price movement of minimum $15 to $20, in which markets
first move to same direction and hit the TP first before reversing back … list down all the strategies, all the
procedures, calibrations, indicators, literature."

**Sources:**
- Each row cites its study file in `research/`.
- Every number comes from a committed result file or registration.
- The trial log (`research/trials.jsonl`) holds 1,106 tests at this writing.
- **New in this catalogue: B20,** the candle-run calibration (section 4; `registrations/B20.json`, `B20_RESULTS.md`).

## 1. The arithmetic every strategy faces

**Geometry.**
- When price has no predictable direction at the trade's scale, the chance that the target comes before the stop is
  S / (S + T).
- **Measured** on 2020–22 random entries (B13-0, B20), it matches within 0.5 points.

**Break-even.** The break-even includes costs: the model's $0.77–0.97 per oz, or the operator's measured $0.26.

| Stop −$13 and target | No-edge chance of TP first (theory) | Measured, random entries 2020–22 | Break-even after model cost | Break-even at $0.26 cost |
|---|---|---|---|---|
| +$10 | 56.5% | about 57% (B13) | about 60% | 57.7% |
| +$13 | 50.0% | about 50% (B13) | about 53% | 51.0% |
| **+$15** | **46.4%** | **46.2%** (B20, about 130,000 entries) | **49.2–49.9%** | **47.4%** |
| **+$20** | **39.4%** | **39.0%** (B20) | **41.7–42.3%** | **40.2%** |

**The requirement.** To make money at +$15 / −$13, a rule must win about 3 points more often than a random entry,
consistently, on data it was not built on. That is the bar every strategy below was measured against.

## 2. How every strategy was tested (the procedure)

1. **Registration first.**
   - The rule, the bins and the pass test are committed to `research/registrations/` before any code or data.
   - No threshold is changed after a result is seen.
2. **Data.**
   - Twelve Data XAU/USD 15m and 1h, 2020–2026. The site's live data agrees with the operator's MT5 within $1–3.
   - **Partitions:**
     - development 2020-01 → 2023-01 (open);
     - validation 2023-01 → 2024-07 (opened only for a registered candidate);
     - holdout 2024-07 → 2026-01 (never opened).
3. **Outcome labeller** (`quantum/research/b13.race`, `harness.simulate`).
   - Each trade runs from the decision bar's close, first touch on the following bars, for one trading day.
   - A bar touching both levels counts as a **loss** unless it opened beyond the target.
   - Gaps fill at the open.
   - Distances are scaled to a $4,000 price.
4. **Costs.** Spread by session, 2 × $0.20 slippage and $7 per lot commission are charged on every trade.
5. **Baseline.** Random entries at every bar with the same direction mix (and the geometry above).
6. **Statistics.**
   - Wilson intervals, t-tests on net results and day-clustered errors where samples overlap (B20).
   - Multiple-testing control: Holm, Benjamini–Hochberg, White's Reality Check, PBO by CSCV and the Deflated Sharpe
     Ratio.
   - Walk-forward and Monte Carlo.
7. **Independent check.**
   - A development "pass" earns one validation run.
   - Only a validation pass opens the holdout.
   - Only a holdout pass justifies a live forward test.

## 3. The catalogue

All rows use a −$13 stop unless stated; TP is the target.

| Study | Strategy (procedure) | Indicators / inputs | Source | Best measured result | Random | Verdict |
|---|---|---|---|---|---|---|
| B1 | Momentum, Donchian channels, session breakouts, volatility conditioning, mean reversion (100 trials) | Returns over k bars, highest / lowest n, session opens, ATR, Bollinger | Moskowitz et al. 2012; Kim et al. 2016; Hurst et al. 2017; Bollerslev 1986 | 0 of 100 with positive net expectancy | — | REJECT |
| B2 / B2b / B2c | Nine SMC setups: FVG retest, order block, BOS, CHoCH, liquidity sweep, etc. At +$20 / +$15 / +$10 / +$2 before −$10, and +$20 before −$20 | Market structure, fair-value gaps, order blocks | Practitioner (ICT / SMC); no peer-reviewed evidence | Best: 1h FVG retest 52.6% vs 52.1% break-even (+$20 / −$20); 0 of 54 net-positive at −$10 | Matched | REJECT |
| B3 | Trend alignment + confirmation entry + SMC sequences (210 trials) | EMA alignment, BOS / CHoCH sequences, displacement | As B1 / B2 | 57.1% / 48.6% / 43.5% at +$10 / +$15 / +$20 on small samples | Matched | REJECT |
| B4 | Round numbers ($50 / $100), session-open momentum, limit entries | Price levels, first 30 minutes of London / New York | Gao et al. 2018; Elaut et al. 2018 | Round numbers 47.6% vs 43.3% break-even at +$15 (z 2.35) on development; **validation 41.5% vs 40.3%** | 40.3% | FAIL on validation |
| B5 | Real COMEX order flow: follow / fade 15- and 60-minute aggressor imbalance; logistic and boosted models (74.5M trades) | Buy / sell aggressor volume | Cont et al. 2014 | AUC 0.50; all lose after costs | Matched | REJECT |
| B6-explore | Site signals only when the 1h / 4h agree | Multi-timeframe direction | — | Full agreement 36.5% at ±$13 | ~50% | Worse than random |
| B7 | Macro: dollar, 10-year and real yields, VIX, oil, breakevens, COT | FRED / Yahoo / CFTC series | Baur & Lucey 2010; Erb & Harvey 2013 | Dollar + real yield agree 54.7% (n 150), not significant | ~50% | REJECT (Reality Check p 0.999) |
| B8 | US news: follow / fade the first 15–30 minutes of CPI, payrolls, FOMC | Release times | — | Fade payrolls 65.7% (n 35), not significant | ~50% | REJECT (Reality Check p 0.822) |
| B9-explore → B9-GRAB-FWD | Liquidity GRAB (wick through a day / week / month level, close back) | PD / PW / PM levels, sweeps | Practitioner | 15m GRAB 61.7% (n 60) on Sep–Nov 2026; **49.4% of 913 on 2020–22** (B10); live: 1 of 3 so far | 46.6% | Live test running |
| B10 | Release the higher-timeframe gate after a weekly break; GRAB in ranges; BREAK in trends | Engine gate, PWH / PWL, regime | — | BREAK in trend 52.4% (n 540), GRAB in range 49.7% (n 394) at ±$13 | ~50% | FAIL |
| B10 / B13-1 (corrected) | The engine's own signals | All engine inputs (EMA, VWAP, RSI, ADX, structure, HTF bias, session, TQ) | — | 64.3% of 70 counted per signal → **52.2% of 23 counted per idea** (2020–22); 45.8% of 24 (2023–24) | ~50% | No edge (erratum, B19) |
| B12-explore | The operator's multi-timeframe level criteria: D / PD / W / PW / M / PM, 4h / 1h / 30m highs and lows, swings, trend vote, rejection, confluence, room, volume (±$22) | Levels, swing points, volume | Operator | No variant beats random; each filter made it worse (45.3–51.5%) | 54.1% | REJECT |
| B13 | Overnight-up / day-down; intraday momentum; a 31-feature boosted model | Clock, first / last half-hour returns, 31 features | Blose et al. 2018; Gao et al. 2018; López de Prado 2018 | Overnight BUY 48.0% (n 641); day SELL 47.7%; intraday momentum 45.7% (n 599); model AUC 0.51 | 46.0–46.4% | FAIL |
| B14 | A two-timeframe BREAK while the engine's gate blocks that side | Liquidity breaks, engine gate | — | 48.0% of 229 at +$15 | 46.3% | FAIL |
| B16 | Sweeps and breakouts of PD / PW / PM, today's, last-4h and last-1h highs / lows, with order blocks, value area and POC | Levels, OB, volume profile | Operator | SWEEP 46.6% of 5,918; BREAKOUT 46.1% of 6,729 | 46.2–46.3% | FAIL |
| B17 | B16 setups + all four confirmations: day / week / month level, trend 3 of 3, engine bias, London / NY | As B16 + EMA trend votes + engine bias + session | Operator | **51.6% of 184** (p 0.072), about one a week | 46.3% | FAIL (not significant) |
| B18 | 4h candle breakout + the four confirmations | 4h highs / lows + as B17 | Operator | 45.8% of 319 | 46.2% | FAIL |
| B19-explore | The rule that made last week 4 of 4 (BUY + level + engine bias) | As B18 | Hindsight | 47.3% of 368 on 2020–22 | 46.7% | Selection, not an edge |
| **B19** | **Trigger → wait for a 15m CLOSE $15 / $20 beyond it, same direction → plan** (−$13; +$15–$30; ATR and structure stops; R:R ≥ 1) | Engine signals; BOS / MSS / CHoCH + bias + VWAP + session; RSI, EMA20, ATR filters | Operator brief | Development +$2.32 / oz (125 trades, t 1.52); **validation −$3.04**; last month 0 of 2 | N2 −$1.2 | FAIL |
| **B20** | **Candle runs: enter in the direction candles are already running**, calibrated by run length, run size, candle body, session, 1h trend, day move; plus a purged logistic model | Consecutive closes, $ moved, body / ATR, sessions, 1h EMA20 / EMA100, day open | Moskowitz et al. 2012 (momentum, at months); Gao et al. 2018 (intraday) | Every bin within ±2.2 points of random; "≥ 3 candles, ≥ $15 moved, 1h trend agrees" **44.6% of 1,364**; model AUC 0.49 | 46.2% | FAIL (no candidate) |
| **B21** | **The site's liquidity / breakout alerts WITH confirmation**, no session filter: GRAB, BREAK, SWEEP, BREAKOUT, then a 15m close $15 / $20 beyond the alert first | PD / PW / PM, today's, 4h and 1h levels, sweeps, closes beyond, OB / value area | Operator | Confirmed: 43.4–49.6% at +$15 first; "any time" 62–72% | 46.2% first; 64–66% any time | FAIL (8 of 8) |
| **B22** | **Every confirmation family in calibrated ML**: LR, naive Bayes, random forest, HGB, XGBoost, LightGBM, ensemble; raw / isotonic / Platt; HMM regimes; CUSUM | 55 features (all of the above) | López de Prado 2018; Niculescu-Mizil & Caruana 2005; Hamilton 1989 | AUC 0.47–0.51; best calibrated top 5% 46.3% | 46.3% | FAIL |
| **B23** | **B22's raw-ensemble tail, frozen** | As B22 | B22 (exploratory) | Development top 0.5% 62.2% → **validation 52.8% of 394 (38 days), 95% 30–76%** | 46.3% | FAIL; holdout sealed |
| **B25** | **Execution timing after a $15 close** (delays 0–60 min, the site's 7-min latency, retest limit, 5m confirmation, stop order at the level) | B19 / B21 triggers | PR #90 audit (engine 60% → 30% at +15 min) | All alert types: close 46.4%, +15 min 47.5%, +30 min 48.9%, retest 45.2% (misses 406 winners), stop order 39.9%; 5m: site latency 46.6% vs close 39.8%, 5m close 40.2% | 46.3% | Delay does not hurt; no timing beats the close |
| TARGET_MOVE_90PCT | "90% of trades move $10–20 my way" | Every site decision source | — | Every source equals a random entry; 90% needs about $90 of room | — | Arithmetic |

**Live, on new data:**
- **B15-ENGINE-FWD:** engine signal alerts, one plan per idea, ±$13. 0 results so far; first check at 30.
- **B9-GRAB-FWD:** 15m liquidity grabs. 3 results, 1 TP.
- **The website's frozen forward test** (Pine-reference arms on 1h). Still running.

## 4. B20 in full: what candle runs do to the odds of +$15 before −$13

**Data:** 2020–22, 64,838 decided 15m closes, each traded in the direction of its own candle.

**Significance** is clustered by trading day; Holm runs over 58 tests.

| Feature | Bin | n | +$15 first | vs random | Net $ / oz |
|---|---|---|---|---|---|
| Consecutive candles in one direction | 1 | 33,642 | 46.1% | −0.2 | −0.96 |
| | 2 | 16,378 | 45.9% | −0.3 | −0.99 |
| | 3 | 7,895 | 46.0% | −0.3 | −0.98 |
| | 4 | 3,628 | 46.8% | +0.5 | −0.75 |
| | 5 | 1,782 | 46.8% | +0.5 | −0.75 |
| | 6 or more | 1,513 | 47.8% | +1.5 | −0.47 |
| $ already moved in the run | under $5 | 43,444 | 46.3% | +0.0 | −0.91 |
| | $5–10 | 13,611 | 45.8% | −0.4 | −1.01 |
| | $10–15 | 4,293 | 46.0% | −0.2 | −0.93 |
| | **$15–20** | 1,687 | **44.2%** | −2.1 | −1.43 |
| | $20–30 | 1,136 | 46.0% | −0.3 | −0.93 |
| | $30 or more | 667 | 48.3% | +2.1 | −0.28 |
| Last candle body / ATR | under 0.5 | 39,853 | 46.4% | +0.1 | −0.87 |
| | 0.5–1.0 | 17,378 | 45.6% | −0.6 | −1.08 |
| | 1.0–1.5 | 5,339 | 45.6% | −0.6 | −1.06 |
| | 1.5–2.5 | 1,977 | 45.7% | −0.5 | −1.03 |
| | 2.5 or more | 291 | 50.5% | +4.4 (z 1.49, Holm p 1.00) | +0.33 |
| Session | London only | 21,009 | 46.4% | +0.2 | −0.77 |
| | London + New York | 5,752 | 45.8% | −0.5 | −0.95 |
| | New York only | 10,799 | 45.4% | −0.9 | −1.06 |
| | Asia / off | 27,278 | 46.2% | −0.0 | −1.03 |
| 1h trend (EMA20 vs EMA100) | agrees | 32,508 | 46.2% | −0.1 | −0.91 |
| | disagrees | 32,330 | 46.0% | −0.2 | −0.97 |
| Move since the day's open | against (< 0) | 28,215 | 46.6% | +0.4 | −0.79 |
| | $0–10 | 17,818 | 45.9% | −0.3 | −1.04 |
| | $10–20 | 8,635 | 44.6% | −1.7 | −1.36 |
| | $20–40 | 6,651 | 46.9% | +0.6 | −0.68 |
| | $40 or more | 3,519 | 45.2% | −1.0 | −1.13 |
| **Combined: ≥ 3 candles, ≥ $15 moved, 1h trend agrees** | | 1,364 | **44.6%** | −1.7 | −1.30 |
| Logistic model, most confident tenth | | 6,484 | 44.6% | −2.2 | −1.36 |

**At +$20 the picture is the same:**
- all events 39.0% vs 39.0% random;
- 6+ candles 41.3%;
- the combined rule 38.8%;
- model AUC 0.48.

**Calibration.**
- The model's predicted chances (43.6–48.4%) did not line up with what happened (44.2–49.2%).
- Its highest-confidence tenth did worst, and its Brier score was worse than simply quoting the base rate. There is
  nothing to calibrate.
- **A run that has already moved $15–20 continued +$15 before −$13 *less* often than a random entry (44.2%).** The
  candles "going in the same direction" on the screenshots are visible after the fact. At the moment they are
  happening, they do not change which comes next.

## 5. Indicators and inputs covered

| Input | Studies |
|---|---|
| EMA 20 / 50 / 100 / 200, trend votes | B1, B3, B17, B18, B19, B20 |
| VWAP (session, weekly, monthly) | engine, B19 |
| RSI, momentum oscillators | B1, B19 (F1), engine |
| ATR, volatility regimes, Bollinger | B1, B19, B20, engine |
| ADX / DMI | engine |
| Market structure (BOS, CHoCH, MSS), displacement | B2, B3, B19, engine |
| Fair-value gaps, order blocks | B2, B3, B16 |
| Liquidity sweeps / grabs / breaks of PD / PW / PM, equal highs / lows | B9, B10, B14, B16, B17 |
| Today's, 4h, 1h and 30m highs / lows; swing points | B12, B16, B18 |
| Volume profile (POC, value area) | B16 |
| Round numbers | B4 |
| Sessions, kill zones, session opens | B4, B13, B17, B20 |
| Multi-timeframe agreement | B6, B12, B14, B17 |
| Candle runs, run size, candle body | B20 |
| Macro: DXY, yields, real yields, VIX, oil, breakevens, COT | B7, engine |
| News: CPI, payrolls, FOMC | B8, engine |
| Order flow (aggressor imbalance) | B5 |
| Machine learning (boosted trees, logistic), meta-labelling | B5, B13, B20 |
| Two-stage confirmation (trigger, then a $15 / $20 close) | B19 |

## 6. Literature used

**Gold and intraday effects:**
- Blose, Gondhalekar & Kort (2018), *J. Economics and Finance*: overnight vs day returns in gold.
- Gao, Han, Li & Zhou (2018), *J. Financial Economics* 129: market intraday momentum.
- Jin, Kearney, Li & Yang (2020), *J. Futures Markets* 40: intraday time-series momentum.
- Elaut, Frömmel & Lampaert (2018), *J. Financial Markets* 37: intraday momentum in FX.
- Baur & Lucey (2010), *Financial Review*: gold as hedge / safe haven.
- Erb & Harvey (2013), NBER w18706: the golden dilemma.

**Momentum and volatility:**
- Moskowitz, Ooi & Pedersen (2012), *J. Financial Economics* 104: time-series momentum (1–12 months).
- Kim, Tse & Wald (2016), *J. Financial Markets* 30: momentum and volatility scaling.
- Hurst, Ooi & Pedersen (2017): a century of trend following.
- Bollerslev (1986): GARCH.
- Andersen & Bollerslev (1997): intraday periodicity.
- Moreira & Muir (2017): volatility-managed portfolios.

**Order flow:**
- Cont, Kukanov & Stoikov (2014), *J. Financial Econometrics*: order-flow imbalance.

**Market efficiency:**
- Fama (1970): efficient markets.
- Lo (2004): adaptive markets.

**Overfitting and testing method:**
- Sullivan, Timmermann & White (1999) and White (2000): data snooping and the Reality Check.
- Bailey & López de Prado (2014): the Deflated Sharpe Ratio.
- Bailey, Borwein, López de Prado & Zhu (2014, 2017): pseudo-mathematics; PBO.
- Harvey, Liu & Zhu (2016): t > 3 for new factors.
- Benjamini & Hochberg (1995).
- Holm (1979).
- Politis & Romano (1994): the stationary bootstrap.
- López de Prado (2018): triple barrier, purged cross-validation.
- Gneiting & Raftery (2007), Brier (1950), Niculescu-Mizil & Caruana (2005): calibration and scoring.

Full references with DOIs: `01_RESEARCH_LITERATURE_REVIEW.md`, `16_CONFIRMED_TRADE_LITERATURE.md`,
`ENTRY_PRICE_RESEARCH.md`.

## 7. What the evidence supports

1. **$15–$20 moves are common.**
   - The median day ranged about $60 in Oct–Nov 2026.
   - From a random moment, price reaches +$15 in a given direction at some point in the day about 65% of the time
     (B16).
   - Whether it gets there **before** −$13 is the part no tested input predicts: 46% at +$15 and 39% at +$20, the
     same as a coin weighted by the distances.
2. **Waiting for confirmation does not change that.** By the time a $15 run (B20) or a $15 close beyond a trigger
   (B19) is visible, the next $15 is again a 46% question.
3. **The only setting that moves "TP first %" is the ratio of stop to target.** It changes how often you win and how
   much each win pays. It does not change the expected result after costs.
4. **Nothing has passed.** No strategy listed here has passed an independent test. The two live tests (B15, B9)
   continue on new data. They are the only route by which a claim could become proven.
