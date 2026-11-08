# Phase C: the plan, written before any Phase C code (2026-11-08)

**Branch:** `claude/research-phase-c`, cut from `claude/research-sym15` (B26 / B27). Research only.

**Sources read for this plan:**
- B26 and B27 (`B26_BASELINE.md`, `B27_RESULTS.md`);
- every registration (`registrations/B4..B27`);
- the strategy catalogue;
- the trial log (2,595 lines);
- the research harness and the B19–B27 code.

**Untouched:** web.8, the production engine and config, the frozen Pine reference, the alerts, and PRs #90 / #91.

## 1. What is already known, so it is not repeated

**Two facts frame Phase C.**

1. **At ±$15, 1,192 registered configurations failed (B27); so did 1,186 on a random walk.**
   - The B27 configurations were every single factor, 13 trigger families × 23 entry mechanisms, five calibrated models, and 22 regimes.
   - On a random walk the same framework flagged none of 1,186 configurations, so the framework does not manufacture winners.
2. **On mid prices a fade is the mirror image of the move it fades.**
   - The B26 mirror check: a BUY wins exactly when the SELL from the same bar loses, in 100% of clean pairs.
   - So testing a trigger's direction also tests its fade (one minus the rate, less costs). Fades are not re-run as separate hypotheses.

### Coverage of the 15 Track A hypotheses

| # | Hypothesis | Already tested at ±$15 (or close) | Phase C |
|---|---|---|---|
| 1 | Liquidity sweep then displacement | Sweeps (B16, B21, B27 SWEEP / PD_SWEEP / GRAB) and displacement (B27) separately | **New: the sequence** (a sweep, then a displacement candle reversing it within 4 bars) |
| 2 | BOS and a confirmed MSS | B27 BOS family (the engine's BOS / MSS / CHoCH), 23 entry modes | Covered; not repeated |
| 3 | CHoCH then a retest | B27: structure flip as a condition; BOS family retests | **New: CHoCH_RETEST** (a structure flip, then a limit back at the flip bar's level) |
| 4 | FVG formation and mitigation | B2, B27 (FVG family with a limit at the midpoint; in-FVG condition) | Covered |
| 5 | Order-block reactions | B2, B16, B27 (order-block retest as a condition) | **New: OB_RETEST as a trigger** (a limit at the order block's edge) |
| 6 | PD / PW high and low sweeps | B9, B16, B21, B27 PD_SWEEP | Covered |
| 7 | Asian range expansion | B27 ASIA_BREAKOUT | Covered |
| 8 | London / New York opening behaviour | B4 (session-open momentum, −$10 stop), B13 (first half hour) | **New at ±$15: opening-range breakouts** (London 08:00 local and New York 09:30 local, 30-minute range) |
| 9 | Failed breakouts and traps | B27 FAILED_BREAKOUT | Covered |
| 10 | Trend continuation after a retracement | B27 EMA_PULLBACK | Covered |
| 11 | Contraction then expansion | B1, B27 VOL_EXPANSION | Covered |
| 12 | Multi-timeframe alignment | B6, B14, B17, B26, B27 (1h / 4h / 1D votes) | Covered |
| 13 | Momentum exhaustion and reversal | B1, B20, B27 (candle runs, RSI, returns quintiles, fades by mirror) | **New: reversal candles at a level** (engulfing and pin bar at PDH / PDL, the Asian range, or a 20-bar extreme) |
| 14 | News expansion and post-news | B8, B27 NEWS / POST_NEWS | Covered |
| 15 | Intermarket | B7 (daily, 2020–22); B27 S6 (2026 intraday, descriptive) | Covered (no 2020–22 intraday bars exist) |
| — | Supertrend (section 4C) | Not tested | **New: SUPERTREND** flips (ATR 10, multiplier 3) |

Confirmation distances: B27 tested $3 / 5 / 7 / 10 / 12 / 15 / 20, all flat at about 48%. Phase C uses your list ($3 / 5 / 8 / 10 / 15 / 20) **for the new families only**.

### Track B: what is new

Exits other than ±$15 at the operator's scale were measured before only at −$13 and −$10 / −$20 (B2, B2b, B13, B20). Phase C adds:
- the full TP × SL grid;
- volatility-scaled exits;
- a trend-horizon hypothesis for large brackets;
- conditional models per bracket.

## 2. The arithmetic every TP / SL pair faces (stated before any Track B result)

For a driftless price on mid quotes:
- **Chance of TP first:** SL / (TP + SL).
- **Expected result before costs:** zero.

With bid / ask execution (B26's model), a BUY's levels sit at TP + Δ and SL − Δ in mid terms, where Δ = spread + entry slippage. So:
- **No-information rate:** p₀ = (SL − Δ) / (TP + SL).
- **Break-even rate:** p* = (SL + slippage_out + commission) / (TP + SL + slippage_out).
- **p* > p₀ for every pair.** No choice of TP and SL turns a coin into profit.
- **Expected loss per trade is about constant,** about $0.6–0.8 per oz under the engine cost model, whatever the pair.

The consequences, which Track B can confirm or refute:

1. **A high hit rate is a geometry, not an edge.**
   - +$3 / −$30 gives p₀ = (30 − 0.5) / 33 = **89.4%**, about the 90% target, and loses about $0.6 per oz per trade.
   - At 0.50 lot (ASSUMED 100 oz) that is about −$30 a trade: a 90% win rate that loses money.
2. **Costs hurt small brackets most.**
   - The ~$0.7 loss is 23% of a $3 target but 2% of a $30 target.
   - The least-bad pairs without information are the largest brackets, traded least often.
3. **Profit needs information about direction.**
   - The information must lift the TP-first rate above p* for that pair. Track B asks whether any registered signal does that for any pair.

**Resolution limit, stated in advance.**
- On 15m bars, a small bracket is often touched on both sides inside one bar. That bar is counted as the stop (worst case) and also reported as the target (best case).
- The true rate lies between the two. Where the gap is wide, the 15m result is inconclusive.
- In development, $3 at the 4,000 scale is about $1.35 at 2020 prices, so the problem is worse there.
- The live store's 5m bars (Sep–Nov 2026) give the direct check.
- **Multi-year 5m or 1m data is the dependency** (MT5 M1 export).

## 3. Research architecture

```
data      Twelve Data 15m / 1h 2020-22 (development) and 2026 (check); live-store 5m (Sep-Nov 2026); intermarket 60m (2026)
          validation 2023-01..2024-07 and holdout 2024-07..2026-01: SEALED
features  B22 engine features + B27 additions + B28 new events (all from closed bars; availability = bar close)
labels    B26 trade: fill at the next open (ask / bid), triggers on the exit side, gap and same-bar rules, 2-day limit,
          closure exits; costs GROSS / OP ($0.26) / ENG (engine model, primary) / ADV
Track A   B28: 8 new trigger families x {immediate, confirm $3/5/8/10/15/20, retest, stop, structure limit}, +-$15
Track B   B29: G  TP x SL grid on every bar (101 pairs), theory check, 15m bounds, 5m check
               V  ATR-scaled brackets (25 pairs)
               M  time-series momentum (20 / 60 days) for large brackets
               C  a calibrated model per bracket (7 brackets, purged walk-forward)
               E  21 trigger families x 7 brackets, immediate entry
selection development only; matched random (same direction, session, month); BH within each study; n >= 300
check     the frozen best per study on 2026 (Holm); nothing selected on 2026
outputs   three leaderboards (A: +-$15, B: dynamic, C: risk-adjusted across both, labelled); trade CSVs; the trial log
```

## 4. Data limits (not substituted)

| Limit | Effect on Phase C |
|---|---|
| No broker specification | Money at 0.50 lot is ASSUMED (100 oz, $7 per lot commission) |
| No broker bid / ask | Spreads are modelled ($0.30 in session, $0.50 off; $0.26; adverse 2×). No tick data, so tick velocity, acceleration and intrabar sequence are NOT TESTED; they are not derived from OHLC. |
| No traded volume (Twelve Data); no order flow or depth | VWAP / volume profile / aggressor proxies are NOT TESTED. CME GC trades were tested in B5 (no edge); depth was never available. |
| 5m history only Sep–Nov 2026 | 5m execution is checked there only; small Track B brackets carry 15m resolution bounds |
| Intraday intermarket bars only from 2023-12 / 2024 | 2026 descriptive only (B27 S6) |
| No dated news list for 2023-02 → 2026-10 | News labels there are NOT DATED |

**Not done without your decision:** fetching multi-year 5m history from Twelve Data. The `research-history` workflow can do it, but it shares the API key, and its daily credits, with the production site. A heavy history fetch could starve the site's live data and so the web.8 forward test.

## 5. Pass / fail (the same rules for both tracks)

| Tier | Rule |
|---|---|
| **INFORMATIVE** | Benjamini–Hochberg significant within its study, Wilson 95% lower bound above the matched random rate (same bracket, direction, session and month), and at least 300 independent trades |
| **TRADEABLE** | INFORMATIVE, the lower bound above that bracket's break-even, and positive expectancy (ENG costs) |
| **HOLDS ON 2026** | Frozen, the same test against 2026's matched random, Holm across all frozen candidates |

**Next step for a pass.** Only a candidate that is TRADEABLE and HOLDS goes forward, as a single registered hypothesis for the sealed validation period. Opening that period needs your approval. A forward shadow test comes after it.

**Direction signals (Track B M).** For signals that predict direction over weeks, a same-month baseline already contains the month's realised drift. It would absorb exactly the effect being tested. Those are compared with a **direction-neutral** random baseline (the mean of BUY and SELL in the same session and month), and that is registered in advance.
