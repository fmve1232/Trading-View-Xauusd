# B24-CONFIRM-FWD: the live forward test of "engine signal + a completed $15 confirmation" (prepared, not started)

**Registration:** `research/registrations/B24-CONFIRM-FWD.json`, committed `fa20f3bc9` before any code.
**Recorder:** `quantum/fwd_b24.py` (`5a9a3760a`). **Tests:** `tests/test_fwd_b24.py`.

**Status:** prepared and tested, **not deployed**. It starts with the first site run that carries the recorder. That
needs your separate approval, because the recorder runs inside the production pipeline. Nothing is recorded before
then, and no history is back-filled.

## What it records, for every engine signal (BUY and SELL)

| Stage | Recorded once, when it happens, never edited |
|---|---|
| Trigger | The signal's timeframe, direction, bar close price and close time. A second signal of the same idea (same direction, within 4 h and $15) is recorded as FOLDED. Signals that appear on a bar already processed are flagged `late`. |
| Confirmation | The first completed 15m close $15 beyond, or INVALIDATED (−$13 first, or an opposite structure break) or EXPIRED (96 bars). Each bar is examined once; a later data revision is flagged, never applied. |
| Entries | **A**: the confirming 15m close. **B (primary)**: the first price the site had when it first saw the confirmation (the 5m forming bar at that run), with its timestamp and the **latency** in seconds. |
| Costs | The engine's cost model at that run (spread + slippage + commission), your $0.26, and the slippage B − A. Broker bid / ask is not available to the pipeline (the MT5 feed is not connected); if it is connected later, its spread is recorded beside these. |
| Exits | A and B × (+$15, +$20) × (−$13, −$10, 3 × ATR, structure stop). Each is resolved on 5m bars from the first bar after the entry: a gap fills at the open, a bar touching both levels counts as the stop, 48-hour limit. |
| Excursions | MFE / MAE to each exit, and over a fixed 24 hours from each entry |

Every finished row is appended to `research_forward/B24-CONFIRM-FWD.json`. The workflow copies that file to
`forward-ledger`, so the full history is kept in git.

## How it is decided (fixed before the start)

- **Primary.** Entry B, +$15 before −$13, after $0.26. Break-even is 47.4%.
- **Three hypotheses:** H-ALL (pooled), H-BUY, H-SELL, each on its own results.
- **Looks:** only at 30, 50, 75 and 100 decided results. PROVEN needs 21 / 32 / 46 / 59 wins (Wilson z = 2.24 above 47.4%) **and** a positive average result after costs.
- **Error rates, simulated before the start:**
  - with no edge, the chance that any of the three is wrongly declared proven is 4.8%;
  - if the true rate is 60%, H-ALL is proven 67% of the time and a single direction 28%.
- **Pace and deadline.** About 3 confirmed engine signals a month in 2026, so the first look comes after about 10 months and the last after about 3 years. Deadline 2029-12-31.
- **Between looks**, every figure is **PRELIMINARY**. Only a PROVEN look can be called statistically validated.

## The weekly report

It is appended to the record after each Friday New York close, for the week and since the start:

| Field | Source |
|---|---|
| Total signals; BUY / SELL | Every trigger |
| Confirmed / invalidated / expired / folded | Stage B |
| +$15 and +$20 success with 95% interval, stop rate | Entry B, S13 (and A for comparison) |
| Average MFE / MAE | Entry B |
| Average latency, slippage, cost model | Per confirmation |
| Expectancy after $0.26, profit factor, maximum drawdown (R) | Entry B, S13 |
| Sample sizes | Every figure |
| Label | PRELIMINARY, or the decided result |

## What it changes in production

Nothing visible:
- the phone alerts are identical with the recorder on or off (tested, including a 3-day real-data replay: 55 messages / 484 lines identical);
- the recorder sends nothing;
- `FWD_B24=0` turns it off.

It adds one block to the alerts report (`b24`), one state key and one file.

## Why this test (B25)

B25 showed that the site's real delay (7 minutes median) does not worsen the odds of the confirmed trades. The
earlier 60% → 30% drop at +15 minutes was the noise of 20 trades. So the forward test can use the price the
site actually had, without a timing penalty assumed in advance. B25 also showed that no other entry timing (retest,
stop order, 5m confirmation) beats the confirming close, so the close (A) is recorded beside the executable price (B),
and nothing else is.

## Amendment A1 (2026-11-10): the confirming close must be $15 to $20 beyond the trigger price

Registered before B24 started and before any code: `research/registrations/B24-CONFIRM-FWD-A1.json`
(SHA-256 `f3799d529cbf97ce177ff62310690fd0629e93506d40c7aa693f42bad5626acd`). It amends the original registration,
which stays byte-identical (SHA-256 `6078abc269e9d7fe446255c413bc98d9c0caf9954e1740bce685c391ce86b363`), and is
recorded in `research/trials.jsonl` (phase `B24-A1`).

The only change: the first 15m close at least $15 beyond the trigger price confirms only if it is no more than $20
beyond. If it is more than $20 beyond, the setup is EXPIRED (overshoot), and it is never confirmed later.
Everything else is unchanged: the −$13 invalidation (checked first), the trigger price (the trigger bar's close,
never reset), 96 bars, entries, exits, looks, thresholds and the deadline. The capped and uncapped historical
results are reported side by side in `research/CF_VALIDATION.md` (2020-22 / 2023-24 / 2026) and
`research/B24_A1_REALDATA.md` (the same 200 live setups of 2026-10-18 to 11-10); the cap was the operator's decision
before either existed, and neither is used to choose a rule.
