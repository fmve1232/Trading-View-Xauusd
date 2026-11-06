# B17: quality over quantity, setups taken only when every confirmation agrees (2026-11-06)

**Request (operator):** "more authentic, more accurate, more precise and refined alerts … enter the market only when we
have all the confirmations … at least $13 to $15, maximum $20 in the same direction … backtest and recalculate on the
previous 3 days."

**Registration:** `research/registrations/B17.json`, committed before any code (39c1b1f40).

**Code:**

- Rules: `quantum.notify.setup_checks` and `trend_votes`, shared with the live alerts.
- Test: `quantum/research/b17.py`.
- 3-day recalculation: `research/tools/b17_recalc_window.py`.
- Results: `research/results/b17_development_2026-11-06.json` and `b17_recalc_2026-11-03_06.json`.
- Trial records: `research/trials.jsonl` (phase `B17`).

**The four confirmations, on a B16 setup:**

1. **Level:** a previous day, week or month high or low.
2. **Trend:** all three trend votes agree (daily close against its 20-day average, 4h EMA20/50, 1h EMA20/50).
3. **Engine:** the frozen engine's own bias agrees.
4. **Session:** the bar closes in London or New York hours.

## The ladder: what each confirmation adds (2020-04 → 2023-01, +$15 before −$13)

| Setups | n | Target first | 95% range | Random | z | Net / oz at $4,000 (t) |
|---|---|---|---|---|---|---|
| All B16 setups | 12,647 | 46.3% | 45.5–47.2% | 46.2% | +0.20 | −$0.88 (−7.11) |
| + day / week / month level | 1,075 | 47.7% | 44.7–50.7% | 46.2% | +0.99 | −$0.49 (−1.15) |
| + trend 3 of 3 | 383 | 50.1% | 45.1–55.1% | 46.3% | +1.50 | +$0.17 (+0.24) |
| + engine bias | 337 | 50.4% | 45.1–55.7% | 46.3% | +1.54 | +$0.26 (+0.34) |
| **+ London / New York = all four** | **184** | **51.6%** | **44.5–58.7%** | 46.3% | +1.46 | +$0.68 (+0.66) |

**Verdict: FAIL** (p 0.072 against 0.05; t 0.66 against 1.645).

- **What the confirmations do:** they move the rate about 5 points above random, and in the right order, but not
  significantly.
- **Other targets, all four confirmations:**
  - +$13 before −$13: 55.4% of 184 (48.2–62.4%; random 49.9%);
  - +$20 before −$13: 43.4% (random 39.0%);
  - "$15 at any time in the day": 66.1%.
- **Frequency:** about **66 a year (1.3 a week)**. Almost all are breakouts: 181 breakouts, only 3 sweeps.
- **Not 90%:** the upper end of the 95% range is 58.7%.

## Recalculation on the last 3 days (3 Nov 12:00 → 6 Nov 22:00 UTC, live engine, GC volume; descriptive)

- **All B16 setups:** 46. Of the 44 that finished, 22 reached +$15 before −$13 (50%).
- **With all four confirmations:** none.
  - During the 4–5 Nov rally the daily trend vote was still down after the October fall, so every BUY failed the
    trend check. This is the same lag that kept the engine silent.
  - Three days are far too few to judge any rate.

## What changed in the alerts (display only; freeze keys unchanged)

- **ALERT_MODE=quality is now the default** (operator, "quality rather than the quantity").
  - **Sent to the phone:** engine signals and their follow-ups, setups with **all four** confirmations (each showing
    its confirmations and this record), the trend-change warning, the registered tests' checks, and the reports.
  - **Website only:** liquidity, structure and H-setup lines, and unconfirmed setups. Every setup is still recorded
    and scored in `research_forward/SETUP-LIVE.json`, with a separate tally for the confirmed ones.
  - `ALERT_MODE=all` restores every alert.
- **No validation opening:** the rule failed. No re-run with changed confirmations, thresholds or targets.
