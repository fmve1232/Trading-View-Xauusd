# Working conventions for this repo

## Delivery (operator instruction, 2026-09-09)

**After every code change, send ALL artefact files together — not only the changed ones —
and post the build record in chat.**

The operator pastes these into TradingView by hand. Sending only the changed files risks a
mismatched set on the chart, and there is no way to tell from the TradingView side which
build a given script is on. A full set every time removes that class of mistake.

There are **eight** artefacts (since v36). Seven are chart scripts; `EdgeCases.pine` is a
run-once diagnostic that is removed after reading its table. `Diagnostics.pine` (v17)
carries the features that no longer fit under the Master's compiled-token limit, on the
Treatment twin's engine verbatim. `Strategy_CHALLENGER.pine` (v31) is the pre-registered
forward-test arm H1; `Strategy_H2.pine` (v36) is arm H2 (sweep-to-value), whose signal block is
byte-identical in Visuals and (v37) the Master, which shows it as a second decision, H2 SETUP.
Send all eight unless the
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

- **SYSTEM OF RECORD (A7, operator, 2026-10-08): the website only** — its pre-registration on the default branch
  (`claude/audit-prompt-real-artefacts-nekqv6`, Amendment 6). Every file on THIS branch is **display only**: its scorecards and amendments A1–A6 are not
  counted and must never be cited as evidence; a change here restarts nothing. Do not edit the website, its freeze key
  or the default branch from this line of work.
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
- **Forward record lives on the chart (v34):** each strategy arm ends with a FORWARD-TEST SCORECARD
  (identical code in all three arms; unit = position, partial exits summed). Keep it identical, or
  the A/B hunk counts break. The registered timeframe is 15M; 5M is for timing only (PREREG A2.4).
- **H2 block:** `// H2-BEGIN` … `// H2-END` must stay byte-identical in Visuals, Strategy_H2 and the
  Master (`h2_parity.py`, which also checks Visuals' `SESSIntel` block equals the Treatment's
  `f_sessionIntel`); `h2_trace.py` executes it against its specification. The Master's H2 SETUP is
  display + alert only: it never changes the DECISION (PREREG A4).
- **Token estimates are estimates.** Compiled ≈ lexical × 2.515 (measured on v23: 100,820 /
  40,081; v14 gave 2.466). Keep the Master ≥ 2% under 100,256 at that ratio.
- The checkers narrow the search; **they do not replace the compiler.** Three static passes
  gave false confidence this session, including one syntax error introduced by a fix.

## Layout

| Path | What |
|---|---|
| `artefacts/` | The eight Pine v6 files. |
| `audit/PREREGISTRATION.md` | The frozen forward test: holdout start, frozen hashes, decision rules. |
| `audit/XAUUSD_Forward_Test_Log.xlsx` | The operator's forward log and automatic verdicts (formulas verified against Python). |
| `audit/AUDIT_PROMPT.md` | The audit prompt, pinned to current hashes. |
| `audit/FINDINGS_TRACEABILITY.md` | All findings, F-A01 … F-A48. |
| `audit/CHANGELOG.md` | Per-build detail, v1 → current. |
| `audit/RUNBOOK.md` | How to collect data from TradingView. |
| `audit/MANIFEST.sha256` | Hashes; the audit's stop rule depends on these. |
| `audit/tools/` | `trace.py`, `precheck.py`, `undeclared.py`, `order.py`; `race_model_check.py` / `formula_check.py` (test the maths on synthetic data, not the Pine); `deadcode.py` (unread / self-only / write-only / uncalled symbols; `retained.txt` lists code kept on operator instruction); `diag_parity.py` (Diagnostics engine == Treatment, and since v39 the stats engine Master == Treatment); `build_diag.py` (regenerates `Diagnostics.pine` from the Treatment twin — edit DIAG blocks there, not in the artefact); `sequence.py` (reads that run before a same-bar write, i.e. an earlier stage or last bar; triage by hand); `pine_exec.py` + `formula_trace.py` (execute the probability/statistics blocks AS WRITTEN in each .pine against first-principles references — run on every engine copy); `fix_v33.py` (F-A38/F-A39, applied v33); `fix_v34.py` (F-A40, applied v34); `h2_parity.py` + `h2_trace.py` (H2 arm); `pinelimits.py` (compile-error classes the others miss, incl. "no output call", G9 non-const input default, G10 higher-timeframe `[1]` request with `lookahead_off`). |
