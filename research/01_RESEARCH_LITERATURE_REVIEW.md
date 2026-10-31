# 01 — Literature review: what the evidence supports, and what it means for this platform (2026-11-01)

**Rules for this review:**

- Only references whose title, authors, year and venue were checked are cited. The verification status is given for
  each.
- Empirical findings are separated from practitioner folklore.
- "Applies to this platform" says what follows for design. It never claims that a method works on XAUUSD until our
  own out-of-sample test says so.

## 1. Verified bibliography

**Status key:**

- **V** = title, authors, year, venue and DOI confirmed (this session, or the 2026-10-22 audit).
- **V-venue** = venue and pages confirmed; DOI not confirmed.
- **book** = monograph.

| # | Reference | Status | Design consequence for the platform |
|---|---|---|---|
| R1 | Fama, E. (1970). Efficient Capital Markets: A Review of Theory and Empirical Work. *Journal of Finance* 25(2), 383–417 | V-venue | The null hypothesis for every signal is "no exploitable predictability after costs". The burden of proof is on the strategy |
| R2 | Lo, A. W. (2004). The Adaptive Markets Hypothesis. *Journal of Portfolio Management* 30, 15–29 | V-venue (DOI not confirmed) | Predictability is time-varying and regime-dependent. No fixed rule should be expected to work in every condition; monitor drift |
| R3 | Moskowitz, Ooi & Pedersen (2012). Time Series Momentum. *Journal of Financial Economics* 104(2), 228–250. doi:10.1016/j.jfineco.2011.11.003 | V | Trend persistence over **1–12 month** horizons across futures. Evidence for intraday persistence must come from our own data |
| R4 | Kim, Tse & Wald (2016). Time Series Momentum and Volatility Scaling. *Journal of Financial Markets* 30, 103–124. doi:10.1016/j.finmar.2016.05.003 | V | Much of time-series momentum's reported alpha comes from **volatility scaling**; it weakened after 2009. Separate the signal from the sizing in every test |
| R5 | Hurst, Ooi & Pedersen (2017). A Century of Evidence on Trend-Following Investing. *Journal of Portfolio Management*, Fall 2017 | V-venue | Trend following is robust over a century on **monthly** data, net of estimated costs. It does not transfer automatically to 5m–1h |
| R6 | Sullivan, Timmermann & White (1999). Data-Snooping, Technical Trading Rule Performance, and the Bootstrap. *Journal of Finance* 54(5), 1647–1691. doi:10.1111/0022-1082.00163 | V | Testing many technical rules on one series produces false winners. Use White's Reality Check / SPA over the **full** set of rules tried |
| R7 | White, H. (2000). A Reality Check for Data Snooping. *Econometrica* 68(5), 1097–1126 | V (2026-10-22) | As R6 |
| R8 | Bailey, Borwein, López de Prado & Zhu (2017). The Probability of Backtest Overfitting. *Journal of Computational Finance* 20(4). doi:10.21314/JCF.2016.322 | V | Use CSCV to estimate PBO before trusting any selected configuration |
| R9 | Bailey & López de Prado (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management* 40(5) | V (2026-10-22) | Deflate every reported Sharpe for the number of trials, skew and kurtosis |
| R10 | Bailey, Borwein, López de Prado & Zhu (2014). Pseudo-Mathematics and Financial Charlatanism. *Notices of the AMS* 61(5) | V (2026-10-22) | Minimum backtest length grows with the number of configurations tried |
| R11 | Harvey, Liu & Zhu (2016). … and the Cross-Section of Expected Returns. *Review of Financial Studies* 29(1), 5–68 | V (2026-10-22) | A new factor needs t > 3, not 2 |
| R12 | Benjamini & Hochberg (1995). Controlling the False Discovery Rate. *JRSS B* 57(1), 289–300 | V-venue | FDR control when screening many setups / features |
| R13 | Bollerslev, T. (1986). Generalized Autoregressive Conditional Heteroskedasticity. *Journal of Econometrics* 31(3), 307–327. doi:10.1016/0304-4076(86)90063-1 | V | Volatility clusters and is forecastable. Use it for stop sizing and regime classification, not for direction |
| R14 | Andersen & Bollerslev (1997). Intraday Periodicity and Volatility Persistence in Financial Markets. *Journal of Empirical Finance* 4(2–3), 115–158. doi:10.1016/S0927-5398(97)00004-2 | V | Intraday volatility has a strong time-of-day pattern. Normalise volatility by session before comparing bars |
| R15 | Hamilton, J. D. (1989). A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle. *Econometrica* 57(2), 357–384 (JSTOR 1912559) | V-venue | The Markov-switching regime model. Candidate regime classifier, adopted only if it beats simple rules out of sample |
| R16 | Adams & MacKay (2007). Bayesian Online Changepoint Detection. arXiv:0710.3742 | V | Online change-point detection; a candidate for the trend-transition engine |
| R17 | Gneiting & Raftery (2007). Strictly Proper Scoring Rules, Prediction, and Estimation. *JASA* 102(477), 359–378. doi:10.1198/016214506000001437 | V | Score probabilities with proper rules (Brier, log loss), never accuracy alone |
| R18 | Niculescu-Mizil & Caruana (2005). Predicting Good Probabilities with Supervised Learning. *ICML*, 625–632. doi:10.1145/1102351.1102430 | V | Boosted trees, SVMs and random forests are mis-calibrated raw. Platt scaling or isotonic regression on **held-out** data |
| R19 | Moreira & Muir (2017). Volatility-Managed Portfolios. *Journal of Finance* 72(4), 1611–1644. doi:10.1111/jofi.12513 | V | Scaling exposure inversely to volatility improves Sharpe for many factors. A sizing layer, testable separately from signals |
| R20 | Cont, Kukanov & Stoikov (2014). The Price Impact of Order Book Events. *Journal of Financial Econometrics* 12(1), 47–88. doi:10.1093/jjfinec/nbt003 | V | Order-flow imbalance (from the **order book**) explains short-horizon price changes. It **cannot** be computed from OTC spot bars or tick volume |
| R21 | Baur & Lucey (2010). Is Gold a Hedge or a Safe Haven? *Financial Review* 45(2), 217–229 | V (2026-10-22) | Gold's relationships with stocks and bonds are regime-dependent (safe haven only in extreme declines). Model them as time-varying |
| R22 | Erb & Harvey (2013). The Golden Dilemma. NBER w18706 | V (2026-10-22) | The gold / real-yield / inflation relations are weak and unstable over short horizons |
| R23 | López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley | book | Triple-barrier labelling, meta-labelling, purged / embargoed CV and CPCV: the labelling and validation design of `09` |
| R24 | Koenker & Bassett (1978). Regression Quantiles. *Econometrica* 46(1) | **not verified in this session** | Quantile regression for target zones. Cite only after verification |
| R25 | Brier, G. W. (1950). Verification of Forecasts Expressed in Terms of Probability. *Monthly Weather Review* 78(1), 1–3 | V-venue | The Brier score |
| R26 | Shiller, R. J. (2000). *Irrational Exuberance*. Princeton University Press | book | Behavioural drivers; context, not a testable intraday rule |

## 2. Method families: evidence, applicability and how we will test (summary)

The full per-method entries (theory, maths, failure modes) go into `05`–`13` as each family is tested. This table
is the decision record. **Status "NOT TESTED" means exactly that.**

| Family | Established evidence | Evidence against / limits | XAUUSD intraday applicability | Test design (development data 2020-01-24 → 2023-01-24) | Status |
|---|---|---|---|---|---|
| Time-series momentum / trend (R3–R5) | Strong at 1–12 months, many markets | Weak after 2009; vol scaling explains much (R4); intraday unproven | Unknown at 5m–1h; plausible at 4h / 1D | Sign of the k-bar return → the next h bars, k, h ∈ a small pre-declared grid; vol-scaled versus not | NOT TESTED |
| Moving-average / Donchian / Turtle | Practitioner; R6 finds rule profits vanish after data-snooping control in the DJIA | Data snooping (R6) | Unknown | As a family under Reality Check | NOT TESTED |
| Momentum oscillators (RSI, MACD, stochastic) | Mostly folklore at intraday horizons | Transformations of the same price path; not independent evidence | Unknown | Ablation against a plain-return baseline | NOT TESTED |
| Mean reversion (VWAP, Bollinger, z-score, OU) | Intraday reversal exists in some FX and futures studies; regime-dependent | Fails in trends; costs dominate at small targets | Unknown; cost-sensitive (our 5m costs are 0.14 R) | Conditional on the range regime; net of costs | NOT TESTED |
| Breakouts (Asian / London / NY / ORB, squeeze) | Practitioner; volatility expansion after compression is documented (R13, R14) | Direction after a breakout is weakly predictable | Session structure matters (R14) | Continuation probability after a defined breakout, against an unconditional baseline | NOT TESTED |
| Market structure / SMC (BOS, CHoCH, sweeps, FVG, OB) | **No peer-reviewed evidence** found; practitioner concepts | Definitions vary; retrospective labelling | Our sweeps / levels: H4's trigger on these levels was **directionless** (`03`) | Exact definitions; TP-before-SL against a matched random-level baseline | H4 variant TESTED: **no edge**. Others NOT TESTED |
| Volume profile / VWAP / auction | Practitioner; centralised-volume concepts | Spot has no central volume; we use a COMEX proxy | Partial (proxy volume) | As SMC | NOT TESTED |
| Volatility models (ATR, EWMA, GARCH, range estimators) | Strong for **volatility** forecasting (R13, R14) | Not for direction | High: stops, sizing, regime | Out-of-sample QLIKE / MSE against realised volatility | NOT TESTED |
| Regime models (HMM, Markov switching, BOCPD) | Established statistics (R15, R16) | Overfit easily; regimes found after the fact | Possible for the volatility state | Out-of-sample: does the regime label change next-period expectancy? | NOT TESTED |
| ML (logistic, GBM, RF, sequence models) | Works when features carry signal; needs calibration (R18) | Overfitting, leakage, non-stationarity (R23) | Unknown; the features so far have shown no skill (Amendment 12) | Purged CV, simple baselines first, DSR / PBO | NOT TESTED |
| Calibration (Platt, isotonic, beta) | Established (R17, R18) | Needs enough resolved outcomes; cannot add skill that is not there | Required before any probability is displayed | Held-out reliability, Brier and log loss | Engine P: TESTED, **no skill** |
| Order flow / microstructure (R20) | Strong on order-book data | Requires L2 / trades data | **Not available** for OTC spot via our feeds; MT5 tick volume is not order flow | — | NOT APPLICABLE with current data |
| Cross-asset / macro (R21, R22) | Relationships exist but are unstable | Regime-dependent, weak at intraday | Our macro vote is display / a gate; no measured skill yet | Rolling, point-in-time lead / lag; out of sample only | NOT TESTED |
| Risk and sizing (R19; Kelly) | Vol-managed sizing improves Sharpe (R19); Kelly is optimal **only with known edge** | With no edge, every sizing rule loses | Sizing is correct mechanically; there is no edge to size | Separate from signal tests | Mechanics TESTED; edge NONE |

## 3. What the literature implies for "90% accuracy"

1. **Under R1 / R2, high unconditional accuracy at intraday horizons is not expected.** The measured direction
   accuracy of the current triggers is 48–50% (`03`).
2. **High *conditional* accuracy is possible for narrowly defined events with a structural cause.** For example,
   "price touches a level within N bars" when the level is very close is nearly certain, but such an event usually
   carries a payoff that the costs consume.
3. **Accuracy must therefore always be reported with:**
   - the event definition;
   - its coverage (the share of bars or opportunities kept);
   - its payoff;
   - its net expectancy;
   - a Wilson interval.

   A 90% hit rate with a 1:9 reward:risk is a losing strategy.
4. **Proving a 90% rate needs data.** For its 95% lower bound to clear 85%, an observed 90% needs **n ≥ 184**
   resolved, independent events. 9 / 10 only proves "more than 60%". `09` §4 has the full table.
