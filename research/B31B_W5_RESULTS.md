# B31b-W5 results: the executable entry price (Critical Workstream 5)

**Verdict: NO CANDIDATE — NO TRADE, INSUFFICIENT EVIDENCE.** On 4,223 directional impulses in the development period
(2020-03 .. 2023-01), none of 20 executable entry mechanisms reaches +$10 before the structural stop more often than a
driftless random walk with the same stop distance would (every mechanism's excess over D / (D + 10) is between −0.024
and +0.015), and every one loses money after costs (mean net R −0.05 to −0.12). Where price is entered decides the stop
distance, and the stop distance decides the +$10-first rate; the entry method adds nothing beyond that. Validation
(2023-24) and holdout (2024-25) were not opened.

- Registration `research/registrations/B31b-W5.json` (commit 238b6c56b, before any code); amendment A1 before any run
  (commit 6049d201f). Code `quantum/research/w5entry.py` (sha256 64a9a4ef...), measuring through W3's
  `w3liq.execute`. One development run, logged in `research/trials.jsonl` (08:36 UTC, code 5e1435d1...). Two
  code-only changes followed: the random-number call moved to `harness.seeded_rng` (the same generator stream, as
  `tests/test_integrity.py` requires), then three unused local variables were removed. The run was repeated after each
  (logged at 08:55 and 08:58 UTC), and every output was identical apart from the code hash. Both repeats are logged as re-runs,
  not new trials. The committed results are from the last one.
- Data: Twelve Data spot mid prices (15 min, 1 h, 5 min; M5 coverage 99.2%), no bid / ask and no volume. Distances are
  $ at $4,000 (scaled by price / 4,000, as in W3 / W4). 100 oz per lot is ASSUMED in all sizing.

## 1. The answer to the question

*"At what exact executable market price should we enter so that XAUUSD has the highest demonstrable probability of
moving at least $10 in our direction before hitting the structural stop?"*

- **The probability is set by the stop distance, not by the entry method.** Shallow entries (market at the impulse,
  the first pullback, 0.236-0.3 limits) have the structural stop ~$13-14 away and reach +$10 first 57-59% of the time;
  deep entries (0.618-0.786 limits, the adaptive K) have it ~$7-9 away and reach +$10 first 43-46%. Both are what a
  driftless walk gives for those distances (D / (D + 10)): moving the entry deeper only moves along that curve.
- **No entry price beats that curve.** The excess over geometry is zero within ±0.03 for all 20 mechanisms and for the
  random-level control, and none has positive net R after costs.
- **There is therefore no "highest demonstrable probability" price to name** on this data. The honest answer is NO TRADE.

## 2. Every mechanism (pooled over both directions: the registered test)

| Mechanism | n | +$10 first | Driftless geometry D/(D+10) | Excess over geometry [95%] | R1 same-stop random timing | Holm p vs R1 | Mean net R [95%] | +$15 | +$20 | Median stop | vs immediate (R2) | vs random price in zone (R3) |
|---|---:|---:|---:|---|---:|---:|---|---:|---:|---:|---:|---:|
| A0  | 2457 | 58.9% | 58.6% | +0.004 [-0.015, +0.022] | 59.0% | 1.00 | -0.050 [-0.08, -0.02] | 50.1% | 42.5% | $13.65 | +0.059 | -0.029 |
| A1  | 2273 | 58.7% | 59.3% | -0.006 [-0.026, +0.013] | 58.9% | 1.00 | -0.063 [-0.10, -0.03] | 47.8% | 41.0% | $14.08 | +0.000 | -0.070 |
| B0.236  | 2258 | 57.0% | 57.7% | -0.007 [-0.026, +0.014] | 57.0% | 1.00 | -0.064 [-0.10, -0.03] | 47.2% | 39.7% | $13.38 | +0.025 | -0.049 |
| B0.382  | 2095 | 53.8% | 54.6% | -0.008 [-0.030, +0.014] | 52.6% | 1.00 | -0.071 [-0.11, -0.03] | 44.3% | 37.9% | $11.54 | +0.068 | -0.005 |
| B0.5  | 1914 | 50.3% | 51.6% | -0.013 [-0.036, +0.008] | 47.3% | 0.07 | -0.094 [-0.14, -0.05] | 41.3% | 34.4% | $10.10 | +0.104 | +0.031 |
| B0.618  | 1511 | 46.0% | 48.0% | -0.020 [-0.045, +0.005] | 41.2% | 0.00 | -0.118 [-0.17, -0.07] | 36.1% | 30.7% | $8.64 | +0.155 | +0.094 |
| B0.786  | 582 | 44.3% | 42.8% | +0.015 [-0.026, +0.055] | 32.9% | 0.00 | -0.047 [-0.15, +0.06] | 35.4% | 28.4% | $6.94 | +0.310 | +0.257 |
| B0.3  | 2227 | 56.6% | 56.5% | +0.001 [-0.019, +0.022] | 54.9% | 0.67 | -0.055 [-0.09, -0.02] | 46.8% | 39.3% | $12.71 | +0.049 | -0.025 |
| B0.45  | 2021 | 51.6% | 53.0% | -0.013 [-0.034, +0.008] | 49.3% | 0.26 | -0.092 [-0.13, -0.05] | 41.5% | 35.2% | $10.65 | +0.087 | +0.018 |
| B0.55  | 1772 | 48.9% | 50.0% | -0.011 [-0.033, +0.012] | 44.5% | 0.00 | -0.093 [-0.14, -0.05] | 39.2% | 32.8% | $9.33 | +0.132 | +0.064 |
| B0.7  | 1117 | 46.2% | 45.4% | +0.008 [-0.021, +0.038] | 37.6% | 0.00 | -0.069 [-0.13, -0.00] | 36.1% | 30.4% | $7.77 | +0.235 | +0.166 |
| C  | 1221 | 48.2% | 49.8% | -0.015 [-0.044, +0.015] | 43.7% | 0.01 | -0.109 [-0.17, -0.05] | 39.0% | 31.1% | $9.19 | +0.166 | +0.082 |
| E  | 1741 | 52.4% | 53.9% | -0.015 [-0.037, +0.008] | 51.0% | 1.00 | -0.082 [-0.12, -0.04] | 42.8% | 36.9% | $11.26 | +0.065 | -0.016 |
| F  | 1951 | 51.4% | 51.7% | -0.003 [-0.026, +0.020] | 48.7% | 0.14 | -0.071 [-0.11, -0.03] | 41.7% | 34.4% | $10.20 | +0.094 | +0.026 |
| G20  | 2126 | 54.9% | 56.1% | -0.012 [-0.034, +0.008] | 54.1% | 1.00 | -0.082 [-0.12, -0.05] | 45.8% | 38.1% | $12.47 | +0.022 | -0.058 |
| G50  | 1942 | 52.9% | 54.6% | -0.017 [-0.039, +0.006] | 51.6% | 1.00 | -0.092 [-0.13, -0.05] | 42.7% | 36.1% | $11.68 | +0.038 | -0.043 |
| H  | 1965 | 59.6% | 62.1% | -0.024 [-0.045, -0.005] | 61.2% | 1.00 | -0.080 [-0.11, -0.05] | 50.2% | 42.3% | $16.37 | -0.117 | -0.204 |
| I  | 2188 | 57.0% | 57.4% | -0.003 [-0.024, +0.017] | 55.7% | 1.00 | -0.057 [-0.09, -0.02] | 46.9% | 39.3% | $13.01 | +0.047 | -0.028 |
| J  | 1113 | 57.9% | 58.9% | -0.010 [-0.038, +0.017] | 60.0% | 1.00 | -0.071 [-0.12, -0.02] | 48.2% | 41.2% | $14.29 | -0.111 | -0.221 |
| K  | 1948 | 42.7% | 41.9% | +0.008 [-0.015, +0.030] | 36.4% | 0.00 | -0.084 [-0.13, -0.03] | 33.3% | 27.6% | $7.19 | +0.208 | +0.137 |
| B_rand (control) | 1813 | 52.5% | 52.6% | -0.001 [-0.023, +0.021] | 49.4% | — | -0.062 [-0.11, -0.02] | 41.9% | 35.2% | $10.40 | +0.103 | +0.040 |

Reading the table:
- *R1 same-stop random timing* (primary benchmark): deeper limits (0.55-0.786, C, K) beat random market entries placed in
  the same window with the same stop distance by 5-11 points, and that survives Holm. That is not an edge: those random
  market entries do *worse* than a driftless walk (entering at a random close during a pullback with a tight stop gets
  stopped by the pullback's continuation), while the limits only come back up to the geometry. Beating a benchmark that
  is itself below fair is not a positive result; the registered candidate rule also requires positive net R, which no
  mechanism has.
- *vs R2 / R3*: the paired differences are within ±0.3 R and none turns a mechanism's net R positive.
- *Waiting for confirmation* (H: M5 resume; J: failed reclaim) costs ~0.11-0.12 R against the immediate entry and
  0.20-0.22 R against a random price in the zone: confirmation arrives after the price has left.

| Mechanism | Entry vs earliest price (ATR, + = better; quartiles) | Delay from detection (min, quartiles) | Share of the earliest price's 24 h move already used (quartiles) | Net R at cost x1.5 / x2 | +$10 first but net negative | +$10 then stopped before +$20 | Realised loss > $650 (worst) |
|---|---|---|---|---|---:|---:|---|
| A0 | +0.00 / +0.00 / +0.00 | 0 / 0 / 0 | 0.00 / 0.00 / 0.00 | -0.078 / -0.103 | 0 | 356 | 8 of 1004 ($2,696) |
| A1 | -0.60 / -0.00 / +0.43 | 15 / 30 / 45 | 0.00 / 0.00 / 0.14 | -0.090 / -0.114 | 0 | 341 | 9 of 920 ($3,536) |
| B0.236 | -0.39 / +0.14 / +0.50 | 15 / 30 / 60 | 0.00 / 0.00 / 0.08 | -0.092 / -0.118 | 0 | 337 | 9 of 961 ($3,535) |
| B0.382 | +0.02 / +0.45 / +0.74 | 15 / 30 / 75 | 0.00 / 0.00 / 0.00 | -0.102 / -0.131 | 0 | 307 | 8 of 961 ($3,535) |
| B0.5 | +0.37 / +0.73 / +1.00 | 15 / 45 / 101 | 0.00 / 0.00 / 0.00 | -0.127 / -0.157 | 0 | 284 | 10 of 949 ($3,535) |
| B0.618 | +0.75 / +1.08 / +1.32 | 30 / 60 / 120 | 0.00 / 0.00 / 0.00 | -0.153 / -0.185 | 0 | 224 | 8 of 816 ($4,198) |
| B0.786 | +1.33 / +1.57 / +1.82 | 45 / 90 / 150 | 0.00 / 0.00 / 0.00 | -0.092 / -0.132 | 0 | 93 | 3 of 324 ($6,061) |
| B0.3 | -0.21 / +0.27 / +0.58 | 15 / 30 / 60 | 0.00 / 0.00 / 0.04 | -0.085 / -0.112 | 0 | 340 | 11 of 960 ($3,535) |
| B0.45 | +0.21 / +0.61 / +0.88 | 15 / 45 / 90 | 0.00 / 0.00 / 0.00 | -0.123 / -0.153 | 0 | 308 | 11 of 975 ($3,535) |
| B0.55 | +0.54 / +0.87 / +1.13 | 30 / 45 / 105 | 0.00 / 0.00 / 0.00 | -0.128 / -0.159 | 0 | 270 | 8 of 905 ($3,780) |
| B0.7 | +1.04 / +1.31 / +1.56 | 30 / 75 / 135 | 0.00 / 0.00 / 0.00 | -0.109 / -0.146 | 0 | 175 | 4 of 601 ($4,920) |
| C | +0.43 / +0.96 / +1.32 | 30 / 45 / 105 | 0.00 / 0.00 / 0.00 | -0.143 / -0.174 | 0 | 194 | 6 of 631 ($3,898) |
| E | -0.08 / +0.36 / +0.77 | 15 / 30 / 75 | 0.00 / 0.00 / 0.01 | -0.114 / -0.143 | 0 | 252 | 6 of 822 ($3,535) |
| F | +0.32 / +0.63 / +0.92 | 15 / 45 / 90 | 0.00 / 0.00 / 0.00 | -0.105 / -0.137 | 0 | 309 | 9 of 944 ($3,535) |
| G20 | -0.24 / +0.27 / +0.68 | 15 / 45 / 105 | 0.00 / 0.00 / 0.05 | -0.110 / -0.137 | 0 | 319 | 9 of 950 ($3,656) |
| G50 | -0.12 / +0.30 / +0.75 | 15 / 30 / 75 | 0.00 / 0.00 / 0.02 | -0.122 / -0.150 | 0 | 301 | 7 of 910 ($1,514) |
| H | -1.46 / -0.44 / +0.30 | 50 / 70 / 100 | 0.00 / 0.08 / 0.28 | -0.103 / -0.125 | 0 | 264 | 5 of 765 ($3,958) |
| I | -0.38 / +0.25 / +0.66 | 15 / 30 / 60 | 0.00 / 0.00 / 0.08 | -0.086 / -0.112 | 0 | 334 | 10 of 928 ($3,535) |
| J | -0.79 / -0.26 / +0.21 | 75 / 120 / 195 | 0.00 / 0.04 / 0.18 | -0.097 / -0.122 | 0 | 155 | 4 of 462 ($962) |
| K | +0.70 / +1.14 / +1.42 | 30 / 60 / 120 | 0.00 / 0.00 / 0.00 | -0.130 / -0.172 | 0 | 286 | 7 of 1117 ($5,103) |

- No trade reached +$10 first and still lost after costs: with a $0.77-0.97 cost, a +$10 exit is always net positive.
- Many +$10 winners were stopped before +$20 when held (e.g. 356 of A0's): the +$10 / +$15 / +$20 races are separate.
- Costs: at 1.5x and 2x the modelled cost every mechanism is worse (no mechanism is near break-even).

## 3. Entry depth and the Fibonacci claim

| Random-level fills by realised depth | n | +$10 first | Median stop | Excess over geometry [95%] | Mean net R [95%] |
|---|---:|---:|---:|---|---|
| 0.20-0.35 of the impulse | 647 | 56.7% | $12.28 | +0.002 [-0.036, +0.037] | -0.052 [-0.12, +0.01] |
| 0.35-0.50 of the impulse | 554 | 54.2% | $10.47 | +0.010 [-0.032, +0.052] | -0.043 [-0.12, +0.04] |
| 0.50-0.65 of the impulse | 384 | 50.8% | $9.24 | +0.012 [-0.037, +0.062] | -0.032 [-0.13, +0.07] |
| 0.65-0.80 of the impulse | 228 | 39.5% | $7.57 | -0.055 [-0.111, +0.006] | -0.188 [-0.35, -0.02] |

The random-level control (one limit per opportunity at a random 0.2-0.8 retracement, so entry depth is unbiased) shows
the same thing directly: the +$10-first rate falls with depth exactly as the stop distance shrinks, the excess over
geometry stays at zero, and the deepest bin is the worst after costs.

| Level vs random level (paired net R at +$10, same opportunity) | Fibonacci? | n | Difference [95%] | Holm p |
|---|---|---:|---|---:|
| B0.236 | yes | 1471 | -0.099 [-0.127, -0.074] | 1.000 |
| B0.382 | yes | 1494 | -0.060 [-0.086, -0.036] | 1.000 |
| B0.5 | yes | 1421 | -0.023 [-0.052, +0.004] | 1.000 |
| B0.618 | yes | 1194 | +0.052 [+0.017, +0.084] | 0.018 |
| B0.786 | yes | 516 | +0.234 [+0.165, +0.305] | 0.000 |
| B0.3 | no | 1504 | -0.079 [-0.105, -0.054] | 1.000 |
| B0.45 | no | 1472 | -0.034 [-0.060, -0.008] | 1.000 |
| B0.55 | no | 1352 | +0.006 [-0.023, +0.034] | 1.000 |
| B0.7 | no | 928 | +0.137 [+0.093, +0.180] | 0.000 |

**The registered Fibonacci rule is met (0.618 and 0.786 beat the random level, Holm p < 0.05) but the evidence does
not support Fibonacci levels.** The non-Fibonacci 0.70 beats it just as clearly, the difference rises smoothly with
depth through Fibonacci and non-Fibonacci levels alike (0.236 −0.10 … 0.55 +0.01, 0.618 +0.05, 0.70 +0.14, 0.786 +0.23),
and the comparison is conditional on the deep level filling: on those paths the shallower random-level entry is, by
construction, the worse price. The deep levels themselves still lose money (0.618 −0.12 R, 0.786 −0.05 R). This is a
depth / selection effect, not a Fibonacci property.

## 4. Does observable price behaviour say which entry will work? (directive section 5)

Predictive rows 1813 (out-of-fold 1417, +$10-first base rate 51.1%).

| Model | Out-of-sample log-loss | In-sample log-loss | Gain vs baseline per trade [95%] | AUC (out of sample) |
|---|---:|---:|---|---:|
| baseline | 0.6845 | 0.6693 | +0.0000 [+0.0000, +0.0000] | 0.586 |
| +returns | 0.6853 | 0.6689 | -0.0008 [-0.0019, +0.0003] | 0.583 |
| +candle | 0.6877 | 0.6686 | -0.0032 [-0.0076, +0.0015] | 0.584 |
| +volatility | 0.6872 | 0.6692 | -0.0027 [-0.0061, +0.0003] | 0.582 |
| +impulse | 0.6864 | 0.6685 | -0.0019 [-0.0049, +0.0009] | 0.583 |
| +retracement | 0.6873 | 0.6686 | -0.0028 [-0.0069, +0.0014] | 0.579 |
| +levels | 0.6862 | 0.6688 | -0.0017 [-0.0056, +0.0025] | 0.585 |
| +mtf | 0.6883 | 0.6683 | -0.0038 [-0.0095, +0.0017] | 0.583 |
| +regime | 0.6854 | 0.6686 | -0.0009 [-0.0029, +0.0012] | 0.585 |
| +all | 0.7056 | 0.6637 | -0.0211 [-0.0315, -0.0106] | 0.565 |

The baseline (stop distance, cost, ATR, session) gives AUC 0.59, essentially the geometry. **Every one of the eight
groups of price-behaviour variables makes the out-of-sample prediction worse**, and all of them together are
significantly worse (−0.021 log-loss per trade), while their in-sample fit improves. That gap is the explanation asked
for: the variables fit noise in the training folds and carry no information about the next +$10 that the stop distance
does not already carry. Spread, bid / ask, data freshness and latency could not be tested: the feed has none.

## 5. Impulses and retracements (directive section 4; descriptive)

| Impulse / retracement (descriptive; uses the future) | 10% | 25% | median | 75% | 90% |
|---|---:|---:|---:|---:|---:|
| impulse size ($ at $4,000) | 8.98 | 11.56 | 15.72 | 22.88 | 32.95 |
| impulse size (ATR) | 2.45 | 2.71 | 3.23 | 3.98 | 5.01 |
| bars from origin to detection | 2.00 | 3.00 | 6.00 | 12.00 | 16.00 |
| bars from origin to the first pullback | 4.00 | 5.00 | 9.00 | 14.00 | 17.00 |
| largest body / impulse | 0.25 | 0.31 | 0.38 | 0.47 | 0.58 |
| deepest retracement before a new extreme / window end (share of impulse) | 0.28 | 0.39 | 0.62 | 1.04 | 1.64 |
| bars spent retracing | 1.00 | 2.00 | 6.00 | 16.00 | 16.00 |
| ATR change during the retracement | 0.73 | 0.90 | 1.00 | 1.08 | 1.21 |
| extreme to the nearest opposing level (ATR) | 0.34 | 0.89 | 2.13 | 4.11 | 7.30 |
| best move from the earliest price within 24 h ($) | 4.58 | 10.42 | 22.98 | 41.00 | 65.49 |

New extreme within the window 66.1%; a higher low formed 82.4%; structure held 71.5%; opportunities 4223, with a pullback 4184.

A typical impulse is $16 (3.2 ATR) built in 6 bars; the median retracement goes 62% of the way back before the impulse
extends or the 4 h window ends, and in 28% of cases the structure (the impulse origin) is lost within 4 h. The median
best move from the earliest price within 24 h is $23, so $10-$20 moves are common; the problem is that the adverse
move to the structural stop comes first as often as geometry predicts.

## 6. The 18 November screenshot (directive section 11)

From `research/results/b31b_w5_case_2026-11-18.json` and the 5-minute bars; times UTC (MT5 = +2 h). The outcomes in the
table are hindsight checks of fixed entries, not rules; no price below is claimed to have been identifiable in advance
unless a registered rule produced it.

1. **Structure at the time.** M15 lower highs and lower lows all day; the M30 swing highs were 3786.59 → 3789.10, a
   *higher* high made by the 13:00 spike, so the registered M30 trend was not bearish. Price had stayed more than 2 ATR
   below its 16-bar high continuously from 17:00 to 21:15: one extended decline, not a fresh impulse. The registered
   detector therefore had **no new opportunity** at the screenshot; the next one was the UP impulse at 23:15.
2. **Prices available without hindsight at ~20:57.** The market (feed mid ~3729.5-3730); a sell limit at the broken
   zone 3729.40 (touched from 20:30); the zone's far side 3734.17 (never touched: the bounce peaked at 3732.74).
3. **A better pullback price?** The bounce high 3732.74 (20:40) is only known afterwards; no registered rule placed an
   order there.
4. **An earlier entry?** A sell at the 19:00 close (3729.64, stop 3740.37) reached +$10 first (3719.19 at 19:35), but
   it came *before* the break of 3729.40 and no tested rule produces it. The sell on the break itself (19:15 close
   3727.99) missed +$10 by $1.20 and was stopped at 23:20.
5. **Waiting for confirmation?** Worse: the 20:45 close 3724.93 with the stop above 3732.74 was stopped at 23:05.
6. **Structural invalidation.** Above the broken zone 3734.17 (+0.2 ATR = 3735.84) for the local structure; above the
   lower high 3750.66 (3752.33) for the larger one. Both were taken out (23:05 and 00:40) before +$10 (02:55).
7. **Executable bid / ask.** Not available: no broker feed, and the research feed is a mid. The modelled cost was
   $0.77 / oz (New York afternoon), not broker-verified.
8. **Did any alternative entry reach +$10 before its stop?** No short from 19:15 on did, at either stop. The only ones
   that did were the anticipatory 19:00 short and the *long* at 3729.54 (+$10 at 23:20, +$20 at 00:35).
9. **Against a matched random entry?** 20 random sells at closes in the same 4 h window with the same $6.30 stop: 5
   reached +$10 first and 15 were stopped. The screenshot short did no better than random sells.

The registered W5 orders of that night (the 23:15 UP impulse) also illustrate section 1: the shallow entries (market,
0.236, 0.3, 1 ATR) reached +$10, the deeper limits filled during the 02:45 collapse and were stopped.

## 7. What W5 could not test, and what would

- **Tick-level ordering and bid / ask** (B5c): the trades were raced on 15-minute bars refined by 5-minute bars, on mid
  prices. The registration declares a re-race of every candidate's trades on Dukascopy ticks; with no candidate it would
  test the null, and it needs the ticks from the operator's computer (Dukascopy refuses cloud addresses).
- **The broker's prices, spread and contract size** (MetaApi + specification): until then sizing assumes 100 oz / lot.
- **Spread / latency features**: no data.

## Verification

- `tests/test_research_w5entry.py` (17 tests): a hand-worked impulse with every mechanism's price and a fill; J's first
  completion, including a dip that starts after the first bar past t1; t1 on a bar that only equals the extreme; every
  impulse a first crossing of 2 ATR (three seeded walks); E's level a swing confirmed by t0 inside the impulse (three
  seeded walks); the EMA limit priced from closed bars only; R1 draws inside the same window with the same stop
  distance; R3 prices inside the eligible zone with the structural stop; an exhaustive truncation check on two seeded
  M5 / M15 walks (every order rebuilt from the bars closed by its own decision). That check caught a real defect before
  any run (H's M5 window depended on how much data existed); it was fixed and recorded in amendment A1.
- Mutation test (12 mutants of the registered rules, each on a scratch copy against the test file): 11 killed. The
  survivor, "E may use a swing confirmed after t0", is an equivalent mutant: a 3 / 3 pivot confirmed after t0 cannot also
  pass E's other conditions (the bars after a pivot high are lower, so the first of them is already t1 before the pivot is
  confirmed, or the level has no close beyond it by t1), and on the development data the mutated rule returns the same
  level for all 4,184 opportunities with a pullback (0 differences). Three other first-round survivors (the first-crossing
  rule, an equal high at t1, J's later dip) led to the new tests above and are now killed.
- Full suite on this branch: 1,029 passed (local run, not CI).

## Files

`research/registrations/B31b-W5.json`, `quantum/research/w5entry.py`, `tests/test_research_w5entry.py`,
`research/results/b31b_w5_development_2026-11-19.json`,
`research/results/b31b_w5_trades_development_2026-11-19.csv.gz` (87,183 orders, no absolute prices),
`research/results/b31b_w5_case_2026-11-18.json`.

Reproduce: `python -m quantum.research.w5entry --part development --rd <research-data clone> --out dev.json --csv trades.csv`
