# PROBABILITY specification

**Status: NOT WRITTEN. Scheduled for Phase 9** — see `PHASES.md`.

This file is a placeholder on purpose. A specification for the probability engine written
before the layer beneath it is validated would describe an intention, and §83
forbids presenting an intention as a result.

## Constraints already fixed

These are decided and will bind whoever writes this document.

- A score is not a probability. `P(TP before SL | features)` must be
  distinguishable from "signal score = 72".
- Every probability declares its event, horizon, conditioning features, outcome
  definition and sample.
- Model order is empirical → logistic → Bayesian → ensemble. The simplest model
  that can be beaten comes first.
- The live engine clamps reported probabilities to `[0.05, 0.95]` (D-04). The
  clamp is a reporting bound, not the model's output, and the two must not be
  confused when scoring.
