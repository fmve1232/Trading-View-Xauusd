# RISK specification

**Status: NOT WRITTEN. Scheduled for Phase 16** — see `PHASES.md`.

This file is a placeholder on purpose. A specification for the risk engine written
before the layer beneath it is validated would describe an intention, and §83
forbids presenting an intention as a result.

## Constraints already fixed

These are decided and will bind whoever writes this document.

- Fixed-fractional and ATR sizing first.
- Kelly only on validated, calibrated probabilities. Fractional by default.
  **Never full Kelly.**
- A clamped probability (D-04) is not a calibrated probability for sizing.
- Drawdown limits and risk of ruin are computed and stored, not assumed.
