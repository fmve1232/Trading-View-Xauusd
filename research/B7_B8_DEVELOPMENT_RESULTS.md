# Phases B7 (macro) and B8 (US news reactions): the operator's −$650 / +$650 trade (development data, 2026-11-03)

**Verdict: REJECT all 54 trials.** Neither macro moves nor news reactions tell which way gold reaches first, $13 up or
$13 down, well enough to beat break-even after costs.

| Study | Trials | Pass B2's five-part rule | Reality Check p | Best result (not significant) |
|---|---|---|---|---|
| B7 macro | 22 | 0 | 0.999 | Buy when the dollar and real yields both fell the day before: 54.7% TP first, n 150, z +1.22, +$21 / trade |
| B8 news | 32 | 0 | 0.822 | Fade the first 30 minutes after payrolls: 65.7% TP first, n 35, z +1.86, +$166 / trade |

With 22 and 32 rules tried, a few will show z near ±2 by chance alone. The Reality Check accounts for that, and finds
nothing.

The operator approved both studies on 2026-11-03 ("merge, approve B7 and B8").

## B7: macro direction (dollar, yields, real yields, VIX, oil, breakevens, COT)

**Declaration.** `quantum/research/b7_macro.py`, committed at `a530091f8` before any macro data was fetched.

**Run.** On GitHub Actions (`research-macro`, run 41590147838). Sources, all free and with no key:

| Series | Source | Coverage |
|---|---|---|
| US dollar index | Yahoo DX-Y.NYB | 2016-11 → 2026-11 |
| 10-year yield | Yahoo ^TNX | 2016-11 → 2026-11 |
| VIX | Yahoo ^VIX | 2016-11 → 2026-11 |
| WTI oil | Yahoo CL=F | 2016-11 → 2026-11 |
| 10-year TIPS real yield | FRED DFII10 | 2003 → 2026-10 |
| 10-year breakeven inflation | FRED T10YIE | 2003 → 2026-11 |
| COMEX gold COT (non-commercial) | CFTC, keyed by its Friday release | 1986 → 2026-10 |

**Method.** Entry at 08:00 UTC (London open) on 771 development days. Each rule uses only data published before the
entry: Yahoo closes from earlier days, FRED values at least 2 business days old, and COT reports already released.
Random entries at the same time reached TP first 49.1–50.3% of the time.

| Rule (gold direction from yesterday's move) | n | TP first ±$13 | Random, same mix | z | $ per trade |
|---|---|---|---|---|---|
| Dollar fell → buy (1 day) | 435 | 51.7% | 49.7% | +0.85 | −$16 |
| Dollar fell → buy (5 days) | 436 | 47.9% | 49.7% | −0.74 | −$66 |
| 10y yield fell → buy | 428 | 49.1% | 49.7% | −0.27 | −$51 |
| Real yield fell → buy (1 day) | 465 | 45.2% | 49.7% | −1.94 | −$102 |
| Real yield fell → buy (5 days) | 437 | 48.5% | 49.7% | −0.49 | −$58 |
| VIX rose → buy | 385 | 50.6% | 49.7% | +0.37 | −$29 |
| Oil rose → buy (5 days) | 434 | 49.1% | 49.6% | −0.21 | −$50 |
| Breakevens rose → buy (5 days) | 421 | 52.3% | 49.6% | +1.10 | −$9 |
| Dollar and real yield agree | 150 | 54.7% | 49.7% | +1.22 | +$21 |
| COT crowded → fade it | 313 | 44.1% | 49.6% | −1.96 | −$115 |
| COT weekly change → follow it | 762 | 52.6% | 49.7% | +1.63 | −$5 |

The ±$10 results are in `research/results/b7_development_2026-11-03.json` and tell the same story. The best was
COT-follow at 53.5% (z +2.02), still below the 54.4% break-even.

**What it means.**
- **The relations are real but mostly simultaneous.** Gold falls when the dollar and real yields rise *at the same
  time*. Yesterday's move is already in today's price.
- **Signed drift is small.** From 08:00 to 20:00 UTC the move in the rule's direction averaged +$4.48 for the
  combined rule and between −$2 and +$3 for the others. That is well short of the $13 the trade needs.
- **Crowded COT positions did not reverse** within the trade's horizon; fading them lost.

## B8: US news reactions (CPI, payrolls, FOMC)

**Declaration.** `quantum/research/b8_news.py`, committed at `bce36a2a1` before the run. 36 CPI, 36 payrolls and 23
scheduled FOMC releases (2020-01-24 → 2023-01-24), from the official BLS and Federal Reserve schedules.

**Date check** (reported, never used to select). This compares the release bar's range with the same clock time on
other days:
- **FOMC:** median 6.8 times; no release flagged.
- **Payrolls:** 3.0 times; 2 flagged.
- **CPI:** 2.8 times; 7 releases from 2020 flagged. The dates are correct: CPI simply moved gold little in 2020.
- One CPI and one payrolls release had no spot bars (a market holiday), so 35 of 36 were usable for each.

| Rule | n | TP first ±$13 | Random, same time | z | $ per trade |
|---|---|---|---|---|---|
| All releases, follow first 15 min | 92 | 51.1% | 49.8% | +0.24 | −$19 |
| All releases, fade first 15 min | 92 | 48.9% | 50.1% | −0.23 | −$58 |
| All releases, follow first 30 min | 93 | 47.3% | 50.4% | −0.60 | −$71 |
| All releases, fade first 30 min | 93 | 51.6% | 49.5% | +0.41 | −$20 |
| CPI, follow first 15 min | 34 | 58.8% | 48.9% | +1.16 | +$76 |
| Payrolls, fade first 30 min | 35 | 65.7% | 50.0% | +1.86 | +$166 |
| Payrolls, follow first 30 min | 35 | 34.3% | 50.0% | −1.86 | −$243 |
| FOMC, follow first 15 min | 23 | 43.5% | 50.5% | −0.67 | −$102 |

All 32 trials are in `research/results/b8_development_2026-11-03.json`.

**What it means.**
- **Gold reacts to news within minutes** (Andersen, Bollerslev, Diebold & Vega). By the time a 15- or 30-minute bar
  has closed, the next $13 is a coin flip again.
- **The payrolls pattern is a possible lead, not an edge.** 65.7% on 35 releases has a 95% range of 49–79%. With 32
  rules tried, the Reality Check says it is what chance produces. The validation partition holds only about 18 more
  payrolls releases, too few to confirm a pattern this size. The live validation now running on the website will
  collect more.

## The research record so far

**561 recorded trials across B1–B8, plus one validation run.** Every family the operator named has now been tested:

| Family | Phase | Result |
|---|---|---|
| Price patterns, sessions, momentum | B1 | none |
| Order blocks, FVG, BOS / CHoCH, sweeps | B2, B3 | none |
| Round numbers, session opens, limit entries | B4 | lead failed on unseen data |
| Volume / real COMEX order flow | B5 | none; model AUC 0.50 |
| Timeframe agreement | B6 | worse than random |
| Macro: dollar, yields, real yields, VIX, oil, breakevens, COT | B7 | none |
| US news: CPI, payrolls, FOMC | B8 | none |

None moves the chance of +$13 before −$13 reliably above the 51% break-even.

The live validation now records every alert's real outcome by timeframe, session, side and day. If a group shows a
real edge there (30+ results, 95% range above break-even), it is flagged STRONG and becomes the next registration.
