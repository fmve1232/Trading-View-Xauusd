# B19: two-stage signals (trigger, then a confirmed $15 / $20 move, then a trade plan), 2026-11-07

**Request:** the operator's re-engineering brief (2026-11-07): "identifies the initial opportunity, waits for $15–$20 of
confirmed movement in the original signal direction, and then produces a disciplined, executable trade plan …
Demonstrate the actual statistical edge through independent testing."

**Registration:** `research/registrations/B19.json`, commit `2c4843f77`, committed before any code.

**Code:**
- `quantum/research/b19.py` (research only; never imported by production).
- `research/tools/b19_montecarlo.py`.

**Tests:** `tests/test_research_b19.py`, 19 tests, at least one per rule.

**Results:** `research/results/b19_*_2026-11-07.json`.

**Trials:** `research/trials.jsonl`, phase `B19`.

**Unchanged:**
- production alerts, the engine and `config.py`;
- the website freeze key `5e4630924d663fc5:a6f2be58c74887ed`;
- B9-GRAB-FWD and B15-ENGINE-FWD.

## 0. The answer

**No version shows a statistical edge that survives independent data.**

1. **2020–22 (development).**
   - On the engine's structure triggers, the $15 confirmation was positive in almost every stop / target combination:
     +$2.32 per oz at −$13 / +$20, profit factor 1.32, 125 trades.
   - The pre-registered test still **failed**: t 1.52; Holm-adjusted p 0.45.
   - The overfitting checks gave it no support:
     - walk-forward test result +0.07 R (t 0.36);
     - PBO 0.46;
     - Deflated Sharpe 0.66;
     - Reality Check p 0.10.
2. **2023–24 (validation), opened once.**
   - **The edge reversed.** The $15 confirmation lost −$3.04 per oz (49 trades).
   - The one candidate the declared screen picked (3 × ATR stop, +$20) lost −$4.40 per oz (38 trades).
   - **Nothing passed, so the 2024–25 holdout stays sealed** (the code refuses to open it).
3. **The engine's own signals are too rare for this design.**
   - There were 64 separate ideas in three years and 24 in eighteen months.
   - After confirmation only 20 and 7 trades remain: INSUFFICIENT by the registration.
4. **Correction to an earlier claim (erratum, section 5).**
   - "The engine's 15m signals won 64% of 70 (2020–22) and 61% of 44 (2023–24)" counted every repeated signal of the
     same idea.
   - Counted once per idea, as the live alerts now do, the record is:
     - 52.2% of 23 in 2020–22 (B10's own measure);
     - 45.8% of 24 in 2023–24 (B19's exit rule);
     - 47.3% of 55 in 2026 (B19's exit rule).
   - All are below the 51% break-even at ±$13.
   - **The "alerts above 60%" mode rests on that count. It has no measured basis.**
5. **Recommendation.**
   - **Do not put new money behind any B19 version.** No production change is justified by these results.
   - Size trades so a normal losing streak cannot end the account: 0.10 lot or less at a $13 stop (section 8).
## 1. Technical audit of the current engine

| Area | What it does now | Finding |
|---|---|---|
| Data | Twelve Data XAU/USD 5m / 15m / 30m / 1h / 4h every 15 minutes; research files 15m and 1h from 24 Jan 2020 | Matches the operator's MT5 within $1–3 at ten turning points, 30 Oct – 6 Nov (2026-11-06 validation). No volume for 2020–24, so the research engine runs without volume, macro or cross-asset inputs (`b10.make_market`) |
| Engine | `quantum/engine.py`: a bar-by-bar port of the Pine Master (v21 order); frozen by the website's freeze key | Entry gate (treatment arm): bull trend AND no bearish higher-timeframe gate AND a recent bar AND session quality ≥ 30 AND no news block AND no drawdown breach, then a trigger (an active bullish structure break, or a displacement candle), then the trade-quality floor (TQ ≥ 55), EV and calibration vetoes |
| Signals | A SIGNAL carries direction, the close, TQ, the engine's SL and TP1–TP3 | **Rare:** 70 on 15m and 25 on 1h in 2020–22 (B10). Live (with macro inputs): 3–6 a week |
| Alerts | Each SIGNAL gets the operator's plan: entry at the signal close, SL −$13, TP1 +$13 (half), stop to entry, TP2 +$20; REPEATs open no plan; "above 60%" mode sends only 15m | **Measured:** 15m signals 64.3% of 70 (2020–22) and 61.4% of 44 (2023–24) at +$13 before −$13. Live Sep–Nov 2026: 31.8% of 22. Week 45: 1 of 10 (8 of them one idea, before the REPEAT rule) |
| Outcomes | Every alert is scored on 5-minute prices; two-level bars counted as losses; costs charged | Recomputed independently on 2026-11-06: 10 of 10 outcomes match |
| Research record | 709 trials in `research/trials.jsonl` before B19 | No rule at a $13 stop beat random entries reliably. The geometry rule P(TP first) ≈ S / (S + T) holds within 0.5 points (B13-0) |
| Weaknesses | — | (1) Signals come late in a move (3 Nov: eight SELLs within $13 of the low after a $55 fall). (2) A $13 stop is about one hour of normal movement (median 1h candle $12–15). (3) Costs: about $0.77–0.97 per oz on the model, $0.26 measured by the operator. (4) Too few signals for strong statistics |

## 2. Proposed architecture (B19, research version)

```
Stage A  trigger                      Stage B  confirmation (15m closes)            Plan
---------------------------------     -----------------------------------------    ------------------------------------
ENG: engine SIGNAL (15m-4h)           TRIGGERED -> CONFIRMATION PENDING             entry  E1 market at the confirming close
STR: engine BOS / MSS / CHoCH           touch +15 / +20: recorded only                     E2 limit at the threshold, 8 bars
     + bias + VWAP + session          CONFIRMED_15 / _20: a CLOSE beyond            stop   $10 / $13 / 3 x ATR14 / structure
REPEAT rule (4 h, $15)                  P0 + d x 15 / 20, filters F0 or F1          target $15 / $20 / $25 / $30
record P0, time, TF, scores,          INVALIDATED: -$13 first, or an opposite       check  R:R >= 1, stop $5-$40, cost <= 15%
regime, session, ATR, RSI, EMAs         structure break (same bar: invalid)              -> EXECUTE / REJECT
                                      EXPIRED: no confirmation in 96 bars           exit   first touch; gap at the open;
                                                                                           two-level bar AMBIGUOUS = loss;
                                                                                           192-bar time stop
```

The direction is never reversed: a BUY trigger can only be confirmed by an upward close, and a move against it
invalidates it.

## 3. Formulas

- **Scale.** s = P0 / 4000. Every distance is quoted at $4,000 and multiplied by s (2020–22 gold traded near $1,800).
- **Favourable and adverse excursion on bar k.** BUY: fav_k = H_k − P0, adv_k = P0 − L_k. SELL: fav_k = P0 − L_k,
  adv_k = H_k − P0.
- **Touch milestone.** REACHED_X ⇔ fav_k ≥ X·s for some k in the window.
- **Close confirmation.** C_k ⇔ (Close_k − P0)·d ≥ X·s.
- **Invalidation.** I_k ⇔ adv_k ≥ 13·s, or an opposite-direction BOS / MSS / CHoCH at k.
- **Confirmation bar.** k* = the first k with C_k ∧ F(k) and no invalidation at any bar ≤ k*. F0: F ≡ true.
  F1: RSI14_k ≥ 55 (SELL ≤ 45) ∧ (Close_k − EMA20_k)·d > 0 ∧ ≥ 1 same-direction structure event in (trigger, k] ∧
  cost_k ≤ $0.80 ∧ (H_k − L_k) ≤ 2.5·ATR14_k ∧ |O_k − Close_{k−1}| ≤ 0.5·ATR14_k.
- **Entry.** E1: Close_{k*}. E2: fill at L = P0 + d·X·s on the first bar of k*+1 … k*+8 that trades through it.
- **Stop distance D.**
  - S10 = 10·s and S13 = 13·s.
  - SATR = 3·ATR14_{k*}.
  - SSTR: BUY = entry − (min L over trigger…k* − 0.2·ATR14); SELL mirrored.
- **Execute.** T·s / D ≥ 1 ∧ 5·s ≤ D ≤ 40·s ∧ cost ≤ 0.15·D / s.
- **Net per trade ($ per oz at $4,000).** net = (exit − entry)·d / s − cost.
- **R multiple.** R = net / (D / s).
- **Profit factor.** PF = Σ net⁺ / |Σ net⁻|.
- **Expectancy.** E = mean(net). t = E / (sd / √n).
- **Maximum drawdown.** maxDD = max over time of (running peak of Σ R − Σ R).
- **Nulls.** N1: S / (S + T). N2: the same pipeline on random triggers (every 8th 15m bar, both directions).
  - Welch test: z = (E − E_N2) / √(v / n + v_N2 / n_N2).
- **Multiple testing.** Holm over H1–H8 on one-sided t p-values. PBO by CSCV (8 groups, monthly blocks). Deflated
  Sharpe against all 288 configurations. White's Reality Check (stationary bootstrap, 1,000 draws) on monthly mean R.

## 4. Backtest: $15 versus $20 confirmation (development, 2020-04 → 2023-01)

**Settings:**
- stop −$13 and target +$20 from the entry;
- entry E1 (market at the confirming close);
- model costs, about $0.77–0.97 per oz.

"N2" is the same pipeline on random triggers. Distances are at $4,000.

### Engine signals (ENG): 64 ideas after the REPEAT rule (15m 22, 30m 18, 1h 13, 4h 11)

| Strategy | Reached +15 / +20 (touch) | Confirmed | Invalidated (price / structure) | Trades | TP first | SL first | PF | Net $ / oz | t | Max DD (R) | Avg hold | N2 net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Existing, as alerted (−13 / +13 from the signal) | 40 / 36 | — | — | 64 | 42.2% | 57.8% | 0.65 | −2.82 | −1.74 | 17.7 | 173 min | — |
| 1b Existing, the engine's own SL / TP1 | 40 / 36 | — | — | 64 | 42.2% | 53.1% | 1.00 | −0.05 | −0.01 | 15.9 | 668 min | — |
| 2 Trigger only (−13 / +20 from the signal) | 40 / 36 | — | — | 64 | 35.9% | 64.1% | 0.76 | −2.24 | −1.09 | 20.9 | 218 min | −0.91 |
| 3 $15 confirmation | 40 / 36 | 20 | 44 (37 / 7) | 20 | 50.0% | 50.0% | 1.39 | +2.67 | 0.70 | 5.3 | 181 min | −1.16 |
| 4 $20 confirmation | 40 / 36 | 19 | 45 (37 / 8) | 19 | 42.1% | 57.9% | 1.01 | +0.08 | 0.02 | 4.7 | 119 min | −1.00 |
| 5a $15 + momentum and structure | 40 / 36 | 5 | 59 (38 / 21) | 5 | 40.0% | 60.0% | 0.93 | −0.57 | −0.07 | 3.2 | 195 min | −0.81 |
| 5b $20 + momentum and structure | 40 / 36 | 5 | 59 (38 / 21) | 5 | 40.0% | 60.0% | 0.93 | −0.57 | −0.07 | 3.2 | 177 min | −0.39 |

### Engine structure triggers (STR): 409 ideas (15m 231, 30m 118, 1h 47, 4h 13)

| Strategy | Reached +15 / +20 (touch) | Confirmed | Invalidated (price / structure) | Expired | Trades | TP first | SL first | Ambiguous | PF | Net $ / oz | t | Max DD (R) | Missed +$30 | N2 net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 As alerted (−13 / +13) | 268 / 217 | — | — | — | 409 | 51.6% | 47.9% | 0.5% | 0.95 | −0.36 | −0.56 | 30.6 | — | — |
| 2 Trigger only | 268 / 217 | — | — | — | 409 | 39.4% | 60.4% | 0.0% | 0.91 | −0.72 | −0.89 | 41.1 | — | −0.91 |
| 3 $15 confirmation | 268 / 217 | 125 | 282 (184 / 98) | 2 | 125 | 48.0% | 52.0% | 0.0% | 1.32 | **+2.32** | 1.52 | 7.1 | 56 | −1.16 |
| 4 $20 confirmation | 268 / 217 | 104 | 302 (191 / 111) | 3 | 104 | 43.3% | 54.8% | 1.0% | 1.11 | +0.82 | 0.50 | 7.4 | 64 | −1.00 |
| 5a $15 + momentum and structure | 268 / 217 | 35 | 352 (200 / 152) | 22 | 35 | 54.3% | 45.7% | 0.0% | 1.77 | +4.83 | 1.61 | 3.2 | 121 | −0.81 |
| 5b $20 + momentum and structure | 268 / 217 | 33 | 354 (201 / 153) | 22 | 33 | 51.5% | 45.5% | 3.0% | 1.56 | +3.71 | 1.22 | 3.2 | 121 | −0.39 |

**What the funnel shows:**

- **$15 beats $20.** Waiting for $20 removes about a fifth of the confirmations and keeps the weaker ones.
- **Most triggers fail before they confirm.** 268 of 409 structure triggers touched +$15, but only 125 closed beyond
  it before price had gone −$13 against them or the structure had flipped. A touch of $15 is not a confirmation: many
  touch it after the trigger has already failed.
- **The filters cost too many trades.** Momentum, structure, cost and calm-bar filters raise the average, but they
  leave too few trades to test (35 and 33).
- **Random triggers lose.** The N2 pipeline loses −$0.4 to −$1.2 per oz in every version: a $15 move alone does not
  predict the next $20.

### Pre-registered tests (H1–H8; Holm over eight; a pass needs n ≥ 50, Holm p ≤ 0.05, beats N2 at 0.05, PF ≥ 1.1)

| | Triggers | Strategy | Trades | Net $ / oz | t | Holm p | vs N2 p | Verdict |
|---|---|---|---|---|---|---|---|---|
| H1 | ENG | $15 confirmation | 20 | +2.67 | 0.70 | 1.00 | 0.157 | INSUFFICIENT |
| H2 | ENG | $20 confirmation | 19 | +0.08 | 0.02 | 1.00 | 0.389 | INSUFFICIENT |
| H3 | ENG | $15 + filters | 5 | −0.57 | −0.07 | 1.00 | 0.488 | INSUFFICIENT |
| H4 | ENG | $20 + filters | 5 | −0.57 | −0.07 | 1.00 | 0.509 | INSUFFICIENT |
| H5 | STR | $15 confirmation | 125 | +2.32 | 1.52 | 0.45 | **0.012** | **FAIL** |
| H6 | STR | $20 confirmation | 104 | +0.82 | 0.50 | 1.00 | 0.135 | FAIL |
| H7 | STR | $15 + filters | 35 | +4.83 | 1.61 | 0.43 | 0.031 | INSUFFICIENT |
| H8 | STR | $20 + filters | 33 | +3.71 | 1.22 | 0.66 | 0.091 | INSUFFICIENT |

### Risk grid: stops × targets (net $ / oz, E1)

**Structure triggers with $15 confirmation (STR X15F0)**

| Stop \ target | +$15 | +$20 | +$25 | +$30 |
|---|---|---|---|---|
| $10 | +1.53 (125) | +1.96 (125) | +2.56 (125) | +2.65 (125) |
| $13 | +2.01 (125) | +2.32 (125) | +3.12 (125) | +3.41 (125) |
| 3 × ATR | +3.05 (45) | +4.01 (86) | +3.88 (108) | +3.56 (121) |
| Structure | — (0) | +4.29 (26) | +4.96 (70) | +3.95 (104) |

**$20 confirmation (STR X20F0)**

| Stop \ target | +$15 | +$20 | +$25 | +$30 |
|---|---|---|---|---|
| $10 | −0.27 | +0.59 | +1.75 | +1.94 |
| $13 | +0.39 | +0.82 | +2.20 | +2.57 |
| 3 × ATR | +1.56 | +0.64 | +1.28 | +0.52 |
| Structure | — | — | +7.17 (20) | 0.00 (53) |

**How to read the grid:**
- Within the development data, longer targets and the $13 stop did a little better than $10.
- The ATR and structure stops are often REJECTED because their R:R is below 1, so fewer trades remain.
- None of these differences survived validation (section 5).
- Of the 75 grid configurations with ≥ 50 trades, 44 were positive. That is what a family of strongly correlated
  configurations does on one lucky sample. The checks below were declared for exactly this.

### Overfitting checks (development, all 288 configurations)

| Check | Result | Reading |
|---|---|---|
| Walk-forward (train 12 months, test 6, four windows) | windows −0.28, −0.22, +0.32, +0.52 R; **56 test trades, +0.07 R, t 0.36** | Picking the best configuration in-sample does not carry forward |
| PBO (CSCV, 8 groups, monthly) | **0.46**; the in-sample best loses out of sample in 43% of splits | Close to a coin flip: the ranking is noise |
| Deflated Sharpe (best per-trade Sharpe, 33 trades, 101 eligible configurations) | **0.66** | Below 0.95: consistent with the luck of the best of many |
| White's Reality Check (monthly mean R vs no trade) | **p 0.103** | No configuration beats doing nothing at 5% |

### Regimes and timeframes (STR, $15 confirmation, −13 / +20)

| Regime | Trades | TP first | Net $ / oz |
|---|---|---|---|
| Trending (STRONG TR / EXPANSION) | 53 | 52.8% | +3.63 |
| Ranging (RANGE / COMPRESS) | 51 | 41.2% | −0.01 |
| Other | 21 | 52.4% | +4.66 |
| Volatile (top fifth of ATR / price) | 34 | 47.1% | +1.72 |
| News (≤ 2 h after CPI / NFP / FOMC) | 2 | — | — |

By timeframe: 15m +3.54 (68 trades), 30m −0.28 (39), 1h +3.50 (14), 4h +2.63 (4).

These splits are descriptive. Choosing "trending only" or "15m only" from them would be the same selection error as
B19-explore's hindsight rule.

## 5. Independent data

### Validation 2023-01-24 → 2024-07-01, opened once

This period was opened before (B13-1), so for engine-signal triggers it is not fully blind.

| Configuration | Trades | TP first | PF | Net $ / oz | t | N2 net | Pass |
|---|---|---|---|---|---|---|---|
| ENG 1 as alerted (−13 / +13) | 24 | 45.8% | 0.75 | −1.88 | −0.70 | — | — |
| ENG 2 trigger only | 24 | 41.7% | 0.99 | −0.05 | −0.01 | −0.92 | no |
| ENG 3 $15 confirmation | 7 | 71.4% | 3.46 | +9.69 | 1.60 | −1.12 | no (7 trades) |
| ENG 4 $20 confirmation | 5 | 60.0% | 2.07 | +5.91 | 0.73 | −0.61 | no |
| ENG 5a / 5b with filters | 1 / 1 | — | — | +19.23 | — | — | no |
| STR 1 as alerted (−13 / +13) | 187 | 52.4% | 0.99 | −0.09 | −0.09 | — | — |
| STR 2 trigger only | 187 | 44.4% | 1.13 | +0.95 | 0.79 | −0.92 | no |
| **STR 3 $15 confirmation** | 49 | 32.7% | 0.67 | **−3.04** | −1.36 | −1.12 | no |
| STR 4 $20 confirmation | 36 | 38.9% | 0.88 | −1.01 | −0.37 | −0.61 | no |
| STR 5a $15 + filters | 12 | 25.0% | 0.47 | −5.52 | −1.28 | −0.79 | no |
| STR 5b $20 + filters | 9 | — | — | −2.77 | −0.50 | −1.25 | no |
| **Development candidate STR X15F0 E1 SATR T20** | 38 | — | — | **−4.40** | −1.65 | −1.57 | **no** |

**The holdout (2024-07-01 → 2026-01-01) stays sealed.**
- The registration opens it only for a candidate that passes development and validation.
- `b19.main` refuses a holdout run for any configuration without a recorded validation pass.

### 2026-03-01 → 2026-11-02 (not sealed; partly seen before; descriptive)

| Configuration | Trades | TP first | Net $ / oz | t |
|---|---|---|---|---|
| ENG 1 as alerted (−13 / +13) | 55 | 47.3% | −1.49 | −0.85 |
| ENG 3 $15 confirmation | 23 | 43.5% | +0.53 | 0.15 |
| ENG 4 $20 confirmation | 21 | 47.6% | +1.92 | 0.52 |
| STR 3 $15 confirmation | 31 | 54.8% | +4.28 | 1.42 |
| STR 4 $20 confirmation | 27 | 51.9% | +3.29 | 1.02 |
| STR 5a / 5b with filters | 6 / 6 | — | −2.77 / −8.27 | — |

Across the three periods, the $15 confirmation on structure triggers went +2.32, −3.04, +4.28. That is the pattern of
noise around zero, not of an edge.

### Erratum: the engine's "64% / 61%" record counted repeats

**Diagnostic** (`research/results/b19_b10_dedupe_2026-11-07.json`): B10's own measure (+13 before −13 on 96 15m bars)
on the engine's 15m SIGNALs, 2020–22.

| Counting | Signals | +13 first |
|---|---|---|
| Every signal (as B10 and B13-1 counted) | 70 | 64.3% |
| One per idea (the live REPEAT rule: same direction within 4 h and $15) | **23** | **52.2%** |

- **The cause:** the engine often fires the same idea several times in a row. 3 Nov 2026 was one SELL idea sent as
  eight alerts.
- **Earlier counts:** B10 and B13-1 counted these as separate trades, which inflated both the sample size and the
  significance.
- **Per idea, the stream is near random in every period:** 52% (2020–22), 46% (2023–24), 47% (2026).
- **B15-ENGINE-FWD already counts one plan per idea** (REPEATs open none), so the live test measures the right thing
  and stays unchanged.
- **The "alerts above 60%" mode (PR #87) was justified by the inflated count.** It is the operator's decision whether
  to keep it.

## 6. Profitability after all trading costs

- **Costs charged:** spread (session-dependent), 2 × $0.20 slippage and $7 per lot commission. That is
  $0.77–0.97 per oz round trip, about 6–7.5% of a $13 stop.
- **The operator's measured cost ($0.26 per oz)** adds about +$0.5 per oz to every line. It changes no verdict.

| Configuration | Development model / operator cost | Validation model / operator cost |
|---|---|---|
| ENG 1 as alerted (−13 / +13) | −2.82 / about −2.3 | −1.88 / about −1.4 |
| STR $15 confirmation | +2.32 / +2.87 | −3.04 / −2.50 |
| STR $20 confirmation | +0.82 / +1.37 | −1.01 / −0.46 |

- **Ambiguous bars** (stop and target in the same 15m bar) were 0–3% of trades. Excluding them changes no figure by
  more than $0.55 per oz.
- **Swap / rollover is not charged.** Trades last about 2–10 hours on average, and a few cross 17:00 New York.

## 7. Monte Carlo: what a losing streak does to a $25,000 prop account

10,000 resamples of 100 trades from each strategy's own results. A 10% maximum loss is 3.85 R at 0.50 lot ($650
stop), 9.6 R at 0.20 lot ($260) and 19.2 R at 0.10 lot ($130).

| Strategy (results resampled) | P(10% loss) at 0.50 lot | at 0.20 lot | at 0.10 lot |
|---|---|---|---|
| ENG 1 as alerted, development | 100% | 98% | 74% |
| ENG 1 as alerted, validation | 100% | 92% | 50% |
| STR 1 as alerted, validation | 100% | 62% | 11% |
| STR $15 confirmation, development | 99% | 41% | 3% |
| STR $15 confirmation, validation | 100% | 99% | 82% |

**At 0.50 lot, the current plan breaches a 10% limit within 100 trades in essentially every simulation, whichever
stream it trades.**

## 8. Recommended SL, TP and risk parameters; configuration for live testing

- **Stop / target.**
  - None is validated.
  - Where the development data says anything, it says a fixed $13 stop did better than $10. Targets of +$20 to +$30
    did better than +$15, and $15 confirmation better than $20.
  - On validation every version lost.
  - **No change to the operator's −$13 / +$13 / +$20 plan is supported, and none is recommended.**
- **Risk.**
  - **0.10 lot (−$130 per stop, about 0.5% of $25,000) or less** while no stream has a proven edge.
  - At 0.50 lot, four stops in a row cost $2,600, already a breach of a 10% limit. At a success rate near 50% and 3–6
    trades a week, that happens several times a year.
- **Live-testing configuration.**
  - **None qualifies** under the registration: no configuration passed validation.
  - B15-ENGINE-FWD keeps running unchanged. It is the clean live test of the engine's signals, one per idea, at
    ±$13: first check at 30 results.
  - **If the operator still wants the two-stage process live,** the honest form is:
    - a display-only "confirmation monitor": trigger, price now, move toward +$15 / +$20, status
      (TRIGGERED / PENDING / CONFIRMED / INVALIDATED / EXPIRED) and the plan;
    - every status shown with its measured record ("no proven edge"), and no claim of confidence;
    - a new registration before it starts.
  - That is a production change, so it waits for the operator's approval.
- **Calibrated confidence.** No calibrated probability above the geometric baseline can be given. On the data, the
  honest confidence of any confirmed signal is S / (S + T), about 39% at −13 / +20.

## 9. Tests and commits

| Item | Reference |
|---|---|
| Registration (before code) | `2c4843f77` |
| Code and 18 tests | `fc6d1352e`, `935b18909` |
| Save fix: an infinite profit factor (the first run stopped while writing; nothing read) | `f3aff7e1e` |
| Development results, committed before validation | `0ec3354f3` |
| Validation (once); holdout sealed | `cc5219230` |
| This report, the 2026 descriptive run, the Monte Carlo | the commit adding this file |
| Tests | `tests/test_research_b19.py`: 19 passed (all 19 test functions); full suite in the PR |

**Every rule has its own test:**
- touch is not confirmation;
- the close confirms;
- price and structure invalidation, and invalidation winning a tie in one bar;
- each F1 filter;
- SELL symmetry, and the direction never reversed;
- no look-ahead;
- the exits: TP, ambiguous, gaps at the open, timeout;
- E2 fill and miss;
- the R:R rejection and the trigger-only entry;
- the REPEAT rule, the statistics helpers and the partition seals;
- the holdout gate and the undefined profit factor.

## 10. The last month (2026-10-07 → 2026-11-06; exploratory, operator request 2026-11-07)

**Tool:** `research/tools/b19_last_month.py`, the B19 rules unchanged on the site's own 15m / 1h store.

**Results:** `research/results/b19_last_month_2026-11-07.json`. 22 configurations, logged as `B19-month`.

**The month:** gold opened at 4,168, made 4,216 (12 Oct) and 3,866 (1 Nov), and closed at 4,069.

| Stream (stop −$13) | Ideas | Confirmed | Trades | TP first at +$15 | TP first at +$20 | Net $ / oz at +$15 |
|---|---|---|---|---|---|---|
| Random entries, BUY (every 15m close) | — | — | 2,093 | 37.6% | 30.8% | — |
| Random entries, SELL | — | — | 2,094 | 53.0% | 44.8% | — |
| Engine signals, entry at the signal (all 10 were SELLs) | 10 | — | 10 | 20% | 10% | −8.19 |
| Structure triggers, entry at the trigger | 18 | — | 18 | 33% | 11% | −4.44 |
| Engine + $15 confirmation | 10 | 1 (9 invalidated) | 1 | 0 of 1 | 0 of 1 | −13.77 |
| Structure + $15 confirmation | 18 | 2 (16 invalidated) | 2 | 0 of 2 | 0 of 2 | −13.87 |
| Structure + $20 confirmation | 18 | 1 | 1 | 0 of 1 | 0 of 1 | −13.97 |
| Either + filters (F1) | — | 0 | 0 | — | — | — |

**What the month shows:**

- **Nothing reached TP first more often than random.**
- **"Sell everything" did best,** because the month fell. That is hindsight, not a rule: in 2023–24 the BUYs won.
- **The confirmation step kept almost every trade out.** Price went −$13 against 25 of 28 triggers before a 15m candle
  closed +$15 beyond them. That avoided 8 of the engine's 10 losing ideas, but the 1–2 trades it did take lost.
- **Waiting for pending triggers:** none was pending at the 6 Nov close.

## Erratum (2026-11-10): cost units

Found while validating the confirmation panel (`research/CF_VALIDATION.md`, PR #90). Section 3 defines
net = (exit − entry)·d / s − cost: the move is put at a $4,000 price (divided by s = P0 / 4000) but the cost is not,
so the cost is under-weighted by 1 / s when gold traded far below $4,000. In consistent units (cost / s) the ENG
X15F0 E1 S13 +$15 figure falls from +$2.97 to +$1.99 per oz on 2020-22 (s ≈ 0.46) and from +$6.12 to +$5.39 on
2023-24 (s ≈ 0.52); 2026 (s ≈ 1.1) is unchanged in substance. The EXECUTE cost cap (cost ≤ 0.15·D / s) mixes the same
units: in consistent units 6 of the 20 confirmed 2020-22 trades and 1 of the 7 2023-24 trades would fail it.

What does not change: every TP-first / SL-first count and rate (outcomes do not depend on the cost), every verdict
(each correction lowers the expectancy, and no B19 configuration was validated), and the confirmation panel, which
shows only those counts. The original figures are kept above as they were reported; the corrected ones, with
`net_b19` beside them for reproduction, are in `research/results/cf_validation.json`.
