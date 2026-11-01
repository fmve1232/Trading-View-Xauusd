#!/usr/bin/env python3
"""v95: Visuals' structure, CHURN and FVG zones are the Master's engine (operator, 2026-10-31: "Copy the engine's code").

1 verbatim: every code line between SX-BEGIN and SX-END in Visuals is a Master line, in the Master's order
2 complete: the backward slice of the Master from bosLabelBull / Bear, chochLabelBull / Bear, mssLabelBull / Bear and
  fvgDetected (v88_check's statement rules) is in Visuals verbatim; one stated exception: the Master's engine switch
  `showFVG` (Visuals' own draw switch stands in), and group-name lines
3 wired: the structure labels read bosLabel* and the CHoCH / MSS first bars, CHURN reads bosLabel*, the FVG boxes
  fvgDetected, the order-block displacement adaptiveATR, the ADX / DI display adxVal / diplus / diminus; no "~BOS" /
  "~CHoCH" text, no V-suffixed parity inputs or computations remain; fvgMaxBars has the Master's default and bounds
4 executed: CHURN's flip counter run as written on random sequences of engine BOS breaks vs an independent reference
5 derivations: v95 == fix_v95.visuals(v94); Visuals == fix_v96.visuals(v95), byte for byte
4b the OB drawing's selection rule, executed
The ta.* series functions inside the block are not executed here (they are the Master's own lines, byte for byte, and
run by TradingView); NOT RUN: the chart. Usage: python3 audit/tools/sx_check.py"""
import os, random, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402
import fix_v95 as F95  # noqa: E402
import fix_v96 as F96  # noqa: E402   (extends F95.TARGETS / SKIP with the order-block lifecycle)

MF, VF = "artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
M = open(MF, encoding="utf-8").read().split("\n")
V = open(VF, encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg)
    fails += not ok


a = next(i for i, l in enumerate(V) if l.startswith("// SX-BEGIN"))
b = next(i for i, l in enumerate(V) if l.startswith("// SX-END"))
blk = [l for l in V[a + 1:b] if l.strip() and not l.lstrip().startswith("//")]
pos, ok1, bad = 0, True, None
for l in blk:
    try:
        pos = M.index(l, pos) + 1
    except ValueError:
        ok1, bad = False, l
        break
report(ok1 and len(blk) > 50, f"1 verbatim: {len(blk)} SX lines, each a Master line in the Master's order" + (f" -- not: {bad[:80]}" if bad else ""))

sx = F95.sx_lines(M)
Vset = set(V)
missing = [l for l in sx if l not in Vset and not re.match(r"^grp\w+ = ", l)]
skipped = [l for l in M if l.startswith(('showFVG = input.bool(true, "Fair Value Gaps (engine)"', 'showOB = input.bool(true, "Order Blocks (engine)"'))]
report(not missing and len(skipped) == 2 and not any(l.startswith(("showFVG = input.bool(true", "showOB = input.bool(true")) for l in V),
       f"2 complete: the Master's structure + FVG slice ({len(sx)} lines) is in Visuals verbatim; the one exception is the engine "
       f"switches showFVG / showOB (Visuals' draw switches stand in)" + (f" -- missing {missing[:2]}" if missing else ""))

txt = "\n".join(V)
code = "\n".join(l.split("//")[0] if '"' not in l else l for l in V if not l.lstrip().startswith("//"))
checks = {
    "labels read the engine": bool(re.search(r"if bosLabelBull or sxChochUp or sxMssUp", code)) and bool(re.search(r"if bosLabelBear or sxChochDn or sxMssDn", code)),
    "CHoCH / MSS first bar": all(x in code for x in ("bool sxChochUp = chochLabelBull and not chochLabelBull[1]",
                                                     "bool sxMssDn = mssLabelBear and not mssLabelBear[1]")),
    "CHURN reads bosLabel*": "if barstate.isconfirmed and (bosLabelBull or bosLabelBear)" in code and "int _nd = bosLabelBear ? -1 : 1" in code,
    "FVG boxes use fvgDetected": "if fvgDetected and bar_index > 3" in code,
    "OB displacement = the engine's (in SX)": any(l.startswith("displacementUp = ") for l in blk) and any("dispOnsetUp" in l for l in blk),
    "ADX / DI display on the engine": "adxValV" not in code and "_diPV" not in code and "_diMV" not in code and "adxVal" in code,
    "no ~ labels": "~BOS" not in code and "~CHoCH" not in code,
    "no V parity inputs": not re.search(r"\b(adxLenV|adxThresholdV|showAdaptiveATRV|adaptiveATRV|regimeStrengthV|atrTrendingV|atrRangingV|brokeUp|brokeDown|fvgMinATR)\b", code),
    "fvgMaxBars = the Master's": re.search(r"^fvgMaxBars\s*=\s*input\.int\(30,.*minval = 10, maxval = 100", txt, re.M) is not None
                                  and re.search(r"^fvgMaxBars = input\.int\(30, .*minval=10, maxval=100", "\n".join(M), re.M) is not None,
    "OB boxes = the engine's queue": "f_obDraw(obBullHighA, obBullLowA, obBullBarA, obBullMitA, true, obBullActive, obBullHigh)" in code
                                     and "f_obDraw(obBearHighA, obBearLowA, obBearBarA, obBearMitA, false, obBearActive, obBearHigh)" in code,
    "no V displacement / obDispATR": not re.search(r"\b(obDispATR|dispOnsetUpV|dispOnsetDownV|displacementUpV|_bodySzV|_dispEnterV)\b", code),
    "obKeep <= the engine's queue (5)": re.search(r"^obKeep\s*=\s*input\.int\(5,.*maxval = 5", txt, re.M) is not None
                                        and "int obMaxQueue = 5" in "\n".join(M),
    "drawings stay OFF by default": re.search(r'^showStruct\s*=\s*input\.bool\(false', txt, re.M) is not None
                                    and re.search(r'^showFVG\s*=\s*input\.bool\(false', txt, re.M) is not None
                                    and re.search(r'^showOB\s*=\s*input\.bool\(false', txt, re.M) is not None,
}
report(all(checks.values()), "3 wired: " + "; ".join(f"{k} {'ok' if v else 'NO'}" for k, v in checks.items()))

c0 = next(i for i, l in enumerate(V) if l.startswith("if barstate.isconfirmed and (bosLabelBull or bosLabelBear)"))
CH = [V[c0], V[c0 + 1], V[c0 + 2], V[c0 + 3]]
rng = random.Random(95)
bad4 = 0
for _ in range(400):
    n = rng.randint(5, 120)
    env = P.Env(ckDir=0.0, isC=True)
    flips = []
    ref_dir, ref = 0, []
    for k in range(n):
        up, dn = rng.random() < .12, rng.random() < .12
        env.update(bosLabelBull=up, bosLabelBear=dn, ckFlip=False)
        P.run([l.replace("barstate.isconfirmed", "isC") for l in CH], env)
        flips.append(bool(env["ckFlip"]))
        f = False
        if up or dn:
            d = -1 if dn else 1
            f = ref_dir != 0 and d != ref_dir
            ref_dir = d
        ref.append(f)
    bad4 += flips != ref
report(bad4 == 0, f"4 executed: CHURN's flip counter on 400 random sequences of the engine's BOS breaks vs a reference: mismatches {bad4}")

# ---- 4b the drawing's selection rule, executed from f_obDraw's own lines (box / label calls replaced by a recorder)
fa = next(i for i, l in enumerate(V) if l.startswith("f_obDraw("))
fb = next(i for i in range(fa + 1, len(V)) if V[i] and not V[i].startswith(" "))
body = [l[4:] for l in V[fa + 1:fb] if l.strip() and "array.push(" not in l and not l.strip().startswith("if obShowLabel")]
body = [l for l in body if l.strip() != "true"]
body.insert(body.index(next(l for l in body if "color _oc" in l)) + 1, "        array.push(rec, _on ? 1 : 0)")
bad4b = 0
for _ in range(500):
    n = rng.randint(0, 5); keep = rng.randint(1, 5)
    hA = [rng.uniform(1990, 2010) for _k in range(n)]
    act = rng.random() < .6
    actHi = hA[0] if (n and act) else rng.uniform(1990, 2010)
    env = P.Env(hA=hA, lA=[h - 2 for h in hA], bA=[100 - k for k in range(n)], mA=[rng.random() < .3 for _k in range(n)],
                bull=True, act=act, actHi=actHi, obKeep=float(keep), zoneFlatCol=True, cOB="OB", cBull="B", cBear="R", rec=[])
    P.run(body, env)
    want = [1 if (k == 0 and act and hA[0] == actHi) else 0 for k in range(min(n, keep))]
    bad4b += env["rec"] != want
report(bad4b == 0, f"4b executed: the OB drawing selects the engine's newest blocks first, at most obKeep, bold only for the active one: 500 cases, mismatches {bad4b}")

v94v = subprocess.run(["git", "show", "c18c4f765:" + VF], capture_output=True, text=True, check=True).stdout
v95v = subprocess.run(["git", "show", "4e79e9f3f:" + VF], capture_output=True, text=True, check=True).stdout
_t = list(F95.TARGETS); _s = set(F95.SKIP)
F95.TARGETS[:] = [x for x in F95.TARGETS if not x.startswith("ob")]; F95.SKIP.discard('showOB = input.bool(true, "Order Blocks (engine)"')
d95 = F95.visuals(v94v, "\n".join(M)) == v95v
F95.TARGETS[:] = _t; F95.SKIP |= _s
report(d95 and F96.visuals(v95v, "\n".join(M)) == "\n".join(V),
       "5 derivations, byte for byte: v95 (4e79e9f3f) == fix_v95.visuals(v94); Visuals == fix_v96.visuals(v95)")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text read and executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
