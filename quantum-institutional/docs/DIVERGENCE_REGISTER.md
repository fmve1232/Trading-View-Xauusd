# Divergence register

Every place the Python engine will, or does, differ from Quantum 5.0.

The purpose is that no parity mismatch is ever explained after the fact. A
divergence that is in this register before the parity run is a known quantity;
one discovered during the run is a finding.

Status values: **REPRODUCED** (Python copies Pine, including any defect) ·
**PENDING** (will diverge when the relevant phase lands) · **CLOSED**.

| ID | Area | Status | Pine behaviour | Python behaviour | Effect |
|---|---|---|---|---|---|
| D-01 | `safe_div` guard | REPRODUCED | `b == 0 ? 0 : a / b` — `1e-12` passes and the result explodes to `1e13` | identical | none while reproduced; the fix is a magnitude guard and is a behaviour change |
| D-02 | SL/TP intrabar race | REPRODUCED | SL tested first; a bar touching both is a LOSS | identical | a tick-resolved race would relabel outcomes and change the whole calibration set |
| D-03 | Timeout accounting | REPRODUCED | timeout counts as a calibration **failure** and is **free** in EV | identical | pessimistic in one statistic, optimistic in the other, on the same observation |
| D-04 | Probability clamp | REPRODUCED | calibrated `p` clamped to `[0.05, 0.95]` | identical | a Brier score computed on clamped values is not the model's Brier score |
| D-05 | Platt slope clamp | REPRODUCED | slope clamped to `[0.02, 0.25]`; distinct fits collapse | identical | a clamped slope carries no evidence of how far outside the range the fit was |
| D-06 | Volume profile basis | PENDING | last-bar-only, marked basis (F-A07) | point-in-time, per bar | Python can compute per-bar what Pine can only compute on the last bar; results **will** differ historically |
| D-07 | Recursive seeds | PENDING | Pine seeds EMA/ATR with its own warm-up | must match Pine's seed exactly | mismatch decays but never reaches zero; excluded bars are declared in the parity report |
| D-08 | Bar feed | PENDING | TradingView's broker feed | whatever provider is configured | fourth-decimal and session-edge differences; mitigated by pinning TradingView's exported OHLCV as the parity input |
| D-09 | Macro/news timing | PENDING | Pine has no publication-time model | strict point-in-time (`data/pit.py`) | Python will be **more conservative** and should produce *fewer* signals around releases |
| D-10 | Regime threshold split | REPRODUCED | classification on raw, `liqReachScore` bump on rounded (**F-A17**) | identical, pinned by a test | +0.8 on `fEvBase` in the boundary bands; always upward |

## Rules

1. **Nothing is silently fixed.** Changing a REPRODUCED row to a corrected
   behaviour is a deliberate edit, recorded here, applied to both A/B arms
   identically, and measured.
2. **A PENDING row must be measured before it is accepted.** "Should be small"
   is not a measurement.
3. **A new divergence found during a parity run is a finding**, goes in
   `FINDINGS.md`, and gets a row here.
