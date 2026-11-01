# 04 — Strategy comparison matrix (2026-11-01)

**Rule:** a number appears only where it was measured. Everything else is **NOT TESTED**.

- **"In-sample"** = the stored recent windows (seen data).
- **"Forward"** = the recorded web.6 ledger.
- **Research tests** of new families run on the Amendment 13 development data only (2020-01-24 → 2023-01-24), each
  logged in the trial registry (`09` §6).

## A. Strategies that exist today (measured)

| Strategy | Evidence base | TF | Sample (in-sample / forward) | Gross R | Net R | Win % | PF | OOS | Calibration | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| H4 Playbook (close beyond the nearest level) | practitioner (levels) | 15m (decides) | 986 / 171 | −0.035 | −0.108 / −0.092 | 35.1 / 38.6 | 0.67 / 0.76 | forward negative, interval includes 0 | — (no P) | **REJECT as a signal.** Keep the levels as display ("levels to watch"); its forward test continues as registered |
| H4 Playbook | | 5m | 1,731 / 511 | −0.035 | −0.176 / −0.179 | 33.4 / 33.5 | 0.61 / 0.58 | forward **significantly negative** (t −4.75) | — | REJECT as a signal |
| Engine treatment | Pine v32 port | 1h (decides) | 30 / 3 | — | +0.05 / −0.16 | 43 / 33 | 1.48 / 1.47 | n too small | P has **no skill** (AUC 0.38–0.52) | **RESEARCH:** keep the forward test; no claim |
| Challenger (H1) | | 1h | 32 / 2 | — | +0.16 / +0.29 | 47 / 50 | 1.45 / 2.68 | n too small | as treatment | RESEARCH |
| Control | | 1h | 2 / 0 | — | −1.02 | 0 | — | — | — | comparison only |
| H2 Sweep and Value | SMC-style, registered | 1h | 8 / 0 | — | +0.33 | 63 | 1.37 | n too small | — | RESEARCH |
| H3 Sweep-to-Value | Pine H2 rule | 1h | 24 / 3 | — | −0.39 / −0.16 | 25 / 33 | 0.69 | negative in-sample on 5m / 15m / 1h | — | **MODIFY or REJECT** after its registered N; no change now |
| H5 High confidence | treatment subset | 1h (N 30) | 3 / 0 | — | +0.83 | 67 | 3.73 | n = 3: nothing shown | — | RESEARCH (selective-trading test) |
| H6 No score veto | treatment superset | 1h | 36 / 0 | — | −0.13 | 36 | 0.88 | n too small | — | RESEARCH |

## B. The research brief's library (Part 4): status

Rows marked TESTED were run on development data only (Phase B1 and B2, 2026-11-01); everything else is **NOT TESTED**.

| # | Strategy | Literature | Baseline it must beat | First test | Decision |
|---|---|---|---|---|---|
| 1 | Time-series momentum (TSMOM) | R3–R5 | always long / short | TSMOM 24h / 72h / 240h on 1h and 15m; 5d / 20d / 60d on 4h | **TESTED (development): REJECT** at these definitions. Gross −0.02…+0.07 R; 4h best = the always-long baseline; 0 of 36 net-positive (`B1_DEVELOPMENT_RESULTS.md`) |
| 2 | EMA20/100/200 alignment | practitioner | as 1 | ablation over 1 | NOT TESTED |
| 3 | VWAP trend continuation | practitioner | as 1 | | NOT TESTED |
| 4 | ADX-confirmed trend | practitioner | as 1 | | NOT TESTED |
| 5 | Donchian breakout | R6 (rule family) | always long / short | N 20 / 55 on 15m, 1h, 4h | **TESTED (development): REJECT.** Gross −0.08…+0.02 R; Reality Check p ≥ 0.996 |
| 6–9 | Session-range breakouts | R14 (intraday pattern) | unconditional continuation rate | Asia range → London; London range → NY, on 15m and 1h | **TESTED (development): REJECT** (Asia → London, London → NY: directionless, 47–50% of 1R trades won). Opening-range breakout NOT TESTED |
| 10–11 | ATR-expansion / squeeze breakout | R13 | as 6 | | NOT TESTED |
| 12 | Breakout and retest | practitioner | as 6 | | NOT TESTED |
| 13–16 | Liquidity sweep / equal H/L / PDH-PDL / PWH-PWL rejection | SMC (no peer review) | random entries, same direction mix | +$20 / +$10 / +$2 before −$10 (price-scaled), 15min and 1h | **TESTED (development, B2 / B2b): REJECT.** Win rates within ±2–3 points of random; none above break-even (`B2_DEVELOPMENT_RESULTS.md`, `B2B_DEVELOPMENT_RESULTS.md`) |
| 17–18 | BOS continuation / CHoCH-MSS reversal | SMC | random entries, same direction mix | as 13–16 | **TESTED (development, B2): REJECT.** Best of all 54: 1h BOS on +$20 / −$10, 35.8% against 33.3% random and a 36.2% break-even (z +1.24, net −0.011 R) |
| 19–20 | FVG continuation / OB retest | SMC | random entries, same direction mix | as 13–16 | **TESTED (development, B2): REJECT** (z ≤ +1.71; every trial net-negative) |
| 21–22 | VWAP / Bollinger mean reversion | mixed | random fade | range regime only | NOT TESTED |
| 23 | RSI divergence | folklore | — | | NOT TESTED |
| 24 | MACD momentum | folklore | as 1 | | NOT TESTED |
| 25 | Failed-breakout reversal | practitioner | as 13 | 20-bar breakout failing within 3 bars | **TESTED (development, B2): REJECT** (below random on 4 of 6 trials) |
| 26 | Volatility-regime conditioning | R13, R19 | unconditioned TSMOM | TSMOM 72h by ATR-percentile tercile | **TESTED (development): REJECT.** Less negative in high vol only because cost is a smaller share of R; gross ≈ 0 |
| 27 | Macro-event strategy | event studies | no-event days | needs a verified historical calendar | NOT TESTED |
| 28 | Cross-asset confirmation | R21, R22 | technical-only | point-in-time rolling relations | NOT TESTED |
| 29 | Market-profile acceptance / rejection | practitioner | as 13 | | NOT TESTED (the research series has no volume) |
| 30 | Trend-pullback continuation | R3 + practitioner | as 1 | | NOT TESTED |

**Order of testing (proposed).** Testing all 30 at once multiplies false discoveries (R6, R8). The proposal is:

- **Phase B1:** families with an empirical prior: 1, 5, 6–9, 26.
- **Phase B2:** SMC families against their matched-random baselines (13–20, 25, 29).
- **Phase B3:** combinations (Part 16), only of components that passed alone.
