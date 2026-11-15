# B31: architecture impact report and study design (written before any B31 code)

The registration is `research/registrations/B31.json`.

Operator directive, 2026-11-15: *"First establish which entry strategies genuinely capture $10 before SL; then
determine whether combining them improves performance."*

**Production is unchanged:** engine, config, freeze key `5e4630924d663fc5:a6f2be58c74887ed`, B15, B9, B24 and PRs
#105–#116. B31 is research code and is never imported by production.

## 1. What already exists (reused, not duplicated)

**Layer 1 — higher-timeframe direction**
- EMA20 / 100 / 200: `features.py` `ema20`, `ema100`, `ema200`.
- VWAP: `vwap`, `wvwap`, `mvwap`.
- Higher-timeframe trend scores and gates: `htf_*`.
- BOS / CHoCH / MSS events: `engine.py:397-435`.
- Premium / discount zone score: `curr_zone`.
- Regime label: `regime_label`.
- **Used by B31:** 1h / 4h EMA20 vs EMA100; the engine's structure events; `regime_label`.

**Layer 2 — liquidity**
- PDH / PDL, PWH / PWL, CDH / CDL, PMH / PML: `engine.py:651-665`.
- Equal highs / lows `eqh` / `eql`: `engine.py:498`.
- Sweep event: `engine.py:796`, a same-bar wick through PD / PW / PM and close back.
- Session flags: `sessions.py`.
- **Used by B31:**
  - its own **correct** PD / PW levels, because the engine's PWH / PWL omit day-opening bars (IA-05, the F1 fix in #114);
  - session highs / lows built from the session flags (new);
  - the engine's EQH / EQL;
  - a sweep detector that allows up to 3 bars beyond the level and records penetration, time beyond and rejection versus acceptance (new);
  - the next opposing pool, for the room check (new).

**Layer 3 — volume**
- In production: GC=F futures volume (labelled as futures volume), relative volume flags `high_volume`, `vol_sma20`, a CVD proxy, and a volume profile (VPOC / VAH / VAL).
- **Not testable in B31:** the 2020–25 research history has **no volume**.

**Layer 4 — volatility**
- ATR14, Bollinger basis, ATR percentile.
- The engine's displacement rule `engine.py:438-452` needs volume, so it never fires on the research data.
- **Used by B31:** ATR14; the engine's FVG rule (gap > 0.3 × ATR) as displacement; ATR percentile in the score.

**Layer 5 — session and news**
- Session flags with DST: `sessions.py`.
- News calendar: `news_calendar.py`. Research dates for CPI / NFP / FOMC run 2020-02 → 2023-01 only (`b8_news.py`).
- **Used by B31:** sessions. News on development only; PCE / PPI / claims / Fed speeches are not available.

**Layer 6 — cross-market**
- Live: DXY, US10Y, EURUSD, SI, S&P, GC (`features.py` `macro_*`, `corr*`, `gc_*`).
- **Not testable in B31:** no intraday history in the research data.

**Strategy modules and risk**
- None of A–E exists as a separate module.
- Their components exist as engine detectors and in past research code (B2 / B3 SMC setups, B16 / B21 sweeps and breakouts, B4 session opens, B1 mean reversion).
- **Used by B31:** five new, separately reported modules built from the detectors above.
- Risk: N1 (#113) sizes the phone plan to $650 including cost; C1 (#116) adds the lifecycle and checks.
- **Used by B31:** risk-normalised sizing from the structural stop (reported).

## 2. Prior evidence (disclosed before running)

Every component of A–E has been tested before, and none showed an out-of-sample edge (`research/STRATEGY_CATALOGUE.md`).

| Module | Closest earlier tests | Result |
|---|---|---|
| A sweep reversal | B2 (liquidity sweep, CHoCH, FVG retest), B16 SWEEP 46.6% of 5,918 vs 46.2% random, B9 GRAB 49.4% of 913 (2020–22), B21 | REJECT / FAIL; B9 still running live |
| B continuation after a grab | B3 (trend + SMC sequences, 210 trials), B17 (all confirmations, 51.6% of 184, p 0.07) | REJECT / FAIL |
| C breakout and retest | B16 BREAKOUT 46.1% of 6,729, B18 4h breakout 45.8%, B10 BREAK in trend 52.4% of 540, B25 retest (misses winners) | FAIL |
| D VWAP mean reversion | B1 mean reversion and Bollinger (0 of 100 net-positive) | REJECT |
| E session expansion | B1 session breakouts, B4 session-open momentum (validation 41.5% vs 40.3%), B13 intraday momentum | REJECT / FAIL |

**What B31 adds:**
- the full sequence, with an entry on a retracement rather than at the trigger close;
- stops at the structural invalidation;
- the room-to-opposing-liquidity check;
- session pools;
- a matched random control for each trade.

**What B31 cannot claim:**
- **Not a first look.** No historical period is untouched: the 2023–25 data has been read by earlier studies. A module that passes here still needs a registered **forward shadow test** before it may reach the phone.

## 3. The arithmetic of a +$10 first target

With TP1 = +$10 and the operator's eligibility rule (net reward / net risk ≥ 1.0 after costs of about $0.8–0.97 / oz):

    (10 − c) / (D + c) ≥ 1   ⇒   D ≤ 10 − 2c ≈ $8.1–8.4

Together with B19's $5 minimum stop, only setups whose structural stop is **$5–8.4** from the entry can qualify.

Break-even for such a trade: p* = (D + c) / (10 + D). At D = $6.5 and c = $0.8, p* = 44%.

A random entry with the same stop reaches +$10 first about D / (10 + D) = 39% of the time. A module therefore needs about **5 points over its matched random control**. The registered test measures exactly that.

**Sizing.** Costs grow with the lot, so the operator's (650 − C) / (D × V) is solved as:

    lots = 650 / (100 D + 100 c)

At D = $6.5, c = $0.97 this gives 0.87 lot. The loss at the stop, including cost, is then $650. A $10 move then earns 0.87 × 100 × (10 − 0.97) ≈ $786; it is not $650.

## 4. Design (full rules in the registration)

**Execution**
- Execution and outcomes run on 15m bars.
- Trend comes from 1h and 4h EMA20 vs EMA100 on completed bars.
- Every condition is read at a bar's close from data up to that close.
- A prefix-invariance test checks that a setup never changes when later bars are added.

**Modules**

| Module | Rule |
|---|---|
| A sweep reversal | Rejected sweep → MSS / CHoCH → FVG (or order block) retracement limit; HTF **not** aligned |
| B continuation after a grab | The same sequence with the HTF aligned (A and B are disjoint) |
| C breakout and retest | Accepted break with an FVG leg → limit at the level |
| D VWAP mean reversion | Ranging regime, 2-sd VWAP deviation, rejection close; the VWAP must lie beyond TP1 |
| E session expansion | The day's first London / New York interaction with the Asian range, as A / B or C |

**Checks on every trade**
- Stop of at least $5.
- Net R:R on TP1 of at least 1.0.
- Cost no more than 15% of the stop.
- No opposing pool inside TP1.
- One position at a time per module, and the REPEAT rule.

**Outcomes and arms**
- **Primary outcome:** TP1 +$10 or the stop, after model costs. TP2 +$15 and TP3 +$20 are reported as rates.
- **Same-bar touches:** AMBIGUOUS, scored as the stop.
- **Arms compared:** the production engine, the F1–F4 engine, a matched random control, COMBINED, and COMBINED with quality score ≥ 75.

**Quality score and probabilities**
- The operator's 100-point score has its weights as declared. Its volume, news and cross-market parts are held constant because those data are not available.
- It is tested for discrimination (AUC) and turned into TP1 / TP2 / TP3 probabilities only through isotonic calibration fitted on development. Calibration is then checked out of sample with Brier scores and reliability tables.

**Decision**
- Validation + holdout pooled, Holm over 7 hypotheses, matched random as the control, the same direction on development, and at least 30 trades.
- Otherwise the verdict is INSUFFICIENT or NOT SUPPORTED.

## 5. What is not done

- No parameter is searched or tuned.
- No rule changes after results.
- No module reaches the phone from B31 alone.
- Volume, cross-market and post-2023 news layers, 5m entry refinement and the broker spread are **not testable** with the research data. Each is listed with the data it would need (registration, `not_testable_with_this_data`).
