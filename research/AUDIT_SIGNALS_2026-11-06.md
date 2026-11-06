# Signal audit, 3–6 Nov 2026 (Tue 12:00 → Fri 11:20 UTC), and B14

**Operator's request (2026-11-06):** "Audit the signals of last 3 days and improve the strategies."

**Method.**

- The frozen web.8 engine was re-run offline on a copy of the store (`market-data` @ 2026-11-06 11:20).
- Every bar's BUY and SELL entry was traced through the engine's own gates in order: trend, higher-timeframe (HTF)
  gate, session, trigger, then the post-trigger vetoes.
- Everything that fired was measured on the 5-minute path: +$13 / −$13 and +$15 / −$13 within one trading day, with
  the trade_race tie rule. Random 5-minute entries over the same window are the comparison.
- Script: the scratch `audit3d.py`, read-only.

## What the market did

| Trading day | Open | High | Low | Close |
|---|---|---|---|---|
| Tue 3 Nov | 3,905 | 3,969 | 3,899 | 3,930 |
| Wed 4 Nov | 3,930 | 4,070 | 3,920 | 4,061 |
| Thu 5 Nov | 4,062 | 4,148 | 4,058 | 4,089 |
| Fri 6 Nov (to 11:20) | 4,089 | 4,107 | 4,037 | 4,066 |

- A +$249 rally (3,899 → 4,148), then a −$111 pullback.
- Random entries in this window: +$13 first for 62.9% of longs and 37.1% of shorts. At +$15 / −$13: 58.3% and 31.1%.
- Any long won here because of the window's direction. That direction was not known in advance.

## 1. Engine signals: two, then 61 hours of silence

| Alerted signal | Entry | Result (±$13) |
|---|---|---|
| 4h SELL, close 3 Nov 18:00 | 3,932.81 | TP |
| 4h SELL, close 3 Nov 22:00 | 3,930.22 | SL (the rally began) |

The 3 Nov morning SELL cluster (8 SL) was covered in the 5 Nov audit. After 22:00 on 3 Nov, no signal fired on 15m,
30m, 1h or 4h.

**Where every bar stopped (first failing gate):**

| Timeframe | Bars | BUY blocked by | SELL blocked by | Passed all gates |
|---|---|---|---|---|
| 15m | 273 | HTF gate 135, trend 106, session 16, no trigger 16 | trend 233, session 27, no trigger 13 | 0 |
| 30m | 136 | trend 60, HTF gate 57, no trigger 10, session 8 | trend 124, no trigger 8, session 3 | 1 BUY and 1 SELL, both vetoed |
| 1h | 68 | trend 29, HTF gate 27, no trigger 8, session 4 | trend 63, no trigger 4, session 1 | 0 |
| 4h | 17 | trend 12, session 2 | trend 14, session 1 | 3 BUYs, all vetoed (trade quality + calibration) |

- On Wed 4 Nov the 15m bull trend was on for 83 of 92 bars, and the HTF bear gate was on for **all 92**. Every BUY
  was blocked.
- The three vetoed 4h BUYs (4,066.67 / 4,126.27 / 4,102.86) would have reached +$13 first 2 times of 3.
- **Cause:** the HTF gate reads the 4h and daily trend. After a $500+ decline it stays bearish for days into a
  V-shaped recovery. This is by design.
- **The 3-year record says loosening it would not help:**
  - B10-1a: releasing it after a weekly break added 3 signals in 3 years.
  - B14 (below): the A2 condition is not an edge.
  - Tuning the gate to catch this rally would be fitting three days. `CLAUDE.md` forbids that.

## 2. Liquidity alerts: 27 alerts for 7 events

| Event (first timeframe: 15m) | Direction | Entry | ±$13 | +$15 / −$13 |
|---|---|---|---|---|
| BREAK PDH 3,969.20, 4 Nov 05:45 | BUY | 3,982.93 | TP | TP |
| GRAB PDH 4,070.46, 5 Nov 00:00 | SELL | 4,065.17 | SL | SL |
| BREAK PDH 4,070.46, 5 Nov 00:30 | BUY | 4,078.75 | TP | TP |
| BREAK PWH 4,081.97, 5 Nov 00:45 | BUY | 4,090.54 | TP | TP |
| GRAB PWH 4,081.97, 6 Nov 01:30 | SELL | 4,066.37 | TP | TP |
| GRAB PDL 4,058.44, 6 Nov 02:15 | BUY | 4,069.63 | SL | SL |
| BREAK PDL 4,058.44, 6 Nov 03:15 | SELL | 4,053.35 | TP | TP |

- **Per alert** (each timeframe counted): BREAK 14 of 16, GRAB 4 of 10.
- **Per event:** BREAK 4 of 4, GRAB 1 of 3.
- **Over 3 years** (B10, 2020–22, +13 / −13): BREAK 50.3% of 895 and GRAB 49.4% of 913, against 50% random. A
  trending week favours breaks; a ranging week favours grabs.
- The B9 grab test (registered): 3 trades, 1 TP and 2 SL. It reads nothing before 30 results.

## 3. H-setup lines: 48 "entry / SL / TP" lines, net −137 points

| Setup (forward arm) | Trades | +$13 first | Own exits (pts) |
|---|---|---|---|
| 15m H4 | 27 | 11 | −15.9 |
| 30m H4 | 10 | 5 | −8.1 |
| 1h H4 | 4 | 4 | +70.1 |
| 4h H4 | 2 | 2 | −81.5 |
| 15m / 30m H3 | 4 | 1 | −27.7 |
| 4h H6 | 1 | 0 | −74.2 |

- That is 23 of 48 (48%), below the window's long-biased random rate.
- They are registered forward tests, labelled "info, not a DECISION". But each line carries an entry, SL and TP, so it
  reads like a trade call.
- Under web.7, 5m H4 was −0.149 R per trade over 62 trades. No H-setup has a proven edge.

## 4. The trend-change warning (A2)

- It fired once: Thu 5 Nov 07:26 UTC, BUY side. PDH 4,070.46 and PWH 4,081.97 had broken on all four timeframes
  while the gate blocked BUYs.
- From 4,121.78, price reached +$15 before −$13. That is one event.

## 5. B14: is the A2 condition an edge? (registered before code, `research/registrations/B14.json`)

- **Event:** a previous-day or previous-week high (low) broken on both 15m and 1h on the same trading day, while the
  frozen engine's 15m HTF gate blocks that direction.
- **Trade:** in the break's direction, from the 15m close at which both have broken; once per direction per day.
- **Data:** development data, 2020-04 → 2023-01. Results in `research/results/b14_development_2026-11-06.json`; 12
  trial records.

| +$15 / −$13 | n | Target first | 95% range | Random | z | Net / oz at $4,000 (t) | Operator's cost (t) | Verdict |
|---|---|---|---|---|---|---|---|---|
| **B14-a gate ON** | 229 | 48.0% | 41.6–54.5% | 46.3% | +0.52 | −$0.40 (−0.43) | +$0.19 (+0.20) | **FAIL** |
| B14-b gate OFF (secondary) | 395 | 43.8% | 39.0–48.7% | 46.3% | −0.99 | −$1.60 (−2.29) | −$1.00 | — |
| B14-c all (secondary) | 618 | 45.6% | 41.7–49.6% | 46.3% | −0.33 | −$1.08 (−1.93) | −$0.48 | — |

**The A2 condition is not an edge.** It stays a risk warning ("don't fight it"), not an entry. Breaks confirmed on two
timeframes with the gate off did worse than random.

## 6. What was changed (alerts and display only; freeze key `5e4630924d663fc5:a6f2be58c74887ed` unchanged)

1. **One liquidity alert per pool event, across timeframes.**
   - The first timeframe that shows it sends the alert. The others stay in the log for the site and the A2 warning.
   - Pools taken on the same bar in the same direction share one line.
   - Replayed on this window: 27 alerts become 7.
2. **Every GRAB / BREAK alert carries the 3-year base rate** ("2020-22: +$13 before −$13 after a BREAK 50% of 895
   (random 50%)"), so a hot streak is read against the long record.
3. **Every H-setup line carries its forward record**, e.g. "[forward record: 27 trades, 11 won, −15.9 pts]".
4. **A daily ENGINE line, also on silent weekdays.**
   - It gives signals per timeframe and what blocked each side most often, for example:
     "15m 0 signals in 92 bars (BUY blocked by higher-timeframe gate 100%; SELL by trend 100%)".
   - It names the last signal and states that no signal means no trade by the engine's rules.

**Not changed, and why:**

- The engine, its gates and its vetoes. B10 and B14 show the obvious loosening is not an edge, and three days cannot
  justify a change.
- The H-setups' rules (registered forward tests).
- B9-GRAB-FWD.
