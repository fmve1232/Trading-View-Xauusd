# Database schema

`migrations/0001_initial_schema.sql` — 24 tables, PostgreSQL. Never applied to a
live database yet.

## Design rules encoded in the DDL

**1. Source is part of the identity of a price row.**
`market_bars` has `(symbol, timeframe, event_time, source_id)` as its key. Two
feeds for XAUUSD are two rows to reconcile (§69), not a last-write-wins
collision that silently keeps whichever arrived last.

**2. A revision is a new row.**
`macro_values` keys on `(series_id, event_time, publication_time, source_id)`.
An in-place update is unrecoverable and silently improves every historical
backtest.

**3. `NULL` means absent, not zero.**
`market_bars.volume` and `news.sentiment` are nullable. An unscored sentiment and
a neutral sentiment are different claims (§83).

**4. Constraints, not conventions.**
`ohlc_consistent` rejects `high < max(open, close)` at insert. Validation code
can be bypassed; a `CHECK` cannot.

**5. Probability or a reason.**
`probabilities` has `CHECK (p_win IS NOT NULL OR unavailable_reason IS NOT NULL)`.
§78: if a field cannot be computed reliably, it is `null` **plus a reason** — the
database enforces the "plus a reason".

**6. Availability never precedes the event.**
`features` has `CHECK (availability_time >= event_time)` — a cheap structural
guard against one class of leakage.

**7. `timestamptz` everywhere.** A naive timestamp column is how a session
boundary ends up off by the server's local offset.

**8. `regimes.composite_raw` is the UNROUNDED value**, with F-021 / F-A17 noted
in the DDL. Storing the rounded value would bake the defect into history.

## Tables

| Group | Tables |
|---|---|
| Reference | `schema_version`, `data_sources`, `instruments`, `formula_registry`, `engine_versions` |
| Market | `market_bars`, `market_quotes`, `data_quality` |
| Macro / news | `macro_values`, `macro_events`, `news` |
| Derived | `features`, `smc_events`, `regimes` |
| Models | `models`, `model_runs`, `probabilities` |
| Decisions | `signals`, `backtests`, `trades`, `risk_metrics` |
| Operations | `dashboard_snapshots`, `system_health`, `audit_logs` |

## Not yet done

Row-level security for Supabase, realtime publication config, retention and
partitioning for `market_bars` (which will dominate the row count), and indexes
driven by real query patterns rather than guesses. Phase 18–19.
