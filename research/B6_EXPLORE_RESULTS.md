# Phase B6-explore — do site signals win more when the higher timeframes agree? (live window, 2026-11-01)

**Verdict: NO.**
- Taking the site's signals only when the 1-hour and 4-hour signals agree did **worse** than random entries:
  36.5% at ±$13 (n 74, z −2.8).
- Agreement with the 1-hour signal alone made no difference (48.5% vs 48.0% against it).
- The only group above random was a 5-minute signal backed by the 15-minute one: 53.9% (n 76). It is not
  significant (z +0.5; 95% interval 43–65%).
- All site signals together reached TP first 43% of the time, against about 50% for random entries.

## Why this was tested

The operator's winning trade (29 Oct 2026, SELL 0.5 lot, 14:45 UTC) matched SHORT signals on the site's 5m and 15m
arms, with the 1-hour signal also SHORT. The losing trade (30 Oct, BUY, 05:10 UTC) went against the 1h and 15m
signals. "Only trade when the timeframes agree" was the natural rule to check.

## Declared before running

The study is declared in `quantum/research/b6_mtf_live.py`, committed at `86f95bd58` before the run.

**Signals:** every 5m and 15m signal the site's arms recorded, 2026-09-28 → 10-30, deduplicated.

**Context:** the latest 1h, 4h and 15m signal decided at or before each signal, within 24 h, 72 h and 60 min.

**Outcomes:**
- +$13 before −$13 (the operator's $650 / $650 at 0.5 lot) and +$10 before −$10;
- spot 5-minute paths over one trading day, with B2's fills;
- one position at a time;
- compared with random entries matched to each group's long / short mix.

## Results

| Group | Target / stop | n | TP first | 95% interval | Random, same mix | z |
|---|---|---|---|---|---|---|
| All site signals | ±$13 | 144 | 43.1% | 35.3–51.2% | 49.6% | −1.57 |
| All site signals | ±$10 | 199 | 42.7% | 36.0–49.7% | 50.3% | −2.13 |
| 1h agrees | ±$13 | 101 | 48.5% | 39.0–58.1% | 52.4% | −0.78 |
| 1h agrees | ±$10 | 149 | 45.0% | 37.2–53.0% | 53.2% | −2.01 |
| 1h against | ±$13 | 100 | 48.0% | 38.5–57.7% | 47.1% | +0.18 |
| 1h against | ±$10 | 148 | 44.6% | 36.8–52.6% | 47.4% | −0.68 |
| **1h and 4h agree** | ±$13 | 74 | **36.5%** | 26.4–47.9% | 52.8% | **−2.81** |
| 1h and 4h agree | ±$10 | 101 | 40.6% | 31.5–50.3% | 53.1% | −2.52 |
| 5m backed by 15m | ±$13 | 76 | 53.9% | 42.8–64.7% | 51.2% | +0.47 |
| 5m backed by 15m | ±$10 | 98 | 54.1% | 44.2–63.6% | 50.7% | +0.67 |

## Reading

1. **Full agreement came late.** By the time every timeframe pointed the same way, the move was usually
   well under way. The next ±$13 then went against it more often than not. This matches B5's finding that price gives
   a little back after a strong one-sided hour.
2. **The site's signals are not a TP-first edge.** Together they did worse than random entries. That agrees with the
   44.8% measured on the forward record earlier (`HC_PHASE1_AUDIT_AND_BASELINE.md`).
3. **Limits.**
   - Five weeks and one market phase: gold fell through late October.
   - Groups of 74–199 trades.
   - The window is the one the site already displays, so nothing here can be validated or registered.
   - The operator's exact trade type (5m + 15m + 1h together) was **not** carved out afterwards: picking a subset
     after seeing results is exactly the cherry-picking the research rules forbid.

Records:
- `research/results/b6_mtf_live_2026-11-01.json`;
- 10 lines in `research/trials.jsonl` (phase `B6-explore`, partition `live-window-2026`).
