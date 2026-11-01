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


## 5. The operator's own trade: SL $500 / TP $1,000 at 0.5 lot

**Conversion.** 0.5 lot = 50 oz, so $1 of price = $50:

- **SL $500** = a **−$10** price move.
- **TP $1,000** = a **+$20** price move.

The event is: **+$20 before −$10.** No trade was left open after one day.

**What a coin flip would get.** 10 ÷ 30 = **33%**. Costs are about $0.8 per oz, i.e. about **$40 per trade** at
0.5 lot, so break-even is **≈ 36%**.

**Expected money per trade** at that win rate p: p × $1,000 − (1 − p) × $500 − $40.

| Source | Measured | Reached TP before SL | Random entries, same direction mix | Money per trade at that rate (0.5 lot) |
|---|---|---|---|---|
| Recorded forward trades (real time) | 600 | **29%** (25–33) | 34% | -108 |
| H4 playbook 15m | 961 | **31%** (28–34) | 33% | -76 |
| H4 playbook 5m | 2719 | **31%** (30–33) | 33% | -68 |
| Engine BUY / SELL 5m | 191 | **42%** (35–49) | 39% | +88 |
| Engine BUY / SELL 15m | 19 | **21%** (9–43) | 39% | -224 |
| Challenger 5m | 190 | **43%** (36–50) | 39% | +107 |
| H3 5m | 70 | **34%** (24–46) | 39% | -26 |
| H5 5m | 87 | **36%** (26–46) | 39% | -6 |
| H6 5m | 191 | **42%** (35–49) | 39% | +88 |
| Random entries, long | 3882 | **27%** (26–29) | 27% | -134 |
| Random entries, short | 3882 | **39%** (38–41) | 39% | +46 |

**Reading:**

- **No source beats random entries.** The recorded forward trades (29%) and the H4 playbook (31%) are *below* both
  random and break-even.
- **The 5m engine signal (42%, 35–49) is above break-even, but not above random entries in the same direction.**
  It was almost all shorts in a falling market, where random shorts already scored 39%. Its range contains the
  random rate, so this is the market's trend in this period, not skill.
- **For this trade a 90% rate would mean +$20 before −$10 nine times in ten, where a coin gets 33%.** Nothing
  measured is anywhere near that. A win rate of **≥ 45%** with this 2 : 1 geometry would already be clearly
  profitable (≈ +$135 per trade at 0.5 lot), and even that has not been shown.

**If 500 / 1000 means MT5 points** (1 point = $0.01, so SL −$5 / TP +$10): coin-flip 33%; recorded forward trades
30%; H4 31%; engine 5m 37% against 37% random. The same conclusion.


## 6. The operator's stated trade (2026-11-01): SL $500 / TP $100 at 0.5 lot

**Conversion.** 0.5 lot = 50 oz, so $1 of price = $50:

- **SL $500** = a **−$10** price move.
- **TP $100** = a **+$2** price move.

The event is: **+$2 before −$10**, a 1 : 5 reward:risk.

**Note:** a $10–20 move in the trade's direction is far more than this TP needs. At 0.5 lot, $10–20 of price is
$500–1,000 of profit.

**Benchmarks:**

- A coin flip wins **83.3%** (10 ÷ 12).
- Costs are about $0.8 per oz, i.e. **$40 per trade** at 0.5 lot: **40% of every winning trade**.
- Money per trade at win rate p: p × $100 − (1 − p) × $500 − $40. It is positive only when p > 540 ÷ 600 =
  **90.0%**.

**So for this trade, 90% is not a high-quality target: it is break-even.**

| Source | Measured | Reached TP before SL (1 day) | Random entries, same direction mix | Money per trade at that rate (0.5 lot) |
|---|---|---|---|---|
| Recorded forward trades (real time) | 600 | **80.2%** (76.8–83.2) | 82.8% | -59 |
| H4 playbook 15m | 961 | **80.0%** (77.4–82.4) | 82.8% | -60 |
| H4 playbook 5m | 2719 | **80.6%** (79.1–82.0) | 82.7% | -57 |
| Engine BUY / SELL 5m | 191 | **84.8%** (79.0–89.2) | 85.2% | -31 |
| Engine BUY / SELL 15m | 19 | **68.4%** (46.0–84.6) | 85.5% | -129 |
| Challenger 5m | 190 | **85.3%** (79.5–89.6) | 85.3% | -28 |
| H3 5m | 70 | **78.6%** (67.6–86.6) | 85.2% | -69 |
| H5 5m | 87 | **81.6%** (72.2–88.4) | 85.3% | -50 |
| H6 5m | 191 | **84.8%** (79.0–89.2) | 85.2% | -31 |
| Random entries, long | 3882 | **79.7%** (78.4–80.9) | 79.7% | -62 |
| Random entries, short | 3882 | **85.5%** (84.4–86.6) | 85.5% | -27 |

**Reading:**

- **Every source sits at or below random entries,** at 68–85%.
- **Every source loses money with this geometry.** Your recorded forward trades won 80% of the time, the kind of
  rate that feels successful, and still lost about **$59 per trade**: each loss wipes out five wins, and costs take
  $40 of each $100 win.
- **Even random shorts in this falling market (85.5%) lost $27 per trade.**
- **To make money with SL $500 / TP $100 at 0.5 lot, a signal must win more than 90% of the time before costs are
  even covered.** Nothing measured does. A claimed rate also needs 184+ trades to establish a 95% lower bound of
  85%; to rule out the 90% break-even it needs far more.

## 7. Follow-up (2026-11-01): the trade confirmed as SL $500 / TP $1,000, and what came after

The operator confirmed the trade as **SL $500 / TP $1,000 at 0.5 lot: +$20 before −$10** (§5). Two pieces of work followed.

- **The site's "Your trade" panel** (display only; `quantum/trade_race.py`).
  - You type SL, TP and lot.
  - It shows the break-even win rate after the selected cost profile.
  - It shows how often each decision source on the chart reached that TP before that SL, against random entries in the same directions.
  - Default is this trade. Its 15m numbers reproduce this study's counts exactly.
- **Phase B2** (`B2_DEVELOPMENT_RESULTS.md`).
  - 9 SMC setups were tested on 2020–22 development data against this trade and the two others (+$10 and +$2 before −$10).
  - None reached the 36.2% break-even of the +$20 / −$10 trade.
  - None beat random entries by 2 standard errors.
  - The 2:1 shape needs only about 3 points over random. None of the setups supplies it.
