# B31b-W2: why modules C, D and E produce so few trades — every setup, its fate and the reason

Operator's workstream 2 (2026-11-15): *"Retain original strategy definitions. Investigate why the available sample sizes
are low. Do not loosen filters merely to generate more trades. Report every rejected setup and rejection reason."*

Order of work:
1. Registration `research/registrations/B31b-W2.json`, committed `fcdfed47e` before any code or run.
2. Code and tests, committed `548344448` before any run: `quantum/research/b31w2.py` and an optional trace in
   `b31.run_module`, which records each setup's fate and reason and changes nothing else (tested).
3. First run on all four periods. It showed that the stop-distance table, built from distances rounded to the cent,
   disagreed with the $5 check by 2 setups in two periods. It also showed that the recorded reason is only the first
   failed check, which hides setups that fail several. Both fixed in `110bcb7a0` (see section 6), before the second run.
4. Second run: every setup's fate and every count were identical to the first run (8,031 setups, CSV byte-identical).

Records:
- `research/results/b31b_w2_2026-11-18.json`: counts per period, module and rule.
- `research/results/b31b_w2_setups_2026-11-18.csv`: one row per setup, with distances only (no prices).
- 8 lines in `research/trials.jsonl` (both runs, append-only).

**No trade outcome was printed, saved or inspected.**

The two reward rules are compared side by side; nothing else differs between them.
- **B31's rule:** net R:R at TP1 +$10, `(10 − cost) / (D + cost) ≥ 1`.
- **The ladder rule:** the operator adopted it on 2026-11-15 and the live B31b-SHADOW-FWD uses it. Net R:R at +$15, the
  mean of +$10 / +$15 / +$20: `(15 − cost) / (D + cost) ≥ 1`.

Under B31's rule the counts reproduce B31 exactly (development C / D / E: 23 / 36 / 4 executed), so the modules are
B31's own.

## 1. Answer

The modules are not rare; they fire 1,600–3,700 times in 2.8 years. Almost all of them fail the eligibility checks.
Most fail several checks at once, and two causes dominate:

1. **The structural stop is shorter than the trading cost allows.** With a round-trip cost of $0.77–0.97 per oz, the
   rule "cost at most 15% of the stop" needs a stop of at least **$5.1–6.5**. The modules' structural stops are a median
   **$4.9 (C), $3.7 (D) and $5.5 (E)** on development. More than half fail the cost check: 58% of C, 75% of D, 44% of E.
   Every setup that fails the $5 minimum also fails the cost check, so the $5 rule never blocks a setup alone.
2. **An opposing liquidity level or VWAP sits inside +$10.** On development:
   - C and E: the nearest opposing pool is a median **$6.7 (C)** and **$5.8 (E)** from the entry. 67% of C and 76% of E
     have a pool closer than the first target.
   - D: its own reversion target, VWAP, is closer than $10 in **88%** of setups. A 2-sigma VWAP fade in a range is a
     move of a few dollars, not +$10.

On top of that, a third of C and D setups repeat an idea already open (same side, within 4 hours and $15).

What passes every check, and what then executes, per period:

| Period | Module | Setups | Repeats | Pass every check (ladder rule) | Executed: B31 rule | Executed: ladder rule |
|---|---|---|---|---|---|---|
| Development 2020-04 → 2023-01 (2.8 y) | C | 1,542 | 589 | 115 (12%) | 23 | 48 |
| | D | 2,003 | 664 | 54 (4%) | 36 | 54 |
| | E | 174 | 0 | 20 (11%) | 4 | 10 |
| Validation 2023-04 → 2024-06 (1.25 y) | C | 718 | 281 | 46 (11%) | 7 | 18 |
| | D | 868 | 291 | 5 (1%) | 2 | 5 |
| | E | 84 | 0 | 5 (6%) | 0 | 1 |
| Holdout 2024-09 → 2025-12 (1.3 y) | C | 791 | 299 | 82 (17%) | 17 | 33 |
| | D | 864 | 289 | 39 (7%) | 21 | 39 |
| | E | 87 | 0 | 22 (25%) | 3 | 7 |
| 2026, Mar → Nov (0.7 y) | C | 424 | 135 | 70 (24%) | 19 | 41 |
| | D | 434 | 144 | 39 (13%) | 21 | 39 |
| | E | 42 | 0 | 11 (26%) | 1 | 7 |

The percentages are of the setups that were not repeats. C's orders that pass every check then often go unfilled: the
limit at the broken level is not retested within 8 bars for 65 of 115 on development.

## 2. The stages before a setup exists (development)

| Module | Stage | Count |
|---|---|---|
| C breakout and retest | First crossings of a pool level in a day | 6,649 |
| | ... back inside within 3 bars (a sweep, not a break) | 4,067 |
| | ... 3 closes beyond (an accepted break) | 2,582 |
| | ... with an FVG in the breakout leg (= a C setup) | 1,542 |
| D VWAP reversion | Ranging bars | 31,294 |
| | First bars of a 2-sigma deviation | 2,406 |
| | ... closed back inside within 3 bars | 2,004 |
| | ... vetoed by a strong displacement body | 1 |
| | = D setups | 2,003 |
| E session expansion | Trading days | 727 |
| | Days whose first Asia-range crossing came in London or New York | 712 |
| | ... a sweep (rejected) | 504 |
| | ... of which with a structure shift and an entry zone | **8** |
| | ... a break (accepted) | 208 |
| | ... of which with an FVG in the breakout leg | 166 |

E is almost entirely its breakout branch: its sweep branch needs the same sweep → structure-shift sequence as module A,
which W1 found rare on this volume-free history (`research/B31B_W1_RESULTS.md`).

## 3. Every rejection and its reason

**Recorded reason** = the first check the setup failed, in B31's order: stop → reward → cost → room. That is the reason
the live record and the CSV carry.

Development, ladder rule (B31's rule in brackets where it differs):

| Module | Measured (not repeats) | Stop below $5 | Net R:R below 1 | Cost above 15% of the stop | Opposing pool / VWAP inside +$10 | Not filled in 8 bars | Retest broke back through | Executed |
|---|---|---|---|---|---|---|---|---|
| C | 953 | 499 | 78 (214) | 55 | 206 (125) | 65 (37) | 2 (0) | 48 (23) |
| D | 1,339 | 922 | 28 (123) | 80 | 255 (178) | 0 | 0 | 54 (36) |
| E | 174 | 71 | 12 (40) | 5 | 66 (47) | 10 (7) | 0 | 10 (4) |

**Each check on its own** (a setup can fail several), development, ladder rule:

| Module | Fails stop | Fails reward | Fails cost | Fails room | Fails room and nothing else | Fails reward and nothing else | Passes every check |
|---|---|---|---|---|---|---|---|
| C | 499 (52%) | 78 (8%) | 554 (58%) | 635 (67%) | 206 | 44 | 115 (12%) |
| D | 922 (69%) | 28 (2%) | 1,002 (75%) | 1,202 (90%) | 255 | 6 | 54 (4%) |
| E | 71 (41%) | 12 (7%) | 76 (44%) | 132 (76%) | 66 | 7 | 20 (11%) |

The same pattern holds in every period (results file, `checks`):
- Room is the most common failure: 43–95% of setups.
- Cost / stop come next: 21–86%.
- Reward fails least: 1–23%.

In 2026 the stops are wider, so fewer setups fail cost / stop and more fail reward.

**The ladder rule** (operator's option a) did what it was meant to do: reward rejections fell by 64% for C (214 → 78)
and 77% for D (123 → 28). Many of the setups it let through then met an opposing pool inside +$10, so room rejections
rose. Executed trades roughly doubled.

Stop distances against the windows the rules allow (development; percentiles in $ at $4,000):

| Module | 10% | 25% | 50% | 75% | 90% | Below $5 | $5 to $8.46 (B31 rule's limit) | $8.46 to $13.46 (ladder rule's limit) | Above $13.46 |
|---|---|---|---|---|---|---|---|---|---|
| C | 1.36 | 2.79 | 4.86 | 7.89 | 12.42 | 499 | 245 | 132 | 77 |
| D | 1.62 | 2.39 | 3.73 | 5.53 | 8.03 | 922 | 299 | 91 | 27 |
| E | 2.57 | 3.87 | 5.50 | 8.07 | 10.27 | 71 | 63 | 28 | 12 |

Every one of the 8,031 setups, with its distances, fate and reason under both rules, is in the CSV.

## 4. How often the modules would trade, and what that means for the live test

Executed trades per week, before one-position-at-a-time across modules (each module holds one position at a time on
its own):

| Period | B31 rule, C + D + E | Ladder rule, C + D + E |
|---|---|---|
| Development | 0.43 | 0.76 |
| Validation | 0.14 | 0.37 |
| Holdout | 0.60 | 1.15 |
| 2026 | 1.16 | 2.45 |

The live forward test (B31b-SHADOW-FWD) uses the ladder rule. Your acceptance gate needs at least 100 completed forward
trades. At these rates that takes about **40 weeks at the 2026 rate and about 90 weeks at the 2024-25 rate**. The live
record so far fits the history: 40 setups in its first 3 trading days. 31 were repeats, 7 were rejected (room 4,
reward 2, stop 1) and 2 executed (both module D). Their results stay in the forward record (B31b-SHADOW-FWD), which
is judged only at 100 trades.

## 5. What this establishes

- **The low counts are the arithmetic of the objective on 15m gold, not a defect in the detectors.**
  - C, D and E find setups.
  - Their natural invalidation is usually closer than the cost allows.
  - Their path to +$10 is usually blocked by a level the market is likely to react to, or, for D, by the VWAP the
    setup is aiming for.
- **No filter was loosened, no threshold was tried, and no outcome was looked at**, as instructed. The registration
  forbids reading any of this as a reason to change a rule.
- **Module D is structurally a small-target setup:** in 88% of its setups the target it fades to is less than $10 away.
- **E's sweep branch is limited by the same structure-shift rarity W1 measured for A** (8 of 504 sweeps).

## 6. Limitations and corrections

- **First run (code `548344448`).** The stop-distance table used distances rounded to the cent. In validation and
  holdout D, 2 setups landed on the other side of the $5 boundary from the check (478 vs 480, 349 vs 351). The
  per-check table did not exist yet. Commit `110bcb7a0` fixed and added both before the second run. All fates and
  counts were identical between the runs. Both runs' trial lines stay in the log.
- **Rates are per module,** without one-position-at-a-time across modules: combined live rates can only be lower.
- **Costs** are the engine's session model, not broker-verified (audit D1).
- **Distances** are scaled by price / 4000, as in B31.
- **The 2026 period** is unsealed and was read by B31 before.
