# Migrations

Applied in filename order. `schema_version` records the highest applied version
and must match `version.SCHEMA_VERSION`.

| File | Contents |
|---|---|
| `0001_initial_schema.sql` | 24 tables (§43), version stamping on every analytical row (§44) |

Never applied to a live database yet. Design notes: `docs/DATABASE_SCHEMA.md`.
