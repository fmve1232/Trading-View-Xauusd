# ENGINE specification

**Status: NOT WRITTEN. Scheduled for Phase 5** — see `PHASES.md`.

This file is a placeholder on purpose. A specification for indicator and engine specifications written
before the layer beneath it is validated would describe an intention, and §83
forbids presenting an intention as a result.

## Constraints already fixed

These are decided and will bind whoever writes this document.

- Every indicator is validated against Quantum 5.0 before it is used (Phase 6
  gate, `PARITY_PLAN.md`).
- Pine semantics go through `pine/semantics.py`. A direct transcription is wrong
  in four ways that do not raise.
- Recursive indicators must match Pine's seed, and the warm-up bars are excluded
  from the parity comparison and declared in the report.
