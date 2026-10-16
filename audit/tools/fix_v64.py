"""v64 (F-A64): macro correlations pair returns over the same completed bar. Applied identically to the Master and the
three arms; Diagnostics and Brief are rebuilt from the Treatment."""
import sys
FILES = ["artefacts/XAUUSD_Quantum_5_0_" + f + ".pine" for f in ("Master", "Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER")]
VAL = ["dxyValid", "yieldValid", "silverValid", "spxValid", "eurusdValid", "tipsValid"]
OLD_STAB = "float _numStab = 0.0\n" + "".join(f"_numStab := {v} ? _numStab + 1.0 : _numStab\n" for v in VAL) + \
    "avgStability = _numStab > 0 ? (stabDXY + stabYld + stabSlv + stabSPX + stabEUR + stabTIPS) / _numStab : 0.0\n"
VALID_BLK = "float _numValid = 0.0\n" + "".join(f"_numValid := {v} ? _numValid + 1.0 : _numValid\n" for v in VAL)
NEW_STAB = ("// v64: one count of the valid macro feeds (it was computed twice, as _numStab here and _numValid below, and a\n"
            "// third time inline in macroStrengthConf); the same six flags, so every value is unchanged (refactor_check.py).\n"
            + VALID_BLK + "avgStability = _numValid > 0 ? (stabDXY + stabYld + stabSlv + stabSPX + stabEUR + stabTIPS) / _numValid : 0.0\n")
OLD_CONF = "macroStrengthConf = int(math.round((((dxyValid ? 1 : 0) + (yieldValid ? 1 : 0) + (silverValid ? 1 : 0) + (spxValid ? 1 : 0) + (eurusdValid ? 1 : 0) + (tipsValid ? 1 : 0)) / 6.0) * 30.0"
NEW_CONF = "macroStrengthConf = int(math.round((_numValid / 6.0) * 30.0"
TIPSRET = "tipsRet = tipsValid and not na(tipsClose[1]) ? safeDiv(tipsClose, tipsClose[1]) - 1 : na\n"
ALIGN = TIPSRET + """// v64 (F-A64): every correlation now pairs gold with the macro asset over the SAME completed bar. Each macro return is
// built from request close[1] (the bar before), while goldRet is this bar's return, so the engine measured gold now
// against the asset one bar earlier: a lag-1 cross-correlation, near zero for liquid markets (a true +0.80 read as
// -0.02 in a model; every macro arrow showed ~ on the operator's chart). Fix, without using any unfinished bar:
//  * chart-timeframe assets (silver, EURUSD, SPX): gold's previous-bar return, goldRetL = goldRet[1];
//  * macroTF assets (DXY, US10Y, TIPS): gold read exactly as they are (macroTF, close[1], lookahead_on), so both
//    returns change on the same bars; windows are counted in macroTF bars (x _kM), so a 1H series on a 15M chart
//    keeps the sample size its significance threshold assumes. A window that would exceed the history limit
//    (e.g. 120 hours on a 1m chart) reads as no data, never as a shorter window judged by the longer one's threshold.
float goldRetL = goldRet[1]
int _kM = math.max(1, int(timeframe.in_seconds(macroTF) / chartTFSeconds))
float _gM = request.security(syminfo.tickerid, macroTF, close[1], barmerge.gaps_off, barmerge.lookahead_on)
float goldRetM = not na(_gM[1]) ? safeDiv(_gM, _gM[1]) - 1 : na
bool _fS = corrShortLen * _kM <= 4500
bool _fM = corrMedLen * _kM <= 4500
bool _fL = corrLongLen * _kM <= 4500
"""
WIN = {"30": ("corrShortLen", "_fS"), "60": ("corrMedLen", "_fM"), "120": ("corrLongLen", "_fL")}
ASSETS = {"DXY": ("dxyRet", "dxyValid", True), "Yld": ("yieldRet", "yieldValid", True), "TIPS": ("tipsRet", "tipsValid", True),
          "Slv": ("silverRet", "silverValid", False), "SPX": ("spxRet", "spxValid", False), "EUR": ("eurRet", "eurusdValid", False)}


def rep(s, old, new, p):
    if s.count(old) != 1:
        sys.exit(f"{p}: anchor found {s.count(old)} times: {old[:80]!r}")
    return s.replace(old, new)


for p in FILES:
    s = open(p, encoding="utf-8").read()
    s = rep(s, OLD_STAB, NEW_STAB, p)
    if s.count(VALID_BLK) != 2:
        sys.exit(f"{p}: expected the moved and the original _numValid block")
    i = s.rindex(VALID_BLK)                     # the original, below; the moved copy sits above avgStability
    assert i > s.index("avgStability = _numValid")
    s = s[:i] + s[i + len(VALID_BLK):]
    s = rep(s, OLD_CONF, NEW_CONF, p)
    s = rep(s, TIPSRET, ALIGN, p)
    for a, (ret, valid, mtf) in ASSETS.items():
        for w, (ln, fit) in WIN.items():
            s = rep(s, f"_ccGold{a}_{w} = ta.correlation(goldRet, {ret}, {ln})\n",
                    f"_ccGold{a}_{w} = ta.correlation(goldRetM, {ret}, math.min({ln} * _kM, 4500))\n" if mtf
                    else f"_ccGold{a}_{w} = ta.correlation(goldRetL, {ret}, {ln})\n", p)
            if mtf:
                s = rep(s, f"corrGold{a}_{w} = {valid} ? _ccGold{a}_{w} : na\n",
                        f"corrGold{a}_{w} = {valid} and {fit} ? _ccGold{a}_{w} : na\n", p)
    open(p, "w", encoding="utf-8").write(s)
    print("applied", p)
