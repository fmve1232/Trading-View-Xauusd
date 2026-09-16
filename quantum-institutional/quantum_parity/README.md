# quantum_parity

Quantum 5.0 expressions transcribed into Python for parity testing.

| | |
|---|---|
| `edge_cases.py` | Master expressions behind the 72-assertion harness |
| `fixtures/` | Exported TradingView series. **Empty** — Phase 6. |

## Rules

1. **Reproduce, do not improve.** Three expressions here encode behaviour the
   audit classified as defective or lossy — `safe_div`'s `== 0` guard, the
   timeout accounting asymmetry, the `[0.05, 0.95]` probability clamp. Fixing
   them breaks parity and hides the defect instead of measuring it.
2. **Pine semantics go through `pine/semantics.py`.** A direct transcription is
   wrong in four ways that do not raise.
3. **Every function cites its harness case IDs.** Citations are re-derived on
   every Quantum 5.0 re-vendor, never carried forward — F-A09 is what happens
   otherwise.

## What a green suite proves

That Python agrees with the Pine **harness**. Not that the harness agrees with
the Master — F-A17 is a case where it did not — and not anything about bar data.

Phase 6 parity is measured against exported TradingView series. See
`docs/PARITY_PLAN.md`.
