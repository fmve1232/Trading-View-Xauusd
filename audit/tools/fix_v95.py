"""v95 (operator, 2026-10-31: "Copy the engine's code"): Visuals' structure, CHURN and FVG zones run on the MASTER'S
ENGINE CODE, copied verbatim (F-030 closed). Visuals only; display only; the Master is unchanged.

SX block (`// SX-BEGIN` ... `// SX-END`): every top-level Master statement the engine's structure flags (bosLabelBull /
Bear, chochLabelBull / Bear, mssLabelBull / Bear, the flags the Master's STRUCTURE cell and alerts use) and its FVG detector (fvgDetected) depend on,
transitively, in the Master's order (the same backward slice v88_check uses for MACRO), byte for byte. Lines Visuals
already had that are Master lines (safeDiv, grpCore, the winsorised gold return, bbBasis) MOVE into the block (MX keeps
only Master lines, so v88_check still holds); bbDev and volSma20 take the Master's exact text (same values: 2.0 * x == x *
2.0 exactly, and a `float` annotation). ONE exception: the Master's engine switch `showFVG` (default ON) is not
copied; Visuals' own `showFVG` (draw the boxes, default OFF) feeds fvgDetected, so the detector runs only when boxes are
drawn. Consumers now read the engine:
  - BOS / CHoCH / MSS labels: the engine's flags (no "~": they ARE the engine's), BOS line at the broken level
  - CHURN: direction changes of the engine's BOS breaks (was the one-pivot ~BOS detector)
  - FVG boxes: the engine's fvgDetected (adaptive-ATR x 0.3 minimum), age = the Master's FVG Max Bars default 30
  - order-block displacement and the ADX / DI display: the engine's adaptiveATR / adxVal / diplus / diminus
The duplicates they replace are merged, not features removed: the three "(match Master)" inputs (now the engine's own
adxLen / adxThreshold / showAdaptiveATR, held equal to the Master by inputs_check), their V-suffixed computations, the
one-pivot break detector (lastPH / lastPL stay: pivots, sweeps and S/R use them) and the ATR-based FVG minimum input."""
import re

M_FILE = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
TARGETS = ["bosLabelBull", "bosLabelBear", "chochLabelBull", "chochLabelBear", "mssLabelBull", "mssLabelBear", "fvgDetected"]
SKIP = {'showFVG = input.bool(true, "Fair Value Gaps (engine)"'}           # the one exception (see above)


def sx_lines(M):
    """the Master's top-level statements in the slice, in order (v88_check's statement / def-use rules)"""
    src = open("audit/tools/v88_check.py", encoding="utf-8").read()
    a = src.index("# ---- 2 complete: backward slice of the Master")
    b = src.index("Vset = set(V)")
    code = src[a:b].replace('need, want, done = set(), {"macroIntelScore", "macroIntelLabel", "macroIntelValid"}, set()',
                            "need, want, done = set(), set(TARGETS), set()")
    ns = {"M": M, "re": re, "TARGETS": TARGETS}
    exec(code, ns)
    out = []
    for idx in sorted(ns["need"]):
        a_, b_ = ns["info"][idx][:2]
        blk = [l for l in M[a_:b_] if l.strip() and not l.lstrip().startswith("//")]
        if any(blk[0].startswith(s) for s in SKIP):
            continue
        out += blk
    return out


V_EDITS = [   # (old, new): exact, each once
    ('showStruct   = input.bool(false, "BOS / CHoCH labels (~ = approximation, NOT the engine\'s signal)", group = grpS, tooltip = "Drawn by a '
     'simplified structure detector, not the Master\'s engine. Use them for chart reading; never treat a ~BOS or ~CHoCH as confirmation that the engine '
     'registered one.")',
     'showStruct   = input.bool(false, "BOS / CHoCH / MSS labels (the engine\'s)", group = grpS, tooltip = "v95: drawn from the Master\'s own '
     'structure engine, copied verbatim (SX block): the same BOS / CHoCH / MSS as the Master\'s STRUCTURE cell. OFF by default (v88: too noisy).")'),
    ('fvgMaxBars   = input.int(60,     "FVG max age (bars)", minval = 5, group = grpZ)\n'
     'fvgMinATR    = input.float(0.3,  "FVG min size (ATR)", minval = 0.05, step = 0.05, group = grpZ)\n',
     '// v95: the Master\'s FVG Max Bars (default and bounds); the minimum size is the engine\'s (0.3 x adaptive ATR, in fvgDetected)\n'
     'fvgMaxBars   = input.int(30,     "FVG max age (bars), as the Master\'s", minval = 10, maxval = 100, group = grpZ)\n'),
    ("// F-A08 PARITY INPUTS. Mirrors of the Master's ADX and Adaptive-ATR controls, needed\n"
     "// because the displacement threshold below is measured in adaptiveATR units, not raw ATR.\n"
     "// Keep all three equal to the Master's or the drawn order blocks stop matching the engine.\n", "// v95: the F-A08 parity inputs (ADX length / threshold, Adaptive ATR) are the engine's own now (SX block).\n"),
    ('adxLenV          = input.int(14,  "  ADX length (match Master)", minval = 1, group = grpZ)\n', ""),
    ('adxThresholdV    = input.int(25,  "  ADX threshold (match Master)", minval = 10, maxval = 50, group = grpZ)\n', ""),
    ("float atrTrendingV = ta.atr(7)\nfloat atrRangingV  = ta.atr(21)\n", "// v95: adaptive ATR, ADX and DI are the engine's (SX block above), so the V copies are gone.\n"),
    ("[_diPV, _diMV, adxValV] = ta.dmi(adxLenV, adxLenV)\n"
     "float regimeStrengthV = math.min(math.max((adxValV - (adxThresholdV - 5)) / 10.0, 0.0), 1.0)\n"
     "float _rawAdaptiveATRV = showAdaptiveATRV ? (atrRangingV * (1.0 - regimeStrengthV) + atrTrendingV * regimeStrengthV) : atr14\n"
     "float adaptiveATRV = math.max(nz(_rawAdaptiveATRV, ta.tr), close * 0.0001)\n", ""),
    ("float _dispEnterV = adaptiveATRV * obDispATR\nfloat _dispHoldV  = adaptiveATRV * (obDispATR * 0.6)\n",
     "float _dispEnterV = adaptiveATR * obDispATR\nfloat _dispHoldV  = adaptiveATR * (obDispATR * 0.6)\n"),
    ("var bool  bullBias = false\nvar bool  haveBias = false\n", ""),
    ("bool brokeUp   = not na(lastPH) and close > lastPH and close[1] <= lastPH\n"
     "bool brokeDown = not na(lastPL) and close < lastPL and close[1] >= lastPL\n",
     "// v95: structure breaks are the ENGINE'S (SX block): BOS on its two pivot scales, CHoCH / MSS on its HH / HL / LH / LL\n"
     "// sequence; the events are the first bar of each state, as the Master's alert reports them.\n"
     "bool sxChochUp = chochLabelBull and not chochLabelBull[1]\nbool sxChochDn = chochLabelBear and not chochLabelBear[1]\n"
     "bool sxMssUp = mssLabelBull and not mssLabelBull[1]\nbool sxMssDn = mssLabelBear and not mssLabelBear[1]\n"),
    ("    if brokeUp\n"
     "        bool isChoch = haveBias and not bullBias\n"
     '        array.push(structLb, label.new(bar_index, high, isChoch ? "~CHoCH▲" : "~BOS▲", xloc.bar_index, yloc.abovebar, color.new(cBull, 20), label.style_label_down, color.white, size.tiny))\n'
     "        array.push(structLn, line.new(bar_index - 1, lastPH, bar_index, lastPH, xloc.bar_index, extend.none, cBull, line.style_solid, 2))\n"
     "        bullBias := true\n"
     "        haveBias := true\n"
     "    if brokeDown\n"
     "        bool isChoch2 = haveBias and bullBias\n"
     '        array.push(structLb, label.new(bar_index, low, isChoch2 ? "~CHoCH▼" : "~BOS▼", xloc.bar_index, yloc.belowbar, color.new(cBear, 20), label.style_label_up, color.white, size.tiny))\n'
     "        array.push(structLn, line.new(bar_index - 1, lastPL, bar_index, lastPL, xloc.bar_index, extend.none, cBear, line.style_solid, 2))\n"
     "        bullBias := false\n"
     "        haveBias := true\n",
     "    if bosLabelBull or sxChochUp or sxMssUp\n"
     '        array.push(structLb, label.new(bar_index, high, sxMssUp ? "MSS▲" : sxChochUp ? "CHoCH▲" : "BOS▲", xloc.bar_index, yloc.abovebar, color.new(cBull, 20), label.style_label_down, color.white, size.tiny))\n'
     "        if bosLabelBull\n"
     "            float _bl = intBosLabelBull ? bosResistanceSnap : swingBosResSnap\n"
     "            array.push(structLn, line.new(bar_index - 1, _bl, bar_index, _bl, xloc.bar_index, extend.none, cBull, line.style_solid, 2))\n"
     "    if bosLabelBear or sxChochDn or sxMssDn\n"
     '        array.push(structLb, label.new(bar_index, low, sxMssDn ? "MSS▼" : sxChochDn ? "CHoCH▼" : "BOS▼", xloc.bar_index, yloc.belowbar, color.new(cBear, 20), label.style_label_up, color.white, size.tiny))\n'
     "        if bosLabelBear\n"
     "            float _bs = intBosLabelBear ? bosSupportSnap : swingBosSupSnap\n"
     "            array.push(structLn, line.new(bar_index - 1, _bs, bar_index, _bs, xloc.bar_index, extend.none, cBear, line.style_solid, 2))\n"),
    ("if showFVG and barstate.isconfirmed and bar_index > 3\n", "if fvgDetected and bar_index > 3   // v95: the engine's detector (SX block)\n"),
    ("    if not na(gLo) and gHi - gLo >= atr14 * fvgMinATR\n", "    if not na(gLo)\n"),
    ("if barstate.isconfirmed and (brokeUp or brokeDown)\n    int _nd = brokeDown ? -1 : 1\n",
     "if barstate.isconfirmed and (bosLabelBull or bosLabelBear)   // v95: the engine's BOS breaks\n    int _nd = bosLabelBear ? -1 : 1\n"),
    ("float volSma20 = ta.sma(volume, 20)\n", "@@SX@@"),
]
DISP_EDITS = [("adxValV", "adxVal"), ("_diPV", "diplus"), ("_diMV", "diminus")]       # the ADX / DI display (two rows)
STAMP_V = "// ║  BUILD STAMP — this file last CHANGED in v95   (engine structure, SX)"


def visuals(vtext, mtext):
    M = mtext.split("\n")
    sx = sx_lines(M)
    t = vtext
    for old, new in V_EDITS:
        assert t.count(old) == 1, f"not the v94 text: {old[:80]!r} ({t.count(old)})"
        t = t.replace(old, new)
    sa = t.index('showAdaptiveATRV = input.bool(false, "  Adaptive ATR Regime (match Master)"')
    t = t[:sa] + t[t.index("\n", sa) + 1:]
    for a, b in DISP_EDITS:
        t = re.sub(rf"\b{a}\b", b, t)
    # Visuals lines that ARE Master lines in the slice move into the block (removed where they were); the rest stay
    MOVES = {"safeDiv(a, b) => not na(a) and not na(b) and math.abs(b) > 1e-10 ? a / b : 0.0": "safeDiv(a, b) =>",
             'grpCore = "CORE"': 'grpCore = "CORE"', "float _rawGoldRet = safeDiv(close, nz(close[1], close)) - 1": None,
             "float _retClampW = math.min(math.max(nz(ta.stdev(_rawGoldRet, 100)[1], 0.0) * 6.0, 0.002), 0.05)": None,
             "goldRet = math.min(math.max(_rawGoldRet, -_retClampW), _retClampW)": None,
             "float bbBasis = ta.sma(close, 20)": None}
    for ln in MOVES:
        if ln in sx:
            assert t.count(ln + "\n") == 1, ln
            t = t.replace(ln + "\n", "", 1)
    if "float bbDev = ta.stdev(close, 20) * 2.0" in sx:
        t = t.replace("float bbDev   = 2.0 * ta.stdev(close, 20)\n", "", 1)
    block = ("// SX-BEGIN (v95) the Master's structure + FVG engine, COPIED: every line between SX-BEGIN and SX-END is a Master line,\n"
             "// in the Master's order (sx_check.py); the backward slice of bosLabel* / chochLabel* / mssLabel* /\n"
             "// fvgDetected. Edit the Master, then re-copy. One exception: the engine switch showFVG is Visuals' draw switch.\n"
             + "\n".join(sx) + "\n// SX-END\n")
    t = t.replace("@@SX@@", block)
    # v94 defect (order.py found it in v95; it exited 0 then, C-03): rkStopD read lkSLp before the link lines declared it.
    # The link lines move, unchanged, to just above the RISK stop line.
    la = t.index("// v94 LINK: the Master's two series (pick them once per chart).")
    lb = t.index("float trkSLd = ", la)
    link = t[la:lb]
    t = t[:la] + t[lb:]
    ra = t.index("// v94: with the link and a live DECISION, the default stop")
    t = t[:ra] + link + t[ra:]
    L = t.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP_V + " " * (len(L[i + 1]) - len(STAMP_V) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    p = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
    out = visuals(open(p, encoding="utf-8").read(), open(M_FILE, encoding="utf-8").read())   # computed before writing
    open(p, "w", encoding="utf-8").write(out)
    print("fixed Visuals (v95)")
