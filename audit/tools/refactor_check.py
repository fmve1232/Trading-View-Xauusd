#!/usr/bin/env python3
"""v59 identical-output refactors in the Master, executed (pine_exec.py): every rewrite that paid for restoring the
v57 / v58 removals must print exactly what the v56 code printed. The v56 expressions are frozen here as text (from
commit 2f7f56d7); the v59 ones are read from the Master as written. Usage: python3 audit/tools/refactor_check.py"""
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
L = open(M, encoding="utf-8").read().split("\n")
NA = float("nan")
rng = random.Random(59)
fails = 0


def report(name, bad, n):
    global fails
    fails += bad > 0
    print(f"  {'PASS' if bad == 0 else 'FAIL'}  {name}: {n} cases, mismatches {bad}")


def fn(head):
    a = next(i for i, l in enumerate(L) if l.startswith(head))
    b = a + 1
    while b < len(L) and L[b].startswith(" "):
        b += 1
    return L[a:b]


env = P.Env()
P.define(fn("f_ciHalf(_pPct) =>"), env)
P.define(fn("_pp(float p, bool ci) =>"), env)
P.define(fn("_si(float x) =>"), env)
V56_ROWS = {
    "SL": '"SL " + tpSLStr + (not na(pSLhit) ? "  ~" + str.tostring(int(pSLhit)) + "%" + (not na(f_ciHalf(pSLhit)) ? "±" + str.tostring(int(f_ciHalf(pSLhit))) : "") : "")',
    "TP1": '"TP1 " + tp1Str + (not na(pTP1) ? "  ~" + str.tostring(int(pTP1)) + "%" + (not na(f_ciHalf(pTP1)) ? "±" + str.tostring(int(f_ciHalf(pTP1))) : "") : "")',
    "TP2": '"TP2 " + tp2Str + (not na(pTP2) ? "  ~" + str.tostring(int(pTP2)) + "%" : "")',
    "TP3": '"TP3 " + tp3Str + (not na(pTP3) ? "  ~" + str.tostring(int(pTP3)) + "%" : "")',
}
NEW = {k: re.search(r'tcp\(\d, (' + re.escape('"' + k + ' "') + r'.*?), cBloomBg', "\n".join(L)).group(1) for k in V56_ROWS}
bad = n = 0
for _ in range(3000):
    env["_ciN"] = rng.choice([0.0, 2.0, 3.0, 12.0, 250.0])   # the global f_ciHalf reads (defining scope)
    e = P.Env(funcs=env.funcs, tpSLStr="4138.19", tp1Str="4170.49",
              tp2Str="4186.83", tp3Str="4197.62")
    for v in ("pSLhit", "pTP1", "pTP2", "pTP3"):
        e[v] = NA if rng.random() < 0.2 else rng.uniform(0, 100)
    for k in V56_ROWS:
        n += 1
        bad += P.evaluate(V56_ROWS[k], e) != P.evaluate(NEW[k], e)
report("plan rows SL / TP1 / TP2 / TP3 text (v56 inline == v59 _pp)", bad, n)

V56_SLV = '(not na(silverClose) and silverClose > silverEMA ? 1 : not na(silverClose) and silverClose < silverEMA ? -1 : 0)'
NEW_SLV = '(silverClose > silverEMA ? 1 : silverClose < silverEMA ? -1 : 0)'
assert NEW_SLV in "\n".join(L)
bad = 0
for _ in range(3000):
    e = P.Env(silverClose=NA if rng.random() < 0.2 else rng.uniform(20, 40), silverEMA=NA if rng.random() < 0.1 else rng.uniform(20, 40))
    if rng.random() < 0.1:
        e["silverEMA"] = e["silverClose"]
    bad += P.evaluate(V56_SLV, e) != P.evaluate(NEW_SLV, e)
report("macro line-2 silver vote (na-guard redundant: comparisons with na are false)", bad, 3000)

V56_DCL = '_confDirLabel == "RISK LOCK" ? riskLockStr : _confDirLabel == "BUY" ? "BUY " + str.tostring(confidenceScore) + "/100" : _confDirLabel == "SELL" ? "SELL " + str.tostring(confidenceScore) + "/100" : _confDirLabel == "NO TRADE" ? "NO TRADE Q" + str.tostring(tradeQuality) : _confDirLabel == "WARMUP" ? "WARMUP " + str.tostring(oOosNeff) + "/10eff " + str.tostring(int(math.min(math.max(hN * 100.0 / math.max(OUTCOME_N * 2 + 1, 1), 0.0), 100.0))) + "%hist" + _histGate : "WAIT"'
NEW_DCL = next(l for l in L if l.lstrip().startswith("string _dirConfLabel = ")).split("string _dirConfLabel = ", 1)[1]
bad = 0
for _ in range(3000):
    e = P.Env(funcs=env.funcs, _confDirLabel=rng.choice(["RISK LOCK", "BUY", "SELL", "NO TRADE", "WARMUP", "WAIT"]), riskLockStr="LOCK:DAYLOSS",
              confidenceScore=float(rng.randint(0, 100)), tradeQuality=float(rng.randint(0, 100)), oOosNeff=float(rng.randint(0, 20)),
              hN=float(rng.randint(0, 900)), OUTCOME_N=float(rng.choice([20, 40])), _histGate=rng.choice(["", " G"]))
    bad += P.evaluate(V56_DCL, e) != P.evaluate(NEW_DCL, e)
report("DECISION confidence label (BUY / SELL branches merged)", bad, 3000)


# ---- helpers that replaced repeated inline code (each executed against the inline form it replaced)
H = {}
for head in ("_si(float x) =>", "_sg(float x, string f) =>", "_b1(bool b) =>", "_v(bool u, bool d) =>", "_ud(bool u, bool d) =>",
             "_byDest(float a, float b, float c, float d, float e, float f, float g, float h) =>"):
    P.define(fn(head), env)
bad = 0
for _ in range(4000):
    x = rng.choice([NA, 0.0, -0.0, rng.uniform(-50, 50), float(rng.randint(-9, 99))])
    u, d = rng.random() < 0.5, rng.random() < 0.5
    e = P.Env(funcs=env.funcs, x=x, u=u, d=d, liqDestLabel=rng.choice(["PDH", "PDL", "PWH", "PWL", "PMH", "PML", "EQH", "EQL", "—"]),
              a1=1.0, a2=2.0, a3=3.0, a4=4.0, a5=5.0, a6=6.0, a7=7.0, a8=NA)
    env["liqDestLabel"] = e["liqDestLabel"]
    pairs = [("str.tostring(int(x))", "_si(x)"), ('(x >= 0 ? "+" : "") + str.tostring(x, "#.##")', '_sg(x, "#.##")'),
             ("(u ? 1 : 0)", "_b1(u)"), ("(u ? 1 : d ? -1 : 0)", "_v(u, d)"), ('(u ? "▲" : d ? "▼" : "·")', "_ud(u, d)"),
             ('liqDestLabel == "PDH" ? a1 : liqDestLabel == "PDL" ? a2 : liqDestLabel == "PWH" ? a3 : liqDestLabel == "PWL" ? a4 : liqDestLabel == "PMH" ? a5 : liqDestLabel == "PML" ? a6 : liqDestLabel == "EQH" ? a7 : liqDestLabel == "EQL" ? a8 : na',
              "_byDest(a1, a2, a3, a4, a5, a6, a7, a8)")]
    for old, new in pairs:
        o, n2 = P.evaluate(old, e), P.evaluate(new, e)
        same = (o == n2) or (isinstance(o, float) and isinstance(n2, float) and o != o and n2 != n2)
        bad += not same
report("helpers _si / _sg / _b1 / _v / _ud / _byDest == the inline code they replaced", bad, 4000 * 6)
# the ENTRY row's offset sign used `> 0`, _sg uses `>= 0`: only reached when mt5Offset != 0, where they agree
assert '(mt5Offset != 0.0 ? "  [MT5" + _sg(mt5Offset, "#.##")' in "\n".join(L)

# ---- alerts: every v56 message is still sent, word for word, through _al (prefix + frequency folded in)
import subprocess
V56 = subprocess.run(["git", "show", "2f7f56d7:" + M], capture_output=True, text=True, check=True).stdout.split("\n")
pre, suf = 'alert("XAUUSD " + timeframe.period + ', ", alert.freq_once_per_bar_close)"
olds = [l[l.index(pre) + len(pre):l.rstrip().rindex(suf)] for l in V56 if pre in l and l.rstrip().endswith(suf)]
cur = "\n".join(L)
assert next(l for l in L if l.startswith("_al(string m) =>")).endswith('alert("XAUUSD " + timeframe.period + m, alert.freq_once_per_bar_close)')
miss = [o for o in olds if "_al(" + o.replace('" BUY | " + _mt5Plan', '" BUY | " + _mt5Plan') + ")" not in cur]
report(f"alerts: all {len(olds)} v56 messages sent unchanged via _al", len(miss), len(olds))
for o in miss[:3]:
    print("     missing:", o[:100])

# ---- plan rows: row 0 / width 0 were the only values ever passed; the 8 rows are the same calls without them
tcpdef = next(l for l in L if l.startswith("tcp(col, txt, bg, ts) =>"))
ok = "_dashMobile ? 9 + col : 0," in tcpdef and "width=0" in tcpdef and len(re.findall(r"(?<![\w.])tcp\(\d, ", cur)) == 8 \
     and len(re.findall(r"tcp\(\d, 0, ", "\n".join(V56))) == 8
report("plan rows: 8 tcp calls, row 0 / width 0 folded into the helper", 0 if ok else 1, 8)


# ---- v60 (Mobile Strip): size mappings computed once, headers in a loop, tc via tcb, opaque colour literals
V59 = subprocess.run(["git", "show", "c919dc5d:" + M], capture_output=True, text=True, check=True).stdout.split("\n")
OLD_SZ = {"_hdSize": 'textSize == "Auto" ? "small" : textSize == "Large" ? "normal" : textSize == "Small" ? "tiny" : "small"',
          "_prSize": 'textSize == "Auto" ? "normal" : textSize == "Large" ? "large" : textSize == "Small" ? "small" : "normal"',
          "_seSize": 'textSize == "Auto" ? "tiny" : textSize == "Large" ? "small" : textSize == "Small" ? "tiny" : "small"',
          "_pSz": 'textSize == "Large" ? "normal" : textSize == "Small" ? "tiny" : "small"'}
glob = {l.split(" = ", 1)[0].split()[-1]: l.split(" = ", 1)[1] for l in L if l.startswith(("string _szHd = ", "string _szSe = "))}
bad = 0
for ts in ("Auto", "Small", "Medium", "Large"):
    e = P.Env(textSize=ts)
    e["_szHd"], e["_szSe"] = P.evaluate(glob["_szHd"], e), P.evaluate(glob["_szSe"], e)
    for v, old in OLD_SZ.items():
        new = next(l for l in L if l.lstrip().startswith("string " + v + " = ")).split(" = ", 1)[1].split("//")[0].strip()
        bad += P.evaluate(old, e) != P.evaluate(new, e)
report("text sizes _hdSize / _prSize / _seSize / _pSz (v59 ternaries == v60 shared mappings)", bad, 16)
heads59 = re.findall(r'tc\(\d, 0, "([A-Z]+)", C_TEXT, _hdSize, _w\d\)', "\n".join(V59))
heads60 = re.findall(r'"([A-Z]+)"', next(l for l in L if l.lstrip().startswith("for [k, h] in array.from(")))
report("desktop headers: same 9 names, same order (loop)", 0 if heads59 == heads60 and len(heads60) == 9 else 1, 9)
ok = any(l.startswith("tc(col, row, txt, tcol, ts, w) => tcb(col, row, txt, tcol, color(na), ts, w)") for l in L)
report("tc = tcb with no background (table.cell's default bgcolor is na)", 0 if ok else 1, 1)
lit59 = re.findall(r"color\.new\((#[0-9A-Fa-f]{6}), 0\)", "\n".join(l for l in V59 if not l.lstrip().startswith("//")))
left = re.findall(r"color\.new\((#[0-9A-Fa-f]{6}), 0\)", "\n".join(l for l in L if not l.lstrip().startswith("//")))
report(f"opaque colours: {len(lit59)} color.new(#rrggbb, 0) -> #rrggbb (identical: transparency 0)", len(left), len(lit59))


# ---- v60 Strip fold, the coordinate expressions of tcb executed as written
tl = next(l for l in L if l.lstrip().startswith("table.cell(tblA, _dashStrip ? col % 3 : col,"))
cx, cy = [x.strip() for x in P._split_args(tl.strip()[len("table.cell("):-1])[1:3]]
gate = next(L[i] for i, l in enumerate(L) if l.startswith("tcb(col, row, txt, tcol, bg, ts, w) =>") for _ in [0])
cond = L[L.index(gate) + 1].strip()[3:]
P.BUILTINS["int"] = lambda x: P.NA if P.isna(x) else int(x)
seen, bad = {}, 0
for col in range(9):
    for row in range(4):
        e = P.Env(col=float(col), row=float(row), _dashStrip=True, _dashMobile=False)
        shown = bool(P.evaluate(cond, e))
        if row >= 2:
            bad += shown                          # detail rows must not be written in the strip
            continue
        x, y = int(P.evaluate(cx.replace("%", "%"), e)), int(P.evaluate(cy, e))
        bad += not (0 <= x < 3 and 0 <= y < 6) or (x, y) in seen
        seen[(x, y)] = (col, row)
        if row == 1:
            bad += seen.get((x, y - 1)) != (col, 0)   # each value sits directly under its own header
report("Strip fold: 9 headers + 9 values on unique cells of the 3 x 6 grid, header above value, details skipped", bad, 36)

left = [i + 1 for i, l in enumerate(L) if re.search(r"array\.get\(gDash[SCF], \d+\)", l)]
helpers = all(any(l.startswith(f"_g{c}(int i) => array.get(gDash{c}, i)") for l in L) for c in "SCF")
report("dashboard array reads go through _gS / _gC / _gF (identical: array.get(gDash*, i))", 0 if helpers and not left else 1, 1)
print(f"RESULT: {'PASS' if fails == 0 else 'FAIL'} -- v56 and v59 Pine text executed side by side; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
