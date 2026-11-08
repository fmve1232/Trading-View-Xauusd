# B26 Phase A: the baseline for +$15 / −$15 (2026-11-08)

**Registration:** `research/registrations/B26.json`, committed `4a3978666` before any code.
**Code:** `quantum/research/b26.py` and `tests/test_research_b26.py` (12 tests), committed `1548e43c8` before any result was read.
**Results:** `research/results/b26/b26_summary.json` and three trade-level files, `b26_trades_P1/P2/P3.csv.gz`.
**Spot check:** `research/tools/b26_spotcheck.py`.
**Branch:** `claude/research-sym15` (research only; nothing deployed; production, web.8, the frozen Pine files and PR #90 / #91 untouched).

## What this measures

Your exact trade, with **no rule at all**: XAUUSD, +$15 take-profit against a −$15 stop from the actual fill, BUY and SELL measured separately.

- **Entries:**
  - An entry is taken at every eligible bar.
  - The decision is made at the bar's close and filled at the next bar's open: a BUY at the ask, a SELL at the bid.
  - TP and SL trigger on the side you would exit on.
- **Costs** come in four registered scenarios (below).

This is the number every later model has to beat. It is not a strategy, and nothing was selected from it.

| Population | Bars | Window | Entries per direction | Independent trades per direction |
|---|---|---|---|---|
| **P1** development | 15m | 2020-04-01 → 2023-01-24 | 64,564 | ~3,960–4,010 |
| **P2** 2026 | 15m | 2026-03-01 → 2026-11-02 | 15,890 | ~2,540–2,580 |
| **P3** live store | **5m** | 2026-09-10 → 2026-11-06 | 11,255 | ~420–440 |

**How to read the population figures:**
- **Units.** P1 distances and costs are scaled to a $4,000 gold price (k = price / 4000), as in every earlier study. P2 and P3 are literal dollars.
- **Sealed data.** Validation (2023-01 → 2024-07) and the holdout (2024-07 → 2026-01) were **not read**. They stay sealed for Phase F.
- **"Independent trades"** is the non-overlapping series: the next entry is taken only after the previous trade has exited. Entries every bar overlap, so their intervals resample whole trading days.

## The answer

1. **Without information, the bracket is a coin flip, and costs then make it a loser.** On 2020–22 data, among trades that reached a level:
   - with no cost: **49.7% (BUY) / 50.2% (SELL)**;
   - after the engine's cost model: **48.0% / 48.0%**, against the **48.3%** the arithmetic predicts for these costs;
   - after your $0.26: **48.8% / 49.3%**, against **49.1%** predicted.

   The labeller reproduces the theory, and the market behaves like a random walk at this scale.
2. **Break-even needs about 50.6%.** That is +$14.93 against −$15.27 per oz in the engine cost scenario, or 50.0% at your $0.26 taken as spread. **The no-information baseline sits 2.2–2.9 points below break-even** with the engine costs (2.2 in session, 2.9 off session), and **0.9 points** below with $0.26.
3. **Expectancy, independent trades (engine costs):**

   | Period | BUY per oz | SELL per oz | Per 0.50 lot (assumed 100 oz) |
   |---|---|---|---|
   | 2020–22 | **−$0.72** (95% interval −1.18 to −0.26) | **−$0.81** (−1.27 to −0.35) | −$36 / −$40 per trade |
   | 2026 | −$1.37 | −$0.38 | — |
   | Sep–Nov 2026 (5m) | −$1.59 | −$0.14 | — |
4. **2026 favours SELL only because gold fell.** Gold dropped 31% from its January high (5,595.46 → 3,871.19):
   - SELL won 51.2% vs BUY 47.7% (no cost, among trades that reached a level);
   - on 5m bars: 52.2% vs 46.6%.

   That is drift in one period, not a repeatable edge. In 2020–22 the two directions were equal.
5. **90% is about 40 points above the baseline.** No session, weekday, volatility, trend or news group comes close (see the regime tables below).

## The baseline in full: independent trades, among trades that reached a level

(TP-first among TP + SL + same-bar outcomes; Wilson 95% interval.)

| Scenario | P1 BUY | P1 SELL | P2 BUY | P2 SELL | P3 BUY (5m) | P3 SELL (5m) |
|---|---|---|---|---|---|---|
| **GROSS** (no cost) | 49.7% (48.1–51.2) | 50.2% (48.6–51.7) | 47.7% (45.8–49.7) | 51.2% (49.2–53.1) | 46.6% (41.9–51.3) | 52.2% (47.5–56.9) |
| **OP** ($0.26 as spread) | 48.8% (47.2–50.4) | 49.3% (47.7–50.9) | 47.1% | 50.3% | 45.9% | 51.3% |
| **ENG** (engine model, primary) | 48.0% (46.4–49.5) | 48.0% (46.4–49.6) | 46.1% (44.1–48.0) | 49.3% (47.4–51.3) | 45.3% (40.7–50.1) | 50.0% (45.3–54.7) |
| **ADV** (adverse) | 46.2% | 46.5% | 44.4% | 47.5% | 43.3% | 48.1% |
| Decided trades (ENG) | 3,808 | 3,819 | 2,512 | 2,535 | 430 | 424 |

**TP-first among all trades.** Here "not TP" also includes trades closed by the weekend, a holiday or the 2-day limit. The rates are lower: P1 ENG 46.1% / 46.2%; P2 45.6% / 48.8%; P3 44.5% / 49.1%.

## Three scorecards (independent trades, ENG)

### A. Prediction

| | P1 BUY | P1 SELL | P2 BUY | P2 SELL | P3 BUY | P3 SELL |
|---|---|---|---|---|---|---|
| Direction right after 1 hour | 51.7% | 48.3% | 50.0% | 50.2% | 53.9% | 47.2% |
| Direction right after 4 hours | 53.0% | 48.0% | 47.8% | 51.8% | 46.3% | 55.0% |
| Brier score of the constant forecast (a model must beat this) | 0.248 | 0.249 | 0.248 | 0.250 | 0.247 | 0.250 |

Direction is a coin flip plus the period's drift. **A correct direction is not a win:** in P1, BUY was right at 4 hours 53.0% of the time, yet won only 48.0% of decided trades after costs.

### B. Execution

| | P1 (15m) | P2 (15m) | P3 (5m) |
|---|---|---|---|
| Median minutes to TP or SL | 135 | 60 | 80–85 |
| 90th percentile | 690 | 240–255 | 330–335 |
| Same-bar TP and SL (counted as the stop) | 0.2% | 1.1% | 0.9–1.1% |
| Closed by the weekend / a holiday | 3.8–4.0% | 1.1% | 1.8–1.9% |
| Gap fills (the price jumped past a level) | 58 of 7,933 | 19 of 5,102 | 1 of 870 |
| Heat taken by winners (MAE): mean / 90th percentile | $6.0 / $12.3 | $5.8 / $12.5 | $6.1 / $12.6 |
| Best price seen by losers (MFE): mean | $5.4 | $5.3 | $5.7–6.2 |
| Fill vs the decision close (spread/2 + slippage) | +$0.37 | +$0.39 | +$0.37 |

**What the excursions mean.**
- A typical winner first goes $6 against you.
- 1 in 10 winners comes within $3 of the stop.
- A typical loser first shows $5–6 of profit.

Any rule that moves the stop, or takes profit early, changes these rates. That has to be tested, not assumed.

### C. Profitability (money is ASSUMED: 0.50 lot = 50 oz; not approved until the broker specification is received)

| | Per oz | Per 0.50 lot |
|---|---|---|
| Target hit (ENG) | +$14.93 (+$15 − $0.07 commission) | **+$746.50** |
| Stop hit (ENG) | −$15.27 (−$15 − $0.20 stop slippage − $0.07) | **−$763.50** (more on a gap) |
| Target / stop at your $0.26 (all in the spread) | +$15.00 / −$15.00 | +$750 / −$750 |

**Why the spread is not in those amounts.** You enter at the ask and exit on the bid, and the levels are set from your actual fill. So the spread shows up as **geometry**: in market (mid) price, the target is $15 + spread + slippage away and the stop is $15 − spread − slippage away. With the engine model's $0.30 + $0.20, that is $15.50 against $14.50, which is why a coin wins 48.3%, not 50%.

| Independent trades, ENG | P1 BUY | P1 SELL | P2 BUY | P2 SELL | P3 BUY | P3 SELL |
|---|---|---|---|---|---|---|
| Expectancy per oz | −$0.72 | −$0.81 | −$1.37 | −$0.38 | −$1.59 | −$0.14 |
| Profit factor | 0.91 | 0.90 | 0.83 | 0.95 | 0.81 | 0.98 |
| Longest losing run | 11 | 11 | 10 | 13 | 9 | 12 |
| Maximum drawdown, in stops | 236 | 215 | 234 | 106 | 52 | 18 |
| Trades per trading day | 5.5 | 5.5 | 14.5 | 14.7 | 10.4 | 10.3 |

**Two consequences for a prop account:**
- **Losing runs.** Even a fair coin produces runs of 10–13 straight losses in a few thousand trades. 11 stops at 0.50 lot is about **$8,400**.
- **Drawdown.** The drawdown rows are what "always trading" a coin with costs does over months.

## By session, weekday, volatility, trend and news

These figures cover every entry, with day-resampled intervals, and are descriptive only. Any group that looks different becomes its own registered hypothesis, tested on validation before anything is concluded.

- **2020–22 (P1).** No group moves outside its interval in a consistent direction:
  - **Sessions.** All sit within 39–48% (ENG). The lowest are NY and Friday, in both directions alike. That points to the weekend and holiday exits, not direction.
  - **Volatility terciles.** 43.7–46.8%.
  - **Trend.** "With the 1h / 4h / 1D trend" vs against vs mixed: BUY 44.4% / 43.5% / 46.2%; SELL 47.5% / 45.3% / 43.5%. **Trading with the trend did not help.**
  - **News windows (CPI, NFP, FOMC).** 956 entries. BUY 50.7% (45–57), SELL 40.7% (35–47): a small sample of the 2020–22 reactions. B8 already found no out-of-sample news edge.
- **2026 (P2, P3).** SELL beats BUY in almost every group, because the year was a downtrend:
  - **Trend.** Alignment did not help here either: SELL with the trend 48.2% vs SELL in a mixed trend 52.1% (P2).
  - **Single days.** The largest group gap (P3 SELL on Mondays, 62.8% of entries) is a handful of trading days in a falling market.
- **News labels in 2026.** I hold no dated release list for 2023-02 → 2026-10-27, so those trades are labelled NOT DATED, never "no news".

## Checks

| Check | Result |
|---|---|
| Unit tests (`tests/test_research_b26.py`) | **12 passed**. Covered: fills, spread shift, same-bar, gaps, closure, timeout, eligibility, causal context, mirror, sequence, scaling, seeded intervals. |
| Full suite (`python -m pytest -q tests`) | **503 passed** |
| Lint (`ruff check`) | clean |
| Mirror check (on mid prices a BUY wins exactly when the SELL from the same bar loses) | **100%** of the clean pairs in each population (P1 60,628; P2 15,337; P3 10,753) |
| Independent re-computation of 60 sampled trades from the bars, 20 per population (`research/tools/b26_spotcheck.py`, a second code path) | **60 of 60 match** (outcome, exit price, net) |
| Resolution: the same 3,718 decisions (P3 window) resolved on 15m vs 5m bars | outcome differs on **0.08–0.13%**; the TP rate moves by less than 0.1 point. 15m history is adequate for this bracket. |
| Reproducibility | A second run gives byte-identical CSVs and summary |

## What this means for the 90% target

- **The gap.** The honest starting point is about **48–50%** among decided trades, and break-even is **50.6%** (engine cost) or **50.0%** ($0.26). 90% is about 40 points above.
- **The required drift.** For a symmetric ±$15 bracket, 90% needs a known drift in your favour of about **$4.9 an hour** (at 2020–22 volatility) to **$11.7 an hour** (last week's). No group in this baseline shows anything like it.
- **What Phase C has to find.** Conditions with real information about the next $15, measured against this baseline with the same direction, session and period. A rule that only selects a period's drift (as 2026 SELL would) does not count.
- **What is not a route to a high hit rate.** The win rate can't be raised by moving the stop or the target without changing the trade. ±$15 is fixed by your instruction, so any improvement has to come from **information at the entry**.

## Unresolved data and execution dependencies

| # | Dependency | Effect until resolved |
|---|---|---|
| 1 | The broker's XAUUSD specification (contract size, tick value, commission, stops level) | Every dollar amount per 0.50 lot is **ASSUMED** (100 oz, $7 per lot commission) |
| 2 | Real broker bid / ask (MetaApi with the investor password, or an MT5 tick export) | Spreads are **modelled** (0.30 in session, 0.50 off, or your 0.26). News and rollover widening are not measured. |
| 3 | MT5 M1 history | 5m bars cover only two months (P3). The longer histories are 15m, which the resolution check supports for this bracket. Fills are still modelled from mid prices. |
| 4 | A dated CPI / NFP / FOMC list for 2023-02 → 2026-10 | 2026 news labels are NOT DATED |
| 5 | The TradingView symbol on your chart | The feed difference vs Twelve Data (+$0.51 on the 4 Nov H2 bar) is not reconciled |
| 6 | Validation and holdout | Sealed until Phase F |

## Trade-level files

`research/results/b26/b26_trades_P1.csv.gz` (129,128 rows), `_P2` (31,780), `_P3` (22,510); one row per entry and direction. Column groups:

- **Identity:** `pop`, `tf`, `dir`, `nyday` (New York trading day).
- **Timing and prices:**
  - `decision_utc`, `decision_px`, `fill_utc`, `fill_mid`;
  - `k` (scale; 1 = literal);
  - `fill_px`, `tp_px`, `sl_px` (actual prices).
- **Outcome (ENG):**
  - `outcome` (TP / SL / AMBIGUOUS / TIMEOUT / CLOSURE / OPEN), `gap`;
  - `exit_utc`, `exit_px`;
  - `minutes`, measured to the close of the exit bar (at most one bar late);
  - `mfe_usd`, `mae_usd`.
- **Costs and P/L (ENG):**
  - `spread`, `slip_in`, `slip_out`, `commission`;
  - `gross_usd_oz`, `cost_usd_oz`, `net_usd_oz`;
  - `net_usd_050lot` (ASSUMED 100 oz).
- **Other scenarios:** `GROSS_` / `OP_` / `ADV_` `outcome` and `net_usd_oz`.
- **Context:**
  - `session`, `weekday`, `vol_tercile`;
  - `trend_state` (UP / DOWN / MIXED from 1h, 4h, 1D), `trend_rel` (WITH / AGAINST / MIXED);
  - `news`.
- **Prediction scorecard:** `dir_1h_correct`, `dir_4h_correct`.
- **Series:** `in_seq_<scenario>` (the independent-trade series).

In P1, the dollar columns (`mfe_usd` … `net_usd_050lot`) are 4000-equivalent; the prices are the actual 2020–22 prices.

## Reproduce

```sh
python -m quantum.research.b26 --rd <research-data> --store5 <market-data>/XAU_USD_5m \
    --store60 <market-data>/XAU_USD_60m --out research/results/b26 [--trials research/trials.jsonl]
python research/tools/b26_spotcheck.py --csv research/results/b26/b26_trades_P3.csv.gz --pop P3 \
    --rd <research-data> --store5 <market-data>/XAU_USD_5m --store60 <market-data>/XAU_USD_60m
python -m pytest -q tests/test_research_b26.py
```

Data used:
- `research-data` at `a0d74e498`;
- `market-data` at `d59b3aec9`;
- data hashes in the summary file.

48 lines were appended to `research/trials.jsonl`, all marked "baseline (no rule, no selection)".
