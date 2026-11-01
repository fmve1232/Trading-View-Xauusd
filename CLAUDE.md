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
  arm H3 is the same rule) docks under DECISION and a LIQUIDITY · SWEEPS block under LIQUIDITY (`panel_check.py` 6); the
  bottom-left panel is drawn only while it has a section. **TradingView shows ONE table per position per script**
  (F-A69: v75/v76's three top-right dock tables showed only the last): since v77 all docks are one table with one gap,
  and no other Visuals table may take its corner. Its rows share heights, so since v78 every dock cell is at most 2 lines
  and headers 1 (`panel_check.py` 6). Since v79 the panel opens with MARKET AT A GLANCE (eight plain answers from values
  Visuals computes; BIAS and ODDS name the Master's cells, never a second engine number; `panel_check.py` 7 executes
  the nearest-level search and the ROOM marks). Since v80 its default style is text GAUGES (`f_gBar` score bars, `f_gPos`
  sliders; executed vs references in `panel_check.py` 7); the v79 sentences stay as "Glance style = Text (v79)". Since v81 the glance is a BOTTOM TICKER by default (six tiles at
  bottom centre, lifted above the Master's plan strip; `panel_check.py` 8), and Visuals' drawings were trimmed by default
  (BB, FVG / OB boxes, session shading, footprint OFF; every switch kept; since v87 FVG / OB, session shading, pivots and
  PMH/PML are ON again, BB / VWAP W-M / footprint stay OFF; `showFVG` / `showOB` there only DRAW, the
  Master's same-named inputs are the engine's and stay ON, recorded in `inputs_check.py` KNOWN). `panel_check.py` 9 EXECUTES
  every ticker tile and H2 TREND text with missing (na) inputs: no "NaN" may reach the screen (F-A70). Since v86 the panel
  ends with a CHECKS · RISK section and the ticker has two more tiles (daily regime, checks) and a forward-record
  banner: the Phase 1 audit's display items (score note, dated NFP / CPI / FOMC calendar with shading and alert, cost vs
  ATR, churn, untested daily regime, position size, typed daily loss cap, Wilson ranges, the website's record typed in).
  All display only; `v86_check.py` executes them (the calendar list must be extended before 2027-12-10). **Since v88
  Visuals' MACRO is the Master's MACRO** (F-A76): `// MX-BEGIN` … `// MX-END` is the Master's macro chain copied verbatim
  (every statement macroIntelScore / Label depend on), and the ticker tile, panel row and glance show its verdict; the
  five GD drivers are labelled OTHER DRIVERS · context (no headline net arrow). Any engine change to the Master's macro
  lines must be copied into the MX block (`v88_check.py` fails otherwise). v88 also turned the v87 drawings and
  Visuals' approximate ~BOS / ~CHoCH labels OFF (operator: "too much noisy"). **Since v95 Visuals' structure is the Master's** (F-A85): `// SX-BEGIN` … `// SX-END` is the Master's slice for bosLabel* / chochLabel* / mssLabel* / fvgDetected, copied verbatim (`sx_check.py`); labels (BOS / CHoCH / MSS), CHURN and FVG boxes read it, and the ADX / adaptive-ATR inputs in Visuals are the engine's own. Any engine change to those Master lines must be re-copied (`sx_check.py` fails otherwise). Since v89 the record banner has two lines (H4 15m and H3 1H, each
  arm's DECIDING record, typed from the ledger; `v86_check.py` 7 recomputes the defaults from the ledger files) and names 15m
  the decision timeframe; refresh the record defaults from the ledger when they are re-sent. Since v93 the CHECKS · RISK section has a BRACKET row (operator, 2026-10-31: SL $500 / TP $1000 at 0.5 lot, inputs in money or MT5 points): every H2 signal on the loaded chart scored TP-or-SL-first from its close, with the 95% range, break-even incl. cost and net $; Unlinked it scores H2 (= arm H3) (`v93_check.py`); since v94, with the LINK connected, it scores the Master's own BUY / SELL and RISK uses the Master's plan stop and lots (`v94_check.py`). Since v90 the Brief replicates the website's per-timeframe H4 verdict
  (`h4Losing`, F-A77; records typed in, `brief_trace.py` 7). **F-A78 (open, website): the engine's calibrated P has no
  skill out of sample** (AUC ~0.5): never present it as a probability; the A11 research data is sealed, never open it here.
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
python3 audit/tools/undeclared.py artefacts/*.pine   # since v95 a gate: exits 1 on any finding (F-A84)
python3 audit/tools/order.py      artefacts/*.pine   # since v95 a gate (F-A84: v94 shipped an order error while it exited 0)
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
python3 audit/tools/h2_age_check.py     # H2 card: last signal's age / outcome / STALE, executed vs a reference (v76)
python3 audit/tools/bug_scan.py artefacts/*.pine  # bug classes (v83); since v91 a GATE: an untriaged R1 / A1 / R4 hit exits 1 (F-A81)
python3 audit/tools/v86_check.py        # v86 checks & risk, calendar, Master SIGNAL text, EdgeCases timing, executed (~40 s)
python3 audit/tools/v88_check.py        # Visuals' MACRO == the Master's: MX block verbatim + complete, executed from both files
python3 audit/tools/ledger_stats.py     # forward-ledger statistics (system of record), intervals, PF, drawdown, pre-cost mean (v90)
python3 audit/tools/pine_web_parity.py  # Pine probability blocks + outcome race == the website's engine, executed, with positive controls
python3 audit/tools/v91_check.py        # v91: Master lots include cost (loss at stop <= stated risk), 25k default, executed (B-01 / B-02)
python3 audit/tools/v92_check.py        # v92: risk lock counts every bar (backtestAllBars, B-09); news-time cost in Visuals (B-03), executed
python3 audit/tools/v93_check.py        # v93: Visuals' BRACKET tracker (operator's SL / TP on H2 signals), executed vs a reference and on real bars
python3 audit/tools/v94_check.py        # v94: the Master -> Visuals LINK (decision x stop, lots), decoding + tracker end to end, executed
python3 audit/tools/sx_check.py         # v95: Visuals' structure / CHURN / FVG = the Master's engine (SX block verbatim + complete + wired)
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
  none). Measure a construct's real cost with a compile before relying on the model for it. **The Master has < ~80 tokens of
  headroom** (F-A72: v84, +~40 raw tokens of alert text, failed at 100,332): `compile_est.py` caps it at the v72 estimate;
  any Master addition needs identical-output savings measured first, otherwise it goes into Visuals. Measured (v85 probes): the Master is about 100,170-100,212 (45-85 free); a Master -> Visuals link (hidden plot + input.source) was declined by the operator (2026-10-21), then **allowed on 2026-10-31 (v94)**: two Data-Window plots `LINK decision x stop` / `LINK lots`, paid for by identical-output rewrites (`v94_check.py`); Visuals reads them through two source inputs the operator picks once per chart (RUNBOOK Step 1a). **And never inline a big function into the main body:**
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
| `audit/FINDINGS_TRACEABILITY.md` | All findings, F-A01 … F-A85. |
| `audit/CHANGELOG.md` | Per-build detail, v1 → current. |
| `audit/RUNBOOK.md` | How to collect data from TradingView. |
| `audit/MANIFEST.sha256` | Hashes; the audit's stop rule depends on these. |
| `audit/VALUE_TRACEABILITY.md` | Every value the operator acts on: variable, Master line, formula, verifying tool (generated by `value_map.py`). |
| `audit/tools/` | `trace.py`, `precheck.py`, `undeclared.py`, `order.py`; `race_model_check.py` / `formula_check.py` (test the maths on synthetic data, not the Pine); `deadcode.py` (unread / self-only / write-only / uncalled symbols; `retained.txt` lists code kept on operator instruction); `diag_parity.py` (Diagnostics and Brief engines == Treatment; since v39 the stats engine Master == Treatment; since v54 the 22 DECISION / gate / veto / reach lines Master == Treatment); `build_diag.py` (regenerates `Diagnostics.pine` from the Treatment twin — edit DIAG blocks there, not in the artefact); `sequence.py` (reads that run before a same-bar write, i.e. an earlier stage or last bar; triage by hand); `pine_exec.py` + `formula_trace.py` (execute the probability/statistics blocks AS WRITTEN in each .pine against first-principles references — run on every engine copy); `fix_v33.py` (F-A38/F-A39, applied v33); `fix_v34.py` (F-A40, applied v34); `h2_parity.py` + `h2_trace.py` (H2 arm); `expectancy_check.py` (expectancy / PF / t-interval / scorecard, executed, vs 'Trading is Math'); `regime_check.py` (regime engine across all volatility percentiles + ATR floor, executed); `decision_check.py` (trend exclusivity, entry gates, veto, DECISION precedence, executed); `value_map.py` (regenerates / checks `VALUE_TRACEABILITY.md`); `build_brief.py` + `brief_panel.pine` + `brief_trace.py` (Market Brief companion, v52); `edgecase_cites.py` (EdgeCases cites Master CODE, each anchor exactly one line, v54); `moved_check.py` (moved-feature ledger: definitions frozen from the build they left, still displayed where they went, v58); `refactor_check.py` (identical-output rewrites executed against the code they replaced, v59); `inputs_check.py` (every input and default, v63); `tf_check.py` (every chart timeframe executed, session engine vs the IANA DST rules, v63); `macro_check.py` (each macro correlation traced to its request: same-bar pairing, macroTF windows; model with known r, v64; each factor counted once, executed, and the Brief's five display-only drivers, v65); `fix_v64.py` / `fix_v65.py` (F-A64 / F-A65, applied); `fix_v67.py` (`(x ? 1 : 0)` → `_b1(x)`, applied v67, UNDONE v68); `fix_v68.py` (F-A66/F-A67: the Master derived from v66, checked byte for byte; dashboard functions NOT inlined since v69); `fix_v70.py` / `fix_v71.py` (GD block + cell queues in the Master; both FAILED to compile, F-A68; kept as the record, not applied since v72); `panel_check.py` (v73: Visuals' terminal panel = its three cards, row for row); `bug_scan.py` + `audit/STRATEGY_MAP_AND_BUG_CATALOGUE.md` (v83: bug-class screens with positive controls, every hit triaged; the strategy map); `fix_v83.py` (F-A71 news label, applied); `fix_v84.py` (H2 swing sweeps in the Master's alert() line: FAILED to compile, F-A72; kept as the record, not applied since v85; the alert is in Visuals, `panel_check.py` 10); `audit/ALERTS_SETUP.md` (what fires, one-alert setup); `h2_age_check.py` (v76: the H2 card's signal age / outcome / STALE marking, executed bar by bar vs an independent reference); `probe_gd.py` + `audit/probes/` (over-limit probes that measure the drivers' real cost in the Master, F-A68); `compile_est.py` + `lexcount.py` (compiled-token estimate with calls expanded, F-A66); `pinelimits.py` (compile-error classes the others miss, incl. "no output call", G9 non-const input default, G10 higher-timeframe `[1]` request with `lookahead_off`, G11 user-function call arity (CE10165), G12 local shadowing a global (warning)); `fix_v86.py` (F-A73 SIGNAL cell "score", applied) + `v86_check.py` (v86 additions executed); `v88_check.py` (Visuals' MACRO = the Master's, F-A76); `ledger_stats.py` + `engine_dump.py` + `engine_calibration.py` (v90: forward-ledger statistics; the website engine run read-only and its probability scored, F-A78); `audit/INSTITUTIONAL_AUDIT_v90.md` (the 17-phase audit); `audit/RESEARCH_AUDIT_PHASE1.md` (Phase 1 research and code audit); `audit/v90_audit/` (independent v90 audit: `AUDIT_REPORT_v90.md` Reports 1–13, `AUDIT_STATE.md`, register CSVs) with `v90_register.py` (every global symbol), `v90_slice.py` (what can change the DECISION), `v90_mutation.py` (seeded defects in a scratch copy: semantic vs tripwire kills); `fix_v91.py` + `v91_check.py` (F-A79 / F-A80, applied v91); `fix_v92.py` + `v92_check.py` (F-A82 / F-A83, applied v92); `fix_v93.py` + `v93_check.py` (BRACKET tracker, v93); `fix_v94.py` + `v94_check.py` (Master -> Visuals LINK, v94); `fix_v95.py` + `sx_check.py` (engine structure in Visuals, F-A85, v95). |
