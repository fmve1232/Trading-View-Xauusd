# Working conventions for this repo

## Delivery (operator instruction, 2026-09-09)

**After every code change, send ALL artefact files together — not only the changed ones —
and post the build record in chat.**

The operator pastes these into TradingView by hand. Sending only the changed files risks a
mismatched set on the chart, and there is no way to tell from the TradingView side which
build a given script is on. A full set every time removes that class of mistake.

There are **six** artefacts (since v17). Five are chart scripts; `EdgeCases.pine` is a
run-once diagnostic that is removed after reading its table. `Diagnostics.pine` (v17)
carries the features that no longer fit under the Master's compiled-token limit, on the
Treatment twin's engine verbatim. Send all six unless the
operator says to drop EdgeCases.

**The chat record must include**, every time:

| Field | Why |
|---|---|
| Build number and commit hash | so a chart can be traced back to a build |
| Per-file line count, bytes, SHA-256 | so a paste can be verified |
| Which files changed since the last send | so re-pasting unchanged files is optional |
| Checker results | precheck / undeclared / order / manifest |
| What visibly changes on the chart | so "looks different" is expected, not alarming |

Generate it with:

```sh
sha256sum artefacts/*.pine
python3 audit/tools/precheck.py   artefacts/*.pine
python3 audit/tools/undeclared.py artefacts/*.pine
python3 audit/tools/order.py      artefacts/*.pine
python3 audit/tools/deadcode.py   artefacts/*.pine
python3 audit/tools/pinelimits.py artefacts/*.pine
python3 audit/tools/diag_parity.py
sha256sum -c audit/MANIFEST.sha256
```

## Non-negotiables carried from the audit

- **Do not tune** thresholds, weights or gates against results measured on this price
  history. The IS/OOS boundary slides and the window already had parameters selected on it.
  See `audit/AUDIT_PROMPT.md` §9. Diagnose instead; the only real fix is a frozen holdout.
- **Do not reconstruct** `cost_invariant.py` or `validate.py` from the comments describing
  them — that tests the reconstruction, not the original.
- **Never mark anything PASS that was not executed.** `NOT RUN` is the honest verdict.
- Changes to the strategy twins go to **both arms identically**, or the A/B breaks. The
  diff between them must stay at its five hunk headers. Engine changes also go into
  `Diagnostics.pine` (outside its `DIAG` fences); `diag_parity.py` fails otherwise.
- **Do not delete features** (operator instruction, 2026-09-26). Wire them; if a file has
  no room, move the feature to a companion that runs the same engine, never drop it.
- **Token estimates are estimates.** Compiled ≈ lexical × 2.515 (measured on v23: 100,820 /
  40,081; v14 gave 2.466). Keep the Master ≥ 2% under 100,256 at that ratio.
- The checkers narrow the search; **they do not replace the compiler.** Three static passes
  gave false confidence this session, including one syntax error introduced by a fix.

## Layout

| Path | What |
|---|---|
| `artefacts/` | The six Pine v6 files. |
| `audit/AUDIT_PROMPT.md` | The audit prompt, pinned to current hashes. |
| `audit/FINDINGS_TRACEABILITY.md` | All findings, F-A01 … F-A34. |
| `audit/CHANGELOG.md` | Per-build detail, v1 → current. |
| `audit/RUNBOOK.md` | How to collect data from TradingView. |
| `audit/MANIFEST.sha256` | Hashes; the audit's stop rule depends on these. |
| `audit/tools/` | `trace.py`, `precheck.py`, `undeclared.py`, `order.py`; `race_model_check.py` / `formula_check.py` (test the maths on synthetic data, not the Pine); `deadcode.py` (unread / self-only / write-only / uncalled symbols; `retained.txt` lists code kept on operator instruction); `diag_parity.py`; `build_diag.py` (regenerates `Diagnostics.pine` from the Treatment twin — edit DIAG blocks there, not in the artefact); `pinelimits.py` (compile-error classes the others miss, incl. "no output call"). |
