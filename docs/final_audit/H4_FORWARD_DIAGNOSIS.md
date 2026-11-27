# H4 forward diagnosis (2026-11-26)

**Answer to the operator's three questions, on the forward (paper) record:**

1. **Why do the entries lose?**
   - The entries show no directional edge. On every timeframe, their chance of reaching TP1, TP2, +$10, +$15 or +$20
     before the stop is at or below that of matched random entries. No difference survives a multiple-testing
     correction.
   - Gross expectancy before costs is about zero or negative: 5m −0.037 R, 15m −0.007 R, 1h −0.270 R.
2. **Are the exits cutting profitable trades?**
   - Not on balance. On 5m, the timeframe with most trades, holding the flipped trades instead would have been worse:
     −0.246 R against −0.219 R realised, and 165 of the 265 would have reached the stop.
   - On 15m and 1h, holding would have been better on average, on small samples.
   - Removing the flip from every trade gives no positive expectancy on 5m, 15m, 30m or 1h.
3. **Do the costs destroy the edge?** There is no gross edge for them to destroy on 5m, 15m or 1h.
   - On 5m the cost is 0.099 R per trade: the median stop is $9.23 and the cost of record about $0.90. It takes
     −0.037 R gross to −0.136 R net.
   - 30m is the only H4 timeframe positive both before and after costs: +0.072 R gross, +0.032 R net, n = 71.
   - 4h is positive on 8 trades only.

**The $15–$20 objective (unchanged).** The share of trades that reached +$15 / +$20 before the original stop:

| Timeframe | Reached +$15 / +$20 | Median stop |
|---|---|---|
| 5m | 38 % / 33 % | $9.23 |
| 15m | 54 % / 48 % | $16.34 |
| 30m | 63 % / 55 % | $22.12 |
| 1h | 63 % / 59 % | $43.01 |
| 4h | 8 of 8 | $94.40 |

Random entries with the same stop reach the same targets as often, or more often. The rate follows the width of the
stop, not the entry.

**Nothing here changes, tunes or proposes a rule.** The counterfactuals explain the record; they are not candidates,
and none may be adopted from this window (CLAUDE.md "Do not tune"; the operator: "Do not modify the frozen H4 strategy
merely to improve these numbers"). The frozen engine, H4's rules, stops and targets are untouched.

## 1. Data and method

| Item | Value |
|---|---|
| Records | `forward-ledger` `624ed94d2` (26 Nov 13:53 UTC), `holdout/<tf>_h4.json`, closed trades of freeze key `1f88aad357497da4:4440d52587f5cc6b` (15 Nov 11:46 → 26 Nov) |
| Bars | `market-data` `092e2c41e`: XAU/USD 5m / 15m / 30m / 60m (Twelve Data mid prices), market-shut quotes removed (`sources.trading_week_only`); 4h = 1h on the New York session grid, as the engine builds it |
| Tool | `audit/tools/h4_forward_diagnosis.py`; tests `tests/test_h4_forward_diagnosis.py` (44) |
| Exit replica | the exit model of `quantum/backtest.simulate` re-implemented without the flip. On 40 random synthetic paths with gaps it reproduces `backtest.simulate` exactly. On the records it reproduces 260 of 261 non-flip exits (one mismatch, §6) |
| Races | 5m bars from the entry's close: each target against the ORIGINAL stop; the stop wins a shared bar; undecided within 7 days = excluded |
| Random twins | for each trade, every other bar close of the arm's timeframe in the same UTC hour ±1, with the same direction, stop / TP1 / TP2 distances, cost and follow-up time. Two pools: the forward window, and the last 60 days of bars (regime-mixed, larger) |
| Test | 2,000 pseudo-ledgers (one twin per trade). The p-value is the normal tail of that matched null (the empirical one is in the JSON). Not tested: fewer than 5 decided trades, fewer than 20 distinct twins per trade (median), or a degenerate null |
| Multiplicity | Holm (family-wise) and Benjamini-Hochberg (false discovery) over every p-value in the run: H4 alone, and all seven forward arms |
| Command | `PYTHONPATH=. python3 audit/tools/h4_forward_diagnosis.py --ledger <fl> --bars <md> --arms h4 --random 2000 --pool-days 0` (and `--pool-days 60`; `--arms treatment,control,challenger,h2,h3,h4,h5`), seed 20261126 |

## 2. The record and its exits

| TF | Trades | Net R | Gross R | Cost R | FLIP | SL | TP2 | BE / BE_GAP | Mean R: FLIP / SL / TP2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 5m | 413 | −0.136 | −0.037 | 0.099 | 265 (64 %) | 57 | 62 | 25 / 4 | −0.219 / −1.073 / +0.914 |
| 15m | 149 | −0.065 | −0.007 | 0.057 | 92 (62 %) | 20 | 29 | 7 / 1 | −0.180 / −1.069 / +0.940 |
| 30m | 71 | +0.032 | +0.072 | 0.040 | 39 (55 %) | 14 | 13 | 5 / 0 | −0.075 / −1.050 / +1.436 |
| 1h | 38 | −0.293 | −0.270 | 0.024 | 18 (47 %) | 11 | 6 | 3 / 0 | −0.256 / −1.028 / +0.672 |
| 4h | 8 | +0.432 | +0.443 | 0.011 | 4 | 0 | 4 | 0 | −0.253 / — / +1.116 |

**Cost:**
- Only 11 of the 413 5m trades (and 4 of 149 on 15m) were gross gains turned into net losses by the cost.
- The cost is the system's cost of record (0.77–0.97 per ounce), an assumption until the broker data arrives
  (`BROKER_COST_VALIDATION.md`).

## 3. The flip exits: what holding would have done

The flipped trades were re-run with the same model and without the flip, up to 7 days.

| TF | Flips | Realised R | Held R (decided) | Held: SL / TP2 / BE / open | Held better / worse |
|---|---:|---:|---:|---|---|
| 5m | 265 | −0.219 | −0.246 | 165 / 52 / 44 / 4 | 82 / 183 |
| 15m | 92 | −0.180 | −0.101 | 51 / 23 / 14 / 4 | 35 / 57 |
| 30m | 39 | −0.075 | −0.158 | 22 / 12 / 3 / 2 | 15 / 24 |
| 1h | 18 | −0.256 | −0.176 | 8 / 6 / 1 / 3 | 9 / 9 |
| 4h | 4 | −0.253 | −0.606 | 3 / 1 / 0 / 0 | 1 / 3 |

**No flip on any trade:**
- Mean R per timeframe (decided): 5m −0.159, 15m −0.014, 30m −0.009, 1h −0.263, 4h +0.255 (n 8).
- None is positive with a sample worth reading.

## 4. Targets before the original stop, time to target, excursions

| TF | TP1 first | TP2 first | +$10 | +$15 | +$20 | Median hours to +$10 / +$15 / +$20 | MFE before the stop (median) | MAE in the trade (median) |
|---|---|---|---|---|---|---|---|---|
| 5m | 45.7 % (41.0–50.6) | 31.3 % | 46.0 % | 38.0 % (33.5–42.8) | 32.5 % (28.2–37.2) | 0.6 / 0.9 / 1.5 | $8.60 (0.99 R) | 0.44 R |
| 15m | 51.4 % | 38.0 % | 60.4 % | 53.7 % (45.7–61.5) | 47.7 % (39.8–55.6) | 0.7 / 1.2 / 1.8 | $17.81 (1.03 R) | 0.41 R |
| 30m | 48.6 % | 42.0 % | 70.4 % | 63.4 % (51.8–73.6) | 54.9 % (43.4–66.0) | 0.7 / 1.5 / 1.7 | $27.55 (1.00 R) | 0.37 R |
| 1h | 47.2 % | 40.0 % | 68.4 % | 63.2 % (47.3–76.6) | 59.5 % (43.5–73.7) | 1.2 / 1.9 / 3.3 | $27.20 (0.60 R) | 0.48 R |
| 4h | 5 of 8 | 5 of 8 | 8 of 8 | 8 of 8 | 8 of 8 | 0.7 / 1.5 / 2.5 | $136.45 (1.16 R) | 0.40 R |

- Brackets are Wilson 95 % intervals.
- A target counts only if it was touched before the original stop: never moved, never at break-even.

## 5. Entries against their matched random twins

The table gives the recorded rate, the twins' mean, and the normal-tail p-value. Holm is for the H4 family.

| TF | Measure | Recorded | Twins, forward window | p | Holm | Twins, 60 days | p | Holm |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 5m | TP1 first | 0.457 | 0.476 | 0.40 | 1.0 | 0.466 | 0.70 | 1.0 |
| 5m | TP2 first | 0.313 | 0.355 | 0.045 | 0.81 | 0.338 | 0.25 | 1.0 |
| 5m | +$15 first | 0.381 | 0.412 | 0.16 | 1.0 | 0.393 | 0.59 | 1.0 |
| 5m | +$20 first | 0.325 | 0.354 | 0.18 | 1.0 | 0.328 | 0.89 | 1.0 |
| 5m | no-flip R | −0.159 | −0.042 | 0.14 | 1.0 | −0.114 | 0.53 | 1.0 |
| 15m | TP1 first | 0.514 | 0.528 | 0.68 | 1.0 | 0.498 | 0.69 | 1.0 |
| 15m | +$15 first | 0.537 | 0.567 | 0.40 | 1.0 | 0.531 | 0.88 | 1.0 |
| 30m | TP1 first | 0.486 | 0.514 | 0.56 | 1.0 | 0.492 | 0.91 | 1.0 |
| 30m | +$15 first | 0.634 | 0.630 | 0.95 | 1.0 | 0.620 | 0.81 | 1.0 |
| 1h | TP1 first | 0.472 | not tested (9 twins) | — | — | 0.549 | 0.33 | 1.0 |
| 1h | +$15 first | 0.632 | not tested | — | — | 0.715 | 0.24 | 1.0 |
| 4h | +$15 first | 1.000 | not tested (3.5 twins) | — | — | 0.863 | 0.26 | 1.0 |

**Families:**

| Family | Twin pool | Tests | Smallest Holm | Smallest BH |
|---|---|---:|---:|---:|
| H4 alone | forward window | 18 | 0.81 | 0.54 |
| H4 alone | 60 days | 30 | 1.0 | 0.98 |
| All seven arms | forward window | 54 | 1.0 | 0.72 |
| All seven arms | 60 days | 66 | 1.0 | 0.995 |

- **No arm on any timeframe differs from its random twins after correction.**
- Every measure and arm is in the evidence JSON.

## 6. Limits

- **Eleven days.** The window covers one regime. Trades overlap, so the intervals, which treat trades as independent,
  are too narrow if anything. 1h (38 trades) and 4h (8) cannot show an effect of any useful size.
- **One mismatch.** The 5m trade opened 20 Nov 21:45 UTC: the ledger's TP1 fill (≈3576.12) implies the engine saw
  the 22 Nov 23:00 bar open at ≈3576.12. The store's copy of that bar now opens at 3533.05.
  - The bar was revised after the run (the R14 point-in-time issue).
  - The record stands as recorded; the diagnosis uses the stored bar.
- **Mid prices.** Twelve Data mid prices with the cost of record. No bid / ask, no broker fills, no swap. The broker
  cost validation is still BLOCKED on the operator's MT5 data.
- **The 60-day pool** includes weeks before the forward test. It is a larger but regime-mixed null; the two pools
  agree.
- **Diagnostic only.** "Held" and "no flip" are what the recorded trades would have done; they are not tested rules.
  Adopting either would be selection on this window.

## 7. Evidence

- `evidence/h4_forward_diagnosis_h4_forward_pool.json` / `.txt`: H4, forward-window twins.
- `evidence/h4_forward_diagnosis_h4_60d_pool.json` / `.txt`: H4, 60-day twins.
- `evidence/h4_forward_diagnosis_all_arms_forward_pool.json` / `.txt`: seven arms, forward-window twins.
- `evidence/h4_forward_diagnosis_all_arms_60d_pool.json` / `.txt`: seven arms, 60-day twins.
