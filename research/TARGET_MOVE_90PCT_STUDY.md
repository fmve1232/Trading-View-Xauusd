# Can the system give 90% of trades a $10–20 move in the signalled direction? (measured 2026-11-01)

**Operator's target:** "more than 90% of trades should move at least $10–20 in the same direction from the price
where the decision triggers."

**Method.** `audit/tools/target_move_study.py`, read-only; nothing was changed or tuned.

- **Path data:** 5-minute XAU/USD bars (Twelve Data), 2026-09-09 → 2026-10-30.
- **Starting point:** for each trigger, the first 5-minute bar after the trigger bar closes, at the trigger price.
- **Outcome:** did price reach **+$a** in the signalled direction before it reached **−$b** against it, within one
  day (or three days)?
- **Ties:** a 5-minute bar touching both levels counts as **not reached**, unless it opened beyond the target.
- **Ranges:** the brackets are Wilson 95% ranges.

**Random comparison.** "random" = 4,000 random 5-minute entries in the same window, long and short separately,
weighted to the same long / short mix as the decision source. The period was falling (gold ≈ 4,170 → 3,890), so
random **shorts** did better than random longs. That is the trend, not skill.

## 1. The core fact: the answer depends on how far price may go against you

For a price path with no edge, the chance of reaching +$a before −$b is **b ÷ (a + b)**:

| Target | Room against the trade | A coin flip wins | Win rate needed to break even after costs (≈ $0.8 per oz) |
|---|---|---|---|
| +$10 | −$10 | 50% | 54% |
| +$10 | −$30 | 75% | 77% |
| +$10 | −$90 | **90%** | **91%** |
| +$20 | −$20 | 50% | 52% |
| +$20 | −$50 | 71% | 73% |

**"90% of trades reach +$10" is easy if you allow $90 against you:** a random entry already does it. But each loss
then costs 9× each win, and the result is a loss after costs. The goal only means something with a small room
against the trade, for example 90% at +$10 before −$10. That would be an extraordinary edge: 40 points above a coin.

## 2. Measured, one-day horizon

| Decision source | Measured (of all triggers: long / short) | +$10 before −$10 | +$10 before −$30 | +$10 before −$90 | +$20 before −$20 | +$20 before −$50 |
|---|---|---|---|---|---|---|
| **Recorded forward trades** (real time, all arms, 5m + 15m) | 600 of 670 (307 long / 363 short) | **45%** (41–49) · random 50% | **76%** (73–79) · random 75% | **84%** (80–86) · random 85% | **47%** (43–51) · random 50% | **61%** (57–65) · random 67% |
| H4 playbook, 15m | 961 of 994 (470 long / 524 short) | **48%** (45–51) · random 50% | **73%** (70–76) · random 75% | **85%** (82–87) · random 85% | **47%** (44–50) · random 50% | **66%** (62–68) · random 67% |
| H4 playbook, 5m | 2719 of 2798 (1341 long / 1457 short) | **48%** (46–50) · random 50% | **75%** (73–76) · random 75% | **86%** (84–87) · random 85% | **47%** (45–49) · random 50% | **66%** (65–68) · random 67% |
| Engine BUY / SELL (treatment), 5m | 191 of 200 (9 long / 191 short) | **57%** (50–64) · random 56% | **82%** (76–87) · random 80% | **88%** (83–92) · random 89% | **56%** (49–63) · random 55% | **71%** (64–77) · random 73% |
| Engine BUY / SELL (treatment), 15m | 19 of 19 (0 long / 19 short) | **32%** (15–54) · random 56% | **58%** (36–77) · random 80% | **74%** (51–88) · random 89% | **37%** (19–59) · random 56% | **47%** (27–68) · random 74% |
| Challenger, 5m | 190 of 199 (7 long / 192 short) | **59%** (52–66) · random 56% | **82%** (76–87) · random 80% | **88%** (82–92) · random 89% | **56%** (49–63) · random 55% | **70%** (63–76) · random 73% |
| H3, 5m | 70 of 70 (3 long / 67 short) | **44%** (33–56) · random 56% | **71%** (60–81) · random 80% | **86%** (76–92) · random 89% | **51%** (40–63) · random 55% | **76%** (65–84) · random 73% |
| H3, 15m | 29 of 29 (1 long / 28 short) | **59%** (41–74) · random 56% | **76%** (58–88) · random 80% | **93%** (78–98) · random 89% | **52%** (34–69) · random 55% | **76%** (58–88) · random 73% |
| H5 high confidence, 5m | 87 of 87 (3 long / 84 short) | **54%** (44–64) · random 56% | **71%** (61–80) · random 80% | **78%** (68–86) · random 89% | **44%** (34–54) · random 55% | **57%** (47–67) · random 73% |
| H6, 5m | 191 of 200 (9 long / 191 short) | **57%** (50–64) · random 56% | **82%** (76–87) · random 80% | **88%** (83–92) · random 89% | **56%** (49–63) · random 55% | **71%** (64–77) · random 73% |
| H2, 5m | 16 of 16 (10 long / 6 short) | **44%** (23–67) · random 48% | **75%** (51–90) · random 73% | **75%** (51–90) · random 83% | **56%** (33–77) · random 48% | **75%** (51–90) · random 65% |
| Random entries, long | 3882 of 4000 (4000 long / 0 short) | **43%** (42–45) · random 43% | **69%** (68–71) · random 69% | **80%** (79–81) · random 80% | **43%** (42–45) · random 43% | **60%** (58–61) · random 60% |
| Random entries, short | 3882 of 4000 (0 long / 4000 short) | **56%** (55–58) · random 56% | **80%** (79–81) · random 80% | **89%** (88–90) · random 89% | **56%** (54–57) · random 56% | **74%** (73–75) · random 74% |

## 3. What it shows

1. **Every decision source scores what a random entry in the same direction scores**, at every target and every
   room. The recorded forward trades (600 measured, real time) reach +$10 before −$10 **45%** of the time
   (41–49%), against **50%** for random. They reach +$10 before −$90 **84%** of the time, against 85% random.
2. **The 85–94% figures in the "−$90" column are the coin-flip arithmetic, not skill.** Random shorts got 89% in
   this falling period.
3. **No source reaches 90% at a room you could trade**, and none is significantly better than random at any room.
   Some are worse: the 15m engine signals were shorts that reached +$10 before −$10 32% of the time, against 56% for
   random shorts (n 19).
4. **The three-day horizon gives the same picture** (`research/results/target_move_2026-11-01.json`).

## 4. What a real 90% would require, and how it would be tested

- **A measurable edge over b ÷ (a + b).** The event is now defined exactly ("+$10 before −$10 within one day",
  and so on). It becomes the target event of the Phase B2 tests. A candidate must beat the random comparison on
  development data, then on validation, then in a new forward test.
- **Evidence size.** To show ≥ 90% with a 95% lower bound of 85% needs **184** resolved trades. A run of 9 / 10
  proves only "more than 60%".
- **Honest expectation, from everything measured so far** (H4, B1's 100 trials, this study): **no tested approach
  moves the odds above a coin flip.** A 90% rate at a tradeable room is not supported by any evidence, and the site
  will not claim it.
