# Order-flow research for XAUUSD (2026-11-01)

The operator asked to go ahead with order-flow data research, after 448 trials and one validation test found no
price-based way to confirm +$10 to +$20 before −$10.

## Summary

1. **Real order flow for gold exists only on COMEX futures** (GC, MGC).
   - Spot XAUUSD trades over the counter, with no consolidated order book.
   - Full exchange data (every order since May 2017) is sold by data vendors (Databento, CME DataMine).
   - A broker's own order book (OANDA) is free with an account, but it covers only that broker's clients.
2. **The academic evidence says order flow predicts price over seconds, not hours.**
   - Order-flow imbalance explains price changes **at the same time** they happen.
   - Its forecasting power peaks about **two price changes ahead** and decays fast.
   - Your trade needs about an hour: +$10 is roughly one hour's typical move in gold.
3. **A free proxy test on our own futures data found nothing at that horizon** (§4). Signed volume was estimated
   from 5-minute bars, which is coarse, so this does not rule out real order flow. It is consistent with the literature.
4. **A study on real CME data is designed below (§5)** and needs a data account from the operator (§6).
   Realistic expectations:
   - the most likely benefit is **better entry timing** (less slippage), worth cents to tens of cents per ounce;
   - it is unlikely to supply the **~$11/hour of predicted drift** that 90% would need (`ENTRY_PRICE_RESEARCH.md` §1).

## 1. What "order flow" can mean for gold, and what data exists

| Source | What it shows | History | Access | Cost (as found) |
|---|---|---|---|---|
| **CME Globex (COMEX GC / MGC) via Databento** | Every order event (MBO) or 10 levels of depth (MBP-10), top of book (MBP-1 / TBBO), trades with aggressor side | MBO from **2017-05-21**; MBP-10 before that | API key; historical download | **$125 free credits** for new accounts; then usage-based $/GB or a subscription. The GC-specific price must be checked in their cost estimator, which could not be reached from this session |
| **CME DataMine (market depth)** | Exchange depth files, nanosecond timestamps, 10 levels | Product-dependent start dates | Purchase via CME; licence agreement | Quote-based (contact CME Data Sales) |
| **OANDA order book / position book** | Distribution of OANDA clients' **pending orders** (stop and limit clusters) and **open positions** in price buckets, snapshot by snapshot | Snapshots by time (the API's order-book call takes an optional time); retention and frequency **unconfirmed** | Free with an OANDA account and API token | Free |
| **Dukascopy ticks** | Bid / ask with "volume" fields per tick | Long history | Free download | Free. The volumes are reported to be **indicative**, not real depth. Project rule: Dukascopy data may not be stored publicly |
| **Yahoo GC=F bars** (already stored) | 5- and 15-minute futures bars **with exchange volume** (no aggressor side) | Since 2026-07-17 in our store | Free | Free; a proxy only |
| MT5 tick volume | Number of the broker's quote changes | — | MT5 | Not order flow |

**Two network notes.**
- `databento.com` and `developer.oanda.com` are not in this cloud session's allowed network. They can be added under
  the environment's network settings (*Allowed domains*).
- The OANDA practice API host would need the same, if that route is chosen.

## 2. What the literature says (searched 2026-11-01)

| Study | Finding | Relevance to +$10 in about an hour |
|---|---|---|
| Cont, Kukanov & Stoikov (2014), *The price impact of order book events*, J. Financial Econometrics 12 | Price changes over short intervals are **linear in order-flow imbalance** (OFI) at the best bid / ask, with slope ∝ 1 / depth. The relation is **contemporaneous** | Explains moves as they happen; does not forecast an hour ahead |
| Xu, Gould & Howison (2019), *Multi-level order-flow imbalance in a limit order book* | Adding deeper levels improves the **contemporaneous** fit out of sample | Same |
| Cont, Cucuringu & Zhang (2023), *Cross-impact of order flow imbalance in equity markets*, Quantitative Finance 23 | **Lagged** OFI (including other assets') improves return forecasts, but mainly at **short horizons, decaying rapidly** | Short horizons only |
| Kolm, Turiel & Westray (2023), *Deep order flow imbalance* | Order-flow features beat raw book states; the effective forecast horizon is **about two average price changes** | Seconds, not an hour |
| Gould & Bonart (2016), *Queue imbalance as a one-tick-ahead price predictor* | Best-queue imbalance predicts the **next** price change | One tick |
| Agricultural futures, CME best bid / offer (Emerald, 2018) | Lagged order imbalance predicts returns **for some contracts**, but generally **no better than trading volume** | Weak, mixed |
| Gold-specific | **No study was found** of gold-futures order flow predicting intraday returns (COMEX or Shanghai) | Untested territory |
| Retail positioning (broker sentiment) | **No academic evidence** found; only broker commentary and indicators | Unsupported |

**The horizon problem in numbers.**
- On COMEX gold the tick is $0.10, so +$10 is 100 ticks.
- The order-flow literature finds predictability lasting a couple of price changes.
- To lift the chance of +$10 before −$10 from 50% to 60%, the predicted drift must hold at about **$2 an hour** for
  the whole trade. For 90%, about **$11 an hour** (`ENTRY_PRICE_RESEARCH.md` §1).
- Order-flow signals are strong and real **inside the next seconds**. That makes them an **execution** tool (when
  exactly to click), not a one-hour direction call.

## 3. Bulk volume classification (the proxy used here)

Easley, López de Prado & O'Hara (2012) estimate the buyer-initiated share of a bar's volume from its price change:

> buy share = Φ(ΔP ÷ σ)

This turns ordinary bar volume into a signed-flow estimate. It is coarse, but it needs no paid data.

## 4. Exploratory test on our own data (B5-explore)

**Declaration and method.**
- Declared in `quantum/research/b5_flow_proxy.py` and committed before running (`832e17ef1`).
- **Data:** Yahoo GC=F 5-minute bars with exchange volume (signals) and spot XAU/USD 5-minute bars (entries and
  paths), 2026-09-09 → 10-30.
- **Signal:** the hourly signed-volume imbalance at or above its trailing 90th percentile (1,883 such bars).
- **Trades:** follow the flow (FLOW_CONT) or fade it (FLOW_REV); +$10 / +$15 / +$20 before −$10, 1 trading day,
  B2's fills, costs and one-position rule.
- **Baseline:** random entries matched to each rule's long / short mix.

| Rule | n | Success | Random, same mix | z | Break-even | Net R | t |
|---|---|---|---|---|---|---|---|
| Follow the flow, +$10 | 264 | 52.7% | 49.8% | +0.92 | 54.3% | −0.034 | −0.56 |
| Follow the flow, +$15 | 215 | 41.9% | 39.7% | +0.66 | 43.4% | −0.041 | −0.49 |
| Follow the flow, +$20 | 199 | 32.2% | 32.9% | −0.22 | 36.2% | −0.123 | −1.24 |
| Fade the flow, +$10 | 264 | 47.3% | 49.8% | −0.80 | 54.3% | −0.137 | −2.22 |
| Fade the flow, +$15 | 224 | 37.5% | 40.1% | −0.78 | 43.4% | −0.148 | −1.82 |
| Fade the flow, +$20 | 198 | 33.8% | 33.0% | +0.26 | 36.2% | −0.070 | −0.69 |

**Results:**
- No trial differs from random by 2 standard errors, and Benjamini-Hochberg passes **0 of 6**.
- Following the flow leans the right way at +$10 and +$15 (+2 to +3 points), as the literature would predict.
- It is not significant, and every rule loses money after costs.
- Random rates in this window are lopsided (long 44%, short 56% at +$10) because gold fell. The table uses
  direction-matched baselines for that reason.
- **Limits:** a proxy, not true order flow, on 7.5 weeks of data. It is logged as exploratory (`live-window-2026`)
  and cannot be registered.

## 5. The real study: B5 on CME data (approved 2026-11-01; declared, not yet run)

**Status.**
- The operator approved it on 2026-11-01 ("approve B5 order flow study").
- It is declared in `quantum/research/b5_orderflow.py`, committed before any order-flow data was obtained. That file
  is the binding specification; the design notes below are the plan it came from.
- It runs on GitHub Actions (`.github/workflows/research-orderflow.yml`):
  - mode **quote** asks Databento for the price and downloads nothing;
  - mode **run** is the study; it downloads nothing if the quote is above the budget (default $100).
- Only aggregate results are published, to the `research-orderflow` branch. Raw trades and per-bar features are never
  stored, except one exception: a repeat-after-failure copy of the 15-minute sums, AES-encrypted with the secret in
  the repository's private Actions cache.

**Deviations from the design below, stated before any data.**

| Design | Declared | Why |
|---|---|---|
| `trades` + `mbp-1` (`mbp-10` if affordable) | `tbbo`: every trade with its aggressor side and the book just before it | A fraction of `mbp-1`'s size. Cont's OFI is therefore **trade-sampled** (between consecutive pre-trade book states). Multi-level OFI is not run |
| 5- or 15-minute decisions; labels on GC paths | 15-minute decisions; labels on **spot** XAU/USD paths (B2's horizon, fills, costs) | The operator trades spot. Comparable with B1–B4. No futures-roll gaps in the paths |
| Front month, roll days skipped | `GC.v.0` (most-traded contract); the roll day and the day after are blanked | Same intent |
| Windows of 1, 5, 15 and 60 minutes | Imbalance over 1, 5, 15 and 60 minutes; OFI over 15 and 60; queue imbalance; trade-count z-score; spread | As designed, less multi-level OFI |
| Logistic against gradient-boosted trees, calibrated | Both; 6-block purged walk-forward; out-of-fold AUC, Brier, log loss, ECE, MCE, calibration slope / intercept. No recalibration map: a map belongs to validation (`09` §5) | — |
| Q2: slippage against the next minutes' mid | The next 15 / 60 minutes' spot move by imbalance decile, against the modelled cost | The operator's fills are on spot, which has no exchange mid; descriptive only |

**Trials and the verdict.**
- 30 rules: 5 features × follow / fade × +$10 / +$15 / +$20, firing at the trailing 90th percentile.
- 6 model trials: each model trades its top decile, one position at a time.
- All 36 face B2's five-part rule. A model also needs an out-of-fold AUC of at least 0.55.
- Q2 (execution) is reported descriptively: the next 15 / 60 minutes' move by imbalance decile.

**Checks before any data.**
- 15 tests on synthetic trades and a mocked Databento client (`tests/test_research_b5_orderflow.py`):
  - aggressor signs and OFI;
  - no look-ahead;
  - roll days;
  - the purged walk-forward;
  - the cost guard and quote-only mode (nothing downloaded);
  - the full command line, the re-run refusal, and the cache;
  - a power check: a planted edge is found, and noise gives an AUC of about 0.5.
- A real DBN `tbbo` stream, built offline with `databento_dbn` 0.70 / `databento` 0.89, gave the expected frame
  (`ts_event` column, side `B` / `A` / `N`, float prices).

### Design notes (2026-11-01, before approval)

**Data (Databento GLBX.MDP3).**
- Front-month GC.
- `trades` (with aggressor side) and `mbp-1` (top of book); `mbp-10` if the budget allows.
- Development window 2020-01-24 → 2023-01-24 only. Validation and holdout stay sealed under Amendment 13.
- Rolls handled by trading the front month only and skipping roll days.

**Features at each 5- or 15-minute decision.** All use only past data:
- aggressor-signed volume imbalance over 1, 5, 15 and 60 minutes;
- Cont's top-of-book OFI over the same windows, depth-normalised;
- multi-level OFI (with `mbp-10`);
- queue imbalance at the decision instant;
- trade intensity;
- spread.

**Labels.** TP-first for +$10 / +$15 / +$20 before −$10 (B2's barrier rules), walked on GC paths.

**Models.**
- Logistic regression (baseline) against gradient-boosted trees.
- Purged, embargoed walk-forward; calibration (Platt / isotonic); AUC, Brier, ECE.
- The top-decile success rate against the base rate.

**Two questions, declared separately:**
- **Q1 (direction):** does order flow raise the TP-first rate at your targets? Judged by B2's five-part rule plus the
  calibration criteria in `09` §5.
- **Q2 (execution):** does order flow at the moment of entry lower the cost of getting in (slippage against the
  next minutes' mid)? This is where the literature says order flow works.

**Expectation, stated now.** Q1 finds a few points at most at the one-hour horizon; Q2 is the realistic benefit.

**B5b (free alternative): OANDA order book.**
- Do clusters of pending **stop** orders beyond the price predict acceleration once crossed?
- This tests Osler's mechanism directly, with real (one broker's) order data instead of round-number guesses.
- Needs an OANDA account token, and confirmation that snapshots with history are available for XAU_USD.

## 6. What the operator needs to provide

**For B5 as declared (§5):**
1. A Databento account (new accounts get $125 of free credit).
2. Its API key as the repository secret `DATABENTO_API_KEY`:
   - GitHub → the repository → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*;
   - never in chat, code or a commit.
3. The word "merge". The workflow can only be started once it is on the default branch.
4. Then: start **research-orderflow** with mode **quote**, read the price in the run's summary, and start it again
   with mode **run** if the price is acceptable.

No change to this session's network settings is needed: GitHub's runners reach Databento.

**Original list (design stage):**

1. **CME data route:**
   - a Databento account (new accounts get $125 of free credit);
   - its API key stored as a GitHub Actions secret, never in chat or code;
   - `databento.com` added to this environment's allowed domains.
   - Before buying anything, check the GC `trades` + `mbp-1` cost for 2020-01 → 2023-01 in their estimator.
2. **and / or the OANDA route:**
   - an OANDA (practice) account token as a secret (the site's `reference.py` already supports one);
   - OANDA's API host allowed in the network settings.
3. **Approval to declare and run B5 / B5b** on development data, under the same rules as B1–B4.

## Sources

- Cont, Kukanov & Stoikov (2014) — https://arxiv.org/abs/1011.6402
- Xu, Gould & Howison (2019) — https://arxiv.org/abs/1907.06230
- Cont, Cucuringu & Zhang (2023) — https://arxiv.org/abs/2112.13213v4 ; https://ideas.repec.org/a/taf/quantf/v23y2023i10p1373-1393.html
- Kolm, Turiel & Westray (2023) — https://papers.ssrn.com/abstract=3900141 ; summary https://quantpedia.com/?p=15337
- Gould & Bonart (2016) — https://arxiv.org/pdf/1512.03492
- Order imbalance in agricultural futures — https://emeraldinsight.com/insight/content/doi/10.1108/AFR-10-2017-0099/full/html
- Databento CME (GLBX.MDP3) coverage and pricing — https://databento.com/datasets/GLBX.MDP3/futures/GC ; https://databento.com/pricing ; https://databento.com/docs/datasets/glbx-mdp3.md
- CME DataMine market depth — https://www.cmegroup.com/market-data/datamine-faq.html ; https://www.cmegroup.com/market-data/files/cme-group-market-depth-faq.pdf
- OANDA order book / position book — https://www.oanda.com/bvi-en/oanda-labs/order-book-position-book-tool/ ; client library (time parameter) https://async-v20.readthedocs.io/en/latest/api.html
- Dukascopy tick format (third-party tools) — https://github.com/keyhankamyar/TickVault ; https://pypi.org/project/tickterial
- Easley, López de Prado & O'Hara (2012), bulk volume classification (method used in §3–4)
