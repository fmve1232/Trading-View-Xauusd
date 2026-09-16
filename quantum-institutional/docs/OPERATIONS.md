# Operations

## Daily

`GET /system-status`. `overall` is the worst component; `signals_permitted`
tells you whether the data-quality gate (§41) would allow a signal at all.

Today it reports `OFFLINE` with every component `not implemented`. That is
correct and should be displayed as-is.

## When a feed fails

The system marks state; it does not improvise (§68).

| State | Meaning | Signals? |
|---|---|---|
| `OK` | | yes |
| `DEGRADED` | non-critical input missing | yes, flagged |
| `STALE` | past its freshness budget | **no** |
| `INVALID` | failed validation | **no** |
| `OFFLINE` | unreachable | **no** |

A signal is never emitted on stale data with a fresh-looking timestamp. If the
dashboard shows a number, the number's quality is shown next to it.

## When Quantum 5.0 changes

1. Re-vendor all five artefacts into `reference/quantum_5_0/`.
2. Re-derive `MANIFEST.sha256`.
3. Re-derive **every** Pine line citation — upstream `audit/tools/trace.py`.
   F-A09 is what happens when this is skipped: every pointer wrong by +7 to +143
   lines while the expressions still matched.
4. Re-run the parity suite. `test_reference_integrity.py` fails until step 2, and
   the edge-case port fails if any transcribed expression moved.
5. All of it in **one commit**. A half-re-vendored reference is worse than an old
   one, because the hashes look current.

## When a parity mismatch appears

1. Is it in `DIVERGENCE_REGISTER.md` already? Then it is expected — check the
   magnitude against what was predicted.
2. Is it a **feed** difference? Check the parity input is TradingView's own
   exported OHLCV (D-08), not a separately sourced history.
3. Is it a **warm-up** difference? Recursive seeds must match Pine's (D-07).
4. Otherwise it is a **finding**. `FINDINGS.md`, and a new register row.

Never widen a tolerance to make a mismatch go away. The tolerance was declared
before the run for exactly this reason.

## Incident log

Every incident gets a row in `audit_logs` with the component, severity, signal
id where applicable, and the git commit. Phase 18.
