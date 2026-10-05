#!/usr/bin/env python3
"""Build artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine from the Treatment twin's engine.

Everything outside `// DIAG-BEGIN` / `// DIAG-END` fences is the Strategy engine verbatim
(apart from the declaration line and comments); audit/tools/diag_parity.py enforces it."""
SRC = "artefacts/XAUUSD_Quantum_5_0_Strategy.pine"
DST = "artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine"

L = open(SRC, encoding="utf-8").read().split("\n")
cut = next(i for i, l in enumerate(L) if l.startswith("bool _costModelValid"))
L = L[:cut]
while L and (L[-1].strip() == "" or L[-1].lstrip().startswith("//")):
    L.pop()


def at(prefix):
    hits = [i for i, l in enumerate(L) if l.startswith(prefix)]
    assert len(hits) == 1, (prefix, len(hits))
    return hits[0]


# banner + declaration + role
ref = L[3]
body = "// ║  BUILD STAMP — this file last CHANGED in v38   (F-A41 HTF data; probe)"
L[2] = body + " " * (len(ref) - len(body) - 1) + "║"
i = at('strategy("XAUUSD Quantum 5.0 — Treatment"')
L[i] = ('indicator("XAUUSD Quantum 5.0 — Diagnostics", overlay=true, max_lines_count=500, '
        'max_labels_count=500, max_boxes_count=500, max_bars_back=5000)')
i = at("// FILE ROLE: A/B TREATMENT ARM")
L[i] = ("// FILE ROLE: DIAGNOSTICS COMPANION — display only, trades nothing. The engine below is the "
        "Treatment twin's, verbatim (audit/tools/diag_parity.py); the diagnostic panel is appended.")

# gCalRel transport, declared before the engine function
i = at("var float[] gCalFitBear = ")
L[i + 1:i + 1] = [
    "// DIAG-BEGIN reliability transport",
    "// [N, predicted %, observed %] x 5 calibration buckets, slot 15 = base rate. Written from values",
    "// the engine already computes; read only by the reliability rows of the diagnostic panel.",
    "var float[] gCalRel = array.new_float(16, na)",
    "// DIAG-END",
]

# per-bucket writes, inside the engine, where c0t..c4t are in scope
i = at("        if calBins > 0")
w = ["        // DIAG-BEGIN reliability writes (raw observed frequency, the same quantity the Brier",
     "        // decomposition uses; N >= 30 before a bucket reports, as everywhere else)"]
for k in range(5):
    w += [f"        array.set(gCalRel, {3 * k}, c{k}t)",
          f"        if c{k}t >= 30",
          f"            array.set(gCalRel, {3 * k + 1}, c{k}s / c{k}t)",
          f"            array.set(gCalRel, {3 * k + 2}, c{k}b * 100.0 / c{k}t)"]
w += ["        // DIAG-END"]
L[i:i] = w
i = at("            float _baseRate = _totalCal > 0 ? _totalBull / _totalCal : 0.5")
L[i + 1:i + 1] = ["            // DIAG-BEGIN base rate",
                  "            array.set(gCalRel, 15, _baseRate * 100.0)",
                  "            // DIAG-END"]

PANEL = r'''
// DIAG-BEGIN panel
// ═══════════════════ DIAGNOSTICS PANEL (v17, engine restored v18) ═══════════════════
// The six features removed from the Master in v15/v16 to stay under its 100,256 compiled-
// token limit, restored here and WIRED to a visible readout. None of them feeds a gate:
// this script trades nothing and alerts nothing. Everything above this block is the
// Treatment twin's engine, verbatim, so every number here is the Master's number.
grpDiag = "DIAGNOSTICS"
diagPos = input.string("Top Right", "Panel position", options=["Top Right", "Bottom Right", "Bottom Left", "Top Left"], group=grpDiag)
dgShowCone = input.bool(true, "Forecast Cone", group=grpDiag)
dgForecastZ = input.float(2.0, "Forecast Band (Z multiple of ATR)", minval=1.0, maxval=3.0, step=0.1, group=grpDiag)
dgClean = input.bool(false, "Clean Institutional Appearance (hides cone)", group=grpDiag)
dgPro = input.bool(false, "Professional Execution Mode (hides cone)", group=grpDiag)
dgShadowOn = input.bool(true, "V1/V2 schema shadow audit", group=grpDiag, tooltip="Computes the pre-GC/OI (V1) regime definition alongside the live V2 one on the SAME bar and counts where they diverge. Feeds nothing.")
dgRelOn = input.bool(true, "Rolling reliability table", group=grpDiag, tooltip="The five calibration buckets: N, predicted, observed, |error|, plus base rate and Brier. Recalculates nothing. Predicted is NOT a validated probability until an OOS reliability run shows predicted matches observed.")
showWhatIf = input.bool(true, "What-if scenario scores", group=grpDiag)
showRollCI = input.bool(true, "Rolling intervals (ROLL, not a holdout)", group=grpDiag)
showDataCensus = input.bool(true, "Data-source census", group=grpDiag)

// ---- 1. FORECAST CONE (restored verbatim from v14) -----------------------------------
// Breach = a 1-bar move beyond the Z x ATR band from the prior bar's cone origin (R5.2-M5).
var bool[] dgBreach = array.from(false, false)
if dgShowCone
    float dgBandNow = math.max(adaptiveATR, atr) * dgForecastZ
    array.set(dgBreach, 0, not na(close[1]) and close > close[1] + dgBandNow)
    array.set(dgBreach, 1, not na(close[1]) and close < close[1] - dgBandNow)
else
    array.set(dgBreach, 0, false)
    array.set(dgBreach, 1, false)
string dgConeStatus = "Cone: —"
if dgShowCone and not dgClean and not dgPro
    string dgCsLabel = fBullScore >= fBearScore and fBullScore >= fRngScore ? "BULL" : fBearScore >= fBullScore and fBearScore >= fRngScore ? "BEAR" : "RNG"
    string dgConeConf = oOosNeff >= 10 ? " C:" + str.tostring(int(oOosWr)) + "%" : " C:LowN"
    dgConeStatus := not array.get(dgBreach, 0) and not array.get(dgBreach, 1) ? "Cone " + dgCsLabel + ": Inside (Z" + str.tostring(dgForecastZ, "#.#") + dgConeConf + ")" : array.get(dgBreach, 0) ? "Cone: Breached ↑" : "Cone: Breached ↓"

// ---- 2. V1/V2 SAME-BAR SHADOW (restored verbatim from v14) ----------------------------
// V1 = the regime composite WITHOUT the GC vote and the OI nudge, through the same clamp,
// rounding and 70/40 categorisation (thresholded on the RAW float, as F-021 requires).
int _mbvV1 = macroBullVotes - (gcConfirmsBull ? 1 : 0)
int _mbrV1 = macroBearVotes - (gcConfirmsBear ? 1 : 0)
bool _macroBullV1 = _mbvV1 >= 3
bool _macroBearV1 = _mbrV1 >= 3
int _macroRegimeV1 = (_macroBullV1 or _macroBearV1) ? 100 : (_mbvV1 >= 2 or _mbrV1 >= 2) ? 60 : 30
float regimeCompositeRawV1 = (regimeScore * 0.30) + (volRegime * 0.15) + (structureRegime * 0.20) + (_macroRegimeV1 * 0.20) + (sessionRegime * 0.15)
int regimeCompositeV1 = int(math.round(regimeCompositeRawV1))
int rCurrV1 = regimeCompositeRawV1 >= 70 ? 0 : regimeCompositeRawV1 >= 40 ? 1 : 2
var int shdBars = 0
var int shdDeltaComp = 0
var int shdRegimeChg = 0
var int shdX40 = 0
var int shdX70 = 0
var int shdMaxAbs = 0
if dgShadowOn and barstate.isconfirmed
    shdBars += 1
    int _d = regimeComposite - regimeCompositeV1
    if _d != 0
        shdDeltaComp += 1
        shdMaxAbs := math.max(shdMaxAbs, math.abs(_d))
    if rCurr != rCurrV1
        shdRegimeChg += 1
    if (regimeCompositeV1 < 40) != (regimeComposite < 40)
        shdX40 += 1
    if (regimeCompositeV1 < 70) != (regimeComposite < 70)
        shdX70 += 1
string shadowLine = not dgShadowOn ? "off" : "n" + str.tostring(shdBars) + " dC" + str.tostring(shdDeltaComp) + " reg" + str.tostring(shdRegimeChg) + " x40:" + str.tostring(shdX40) + " x70:" + str.tostring(shdX70) + " max" + str.tostring(shdMaxAbs)

// ---- 3. RELIABILITY (restored from v14; observed = raw frequency, as in the v16 Brier) --
_relRow(int _i) =>
    float _rn = array.get(gCalRel, _i * 3)
    float _pd = array.get(gCalRel, _i * 3 + 1)
    float _ob = array.get(gCalRel, _i * 3 + 2)
    na(_rn) or _rn < 30 or na(_pd) ? "B" + str.tostring(_i) + " N<30" : "B" + str.tostring(_i) + " n" + str.tostring(int(_rn)) + "  P" + str.tostring(_pd, "#") + "  O" + str.tostring(_ob, "#") + "  |E|" + str.tostring(math.abs(_pd - _ob), "#")
float _brBase = array.get(gCalRel, 15)
string relHead = "base " + (na(_brBase) ? "—" : str.tostring(_brBase, "#") + "%") + "  ROLLn " + str.tostring(oOosN) + "  CalErr " + (oCalGrade > 0 ? str.tostring((100.0 - oCalGrade) / 2.0, "#.#") : "—") + (not na(__cb) ? "  Brier " + str.tostring(__cb, "#.###") : "")

// ---- 4. WHAT-IF SCENARIOS (engine values, v21) -------------------------------------
// Heuristic SCORES 0-100, not probabilities, clamped [10, 90]. Published by the engine itself
// (wiPdhCont / wiPdlCont / wiVwapHold / wiVwapFail), so the panel shows the engine's numbers
// instead of recomputing them.
_wi(float _v) => na(_v) ? "—" : str.tostring(int(_v))

// ---- 5. ROLLING INTERVALS (F-037 / F-A14 formulas, shown ONLY here, labelled ROLL) ------
// 95% normal half-width at the overlap-corrected effective N = N / OUTCOME_N. The sample is a
// rolling, re-drawn analog population, NOT a fixed holdout: the interval describes sampling
// noise inside that population, not out-of-sample validity. Hence the panel's heading.
float diagWrCI = na
float _pWr = oWr / 100.0
float _pWrDir = bearBiasScore > bullBiasScore ? oBear / 100.0 : _pWr  // F-A28: the bear rate, not 1 - bull
if showStatsEngine and oMatch >= 30
    diagWrCI := 1.96 * math.sqrt(_pWrDir * (1.0 - _pWrDir) / math.max(oMatch / math.max(OUTCOME_N, 1), 1.0)) * 100.0
float diagOosCI = oOosNeff >= 10 ? 1.96 * math.sqrt(math.max(oOosWr / 100.0 * (1.0 - oOosWr / 100.0), 0.0025) / math.max(oOosN / OUTCOME_N, 1.0)) * 100.0 : na
string ciLine = "WR " + (na(diagWrCI) ? "—" : str.tostring(int(_pWrDir * 100.0)) + "% ±" + str.tostring(diagWrCI, "#")) + "   OOS " + (na(diagOosCI) ? "—" : str.tostring(int(oOosWr)) + "% ±" + str.tostring(diagOosCI, "#"))

// ---- 6. DATA-SOURCE CENSUS (hDataStatus WIRED) --------------------------------------
// The engine stores barDataStatus per observation in hDataStatus (restored v18). Scanned on
// the last bar only; slots 0 .. min(hN, HIST_MAX) - 1 are the written ones.
// bit0 = GC contributed a macro vote, bit1 = OI contributed a regime nudge.
int dsN = 0
int dsGC = 0
int dsOI = 0
if barstate.islast and showDataCensus
    for _s = 0 to math.max(math.min(hN, HIST_MAX) - 1, 0)
        // v24: was `_v`, which shadowed the engine's global `_v` (return variance) -- compiler
        // warning at the operator's first Diagnostics save. Behaviour unchanged; name only.
        int _dsv = array.get(hDataStatus, _s)
        dsN += 1
        dsGC += _dsv % 2
        dsOI += int(math.floor(_dsv / 2.0)) % 2
string censusLine = hN > 0 ? "GC " + str.tostring(dsGC * 100.0 / math.max(dsN, 1), "#") + "%  OI " + str.tostring(dsOI * 100.0 / math.max(dsN, 1), "#") + "%  of " + str.tostring(dsN) + " stored obs  (now D" + str.tostring(barDataStatus) + ")" : "no stored observations yet"

// ---- 7. GATE FUNNEL (v20) -- why a backtest does or does not trade ---------------------
// Counts confirmed bars through the Treatment entry chain, exactly as the strategy arm gates
// them. Vetoes are counted INDEPENDENTLY among signal bars, so they can overlap; PASS is a bar
// that clears everything (= an entry the strategy would take, position permitting).
var int fnBars = 0
var int fnTrend = 0
var int fnHtf = 0
var int fnPre = 0
var int fnSig = 0
var int fnTQ = 0
var int fnEV = 0
var int fnCal = 0
var int fnRisk = 0
var int fnPass = 0
if barstate.isconfirmed
    fnBars += 1
    bool _fT = bullTrend or bearTrend
    bool _fH = (bullTrend and not htfBearScoreGate) or (bearTrend and not htfBullScoreGate)
    fnTrend += _fT ? 1 : 0
    fnHtf += _fH ? 1 : 0
    fnPre += buyPreFilters or sellPreFilters ? 1 : 0
    if shouldBuy or shouldSell
        fnSig += 1
        fnTQ += effTqMinCot > 0 and tradeQuality < effTqMinCot ? 1 : 0
        fnEV += not na(planExpectancy) and planExpectancy < 0.0 ? 1 : 0
        fnCal += _calVeto ? 1 : 0
        fnRisk += useRiskLimits and riskLock ? 1 : 0
        fnPass += not tqVeto ? 1 : 0
string funnel1 = "bars " + str.tostring(fnBars) + " > trend " + str.tostring(fnTrend) + " > +HTF " + str.tostring(fnHtf) + " > +sess/news/DD/recent " + str.tostring(fnPre) + " > +trigger = SIGNALS " + str.tostring(fnSig)
string funnel2 = "TQ<floor " + str.tostring(fnTQ) + "  EV<0 " + str.tostring(fnEV) + "  P<min " + str.tostring(fnCal) + "  risk " + str.tostring(fnRisk) + "  →  PASS " + str.tostring(fnPass)

// ---- 8. LAYOUT INPUTS (engine's dashboard inputs, wired here in v21) --------------------
// textSize -> text size; density -> how many rows (Compact: core, Standard: + cross-check,
// Spacious: the auction row carries the full cross-check prefix as well); mobileOverride / dashMode Mobile* -> compact, mirror hidden;
// debugMode -> raw gate booleans row.
dgTs = textSize == "Large" ? size.normal : textSize == "Medium" ? size.small : size.tiny
bool dgCompact = mobileOverride or dashMode == "MobilePort" or dashMode == "MobileLand" or density == "Compact"
bool dgWide = density == "Spacious" and not dgCompact

// ---- 9. ENGINE CROSS-CHECK (the Master's display strings, from the same engine) ----------
string xDecision = decisionLog
string xSignal = calProbStr + "  conf " + confLabel + "  cal " + oCalDetail
string xMacro = gcState + "  " + oiState + cotState + curveState + migState + "  DXY-RSI " + (na(_rawDXYRSI) ? "—" : str.tostring(_rawDXYRSI, "#")) + "  EURcorr " + str.tostring(avgCorrEUR, "#.##") + "  TIPS " + tipsMag
string xStruct = "PDH1st " + (na(oPdh1stPct) ? "—" : str.tostring(oPdh1stPct) + "/PDL " + str.tostring(oPdl1stPct) + "%") + "  BOS cont " + str.tostring(int(oBosCont)) + "/fail " + str.tostring(int(oBosFail)) + "%  MAE " + (na(oMaxAdverseATR) ? "—" : str.tostring(oMaxAdverseATR, "#.#")) + "  2nd-target " + str.tostring(liqDestScoreSecondary) + "  hitN " + (na(array.get(gHitN, 0)) ? "—" : str.tostring(array.get(gHitN, 0), "#"))
string xFlow = "CVD " + (cvdBull ? "bull" : "bear") + "  vdK " + str.tostring(vdK, "#.#") + "  VA " + vaPos + " " + str.tostring(vaRatio, "#.##") + "  WR" + (wrCIStr == "" ? "" : " " + wrCIStr) + " (ROLL)"
string xAuction = "»" + aucBias + " " + aucState + " " + str.tostring(aucProb) + "%  " + aucCycle + "  " + discStr + "  accept " + str.tostring(acceptScore) + acceptGrade + "  " + valueMigStr + (openType != "" ? "  open " + openType : "") + (lastSweepQ > 0 ? "  sweep " + lastSweepGrade + " " + str.tostring(lastSweepQ) : "")
string xDebug = "trend " + (bullTrend ? "B" : bearTrend ? "S" : "-") + "  htfGate " + (htfBullScoreGate ? "B" : htfBearScoreGate ? "S" : "-") + "  sess " + str.tostring(int(sessionQuality)) + "  trig " + (bullStructActive or displacementUp ? "B" : "") + (bearStructActive or displacementDown ? "S" : "") + "  TQ " + str.tostring(tradeQuality) + "/" + str.tostring(effTqMinCot) + "  EV " + (na(planExpectancy) ? "—" : str.tostring(planExpectancy, "#.##")) + "  P " + str.tostring(math.round(_calPLong * 100.0)) + "/" + str.tostring(math.round(_calPShort * 100.0))

// ---- 10. DASHBOARD MIRROR (engine's dashboard builder + table helpers, wired v21) --------
// f_dashData1 is the Master's dashboard data builder (decision labels, bias, grade, Kelly).
// Running it here and drawing its output with the engine's own tc / tcb / tcp helpers shows
// the dashboard's numbers computed a second, independent time from the same engine.
f_dashData1()
if barstate.isfirst
    tblA := table.new(position.bottom_left, 9, 2, bgcolor=color.new(#0B0F14, 5), border_width=1, border_color=color.new(#2A3340, 0))
    tblPlan := table.new(position.bottom_right, 1, 7, bgcolor=color.new(#0B0F14, 5), border_width=1, border_color=color.new(#2A3340, 0))
if barstate.islast and not dgCompact
    color _hc = color.new(#8FA3B8, 0)
    tc(0, 0, "DECISION", _hc, dgTs, 0)
    tcb(0, 1, array.get(gDashS, 5), color.white, array.get(gDashC, 2), dgTs, 0)
    tc(1, 0, "LIVE", _hc, dgTs, 0)
    tc(1, 1, array.get(gDashS, 6), color.white, dgTs, 0)
    tc(2, 0, "BIAS", _hc, dgTs, 0)
    tcb(2, 1, array.get(gDashS, 1), color.white, color.new(array.get(gDashC, 0), 80), dgTs, 0)
    tc(3, 0, "B/S/R %", _hc, dgTs, 0)
    tc(3, 1, str.tostring(array.get(gDashF, 1), "#") + "/" + str.tostring(array.get(gDashF, 0), "#") + "/" + str.tostring(array.get(gDashF, 5), "#"), color.white, dgTs, 0)
    tc(4, 0, "MTF", _hc, dgTs, 0)
    tc(4, 1, array.get(gDashS, 0) + " " + array.get(gDashS, 8) + array.get(gDashS, 4), color.white, dgTs, 0)
    tc(5, 0, "GRADE", _hc, dgTs, 0)
    tc(5, 1, array.get(gDashS, 7), color.white, dgTs, 0)
    tc(6, 0, "KELLY", _hc, dgTs, 0)
    tc(6, 1, str.tostring(array.get(gDashF, 4), "#.##") + "%", color.white, dgTs, 0)
    tc(7, 0, "CHG", _hc, dgTs, 0)
    tc(7, 1, array.get(gDashS, 2), array.get(gDashC, 1), dgTs, 0)
    tc(8, 0, array.get(gDashS, 9) + " " + array.get(gDashS, 10), _hc, dgTs, 0)
    tc(8, 1, array.get(gDashS, 3), color.white, dgTs, 0)
    color _pb = color.new(#132030, 0)
    tcp(0, 0, "PLAN (MT5) " + tpDirStr, _pb, dgTs, 0)
    tcp(0, 1, "Entry " + tpEntryStr, _pb, dgTs, 0)
    tcp(0, 2, "SL " + tpSLStr, _pb, dgTs, 0)
    tcp(0, 3, "TP1 " + tp1Str + "  TP2 " + tp2Str, _pb, dgTs, 0)
    tcp(0, 4, "TP3 " + tp3Str, _pb, dgTs, 0)
    tcp(0, 5, "RR " + tpRRStr, _pb, dgTs, 0)
    tcp(0, 6, "EV " + (na(planExpectancy) ? "—" : str.tostring(planExpectancy, "#.##") + "R") + "  P " + str.tostring(math.round((tpIsLong ? _calPLong : _calPShort) * 100.0)) + "%", _pb, dgTs, 0)

// ---- 11. ENGINE ZONES OVERLAY (engine's OB / FVG / S-R drawing handles, wired v21) ------
// Draws the ENGINE's own zones, so they can be compared with what Visuals draws. OFF by
// default because Visuals already draws zones; turn it on to check the two agree.
// S/R here = the engine's scored liquidity pools (PDH/PDL/PWH/PWL/PMH/PML/EQH/EQL), split
// into resistance (above price) and support (below), strength = the engine's pool score.
dgZones = input.bool(false, "Engine zones overlay (compare with Visuals)", group=grpDiag)
_dgLine(line _ln, float _y, color _c) =>
    line.delete(_ln)
    na(_y) ? line(na) : line.new(bar_index - 30, _y, bar_index + 5, _y, color=_c, width=1, style=line.style_dotted)
_dgLab(label _lb, float _y, string _t, color _c) =>
    label.delete(_lb)
    na(_y) ? label(na) : label.new(bar_index + 6, _y, _t, color=color.new(_c, 100), textcolor=_c, style=label.style_label_left, size=size.tiny)
if dgZones and barstate.islast
    bullOBLowLine := _dgLine(bullOBLowLine, obBullActive ? obBullLow : na, color.teal)
    bullOBHighLine := _dgLine(bullOBHighLine, obBullActive ? obBullHigh : na, color.teal)
    bearOBLowLine := _dgLine(bearOBLowLine, obBearActive ? obBearLow : na, color.maroon)
    bearOBHighLine := _dgLine(bearOBHighLine, obBearActive ? obBearHigh : na, color.maroon)
    bullOBLabel := _dgLab(bullOBLabel, obBullActive ? obBullHigh : na, "engine OB+", color.teal)
    bearOBLabel := _dgLab(bearOBLabel, obBearActive ? obBearLow : na, "engine OB-", color.maroon)
    bool _fvgOn = fvgActive and fvgShowQuality
    fvgUpperLineObj := _dgLine(fvgUpperLineObj, _fvgOn ? fvgHighUpper : na, color.orange)
    fvgLowerLineObj := _dgLine(fvgLowerLineObj, _fvgOn ? fvgLowLower : na, color.orange)
    fvgLabel := _dgLab(fvgLabel, _fvgOn ? fvgHighUpper : na, "engine FVG" + (fvgWasBullish ? "+" : "-") + (na(fvgVolPctAtDetect) ? "" : " vol" + str.tostring(fvgVolPctAtDetect, "#") + "%"), color.orange)
    array.clear(srResLevels)
    array.clear(srResStrengths)
    array.clear(srSupLevels)
    array.clear(srSupStrengths)
    float[] _pl = array.from(poolPdH, poolPdL, poolPwH, poolPwL, poolPmH, poolPmL, poolEqH, poolEqL)
    float[] _ps = array.from(liqScorePDH, liqScorePDL, liqScorePWH, liqScorePWL, liqScorePMH, liqScorePML, liqScoreEQH, liqScoreEQL)
    for _i = 0 to 7
        float _lv = array.get(_pl, _i)
        if not na(_lv) and _lv > close
            array.push(srResLevels, _lv)
            array.push(srResStrengths, nz(array.get(_ps, _i)))
        else if not na(_lv)
            array.push(srSupLevels, _lv)
            array.push(srSupStrengths, nz(array.get(_ps, _i)))
    while array.size(srLines) > 0
        line.delete(array.pop(srLines))
    if array.size(srResLevels) > 0
        for _i = 0 to array.size(srResLevels) - 1
            array.push(srLines, line.new(bar_index - 20, array.get(srResLevels, _i), bar_index + 3, array.get(srResLevels, _i), color=color.new(color.red, 100 - math.min(math.max(int(array.get(srResStrengths, _i)), 20), 90)), width=2))
    if array.size(srSupLevels) > 0
        for _i = 0 to array.size(srSupLevels) - 1
            array.push(srLines, line.new(bar_index - 20, array.get(srSupLevels, _i), bar_index + 3, array.get(srSupLevels, _i), color=color.new(color.green, 100 - math.min(math.max(int(array.get(srSupStrengths, _i)), 20), 90)), width=2))
// order-block history: every newly formed engine OB is kept as a pair of lines (last 5)
if dgZones and obBullActive and not obBullActive[1]
    array.push(bullOBHistLowA, line.new(bar_index, obBullLow, bar_index + 20, obBullLow, color=color.new(color.teal, 60)))
    array.push(bullOBHistHighA, line.new(bar_index, obBullHigh, bar_index + 20, obBullHigh, color=color.new(color.teal, 60)))
    if array.size(bullOBHistLowA) > 5
        line.delete(array.shift(bullOBHistLowA))
        line.delete(array.shift(bullOBHistHighA))
if dgZones and obBearActive and not obBearActive[1]
    array.push(bearOBHistLowA, line.new(bar_index, obBearLow, bar_index + 20, obBearLow, color=color.new(color.maroon, 60)))
    array.push(bearOBHistHighA, line.new(bar_index, obBearHigh, bar_index + 20, obBearHigh, color=color.new(color.maroon, 60)))
    if array.size(bearOBHistLowA) > 5
        line.delete(array.shift(bearOBHistLowA))
        line.delete(array.shift(bearOBHistHighA))

// ---- 12. VOLUME SOURCE CHECK (free TradingView plan, v22) ------------------------------
// OANDA XAUUSD is spot OTC: its volume is TICK volume (price changes), the only real-time
// volume a free plan has. COMEX GC1! carries real exchange volume, delayed ~10 min on a free
// plan. The engine already fetches GC1!'s PREVIOUS-bar volume (_gcVol). Pairing it with the
// chart's previous-bar tick volume compares two COMPLETE bars, so the delay does not bias the
// comparison on charts of 30M and up (below that the previous GC bar may still be incomplete).
//   corr    -- Pearson correlation of the two over the last 100 closed bars: how far the
//              tick-volume filters (displacement, climax, CVD) can be trusted as real volume.
//   confirm -- the PREVIOUS bar's displacement, checked against real COMEX volume expansion
//              (engine's gcVolExp). Available one bar late, by construction.
// Display only: nothing here feeds a gate. The GOOD / PARTIAL / WEAK words are reading aids
// for the correlation, not thresholds of the strategy.
// v24 FIX (compiler warning at the first save): ta.correlation was called INSIDE a ternary,
// so on bars where gcValid was false it did not run and its 100-bar window skipped them --
// the correlation could then span more than 100 bars. It now runs on every bar and the
// ternary only chooses what to show.
float dgVolCorrAll = ta.correlation(volume[1], _gcVol, 100)
float dgVolCorr = gcValid ? dgVolCorrAll : na
bool dgPrevDisp = displacementUp[1] or displacementDown[1]
string volLine = not gcValid ? "COMEX feed not valid — tick volume unverified (" + gcState + ")" : "tick vs COMEX corr(100) " + (na(dgVolCorr) ? "—" : str.tostring(dgVolCorr, "#.##") + (dgVolCorr >= 0.7 ? " GOOD" : dgVolCorr >= 0.4 ? " PARTIAL" : " WEAK")) + "  |  prev-bar displacement " + (dgPrevDisp ? (gcVolExp ? "CONFIRMED by COMEX volume" : "NOT confirmed by COMEX volume") : "none") + (timeframe.in_seconds() < 1800 ? "  |  <30M: COMEX bar may be incomplete" : "")

// ---- 13. MISSED-MOVE AUDIT (v27) -- why the decision said WAIT while price moved -------
// Operator report: DECISION "mostly remained WAIT although the market moved 30 to 50 dollars".
// A MOVE starts at bar s when, within the next dgMoveBars bars, the high rises (or the low
// falls) at least dgMoveUSD from close[s]. Consecutive start bars form one EPISODE. For
// each episode this records the FURTHEST the Treatment entry chain got in the move's
// direction on any start bar, in gate order:
//   trend > HTF > sess/news/DD > trigger (structure or displacement) > TQ floor > EV<0 >
//   P<min > risk lock > ENTRY
// "ENTRY" means a trade in the move's direction would have been signalled while the move was
// still ahead -- NOT that it won (the stop can still be hit first). Evaluated only on
// confirmed bars, from values already computed; it changes no gate. It measures; it does
// not propose thresholds (AUDIT_PROMPT §9).
dgMoveUSD = input.float(30.0, "Missed-move audit: move size (price units)", minval=1.0, group=grpDiag)
dgMoveBars = input.int(12, "Missed-move audit: within N bars", minval=2, maxval=100, group=grpDiag)
_dgStage(bool _tr, bool _htfBlk, bool _pre, bool _sig) => not _tr ? 0 : _htfBlk ? 1 : not _pre ? 2 : not _sig ? 3 : effTqMinCot > 0 and tradeQuality < effTqMinCot ? 4 : not na(planExpectancy) and planExpectancy < 0.0 ? 5 : _calVeto ? 6 : useRiskLimits and riskLock ? 7 : 8
int dgStL = _dgStage(bullTrend, htfBearScoreGate, buyPreFilters, shouldBuy)
int dgStS = _dgStage(bearTrend, htfBullScoreGate, sellPreFilters, shouldSell)
float dgFwdHi = ta.highest(high, dgMoveBars)
float dgFwdLo = ta.lowest(low, dgMoveBars)
bool dgMvU = bar_index > dgMoveBars and dgFwdHi - close[dgMoveBars] >= dgMoveUSD
bool dgMvD = bar_index > dgMoveBars and close[dgMoveBars] - dgFwdLo >= dgMoveUSD
var int[] dgMiss = array.new_int(9, 0)
var int dgEpU = -1
var int dgEpD = -1
var int dgNU = 0
var int dgND = 0
if barstate.isconfirmed
    if dgMvU
        dgEpU := math.max(dgEpU, dgStL[dgMoveBars])
    else if dgEpU >= 0
        array.set(dgMiss, dgEpU, array.get(dgMiss, dgEpU) + 1)
        dgNU += 1
        dgEpU := -1
    if dgMvD
        dgEpD := math.max(dgEpD, dgStS[dgMoveBars])
    else if dgEpD >= 0
        array.set(dgMiss, dgEpD, array.get(dgMiss, dgEpD) + 1)
        dgND += 1
        dgEpD := -1
string missLine = "moves >=" + str.tostring(dgMoveUSD, "#") + " in " + str.tostring(dgMoveBars) + " bars: up " + str.tostring(dgNU) + " / down " + str.tostring(dgND) + "  ENTRY " + str.tostring(array.get(dgMiss, 8)) + "  |  stopped at: trend " + str.tostring(array.get(dgMiss, 0)) + "  HTF " + str.tostring(array.get(dgMiss, 1)) + "  sess/news/DD " + str.tostring(array.get(dgMiss, 2)) + "  trigger " + str.tostring(array.get(dgMiss, 3)) + "  TQ " + str.tostring(array.get(dgMiss, 4)) + "  EV " + str.tostring(array.get(dgMiss, 5)) + "  P " + str.tostring(array.get(dgMiss, 6)) + "  risk " + str.tostring(array.get(dgMiss, 7))

// ---- 14. MATH PROBES (v32) -- questions only the chart can answer ------------------------
// (a) HTF semantics. Up to v37 the engine requested daily data as request.security(.., "D",
//     close[1], lookahead_off): TWO days back on historical bars, ONE day back live. The
//     operator's chart measured it (2d back on 6,027 of 6,091 bars) -> F-A41. Since v38 the
//     engine uses close[1] + lookahead_on (the last COMPLETED day, live and history alike), and
//     this probe makes the same call: expect "=1d back" on almost every bar. Counted on
//     confirmed bars against the chart's own previous-day closes.
// (b) Cornish-Fisher domain (F-A39). q(w) is monotone only if a2 = K/8 - S^2/6 > 0 and
//     (S/3)^2 - 4 a2 (1 - K/8 + 5 S^2/36) < 0; outside it the Newton inverse has no solution.
//     Counted on bars where the engine applies the transform; plus the largest |z| it produced.
// (c) Calibration fit in use (F-A38): slope and intercept of the bull and bear fits, and
//     read against the clamps (slope 0.02 / -0.02 / 0.25, intercept +-1).
// Display only; nothing here feeds a gate.
float dgHtfD = request.security(syminfo.tickerid, "D", close[1], barmerge.gaps_off, barmerge.lookahead_on)
bool dgNewDay = ta.change(time("D")) != 0
var float dgD1 = na
var float dgD2 = na
if dgNewDay
    dgD2 := dgD1
    dgD1 := close[1]
var int dgHtfEq1 = 0
var int dgHtfEq2 = 0
var int dgHtfOth = 0
var int dgCfApplied = 0
var int dgCfNonMono = 0
var float dgCfMaxZ = 0.0
if barstate.isconfirmed and not na(dgHtfD) and not na(dgD2)
    float _tol = syminfo.mintick * 2
    if math.abs(dgHtfD - dgD1) <= _tol
        dgHtfEq1 += 1
    else if math.abs(dgHtfD - dgD2) <= _tol
        dgHtfEq2 += 1
    else
        dgHtfOth += 1
if barstate.isconfirmed and _cfValid and math.abs(retSkew) < 1.5 and math.abs(retKurt) < 7.0 and not na(retZScore)
    float _K = math.min(math.max(retKurt, -1.0), 3.0)
    float _a2 = _K / 8.0 - retSkewC * retSkewC / 6.0
    float _a0 = 1.0 - _K / 8.0 + 5.0 * retSkewC * retSkewC / 36.0
    dgCfApplied += 1
    dgCfNonMono += _a2 > 0 and (retSkewC / 3.0) * (retSkewC / 3.0) - 4.0 * _a2 * _a0 < 0 ? 0 : 1
    dgCfMaxZ := math.max(dgCfMaxZ, math.abs(retZScore))
string probeLine = "D close[1]: =1d back " + str.tostring(dgHtfEq1) + " / =2d back " + str.tostring(dgHtfEq2) + " / other " + str.tostring(dgHtfOth) + "  |  CF non-monotone " + str.tostring(dgCfNonMono) + "/" + str.tostring(dgCfApplied) + " max|z| " + str.tostring(dgCfMaxZ, "#.#") + "  |  fit bull k " + str.tostring(array.get(gCalFit, 0), "#.####") + " a " + str.tostring(array.get(gCalFit, 1), "#.##") + "  bear k " + str.tostring(array.get(gCalFitBear, 0), "#.####") + " a " + str.tostring(array.get(gCalFitBear, 1), "#.##")

// ---- 15. ANALOG EVIDENCE (moved from the Master's cross-check line in v37) -------------
// The Master's F-007 / F-008 / F-011 readouts, verbatim apart from the dg prefix: analog count
// and win rate (A / WR / ROLL n), PDH-first / MAE / BOS continuation, the calibration example,
// grade and Brier, IS vs ROLL win rate (!FIT = IS more than 15 points above ROLL), and the
// adaptive feature weights Str/Htf/Liq/Mr/Cor. Moved to make room for the Master's H2 SETUP row
// (token ceiling); same engine, so the same numbers. Display only.
string dgEvid = showStatsEngine ? "A" + str.tostring(oMatch) + (oMatch < 30 ? "!LOW" : "") + " WR" + str.tostring(int(oWr)) + "% ROLL" + str.tostring(oOosN) : "stats engine off"
string dgAnl = showStatsEngine and oMatch >= 30 ? (not na(oPdh1stPct) ? "  PDH1st" + str.tostring(oPdh1stPct) + "/PDL" + str.tostring(oPdl1stPct) + "%" : "") + (not na(oMaxAdverseATR) ? " MAE" + str.tostring(oMaxAdverseATR, "#.#") + "R" : "") + " BOScont" + str.tostring(int(oBosCont)) + "/fail" + str.tostring(int(oBosFail)) + "%" : ""
string dgCal = (showStatsEngine and oCalDetail != "" ? "  Cal " + oCalDetail : "") + (showStatsEngine and __cg != "N/A" ? "  Cal" + __cg + (not na(__cb) ? "/B" + str.tostring(__cb, "#.##") : "") : "")
string dgIsOos = showStatsEngine and __in >= 10 and oOosN >= 10 ? "  IS" + str.tostring(int(__iw)) + "%/ROLL" + str.tostring(int(oOosWr)) + "%" + (__iw - oOosWr > 15 ? "!FIT" : "") : ""
string dgFeatW = showStatsEngine and oMatch >= 30 ? "  W" + str.tostring(int(__fs)) + "/" + str.tostring(int(__fh)) + "/" + str.tostring(int(__fl)) + "/" + str.tostring(int(__fm)) + "/" + str.tostring(int(__fc)) : ""
string evidLine = dgEvid + dgAnl + dgCal + dgIsOos + dgFeatW

// ---- PANEL -----------------------------------------------------------------------------
var table tDiag = table.new(diagPos == "Top Right" ? position.top_right : diagPos == "Bottom Right" ? position.bottom_right : diagPos == "Bottom Left" ? position.bottom_left : position.top_left, 2, 26, bgcolor=color.new(#0B0F14, 5), border_width=1, border_color=color.new(#2A3340, 0))
_dRow(int _r, string _k, string _v, color _c) =>
    table.cell(tDiag, 0, _r, _k, text_color=color.new(#8FA3B8, 0), text_size=dgTs, text_halign=text.align_left)
    table.cell(tDiag, 1, _r, _v, text_color=_c, text_size=dgTs, text_halign=text.align_left)
if barstate.islast
    color _cT = color.new(#E6EDF3, 0)
    table.cell(tDiag, 0, 0, "QUANTUM DIAGNOSTICS  v38 " + QVERSION + "  B" + str.tostring(SCHEMA_BUILD), text_color=color.white, bgcolor=color.new(#1F3A5F, 0), text_size=size.tiny)
    table.cell(tDiag, 1, 0, "ROLL, NOT A HOLDOUT — VALIDITY: NOT ESTABLISHED", text_color=color.new(#FFB020, 0), bgcolor=color.new(#1F3A5F, 0), text_size=size.tiny)
    _dRow(1, "Forecast cone", dgConeStatus, _cT)
    _dRow(2, "V1/V2 shadow", shadowLine, _cT)
    _dRow(3, "Reliability", dgRelOn and showStatsEngine ? relHead : "off", _cT)
    for _b = 0 to 4
        _dRow(4 + _b, "  bucket " + str.tostring(_b), dgRelOn and showStatsEngine ? _relRow(_b) : "", _cT)
    _dRow(9, "Rolling 95% CI", showRollCI ? ciLine : "off", _cT)
    _dRow(10, "What-if (score)", showWhatIf ? "PDH cont " + _wi(wiPdhCont) + "  PDL cont " + _wi(wiPdlCont) + "  VWAP hold " + _wi(wiVwapHold) + " / fail " + _wi(wiVwapFail) : "off", _cT)
    _dRow(11, "Data sources", showDataCensus ? censusLine : "off", _cT)
    _dRow(12, "Gate funnel", funnel1, _cT)
    _dRow(13, "Vetoes (of signals)", funnel2, _cT)
    if not dgCompact
        _dRow(15, "Decision log", xDecision, _cT)
        _dRow(16, "Signal / conf / cal", xSignal, _cT)
        _dRow(17, "Macro feeds", xMacro, _cT)
        _dRow(18, "Structure stats", xStruct, _cT)
        _dRow(19, "Flow / VA", xFlow, _cT)
    // v24: the auction layer moved here from the Master (token ceiling, F-A32), so this row is
    // its only display and is no longer Spacious-only. Standard shows the auction read alone;
    // Spacious shows the engine's full auctionStr (cross-check prefix + auction read).
    if not dgCompact
        _dRow(20, "Auction", dgWide ? auctionStr : xAuction, _cT)
    if debugMode
        _dRow(21, "Gate booleans", xDebug, _cT)
    _dRow(22, "Volume (free plan)", volLine, _cT)
    _dRow(23, "Missed moves", missLine, _cT)
    _dRow(24, "Math probes", probeLine, _cT)
    _dRow(25, "Analog evidence", evidLine, _cT)
    _dRow(14, "Engine", "Treatment-twin engine, verbatim · " + mktRegime + " · N " + str.tostring(oMatch), _cT)
// Pine rejects an indicator with no output function call ("Script must have at least one
// output function call"); tables do not count. Same fix as the EdgeCases harness.
plot(na, "diagnostics", display = display.none)
// DIAG-END
'''
L += PANEL.rstrip("\n").split("\n")
open(DST, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("wrote", DST, len(L), "lines")
