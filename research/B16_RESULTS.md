# B16: the operator's level rules (sweeps and breakouts with order blocks, volume profile and POC), +$15 after the alert

**Request (operator, 2026-11-06).** Use the previous day, week and month highs and lows, today's high and low, and the
4-hour and 1-hour candle highs and lows. Combine them with liquidity sweeps, order blocks, the volume profile and the
POC. Send an alert that follows the rules strictly, with at least +$15 of movement after it.

**Registration.** `research/registrations/B16.json` was committed before any code (4551e7a4b). Its amendment was
committed before any outcome (88b07cb7f): the development data carry no volume, so the profile is time-at-price.

**Code.**

- The rules are in `quantum.notify.setup_levels` / `setup_events`, the same functions the live alerts use.
- The test is `quantum/research/b16.py`.
- Results are in `research/results/b16_development_2026-11-06.json`; trial records are in `research/trials.jsonl`
  (phase `B16`).

## Verdict: both rules FAIL

| +$15 before −$13 (2020-04 → 2023-01, 15m) | Trades | Target first | 95% range | Random, same mix | z | Net / oz at $4,000 (t) | Operator's cost |
|---|---|---|---|---|---|---|---|
| **SWEEP** (level swept, closed back, at an order block / value-area edge / POC) | 5,918 | 46.6% | 45.3–47.8% | 46.2% | +0.54 | −$0.83 (−4.57) | −$0.22 |
| **BREAKOUT** (close beyond a level, outside the value area, not into an opposing order block) | 6,729 | 46.1% | 44.9–47.3% | 46.3% | −0.23 | −$0.93 (−5.46) | −$0.35 |

**Secondary results:**

- **+$13 before −$13:** sweeps 50.2%, breakouts 49.4% (random 49.8%).
- **+$20 before −$13:** 40.2% and 39.1% (random 39.0%).
- **"At least $15 after the alert", ignoring the stop:**
  - sweeps 64.7%, breakouts 65.4%;
  - random entries 66.4% (long) and 63.7% (short).
  - A $15 move within the day happens about two times in three after **any** entry. It usually comes after the −$13
    stop would have been hit, so it is not an edge.
- **By level:** no group stands out from noise. The largest gaps are on the smallest samples, e.g. month-low
  breakouts 12 of 18 and month-low sweeps 2 of 8. Picking them now would be selection after the fact.
- **By zone:** order-block sweeps 40–49% (n 60 / 85); POC 47.0% (n 2,236); value-area edge 46.3% (n 3,537).

**How often the rules fire:** 12,785 setups in 2.8 years, about 18 a trading day. Most come from the 1h, 4h and
today's highs and lows. The previous day, week and month levels alone give about 1–2 a day.

## What happens now (as registered)

The alerts go out anyway, because the operator asked for them:

- **What triggers one:** a 15m SETUP alert per qualifying bar and direction.
- **What each alert shows:**
  - the levels, the zone and the entry;
  - SL −$13, TP1 +$13 (close half, SL to entry), the +$15 mark and TP2 +$20;
  - the MT5 line;
  - this 3-year record and "information, not a confirmed signal".
- **Live record:** each setup is scored +$15 before −$13 in `research_forward/SETUP-LIVE.json`, which is copied to
  forward-ledger. That record is separate from the engine test (B15).
- **Variables:** `SETUP_LEVELS=major` keeps only the previous day, week and month levels; `ALERT_SETUPS=0` turns the
  alerts off.
- **No validation opening:** neither primary passed. No re-run with changed levels, zones, tolerances or targets.
