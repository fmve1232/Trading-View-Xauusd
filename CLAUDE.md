# Working conventions for this repo

## Delivery (operator instruction, 2026-09-09; paste set narrowed 2026-10-13)

**After every code change, send the CHART SET together — every file in it, changed or not —
plus any other artefact that changed, and post the build record in chat.**

- **Chart set** (pasted routinely): `Master.pine`, `Visuals.pine` and `Brief.pine`, and `Diagnostics.pine`
  (the operator adds it when wanted).
- **On the chart (operator, 2026-10-17):** the free plan allows two indicators, so **Master + Visuals** are always on;
  Brief or Diagnostics is swapped into the second slot when needed. The four cannot be merged into two without cutting
  features (each engine copy is at 98-99.6% of the token limit). Anything the operator needs every day must therefore
  be visible in Master or Visuals (v66 copied the Brief's five gold drivers into Visuals). Since v73 Visuals shows its
  candle, H2 and driver values in ONE terminal panel (default bottom left since v74, clear of the Master's top-right
  dashboard and bottom-right plan); the three separate cards stay selectable (`panel_check.py` holds the panel equal to
  them). Since v74 the five drivers are docked UNDER the Master's MACRO column by default (same anchor, no frame, the
  Master's nine column widths x Density; `dashMode` / `textSize` / `density` copied from the Master and held equal by
  `inputs_check.py`; `panel_check.py` 5 reads the geometry from the Master's code). Since v75 the H2 card (the website's
  arm H3 is the same rule) docks under DECISION and a LIQUIDITY · SWEEPS block under LIQUIDITY, each its own table and
  gap (`panel_check.py` 6); the bottom-left panel is drawn only while it has a section.
- **Repo set** (kept unchanged, never deleted, sent only when it changes): `Strategy.pine`, `Strategy_OLDGATES.pine`,
  `Strategy_CHALLENGER.pine`, `Strategy_H2.pine` (display-only arms under A7), `EdgeCases.pine` (run-once).
- The build record still lists **all nine** files with their hashes, so any copy on the chart can be checked.
- Comments stay in the pasted files (operator, 2026-10-13). TradingView does not count them toward its token limit,
  and they carry the audit trail.

The operator pastes these into TradingView by hand. Sending only the changed files risks a
mismatched set on the chart, and there is no way to tell from the TradingView side which
build a given script is on. A full set every time removes that class of mistake.

There are **nine** artefacts (since v52). Eight are chart scripts; `EdgeCases.pine` is a
run-once diagnostic that is removed after reading its table. `Diagnostics.pine` (v17)
carries the features that no longer fit under the Master's compiled-token limit, on the
Treatment twin's engine verbatim. `Strategy_CHALLENGER.pine` (v31) is the pre-registered
forward-test arm H1; `Strategy_H2.pine` (v36) is arm H2 (sweep-to-value), whose signal block is
byte-identical in Visuals and (v37) the Master, which shows it as a second decision, H2 SETUP.
`Brief.pine` (v52) is the website's Market Brief on the chart (trend, lean, last sweep, target,
what to do, the arm-H4 playbook, gates), on the Treatment engine verbatim like Diagnostics: build it
with `audit/tools/build_brief.py` (panel source `audit/tools/brief_panel.pine`), check it with
`brief_trace.py`, which executes it against the website's own `arm_h4.py` and `app.js`. Since v57 it also carries the
engine cross-check line and data-feed status (ENGINE / DATA rows); since v59 the Master shows them again too.
Which of the nine are sent each time: see the chart set / repo set rule above.

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
python3 audit/tools/diag_parity.py      # Diagnostics and Brief engines == Treatment
python3 audit/tools/brief_trace.py      # Market Brief vs the website's code (~40 s)
python3 audit/tools/regime_check.py      # low / normal / high / abnormal volatility
python3 audit/tools/decision_check.py    # trend exclusivity, gates, veto, DECISION precedence
python3 audit/tools/expectancy_check.py
python3 audit/tools/value_map.py --check # traceability table current
python3 audit/tools/edgecase_cites.py    # EdgeCases code anchors still match the Master
python3 audit/tools/moved_check.py       # features moved between files kept their exact definitions and display
python3 audit/tools/refactor_check.py    # token-saving rewrites print exactly what the code they replaced printed
python3 audit/tools/inputs_check.py      # every input: valid, consistent across copies, = the frozen defaults, lengths >= 1
python3 audit/tools/tf_check.py         # every chart timeframe 1m..1M executed; DST vs IANA; sessions (~25 min)
python3 audit/tools/macro_check.py      # every macro correlation pairs gold and the asset over the same completed bar
python3 audit/tools/compile_est.py      # compiled-token estimate (calls expanded), calibrated on compiler reports
python3 audit/tools/panel_check.py      # Visuals' terminal panel shows exactly what its three cards show (v73)
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
  `Diagnostics.pine` and `Brief.pine` (rebuild both); `diag_parity.py` fails otherwise.
- **Do not delete features** (operator instruction, 2026-09-26). Wire them; if a file has
  no room, move the feature to a companion that runs the same engine, never drop it.
  **Reaffirmed 2026-10-16: "we will not remove anything, every value was added with a purpose".** Moving a
  feature does not license removing it from where it was; free tokens by identical-output rewrites
  (`refactor_check.py`), and the Master must DISPLAY every value it computes (`deadcode.py` fails otherwise).
  **Reaffirmed 2026-10-17: "don't delete anything, look for its purpose and wire it up".** Since v67 EVERY file has
  0 dead and 0 structural (no exemptions: `deadcode.py` fails on any unread value, tuple slots included); the only
  accepted case is a value displayed by a companion running the same code (Diagnostics / Visuals), which is checked.
  An unread value is wired into a display, never removed; `deadcode.py --all` lists the companion-wired ones.
- **Forward record lives on the chart (v34):** each strategy arm ends with a FORWARD-TEST SCORECARD
  (identical code in all three arms; unit = position, partial exits summed). Keep it identical, or
  the A/B hunk counts break. The registered timeframe is 15M; 5M is for timing only (PREREG A2.4).
- **H2 block:** `// H2-BEGIN` … `// H2-END` must stay byte-identical in Visuals, Strategy_H2 and the
  Master (`h2_parity.py`, which also checks Visuals' `SESSIntel` block equals the Treatment's
  `f_sessionIntel`, and since v62 the block's INPUTS: `h2S1 / h2S4 / h2SD` are the RAW 1H / 4H / 1D scores in every
  file, never the engine's timeframe-gated `htf*Score`, F-A60); `h2_trace.py` executes it against its specification. The Master's H2 SETUP is
  display + alert only: it never changes the DECISION (PREREG A4).
- **GD block (v66):** `// GD-BEGIN` … `// GD-END` (the five display-only gold drivers) must stay byte-identical in
  `brief_panel.pine`, the Brief and Visuals (NOT the Master since v72, F-A68), and the engine lines Visuals copies for it must equal the Master's
  (`macro_check.py` E). Edit the panel source, rebuild the Brief, then copy the block into Visuals.
- **Token estimates are estimates — use `compile_est.py`, not lexical × 2.515** (F-A66: v67 compiled at 100,335 while
  lexical × 2.515 said ~97,800). TradingView EXPANDS every user-function call: a helper called many times costs its body
  each time, and a large function called once counts twice. So never "save tokens" by turning repeated code into a
  helper; repeated cells belong in a loop over data (the v70 / v71 cell queues are NOT in the Master: both builds failed). **The GD block is NOT in the Master** (F-A68): v70 and v71 with it
  failed at 103,989 and 104,510 while the model said ~99,600; the cause is not identified (not the record type: v71 had
  none). Measure a construct's real cost with a compile before relying on the model for it. **And never inline a big function into the main body:**
  TradingView also limits the main body (CE10295, v68 Master at 28,122 main-body lexical; 26,538 compiled). Gate
  (`compile_est.py`): both models below the limit and no higher than a build that really compiled, main body
  ≤ 26,538. Each compiler report goes into the tool's calibration.
- The checkers narrow the search; **they do not replace the compiler.** Three static passes
  gave false confidence this session, including one syntax error introduced by a fix.

## Layout

| Path | What |
|---|---|
| `artefacts/` | The nine Pine v6 files. |
| `audit/PREREGISTRATION.md` | The frozen forward test: holdout start, frozen hashes, decision rules. |
| `audit/XAUUSD_Forward_Test_Log.xlsx` | The operator's forward log and automatic verdicts (formulas verified against Python). |
| `audit/AUDIT_PROMPT.md` | The audit prompt, pinned to current hashes. |
| `audit/FINDINGS_TRACEABILITY.md` | All findings, F-A01 … F-A68. |
| `audit/CHANGELOG.md` | Per-build detail, v1 → current. |
| `audit/RUNBOOK.md` | How to collect data from TradingView. |
| `audit/MANIFEST.sha256` | Hashes; the audit's stop rule depends on these. |
| `audit/VALUE_TRACEABILITY.md` | Every value the operator acts on: variable, Master line, formula, verifying tool (generated by `value_map.py`). |
| `audit/tools/` | `trace.py`, `precheck.py`, `undeclared.py`, `order.py`; `race_model_check.py` / `formula_check.py` (test the maths on synthetic data, not the Pine); `deadcode.py` (unread / self-only / write-only / uncalled symbols; `retained.txt` lists code kept on operator instruction); `diag_parity.py` (Diagnostics and Brief engines == Treatment; since v39 the stats engine Master == Treatment; since v54 the 22 DECISION / gate / veto / reach lines Master == Treatment); `build_diag.py` (regenerates `Diagnostics.pine` from the Treatment twin — edit DIAG blocks there, not in the artefact); `sequence.py` (reads that run before a same-bar write, i.e. an earlier stage or last bar; triage by hand); `pine_exec.py` + `formula_trace.py` (execute the probability/statistics blocks AS WRITTEN in each .pine against first-principles references — run on every engine copy); `fix_v33.py` (F-A38/F-A39, applied v33); `fix_v34.py` (F-A40, applied v34); `h2_parity.py` + `h2_trace.py` (H2 arm); `expectancy_check.py` (expectancy / PF / t-interval / scorecard, executed, vs 'Trading is Math'); `regime_check.py` (regime engine across all volatility percentiles + ATR floor, executed); `decision_check.py` (trend exclusivity, entry gates, veto, DECISION precedence, executed); `value_map.py` (regenerates / checks `VALUE_TRACEABILITY.md`); `build_brief.py` + `brief_panel.pine` + `brief_trace.py` (Market Brief companion, v52); `edgecase_cites.py` (EdgeCases cites Master CODE, each anchor exactly one line, v54); `moved_check.py` (moved-feature ledger: definitions frozen from the build they left, still displayed where they went, v58); `refactor_check.py` (identical-output rewrites executed against the code they replaced, v59); `inputs_check.py` (every input and default, v63); `tf_check.py` (every chart timeframe executed, session engine vs the IANA DST rules, v63); `macro_check.py` (each macro correlation traced to its request: same-bar pairing, macroTF windows; model with known r, v64; each factor counted once, executed, and the Brief's five display-only drivers, v65); `fix_v64.py` / `fix_v65.py` (F-A64 / F-A65, applied); `fix_v67.py` (`(x ? 1 : 0)` → `_b1(x)`, applied v67, UNDONE v68); `fix_v68.py` (F-A66/F-A67: the Master derived from v66, checked byte for byte; dashboard functions NOT inlined since v69); `fix_v70.py` / `fix_v71.py` (GD block + cell queues in the Master; both FAILED to compile, F-A68; kept as the record, not applied since v72); `panel_check.py` (v73: Visuals' terminal panel = its three cards, row for row); `probe_gd.py` + `audit/probes/` (over-limit probes that measure the drivers' real cost in the Master, F-A68); `compile_est.py` + `lexcount.py` (compiled-token estimate with calls expanded, F-A66); `pinelimits.py` (compile-error classes the others miss, incl. "no output call", G9 non-const input default, G10 higher-timeframe `[1]` request with `lookahead_off`, G11 user-function call arity (CE10165), G12 local shadowing a global (warning)). |
