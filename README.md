# Trading-View-Xauusd

Pine v6 artefacts for the XAUUSD Quantum system, and the independent audit
prompt written against them.

## Layout

| Path | What it is |
|---|---|
| `artefacts/` | The five Pine v6 files under audit. Byte-identical to the reviewed build. |
| `audit/AUDIT_PROMPT.md` | The audit prompt — 11 sections, pinned to the hashes below. |
| `audit/MANIFEST.sha256` | Artefact hashes. The audit's stop rule depends on these. |

## Artefact roles

- **`XAUUSD_Quantum_5_0_Master.pine`** — canonical live indicator. The only file
  intended to be traded from.
- **`XAUUSD_Quantum_5_0_Strategy.pine`** — A/B *treatment* arm. Backtest only.
- **`XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine`** — A/B *control* arm (pre-Q5.5
  gates). Backtest only. Do not deploy.
- **`XAUUSD_Quantum_5_0_EdgeCases.pine`** — standalone 72-assertion diagnostic
  harness. Not on the decision path.
- **`XAUUSD_Quantum_5_5_Visuals.pine`** — chart-drawing companion to the Master.

## Verify before auditing

```sh
sha256sum -c audit/MANIFEST.sha256
```

If any hash mismatches, stop and request the correct build. A finding written
against a different build is a false record. See `audit/AUDIT_PROMPT.md` §1.

## Web platform

`quantum/` is a Python port of the Master engine, run on free market data by
`.github/workflows/quantum-site.yml` and published from `site/` to GitHub Pages. Setup,
parity notes (D-01 … D-07) and limits: [`docs/PLATFORM.md`](docs/PLATFORM.md).

```sh
pip install -r requirements.txt && python -m pytest -q tests
python -m quantum.pipeline --synthetic --out site/data   # offline demo, labelled SYNTHETIC
```

