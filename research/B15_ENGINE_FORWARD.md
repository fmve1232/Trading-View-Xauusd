# B15-ENGINE-FWD: live forward test of the engine's own signal alerts (registered 2026-11-06)

**Approval:** operator, 2026-11-06: "approve engine test". The registration (`research/registrations/B15-ENGINE-FWD.json`,
commit f5097bfc6) was committed before any tracking code.

**Question:** do the engine's signal alerts reach +$13 before −$13 more often than break-even (51.0%) on data no one has
seen?

**Why this stream:** it is the only one that beat random on two separate histories.

| Data | Result | Source |
|---|---|---|
| 2020–22 development | 64.3% of 70 | B10, secondary |
| 2023–24 validation | 61.4% of 44 | B13-1; failed its Holm-corrected test |
| Live window, Sep–Nov 2026 | 31.8% of 22 | B9-explore |

## Rules (as registered)

| Item | Rule |
|---|---|
| Stream | Every plan the alerts open: a SIGNAL of the frozen treatment engine on 15m, 30m, 1h or 4h. REPEATs open no plan and are not counted. |
| Entry | The signal bar's close. The alert-time price, delay and LATE flag are recorded beside it. |
| Outcome | TP1 +$13 before SL −$13: the plan's own result, on the 5-minute path where it covers the signal's close. A bar touching both levels counts as a loss unless it opened beyond TP1. |
| Not counted | EXPIRED (no result in 3 days); plans whose TP1 or SL is not $13 of price |
| Verdict | Checks only at 30, 40 … 100 results. PROVEN when the Wilson 95% lower bound is above 51.0% (21/30 … 61/100). NOT PROVEN at 100 results or after 2027-06-30. |

**Error rates (simulated in advance):**

- With no edge, the rule says PROVEN 5.5% of the time.
- A true 55% is proven 22.6% of the time, 60% 56.6%, and 64% 82.7%.

## Where it lives

- **Code:** `quantum/notify.py` (`eng_trades`, `eng_verdict`, `eng_run`). It is rebuilt every run from the plan log
  (`plan_validation.json`), so it cannot disagree with the alerts.
- **Record:** `<store>/research_forward/B15-ENGINE-FWD.json`, holding every trade and every check. It is copied to
  `forward-ledger` every run, with its git history.
- **Site:** the "Engine signal test" section of the plan card.
- **Phone:** a line at each check and at the verdict; the status rides with the daily report.

**Secondary, reported but not decisive:**

- the rate by timeframe, direction and session;
- TP2 (+$20) after TP1, and the money at the two-target plan;
- the rate from the alert-time price and without LATE alerts;
- at the verdict: random entries in the same directions over the same weeks.

**Start:** the first site run that carries this code. The run's time is recorded as `started_utc` in the record.
