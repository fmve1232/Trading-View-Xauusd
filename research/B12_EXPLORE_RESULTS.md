# B12-explore: the operator's multi-timeframe level criteria at +$22 / −$22 (live window, 2026-11-05)

**Request (operator, 2026-11-05).** Define criteria from the daily, previous-day, 4h, 1h and 30m highs and lows,
support and resistance, and the weekly and monthly highs and lows. Set the trend, enter where the market moves in the
signal's direction, confirm by volume, and get +$10 to +$20 the same way. The trade is 0.5 lot with SL and TP of
$1,100 each, which is **$22** of price.

**Rules.** They are fixed in `research/tools/b12_explore_mtf_levels.py` (docstring) before the run:

| Item | Rule |
|---|---|
| Levels | today's H / L so far; previous day, week and month H / L; this week's and month's H / L so far; the last completed 4h, 1h and 30m bars' H / L; the last three confirmed 1h swing highs / lows |
| Trend | 2 of 3 votes: the last day's close vs its 20-day average; 4h EMA20 vs EMA50; 1h EMA20 vs EMA50 |
| Entry | a 15m bar trades into a level and closes back on the trend side, in the half of its range nearer that side |
| Variants | V0 trend only; V1 + level rejection; V2 + confluence (2 or more levels within $3); V3 + room (no major level within $22 ahead); V4 + COMEX volume ≥ 1.2 × the 20-bar median; C1 rejection **against** the trend |
| Outcome | +22 before −22 on 5-minute bars within one trading day (a bar touching both is a loss unless it opened beyond the target); also +10 and +20 before −22 |
| Baseline | random 15m closes in the same long / short mix |

**Data.** Store 5-minute XAU/USD (Twelve Data) and COMEX GC volume, 2026-09-09 → 2026-11-05 (`market-data` @ the
commit in the results file). Results are in `research/results/b12_explore_2026-11-05.json`, and the 18 cells are in
`research/trials.jsonl` (phase `B12-explore`).

| Variant | Decided | +22 first | 95% range | Random, same mix | z | +10 first (random) | $ per trade at 0.5 lot |
|---|---|---|---|---|---|---|---|
| V0 trend only | 3,200 | 51.5% | 49.8–53.2% | 54.1% | −2.94 | 72.1% (73.7%) | +$20 |
| V1 + level rejection | 1,084 | 50.8% | 47.9–53.8% | 54.1% | −2.17 | 72.4% (73.7%) | +$5 |
| V2 + confluence | 899 | 49.6% | 46.4–52.9% | 54.1% | −2.70 | 72.0% (73.7%) | −$22 |
| V3 + room to target | 368 | 47.8% | 42.8–52.9% | 54.1% | −2.42 | 71.2% (73.7%) | −$61 |
| V4 + volume | 159 | 45.3% | 37.7–53.0% | 54.1% | −2.22 | 71.7% (73.6%) | −$117 |
| C1 rejection against the trend | 1,036 | 46.9% | 43.9–50.0% | 44.9% | +1.29 | 64.5% (63.1%) | −$81 |

**Reading.**

- **No version beats random entries in the same direction.** Each added filter (level, confluence, room, volume) made
  the result slightly worse.
- In this window the trend rule was DOWN almost throughout (3,152 of 3,200 trend entries were shorts). Random shorts
  won 54.2%, which is the falling market, not the criteria.
- "+$10 in my direction before −$22" happened about 72% of the time, but random entries did 73.7%. That is the
  geometry: 22 / (10 + 22) = 69%.
- The positive dollar figures for V0 / V1 come from the market's drift and are below what random entries in the same
  direction earned.

**Limits.**

- The window is one regime (an 8-week decline, then a rebound).
- The trend rule's short / long imbalance makes the comparison mostly about shorts.
- A fair test needs both regimes: the proposed B12 runs the same rules on 2020–2023, and an ML meta-label with purged
  CV, before the operator relies on any of it.
- Volume can only be tested live, because 2020–2023 COMEX volume is not stored.

**Risk at $1,100 a trade on a $25k account.**

- One loss (−$1,113 with costs) uses 89% of a 5% daily limit ($1,250).
- Three net losses (−$3,339) exceed a 10% maximum loss.
- With about 50% odds, a fair-coin walk reaches −3 net losses before +2 net wins (an 8% target) about 40% of the time.
