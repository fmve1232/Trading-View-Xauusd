# Data dictionary

Types in `src/quantum_institutional/data/contracts.py`. Tables in
`migrations/0001_initial_schema.sql`.

## The three timestamps

| Field | Meaning | May a point-in-time query filter on it? |
|---|---|---|
| `event_time` | When the thing happened, or the bar opened | **No** |
| `publication_time` | When it became publicly available | **Yes — only this one** |
| `received_time` | When this system got it | **No** |

Worked example. September CPI:

| | |
|---|---|
| `event_time` | 2026-09-01 — the reference month |
| `publication_time` | 2026-09-10 13:30 UTC — the release |
| `received_time` | 2026-09-10 13:30:00.3 UTC |

A model that sees this value before 13:30 UTC on the 10th is leaking. Filtering
on `event_time` backdates it by nine days. Filtering on `received_time` makes the
backtest depend on the ingest machine.

## `Bar`

| Field | Type | Notes |
|---|---|---|
| `symbol` | `str` | canonical, not the provider's spelling |
| `timeframe` | `Timeframe` | |
| `event_time` | `datetime` | bar **open**, left-aligned, UTC, enforced at construction |
| `open` / `high` / `low` / `close` | `float` | |
| `volume` | `float \| None` | `None` = absent. Never defaulted to 0 |
| `volume_type` | `VolumeType` | see below |
| `source` | `str` | |
| `quality` | `Quality` | |

A feed that labels bars by **close** time shifts every signal by one bar if it is
normalised anywhere later than ingestion. `validate_bars` catches it via
`timeframe_alignment`.

## `VolumeType` — §7

| Value | Counts |
|---|---|
| `TICK` | price changes (most spot XAUUSD feeds) |
| `EXCHANGE` | matched contracts |
| `FUTURES` | COMEX GC / MGC contracts |
| `OTC_ESTIMATE` | estimated OTC |
| `NONE` | the feed supplies no volume |

Never summed across types. Aggregating mixed types yields `volume=None`, not a
number with no unit.

## `Quality`

`OFFLINE < INVALID < STALE < DEGRADED < OK`. Combining takes the **worst**. Only
`OK` and `DEGRADED` are `is_tradeable` (§41).

| Value | Meaning |
|---|---|
| `OFFLINE` | source not reachable at all |
| `INVALID` | present but failed validation — do not use |
| `STALE` | last good value, past its freshness budget |
| `DEGRADED` | usable, a non-critical input missing |
| `OK` | |

## `Timeframe`

`1m 3m 5m 15m 30m 1H 2H 4H 6H 12H 1D 1W`. All whole minutes, all derivable from
1m. `1W` is **rejected** by `aggregate()`: the epoch anchor puts the week
boundary on a Thursday, which no exchange uses.

## Validation checks — §12

| Check | Severity |
|---|---|
| `ohlc_consistency` | INVALID |
| `chronological_order` | INVALID |
| `duplicate_timestamp` | INVALID |
| `timeframe_alignment` | INVALID |
| `gap` | DEGRADED |
| `negative_volume` | DEGRADED |
| `missing_volume` | DEGRADED |
| `timeframe_mismatch` | DEGRADED |
| `empty_dataset` | DEGRADED |

`gap` is calendar-blind, so every XAUUSD weekend reports as a gap. Correct as a
statement of the data, useless as an alert. Filter by weekday until the session
calendar lands (Phase 20).
