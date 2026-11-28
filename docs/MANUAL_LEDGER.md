# Manual MT5 trade ledger: how to use it

Mandate 2026-11-28, Parts 9 and 12-17, 21. Code: `quantum/manual_ledger.py` (standard library only). Tests:
`tests/test_manual_ledger.py`. Mutation test: `audit/tools/ledger_mutation.py`.

## What it records, and what it never does

**One line per event, appended, never edited.** Each line carries its sequence number and the SHA-256 of the line before
it. An edit, deletion, insertion or reordering is therefore found by `verify`, and every append refuses to write to a
broken file.

**Five events are kept apart (Part 9):**

| Event | Who records it | State after it |
|---|---|---|
| `GENERATED` (a Quantum signal, id `Q-0001` …) | the import from the phone's C1 record, or you | `AWAITING_USER_CONFIRMATION` if actionable; `SIGNAL_GENERATED` (watch-only) if not; `SIGNAL_CANCELLED` / `BLOCKED_OPEN_TRADE` if a trade is already open |
| `ACCEPTED` | you | still awaiting: you intend to trade it |
| `EXECUTED` (fill, time, lot, actual stop, evidence) | you, or a broker record | `TRADE_OPEN`; the single slot is occupied |
| `CLOSED` (exit, time, outcome, gross P/L, commission, swap, evidence) | you, or a broker record | `TRADE_CLOSED`; the slot is free |
| `VERIFIED` (the statement's net P/L, evidence) | you, from the MT5 statement | the final verified result |

**Other lines:**
- `EXPIRED`: no execution confirmed by the expiry.
- `CANCELLED`, with one of these reasons: `USER_DECLINED`, `INVALIDATED`, `ENTRY_MISSED`, `BLOCKED_OPEN_TRADE`, `REJECTED`, `OTHER`.
- `OUTCOME`: the signal-level theoretical result, measured on market bars.
- `CORRECTION`: names the line it corrects, the field, the new value and the reason.

**Rules the code enforces** (each one is a test, and a mutant of it is killed):
- **One trade at a time.** A second execution is refused while a trade is open. A signal generated meanwhile is recorded as blocked and never counted as a trade.
- **Execution and closure are never inferred.** Only the sources `user` and `mt5` may record them, and evidence is required. A price reaching the stop or a target changes nothing.
- **Plans are complete.** A signal is actionable only with a complete Part 12 plan: entry, stop, TP1 and TP2 in the right order; R:R; spread, commission and slippage; maximum entry deviation; confirmation; invalidation; expiry; and reason. Anything less is recorded as NO TRADE with its reason.
- **Expiry.** A signal cannot be expired before its expiry time. A trade executed after expiry is still recorded and is flagged `after_expiry`.
- **Execution deviation.** It is flagged when the fill is farther from the planned entry than the maximum deviation (Part 16). The R:R is recomputed from the actual fill.
- **No sizing.** No lot is ever proposed. The lot you enter is what you traded.

## Recording what you did

```sh
# after you place the order on MT5 (times in UTC, with Z)
python -m quantum.manual_ledger record --ledger PATH --kind EXECUTED --signal Q-0007 --source user \
  --data '{"fill": 3541.8, "t_fill": "2026-11-20T16:32:10Z", "lot": 0.46, "sl_actual": 3554.53, "ticket": "123456", "evidence": "MT5 trade tab screenshot 20 Nov"}'

# after it closes
python -m quantum.manual_ledger record --ledger PATH --kind CLOSED --signal Q-0007 --source user \
  --data '{"exit_px": 3528.5, "t_exit": "2026-11-20T17:25:00Z", "outcome": "TP1", "pl_gross": 611.8, "commission": -6.44, "swap": 0, "evidence": "MT5 history row"}'

# you missed the entry, or decided not to trade it
python -m quantum.manual_ledger record --ledger PATH --kind CANCELLED --signal Q-0008 --source user --data '{"reason": "ENTRY_MISSED"}'

# a mistake: never edit the file, add a correction
python -m quantum.manual_ledger record --ledger PATH --kind CORRECTION --signal Q-0007 --source user \
  --data '{"target_seq": 12, "field": "fill", "value": 3541.9, "reason": "typed 3541.8; MT5 shows 3541.9", "evidence": "MT5 trade tab"}'
```

A refused line prints `REFUSED: <why>`, and nothing is written. `notify --signal Q-0007` prints the Part 21 phone text for one signal:
- `XAUUSD SELL | Signal ID: …`, `Entry`, `SL | TP1`, `TP2 | RR`, `Confirm`, `Expiry … PKT`, `Status: WAITING FOR EXECUTION` while it is actionable;
- `XAUUSD | NO TRADE` / `Reason: …` otherwise;
- `ENTRY MISSED — DO NOT CHASE` after that cancellation.

## Signals from the published records

`import-c1 --index index.json` records each finished or confirmed C1 setup once, keyed `c1:<id>`.
- **Confirmed setup:** becomes an actionable signal with the published plan.
  - The maximum entry deviation is the existing LATE rule: `alerts.plans.late_frac` (0.30) × the stop distance.
  - The expiry is the confirming close plus `alerts.c1.fresh_sec`.
- **Invalidated, rejected or expired setup:** becomes a non-actionable signal, followed by its cancellation or expiry.
- **Setup still waiting for its close:** not a signal yet; a later run picks it up.
- **Higher-timeframe alignment:** C1 does not publish it, so the field says `UNAVAILABLE (not published by C1)`. It is not filled in.

`expire` marks the awaiting signals that are past their expiry. `outcomes --bars <store>/XAU_USD_5m` adds each actionable signal's theoretical result once its 48-hour window or its stop decides it. The result is measured from the planned entry, and a bar touching both a target and the stop counts as the stop. Recorded for each signal:
- whether +$10, +$15 and +$20 were reached before the stop, with the times;
- whether TP1, TP2 and TP3 were reached before the stop;
- MFE and MAE.

## Statistics, export, reconciliation

- **`stats`:** the five Part 15 populations are kept apart: all generated, qualified, accepted, executed, closed executed.
  - **Theoretical results** come from bars and apply to signals.
  - **Actual results** come from your confirmed MT5 lines only:
    - win, loss and break-even rates with Wilson intervals;
    - net total and mean; net R (when you record `risk_money`);
    - average win and loss; profit factor; maximum drawdown; longest losing streak;
    - commission and swap; slippage; execution-deviated and after-expiry counts;
    - TP-first vs SL-first; by setup, timeframe and session.
  - Below 30 trades a population says INSUFFICIENT EVIDENCE. Every line counts, including expired, cancelled, blocked and losing ones.
- **`export --csv`:** one row per signal with the Part 14.1 fields, in fixed columns. The same ledger always gives the same bytes.
- **`reconcile --mt5 history.csv [--server-utc-offset H]`:** read-only. It compares your confirmed trades with an MT5 history export and lists:
  - differences in fill, exit and net P/L;
  - ledger trades the broker file lacks;
  - XAUUSD broker trades the ledger lacks (a missing record).

  It matches by ticket. It matches by time only if you give the broker server's UTC offset, because MT5 history is in server time and the offset is never assumed.

## Where the file lives (decision needed)

The GitHub repository is **public**. A ledger committed to it, including to the `forward-ledger` branch, would publish your fills and P/L. Nothing here writes to the repository, and no workflow was added.

Until you decide where it is kept, keep the file on your own computer and back it up. Any copy is checked by `verify`, so a backup that differs from the original is caught.

Wiring it into production would need your approval, and is not done in this change:
- an import step in the scheduled run (`import-c1`, `expire`, `outcomes`);
- the website's trading-status section (`snapshot` gives state and ids only: no fill, no P/L, no balance);
- the Part 21 text on the phone.
