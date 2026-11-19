# B31b-W4 results: pullback continuation, reversal, breakout-retest and entry timing

**Verdict: NO CANDIDATE. NO TRADE stays.** None of the 15 registered entry methods beats its matched random control
at +$10 after costs on the development period (smallest one-sided p = 0.147; Holm-adjusted p = 1.00 for all 15), and
14 of 15 have a negative mean net R. Directional entries stay disabled; nothing here is wired to alerts or shadow, and
validation (2023-24) and holdout (2024-25) stay sealed.

- Registration: `research/registrations/B31b-W4.json` (commit cada883c4, before any code), amendment A1 before any run
  (commit b6f15f44d). Code: `quantum/research/w4pull.py` (sha256 f974c75e...), measuring through W3's own
  `w3liq.execute` / `w3liq.matched_random` (fills, $650 sizing, cost rule, +$10 / +$15 / +$20 races, M5 ambiguity, gap
  losses). One development run, logged in `research/trials.jsonl`.
- Data: Twelve Data spot XAU/USD, development partition 2020-03-09 .. 2023-01-24 (67,332 scored 15m bars, M5 coverage
  99.2%, data hash f113f97ad2105ff9). M30 context: bearish 15.1% of bars, bullish 18.5%, none 66.4%.
- Distances are in $ at $4,000 (a historical move scaled by price / 4,000, as in W3).

## 1. Every method (pooled over both directions: the registered test)

| Method | What | n | +$10 first | Random | p (raw) | Holm p | Mean net R [95%] | +$15 | +$20 | PF | Max DD | Median stop | Loss > $650 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| A1 | zone rejection close | 226 | 52.2% | 49.3% | 0.196 | 1.00 | -0.053 [-0.18, +0.06] | 42.9% | 36.3% | 0.89 | $14,149 | $9.03 | 1 of 108 |
| A2 | EMA band + displacement | 251 | 57.8% | 54.4% | 0.147 | 1.00 | -0.027 [-0.13, +0.08] | 48.6% | 41.8% | 0.94 | $10,872 | $11.74 | 2 of 106 |
| A3 | M5 MSS after the approach | 172 | 49.4% | 53.7% | 0.864 | 1.00 | -0.122 [-0.26, +0.01] | 40.7% | 33.7% | 0.76 | $16,193 | $9.72 | 1 of 86 |
| A4 | retest limit at the broken level | 46 | 39.1% | 43.5% | 0.719 | 1.00 | -0.125 [-0.45, +0.24] | 34.8% | 32.6% | 0.80 | $5,679 | $6.60 | 0 of 28 |
| A5 | sweep of the pullback high + displacement | 132 | 50.8% | 51.7% | 0.581 | 1.00 | -0.076 [-0.24, +0.08] | 41.7% | 34.1% | 0.84 | $12,990 | $10.29 | 0 of 65 |
| A6 | failed reclaim of the broken level | 252 | 48.8% | 50.9% | 0.738 | 1.00 | -0.132 [-0.24, -0.03] | 41.3% | 33.7% | 0.74 | $23,996 | $9.79 | 0 of 129 |
| T1 | early limit at the approach | 114 | 46.5% | 42.8% | 0.216 | 1.00 | +0.061 [-0.16, +0.28] | 37.7% | 32.5% | 1.11 | $6,470 | $7.04 | 0 of 61 |
| T4 | next M15 close after A1 | 147 | 51.7% | 54.2% | 0.725 | 1.00 | -0.121 [-0.27, +0.02] | 44.2% | 36.1% | 0.75 | $13,839 | $11.47 | 0 of 71 |
| T6 | limit at A2's displacement midpoint | 151 | 49.7% | 50.8% | 0.609 | 1.00 | -0.106 [-0.26, +0.04] | 39.1% | 36.4% | 0.79 | $15,496 | $9.39 | 3 of 76 |
| B1 | sweep + reclaim close | 387 | 43.7% | 45.2% | 0.724 | 1.00 | -0.137 [-0.23, -0.04] | 35.1% | 29.5% | 0.76 | $35,902 | $7.84 | 4 of 218 |
| B2 | reclaim + displacement | 187 | 57.8% | 57.8% | 0.505 | 1.00 | -0.053 [-0.17, +0.06] | 46.0% | 39.0% | 0.88 | $11,242 | $13.63 | 1 of 79 |
| B3 | reclaim + M15 MSS | 294 | 59.2% | 57.5% | 0.283 | 1.00 | -0.051 [-0.16, +0.05] | 49.3% | 41.8% | 0.87 | $11,321 | $14.29 | 1 of 120 |
| B4 | higher low after the MSS | 134 | 45.5% | 49.1% | 0.793 | 1.00 | -0.160 [-0.33, +0.00] | 37.3% | 27.6% | 0.71 | $15,984 | $9.40 | 0 of 73 |
| C1 | break, acceptance, retest rejection | 528 | 45.8% | 45.4% | 0.418 | 1.00 | -0.095 [-0.20, +0.00] | 37.5% | 29.7% | 0.83 | $39,650 | $7.65 | 5 of 286 |
| C2 | C1 with the M30 context | 133 | 46.6% | 47.4% | 0.567 | 1.00 | -0.104 [-0.28, +0.06] | 39.1% | 35.3% | 0.81 | $16,562 | $8.14 | 0 of 71 |

Funnel (orders → eligible): most rejections are the cost rule (cost must be <= 15% of the stop distance). The
structure-based stops are often only $3-6, so the spread + commission eat the trade: A4 (retest limit) kept 46 of 585
orders, T1 114 of 585, C1 547 of 1,884, B1 430 of 1,426.

## 2. Direction split (descriptive only: NOT a registered test, and 30 cells)

| Direction split (descriptive, NOT a registered test) | d = -1 (short) | d = +1 (long) |
|---|---|---|
| A1 | n 94, 59.6%, +0.073 [-0.12, +0.26] | n 132, 47.0%, -0.142 [-0.30, +0.03] |
| A2 | n 101, 56.4%, -0.096 [-0.25, +0.06] | n 150, 58.7%, +0.020 [-0.13, +0.16] |
| A3 | n 74, 48.6%, -0.165 [-0.36, +0.04] | n 98, 50.0%, -0.089 [-0.27, +0.09] |
| A4 | n 28, 46.4%, +0.068 [-0.37, +0.53] | n 18, 27.8%, -0.424 [-0.86, -0.00] |
| A5 | n 56, 37.5%, -0.325 [-0.55, -0.10] | n 76, 60.5%, +0.107 [-0.10, +0.32] |
| A6 | n 110, 55.5%, -0.010 [-0.16, +0.15] | n 142, 43.7%, -0.226 [-0.36, -0.09] |
| T1 | n 59, 44.1%, -0.041 [-0.31, +0.24] | n 55, 49.1%, +0.171 [-0.14, +0.48] |
| T4 | n 71, 56.3%, -0.047 [-0.24, +0.15] | n 76, 47.4%, -0.190 [-0.38, +0.01] |
| T6 | n 67, 47.8%, -0.150 [-0.37, +0.07] | n 84, 51.2%, -0.072 [-0.29, +0.13] |
| B1 | n 195, 44.1%, -0.123 [-0.27, +0.04] | n 192, 43.2%, -0.152 [-0.28, -0.02] |
| B2 | n 115, 56.5%, -0.060 [-0.21, +0.10] | n 72, 59.7%, -0.040 [-0.21, +0.14] |
| B3 | n 154, 59.1%, -0.041 [-0.19, +0.11] | n 140, 59.3%, -0.063 [-0.19, +0.09] |
| B4 | n 69, 43.5%, -0.184 [-0.44, +0.04] | n 65, 47.7%, -0.135 [-0.36, +0.10] |
| C1 | n 236, 42.8%, -0.155 [-0.31, -0.01] | n 292, 48.3%, -0.046 [-0.17, +0.07] |
| C2 | n 54, 42.6%, -0.175 [-0.42, +0.07] | n 79, 49.4%, -0.055 [-0.27, +0.17] |

The operator's specific case, **bearish continuation after a pullback into the breakdown zone (A1, short)**: n = 94,
+$10 first 59.6%, mean net R +0.073, 95% CI [-0.12, +0.26]. The interval includes zero, the cell was not pre-specified,
and the pooled registered test (A1: 52.2% vs 49.3% random, p = 0.196) is not significant. This is not evidence of an
edge; at most it is a hypothesis that would need its own registration and the sealed periods.

## 3. Early vs late confirmation (operator section 7), paired on the same Module A episodes

| Compared with A1 (first rejection close) | Paired episodes | Mean net R difference [95%] | Entry better by (median) | +$10 first: A1 / it |
|---|---:|---|---:|---|
| T1 early limit at the approach | 74 | +0.039 [-0.24, +0.31] | $-1.41 | 40 / 32 |
| A3 M5 MSS | 76 | -0.326 [-0.53, -0.12] | $+5.98 | 48 / 40 |
| T4 one more M15 close | 106 | -0.346 [-0.47, -0.23] | $+3.16 | 77 / 63 |
| A4 retest limit | 35 | -0.118 [-0.43, +0.22] | $-3.30 | 19 / 13 |
| A2 EMA + displacement | 127 | -0.131 [-0.31, +0.05] | $+2.06 | 80 / 78 |
| T6 displacement midpoint | 83 | -0.140 [-0.37, +0.09] | $-0.83 | 49 / 44 |
| A5 sweep of pullback high | 62 | +0.167 [-0.10, +0.44] | $-0.16 | 30 / 37 |
| A6 failed reclaim | 176 | -0.011 [-0.09, +0.06] | $+0.00 | 86 / 85 |

- **Waiting costs money.** One more M15 close after the rejection (T4) costs -0.35 R [-0.47, -0.23]; waiting for an M5
  structure break (A3) costs -0.33 R [-0.53, -0.12]. Both get a "better looking" confirmation and a worse trade: the
  stop is still beyond the pullback extreme, so the extra distance comes straight out of the reward.
- Entering earlier (T1, a limit at the approach) is no different from the first rejection close (+0.04 R
  [-0.24, +0.31]); its stop is tighter, so 443 of its 585 orders fail the cost rule.
- This matches B30 / W3: on this data, confirmation buys certainty about the past, not about the next $10.

## 4. Bullish reversal vs short-covering bounce vs continuation (Module B taxonomy)

1,426 sweeps against the M30 trend (a low swept and reclaimed in a bearish context, or the mirror), followed for 96 bars
(future data, descriptive only, never a feature):

| What followed | Events | Share |
|---|---:|---:|
| Continuation (a close beyond the sweep extreme before a 1 x ATR bounce) | 730 | 51% |
| Short-covering bounce (1 x ATR bounce, then a close beyond the sweep extreme) | 485 | 34% |
| Genuine reversal (1 x ATR bounce, the extreme holds, an M30 structure flip) | 210 | 15% |
| Failed breakdown (1 x ATR bounce, the extreme holds, no M30 flip) | 1 | 0% |

A reclaim against the trend is more often a pause than a turn; none of B1-B4 (reclaim close, + displacement, + MSS,
higher low) separates the 15% from the rest well enough to beat random after costs.

## 5. The 18 Nov screenshots, reconstructed point in time (deliverable 1)

`research/results/b31b_w4_reconstruction_2026-11-18.json` (`quantum/research/w4recon.py`): zones rebuilt by
`quantum/keyzones.py` (the live rules) from the bars closed at each decision time. MT5 server time = UTC + 2.

- **Price alignment.** The screenshots show 3729.54 (M15) and 3728.85 (M30) at about 20:52-20:57 UTC (22:52-22:57 MT5).
  Twelve Data traded 3728.20-3731.26 in the 20:50 M5 bar and 3730.18 at 20:55: the feed and the broker agree to about
  $1 at that time (one observation, not a calibration of the offset).
- **Every visual zone is reproduced from data known at 20:45 UTC**, within $0.0-2.8 of its midpoint:

| Operator's zone | Data zone at 20:45 UTC | What built it | State at 20:45 |
|---|---|---|---|
| 3720-3725 | 3719.19-3721.53 | 15m swing low 3719.19 (pivot 19:30, known 20:30) | FRESH |
| 3728-3734 | 3729.40-3734.17 | 15m swing low 3729.40 (17:45), broken at 19:15 | BROKEN (now resistance; price inside) |
| 3741-3749 | 3740.17-3746.12 and 3747.02-3750.66 | 15m / 30m / 1h swing low 3742.26 (pivot 12:45, known 13:45) + swing high 3743.22; swing high 3750.66 (17:15) | INVALIDATED; FRESH |
| 3756-3765 | 3757.39-3763.66 | 15m / 30m / 1h swing low 3757.39 (08:15) | INVALIDATED (10 visits, 3 acceptances) |
| 3772-3780 | 3771.18-3775.31 and 3779.46-3782.83 | Asia low 3774.48 + swing high 3773.41; swing lows 3779.46 / 3781.06 | INVALIDATED |
| 3787-3794 | 3782.83-3793.68 and 3793.68-3797.08 | London high 3789.10 + 1h swing high + swing low 3790.28; swing high 3797.08 | BROKEN; FRESH |

  What the picture does not show: four of the six areas had already been traded through twice that day (INVALIDATED),
  i.e. they were not holding as support / resistance any more.
- **The day, candle by candle (UTC):** Asia sell-off 3852 → 3790 (00:00-02:00, six bars >= 1.5 ATR); lower lows at 03:45
  (below 3790.28) and 06:15 (below 3779.46); 08:00 drop to 3759.40; 12:30 close below 3757.39, **reversed by a 3.2 ATR
  bar at 13:00 (3745.50 → 3771.20, range $27.68)**, and the 13:30 bar closed above the 3773.41 swing high (3783.66, high 3784.80); lower high 3789.10 at 13:45; close
  below 3742.26 at 16:30; lower high 3750.66 at 17:15; close below 3729.40 at 19:15; low 3719.19 at 19:35; the bounce to
  3732.74 (20:40) is the screenshot.
- **Why no registered entry fired at the screenshot:** the M30 context was NONE, not bearish. The last two confirmed M30
  swing highs were 3786.59 → 3789.10, a *higher* high made by the 13:00 short-covering spike, so the M30 structure was
  not LH / LL even though price kept making lower lows. Module A needs a bearish M30 context.
- **Remaining opportunity at 3729.54 (section 6), from the zones known then; no probability is shown because none is
  calibrated:**

| Plan | Stop (beyond the structure + 0.2 ATR) | Stop distance | Lots at $650 | +$10 / +$15 / +$20 | Opposing liquidity |
|---|---|---:|---:|---|---|
| SELL 3729.54 | 3735.84 (above 3729.40-3734.17) | $6.30 (cost 12% of it) | 0.91 | 3719.54 / 3714.54 / 3709.54 | +$10 lands inside the FRESH 3719.19-3721.53 support; +$15 / +$20 need a new low |
| BUY 3729.54 | 3717.52 (below 3719.19) | $12.02 | 0.50 | 3739.54 / 3744.54 / 3749.54 | BROKEN 3734.17-3735.47 at +$4.6, then 3740.17-3746.12 |

- **What happened next (hindsight, one case, not evidence):** price rose to 3758.13 by 01:00 UTC on 19 Nov, then fell
  to 3695.08 by 03:00. The SELL would have been stopped at 23:05 UTC (just after the daily reopen) before its targets
  were touched at 02:55; the BUY would have reached +$10 at 23:20, +$15 at 00:25 and +$20 at 00:35. The bounce from
  3720-3725 was a short-covering rally of about $28 before the next leg down.

## 6. 17-18 Nov case study, trade by trade (descriptive; recent period, overlaps the live forward test)

`research/results/b31b_w4_case_study_2026-11-17_18.json` (market-data store bars). Times UTC (MT5 = +2 h).

| Decision | Method | Side | Entry | Stop | Stop distance | Lots | +$10 / +$15 / +$20 |
|---|---|---|---:|---:|---:|---:|---|
| 17 Nov 02:15 | C1 | BUY | 3869.05 | 3858.10 | $11.33 | 0.52 | TP / TP / SL |
| 17 Nov 06:00 | C1 | BUY | 3881.00 | 3877.06 | $4.06 | — | rejected: cost > 15% of the stop |
| 17 Nov 13:45 | T1 / A4 (limits) | SELL | 3850.92 / 3852.76 | 3857.77 | $7.11 / $5.20 | 0.82 / 1.08 | SL / SL / SL (both) |
| 17 Nov 16:00 | A2 | SELL | 3875.84 | 3893.43 | $18.15 | 0.34 | TP / TP / TP |
| 17 Nov 19:45-20:00 | A1 / A6 / T4 | SELL | 3849.42 / 3849.42 / 3846.80 | 3893.43 / 3864.57 / 3893.43 | $45.73 / $15.74 / $48.49 | 0.13 / 0.39 / 0.13 | TP / TP / TP |
| 18 Nov 12:45 | T1 / A4 (limits) | SELL | 3755.30 / 3757.39 | 3763.62 | $8.86 / $6.63 | 0.67 / 0.87 | SL / SL / SL (both) |
| 18 Nov 15:15 | A1 / A2 / A6, T6 | SELL | 3755.87, 3760.39 | 3782.54-3790.77 | $23.57-37.18 | 0.17-0.26 | TP / TP / TP |
| 18 Nov 15:45 | C1 | SELL | 3755.22 | 3763.82 | $9.16 | 0.65 | TP / TP / TP |
| 18 Nov 18:15 | C1 | SELL | 3736.14 | 3744.74 | $9.21 | 0.65 | TP / TP / SL |

Two strongly trending days make several continuation entries look good; the wide-stop ones (A1 / T4, $45-48) earn only
0.2 R at +$10. Three years of development data say the same entries do not beat random: a visually attractive chart
is not a statistical edge.

## 7. Risk notes (section 10)

- Realised loss beyond the $650 plan through gaps on these entries: 18 of 1,577 stopped trades across the 15 methods (counted per method, after one position at a time)
  (worst per method in the JSON). The live GAP RISK line (PR #129) discloses this on every ENTRY ELIGIBLE alert.
- 100 oz per lot is ASSUMED in all sizing; it must be checked against the broker's contract specification.
- Costs are the research model (session spread + slippage + commission), not the broker's.

## 8. Limits

Development period only (2020-23); a different regime from 2026. Spot feed without volume. Module B overlaps W3's
engine A and Module C W3's engine B (disclosed in the registration). The direction split, the session table and the
case study are descriptive and were not part of the test. No parameter was tuned; every value was fixed before the run.

## Verification

- `tests/test_research_w4pull.py` (14 tests): a hand-worked bearish episode (A1 / T4 / A4 / T1 orders and fills), A6 and T4
  negatives, A3 on crafted M5 bars, Module C's retest after the acceptance bar, the break judged only with swings known
  before it, the taxonomy (incl. a same-bar tie), Holm, the M30 context, the reconstruction's point-in-time property,
  and an exhaustive truncation check: every order on two seeded M5 / M15 walks is rebuilt identically from the bars
  closed by its own decision (M5 included).
- Mutation test: 10 of 12 mutants killed. The two survivors: "A3 compares with the M5 pivot confirmed on the next bar"
  is equivalent (the bar confirming a pivot low has its low above it, so its close cannot be below it); "approach
  distance ignored" is equivalent for A1 / T4 (A1's bar must enter the zone anyway) and only moves A3's 2-hour window.
- Full suite on this branch: 1,011 passed (local run, not CI).

## Files

`research/registrations/B31b-W4.json`, `quantum/research/w4pull.py`, `quantum/research/w4recon.py`,
`tests/test_research_w4pull.py`, `research/results/b31b_w4_development_2026-11-19.json`,
`research/results/b31b_w4_trades_development_2026-11-19.csv` (8,018 orders, no prices),
`research/results/b31b_w4_case_study_2026-11-17_18.json`, `research/results/b31b_w4_reconstruction_2026-11-18.json`.

Reproduce: `python -m quantum.research.w4pull --part development --rd <research-data clone> --out dev.json --csv trades.csv`
