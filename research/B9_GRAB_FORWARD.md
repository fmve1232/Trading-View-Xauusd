# B9: liquidity GRAB reversal, +$13 before −$13 (exploration and live forward registration, 2026-11-04)

**Status:** registered and approved by the operator on 2026-11-04 ("approve GRAB forward test"). The registration is
`research/registrations/B9-GRAB-FWD.json`, committed before any tracking code. The live record starts at the first site
run that carries the code.

## B9-explore: what selected the lead

**Question.** The operator asked which signal most often moves **+$13** their way before their **−$13** stop
($650 / $650 at 0.5 lot; break-even 51.0% with costs).

**Method.** Every signal source on the site, plus the liquidity GRAB and BREAK events, was measured on the stored market
data from 2026-09-09 to 2026-11-04 (`market-data` @ `06b8805a`). The rules are those of `quantum/trade_race.py`:

- the path is walked on 5-minute bars;
- the horizon is one trading day;
- a bar touching both levels is a loss unless it opened beyond the target;
- each source is compared with random entries taken in the same directions.

The sources' triggers are in-sample. All 50 cells are logged in `research/trials.jsonl` (phase `B9-explore`), and the
full table is in `research/results/b9_explore_2026-11-04.json`.

| Source | Decided | +$13 first | 95% range | Random, same directions |
|---|---|---|---|---|
| H4 Playbook, 5m | 2,886 | 48.4% | 46.6–50.3% | 49.8% |
| Engine signal, 15m | 22 | 31.8% | 16.4–52.7% | 55.9% |
| Engine signal, 5m (196 of 205 were SELLs in a falling market) | 205 | 60.5% | 53.7–66.9% | 55.4% |
| Recorded forward trades, 5m (real time) | 62 | 48.4% | 36.4–60.6% | 50.0% |
| **Liquidity GRAB, 15m** | 60 | **61.7%** | 49.0–72.9% | 46.6% |
| Liquidity GRAB, 5m / 30m / 1h / 4h | 61 / 60 / 60 / 56 | 59.0 / 58.3 / 55.0 / 51.8% | | about 47% |
| Liquidity BREAK, 15m | 44 | 38.6% | 25.7–53.4% | 51.9% |

**Reading.**

- No source is proven.
- The best cell (15m GRAB, z +2.35 against random) is about what the largest of 50 comparisons gives by chance.
- Its 95% range includes break-even.
- The same events appear on every timeframe.
- The 2020–2022 study (B2 / B2b / B2c) found no edge in sweeps.
- The academic evidence on stops beyond levels points to continuation, not reversal (Osler 2003, 2005).

It is still the strongest lead, and it costs nothing to test on new data, so it is registered as a live forward test
rather than used.

**A wider stop is not an improvement.** With a −$26 stop the 15m GRAB reached +$13 first 76.7% of the time. But
break-even rises to 67.3%, and each loss becomes $1,300 at 0.5 lot.

## B9-GRAB-FWD: the live test (fixed before any data)

**Signal and direction.**

- The signal is the engine's own sweep on a 15m, 30m, 1h or 4h bar.
- After a low is swept, BUY. After a high is swept, SELL.

**Entry and levels.**

- Entry is the GRAB bar's close.
- The target is +$13 and the stop −$13, walked on 5-minute bars for one trading day.
- A bar touching both levels counts as a loss unless it opened beyond the target.

**One trade per pool per trading day,** taken at the first timeframe that shows the sweep.

**Not counted in the rate:**

- NONE: neither level reached within the day;
- GAP: the 5-minute data needed is missing.

**Verdict.**

- It is checked only at 30, 40 … 100 decided results.
- PROVEN when the Wilson 95% lower bound is above 51.0% at a check.
- Otherwise NOT PROVEN, at 100 results or on 2027-03-31.

**Error rates (simulated, stated in advance).**

- With no edge, the rule says PROVEN 5.4% of the time.
- With a true 60% it proves 56.5% of the time, and with 65%, 87.4%.

**Pace.** About 7–9 grabs a week: 30 results in about 4 weeks, 100 in about 3 months.

**Where it shows.**

- On the phone, the first GRAB of a pool each day carries the plan, the MT5 distances and the timing.
- On the phone, a follow-up says TP or SL.
- On the website, the plan card shows the running count, rate and verdict.

**Unchanged:** the engine, its configuration, every freeze key, the signal alerts and their validation.

## Start record (2026-11-04 UTC)

The test was deployed by merge `96f409ca71528ea69f2082c360714dfff19f1bee` (PR #75), run `quantum-site` #2592 (Actions
run 41935901280).

| Item | Value |
|---|---|
| Started | **2026-11-04 23:47:25 UTC**; only GRAB bars closing after this count |
| Record | `research_forward/B9-GRAB-FWD.json` on `market-data`, and with git history on `forward-ledger` @ `d6556ff1dfea1fed2071d134344f420e8a9219ac` |
| Trades at start | 0; no checks; no verdict |
| Engine key | unchanged, `5e4630924d663fc5:a6f2be58c74887ed` (web.8) |
