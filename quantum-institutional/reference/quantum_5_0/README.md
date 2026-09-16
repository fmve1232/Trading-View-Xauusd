# Quantum 5.0 — reference layer, READ ONLY

Build **v12**, upstream `fmve1232/Trading-View-Xauusd` commit `b5fd337`.

**Do not edit these files.** They are the parity reference. Every line citation
in `quantum_parity/`, every entry in `docs/FINDINGS.md` and every fixture is
written against these exact bytes.

`scripts/verify_reference.py` runs first in CI and fails the build if any hash
moves.

| File | Lines | Role |
|---|---:|---|
| `XAUUSD_Quantum_5_0_Master.pine` | 5 645 | Canonical live indicator. The only file traded from. |
| `XAUUSD_Quantum_5_0_Strategy.pine` | 5 002 | A/B **treatment** arm. Backtest only. |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` | 5 002 | A/B **control** arm. Backtest only. Do not deploy. |
| `XAUUSD_Quantum_5_5_Visuals.pine` | 994 | Chart companion to the Master. |
| `XAUUSD_Quantum_5_0_EdgeCases.pine` | 301 | 72-assertion diagnostic. Not on the decision path. |

## Re-vendoring

All five files, the manifest, and every re-derived line citation in **one
commit**. See `docs/OPERATIONS.md`. A half-re-vendored reference is worse than
an old one, because the hashes look current.

```sh
sha256sum -c MANIFEST.sha256
```
