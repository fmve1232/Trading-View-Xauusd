# CALIBRATION specification

**Status: NOT WRITTEN. Scheduled for Phase 10** — see `PHASES.md`.

This file is a placeholder on purpose. A specification for calibration written
before the layer beneath it is validated would describe an intention, and §83
forbids presenting an intention as a result.

## Constraints already fixed

These are decided and will bind whoever writes this document.

- Train / calibrate / validate / test are separate. **Never calibrate on the
  final test set.**
- Metrics: Brier, log loss, reliability curve, ECE, MCE, calibration slope and
  intercept, with sample size and effective N alongside every one.
- Computed on **unclamped** probabilities; the `[0.05, 0.95]` clamp (D-04) is
  evaluated separately.
- Quantum 5.0's Platt fit rejects non-positive slopes and near-zero variance,
  and clamps the slope to `[0.02, 0.25]` — a clamped slope carries no evidence
  of how far outside the range the fit was (D-05).
