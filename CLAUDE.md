# Working conventions for this repo

## Production vs reference (operator decision, 2026-09-27)

**The Python website (`quantum/`, `site/`) is the production system and the primary forward
test** (`audit/PREREGISTRATION.md` Amendment 2 and §7). TradingView is **not** a dependency:
the operator does not paste builds into TradingView. The Pine artefacts are the frozen
reference implementation of the model (v32), used only to validate the website. The delivery
rule below applies only when a `.pine` file is actually changed.

## Delivery (operator instruction, 2026-09-09)

**After every code change, send ALL artefact files together — not only the changed ones —
and post the build record in chat.**

The operator pastes these into TradingView by hand. Sending only the changed files risks a
mismatched set on the chart, and there is no way to tell from the TradingView side which
build a given script is on. A full set every time removes that class of mistake.

There are **seven** artefacts (since v31). Six are chart scripts; `EdgeCases.pine` is a
run-once diagnostic that is removed after reading its table. `Diagnostics.pine` (v17)
carries the features that no longer fit under the Master's compiled-token limit, on the
Treatment twin's engine verbatim. `Strategy_CHALLENGER.pine` (v31) is the pre-registered
forward-test arm H1. Send all seven unless the
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

- **ONE SYSTEM OF RECORD (operator decision 2026-10-06, `PREREGISTRATION.md` Amendment 6):** only the
  website's forward tests count (§7 arms on 1H and the Amendment 5 H2). The Pine line developed separately
  on branch `claude/xauusd-developed-files-tmnk9g` (builds v33–v41, with its own amendments A1–A6 and its own
  15M H2) is **display only**: never cite its scorecards or verdicts as evidence, and do not merge it into
  this line without a new amendment.
- **HOLDOUT FREEZE (from 2026-09-28 00:00 UTC):** the website engine is frozen by its freeze key
  (`PREREGISTRATION.md` §7; any change to `holdout.ENGINE_SOURCES` or `config.py` restarts it). The Pine
  reference files (Master, Treatment, Control, Challenger) stay at the hashes in `audit/PREREGISTRATION.md` §2. Only signal-neutral compile/runtime
  fixes and display-only changes are allowed; any other change restarts the forward test.
- **Do not tune** thresholds, weights or gates against results measured on this price
  history. The IS/OOS boundary slides and the window already had parameters selected on it.
  See `audit/AUDIT_PROMPT.md` §9. Diagnose instead; the only real fix is a frozen holdout.
- **Do not reconstruct** `cost_invariant.py` or `validate.py` from the comments describing
  them — that tests the reconstruction, not the original.
- **Never mark anything PASS that was not executed.** `NOT RUN` is the honest verdict.
- Changes to the strategy twins go to **both arms identically**, or the A/B breaks. The
  diff between them must stay at its five hunk headers; Treatment vs Challenger must stay at
  four (stamp, title, role, trend gate) and engine changes go into the Challenger too. Engine changes also go into
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
| `artefacts/` | The seven Pine v6 files. |
| `audit/PREREGISTRATION.md` | The frozen forward test: holdout start, frozen hashes, decision rules. |
| `audit/XAUUSD_Forward_Test_Log.xlsx` | The operator's forward log and automatic verdicts (formulas verified against Python). |
| `audit/AUDIT_PROMPT.md` | The audit prompt, pinned to current hashes. |
| `audit/FINDINGS_TRACEABILITY.md` | All findings, F-A01 … F-A38. |
| `audit/CHANGELOG.md` | Per-build detail, v1 → current. |
| `audit/RUNBOOK.md` | How to collect data from TradingView. |
| `audit/MANIFEST.sha256` | Hashes; the audit's stop rule depends on these. |
| `relay/` | Cloudflare Worker tick relay for the site's live chip (display only; `relay/README.md`). |
| `audit/tools/` | `trace.py`, `precheck.py`, `undeclared.py`, `order.py`; `race_model_check.py` / `formula_check.py` (test the maths on synthetic data, not the Pine); `deadcode.py` (unread / self-only / write-only / uncalled symbols; `retained.txt` lists code kept on operator instruction); `diag_parity.py`; `build_diag.py` (regenerates `Diagnostics.pine` from the Treatment twin — edit DIAG blocks there, not in the artefact); `sequence.py` (reads that run before a same-bar write, i.e. an earlier stage or last bar; triage by hand); `pinelimits.py` (compile-error classes the others miss, incl. "no output call").; `xcheck_dukascopy.py` (Twelve Data vs Dukascopy price cross-check for the website's data; runs on GitHub via the `xcheck-dukascopy` workflow). |

## Web platform (`quantum/`, `site/`)

- `quantum/` ports the Master engine to Python for the GitHub Pages site. An engine change in the
  Pine artefacts is ported to `quantum/` in the same build (and the reverse); `python -m pytest -q
  tests` must pass, including `test_no_lookahead`.
- The same non-negotiables apply: defaults in `quantum/config.py` are the Pine input defaults and are
  **not tuned**. Changing any of them changes the config hash, which restarts the frozen forward
  holdout — by design.
- Deliberate differences from Pine are listed in `docs/PLATFORM.md` (D-01 … D-07 and D-09 … D-10; D-08 is now shared with Pine v32). Any other
  difference is a bug.
- The artefact delivery rule above applies to the `.pine` files only; the site deploys itself.

