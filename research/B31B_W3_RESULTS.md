# B31b-W3: M15 / M30 liquidity sweeps, liquidations and breakouts — what happens before, during and after, and whether any entry reaches +$10 / +$15 / +$20 before its stop

Operator's directive "CLAUDE DIRECTIVE — QUANTUM WORKSTREAM 3" (2026-11-18). Registration `research/registrations/B31b-W3.json`.

## 0. Answer

1. **A liquidity sweep or breakout on M15 / M30 gold, on its own, does not predict which way the next $10 goes.**
   - **Sweeps:** after a bar takes a level and closes back inside (14,090 events from 2020 to 2023), the next +$10 came first in the reversal direction:
     - 48.5% (buy-side) and 50.0% (sell-side) on M15;
     - 46.9% and 49.7% on M30.
   - **Path symmetry:** at every horizon from 15 minutes to 4 hours, the median move for and against the reversal is the same size (directional efficiency 0.48–0.50).
2. **No entry method beats a random entry with the same stop.**
   - 10 entry methods × 2 timeframes = 20 variants: none reaches +$10 first more often than a matched random entry (one-sided p 0.23–0.98).
   - All 20 lose money after costs at +$10 (net −0.04 to −0.15 R a trade). The same holds at +$15 and +$20, except A-MSS M30 at +$20 (+0.023 R, not significant).
3. **No combination of conditions fixes it.**
   - **The model:** a logistic model on 36 condition measures (trend, volatility, session, room, penetration, wick, displacement, waiting time and the directional efficiency so far) predicts no better than the stop / target geometry alone, out of sample, in all 20 variants.
   - **Single conditions:** 0 of 701 single-condition tests survive the multiple-testing correction.
   - **Filters:** every filter that seemed to raise the +$10 rate (room ≥ $10, London / New York only, a displacement bar) raised the geometric break-even by the same amount. They chose wider stops, not better direction.
4. **Registered verdict: NO CANDIDATE for engine A (reversal) and for engine B (continuation).**
   - Under the registration, validation (2023-24) and holdout (2024-25) are therefore **not opened**; they stay sealed.
   - Nothing is frozen and nothing goes to production. The formula's output is **NO TRADE — INSUFFICIENT EVIDENCE**.
5. **The confirmation methods arrive late.** For sweeps that did reverse $10:
   - the market-structure-shift entry (A-MSS) came in after a median 74% (M15) and 113% (M30) of that $10 move had already happened;
   - the M5 shift (A-M5MSS) after 37–43%;
   - one confirming candle (A-CONF) after 22–32%.
6. **The $650 limit:**
   - **Sizing holds it:** modelled loss never exceeds $650 (lots = 650 / ((stop + cost) × 100), floored to 0.01).
   - **Gaps can break it:** 90 of 9,335 stopped trades (1.0%) lost more than $650. The worst lost $3,041.

The 17–18 Nov chart you sent shows both sides of this (section 8).
- **The top was a sweep that worked:** 3,886–3,892 on 17 Nov at 16:00 UTC, class A, +$10 lower within 25 minutes.
- **The low sweeps on 18 Nov failed:** 16:30 and 18:00 UTC, both class D, price kept falling.

At the moment of the sweep the two looked the same to every measure tested.

## 1. What was done, in order

| Step | Commit | What |
|---|---|---|
| 1 | — | **5-minute history added.** Twelve Data 5-minute XAU/USD from 16 Mar 2020 (the feed's first 5-minute bar) to 18 Nov 2026: 509,379 bars, 104 requests over three `research-history` runs, each started after the website's own data fetch so they never shared a minute. All site runs at the time (#3576–3580) succeeded. |
| 2 | `69c746a7c` | **Registration**, before any code: event definitions, measurements, classes, 10 entry methods, costs and $650 sizing, matched random control, model, selection rule, freeze, validation / holdout gate, shadow module. |
| 3 | `776235851`, `9becea6ad` | **Code and tests**, before any development run: `quantum/research/w3liq.py`, plus amendment A1 (three pre-run clarifications). 21 deliberate bugs injected: 20 caught, 1 equivalent. |
| 4 | `87e6b9d4a` | **Shadow module** `quantum/research/w3shadow.py`, tested. |
| 5 | — | **Development run 1.** Showed two labelling defects in the classes (C1, C2) — trade results unaffected. |
| 6 | `4432bf23f` | **Corrections C1 / C2** (class labels only). |
| 7 | — | **Run 2.** Every trade, model and selection result was identical to run 1. Comparing the two showed 21 events whose "primary level" label changed between processes. |
| 8 | `7d77f391b` | **Reproducibility fix R1:** tie-break by name; a test under three hash seeds. |
| 9 | — | **Run 3**, the result of record. Byte-identical under two further hash seeds (101, 202). Also a descriptive run on Jan–Nov 2026 (unsealed). |

All three development runs and the 2026 run are in `research/trials.jsonl` (append-only).

**Data and conventions:**
- **Distances are in $ at $4,000:** a historical move is scaled by price / 4,000, as in B31, so "+$10" means the same relative move in 2020 ($1,800 gold) as today.
- **Costs are today's engine model:** session spread + 2 × $0.20 slippage + $7 commission per lot, $0.58–0.97 per oz a round trip.
- **Volume is not used.** The spot series has none, and W1 found tick volume unreliable. The "relative volume" items of the directive are therefore NOT TESTED.
- **TWAP replaces VWAP.** VWAP cannot be computed without volume; a TWAP anchored at the trading-day start is used, and labelled TWAP.

## 2. Deliverable A — what happens before, during and after a liquidity event

### 2.1 How many events

**An event:** the first crossing of a live level by a bar.

**Levels:** PDH / PDL, PWH / PWL, the Asian / London / New York session high and low, the previous session's high and low, swing highs and lows (3 bars each side), and equal highs and lows.

**Grouping:** all levels crossed by one bar on one side make one event.

**Kinds of event:**
- **SWEEP:** the bar closes back inside the level.
- **BREAK:** the bar closes beyond it.

Development, 2020-03 → 2023-01 (150 weeks):

| Type (directive's list) | M15 events | per week | M30 events | per week |
|---|---|---|---|---|
| 1 buy-side sweep | 2,275 | 15.2 | 1,254 | 8.4 |
| 2 sell-side sweep | 2,257 | 15.0 | 1,210 | 8.1 |
| 3 PDH liquidation (sweep or break) | 361 | 2.4 | 363 | 2.4 |
| 4 PDL liquidation | 335 | 2.2 | 337 | 2.2 |
| 5 previous-session high / low | 1,911 | 12.7 | 1,915 | 12.8 |
| 6 Asian high / low | 1,069 | 7.1 | 1,069 | 7.1 |
| 7 sweep in London | 2,167 | 14.4 | 1,269 | 8.5 |
| 8 sweep in New York | 870 | 5.8 | 473 | 3.2 |
| 9 equal highs / lows | 695 | 4.6 | 293 | 2.0 |
| 10 swing stop hunt (sweep) | 4,299 | 28.6 | 2,082 | 13.9 |
| 11 false breakout (back inside within 2 bars) | 2,055 | 13.7 | 1,041 | 6.9 |
| 12 accepted breakout (3 closes beyond) | 2,626 | 17.5 | 1,370 | 9.1 |
| 13 breakout, retest | 1,561 | 10.4 | 806 | 5.4 |
| 14 sweep then market-structure shift | 2,090 | 13.9 | 1,105 | 7.4 |
| **All events** | **9,214** | **61.4** | **4,876** | **32.5** |

- **Levels involved:** swings are 72% of M15 sweeps; previous-session levels 16%; PD 5%; equal highs / lows 3%; PW 1%.
- **2026 was the same:** 63.4 events a week on M15 and 34.2 on M30.

### 2.2 Before the event (development medians)

- **Distance:** price closed 0.6 ATR from the level on the bar before, after 4 bars of momentum toward it (0.6–0.7 ATR).
- **Range:** the last 16 bars spanned 3.5 ATR.
- **Volatility:** ATR14 / ATR100 was 0.90, slightly quieter than average.
- **ATR:** the median M15 ATR was $4.5 (M30 $6.6).
- **Room in the reversal direction** (to the nearest live level on the other side):
  - sweeps: $12.0 (M15), $16.5 (M30);
  - breaks: $15.9 (M15), $22.7 (M30).

### 2.3 During the crossing bar

| | M15 sweep | M15 break | M30 sweep | M30 break |
|---|---|---|---|---|
| Penetration beyond the level, median | $0.81 | $2.90 | $1.23 | $4.41 |
| Penetration, 75th percentile | $1.74 | $5.45 | $2.48 | $8.37 |

A sweep that closes back inside goes about $1 through the level. A break goes $3–4 through.

### 2.4 After the event (reversal direction; continuation is the mirror)

| | M15 sweep | M15 break | M30 sweep | M30 break |
|---|---|---|---|---|
| Median move for / against, first 15 min | $1.9 / $2.1 | $2.2 / $2.0 | $2.1 / $2.2 | $2.4 / $2.3 |
| Median move for / against, first hour | $4.0 / $4.2 | $4.4 / $4.2 | $4.2 / $4.3 | $4.6 / $4.4 |
| Median move for / against, 4 hours | $8.5 / $8.4 | $8.9 / $8.2 | $8.4 / $8.6 | $9.2 / $8.3 |
| Directional efficiency (median) at 15 / 60 / 240 min | 0.48 / 0.49 / 0.50 | 0.53 / 0.52 / 0.53 | 0.50 / 0.49 / 0.49 | 0.53 / 0.53 / 0.54 |
| +$10 reversal within 24 h | 76.3% | 77.3% | 75.2% | 77.8% |
| +$10 continuation within 24 h | 77.2% | 75.6% | 76.7% | 76.4% |
| Which +$10 came first: reversal | 49.2% | 50.4% | 48.3% | 51.2% |
| Price back at the level within 4 h | 86.5% | 86.4% | 81.2% | 81.8% |
| Back to the liquidation origin within 4 h | 42.5% | 30.6% | 28.9% | 17.2% |

**Directional efficiency** is the move in the reversal direction / (that move + the move against it). It describes the path; it is not a probability.

**Breaks lean slightly to reversal.** After a break (closed beyond), the reversal +$10 came first slightly more often than continuation (50.4% M15, 51.2% M30); a break more often failed than continued.

**Types 11–14 are measured from the crossing bar's close.** Rates such as "sweep then shift: reversal first 80%" include the move that created the shift. That is hindsight, not something you can trade. Each type's tradeable version is its entry method in section 4, measured from its own entry.

### 2.5 Classes A–G (outcome labels; never used as inputs)

| | M15 sweeps | M30 sweeps | | M15 breaks | M30 breaks |
|---|---|---|---|---|---|
| A reversal before the extreme was exceeded (A1) or after (A2) | 1,728 (38%) | 1,097 (45%) | B continuation | 1,378 (29%) | 894 (37%) |
| D continuation (sweep failed) | 2,051 (45%) | 1,174 (48%) | C false breakout then reversal | 1,467 (31%) | 921 (38%) |
| F both sides taken (whipsaw) | 731 (16%) | 182 (7%) | F | 564 (12%) | 126 (5%) |
| E no $10 move within 24 h | 1 | 0 | E | 1,233 (26%) | 450 (19%) |
| G order unknown | 21 | 11 | G | 40 | 21 |

**Successful vs failed reversals (sweep A vs D / E), significant after Benjamini-Hochberg:**
- **M15:** the successful ones had
  - slightly higher volatility (ATR $4.93 vs $4.76);
  - a slightly wider crossing bar (1.28 vs 1.21 ATR) with a bigger body (0.43 vs 0.40 ATR);
  - more room in both directions (reversal $14.6 vs $13.0; continuation $10.8 vs $9.8).
- **M30:** no measure differed significantly.

These differences are small, and as decision inputs at the entry they add nothing beyond stop distance (section 5).

**Genuine vs false breakouts (break B vs C / E):** genuine ones had
- deeper penetration (M15 $4.49 vs $2.81; M30 $6.14 vs $3.96);
- a bigger body (M15 1.32 vs 1.05 ATR) and a close further beyond (0.54 vs 0.32 ATR);
- more levels taken at once (M15 2 vs 1; M30 3 vs 2);
- more room on both sides.

Again, none of this predicted the trade result beyond geometry (section 5).

## 3. Deliverable B — reversal vs continuation by timeframe, session and regime

**Share of events whose +$10 reversal came first** (development; the rest went +$10 in the continuation direction first). n is in brackets.

| | M15 sweeps | M15 breaks | M30 sweeps | M30 breaks |
|---|---|---|---|---|
| Asian session | 51.4% (1,403) | 50.7% (1,531) | 46.3% (717) | 52.8% (745) |
| London open (07–09 UTC) | 46.8% (532) | 46.7% (550) | 49.2% (376) | 45.2% (354) |
| London continuation | 48.9% (1,303) | 50.8% (1,305) | 50.0% (698) | 51.8% (703) |
| New York open (first 2 h) | 47.1% (323) | 48.0% (346) | 46.1% (191) | 48.7% (187) |
| London / New York overlap (all bars in both) | 47.6% (332) | 47.9% (351) | 46.2% (195) | 49.5% (190) |
| New York continuation | 48.1% (538) | 50.3% (591) | 47.8% (278) | 51.3% (275) |
| After the New York close | 49.1% (424) | 56.2% (354) | 50.0% (200) | 56.6% (145) |
| Trending (efficiency ≥ 0.30) | 49.9% (1,211) | 47.7% (1,193) | 45.3% (702) | 50.2% (638) |
| Mixed | 49.5% (1,406) | 52.1% (1,485) | 50.7% (714) | 51.2% (763) |
| Ranging (efficiency < 0.15) | 48.7% (1,915) | 50.8% (2,004) | 48.6% (1,048) | 51.7% (1,011) |
| Low volatility (ATR ratio ≤ 0.8) | 52.8% (1,347) | 49.9% (1,460) | 49.2% (531) | 48.6% (518) |
| Normal volatility | 47.7% (2,692) | 50.9% (2,709) | 47.9% (1,779) | 51.8% (1,730) |
| High volatility (≥ 1.25) | 47.9% (493) | 49.1% (513) | 48.7% (154) | 52.4% (164) |
| Within 1 h after CPI / NFP / FOMC | 49.1% (55) | 51.4% (70) | 56.4% (39) | 48.2% (56) |

**The same event behaves close to a coin flip in every session and regime.**
- **Where n is large** (over 300) the share stays between 45% and 53%.
- **Two corners lean further:** breaks after the New York close (56%, n 145–354) and the few news events.
- **Neither is a tested hypothesis:** both are small corners of a large table.

Per-variant session and regime results are in the results file (`variants → breakdown`). Their best cells, such as A-MSS M30 at the New York open (83% of 30), are small and do not survive the count of cells examined.

## 4. Deliverable D — TP performance of every entry method (development, eligible trades, one position at a time)

**What the numbers mean:**
- **"+$T first"** = the target before the structural stop, raced separately for +$10, +$15 and +$20 from the same fill.
- **Random** = 20 random entries per trade in the same session and volatility tercile, with the same direction, stop distance and targets.
- **Net R** = the result after costs as a multiple of the cost-inclusive risk; × $650 = dollars a trade.
- **Ties:** a 15m bar touching both stop and target is ordered with 5-minute bars, and otherwise counted as the stop.

| Method | TF | Trades | Per week | +$10 first | Random | p | +$15 first | Random | +$20 first | Random | Net R at +$10 [95%] | Net R +$15 | Net R +$20 | Median stop $ | Median min to +$10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A-IMM | M15 | 1,249 | 8.3 | 43.2% | 46.1% | 0.97 | 33.0% | 36.7% | 28.1% | 30.4% | -0.146 [-0.199, -0.092] | -0.175 | -0.143 | 7.8 | 50 |
| A-CONF | M15 | 1,167 | 7.8 | 49.3% | 49.0% | 0.44 | 39.3% | 39.4% | 34.3% | 32.7% | -0.086 [-0.137, -0.032] | -0.095 | -0.059 | 9.2 | 65 |
| A-MSS | M15 | 1,301 | 8.7 | 56.6% | 59.3% | 0.97 | 47.3% | 49.0% | 40.3% | 41.2% | -0.106 [-0.146, -0.065] | -0.098 | -0.080 | 14.4 | 95 |
| A-M5MSS | M15 | 950 | 6.3 | 50.6% | 53.3% | 0.94 | 40.0% | 43.3% | 34.6% | 36.0% | -0.112 [-0.172, -0.055] | -0.146 | -0.118 | 10.7 | 85 |
| A-RETEST | M15 | 275 | 1.8 | 39.6% | 43.8% | 0.91 | 29.5% | 34.8% | 25.1% | 28.5% | -0.148 [-0.283, -0.017] | -0.213 | -0.164 | 7.0 | 35 |
| A-DISP | M15 | 545 | 3.6 | 49.5% | 48.8% | 0.37 | 38.0% | 39.7% | 32.5% | 33.0% | -0.086 [-0.161, -0.005] | -0.128 | -0.120 | 9.3 | 65 |
| B-CLOSE | M15 | 2,569 | 17.1 | 51.0% | 51.0% | 0.50 | 41.8% | 41.3% | 34.1% | 34.1% | -0.076 [-0.112, -0.040] | -0.065 | -0.091 | 9.7 | 50 |
| B-ACC | M15 | 1,767 | 11.8 | 56.3% | 55.4% | 0.24 | 45.2% | 45.2% | 37.4% | 37.8% | -0.063 [-0.103, -0.023] | -0.085 | -0.101 | 12.2 | 65 |
| B-RETEST | M15 | 552 | 3.7 | 42.9% | 46.2% | 0.94 | 35.1% | 36.6% | 29.0% | 30.1% | -0.143 [-0.229, -0.056] | -0.119 | -0.100 | 7.7 | 65 |
| B-DISP | M15 | 757 | 5.0 | 41.9% | 45.0% | 0.95 | 32.9% | 35.3% | 27.1% | 28.8% | -0.148 [-0.225, -0.073] | -0.158 | -0.155 | 7.5 | 45 |
| A-IMM | M30 | 1,129 | 7.5 | 45.7% | 48.8% | 0.98 | 37.8% | 39.4% | 31.6% | 32.6% | -0.140 [-0.195, -0.085] | -0.114 | -0.115 | 9.0 | 65 |
| A-CONF | M30 | 896 | 6.0 | 52.2% | 53.2% | 0.72 | 43.1% | 43.3% | 36.2% | 36.0% | -0.099 [-0.160, -0.040] | -0.076 | -0.061 | 11.1 | 110 |
| A-MSS | M30 | 780 | 5.2 | 65.8% | 65.4% | 0.41 | 57.3% | 55.0% | 49.0% | 46.4% | -0.038 [-0.088, +0.011] | -0.002 | +0.023 | 20.3 | 125 |
| A-M5MSS | M30 | 747 | 5.0 | 53.8% | 55.3% | 0.79 | 44.0% | 45.1% | 38.3% | 37.8% | -0.084 [-0.147, -0.020] | -0.080 | -0.033 | 11.7 | 112 |
| A-RETEST | M30 | 308 | 2.1 | 42.2% | 43.8% | 0.71 | 33.8% | 34.8% | 26.3% | 27.8% | -0.151 [-0.264, -0.041] | -0.140 | -0.189 | 7.2 | 50 |
| A-DISP | M30 | 317 | 2.1 | 50.8% | 55.5% | 0.95 | 41.6% | 45.5% | 35.3% | 37.5% | -0.143 [-0.237, -0.050] | -0.130 | -0.120 | 12.4 | 95 |
| B-CLOSE | M30 | 1,818 | 12.1 | 53.4% | 55.7% | 0.97 | 44.8% | 45.5% | 37.5% | 38.1% | -0.105 [-0.146, -0.066] | -0.087 | -0.091 | 11.9 | 65 |
| B-ACC | M30 | 1,113 | 7.4 | 61.2% | 60.1% | 0.23 | 51.0% | 49.6% | 42.9% | 41.7% | -0.047 [-0.092, +0.003] | -0.049 | -0.049 | 15.5 | 110 |
| B-RETEST | M30 | 488 | 3.3 | 46.9% | 49.1% | 0.83 | 38.9% | 39.7% | 32.0% | 32.8% | -0.119 [-0.207, -0.031] | -0.089 | -0.101 | 9.0 | 65 |
| B-DISP | M30 | 613 | 4.1 | 46.2% | 47.8% | 0.78 | 38.8% | 38.3% | 32.0% | 31.6% | -0.141 [-0.222, -0.062] | -0.112 | -0.118 | 9.0 | 65 |

**Methods:**
- **A-IMM:** at the sweep candle's close.
- **A-CONF:** the next candle confirms.
- **A-MSS:** M15 / M30 structure shift.
- **A-M5MSS:** M5 structure shift within 60 minutes.
- **A-RETEST:** limit at the swept level.
- **A-DISP:** limit at 50% of a displacement candle.
- **B-CLOSE:** breakout candle's close.
- **B-ACC:** after 3 closes beyond.
- **B-RETEST:** limit at the broken level.
- **B-DISP:** limit at 50% of the breakout displacement candle.

The exact rules are in the registration.

**What the table shows:**
- **High rates come with wide stops.** The variants with the highest +$10 rates (A-MSS M30 65.8%, B-ACC M30 61.2%) have the widest stops ($20.3, $15.5). Random entries with the same stops do just as well (65.4%, 60.1%). Their rate is geometry, and they still lose after costs.
- **The +$10 / +$15 / +$20 ladder is reported separately**, as the directive asks. A trade that reached +$10 often did not reach +$15: for A-MSS M30, 65.8% → 57.3% → 49.0%.

**Other performance measures** (results file, `variants → summary`):
- **Profit factor** at +$10: 0.71–0.89. Every variant is below 1.
- **Drawdown** at $650 risk a trade, over 150 weeks: $26,078 to $141,458. The cumulative loss of each variant.
- **MFE / MAE after the fill** over 24 h: medians of $20–27 for and $23–33 against, depending on the variant.
- **Ambiguous bars:** at most 5 per variant counted as a stop because 5-minute bars could not order them; up to 9 were ordered by 5-minute bars.

**Rejections and misses** (development, every order):

| Method | TF | Orders | Eligible | Rejected: cost > 15% of stop | Limit not filled | Stop on the wrong side (gap) |
|---|---|---|---|---|---|---|
| A-IMM | M15 | 4,532 | 1,323 | 3,209 | 0 | 0 |
| A-RETEST | M15 | 4,532 | 275 | 3,401 | 844 | 12 |
| B-CLOSE | M15 | 4,682 | 2,857 | 1,825 | 0 | 0 |
| B-RETEST | M15 | 2,626 | 555 | 1,005 | 1,065 | 1 |
| A-IMM | M30 | 2,464 | 1,195 | 1,269 | 0 | 0 |
| B-ACC | M30 | 1,370 | 1,265 | 105 | 0 | 0 |

All 20 rows are in the results file (`funnel`).
- **Cost:** sweep stops are short (median $0.8 of penetration plus a 0.2 ATR buffer), so 71% of immediate M15 sweep entries fail the 15% cost rule. That is W2's finding again.
- **Unfilled limits:** a limit at the swept level is not revisited within 8 bars in most cases.

## 5. Deliverable C — the quantitative entry formula

**The registered formula** (variables, calculations, thresholds and rejection logic):

1. **Levels:** the 9 kinds of section 2.1, each known before the bar opens and used once.
2. **Event:** the crossing bar; SWEEP if it closes back inside the nearest crossed level, else BREAK.
3. **Entry, structural stop and fill:** per the method; the stop is beyond the structure by 0.2 × ATR14.
4. **Distance:** D = |entry − stop| / (price / 4000).
5. **Cost:** c = session spread + 2 × slippage + commission / 100 oz.
6. **Rejections:** the stop on the wrong side; lots = floor_0.01(650 / ((D + c) × 100)) below 0.01; c > 15% of D.
7. **Targets:** +$10 / +$15 / +$20 from the fill. Time stop 24 h.
8. **Probability:** p = logistic model on the 36 measures plus the 3 geometry terms; trade only if p ≥ (D + c) / (10 + D) + 0.05 (the break-even plus a fixed margin).

**What the data said about each part:**
- **The model adds nothing.** Out of sample (walk-forward on development), the full model's AUC was **lower** than the geometry-only model's in all 20 variants. The full model was 0.49–0.61; geometry alone 0.55–0.65. The 95% interval of the difference was below or around zero in every variant.
- **Its probabilities are worse than the plain hit rate:**
  - its Brier skill against the base rate was negative in 17 of 20 variants;
  - against geometry it was negative in all 20.
- **Reliability is flat.** For B-ACC M30, the model's top decile predicted 94% and hit 67%.
- **Ablation:** removing any group of measures (level, trend, volatility, location, momentum, the crossing bar, the waiting time / directional efficiency so far, session) changed out-of-sample AUC by −0.004 to +0.004 on average.
- **The early directional efficiency** ("waiting" group, used by the delayed entries) carried no information: +0.0035 AUC.

**The registered selection.** It needed n ≥ 30, positive net R with a 95% lower bound > 0, and +$10-first above random at p < 0.05. **No variant passed**, under either rule (all entries, or model-gated): 40 tried.
- **The nearest:**
  - **A-IMM M15 with the model gate:** 82 trades, +$10 first 61.0% vs random 50.4% (p 0.031), net +0.17 R, but the 95% interval was −0.04 to +0.37. With 40 rules tried, p 0.031 is expected by chance.
  - **A-MSS M30 with the model gate:** +0.018 R [−0.081, +0.115].
- **PBO 0.27.** The rule that looked best in-sample lost out of sample in 61% of splits; its mean was −0.055 R.

**So the formula's output is NO TRADE — INSUFFICIENT EVIDENCE**, for every event, until a definition is found that beats random entries with the same stop.
- **The score is not a probability.** Its quality score (the percentile of the model's predictor) is defined in the code, but showing it would suggest a ranking that has no measured value. It is not shown anywhere.
- **Nothing is frozen.**

## 6. Deliverable E — opportunity frequency

| | Development 2020-23 | 2026 (Jan–Nov, descriptive) |
|---|---|---|
| Events per week, M15 | 61.4 | 63.4 |
| Events per week, M30 | 32.5 | 34.2 |
| Sweeps per week (M15, both sides) | 30.2 | 29.0 |
| Eligible entries per week, all 20 variants together (one position per variant) | 129 | 191 |
| Of which with a measured edge over random | 0 | not tested (2026 is not a test period) |

Per variant per week: section 4 (development) and the 2026 file. A single method gives 2–17 trades a week on development and 2–28 in 2026.

**Missed and late entries:** of the 3,460 M15 sweeps whose +$10 reversal happened, only 16 got no delayed entry at all. The delayed methods entered late:

| Delayed method | Share of the +$10 reversal gone at entry (median, M15 / M30) | 75th percentile |
|---|---|---|
| A-CONF (next candle) | 22% / 32% | 41% / 60% |
| A-M5MSS (M5 shift) | 43% / 37% | 70% / 70% |
| A-DISP (displacement pullback) | 28% / 42% | 48% / 71% |
| A-MSS (M15 / M30 shift) | 74% / 113% | 114% / 166% |
| A-RETEST (limit at the level) | −12% / −19% (a better price), but its stop (from the level to the sweep extreme) is so short that 92% of fills fail the cost rule, and the eligible ones lost more | — |

**2026 (unsealed, descriptive).** A-IMM M15 did better than random in 2026 (54.1% vs 48.3%, p 0.004) and roughly broke even (+0.010 R, 95% −0.071 to +0.095).
- **On development it was the worst variant:** 43.2% vs 46.1%.
- **One period is not evidence:** 60 rates were looked at in 2026, so one p of 0.004 is not significant (Holm-adjusted 0.24). It also reversed between periods.
- **It is not a candidate.** The registration selects on development only.

## 7. Validation and holdout

**Not opened.** The registration (`selection_and_freeze`, `validation_and_holdout_gate`) opens validation only for a frozen candidate. No candidate exists, so `B31b-W3-FREEZE.json` was not written. The code refuses validation without it, and holdout without a validation PASS (tested).
- **The sealed periods stay unused.** 2023-24 and 2024-25 remain available for a future, differently defined hypothesis.

## 8. Case study: 17–18 Nov 2026 (your M15 / M30 screenshots)

- **What was run:** the registered detector on the market-data store's bars (Twelve Data, UTC; your MT5 chart is in server time, usually UTC+2). Run after the fact and descriptive only; nothing was adjusted to fit the chart.
- **What it found:** 40 events. The main ones:

| UTC | TF | Event | Levels | Level / extreme / close | Class | What followed |
|---|---|---|---|---|---|---|
| 17 Nov 06:00 | M30 | buy-side SWEEP | NY high, previous session high | 3885.61 / 3886.42 / 3881.00 | A1 | −$10 in 50 min |
| 17 Nov 15:45 | M15 | buy-side BREAK | Asia, London, previous-session and equal highs | 3871.62 / 3891.96 / 3890.69 | C (false breakout) | −$10 in 5 min; B-CLOSE long hit its stop |
| 17 Nov 16:00 | M30 | buy-side SWEEP (the top) | Asia, London, previous-session highs | 3886.42 / 3891.96 / 3875.84 | A1 | −$10 in 25 min. A-IMM short: entry 3875.84, stop 3894.39 ($19.1), 0.32 lot, reached +$10 / +$15 / +$20. A-CONF entered $5.4 lower. A-MSS entered $19.7 lower, 3 h later |
| 18 Nov 00:30 | M15 / M30 | sell-side BREAK | London low, PDL, swing low | 3837.09 / 3831.12 / 3831.37 | B | −$10 in 5 min. B-CLOSE short: entry 3831.37, stop 3843.51, reached all three targets |
| 18 Nov 07:15 | M15 | sell-side BREAK | Asia low, previous session low | 3774.48 / 3770.31 / 3773.35 | B | −$10 in 60 min |
| 18 Nov 16:30 | M30 | sell-side SWEEP | swing low | 3742.26 / 3739.16 / 3742.83 | D (sweep failed) | price kept falling |
| 18 Nov 18:00 | M15 / M30 | sell-side SWEEP | London low, previous session low | 3734.22 / 3729.40 / 3734.96 | D (sweep failed) | −$10 more in 95 min. A-IMM long: entry 3734.96, stop 3726.53, hit the stop; so did A-CONF and A-RETEST |

**On your chart:**
- **The top was a buy-side sweep that reversed.** This is the pattern the directive describes.
- **The lows were sell-side sweeps that did not reverse.** On 18 Nov, buying each low that was swept and closed back inside lost every time.

In history the two cases occur about equally often (section 2.4). Nothing measured at the sweep told them apart.

## 9. Deliverable F — the shadow module (research only, not connected)

`quantum/research/w3shadow.py` (tests: `tests/test_research_w3shadow.py`).

**What it does:**
- **Runs the same detector**, imported rather than copied, on the store's closed bars at a given instant.
- **Appends records** to a hash-chained JSONL ledger:
  - EVENT;
  - ENTRY: id, time, engine, method, timeframe, level, sweep / break price, decision, entry reference, stop, TP1–3, cost, lots, eligibility and rejection reason, data freshness;
  - RESOLVE: TP / SL order per target, minutes to target, MFE / MAE, and a matched control entry;
  - CLASS.
- **Safety rules:**
  - an id is never written twice;
  - a decision first seen more than 20 minutes after its close is STALE and never qualifies;
  - QUALIFIES is possible only under a frozen candidate, and there is none;
  - it has no alert, notification or network code (tested).

**Replays on the store** (mechanics checks, not evidence):
- **25 Oct → 18 Nov, one step every 2 hours:** 299 steps, 3,153 records, chain valid, no duplicate ids.
  - 1,279 entries, 791 eligible, 780 resolved.
  - +$10 first: 420 (53.8%), against 455 (58.3%) for their matched controls.
- **17–18 Nov at the live cadence (every 15 minutes):** 186 steps.
  - The first step found a 3-day backlog; all 62 of its entries were correctly marked STALE.
  - After that, all 124 entries were seen within 11 minutes of their decision; median freshness 60 s.
- **Not connected:** it is not wired into the site's workflow. That needs your explicit authorization. With no candidate it would record events and entries only, with QUALIFIES always false.

## 10. Deliverable G — production safety

- **Changed files:** none outside research.
  - New: `quantum/research/w3liq.py`, `quantum/research/w3shadow.py`, `tests/test_research_w3liq.py`, `tests/test_research_w3shadow.py`, `research/registrations/B31b-W3.json`.
  - Results: `research/results/b31b_w3_development_2026-11-18.json`, `research/results/b31b_w3_recent_2026-11-18.json`, the two events CSVs (distances and labels only, no prices), `research/results/b31b_w3_case_study_2026-11-17_18.json`.
  - Records: this report, 4 lines in `research/trials.jsonl`, a row in `research/README.md`.
- **Unchanged:** the engine, `config.py`, the website, the alerts, the workflows, B9 / B15b / B31b-SHADOW-FWD and B24 (OFF).
  - **Freeze key** after the work: `1f88aad357497da4:4440d52587f5cc6b` (unchanged).
  - **Research isolation:** research code is not imported by production (`tests/test_integrity.py`).
- **W2 untouched:** its findings and files are unchanged.
- **Tests:**
  - `tests/test_research_w3liq.py` 22 and `tests/test_research_w3shadow.py` 5, all passing locally.
  - Mutation: 22 injected bugs, 21 caught, 1 equivalent (a swing level usable on its own confirmation bar cannot be crossed by that bar).
  - Full suite locally: 978 passed (5 min 16 s). GitHub CI results are on the PR; local results are not CI.
- **Reproducibility:** the development run is byte-identical under two different hash seeds and equal to the committed results file. Code `quantum/research/w3liq.py` sha256 `19039a03…`.
- **Data side effect:** three `research-history` runs added the 5-minute series to the `research-data` branch, using the shared Twelve Data key, about 104 of the 800 daily credits. Each run was placed between the website's fetches; the site runs at the time succeeded.
- **Branch and PR:** branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-w3-liquidity`, draft PR, **not merged**. A merge, wiring the shadow module and any alert each need your explicit authorization.

## 11. The directive's ten questions

1. **What is common immediately before an M15 / M30 sweep?**
   - Price works toward a level over 4 bars (0.6–0.7 ATR of momentum) in slightly quieter than average volatility (ATR ratio 0.90).
   - The level is usually a recent swing (72% on M15), less often a previous-session (16%), PD (5%) or equal-high / low (3%) level.
2. **What happens immediately after?**
   - Nothing directional. For the first 15 minutes, the first hour and 4 hours, the move for and against the reversal has the same median ($2 / $4 / $8.5), and directional efficiency is 0.48–0.50.
   - Price is back at the level within 4 hours 81–87% of the time.
3. **What distinguishes a successful from a failed reversal?** Descriptively: higher volatility, a wider crossing bar and more room in both directions. None of it predicted the trade result beyond stop distance.
4. **What distinguishes a genuine from a false breakout?** Descriptively: deeper penetration, a bigger body closing further beyond, several levels taken together. None of it predicted the trade result beyond stop distance.
5. **Which entry has the best net probability of +$10 before the stop?**
   - Highest rate: A-MSS M30 (65.8%), but random entries with its $20 stop reach 65.4%.
   - Least negative: A-MSS M30, −0.038 R.
   - None is above break-even or above random.
6. **+$15 and +$20?**
   - +$15: A-MSS M30 (57.3% vs 55.0% random; −0.002 R).
   - +$20: A-MSS M30 (49.0% vs 46.4%; +0.023 R).
   - Neither is significant. Neither is a candidate (selection was on +$10, as registered).
7. **How many opportunities a week?** 61 M15 and 33 M30 events, 2–17 entries a week per method. None with a measured edge.
8. **Which filters improve results, and which only reduce frequency?** None improved the rate relative to geometry. Room ≥ $10, London / New York only, a displacement bar and HTF agreement either did nothing or selected wider stops, whose higher rate random entries share. All of them only reduce frequency.
9. **Can the $650 maximum loss be respected after costs?**
   - In the plan, always, by sizing.
   - In execution, not always: 1% of stopped trades lost more than $650 through gaps, at worst $3,041.
10. **Out-of-sample advantage over matched random entries?** Not established. No variant beat random even in-sample. Validation was therefore not opened, as registered.

## 12. Limitations

- **Prices:** Twelve Data spot mid prices, not your broker's bid / ask. Costs are modelled, not your broker's.
- **No volume tests:** volume was not tested because the data has none.
- **The 2026 column was read before**, by B31 and W2. Development had been read by earlier studies of related events (B2, B16, B21, B31). W3's definitions are new; its selection used development only.
- **Corrections:** C1 / C2 (class labels) and R1 (label determinism) were made after the first development run. Every trade, model and selection result was identical before and after. All runs are in the trial log.
- **Rates assume one position per method.** Methods overlap in time, so a single account taking several methods would have fewer trades.
