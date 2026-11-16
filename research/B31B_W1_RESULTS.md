# B31b-W1: modules A and B with a volume-neutral structure detector — step 1 result

Operator's workstream 1 (2026-11-15): *"Investigate volume-free break-of-structure detection. Preserve the original
structural logic wherever possible. Test detector firing rates before running strategy performance tests. Do not change
registered rules after observing evaluation results."*

Order of work:
1. Registration `research/registrations/B31b-W1.json`, committed `394703a15` before any code or run.
2. Code and tests, committed `2f65ed935` before any run: `quantum/research/b31w1.py`, 10 tests, 18 of 18 mutants killed.
3. Step 1 ran on the development partition (2020-01 → 2023-01, scored from 2020-04-01). Counts only; no trade outcome
   was printed, saved or inspected. Record: `research/results/b31b_w1_step1_2026-11-15.json`. A second run on a clean
   tree gave the identical file.

## 1. Answer

**DETECTOR INSUFFICIENT.** The volume-neutral detector fires as designed, but the full A / B sequence passed every
check only **7 times in 2.8 years** (A 2, B 5). The registered gate needs 30, so **step 2 was not run** and the
validation and holdout partitions stay sealed for this question. No A / B outcome has been looked at.

## 2. The detector works

The frozen engine ran unchanged on a copy of its features with `v = 1` and `vol_sma20 = 0`, so its three volume
conditions are always met and every other structural clause is its own.

| Structure events on 70,173 15m bars | BOS | MSS | CHoCH | Per 1,000 bars |
|---|---|---|---|---|
| As the research data is (no volume) | 0 | 937 | 624 | 22.3 |
| Volume-neutral | 1,232 | 937 | 624 | 39.8 |
| Live engine with futures volume, 1,500 bars to 14 Nov (PR #120) | 17 | 18 | 12 | 31.3 |

The volume-neutral rate is of the same order as the live engine's, and somewhat higher, as expected with the volume
filter removed.

## 3. Why A and B are still rare: the sequence, then the checks

| Stage, development 2020-04 → 2023-01 | Count |
|---|---|
| Rejected liquidity sweeps | 4,067 |
| ... followed within 8 bars by a structure event in the trade's direction | 351 (8.6%) |
| ... of which an MSS / CHoCH | 101 |
| A setups (MSS / CHoCH, higher timeframes not aligned, an FVG or order block to enter at) | 15 |
| B setups (any structure event, higher timeframes aligned, an FVG or order block) | 54 |

| Module | Setups | Repeats | Stop below $5 | Net R:R on the ladder below 1 | Opposing pool inside +$10 | Cost above 15% of the stop | Other | Limit not filled | Executed |
|---|---|---|---|---|---|---|---|---|---|
| A sweep reversal | 15 | 4 | 5 | 0 | 4 | 0 | 0 | 0 | **2** |
| B continuation after a grab | 54 | 15 | 2 | 13 | 14 | 3 | 1 | 1 | **5** |
| E session expansion (secondary) | 180 | 0 | 71 | 13 | 69 | 5 | 1 | 10 | 11 |

- **The sequence is the first limit.** Fewer than 1 rejected sweep in 11 is followed within two hours by a structure
  break in the trade's direction, and only a fifth of those also have the trend alignment and an entry zone the module
  needs: 69 setups in 2.8 years, about 25 a year.
- **The checks are the second.** Of the 50 setups that were not repeats, 18 had an opposing liquidity pool closer than
  +$10, 13 had a structural stop too wide for the ladder, and 7 had a stop under $5.
- **The ladder rule (operator's option a) did what it was meant to:** only 13 setups were rejected for reward, against
  the stop window of $5–8.4 that removed most setups in B31.

## 4. What this establishes

- Removing the volume condition does not make A and B testable: the sequence itself is rare on 15m gold. This agrees
  with the live count (PR #120: 3 of 86 rejected sweeps in 7 days had a trade-direction structure event within 8 bars).
- Nothing is known about whether A / B entries win: 7 trades cannot say, and they were not inspected.
- The live forward record (B31b-SHADOW-FWD) keeps recording A and B with real futures volume. At this rate it will
  collect a few A / B trades a year.

## 5. Limitations

- One detector was declared and run; no other was tried, by registration.
- The 2020-25 research history has no volume, so "volume-neutral" is the only form of the engine's rule it can carry.
- Distances are scaled by price / 4000, as in B31.
- Costs are the engine's model, not broker-verified (audit D1).
