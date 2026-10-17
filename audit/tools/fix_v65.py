"""v65: (a) the 36 correlation lines become one function per asset (identical expansion, refactor_check.py);
(b) F-A65, each macro factor counted once: TIPS off when its symbol IS the 10Y yield's; USD counted once (DXY, with
EURUSD only when DXY has no data); the majority is taken over the factors that remain. Applied identically to the
Master and the three arms; Diagnostics and Brief are rebuilt from the Treatment."""
import sys
FILES = ["artefacts/XAUUSD_Quantum_5_0_" + f + ".pine" for f in ("Master", "Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER")]
AS = [("DXY", "dxyRet", "dxyValid", True), ("Yld", "yieldRet", "yieldValid", True), ("Slv", "silverRet", "silverValid", False),
      ("SPX", "spxRet", "spxValid", False), ("EUR", "eurRet", "eurusdValid", False), ("TIPS", "tipsRet", "tipsValid", True)]
W = [("30", "corrShortLen", "_wS", "_fS"), ("60", "corrMedLen", "_wM", "_fM"), ("120", "corrLongLen", "_wL", "_fL")]


def old_lines(a, ret, valid, mtf):
    cc = [f"_ccGold{a}_{w} = ta.correlation({'goldRetM' if mtf else 'goldRetL'}, {ret}, {wv if mtf else ln})" for w, ln, wv, fv in W]
    gt = [f"corrGold{a}_{w} = {valid}{' and ' + fv if mtf else ''} ? _ccGold{a}_{w} : na" for w, ln, wv, fv in W]
    return cc, gt


FN = """// v65: one function per asset, expanding to exactly the v64 lines (refactor_check.py): the three windows are computed
// every bar and gated after, as before; a macroTF asset passes its macroTF-bar windows and fit flags (F-A64).
f_cc3(float g, float r, bool v, int a, int b, int c, bool fa, bool fb, bool fc) =>
    float x = ta.correlation(g, r, a)
    float y = ta.correlation(g, r, b)
    float z = ta.correlation(g, r, c)
    [v and fa ? x : na, v and fb ? y : na, v and fc ? z : na]
"""


def call(a, ret, valid, mtf):
    args = (f"goldRetM, {ret}, {valid}, _wS, _wM, _wL, _fS, _fM, _fL" if mtf
            else f"goldRetL, {ret}, {valid}, corrShortLen, corrMedLen, corrLongLen, true, true, true")
    return f"[corrGold{a}_30, corrGold{a}_60, corrGold{a}_120] = f_cc3({args})"


R3 = [
    ("tipsValid = not na(tipsClose) and not na(_rawTIPSFast) and not na(_rawTIPSSlow) and tipsStaleCount < MACRO_STALE_MAX\n",
     "// v65 (F-A65): a TIPS symbol that IS the 10Y yield's (the default, Q5.5) counts the 10Y twice: the layer is off.\n"
     "bool _tipsOn = tipsSymbol != yieldSymbol\n"
     "tipsValid = _tipsOn and not na(tipsClose) and not na(_rawTIPSFast) and not na(_rawTIPSSlow) and tipsStaleCount < MACRO_STALE_MAX\n"),
    ("macroBullVotes = (gcConfirmsBull ? 1 : 0) + (dxyBear ? 1 : 0) + (yieldFalling ? 1 : 0) + (spxBull ? 1 : 0) + (eurusdBull ? 1 : 0) + (silverBull ? 1 : 0) + (tipsFalling ? 1 : 0)\n"
     "macroBearVotes = (gcConfirmsBear ? 1 : 0) + (dxyBull ? 1 : 0) + (yieldRising ? 1 : 0) + (spxBear ? 1 : 0) + (eurusdBear ? 1 : 0) + (silverBear ? 1 : 0) + (tipsRising ? 1 : 0)\n",
     "// v65 (F-A65): the dollar is ONE factor. EUR is 57.6% of DXY, so a DXY vote and a EURUSD vote were the same move\n"
     "// counted twice; EURUSD now votes only when DXY has no data.\n"
     "macroBullVotes = (gcConfirmsBull ? 1 : 0) + ((dxyValid ? dxyBear : eurusdBull) ? 1 : 0) + (yieldFalling ? 1 : 0) + (spxBull ? 1 : 0) + (silverBull ? 1 : 0) + (tipsFalling ? 1 : 0)\n"
     "macroBearVotes = (gcConfirmsBear ? 1 : 0) + ((dxyValid ? dxyBull : eurusdBear) ? 1 : 0) + (yieldRising ? 1 : 0) + (spxBear ? 1 : 0) + (silverBear ? 1 : 0) + (tipsRising ? 1 : 0)\n"),
    ("int _macroPool = 6 + (gcValid ? 1 : 0)\n",
     "// v65: the factor slots: USD, 10Y, SPX, silver, TIPS when it is its own feed, GC when valid (majority rule unchanged)\n"
     "int _macroPool = 4 + (_tipsOn ? 1 : 0) + (gcValid ? 1 : 0)\n"),
    ("_wEURr = eurusdValid ? 20.0 : 0.0\n",
     "// v65 (F-A65): EURUSD weighs only as the dollar's stand-in (DXY no data), by |corr| like DXY, not a fixed 20.\n"
     "_wEURr = eurusdValid and not dxyValid ? math.min(math.abs(avgCorrEUR) * 100, 30) : 0.0\n"),
    ("+ (eurusdValid ? (eurusdROC > 0.15 ? 5.0 : eurusdROC < -0.15 ? -5.0 : 0.0) : 0.0)\n",
     "+ (eurusdValid and not dxyValid ? (eurusdROC > 0.15 ? 5.0 : eurusdROC < -0.15 ? -5.0 : 0.0) : 0.0)\n"),
    ("msEUR = eurusdValid ? (eurusdBull ? wEUR : eurusdBear ? -wEUR : 0.0) : 0.0\n",
     "msEUR = eurusdValid and not dxyValid ? (eurusdBull ? wEUR : eurusdBear ? -wEUR : 0.0) : 0.0\n"),   # applied v65 (2nd pass)
    ("macroStrengthConf = int(math.round((_numValid / 6.0) * 30.0",
     "macroStrengthConf = int(math.round((_numValid / (5.0 + (_tipsOn ? 1 : 0))) * 30.0"),
]


def rep(s, old, new, p):
    if s.count(old) != 1:
        sys.exit(f"{p}: anchor found {s.count(old)} times: {old[:90]!r}")
    return s.replace(old, new)


for p in FILES:
    s = open(p, encoding="utf-8").read()
    cc_all, gt_all = [], []
    for a in AS:
        cc, gt = old_lines(*a)
        cc_all += cc
        gt_all += gt
    blk_cc = "\n".join(cc_all) + "\n"
    s = rep(s, blk_cc, FN + "\n".join(call(*a) for a in AS) + "\n", p)
    for g in gt_all:
        s = rep(s, g + "\n", "", p)
    for old, new in R3:
        s = rep(s, old, new, p)
    open(p, "w", encoding="utf-8").write(s)
    print("applied", p)
