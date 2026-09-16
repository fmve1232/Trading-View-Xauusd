# Data contracts

JSON Schema for records crossing a boundary — a provider adapter, the API, or
another service. The Python dataclasses in
`src/quantum_institutional/data/contracts.py` are authoritative; these mirror
them for consumers that are not Python.

| File | Mirrors |
|---|---|
| `bar.schema.json` | `contracts.Bar` |
| `macro_value.schema.json` | `contracts.MacroValue` |
| `signal.schema.json` | the §78 final decision object |

Drift between a schema and its dataclass is a bug. Phase 17 generates these from
the dataclasses so they cannot drift.
