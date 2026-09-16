# Deployment

**Nothing is deployed.** This documents the intended topology and the honest
cost position.

## Intended topology

| Layer | Choice | Free tier? |
|---|---|---|
| Source control + CI | GitHub Actions | yes, within minute limits |
| Database | Supabase / PostgreSQL | yes, with storage and connection limits |
| Realtime | Supabase Realtime (database changes + broadcast) | yes, within message limits |
| API / edge | Cloudflare Workers | yes, with CPU-time limits |
| Batch compute | GitHub Actions scheduled workflows | yes |
| **Continuous stream** | **a persistent process** | **no** |
| Dashboard | static frontend on any CDN | yes |

## The cost position, stated plainly

§5 asks for zero-investment-first. That is achievable for **everything except a
continuous live feed**.

- Batch work — historical ingest, nightly features, training, walk-forward —
  fits scheduled jobs comfortably.
- A permanent high-frequency market stream does not. Serverless functions are
  not suitable for it (§4), and free market-data tiers are rate-limited,
  delayed, or both.

The architecture's answer is not to pretend otherwise. It is the provider
abstraction (§6): a paid feed is a new adapter and a config change, not a
rewrite of the engine. Run on free tiers and delayed data during research; state
the cost when live trading needs a real feed.

## Local

```sh
make install
make verify     # vendored Quantum 5.0 artefacts unchanged
make all        # verify + lint + typecheck + test
make api        # http://localhost:8000/docs
```

## Deploy order, when there is something to deploy

1. Apply migrations. `schema_version` must match `version.SCHEMA_VERSION`.
2. Deploy the API with `GIT_COMMIT` injected — a build artefact has no `.git`.
3. Confirm `GET /version` reports `reproducible: true`.
4. Confirm `GET /system-status` before pointing a dashboard at it.
5. `EXECUTION_MODE` stays `PAPER` until explicitly changed (§65).
