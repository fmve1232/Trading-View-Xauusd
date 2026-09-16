# ML specification

**Status: NOT WRITTEN. Scheduled for Phase 13** — see `PHASES.md`.

This file is a placeholder on purpose. A specification for the machine-learning layer written
before the layer beneath it is validated would describe an intention, and §83
forbids presenting an intention as a result.

## Constraints already fixed

These are decided and will bind whoever writes this document.

- Every feature carries feature time, information time and availability time.
  A CPI value released at 13:30 UTC must not appear in an observation before
  13:30 UTC (§30).
- No future normalisation, no future scaling, no test-set calibration, no
  test-set threshold selection (§72).
- Walk-forward, with every fold's result stored.
- Complexity must earn its place out of sample. Model selection is never on
  backtest return alone (§74).
