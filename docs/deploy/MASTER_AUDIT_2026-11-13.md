# Master audit, 13 Nov 2026: data lineage, cross-asset relationships, calibration and end-to-end integrity

Operator directive of 13 Nov 2026 ("Master directive — XAUUSD quantitative validation, market correlation and end-to-end
system integrity"). **Read-only:** no production change, no engine or threshold change, no research registration, no
amendment, no merge, no deploy. B15 continues unchanged; B24 stays OFF (`fwd_b24.on()` False on every branch checked).

Everything below was computed from recorded inputs with the tools named next to it; each can be re-run.

| Input | Where | As of |
|---|---|---|
| Deployed code | `claude/audit-prompt-real-artefacts-nekqv6` @ `30a3da10d` | 13 Nov |
| Production store | branch `market-data` @ `8e982370d` (read-only copy) | 13 Nov 13:34 UTC |
| Forward ledger | branch `forward-ledger` @ `35c0e4c35` (read-only copy) | 13 Nov 13:34 UTC |
| Research XAU history | branch `research-data` @ `a0d74e498` (Twelve Data 15m / 1h, 2020-01-24 → 2026-11-02) | 2 Nov |
| Tools (this commit) | `audit/tools/xasset_corr.py`, `macro_ablation.py`, `calib_audit.py`, `py_trace.py`, `store_inventory.py` | — |
| Outputs (statistics only, no vendor data) | `docs/deploy/master_audit_2026-11-13/*.json`, `store_inventory.txt` | — |

**Sealed data.** Amendment 13 seals VALIDATION (2023-01-24 → 2024-07-01) and the HOLDOUT (2024-07-01 → 2026-01-01). No
statistic below reads data from that span; the tools cut it and assert the cut. One slip is disclosed in §13.

## 0. Summary

1. **No stream has a demonstrated live edge.** B15-ENGINE-FWD (registered) is 4 TP / 7 SL of 11 = 36% [15%, 65%] against
   a 51% break-even; its first look is at 30 results and needs 21 of 30, i.e. 17 of the next 19. B9 is 4/10 = 40%
   [17%, 69%]. The frozen ledger's only interval excluding zero is the 5m H4 research arm, and it is **negative**: −0.159 R
   per trade [−0.250, −0.060] over 320 trades. Treatment arms have 1–3 forward trades per timeframe: no evidence either way.
2. **The engine's probability is not calibrated.** On the archived forward record (39 unique trades) it showed 63% on
   average while 36% reached TP1 (p = 0.0004); the higher it read, the worse trades did (AUC 0.30). Under the current
   freeze key the 15 unique trades are not yet decisive (58% shown, 40% observed, p = 0.14). The website already calls it
   "a score, not a probability"; the engine still gates signals on it (`p ≥ 0.50`, `cal_veto`).
3. **Cross-asset relationships are real, contemporaneous and not predictive.** In 2026 (after the holdout), gold's hourly
   returns move with silver (r +0.81), against the dollar (DXY −0.46, EURUSD +0.46), against the 10-year yield (−0.32) and,
   contrary to the textbook, **with** the S&P 500 (+0.49). None of the six feeds improves an out-of-sample forecast of
   gold's next 1 h or 4 h beyond gold's own last move: 12 of 12 tests, every Diebold–Mariano statistic negative, every
   Holm-adjusted p = 1.0. The apparent 52–55% hit rates come from drift (an intercept-only model scores the same).
4. **Macro reaches the signal, weakly and without demonstrated benefit.** Removing every cross-asset feed from the frozen
   engine changes 21 of 77 15m signals since 5 Aug (12 removed, 9 added). The signals that need the feeds went 2 TP / 10
   SL; those the feeds suppress went 2 TP / 7 SL; the baseline went 39 TP / 37 SL (51%, i.e. break-even). Small samples:
   no evidence that the feeds help.
5. **Point-in-time gaps.** The store keeps only the latest version of each bar. The revision log (since 3 Oct) shows that
   on 16 Oct one run rewrote **XAU daily** closes from Jan–Mar 2026 by up to 1.77% (27 Jan 5099.20 → 5189.62); XAU 5m bars
   are revised after the engine read them (870 rows in six weeks, up to 18.7 bp ≈ $7.6); Yahoo hourly history flips
   between versions on almost every run (one SI bar ±4.3%). Volume revisions are not logged at all (R16), so R18
   (decision-time volume incomplete) cannot be replayed point-in-time.
6. **Four integrity gaps that matter for manual decisions** (all latent or display, none fired on a recorded trade):
   (a) economic-event exposure is **not** a gate (`engine.py:948` hard-wires `news_blk = … and False`);
   (b) the phone's RECORD line is a **hard-coded string** whose "live 32% of 22" never updates and shows no intervals;
   (c) if Twelve Data fails, the price **silently falls back** to Yahoo spot, then **COMEX futures** (a $10–30 premium);
   the website shows a banner, the phone does not (all 1,837 recorded trades were on Twelve Data, so it has not happened);
   (d) every cross-asset feed is "valid" for **5 days** (`MACRO_STALE_DAYS`), even 15-minute ones.

Bottom line for the operator, in the directive's words: **if no registered stream passes its decision rule, there is no
valid signal. Today none does: NO VALID SIGNAL — NO TRADE.** The engine's output is research, recorded honestly.

---

## 1. Feature inventory (what exists, and whether it reaches a decision)

Static scan of the production Python (`py_trace.py`; quantum/ without quantum/research/), checked by hand where it matters.

| Layer | Count | Decision path | Notes |
|---|---|---|---|
| Engine features computed (`features.py`) | 146 keys | 96 read by the engine / arms | 14 display-only, 23 display + feed other features, 9 internal, 4 never read |
| Engine arms | treatment (phone), control, challenger, H2–H6 | treatment → phone alerts (15m only in `sixty`) | control is the only arm that requires `macro_bull` to enter |
| Phone streams (`notify.py`) | 12 send sites | 15m engine plans + follow-ups, registered checks, daily report, news | everything else website-only in `sixty` |
| Registered forward tests | B15-ENGINE-FWD, B9-GRAB-FWD, B24 (OFF) | record only | — |
| Exploratory live records | SETUP-LIVE, CONFIRM-LIVE, H-records | record only | no registered decision rule |
| Display modules | `macro_panel`, `reference`, `mt5`, `events`, `confirm_panel`, `news_calendar` | none (separate non-fatal steps; outside `ENGINE_SOURCES`) | — |

**Display-only engine features (never read by any decision)** — computed, shown on the dashboard, no effect on a signal:
VIX level (`vix`), the 2s10s curve (`curve_2s10s`, `curve_steep`; FRED DGS2 is fetched only for this), GC divergence and
"strong" volume flags (`gc_diverges`, `gc_strong_*`, `gc_fail`), COT crowding detail (`cot_crowd_*`; COT gating is OFF,
`cot_enable = False`, so `cot_regime` is constant 0), OI state text, correlation health per asset (`corr_health`,
`corr_sig`), `ret_kurt`, `reg_horizon_mult`, `reg_size_mult`, `vol_imputed`. The 10-year **real** yield (FRED DFII10) is
fetched every run and unused under DEFAULT (`tips_source = "us10y"`).
**Never read:** `cf_unsolved`, `d_c2`, `highest_n` (placeholder `None`), `ret_z_raw`.
Action: label these on the website as "context — not used in any decision" (display change, §12 P-7). Do not delete them
(operator instruction 2026-09-26).

## 2. Data-source inventory (from the code, verified against the store)

Ages and grids measured on the production store at 13 Nov 13:34 UTC (`store_inventory.txt`).

| Source | Symbol / id | Frequency | Timezone in store | Delay at read (measured) | Coverage in store | Used by | Limitations |
|---|---|---|---|---|---|---|---|
| Twelve Data | XAU/USD | 5m, 15m, 30m, 1h, 1d | UTC (`timezone=UTC`), bar open time | 4 min (last 5m bar) | 5m since 2026-09-09; 15m 08-05; 30m 07-22; 1h 03-02; 1d 2007-08 | **engine price** | No volume (spot). First bar after each shut repaired (`repair_reopen`). Closed bars revised later (§7). |
| Yahoo | GC=F (COMEX gold, front month) | 5m–60m, 1d | UTC, bar open | **14 min** (≈10 min CME delay) | 5m–30m since Jul–Aug 2026; 60m 2024-05; 1d 2016-09 | **engine volume** (spot bars carry GC volume, D-07); GC confirmation vote | Futures, not spot; delayed; decision-time volume incomplete (R18) |
| Yahoo | SI=F (COMEX silver) | 5m–60m | UTC | 14 min | 60m since 2024-05 | engine (macro vote, correlations) | Futures proxy for XAGUSD |
| Yahoo | DX-Y.NYB (ICE dollar index) | 60m | UTC, :00 grid | forming hour | since 2024-05 | engine (USD vote) | Hourly only; no volume |
| Yahoo | ^TNX (10-year yield ×10) | 60m | UTC, **:20 grid** | prior session (US hours only) | since 2024-05 | engine (yield vote) | Off the 15-minute grid; last bar of session short |
| Yahoo | ^GSPC (S&P 500) | 5m–60m | UTC, **:30 grid**, 12% short steps | prior session | 60m since 2023-10 | engine (risk vote) | Regular hours only; partial last bar |
| Yahoo | EURUSD=X | 5m–60m | UTC | 4 min | 60m since 2023-12 | engine (stand-in only when DXY is missing) | — |
| Yahoo | ^VIX | 1d | UTC date | daily | since 2016-09 | **display only** | — |
| FRED | DGS2, DFII10 | daily | observation date, shifted +1 day | ≥ 1 business day | full | display only (curve); DFII10 unused | Not reachable offline |
| CFTC | COT legacy, futures-only, 088691 | weekly (Tue as-of, Fri release) | aligned on release time | 3 days | 1986 → | display only (gating OFF) | — |
| BLS / Fed schedule | NFP, CPI, FOMC (hard-coded list) | event dates | New York | n/a | to 2027-12-10 | display (site cost multiplier, news line) | must be extended before 2027-12-10 |
| ForexFactory, myfxbook, fxstreet | calendar / news RSS | events | — | — | — | display (`events.py`) | — |
| OANDA v20 (practice), gold-api.com | XAU_USD bid/ask, mid | snapshot | UTC ns | measured per call | — | display + cross-check | — |
| MetaApi | broker MT5 feed | snapshot | — | — | — | display + validation | content not verified here |
| Finnhub WebSocket (relay Worker) | live price chip | ticks | — | — | — | display only | not verified here |
| Dukascopy | XAU ticks | weekly job | — | — | — | cross-check (`xcheck-dukascopy`) | — |

**Not in the system at all** (directive §3 items with no code path): Fed funds / rate futures and repricing, Nasdaq-100,
GBPUSD, USDJPY as an engine input (JPY appears only on the macro panel), oil in the engine (panel and B7 only), inflation
breakevens in the engine (panel and B7 only), central-bank gold purchases, ETF flows, physical supply/demand, futures open
interest beyond the weekly COT figure, geopolitical event feeds. None is claimed as wired.

## 3. Source → decision traceability (the paths that reach the phone)

```
Twelve Data XAU/USD ─ sources.twelvedata → market._fetch_merge (store merge; on failure: stored copy, status "store (live fetch failed)")
  → sources.trading_week_only, repair_reopen, drop_incomplete (only CONFIRMED bars reach the engine)
  → features.compute (146 keys) → engine.run(treatment): entry gate = trend score ≥ threshold ∧ HTF gate not opposite
    ∧ session quality ≥ 30 ∧ structure trigger; vetoes: trade quality < floor, plan EV < 0, calibration p < 0.50, risk lock
  → SIGNAL event → report.build → site/data/15m.json → notify.messages → stale-signal gate (FRESH / DELAYED / NOT ACTIONABLE)
  → plan (fixed $13 stop) → phone (sixty: 15m only) → plan_validation.json / B15 record → follow-up on TP1 / SL / entry
Yahoo GC=F volume ─ joined bar for bar onto the spot bars (D-07) → volume-gated features (high_volume, order blocks, VP)
Yahoo DXY / ^TNX / SI=F / ^GSPC / EURUSD / GC=F ─ align(): last bar opened before the chart bar's close, read at close[1]
  → per-asset trend flags (EMA10/EMA20) → macro votes (macro_bull/bear) and macro_strength
  → in the treatment arm they are NOT an entry condition; they enter trade quality's `tq_macro` term (weight 0.15, shared
    with the HTF votes via mtf_conf_score), which the TQ-floor veto reads, and also the regime composite (macro 20%), the
    liquidity-reach estimate and the EV correlation term. Their combined effect on signals is measured by the ablation (§5)
```

Silent fallbacks and hard-coded values found on these paths:

| Item | File:line | Effect | Status |
|---|---|---|---|
| Price fallback Twelve Data → Yahoo XAUUSD=X → **Yahoo GC=F futures** | `quantum/data/market.py` (`download_all`, candidates) | phone alerts would quote futures prices with no label (website shows a banner) | latent: 1,837 / 1,837 recorded trades on Twelve Data |
| Store fallback when a live fetch fails | `market._fetch_merge` | stale series used; status says so on the site; signals cannot be newer than the stored bars | by design; covered by the stale-signal gate and outage notice for XAU |
| `MACRO_STALE_DAYS = 5.0` for every cross-asset feed | `quantum/features.py:18` | a 2-day-old DXY trend counts as current for a 15m signal | latent; engine source (freeze key) |
| `news_blk = cfg.use_news_suppress and False` | `quantum/engine.py:948` | no event-exposure gate anywhere in the signal path | by design since the web build; a display line is possible (§12 P-4) |
| `SIGNAL_RECORD` hard-coded performance text | `quantum/notify.py:989` | the phone shows a fixed "live 32% of 22" forever | display (§12 P-2) |
| `cal_gate_min_p = 0.50` on an uncalibrated score | `quantum/config.py:38`, `engine.py:1341` | the veto's threshold has no probability meaning | engine (freeze key); report only |

Exception handling: 32 broad handlers in production; 31 record the reason (status note or report field); one
(`manifest.py:135`, bookkeeping) continues silently. Static hygiene: pyflakes finds 1 unused import (`arm_h4.py:19`) and
1 unused local (`arm_h2.py:89`). Uncalled functions: `contract.round_price`, `news_calendar.now_utc`, `sources._empty`;
test-only: 7 helpers in `contract.py`, `cost_profiles.py`, `confirm_panel.py`, `notify.plan_result`.

## 4. Cross-asset relationship analysis (exploratory)

`xasset_corr.py`, output `xasset.json`. **Exploratory, not registered:** nothing here may select a feature without a
registered study on unseen data.

**Method.** Hourly bars of each feed, 2026-01-01 → 2026-11-13 (after the holdout). A feed's hour is used only when it is a
full hour (neighbours exactly one hour away); gold's return is taken over the same span from Twelve Data 15-minute closes
(exact for :00 and :30 grids; ^TNX's :20 grid uses the :15 closes, 5 minutes early). 4-hour and daily figures sum matched
hours. 95% intervals: moving-block bootstrap (24-observation blocks). Predictive tests start gold's window at the first
15-minute mark ≥ 15 minutes after the feed's bar closed (covers Yahoo's ~10-minute delay), regress gold's next 1 h / 4 h
return on the feed's last-hour return (Newey–West), and run a monthly walk-forward against two baselines (drift only;
drift + gold's own last hour). Holm over all 24 predictive tests.

**Contemporaneous relationships (description, not causation, not an edge):**

| Feed | n (1 h) | Pearson 1 h [95%] | Spearman | Vol-adjusted | 4 h | Daily | Monthly range | Months with opposite sign |
|---|---|---|---|---|---|---|---|---|
| DXY | 5,107 | −0.46 [−0.50, −0.42] | −0.41 | −0.49 | −0.50 | −0.49 | −0.24 … −0.62 | 0 of 11 |
| US10Y (^TNX) | 1,090 | −0.32 [−0.45, −0.18] | −0.31 | −0.32 | −0.22 | −0.24 | +0.10 … −0.65 | **2 of 11** (Jan, Feb) |
| S&P 500 | 1,090 | **+0.49** [+0.40, +0.59] | +0.46 | +0.53 | +0.57 | +0.51 | +0.28 … +0.72 | 0 of 11 |
| EURUSD | 5,267 | +0.46 [+0.42, +0.51] | +0.40 | +0.49 | +0.49 | +0.49 | +0.27 … +0.63 | 0 of 11 |
| Silver (SI=F) | 4,580 | +0.81 [+0.79, +0.83] | +0.80 | +0.83 | +0.83 | +0.87 | +0.78 … +0.88 | 0 of 11 |
| GC=F | 4,581 | +0.98 | +0.98 | +0.98 | +0.99 | +1.00 | +0.96 … +1.00 | 0 of 11 |

- **Stability.** Every feed's monthly correlations differ more than chance allows (Cochran's Q, p < 0.01 for all six):
  the sign is stable for five, the size is not. The yield relation was **positive** in Jan–Feb 2026 and negative after.
- **Regimes.** Gold's own volatility tercile changes little. Session matters: DXY −0.35 in Asia vs −0.57 in late New York;
  EURUSD +0.40 vs +0.55. VIX above vs below its past median: no material difference.
- **Equities.** The positive S&P relation in 2026 contradicts the "risk-off gold" textbook sign. The engine counts
  `spx_bull` as a gold-**bullish** vote (sign +1), which agrees with 2026 but is a regime assumption, not a law.

**Predictive value (the question that matters):**

| Feed | Horizon | OOS rows | Slope p (Holm) | OOS R² vs zero | OOS R² vs own lag | Diebold–Mariano t (full better > 0) | Hit: drift / own / full |
|---|---|---|---|---|---|---|---|
| DXY | 1 h / 4 h | 3,689 | 0.49 / 0.23 (1.0) | −0.004 / −0.003 | −0.003 / −0.000 | −1.51 / −0.34 | 50 / 50 / 51 ; 49 / 49 / 48 |
| US10Y | 1 h / 4 h | 785 | 0.88 / 0.37 (1.0) | −0.042 / −0.027 | −0.005 / −0.002 | −0.79 / −0.97 | 53 / 51 / 50 ; 49 / 50 / 50 |
| S&P 500 | 1 h / 4 h | 785 | 0.57 / 0.49 (1.0) | −0.007 / −0.030 | −0.010 / −0.006 | −1.70 / −1.47 | 54 / 56 / 54 ; 43 / 43 / 45 |
| EURUSD | 1 h / 4 h | 3,793 | 0.37 / 0.20 (1.0) | −0.003 / −0.002 | −0.002 / −0.000 | −0.99 / −0.15 | 50 / 50 / 51 ; 49 / 48 / 49 |
| Silver | 1 h / 4 h | 3,311 | 0.86 / 0.57 (1.0) | +0.000 / −0.000 | −0.000 / −0.000 | −1.48 / −0.41 | 52 / 53 / 52 ; 54 / 53 / 52 |
| GC=F | 1 h / 4 h | 3,312 | 0.80 / 0.71 (1.0) | −0.000 / +0.000 | −0.001 / −0.000 | −1.25 / −1.24 | 52 / 53 / 52 ; 54 / 53 / 53 |

**Result: no incremental predictive value.** In all 12 feed × horizon tests the model with the feed forecasts gold *worse*
out of sample than gold's own last move (negative Diebold–Mariano t in 12 of 12). Hit rates above 50% are matched by the
drift-only model: gold's forward windows rose only 44–49% of the time in this sample, and a fitted intercept learns that.

**Daily, development partition (2020-01-24 → 2023-01-24), VIX** (the only daily cross-asset series the store holds for
that span): gold at 16:15 New York vs VIX close-to-close, 719 days. Same day r = −0.12 [−0.20, −0.05] (stable: −0.09,
−0.14, −0.14 by year; rolling 60-day median −0.18, negative 85% of the time). Next day r = −0.06, Newey–West p = 0.18:
**not predictive.** For DXY, nominal and real yields, oil, breakevens and COT on the same partition, B7 (registered,
22 trials) already found none beats break-even (`research/B7_B8_DEVELOPMENT_RESULTS.md`; Reality Check p = 0.999).

**Limitations.** One post-holdout period (10.5 months), one regime; hourly granularity (no tick-level lead-lag); Yahoo
series are revised (§7); ^TNX alignment approximate; equity and yield feeds cover US hours only; correlation tests ignore
heteroskedasticity beyond the bootstrap blocks. A null here is evidence of no simple linear lead at 1–4 h, not proof that
no nonlinear or event-conditional relation exists.

**Recommended action:** keep the feeds as *context*, state on the website that they are contemporaneous, and do **not**
add any cross-asset predictor to entries. Any future macro filter needs a registration and an unseen test period.

## 5. Macro-to-micro integration

What the engine distinguishes, and what decides:

| Layer the directive names | What the engine has | Reaches the phone signal? | Demonstrated predictive value |
|---|---|---|---|
| Long-term fundamental direction | none (no ETF flows, CB purchases, positioning beyond display COT) | no | — |
| Medium-term macro regime | macro votes (USD, yields, S&P, silver, GC confirm), macro_strength, regime composite | weakly (TQ 15% shared, regime 20%) | none found (§4, B7) |
| Intraday directional bias | HTF gate (5m/15m/1h/4h EMA alignment), bias scores | **yes: gate** (no entry against an opposite HTF gate) | the gate lags (blocked BUYs through a +$249 rally, 4 Nov); the registered override B14 FAILED (48.0% vs 46.3% random) |
| Short-term technical structure | trend score, BOS / CHoCH / displacement triggers, order blocks, FVG, VP | **yes: entry** | 15m stream 64% (2020–22, n 70) → 32% live (n 22) → B15 36% (n 11) |
| Entry conditions | session quality ≥ 30, TQ floor, EV ≥ 0, `p ≥ 0.50`, risk lock | **yes: vetoes** | `p` not calibrated (§6) |

**Ablation of the frozen engine** (`macro_ablation.py`, `ablation.json`; treatment arm, DEFAULT config, offline from the
production store on Twelve Data prices, signals from 2026-01-01; outcomes = ±$13 from the signal bar's close on later bars
of the same timeframe, descriptive):

| Timeframe (period) | Baseline signals (TP / SL) | Remove all cross-asset: removed (TP/SL) | added (TP/SL) | Largest single feed |
|---|---|---|---|---|
| 15m (5 Aug → 13 Nov) | 77 (39 / 37) | 12 (2 / 10) | 9 (2 / 7) | silver: 4 removed, 3 added |
| 30m (22 Jul →) | 43 (23 / 20) | 1 (1 / 0) | 13 (6 / 7) | DXY: 3 added |
| 1h (2 Mar →) | 91 (36 / 50, 5 both) | 14 (5 / 7, 2 both) | 22 (5 / 17) | S&P: 5 removed |
| 4h (2 Mar →) | 52 (21 / 21, 10 both) | 3 (2 / 1) | 0 | — |

Reading: the feeds change 27% of 15m and 40% of 1h signals (removed + added over baseline), so they are wired; on these samples neither the signals
they enable nor the ones they block do better than break-even. **Conflicts between timeframes** are explained on the
website (CONTEXT line, HTF gate state) but the engine resolves them by rule (gate), not by measured predictive weight:
no layer has demonstrated predictive value that would justify a weight.

## 6. Probability-calibration audit

Every probability or rate shown, its basis, and the verdict:

| Shown | Where | Basis | Sample | Verdict |
|---|---|---|---|---|
| Engine `p` (P(TP1 before SL)), shown as "Long score" | website; `cal_veto` gate | logistic fit of the bull score on the analog history, in-sample (`analog.py:345`) | forward, archived keys: 39 unique trades | **NOT CALIBRATED — overconfident.** Shown 0.63, observed 0.36 [0.23, 0.52]; expected 24.4 wins, observed 14 (z −3.52, p 0.0004); Brier 0.340 vs 0.230 for the base rate (skill −0.48); log loss 0.90; AUC 0.30 (higher p, worse outcome); the 9 trades shown ≥ 0.65 (mean 0.78) won 1 (11%) |
| same, current freeze key | — | — | 15 unique trades | INSUFFICIENT DATA (shown 0.58, observed 0.40 [0.20, 0.64], p 0.14) |
| RECORD line "64% of 70 (2020-22)" | phone, every 15m alert | development backtest of the 15m stream | 45/70 | [52.6%, 74.5%]; selected as "the only alert above 60%" among several streams (selection bias; did not pass Holm, F-01) |
| "61% of 44 (2023-24)" | same | B13's registered validation opening (approved) | 27/44 | [46.6%, 74.3%]; vs 47.6% random, p 0.033, **FAIL after Holm** (`research/B13_RESULTS.md`) — the phone line does not say it failed |
| "live Sep-Nov 2026 32% of 22" | same | **hard-coded** | 7/22 | [16.4%, 52.7%]; differs from 2020–22 (Fisher p = 0.013); never updates |
| LADDER odds (+$10 57%, +$13 50%, +$15 46%, +$20 39%) | phone | driftless formula SL / (SL + TP) | — | correct as a no-edge benchmark and labelled so; not a measurement |
| Plan line "odds with no edge" (two targets) | phone | same formula | — | correct, labelled |
| One-TP plan line "TP first ~50% (measured; …)" | phone if `PLAN_TP2_USD=0` (not production) | formula, not a measurement | — | wording inaccurate ("measured"); random baselines measured 49.1–50.3% at ±$13 agree only for the symmetric case |
| Setup "measured odds" (B16 / B17) | website | development 2020–22 rates | 5,918 / 184 | historical, labelled "not an edge" / "not proven"; no live calibration rule |
| SETUP-LIVE BREAKOUT 68% | website | live record | 32/47 | exploratory; chosen after looking at 5 kinds; overlapping setups correlated (F-09) |
| Confirm panel probabilities | website, NO TRADE verdict | B19 development rates | per trigger | historical rates, not live-calibrated; verdict NO TRADE shown |
| Macro panel "implies for gold" | website | sign of the last 2 days' 15m correlation if \|r\| ≥ 0.2, else textbook sign | ≤ 192 bars | contemporaneous only; §4 shows no predictive value; wording should say "moves with", not "implies" |

`forward_stats.py` reports "calibration NOT ASSESSABLE" because no single ledger has 10 trades with `p`; pooling ledgers
is valid only after removing duplicate entries (arms share bars: 76 rows are 39 trades). `calib_audit.py` does that.

**Actions:** show NOT CALIBRATED next to every engine `p` / score (display, P-1); compute the RECORD line from the records
with Wilson intervals instead of a constant (display, P-2); fix "measured" in the one-TP line (display, P-2). The gate
itself (`cal_gate_min_p`) is engine logic under the freeze key: report only; any change is an amendment.

## 7. Data-quality and point-in-time audit

| Issue | Evidence | n | Impact | Action |
|---|---|---|---|---|
| **XAU daily history rewritten** | revision log: run 2026-10-16 16:04 changed Jan–Mar 2026 daily closes, up to 177 bp (27 Jan 5099.20 → 5189.62; 24 Mar 4399.43 → 4474.44) | 653 rows | daily levels, previous-month high/low, prior daily close for bars in Feb–Apr; forward decisions (from 28 Sep) used post-rewrite values only for those old bars | read-only investigation: cause (vendor re-base vs code), and whether any recorded decision read a pre-rewrite value |
| XAU intraday bars revised after the read | 5m: 870 rows in 6 weeks, median 2.1 bp, max 18.7 bp ($7.6), typically ≤ 20 min after the close; 15m 42 rows; 1h 15 | — | a signal can be computed on a first print that later changes; the stale-signal gate does not see it | log, and compare decision-time vs final bars per signal (R14 protocol extension) |
| Yahoo version flips | SI=F 60m 1.17 M logged rows, p99 18.8 bp, max 434 bp (one 2025 bar alternating every run); GC 60m 1.90 M rows, max 126 bp | 16.8 M revised-bar events in 2,707 runs | cross-asset features differ run to run; R14 measured low live impact | R14 study (protocol v2 awaiting approval) |
| **Volume revisions not logged** | manifest compares `PRICE_COLS` only | — | R18 cannot be replayed point-in-time | log volume revisions (bookkeeping, P-5) |
| No store history | `market-data` is one orphan commit per run | — | a past decision's exact inputs cannot be re-read except via the price revision log | retain per-run snapshots or monthly archives (P-5) |
| Decision-time volume incomplete (R18) | GC=F arrives ~10 min late (age 14 min vs XAU 4 min at the read) | — | the volume of the bar just closed is partial at decision time | R18 study (approval pending) |
| Off-grid and short bars | ^TNX :20 grid; ^GSPC :30 grid with 12% short steps; XAU bars stamped inside the weekend shut appear in the revision log (2–18 rows per series) and are dropped by `trading_week_only` | — | alignment rule handles them (last bar opened before close, close[1]); correlation studies must not | documented in §4 |
| Research vs production XAU consistency | 8,529 overlapping 15m bars (Aug–Nov): 2 differ by > 1 cent, max $3.06 | 8,529 | none material | none |
| Stale macro feeds accepted 5 days | `MACRO_STALE_DAYS = 5.0` | — | latent | per-feed limits = an amendment; measure first |
| Price-source fallback | 1,837 / 1,837 recorded trades `twelvedata:XAU/USD` | 1,837 | latent | phone label or suppression (P-3) |

**Point-in-time replay today** is possible for prices (from the revision log, since 3 Oct) but not for volume, and not
before 3 Oct. Historical backtests and site statistics use the latest (revised, final-volume) data: they are not
representative of what the live engine saw. No registered research or holdout record was amended.

## 8. Dead-code and disconnected-variable report

From §1 and §3: 4 never-read engine keys; 14 display-only engine features; DFII10 fetched and unused; DGS2 fetched for a
display curve only; COT fetched and displayed, gating off; VIX display only; 3 uncalled functions; 7 test-only helpers;
1 unused import; 1 unused local; 1 silent broad exception handler (bookkeeping). The Pine reference's own dead-code report
(`deadcode.py`) is part of the PR checks (#99). Nothing is removed (operator instruction: do not delete features).

## 9. Statistical validation report (records kept separate)

| Category | Stream | Sample | Result | Status |
|---|---|---|---|---|
| Exploratory | cross-asset predictive tests (this audit) | 12 tests, 2026 | none beats own lag; Holm p = 1.0 | null |
| Exploratory (live) | SETUP-LIVE BREAKOUT | 32/47 | 68% [54, 80] | no decision rule; not evidence |
| Registered, development | B7 macro (22 trials), B8 news (32 trials) | 771 days | 0 pass; Reality Check p 0.999 / 0.822 | REJECTED |
| Registered, development / validation | B1–B27 (see `research/STRATEGY_CATALOGUE.md`) | — | "Nothing has passed": no candidate reached a registered pass; B14 (gate override) 48.0% of 229 vs 46.3% random, FAIL | REJECTED |
| Training / history | 15m engine stream | 70 (2020–22) / 44 (2023–24) | 64% / 61% | did not pass after Holm (F-01) |
| Forward (registered) | B15-ENGINE-FWD | 11 | 4 TP / 7 SL = 36% [15, 65]; break-even 51% | COLLECTING; first look at 30 |
| Forward (registered) | B9-GRAB-FWD | 10 | 40% [17, 69] | COLLECTING |
| Forward (frozen ledger) | 5m H4 | 320 | −0.159 R [−0.250, −0.060] | significantly negative (research arm, not alerted) |
| Forward (frozen ledger) | 15m / 30m / 1h / 4h H4 | 84 / 50 / 25 / 13 | +0.010 / +0.136 / +0.178 / −0.029 R, all intervals include 0 | no evidence |
| Forward (frozen ledger) | treatment arms (the phone's logic) | 1–3 per timeframe | — | no evidence either way |
| Production observation | live 15m stream (hard-coded) | 22 | 32% [16, 53] | below break-even |

These categories are never pooled into one success rate in this report, and must not be on the phone or the website.
Tests and mutation tests (PRs #99–#103) prove the code does what it says; they say nothing about profitability.

## 10. The five draft PRs (#99–#103), re-verified

| PR | Head | State | Evidence |
|---|---|---|---|
| #99 C — read-only PR checks | `9cc1bdef5` | draft, open | GitHub run: both jobs **passed** (tests 3 min, reference checkers 9 s) |
| #100 B — env versions in manifest | `33a1272df` | draft, open | local 678 passed, 2 skipped |
| #101 A — disclaimer | `01965249d` | draft, open | local 689 passed, 2 skipped; 12/12 mutants |
| #102 D — 15m vs website-only report | `77b0006e7` | draft, open | local 682 passed, 2 skipped; 13/13 mutants |
| #103 E — plan stop vs engine reference | `ddddb9390` | draft, open | local 682 passed, 2 skipped; 10/10 mutants |

Base unchanged (`30a3da10d`); none merged; combined merge (scratch) 719 passed, 46/46 mutants, 12 Nov replay state and
records identical, stale-signal rules 0 violations. Protected checks on all five: freeze key
`5e4630924d663fc5:a6f2be58c74887ed`, B24 OFF, MANIFEST OK, registrations identical, no protected path touched. Only #99
has GitHub CI evidence; the others' results are local.

## 11. Risks and unresolved limitations

1. No validated live edge in any stream (§9). The phone still presents plan levels; PR #101 (disclaimer) addresses the
   wording, not the absence of an edge.
2. The engine's probability is overconfident on the forward record and still gates signals (§6).
3. Point-in-time inputs cannot be reconstructed for volume, or before 3 Oct for prices (§7); backtests use revised data.
4. Latent silent substitutions: futures price fallback; 5-day macro staleness (§3).
5. No event-exposure gate (§3); the operator has to check the calendar on the website.
6. Dependencies unpinned (PR #100 records versions only); `DatetimeIndex.dayofweek` (used by `quantum/sessions.py`, an
   engine source) is deprecated in pandas 3.1.
7. Mobile delivery to the operator's Android handset is **not verified**.
8. This audit's cross-asset results cover one 10.5-month period; regimes change.

## 12. Improvement roadmap (ranked by impact on decisions and capital protection) and draft-PR proposals

None of these is started. Each needs separate approval; each is a separate PR.

| Rank | Proposal | Type | Freeze key | What it changes | Why first |
|---|---|---|---|---|---|
| 1 | Decide #101 (disclaimer), #103 (plan stop vs engine reference), #102 (report split) | display | unchanged | phone wording | already built and verified |
| 2 | **P-1** NOT CALIBRATED badge wherever the engine `p` / score appears; tooltip with §6 numbers | display | unchanged | website | stops a number that reads as a probability |
| 3 | **P-2** RECORD line computed from `plan_validation.json` / B15 with Wilson intervals; "measured" → "no-edge formula" in the one-TP line | display (notify) | unchanged | phone text | removes a hard-coded, stale performance figure |
| 4 | **P-3** Price-source guard: if the source is not Twelve Data spot, phone alerts say "PRICE SOURCE: COMEX FUTURES (not spot) — NO TRADE" | display (notify) | unchanged | phone text in a fallback only | makes a latent silent substitution visible |
| 5 | **P-4** Event-exposure line on phone alerts inside or within 60 min of an NFP / CPI / FOMC window (from `news_calendar`) | display (notify) | unchanged | phone text | directive §7 item missing from the signal path |
| 6 | Merge #99 (CI) and #100 (versions), then pin dependencies to today's versions with byte-identical outputs | ops | unchanged | workflows | real pre-merge verification; holdout integrity |
| 7 | **P-5** Point-in-time bookkeeping: log volume revisions; retain per-run store snapshots (or monthly archives) | bookkeeping | unchanged | forward-ledger branch | makes R14 / R18 and any replay reproducible |
| 8 | **P-6** Read-only investigation of the 16 Oct daily rewrite | read-only | unchanged | none | determine cause; confirm no recorded decision affected |
| 9 | R14 / R18 studies (protocols already proposed) | research (registration) | unchanged | none | quantify decision-time vs final data |
| 10 | **P-7** Label display-only engine features on the website ("context — not used in any decision") | display | unchanged | website | stops dashboard data reading as operational |
| 11 | **P-8** Macro panel wording: "moves with gold (last 2 days)" instead of "implies" | display | unchanged | website | §4 |
| 12 | Per-feed staleness limits; event gate in the engine; any calibration change | engine | **restarts the holdout** | engine | only by amendment, after an impact study |
| — | Add cross-asset predictors to entries | — | — | — | **not recommended**: no out-of-sample value (§4) |
| — | Tune thresholds on this history | — | — | — | **not allowed** |

## 13. Disclosures and corrections

- **Sealed-data slip (disclosed, discarded).** The first ablation run fell back to Yahoo GC=F prices (no Twelve Data key
  was set in the offline run) and, on 1h and 4h, reached back to 2024-05, i.e. into the sealed holdout span. Its signal
  counts and outcomes were printed once, then discarded unused; the tool now forces the Twelve Data path, asserts the
  price source, and counts signals only from 2026-01-01. No registration, threshold or record was influenced.
- **Calibration correction.** A first pass pooled 38 / 76 ledger rows; arms share entries, so the independent samples are
  15 / 39 unique trades. The verdicts above use the unique trades.
- Earlier statement in the 13 Nov handover: PR A's tests were said to cover quality mode only; they covered sixty mode
  only, and now cover both.

## 14. Not verified (and why)

The website's rendering, the live price chip, MetaApi and OANDA content (hosts unreachable from this environment); FRED,
CFTC and Yahoo live endpoints (blocked here; the store copies were used); the Android handset (operator only); any data
from the sealed VALIDATION and HOLDOUT spans (sealed by design).

## Appendix A. Draft-PR proposals (specs only; nothing is built until approved, one PR each)

Common rules for every proposal: outside `holdout.ENGINE_SOURCES` (the freeze key stays
`5e4630924d663fc5:a6f2be58c74887ed`); no threshold, gate or engine change; B15 and every record byte-identical (verified
by a with/without replay as for #101–#103); tests + mutation test + 12 Nov real-payload replay; draft PR; no merge without
approval.

| Id | Files | Change | Tests that pin it | Records | Rollback |
|---|---|---|---|---|---|
| P-1 | `site/app.js` | "NOT CALIBRATED" badge next to every engine `p` / long-short score and in the calibration card, with the forward numbers (shown vs observed, unique trades) from a small JSON the pipeline writes with `calib_audit.py`'s method (display code, outside `ENGINE_SOURCES`) | node tests on the rendered labels | none | revert |
| P-2 | `quantum/notify.py` | RECORD line computed at send time: history figures with Wilson intervals and their verdicts ("FAIL after Holm"), live figure from `plan_validation.json` 15m records and B15's own record, each labelled by category; one-TP line: "TP first ~50% (no-edge formula)" | unit tests on the text; mutation (stale constant, missing interval, pooled categories) | none (reads only) | revert |
| P-3 | `quantum/notify.py` | if `meta.price_source` is not `twelvedata:XAU/USD`, prepend "PRICE SOURCE: <source> (not the spot feed) — levels are not your broker's — NO TRADE" to trading alerts | scenario test with a GC=F payload | none | revert |
| P-4 | `quantum/notify.py` | an "EVENT RISK: <name> at <time> (in N min)" line on trading alerts within 60 minutes of an NFP / CPI / FOMC window (`news_calendar.state`) | unit + scenario tests around a dated window | none | revert |
| P-5 | `quantum/manifest.py`, workflow | log volume revisions beside price revisions; keep a compressed per-run snapshot index (or monthly archive tag) so a decision's inputs can be re-read | unit tests on the revision diff; replay test reading a snapshot | additive bookkeeping on the forward-ledger branch | revert; logs already written stay |
| P-6 | none (read-only) | investigate the 16 Oct XAU daily rewrite: compare the pre/post values with the Dukascopy cross-check and Twelve Data's history; list any recorded decision whose inputs included a rewritten bar | — | none | — |
| P-7 | `site/app.js` | mark display-only engine features "context — not used in any decision" (list in §1) | node tests | none | revert |
| P-8 | `quantum/macro_panel.py` text, `site/app.js` | "moves with gold over the last 2 days (r = …)" instead of "implies for gold"; no colour by textbook sign without a measured r | unit + node tests | none | revert |
| P-9 (amendment) | `quantum/features.py`, `engine.py` | per-feed staleness limits; an engine event gate; any calibration change | impact study first | **restarts the holdout** | — |
