# B18: the operator's 4h candle breakout with all four confirmations (2026-11-06)

**Request (operator):** "quality trades with confirm movement of market at every 4h candle confirmation … strictly
follow my instructions". The operator chose a **4h candle breakout alert** with **all four** confirmations.

**Registration:** `research/registrations/B18.json`, committed before any code (5c805e8d1).

**Code:**

- Rule: `quantum.notify.h4_events`, shared with the live alert.
- Test: `quantum/research/b18.py`.
- 3-day recalculation: `research/tools/b18_recalc_window.py`.
- Results: `research/results/b18_development_2026-11-06.json` and `b18_recalc_2026-11-03_06.json`.
- Trial records: `research/trials.jsonl` (phase `B18`).

**The rule, checked at each 4h close (17:00 New York session grid):**

- **Breakout:** BUY when the candle closes above the previous 4h high; SELL when it closes below the previous 4h low.
- **Confirmations, all required:**
  1. **Level:** the close is beyond a previous day, week or month high (BUY) or low (SELL).
  2. **Trend:** all three trend votes agree at the close.
  3. **Engine:** the engine's own bias on the 4h candle agrees.
  4. **Session:** the candle closes in London or New York hours.

## The ladder (2020-04 → 2023-01, +$15 before −$13 from the 4h close)

| 4h breakouts | n | Target first | 95% range | Random | z | Net / oz at $4,000 (t) |
|---|---|---|---|---|---|---|
| Every 4h breakout | 1,995 | 46.6% | 44.4–48.8% | 46.3% | +0.26 | −$0.82 (−2.61) |
| + beyond a day / week / month level | 1,074 | 46.7% | 43.8–49.7% | 46.3% | +0.28 | −$0.76 |
| + trend 3 of 3 | 620 | 46.9% | 43.0–50.9% | 46.3% | +0.30 | −$0.71 |
| + engine bias | 524 | 46.4% | 42.1–50.7% | 46.3% | +0.05 | −$0.87 |
| **+ London / New York = all four** | **319** | **45.8%** | **40.4–51.3%** | 46.2% | −0.17 | −$0.96 (−1.22) |

**Verdict: FAIL.**

- **No step helps:** on 4h candles the confirmations add nothing.
- **Other targets, all four confirmations:**
  - +$13 before −$13: 50.3% of 322 (random 49.8%);
  - +$20 before −$13: 39.4% (random 39.0%);
  - "$15 at any time in the day": 67.1%.
- **Frequency:** about 114 a year, roughly 2 a week.
- **Another baseline:** random entries at 4h closes reached +$15 first 47.3% of the time (long) and 45.4% (short).

## Recalculation on the last 3 days (live engine on the site's 4h bars; descriptive)

- **4h breakouts:** 9. Five reached +$15 first, four of them BUYs in the 4–5 Nov rally.
- **With all four confirmations:** none.
  - The trend vote lagged the 4–5 Nov rally, so all five BUYs then failed the trend check.
  - The only breakout with trend 3 of 3 (Fri 6 Nov 10:00 BUY) failed the level and engine checks and hit the stop.
- Three days are far too few to judge.

## What changed (display only; freeze keys unchanged)

- **In quality mode (the default), the phone's setup alerts are now these 4h breakouts with all four confirmations,**
  checked at every 4h close.
- **Each alert shows:**
  - the candle, the previous 4h high or low, and the levels it closed beyond;
  - the four confirmations;
  - entry, SL −$13, TP1 +$13 (half), +$15 and TP2 +$20;
  - the MT5 line;
  - this record.
- **The 15m setups** (B16 / B17) stay on the website and in the records. Engine signals and their follow-ups still go
  to the phone.
- **Records:** every 4h breakout, confirmed or not, is scored +$15 before −$13 in `research_forward/SETUP-LIVE.json`.
- **No validation opening:** the rule failed. No re-run with changed candles, confirmations or targets.

**Later the same day (operator, "Yes please"):** the 15m setups with all four confirmations went back to the phone,
beside the 4h breakouts. B17 measured them at 51.6% of 184 (random 46.3%, p 0.07): better than this rule, still not proven.
