# B31b-W13 development results (2026-11-25): NO SUPPORTED MECHANISM

**Question:** which entry mechanism reaches +$10 (preferably +$15 / +$20) before its structural stop often enough to make money after spread, commission and slippage?

**Method (`research/registrations/B31b-W13.json`, committed before any code or computation):**
- **Mechanisms:** 50, grouped in the operator's six families, each the registered rule of its own study (W3, W4, W5, W7). No new rule, filter, stop or threshold.
- **Trades:** each study's own counted development trades, 24 Jan 2020 – 24 Jan 2023 (hash `f113f97ad2105ff9`). W3, W7, W8 and W12 were re-run from unchanged code and reproduced their committed counts exactly (W3 A-IMM M15 1,249; W7 E0 M15 1,031, E1 M15 754; W8 67 / 74 / 49 / 68; W12 2,090 decided).
- **Cost:** every trade re-costed at the W8 broker decision cost.
- **Pass rule (SUPPORTED):** at least 100 decided trades; net R > 0 with a day-clustered 95% lower bound > 0; Holm p < 0.05 over all 50; positive in at least 5 of 6 walk-forward folds and in each of 2020, 2021 and 2022.

## The answer

**No mechanism is supported.** The ten best by the lower bound of net R:

| Rank | Mechanism | Trades | +$10 first | Net R per trade (95%) |
|---|---|---|---|---|
| 1 | W3 B-ACC M30 at the London / New York open (session continuation) | 359 | 66.3% | −0.001 (−0.073 to +0.070) |
| 2 | W3 B-ACC M15 at the London / New York open | 485 | 60.6% | −0.001 (−0.074 to +0.072) |
| 3 | W5 A0 (market at the impulse close) | 2,457 | 58.9% | −0.050 (−0.083 to −0.020) |
| 4 | W3 A-MSS M30 (sweep, then M30 structure shift) | 780 | 65.8% | −0.037 |
| 5–10 | W5 B0.3, I, A1, B0.236, B0.382, H | 1,965–2,273 each | 54–60% | −0.055 to −0.080 |

### Best of each family

| Family | Best mechanism | Net R / trade | +$10 first | Verdict |
|---|---|---|---|---|
| 1 Sweep + displacement | W4 B2 | −0.052 | 57.8% | negative |
| 2 Structure shift 5M / 15M | W3 A-MSS M30 | −0.037 | 65.8% | negative |
| 3 Sweep, reclaim, retest | W4 B1 | −0.137 | 43.7% | negative (all three below zero with 95% confidence) |
| 4 Breakout, then retest | W4 C1 | −0.095 | 45.8% | negative |
| 5 Session continuation (London / NY open) | W3 B-ACC M15 / M30 | −0.001 | 61–66% | break-even; negative at 1.5 × cost |
| 6 Entry timing / structural stops | W4 T1 (n 114) | +0.061 (−0.154 to +0.286) | 46.5% | not significant; 2020 negative; Holm 1.0 |

**Against the live strategies:**

| Strategy | Net R / trade | Note |
|---|---|---|
| W7 E1 M15 (live breakout shadow entry) | −0.061 | |
| W7 E0 M15 | −0.027 | |
| W12 boundary sweep | −0.255 | the worst |
| W3 immediate sweep reversal | about −0.14 | |

Only session continuation comes close, and it does not beat break-even.

## W12 revalidation (trade-level)

- **Independence:**
  - 2,100 trades on 731 distinct trading days.
  - 114 overlapped another open trade; at most 3 were open together.
  - One position at a time: 2,001 trades, net −0.260 R. Overlap does not cause the loss.
- **Entry timing:**
  - Of the 1,536 stop-first trades, 32% were stopped in the first M5 bar, 54% within 15 minutes and 83% within an hour (median 15 minutes).
  - 48% went less than $1 (at the $4,000 scale) beyond the wick.
  - 64% later reached +$10 from the entry within 24 h (32% did both).
  - The stop at the exact wick is too tight, not too wide. But a wider stop does not fix the expectancy: W3's immediate reversal, with its stop beyond the wick, reaches 43% instead of 26% and still loses −0.14 R, because the break-even rate rises with the stop.
- **Stop width:**
  - Median $3.35 (quartiles $1.88–$5.55).
  - Winners used a median 38% of the stop; 15% came within a quarter of it.
- **Dollar filter (EUR/USD not confirming the run):**
  - +4.1 points in the +$10-first rate.
  - Year-stratified permutation p = 0.033.
  - Positive in all 6 folds and every year, and +3.3 points within the New York open alone.
  - A small, consistent effect, but not significant after Holm over the three confirmations (about 0.10). The trades stay at −0.19 R.
- **Regimes:** negative in every year (2020 −0.23, 2021 −0.28, 2022 −0.25) and every volatility regime (LOW −0.29, NORMAL −0.27, HIGH −0.21).
- **Expectancy at the broker cost:**
  - −$166 per trade and −$2,305 per week at 14 trades a week.
  - Profit factor 0.65; maximum drawdown $354,168 at $650 per trade.
  - At 1.5 × cost: −0.32 R.

## Cost check from the operator's 26 Nov screenshots

- At 15:55 New York (20:55 UTC) the broker's spread read $0.65–0.89 (M15 / M30 / H1, axis fit within $0.10).
- The decision cost assumes $0.30 in New York hours. That is one reading on a volatile afternoon.
- At 1.5 × cost every mechanism above is negative, including session continuation (−0.02 / −0.03 R).

## Recommendation

**No mechanism deserves a controlled forward test.**
- None passed development, so the sealed validation partition was not opened.
- The closest, London / New York open continuation, is at break-even before a realistic New York spread.
- The live breakout monitor already records E1 shadow entries with their session, so forward evidence on that family accrues with no change to production.

Production, alerts, the frozen forward test and the freeze key are unchanged.

## Full tables

**Verdict: NO SUPPORTED MECHANISM** (development 150 weeks; cost: the W8 broker decision cost)

### Family 1 sweep + displacement

| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | $ / trade | PF | Max DD $ | Folds + · years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W3 A-DISP M15 | 545 | 3.6 | 49.5% | 38.0% | 32.5% | 50.5% | 30.7 / 34.0 | -0.086 (-0.165 to -0.007) | -56 | 0.83 | 41,497 | 1/6 · -0.07 / -0.06 / -0.15 |
| W3 A-DISP M30 | 317 | 2.1 | 50.8% | 41.6% | 35.3% | 48.6% | 28.1 / 34.4 | -0.143 (-0.236 to -0.051) | -93 | 0.71 | 32,551 | 1/6 · -0.09 / -0.17 / -0.18 |
| W4 A5 | 132 | 0.9 | 50.8% | 41.7% | 34.1% | 49.2% | 28.7 / 31.5 | -0.076 (-0.236 to +0.081) | -50 | 0.84 | 12,982 | 2/6 · -0.01 / -0.27 / +0.01 |
| W4 B2 | 187 | 1.2 | 57.8% | 46.0% | 39.0% | 42.2% | 30.1 / 31.4 | -0.052 (-0.167 to +0.068) | -34 | 0.88 | 11,235 | 3/6 · -0.23 / +0.10 / -0.05 |

### Family 2 structure shift 5M/15M

| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | $ / trade | PF | Max DD $ | Folds + · years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W3 A-MSS M15 | 1301 | 8.7 | 56.6% | 47.3% | 40.3% | 42.6% | 31.0 / 30.7 | -0.106 (-0.147 to -0.065) | -69 | 0.76 | 93,201 | 0/6 · -0.17 / -0.07 / -0.11 |
| W3 A-MSS M30 | 780 | 5.2 | 65.8% | 57.3% | 49.0% | 31.9% | 31.0 / 30.4 | -0.037 (-0.086 to +0.014) | -24 | 0.89 | 25,913 | 2/6 · -0.08 / -0.05 / -0.01 |
| W3 A-M5MSS M15 | 950 | 6.3 | 50.6% | 40.0% | 34.6% | 49.1% | 31.7 / 30.7 | -0.112 (-0.169 to -0.055) | -73 | 0.77 | 71,662 | 0/6 · -0.19 / -0.05 / -0.10 |
| W3 A-M5MSS M30 | 747 | 5.0 | 53.8% | 44.0% | 38.3% | 45.8% | 29.9 / 30.4 | -0.084 (-0.149 to -0.022) | -55 | 0.82 | 45,155 | 1/6 · -0.16 / -0.04 / -0.04 |
| W4 A3 | 172 | 1.1 | 49.4% | 40.7% | 33.7% | 50.0% | 36.2 / 32.0 | -0.121 (-0.256 to +0.014) | -79 | 0.76 | 16,175 | 2/6 · -0.15 / -0.24 / -0.01 |
| W4 B3 | 294 | 2.0 | 59.2% | 49.3% | 41.8% | 40.8% | 30.9 / 30.0 | -0.050 (-0.150 to +0.048) | -33 | 0.88 | 11,278 | 3/6 · -0.13 / +0.06 / -0.09 |
| W4 B4 | 134 | 0.9 | 45.5% | 37.3% | 27.6% | 54.5% | 29.8 / 31.1 | -0.160 (-0.322 to -0.004) | -104 | 0.71 | 15,979 | 3/6 · -0.36 / +0.05 / -0.14 |

### Family 3 sweep, reclaim, retest

| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | $ / trade | PF | Max DD $ | Folds + · years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W3 A-RETEST M15 | 275 | 1.8 | 39.6% | 29.5% | 25.1% | 60.4% | 37.4 / 42.6 | -0.148 (-0.284 to -0.010) | -96 | 0.76 | 32,192 | 0/6 · -0.20 / -0.12 / -0.09 |
| W3 A-RETEST M30 | 308 | 2.1 | 42.2% | 33.8% | 26.3% | 57.8% | 33.1 / 39.3 | -0.151 (-0.260 to -0.041) | -98 | 0.74 | 34,172 | 0/6 · -0.13 / -0.16 / -0.17 |
| W4 B1 | 387 | 2.6 | 43.7% | 35.1% | 29.5% | 56.3% | 33.2 / 39.4 | -0.137 (-0.235 to -0.034) | -89 | 0.76 | 35,932 | 1/6 · -0.13 / -0.17 / -0.11 |

### Family 4 breakout, then retest

| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | $ / trade | PF | Max DD $ | Folds + · years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W3 B-RETEST M15 | 552 | 3.7 | 42.9% | 35.1% | 29.0% | 57.1% | 33.4 / 33.9 | -0.142 (-0.227 to -0.051) | -92 | 0.75 | 52,571 | 1/6 · -0.18 / -0.14 / -0.11 |
| W3 B-RETEST M30 | 488 | 3.3 | 46.9% | 38.9% | 32.0% | 53.1% | 32.3 / 30.3 | -0.118 (-0.200 to -0.028) | -77 | 0.78 | 42,426 | 0/6 · -0.12 / -0.11 / -0.11 |
| W4 C1 | 528 | 3.5 | 45.8% | 37.5% | 29.7% | 54.2% | 35.7 / 34.2 | -0.095 (-0.189 to -0.002) | -61 | 0.83 | 39,621 | 0/6 · -0.13 / -0.13 / -0.06 |
| W4 C2 | 133 | 0.9 | 46.6% | 39.1% | 35.3% | 53.4% | 39.2 / 29.6 | -0.103 (-0.264 to +0.062) | -67 | 0.81 | 16,545 | 2/6 · +0.07 / -0.13 / -0.29 |
| W4 A4 | 46 | 0.3 | 39.1% | 34.8% | 32.6% | 60.9% | 50.0 / 32.2 | -0.128 (-0.473 to +0.216) | -83 | 0.79 | 5,728 | 1/6 · -0.13 / +0.20 / -0.34 |
| W7 E2 M15 | 646 | 4.3 | 43.8% | 36.2% | 30.0% | 56.0% | 36.4 / 35.7 | -0.127 (-0.209 to -0.047) | -82 | 0.77 | 59,358 | 0/6 · -0.15 / -0.16 / -0.07 |
| W7 E2 M30 | 640 | 4.3 | 47.3% | 40.3% | 32.8% | 52.5% | 34.0 / 33.1 | -0.121 (-0.196 to -0.050) | -79 | 0.77 | 54,658 | 0/6 · -0.06 / -0.23 / -0.06 |

### Family 5 session continuation (London / NY open)

| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | $ / trade | PF | Max DD $ | Folds + · years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W3s B-ACC M15 | 485 | 3.2 | 60.6% | 48.7% | 40.0% | 38.4% | 33.9 / 29.0 | -0.001 (-0.074 to +0.072) | -1 | 1.00 | 11,860 | 3/6 · +0.04 / -0.03 / -0.00 |
| W3s B-ACC M30 | 359 | 2.4 | 66.3% | 54.9% | 45.4% | 30.1% | 32.7 / 28.3 | -0.001 (-0.073 to +0.070) | -1 | 1.00 | 7,098 | 4/6 · -0.02 / +0.04 / -0.03 |
| W7s E1 M15 | 181 | 1.2 | 55.8% | 41.4% | 35.4% | 44.2% | 39.8 / 27.3 | +0.008 (-0.126 to +0.151) | +5 | 1.02 | 10,405 | 3/6 · +0.10 / -0.12 / +0.06 |
| W7s E1 M30 | 166 | 1.1 | 57.8% | 48.8% | 39.8% | 41.6% | 34.2 / 29.5 | -0.056 (-0.192 to +0.071) | -36 | 0.87 | 11,852 | 1/6 · -0.01 / -0.18 / +0.01 |

### Family 6 entry timing / structural stops

| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | $ / trade | PF | Max DD $ | Folds + · years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W5 A0 | 2457 | 16.4 | 58.9% | 50.1% | 42.5% | 40.9% | 32.2 / 31.0 | -0.050 (-0.083 to -0.020) | -33 | 0.88 | 87,413 | 0/6 · -0.04 / -0.07 / -0.04 |
| W5 A1 | 2273 | 15.1 | 58.7% | 47.8% | 41.0% | 40.5% | 31.3 / 32.5 | -0.063 (-0.095 to -0.030) | -41 | 0.85 | 96,327 | 0/6 · -0.06 / -0.08 / -0.05 |
| W5 B0.236 | 2258 | 15.0 | 57.0% | 47.2% | 39.7% | 42.6% | 31.2 / 32.3 | -0.064 (-0.099 to -0.029) | -41 | 0.85 | 95,080 | 0/6 · -0.06 / -0.05 / -0.07 |
| W5 B0.382 | 2095 | 14.0 | 53.8% | 44.3% | 37.9% | 45.9% | 31.9 / 32.6 | -0.071 (-0.108 to -0.033) | -46 | 0.85 | 98,054 | 0/6 · -0.08 / -0.04 / -0.09 |
| W5 B0.5 | 1914 | 12.7 | 50.3% | 41.3% | 34.4% | 49.6% | 32.8 / 32.9 | -0.094 (-0.137 to -0.052) | -61 | 0.81 | 122,352 | 0/6 · -0.13 / -0.03 / -0.12 |
| W5 B0.618 | 1511 | 10.1 | 46.0% | 36.1% | 30.7% | 54.0% | 33.6 / 33.5 | -0.118 (-0.169 to -0.060) | -77 | 0.78 | 121,576 | 0/6 · -0.11 / -0.11 / -0.14 |
| W5 B0.786 | 582 | 3.9 | 44.3% | 35.4% | 28.4% | 55.7% | 39.2 / 37.2 | -0.048 (-0.144 to +0.055) | -31 | 0.92 | 23,031 | 3/6 · -0.01 / +0.04 / -0.16 |
| W5 B0.3 | 2227 | 14.8 | 56.6% | 46.8% | 39.3% | 43.1% | 31.6 / 32.3 | -0.055 (-0.090 to -0.020) | -36 | 0.87 | 80,920 | 1/6 · -0.03 / -0.06 / -0.07 |
| W5 B0.45 | 2021 | 13.5 | 51.6% | 41.5% | 35.2% | 48.2% | 32.7 / 32.8 | -0.091 (-0.134 to -0.054) | -59 | 0.81 | 122,219 | 0/6 · -0.11 / -0.05 / -0.11 |
| W5 B0.55 | 1772 | 11.8 | 48.9% | 39.2% | 32.8% | 51.1% | 33.1 / 33.1 | -0.093 (-0.139 to -0.049) | -60 | 0.82 | 112,153 | 1/6 · -0.11 / -0.03 / -0.13 |
| W5 B0.7 | 1117 | 7.4 | 46.2% | 36.1% | 30.4% | 53.8% | 35.0 / 34.8 | -0.069 (-0.131 to -0.004) | -45 | 0.87 | 62,443 | 1/6 · -0.04 / -0.06 / -0.11 |
| W5 C | 1221 | 8.1 | 48.2% | 39.0% | 31.1% | 51.7% | 33.3 / 35.0 | -0.108 (-0.163 to -0.053) | -70 | 0.79 | 91,340 | 1/6 · -0.07 / -0.10 / -0.17 |
| W5 E | 1741 | 11.6 | 52.4% | 42.8% | 36.9% | 47.2% | 31.2 / 31.9 | -0.082 (-0.125 to -0.037) | -53 | 0.83 | 94,763 | 0/6 · -0.08 / -0.07 / -0.10 |
| W5 F | 1951 | 13.0 | 51.4% | 41.7% | 34.4% | 48.4% | 32.6 / 32.7 | -0.071 (-0.113 to -0.031) | -46 | 0.85 | 95,214 | 1/6 · -0.05 / -0.03 / -0.14 |
| W5 G20 | 2126 | 14.2 | 54.9% | 45.8% | 38.1% | 44.7% | 31.8 / 32.6 | -0.081 (-0.118 to -0.045) | -53 | 0.82 | 119,925 | 0/6 · -0.03 / -0.08 / -0.13 |
| W5 G50 | 1942 | 12.9 | 52.9% | 42.7% | 36.1% | 46.9% | 31.2 / 32.5 | -0.092 (-0.132 to -0.051) | -60 | 0.80 | 119,860 | 0/6 · -0.07 / -0.12 / -0.08 |
| W5 H | 1965 | 13.1 | 59.6% | 50.2% | 42.3% | 38.9% | 30.8 / 32.0 | -0.080 (-0.111 to -0.046) | -52 | 0.80 | 105,510 | 0/6 · -0.07 / -0.06 / -0.10 |
| W5 I | 2188 | 14.6 | 57.0% | 46.9% | 39.3% | 42.4% | 31.8 / 32.3 | -0.057 (-0.092 to -0.022) | -37 | 0.87 | 81,985 | 0/6 · -0.05 / -0.04 / -0.07 |
| W5 J | 1113 | 7.4 | 57.9% | 48.2% | 41.2% | 41.5% | 31.2 / 31.3 | -0.070 (-0.114 to -0.026) | -46 | 0.83 | 55,570 | 1/6 · -0.06 / -0.11 / -0.04 |
| W5 K | 1948 | 13.0 | 42.7% | 33.3% | 27.6% | 57.3% | 31.6 / 31.5 | -0.084 (-0.131 to -0.034) | -54 | 0.85 | 116,806 | 0/6 · -0.09 / -0.05 / -0.11 |
| W4 T1 | 114 | 0.8 | 46.5% | 37.7% | 32.5% | 53.5% | 44.9 / 31.0 | +0.061 (-0.154 to +0.286) | +40 | 1.11 | 6,470 | 5/6 · -0.02 / +0.05 / +0.14 |
| W4 T4 | 147 | 1.0 | 51.7% | 44.2% | 36.1% | 48.3% | 31.1 / 31.1 | -0.121 (-0.270 to +0.023) | -78 | 0.75 | 13,818 | 1/6 · -0.23 / +0.03 / -0.14 |
| W4 T6 | 151 | 1.0 | 49.7% | 39.1% | 36.4% | 50.3% | 33.4 / 32.8 | -0.106 (-0.256 to +0.050) | -69 | 0.79 | 15,454 | 1/6 · -0.05 / -0.19 / -0.12 |
| W7 E3 M15 | 598 | 4.0 | 48.0% | 37.6% | 29.9% | 52.0% | 31.6 / 35.1 | -0.104 (-0.178 to -0.028) | -67 | 0.80 | 46,436 | 0/6 · -0.13 / -0.15 / -0.04 |
| W7 E3 M30 | 655 | 4.4 | 49.8% | 39.4% | 32.2% | 50.1% | 31.4 / 32.3 | -0.123 (-0.190 to -0.052) | -80 | 0.76 | 56,758 | 0/6 · -0.11 / -0.16 / -0.10 |

### Baselines (not candidates)

| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | $ / trade | PF | Max DD $ | Folds + · years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W3 A-IMM M15 | 1249 | 8.3 | 43.2% | 33.0% | 28.1% | 56.8% | 34.1 / 36.1 | -0.146 (-0.201 to -0.092) | -95 | 0.74 | 119,227 | 0/6 · -0.14 / -0.15 / -0.14 |
| W3 A-IMM M30 | 1129 | 7.5 | 45.7% | 37.8% | 31.6% | 54.3% | 31.9 / 34.4 | -0.140 (-0.196 to -0.086) | -91 | 0.74 | 111,718 | 0/6 · -0.17 / -0.20 / -0.06 |
| W12 H1 | 2090 | 13.9 | 26.0% | 19.9% | 15.7% | 73.5% | 26.7 / 27.9 | -0.255 (-0.312 to -0.197) | -166 | 0.65 | 354,168 | 0/6 · -0.23 / -0.28 / -0.25 |
| W12x H1 (one at a time) | 1991 | 13.3 | 25.9% | 20.0% | 15.8% | 73.6% | 26.8 / 28.0 | -0.260 (-0.320 to -0.199) | -169 | 0.65 | 344,258 | 0/6 · -0.24 / -0.29 / -0.24 |
| W7 E0 M15 | 1031 | 6.9 | 51.3% | 39.7% | 31.7% | 48.7% | 36.2 / 35.0 | -0.027 (-0.085 to +0.034) | -18 | 0.94 | 31,550 | 2/6 · -0.03 / -0.00 / -0.04 |
| W7 E0 M30 | 973 | 6.5 | 47.6% | 38.0% | 31.8% | 52.2% | 32.9 / 32.6 | -0.158 (-0.213 to -0.102) | -103 | 0.70 | 102,023 | 0/6 · -0.14 / -0.23 / -0.12 |
| W7 E1 M15 | 754 | 5.0 | 51.5% | 39.3% | 31.7% | 48.5% | 35.1 / 33.5 | -0.061 (-0.127 to +0.001) | -39 | 0.88 | 37,499 | 1/6 · -0.00 / -0.08 / -0.10 |
| W7 E1 M30 | 659 | 4.4 | 52.0% | 43.1% | 35.8% | 47.5% | 32.2 / 32.1 | -0.111 (-0.180 to -0.044) | -72 | 0.77 | 48,935 | 0/6 · -0.08 / -0.21 / -0.04 |
| W8 E0 M15 | 67 | 0.4 | 50.7% | 34.3% | 25.4% | 49.3% | 26.3 / 30.9 | -0.109 (-0.302 to +0.093) | -71 | 0.78 | 6,203 | 0/6 · -0.25 / -0.09 / -0.06 |
| W8 E0 M30 | 74 | 0.5 | 58.1% | 41.9% | 29.7% | 40.5% | 26.2 / 32.4 | -0.022 (-0.223 to +0.168) | -14 | 0.95 | 3,952 | 3/6 · -0.19 / +0.01 / -0.04 |
| W8 E1 M15 | 49 | 0.3 | 53.1% | 36.7% | 24.5% | 46.9% | 25.7 / 28.2 | -0.036 (-0.300 to +0.203) | -23 | 0.92 | 4,048 | 3/6 · +0.04 / -0.14 / +0.05 |
| W8 E1 M30 | 68 | 0.5 | 60.3% | 44.1% | 32.4% | 38.2% | 27.5 / 30.3 | +0.042 (-0.172 to +0.246) | +28 | 1.11 | 3,629 | 2/6 · -0.22 / -0.10 / +0.14 |
| W5 B_rand | 1813 | 12.1 | 52.5% | 41.9% | 35.2% | 47.2% | 33.1 / 32.3 | -0.062 (-0.105 to -0.019) | -40 | 0.87 | 81,351 | 0/6 · -0.06 / -0.03 / -0.10 |

### Strongest by the lower 95% bound of net R (at least 100 trades)

| Mechanism | Lower bound | Net R | Trades |
|---|---|---|---|
| W3s B-ACC M30 | -0.073 | -0.001 | 359 |
| W3s B-ACC M15 | -0.074 | -0.001 | 485 |
| W5 A0 | -0.083 | -0.050 | 2457 |
| W3 A-MSS M30 | -0.086 | -0.037 | 780 |
| W5 B0.3 | -0.090 | -0.055 | 2227 |
| W5 I | -0.092 | -0.057 | 2188 |
| W5 A1 | -0.095 | -0.063 | 2273 |
| W5 B0.236 | -0.099 | -0.064 | 2258 |
| W5 B0.382 | -0.108 | -0.071 | 2095 |
| W5 H | -0.111 | -0.080 | 1965 |
