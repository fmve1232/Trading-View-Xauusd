# Phase B10: the lagging higher-timeframe gate and regime-matched liquidity alerts (development data, 2026-11-05)

**Verdict.**

- **B10-1a is INSUFFICIENT.**
- **B10-2a and B10-2b FAIL.**
- None supports an engine or alert change.

The rules were registered in `research/registrations/B10.json` before any code or data, and the operator approved
them on 2026-11-05 ("approve B10"). The code is `quantum/research/b10.py`. The results are in
`research/results/b10_development_2026-11-05.json`, and the 18 trials are in `research/trials.jsonl` (phase `B10`).

| Primary (15min, Holm over three) | n | +13 first | 95% range | Random, same directions | z | Mean net / oz | t | Verdict |
|---|---|---|---|---|---|---|---|---|
| B10-1a: signals added by releasing the HTF gate after a weekly break | 3 | 33.3% | 6.1–79.2% | 49.3% | −0.55 | −$2.42 | −0.58 | **INSUFFICIENT** (fewer than 30) |
| B10-2a: GRAB in RANGE / COMPRESS | 394 | 49.7% | 44.8–54.7% | 49.8% | −0.00 | −$0.42 | −1.42 | **FAIL** |
| B10-2b: BREAK in STRONG TR / EXPANSION | 540 | 52.4% | 48.2–56.6% | 49.9% | +1.18 | −$0.10 | −0.39 | **FAIL** |

**Settings.**

- Development partition: 2020-01-24 → 2023-01-24, scored from 2020-04-01.
- Outcome: +13 / −13 at $4,000, scaled by entry / 4000, on 15-minute bars for one trading day.
- Break-even after costs: about 53.3%, from the frozen model's cost ($0.77 per oz in session, $0.97 off session at $4,000; see the erratum).

## What it means

**B10-1a: the gate is rarely what binds.**

- Releasing the bear gate after a weekly break freed it on about 39% of the 70,173 bars (27,341 / 23,042 for the two
  gates).
- But it added only 3 signals in three years on 15m, and none on 1h.
- On this data the other entry conditions (trend score, session quality, structure trigger, vetoes) almost always bind
  first.
- On 4–5 Nov 2026 the gate did bind: it was on for 103 of 119 bars. That was one rally after a $500 fall, with the live
  engine's macro inputs, which this data lacks.
- A faster gate would not have changed the engine's history, so **no engine amendment is proposed**.
- The daily-break variant (B10-1b, secondary) added 8 signals, 5 of them winners. That is too few to mean anything.

**B10-2a and B10-2b: matching the alert to the regime does not create an edge.**

- Over three years, sweeps reverted no more often than random, in ranges (49.7%) or overall (49.4%).
- Breaks continued no more often than random, in trends (52.4%) or overall (50.3%). Neither covers costs.
- The live window's contrast (BREAKs 3 of 3 during the November rally; B9-explore GRABs 61.7%) was the regime of the
  moment, not a property of the setups.
- The B9-GRAB-FWD live test continues unchanged, as registered. The prior evidence for it is now weaker.

## Secondary results (reported, not decisive)

| 15min | n | +13 first | 95% range | Random | z | Mean net / oz | t |
|---|---|---|---|---|---|---|---|
| The engine's own signals (no macro inputs) | 70 | 64.3% | 52.6–74.5% | 49.5% | +2.47 | +$1.34 | +1.93 |
| … with the weekly release | 70 | 65.7% | 54.0–75.8% | 49.5% | +2.71 | +$1.52 | +2.21 |
| … with the daily release (B10-1b) | 75 | 66.7% | 55.4–76.3% | 49.5% | +2.97 | +$1.63 | +2.47 |
| GRAB, all regimes | 913 | 49.4% | 46.2–52.6% | 49.8% | −0.23 | −$0.45 | −2.32 |
| BREAK, all regimes | 895 | 50.3% | 47.0–53.5% | 49.9% | +0.24 | −$0.36 | −1.85 |

| 1h | n | +13 first | 95% range | Random | z | Mean net / oz | t |
|---|---|---|---|---|---|---|---|
| The engine's own signals | 25 | 40.0% | 23.4–59.3% | 50.1% | −1.01 | −$1.70 | −1.40 |
| GRAB in range / all | 371 / 824 | 49.1% / 48.3% | | 49.8% | | −$0.49 / −$0.57 | |
| BREAK in trend / all | 336 / 793 | 50.0% / 49.9% | | 49.9% | | −$0.37 / −$0.39 | |

**The engine's 15m signal stream is the one figure that stands out:** 64.3% against 49.5% random on 70 trades. It is
**not evidence of an edge**, for four reasons:

1. It is a secondary measure among 18 here.
2. On 1h the same engine did 40% (25 trades).
3. This version runs without the macro, volume and cross-asset inputs the live engine uses, so it is not the live signal
   stream.
4. On the live window, the live engine's 15m signals did 31.8% (22 trades; B9-explore).

It can only become a hypothesis through its own registration, and then on the sealed validation partition.

## Interpretation note (fixed before any outcome was read)

The registration says the release starts "from the first bar whose close is above the previous week's high". The code
reads this as a close from below: the previous close at or below the level. So after a release ends (the 5-day cap or
the opposite close), a new release needs a new break. Without this, the cap would not bind while price stays above the
level. The change was made when a unit test exposed the ambiguity, before the study read any outcome.

## Erratum (audit, 2026-11-05; verdicts unchanged)

- **The "Mean net / oz" columns, and `mean_net_usd_at_4000_per_oz` / `usd_per_trade_0p5lot_at_4000` in the results
  file, are in 2020–2022 dollars, not dollars at $4,000.** `b10.outcomes` multiplies both the distances and the cost by
  entry / 4000. At 2020–2022 prices that factor is about 0.45, so the figures at $4,000 are about 2.2 times larger.
  For example, the engine's 15m signals at +$1.34 are about +$3.0 per oz at $4,000.
- Every verdict stands: the registration's P2 is the t-statistic of these scaled dollars ("mean net result per trade > 0 (scaled $, after costs)"), so only the labels were wrong.
- **The break-even note was wrong.** Scaling the cost keeps its share of the distances the same. The 53.3% comes from
  the frozen engine's cost model (`harness.cost_pts`: $0.77 / $0.97 per oz at $4,000). The operator's measured round
  trip is $0.26, which gives (13 + 0.26) / 26 = 51.0%.
- B13 reports net results in dollars at $4,000 with both costs.
