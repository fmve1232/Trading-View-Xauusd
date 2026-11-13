# Stage-2 evidence verification of the 13 Nov master audit

Operator instruction of 13 Nov 2026: reproduce every headline statistic from the raw records; mark anything that cannot
be reproduced UNVERIFIED. **Read-only**: no production change, merge, deploy, strategy or threshold change, registration,
amendment or freeze-key change; B24 OFF; no synthetic signals; no record altered. A passing test or a reproduced number
is not evidence of profitability.

## 0. Inputs (every number below comes from these and the scripts named)

| Input | Identifier | Hash / note |
|---|---|---|
| Deployed code | `claude/audit-prompt-real-artefacts-nekqv6` @ `30a3da10d` | freeze key `5e4630924d663fc5:a6f2be58c74887ed` |
| Production store (read-only copy) | `market-data` @ `8e982370d`, 2026-11-13T13:34:10Z | `plan_validation.json` d1a2f5a0…cd8; `alerts_state.json` 988fbb17…435; `alerts_delivery.json` 3d35372a…081 |
| Forward ledger (read-only copy) | `forward-ledger` @ `35c0e4c35`, 2026-11-13T13:34:12Z | `research_forward/B15-ENGINE-FWD.json` f719c101…bd6; ledger files hashed in `v2_calib.json` |
| B15 registration | `research/registrations/B15-ENGINE-FWD.json`, committed `f5097bfc6` (2026-11-06, before any tracking code) | 70571cec…770 |
| Research XAU history | `research-data` @ `a0d74e498` (Twelve Data 15m, 2020-01-24 → 2026-11-02) | — |
| Scripts (this commit) | `audit/tools/v2_*.py` (+ stage-1 `xasset_corr.py`, `calib_audit.py`, `py_trace.py`) | outputs in `docs/deploy/verification_2026-11-13/` |

Full hashes: `verification_2026-11-13/inputs_sha256.txt`. Reproduce: §12.

## 1. Evidence table

Confidence: **VERIFIED** = reproduced from raw records by an independent script; **CORRECTED** = reproduced, but the
stage-1 statement was wrong or incomplete (the corrected statement is given); **UNVERIFIED** = could not be established.

| # | Claim (stage 1) | Source | Reproduction method | Result | Limitation | Confidence |
|---|---|---|---|---|---|---|
| 1 | B15 is 4 TP / 7 SL of 11 | B15 record; `plan_validation.json` | `v2_b15.py`: raw trades, decided order; every trade matched to `plan_validation.json` by (tf, decision time, side, entry) | 4/11 = 36.4%, Wilson 95% [15.2%, 64.6%]; 11 of 11 matched, 0 result mismatches, 0 decided plans missing | all 11 are SELLs within 4 days (10–13 Nov): not independent | VERIFIED |
| 2 | B15's first look needs 21/30, i.e. 17 of the next 19 | registration `primary_test` | thresholds recomputed: smallest k with Wilson lower bound > 51.0% | 21/30, 27/40, 33/50, 39/60, 44/70, 50/80, 56/90, 61/100 — identical to the registration | — | VERIFIED; **CORRECTED wording**: 17 of 19 is for the **first** look only; missing it does not end the test (e.g. 57 of the next 89 by the 100th result) |
| 3 | "51% break-even" | registration `rule.costs` | (13 + 0.26) / 26 | 0.5100 | it is the cost break-even AND the registered pass threshold for the Wilson lower bound | VERIFIED |
| 4 | Engine `p` NOT CALIBRATED (archive 39 unique trades, p = 0.0004) | forward ledger `holdout/archive/*.json` | `v2_calib.py`: one row per (tf, entry, side); exact Poisson-binomial test; Wilson; bootstrap by trade and by trading day | 14/39 TP1 = 35.9% [22.7%, 51.6%] vs mean p 62.6%; **exact two-sided p = 0.00061** (normal approx 0.00044); obs − p = −0.267, day-cluster bootstrap [−0.433, −0.088] | `p` is the value computed by the run that first saw the trade closed (§3); 5 engine versions pooled | **CORRECTED**: p = 0.0006 (exact), and the overconfidence is version-specific (row 5) |
| 5 | (new) by engine version | same | per freeze key | key `32babc71`: 15 trades, 27% vs 67%, exact p 0.0012; `3252a9f0`: 5, 20% vs 66%, p 0.047; **`6f3964ad`: 12, 50% vs 57%, p 0.77 (consistent with calibration)** | small groups | VERIFIED |
| 6 | Current key: 15 unique trades, INSUFFICIENT DATA | `holdout/*.json` | as row 4 | 6/15 = 40.0% [19.8%, 64.3%] vs 58.4%; exact p 0.185; day-cluster bootstrap [−0.511, +0.189] over **4 trading days** | — | VERIFIED (p was 0.14 by the normal approximation) |
| 7 | 12 cross-asset forecasts: none beats gold's own lag | store aux series; research XAU | `v2_xasset.py`: strict cut (nothing before 2026-01-01), drift / own / full walk-forward, DM with Newey–West, Holm over 24 | identical to stage 1: full vs own R² ≤ 0 in 12/12, DM t < 0 in 12/12, Holm p = 1.0 | one 10.5-month period; FINAL (revised) data | VERIFIED |
| 8 | (new) robustness of row 7 | same | 60-min delay; 5 training months | 60 min: DXY 4h and EURUSD 4h DM t +0.42 / +0.09 (p 0.34 / 0.47), the rest negative; 5 months: 12/12 negative; Holm p = 1.0 in all 36 | — | VERIFIED |
| 9 | Contemporaneous correlations (DXY −0.46 …) | same | stage-1 script, unchanged | reproduced | computed on FINAL data | VERIFIED; **sensitivity**: on 3 Oct–13 Nov, first-seen values give GC +0.941 vs final +0.986, silver +0.787 vs +0.845, DXY −0.327 vs −0.365, US10Y −0.313 vs −0.258 |
| 10 | "VIX above vs below its past median: no material difference" | store `_VIX_1d` | `v2_vix_regime.py`: threshold from 2026 closes only | DXY −0.43 (VIX high) vs −0.54 (low); US10Y −0.32 vs −0.44; EURUSD +0.44 vs +0.52 | descriptive | **CORRECTED**: the dollar and yield links are weaker when VIX is high; stage 1's median used 2016–2025 VIX (sealed years included) |
| 11 | "No statistic reads the sealed span" | scripts | code review + `v2_cut_diagnostic.py` | (a) stage-1 hourly study used the 31 Dec 2025 close as the base of each series' first return and a 2016–2025 VIX median; (b) the frozen engine's 2026 signals depend on pre-2026 **XAU daily** history (6 of 77 15m, 2 of 43 30m, 16 of 91 1h signals change when it is deleted; differing bars 31 Mar–28 Sep); deleting pre-2026 cross-asset data or GC/VIX daily changes **nothing** | (b) is the engine's own daily lookback, as in production; no outcome in the sealed span was evaluated | **CORRECTED** (a) removed in `v2_xasset.py` with identical results; (b) disclosed |
| 12 | Ablation: 21 of 77 15m signals change; needs feeds 2 TP / 10 SL; suppressed 2 / 7 | store copy | `v2_ablation.py` signal by signal (`v2_ablation_signals.csv`), `v2_ablation_ideas.py` | signal counts reproduced (77 → 74; 12 removed, 9 added). As **distinct ideas** (REPEAT rule): needs feeds 5 ideas (2 TP / 3 SL), suppressed 7 (2 / 5), unchanged baseline 23 (11 / 11 / 1 both) | outcomes are hypothetical (±$13 on FINAL bars); **no changed signal has a recorded plan outcome** (4 were recorded as REPEAT, the rest never sent) | **CORRECTED**: the signal-level tally overcounted clustered signals; no evidence either way |
| 13 | (new) offline engine = production | store records | baseline signals vs production's recorded signals, 2 Nov 10:00 → 13 Nov | 15m 20/20, 30m 11/11, 1h 2/2, 4h 7/7 matched; 0 offline-only, 0 production-only | only 11 days of production records exist | VERIFIED |
| 14 | 870 XAU 5m bars revised after the read | revision log | `v2_pit.py` | 870 revisions on 867 bars (4 Oct → 13 Nov); median 15.3 min after the bar's close (the next run); \|change\| median $0.85, 43% > $1, max $7.65 | log exists only since 3 Oct | VERIFIED |
| 15 | Daily closes Jan–Mar 2026 rewritten, up to 177 bp | revision log; manifests | `v2_pit.py`; manifests' commit field | one run (2026-10-16 16:04) rewrote **652** daily bars from **2022-08-15 to 2026-10-15** (median 4.4 bp, max 177 bp); same deployed commit `947b93804` before and after | cause | **CORRECTED** (scope); cause **UNVERIFIED** (code change excluded; vendor re-basing inferred from changed rounding) |
| 16 | Revisions recoverable? | revision log; branch history | `v2_pit.py`; `git rev-list`; Actions artifacts | see §5: XAU price revisions since 3 Oct 100% recoverable; 11.14 M of 16.80 M aux revisions recorded as counts only (old values lost; GC 5m 97% lost); no volume ever; `market-data` keeps **1** commit; site payloads kept **24 h** | — | VERIFIED |
| 17 | 96 decision / 14 display-only / 4 never-read features | `py_trace.py`; engine | `v2_features.py`: perturb each of 192 keys, re-run the engine (15m, 1h) | 14 display-only and 4 never-read: no effect (confirmed). Of 192 keys, **40 (15m) / 46 (1h) change signals**; 29 / 26 change only state or display; 117 / 114 none | perturbation shows sensitivity, not use under DEFAULT (e.g. `cot_regime` is constant 0 but its perturbation changes 1h signals); keys feeding other features are tested through those features | **CORRECTED**: "96 decision" = read by decision code; 40–46 demonstrably drive signals |
| 18 | Price fallback never used | ledgers | price_source on every row | 1,837 / 1,837 `twelvedata:XAU/USD` | only recorded trades | VERIFIED |
| 19 | (new) a phone alert was lost | `alerts_delivery.json` | every delivery record | 15 records since 2026-11-11 22:29; **1 failed: 13 Nov 07:19 15m SELL 3897.97 (plan #12), ConnectionError, no retry**; the phone then received 5 REPEATs of #12 and its TP1 follow-up | log only since 11 Nov | VERIFIED |
| 20 | Shown `p` = `p` at entry | `holdout.update_ledger` | code reading | a trade is written once, when first seen CLOSED; `p` is recomputed for the entry bar by that run; the value displayed at entry was never stored | — | **CORRECTED**; displayed-at-entry `p` UNVERIFIED (unrecoverable) |

## 2. B15 (requirement 2)

Registration (verbatim): *"proven: at a look, the Wilson 95% lower bound of the TP1-first rate is above 51.0% (needs
21/30, 27/40, 33/50, 39/60, 44/70, 50/80, 56/90, 61/100)"*; looks only at 30, 40 … 100 decided results; not proven by 100
or by 2027-06-30. Recomputed: 20/30 gives a lower bound of 0.4878, 21/30 gives 0.5212, so 21 is the minimum. With 4 of
11 decided now, the TP1 results still needed: 17 of the next 19 (look 30), 23 of 29 (40), 29 of 39 (50), 35 of 49 (60),
40 of 59 (70), 46 of 69 (80), 52 of 79 (90), 57 of 89 (100). The registration states its own error rates (5.5% false
PROVEN with no edge). The 11 trades are all SELLs inside four days, so the effective sample is smaller than 11.

## 3. Calibration (requirement 3)

**What `p` is.** `quantum/holdout.py` `update_ledger` appends a trade "once, the first time it is seen closed". The
row's `p` is `pos["p"]` from `backtest.py`, i.e. the engine's probability for the **entry bar**, computed by the run that
recorded the trade (minutes to days after entry). The engine has no look-ahead (`tests/test_no_lookahead.py`), so the
outcome cannot enter `p`; revisions of earlier bars and that run's data window can. The `p` the website displayed at
entry time was never stored.

**Test.** H0: trade i reaches TP1 first independently with probability p_i. Under H0 the number of TP1 trades S has a
Poisson-binomial distribution, computed exactly by dynamic programming; the two-sided p-value sums every count no more
likely than the observed one. Unit: one row per (timeframe, entry time, side) — arms that took the same entry agree on
`p` and on the outcome in 100% of cases (0 disagreements), so duplicates are dropped, not averaged away. Dependence:
trades cluster in days (archive 39 trades on 14 days, up to 8 a day; current 15 on 4 days) and 13–14 same-side pairs on
different timeframes fall within 4 hours of each other; the day-cluster bootstrap relaxes independence within a day.

| Scope | Unique trades (rows) | TP1 | Mean p | Exact p | Normal p | obs − p, day-cluster 95% | Brier vs base rate | AUC |
|---|---|---|---|---|---|---|---|---|
| Current key | 15 (38) | 6 = 40.0% [19.8, 64.3] | 0.584 | 0.185 | 0.143 | −0.184 [−0.511, +0.189] | 0.263 vs 0.240 | 0.65 |
| Archive (5 keys) | 39 (76) | 14 = 35.9% [22.7, 51.6] | 0.626 | **0.00061** | 0.00044 | −0.267 [−0.433, −0.088] | 0.340 vs 0.230 | 0.30 |

**Verdict.** NOT CALIBRATED (overconfident) on the archived forward record, robust to day clustering; concentrated in
two engine versions (`32babc71`, `3252a9f0`); one version (`6f3964ad`, 12 trades) is consistent with calibration; the
current version is INSUFFICIENT DATA. A small p-value says the shown numbers did not match outcomes in that sample; it
says nothing about future performance. Display rule supported by this evidence: **NOT CALIBRATED — RESEARCH SCORE ONLY**.

## 4. Cross-asset forecasts (requirement 4)

Exact construction (`v2_xasset.py`, `xasset_corr.py`):
- Feeds: Yahoo hourly DXY (DX-Y.NYB, :00), US10Y (^TNX, :20), S&P (^GSPC, :30), EURUSD (:00), SI=F (:00), GC=F (:00).
  A bar is used only if its neighbours are exactly 1 h away (a full hour). Its return ln(C_k/C_{k−1}) spans
  [t_k, t_k+1h]. **Nothing before 2026-01-01** (no base bar, no threshold).
- Gold: Twelve Data XAU/USD 15m closes (research-data to 2 Nov, the production store after); price at T = close of the
  bar ending at T. For :20 bars the :15 close (5 minutes early).
- Forecast time f0 = first 15-minute mark ≥ bar close + 15 min (sensitivity: + 60 min). Target: ln(P(f0+h)/P(f0)),
  h = 1 h, 4 h. Gold's own lag: ln(P(f0)/P(f0−1h)).
- Models, refitted at each month on all earlier months (OLS): drift (intercept), own (+ own lag), full (+ feed return).
  First OOS month: April 2026 (3 training months) or June (5). OOS window: 2026-04-01 → 2026-11-13 (US feeds to
  11-12 18:20 / 19:30). OOS rows: DXY 3,689 (Apr 493, May 463, Jun 499, Jul 519, Aug 493, Sep 486, Oct 511, Nov 225),
  EURUSD 3,793, SI 3,311, GC 3,312, US10Y 785, S&P 785.
- Diebold–Mariano: d_t = e²_own − e²_full; long-run variance = Σ(d−d̄)² + 2 Σ_{l=1..L} (1 − l/(L+1)) Σ (d_t−d̄)(d_{t−l}−d̄),
  L = 1 (1 h) or 5 (4 h, overlapping targets); se = √LRV / n; one-sided p for "full better". DXY 1 h example: mean
  d = −2.71e−08, se = 1.80e−08, t = −1.51, p = 0.934 (MSE drift 8.2565e−06, own 8.2571e−06, full 8.2842e−06).
- Holm over the 24 tests (12 in-sample Newey–West slopes + 12 DM).

Result (all three settings, 36 feed × horizon × setting comparisons): no feed beats gold's own lag; Holm p = 1.0 for
all. Two 4 h comparisons at the 60-minute delay are positive and not significant (DXY t +0.42, EURUSD t +0.09).
**Data used: FINAL (revised) values**; first-seen values exist only from 3 Oct and, for GC / SI intraday, mostly not at
all (§5). Same-time correlations differ by up to 0.06 between first-seen and final on 3 Oct–13 Nov (row 9).

## 5. Point-in-time data (requirements 6, 7)

| What | Recoverable? | Evidence |
|---|---|---|
| XAU price bars as first stored, since 2026-10-03 | **yes** (every revision listed with old O/H/L/C) | 870 (5m), 42 (15m), 3 (30m), 15 (1h), 653 (1d) listed; 0 count-only |
| XAU daily history before the 16 Oct rewrite | **yes** for the 652 bars (old values listed) | run 2026-10-16T16:04:37Z |
| Cross-asset bars as first stored, since 2026-10-03 | **partly** | listed vs count-only: GC 5m 2.8% recoverable, GC 15m 13.9%, GC 30m 22.7%, SI 5m 10.5%, SI 15m 59.6%; GC / SI 60m, DXY, ^TNX, ^GSPC, EURUSD 100% |
| Any bar before 2026-10-03 as originally seen | **no** | the manifest and revision log start 2026-10-03; `market-data` is one orphan commit per run (`git rev-list` = 1) |
| Volume as seen at decision time (R18) | **no** | `manifest.py` compares price columns only |
| Bars whose diff failed in the manifest step | **no** | `manifest.py:135` `except Exception: continue` (silent) |
| The site payload as served (bars, `p`, levels shown) | **24 hours** | `github-pages` artifact of run 43513591862: created 21:50:47Z, expires 21:50:46Z next day |
| `p` as displayed at entry | **no** | §3 |
| Forming-bar states | **no** (counts only) | manifest `forming_bar_updates` |

Requirement 7 answers. Sealed data: removed from the cross-asset study (identical results); present only as the
engine's own XAU daily lookback in the ablation (row 11). COMEX futures as a substitute for spot: **no** — every engine
run asserts `twelvedata:XAU/USD`; GC appears only as a cross-asset feed and as the volume source (D-07, as in
production). Revised values: **yes, used** — every stage-1 and stage-2 analysis runs on final data except the explicit
first-seen sensitivity; no result here is a reconstruction of what the engine saw live.

## 6. Feature dependency inventory (requirement 8)

`v2_features_15m.csv`, `v2_features_1h.csv`: one row per key of the feature dict (192, including generated per-asset
keys), with the static class, the perturbation, and whether signals / other events / dashboard state changed.

| Static class (py_trace) | Keys tested | Change signals 15m / 1h | State / display only 15m / 1h | No effect 15m / 1h | Engine crashed (so it reads the key) | Not perturbable |
|---|---|---|---|---|---|---|
| decision (read by decision code; 96 minus 6 price inputs not perturbed) | 90 | 38 / 42 | 27 / 26 | 22 / 19 | 2 | 1 |
| generated per-asset keys (not classified statically) | 53 | 2 / 4 | 2 / 0 | 47 / 47 | 1 | 1 |
| display + feeds other features | 22 | 0 / 0 (their effect flows through the features they feed, tested directly) | 0 | 22 | 0 | 0 |
| display only | 14 | 0 / 0 | 0 | 14 | 0 | 0 |
| internal only | 9 | 0 / 0 (as above) | 0 | 9 | 0 | 0 |
| never read | 4 | 0 / 0 | 0 | 3 | 0 | 1 (`highest_n` = None) |
| **total** | **192** | **40 / 46** | **29 / 26** | **117 / 114** | 3 | 3 |

Signal drivers on 15m (40): ATR / ADX family, trend scores, HTF gates and alignment, macro bull / bear and their votes,
macro strength, correlation health, mean-reversion composite, pivots, previous-month low, regime flags and multipliers,
session spread and quality, VWAP, EMA200, volume SMA. Decision-class keys with no effect on 15m include the feed status
codes (`COT_STATUS`, `OI_STATUS`, `US2Y_STATUS`), the per-asset validity flags, `num_valid`, `avg_stability`, `rsi`,
`pr_raw_vol`. Limitation: one sample per timeframe; a key with no effect here may matter in other conditions.

## 7. Probability labels (requirement 9)

| Where | Text | Basis | Assessment |
|---|---|---|---|
| Phone: plan line (two targets, production) | "odds with no edge: SL 50% · TP1 then entry 18% · TP2 32% (no signal beats these)" | driftless formula | correct as a benchmark |
| Phone: plan line (one target) | "TP first ~50% (measured; no signal beats it)" | formula | **wrong word** ("measured") |
| Phone: LADDER | "+$10 57% … (no signal beats these odds)" | formula | correct as a benchmark |
| Phone: RECORD line | "64% of 70 (2020-22), 61% of 44 (2023-24); live … 32% of 22" | constant string `notify.py:989` | **hard-coded, no intervals, omits that 2023-24 FAILED after Holm** |
| Phone: setup / 4h breakout / liquidity lines | "3-year record … +$15 before −$13 x% of n (random y%): verdict" | development 2020–22 constants | historical, with random baseline and verdict: acceptable; label "historical, not a forecast" would be clearer |
| Phone: registered-test status / checks | "COLLECTING: n results, k% …", "95% a–b; break-even 51%" | live records | correct |
| Daily report | "expected x%", "Your SL / TP sizes predict x%" | formula | "predict" reads as a model; it is the no-edge geometry |
| Daily report advice | "WEAK … Stop taking these signals" / "STRONG … Keep them" | per-group Wilson vs break-even over ~20 groups | **no multiple-comparison control**; directive language from one group |
| Website: engine `p` / "Long score" | "read it as a score, not a probability"; "read P as a ranking, not a probability" when Brier is worse | in-sample fit | label present; add NOT CALIBRATED with the forward numbers (P-1) |
| Website: "TP-first probability" (trade panel) | "MODEL NOT VALIDATED … measured … (95% …, n, in-sample) · random y%" | in-sample rate | label present |
| Website: confirm panel | "**Target-before-stop probability** (the chance that decides profit), measured after a $15 confirmation" | B19 development rates | **"probability" / "chance" for a historical rate**: relabel "historical rate, not a forecast" |
| Website: macro panel | "what its move implies for gold" | 2-day 15m correlation sign or textbook sign | contemporaneous only: relabel "moves with" |
| Engine (no display) | `cal_veto` `p < 0.50` | uncalibrated score | gate on a score; report only (engine) |
| Phone | "TQ 72" | trade-quality score 0–100 | not a probability; unlabelled |

## 8. Fallbacks, stale acceptance, unlogged revisions, handlers, notification paths (requirement 10)

- **Silent / unannounced substitutions:** price chain Twelve Data → Yahoo spot → COMEX futures (phone unlabelled);
  store copy when a fetch fails (site status only); EURUSD as the dollar's stand-in when DXY is missing (documented
  F-A65); plan outcomes resolved on the signal's own timeframe when 5m bars are missing (recorded per trade, `path`).
- **Stale acceptance:** every cross-asset feed valid for 5 days (`MACRO_STALE_DAYS`); GC confirmation 3 bars; COT 10 days.
- **Unlogged revisions:** volume (never); count-only aux revisions (11.14 M); `manifest.py:135` silent `continue`.
- **Broad handlers (32, `v2_handlers.csv`):** 29 record the failure in a status / report / error field; 3 do not:
  `manifest.py:135` (revisions of a file skipped), `macro_panel.py:59` (returns None), `notify.py:1762` (ntfy id → None).
- **Notification paths:** ntfy is the only configured channel in the delivery log (Telegram / Discord: no records);
  one attempt per send, **no retry**; a failure is visible only in `alerts_delivery.json` — on 13 Nov 07:19 the plan #12
  alert was lost while its repeats and TP1 follow-up were delivered. Not exercised in production: the outage notice on
  a real failure, the B15 CHECK message, news lines (none in the log). **Handset delivery: UNVERIFIED** (operator only).

## 9. Corrections to the 13 Nov audit (all made in this report; the audit file is not rewritten)

1. B15 "17 of the next 19" is for the first look only; later looks remain possible.
2. Calibration p-value 0.0004 → exact 0.0006; the overconfidence is concentrated in two archived engine versions; one
   version is consistent with calibration; `p` is recomputed at close, not stored at display.
3. VIX regime: the dollar / yield links are weaker in high-VIX hours (stage 1 said no difference, using sealed-year VIX).
4. Sealed data: stage 1's cross-asset study used one 31 Dec 2025 base price per series and a 2016–2025 VIX median
   (removed; identical predictive results); the ablation's engine reads pre-2026 XAU daily history (its normal lookback).
5. Ablation: at the idea level the comparison is 2 TP / 3 SL vs 2 / 5 — no evidence either way; no changed signal has a
   recorded production outcome.
6. Daily rewrite: 652 bars from 2022-08 to 2026-10, not only Jan–Mar 2026.
7. Features: "96 decision" means read by decision code; 40 (15m) / 46 (1h) demonstrably change signals.

## 10. Unresolved questions and risks

1. Cause of the 16 Oct daily re-basing (UNVERIFIED): needs the vendor's changelog or a Dukascopy comparison of the two
   versions (P-6, read-only).
2. Whether the engine-version difference in calibration (row 5) is real or chance (groups of 5–15 trades).
3. How the shown `p` differs from the recorded `p` (unrecoverable for the past; recordable from now with P-5).
4. Delivery reliability: 1 failure in 15 recorded sends since 11 Nov; no retry; earlier failures unknowable.
5. Revised data in every historical analysis: no backtest or replay here is "what the engine saw".
6. The cross-asset null holds for one period and simple linear leads; not a proof of no relation.
7. B15's 11 trades are one-sided and clustered; independence-based intervals are optimistic.

## 11. Prioritised remediation plan (proposals; nothing is built; each a separate draft PR after approval)

All outside `holdout.ENGINE_SOURCES` unless marked; each with tests, a mutation test, the 12 Nov real-payload replay
and a with/without comparison proving every record byte-identical; rollback = revert the merge commit.

| Rank | Id | Files | Change | Tests | Expected impact |
|---|---|---|---|---|---|
| 1 | **P-0 (new)** | `quantum/notify.py` | one retry on a connection failure; if still failed, the next delivered message says "1 earlier alert was NOT delivered: <first line>"; follow-ups / REPEATs of a plan whose opening alert failed carry the plan's levels again | fake `requests.post` raising ConnectionError; delivery-log assertions | no follow-up for a plan you never saw; failures visible on the phone |
| 2 | P-1 | `site/app.js` (+ a small JSON from the pipeline, display only) | "NOT CALIBRATED — RESEARCH SCORE ONLY" wherever the engine `p` / score appears, with §3's numbers by engine version | node tests on labels | no score read as a probability |
| 3 | P-2 | `quantum/notify.py` | RECORD line computed from records with Wilson intervals and verdicts (incl. "2023-24 FAILED after Holm"); "measured" → "no-edge formula"; "predict" → "no-edge geometry" | text tests; mutation (stale constant, missing interval) | phone figures become current and honest |
| 4 | P-3 | `quantum/notify.py` | price-source line when not Twelve Data spot ("— NO TRADE") | scenario test with a GC=F payload | no silent futures prices on the phone |
| 5 | P-2b (new) | `quantum/notify.py` | daily-report WEAK / STRONG advice: Holm (or a stated family size) across the groups; no imperative from one uncorrected group | unit tests on `advice` | no "keep / stop" from multiple-comparison noise |
| 6 | #103, #102, #101 | (built) | as reviewed | as in the PRs | wording |
| 7 | P-9 (new) | `site/app.js` | confirm panel "probability / chance" → "historical rate (development 2020–22), not a forecast"; macro panel "implies" → "moves with" | node tests | labels match their basis |
| 8 | P-4 | `quantum/notify.py` | event-risk line near NFP / CPI / FOMC, no change to signal eligibility | window tests | event exposure visible |
| 9 | P-5 | `quantum/manifest.py`, workflow | log volume revisions; no count-only rows for XAU and the engine's GC volume (cap raised or a compressed diff); keep the site payload per run (e.g. 90-day artifact or a ledger archive of the alerted bars, `p`, levels); make `manifest.py:135` record the failure | diff unit tests; replay from an archived payload | point-in-time replay of decisions becomes possible from the change onward |
| 10 | P-6 | read-only | the 16 Oct re-basing: compare both versions with Dukascopy | — | cause of the rewrite established or ruled UNVERIFIED |
| 11 | P-7, P-8 | `site/app.js` | display-only features labelled; macro panel wording | node tests | — |
| 12 | engine items | `features.py`, `engine.py` | staleness limits, event gate, calibration | — | **restart the holdout: amendment only** |

## 12. Reproduce

```
# copies of the inputs (read-only)
git archive origin/market-data | tar -x -C md          # 8e982370d used here; the branch moves every 15 min
git archive origin/forward-ledger | tar -x -C fl       # 35c0e4c35 used here
git archive origin/research-data | tar -x -C rd
python3 -I audit/tools/v2_b15.py <checkout> fl md
python3 -I audit/tools/v2_calib.py fl out
python3 -I audit/tools/v2_xasset.py rd md fl out
python3 -I audit/tools/v2_vix_regime.py rd md out/v2_vix_regime.json
python3 -I audit/tools/v2_pit.py fl out
python3 -I audit/tools/v2_handlers.py <checkout> out/v2_handlers.csv
cp -r md md_copy   # the engine scripts run on a COPY
PYTHONPATH=<deployed checkout> python3 -I audit/tools/v2_ablation.py md_copy 2026-11-13T13:34:10Z out
PYTHONPATH=<deployed checkout> python3 -I audit/tools/v2_cut_diagnostic.py md_copy 2026-11-13T13:34:10Z out/v2_cut_diagnostic.json
python3 -I audit/tools/v2_ablation_ideas.py out/v2_ablation_signals.csv out/v2_ablation_ideas.json
PYTHONPATH=<deployed checkout> python3 -I audit/tools/v2_features.py md_copy 2026-11-13T13:34:10Z out/py_trace.json out 15m 1h
```
Run offline: the engine scripts disable every network call and assert the Twelve Data price source; the store copy was
compared with the original after every run (unchanged).
