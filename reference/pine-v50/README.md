# TradingView line, builds v41–v50 — display-only reference

These are the operator's current TradingView scripts (supplied 2026-10-11), kept here so that the
website can be checked against them. **They are not the counted system.** Under
`audit/PREREGISTRATION.md` Amendment 6, only the website's forward tests count. Under Amendment 7,
the defects these builds fixed that also existed on the website were ported to `quantum/`.
`artefacts/` (v32) remains the frozen Pine reference of §2.

Hashes are in `SHA256SUMS` (`sha256sum -c SHA256SUMS` from this folder).

| File | Build stamp | Role on TradingView |
|---|---|---|
| `XAUUSD_Quantum_5_0_Master.pine` | v50 | the live indicator |
| `XAUUSD_Quantum_5_0_Strategy.pine` | **v41** (see note 1) | Treatment arm |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` | v48 | Control arm |
| `XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine` | v48 | Challenger (fast trend, H1) |
| `XAUUSD_Quantum_5_0_Strategy_H2.pine` | v48 | the Pine line's H2 = **H3 on the website** |
| `XAUUSD_Quantum_5_0_Diagnostics.pine` | v44 | diagnostics companion |
| `XAUUSD_Quantum_5_5_Visuals.pine` | v48 | chart visuals, H2 card |
| `XAUUSD_Quantum_5_0_EdgeCases.pine` | v33 | run-once assertion table |

## Parity map: every engine change in these builds, against the website

| Pine | What | Website (`quantum/`) |
|---|---|---|
| F-A41 (v38) | HTF requests: last completed bar, the same live and in history | **already equal** (D-01 since web.1) |
| F-A46 (v41) | volume profile rebuilt on every bar | **already equal** (D-06) |
| F-A39 (v33) | Cornish-Fisher inverse only inside its domain | **guarded differently**: an inverse is kept only where it solves q(w) = z (D-08, Pine v32's F-A38). Both stop the divergence |
| F-A44 (v39) | PDL-first branch in the analog statistics | **already equal** (the Master had it; only the strategy twins lacked it) |
| F-A47 (v42) | exits placed on the entry bar | **already equal**: the backtest protects the first bar after entry |
| F-A40 (v34) | MTF scores normalised by the votes available on the chart's timeframe | **ported in web.5** (Amendment 7) |
| F-A48 (v43) | plan built on the final scores | **ported in web.5** |
| F-A38 (v33, Pine numbering) | constrained calibration fit | **ported in web.5** |
| F-A45 (v40) | feature accuracy among resolved analogs | **ported in web.5** |
| F-A49 (v44) | analog win-rate side by the final scores; PF labelled "resolved" | not applicable: the website shows the analog win rate without choosing a side |
| F-A52 (v46) | regime size haircut applied to $ risk and lots | **ported** (`report.py`, display; the website lacked the haircut entirely) |
| F-A53 (v50) | macro label: bull-ish / bear-ish with its score | **already equal**: the website writes BULL-ISH / BEAR-ISH with the score beside it |
| v49 | alerts on first BOS / CHoCH / MSS / sweep | **ported** (`notify.py`) |
| v37 | session intelligence moved to Visuals | display layout only |
| A3 H2 (v36) | sweep-to-value rule | **arm H3** (`quantum/arm_h3.py`, Amendment 7 §3) |

## Notes found while comparing

1. **The Treatment file is behind the other arms.** `Strategy.pine` is at v41, while
   `Strategy_OLDGATES.pine` and `Strategy_CHALLENGER.pine` are at v48. Treatment lacks F-A47 (exits on the
   entry bar), F-A48 (plan side) and F-A49. On TradingView, the arms therefore differ by more than their
   gates. This does not affect the website, whose three arms share one engine.
2. **This line branched from v31, not v32.** It has `SCHEMA_BUILD = 5` and its own F-A38 / F-A39 numbering;
   the website and `artefacts/` carry v32's Cornish-Fisher guard (F-A38 in this repository's numbering).
