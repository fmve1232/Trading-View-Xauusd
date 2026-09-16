# API specification

FastAPI. `make api`, then `http://localhost:8000/docs`.

## Implemented

| Endpoint | Returns |
|---|---|
| `GET /health` | Liveness. Answers "is the process up", not "is the data good". |
| `GET /version` | `engine_version`, `formula_registry_version`, `schema_version`, `git_commit`, `reproducible` (§57) |
| `GET /system-status` | Per-component quality, overall, `signals_permitted` (§54) |

`/system-status` currently reports `overall: OFFLINE` and
`signals_permitted: false`, with every component `not implemented`. That is
correct, and it is what the dashboard should display.

## Declared, returning `503 DATA_UNAVAILABLE`

`/market` · `/bars` · `/features` · `/smc` · `/regime` · `/macro` · `/news` ·
`/probability` · `/signals` · `/risk` · `/performance` · `/models` · `/audit` ·
`/trace`

```json
{
  "status": "DATA_UNAVAILABLE",
  "path": "/probability",
  "reason": "Phase 9 -- probability engine",
  "checked_at": "2026-09-16T12:00:00+00:00"
}
```

**Why 503 and not 404 or 501.** The resource is legitimate and temporarily
unserveable. A 404 tells a client the route does not exist, and a client that
caches that will not come back when the engine lands.

**Why declare them at all.** The dashboard and the API contract can be built
against the real route list now, and no consumer can ever receive a
plausible-looking fabricated payload (§83). A route starts returning data
because an engine was wired up, not because a placeholder was left in.

## `/trace` — §47

The endpoint that makes everything else auditable:

```
signal_id → probability → model → features → formulas → raw data → source → version
```

Mandatory per §47, Phase 18. It depends on `audit_logs` and on every analytical
table carrying its version columns — which is why those columns are in the
schema from migration 0001 rather than added later.

## Conventions

- Every response carries a UTC ISO-8601 timestamp.
- Errors use the same `{status, reason, checked_at}` shape. A caller never has to
  parse two error formats.
- No endpoint returns a default in place of missing data.
