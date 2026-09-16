# Architecture

## Position of Quantum 5.0

```
        QUANTUM 5.0 (Pine v6)              reference / validation layer
        vendored read-only, hash-pinned    never modified from here
                    │
                    │  parity  (Phase 6 gate)
                    ▼
        ┌───────────────────────────┐
        │   PYTHON QUANT CORE       │      the quantitative source of truth
        │   indicators · SMC        │
        │   statistics · regime     │
        │   probability · ML · risk │
        └─────────────┬─────────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
   HISTORICAL DATA            LIVE DATA
         └────────────┬────────────┘
                      ▼
              POSTGRES / SUPABASE           state, versions, audit
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
     REST / WebSocket          Realtime
         └────────────┬────────────┘
                      ▼
               LIVE WEB DASHBOARD
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
   HUMAN ANALYSIS             MT5 EXECUTION  (optional, PAPER by default)
```

Pine stays as the reference environment. Python becomes the brain. The arrow
between them is **parity**, and it is a gate, not a formality.

## Layering

A module may import only from layers above it.

```
contracts + pine semantics        no dependencies at all
  validation · aggregation · pit  pure functions over contracts
    providers                     I/O, behind ABCs
      indicators · smc · statistics
        features
          regime · macro · news · fusion
            probability · calibration
              ml
                risk · expected value · decision
                  api · realtime · dashboard
```

Three rules make this hold:

1. **No engine imports a vendor SDK, a web framework, or a database driver.**
   That is what makes "components can migrate" (§5) true rather than a slogan.
2. **Contracts are plain frozen dataclasses**, not pydantic models. Pydantic
   appears only at the API boundary. Every engine imports contracts, so
   contracts must stay dependency-free.
3. **The dashboard never recomputes financial logic** (§42). It renders what the
   engine wrote. A dashboard number and a database number that disagree is a bug
   with no correct resolution.

## Batch versus stream

§4. These are different systems and the architecture does not pretend otherwise.

| | Batch | Continuous |
|---|---|---|
| Work | historical ingest, nightly features, training, walk-forward | live XAUUSD quotes, news wire |
| Compute | scheduled jobs (GitHub Actions, scheduled Workers) | a persistent process |
| Serverless suitable? | yes | **no** |

Serverless functions are not suitable for a permanent high-frequency market
stream, and designing as if they were is the quickest way to a system that
appears to work and silently drops ticks.

## Point-in-time, everywhere

Every revisable record carries three timestamps — `event_time`,
`publication_time`, `received_time`. Only `publication_time` may be filtered on.

- `event_time` is when the thing happened. A CPI reference month starts on the
  1st; the number does not exist then.
- `received_time` is a property of this machine. Filtering on it makes a
  backtest depend on the speed of the box that ran the ingest.

Revisions are new rows, never updates. `data/pit.py` implements the query;
`assert_no_lookahead` raises rather than degrading, because a leak is a bug in
the code and degrading would hide it behind a quality flag and let the backtest
finish.

## Quality, not booleans

`Quality` is ordered `OFFLINE < INVALID < STALE < DEGRADED < OK`. A pipeline
stage takes the **worst** of its inputs, so one stale input degrades the result
rather than being averaged away. Only `OK` and `DEGRADED` may back a production
signal (§41).

## Failure is a state, not an exception to swallow

§68 and §83. When a feed fails, the system marks `DEGRADED` / `STALE` /
`INVALID` / `OFFLINE`. It does not emit a stale signal that looks fresh, and it
does not substitute a default.

The API expresses the same rule: fourteen declared endpoints return
`503 DATA_UNAVAILABLE` naming the phase that will implement them. No consumer
can receive a fabricated payload, and a route starts returning data only because
an engine was wired up.

## Versioning

Every analytical row carries `engine_version`, `formula_version`,
`data_version`, `model_version` and `git_commit`. `git_commit` is **read**, never
guessed: unknown is `None`, and a result with an unknown commit reports itself as
not reproducible. A fabricated hash would make an irreproducible result look
reproducible, which is worse than admitting the gap.
