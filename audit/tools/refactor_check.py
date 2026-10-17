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
    pairs = [('na(x) ? "—" : str.tostring(int(x))', "_si(x)"),   # v61 F-A59: intentional, "—" instead of "NaN" ('(x >= 0 ? "+" : "") + str.tostring(x, "#.##")', '_sg(x, "#.##")'),
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
# v68: tc (= tcb with no background) is written out at each call site; the derivation case below proves it.

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

# ---- v62 (F-A60): the raw HTF scores are computed once (h2S1 / h2S4 / h2SD) and the engine gates them as before.
# The v61 engine lines are frozen here; the v62 lines are read from the Master. The engine's htf*Score must not move.
V61_HTF = {f"htf{k}Score": f"htf{k}Available ? htfTrendScore(htf{k}Close, htf{k}Ema20, htf{k}Ema100M, htf{k}Ema200) : 50"
           for k in ("1h", "4h", "1d")}
P.define(fn("htfTrendScore(htfClose, htfEma20, htfEma100M, htfEma200) =>"), env)
raw = [l for l in L if re.match(r"^int h2S[14D] = htfTrendScore\(", l)]
gated = [l for l in L if re.match(r"^htf(1h|4h|1d)Score = ", l)]
bad = n = 0
for _ in range(4000):
    e = P.Env(funcs=env.funcs)
    for k in ("1h", "4h", "1d"):
        e[f"htf{k}Available"] = rng.random() < 0.5
        for v in ("Close", "Ema20", "Ema100M", "Ema200"):
            e[f"htf{k}{v}"] = NA if rng.random() < 0.1 else float(rng.choice([1, 2, 3, 4]))
    old = {k: P.evaluate(x, e) for k, x in V61_HTF.items()}
    P.run(raw + gated, e)
    n += 3
    bad += sum(old[k] != e[k] for k in old)
report("engine htf1hScore / htf4hScore / htf1dScore (v61 inline == v62 gated h2S*)",
       bad if len(raw) == 3 and len(gated) == 3 else n, n)

# ---- v63: the MTF bias counts and the agreement count reuse sums that already exist (the v62 lines frozen here)
V62_CNT = {"_htfBullCnt": "_b1(htf15mBull) + _b1(htf1hBull) + _b1(htf4hBull)",
           "_htfBearCnt": "_b1(htf15mBear) + _b1(htf1hBear) + _b1(htf4hBear)",
           "_agreeCount": "shouldBuy ? _b1(htf5mBull) + _b1(htf15mBull) + _b1(htf1hBull) + _b1(htf4hBull) + _b1(htf1dBull) : "
                          "shouldSell ? _b1(htf5mBear) + _b1(htf15mBear) + _b1(htf1hBear) + _b1(htf4hBear) + _b1(htf1dBear) : 0"}
P.define(fn("_b1(bool b) =>"), env)
pre = [l for l in L if re.match(r"^htfFull(Long|Short) = ", l)] + \
      [l.strip() for l in L if re.match(r"^\s+int _inst(Bull|Bear)Cnt = ", l)]
new = {k: next(l.strip().split(" = ", 1)[1] for l in L if l.strip().startswith(f"int {k} = ")) for k in V62_CNT}
bad = n = 0
import itertools  # noqa: E402
for bits in itertools.product([False, True], repeat=12):
    e = P.Env(funcs=env.funcs)
    for i, k in enumerate(("5m", "15m", "1h", "4h", "1d")):
        e[f"htf{k}Bull"], e[f"htf{k}Bear"] = bits[2 * i], bits[2 * i + 1] and not bits[2 * i]
    e["shouldBuy"], e["shouldSell"] = bits[10], bits[11] and not bits[10]
    P.run(pre, e)
    for k in V62_CNT:
        n += 1
        bad += P.evaluate(V62_CNT[k], e) != P.evaluate(new[k], e)
report("MTF bias counts / agreement count (v62 sums == v63 reuse of _inst*Cnt / htfFull*)", bad if len(pre) == 4 else n, n)

# ---- v63 (F-A63): MTF scores and agreement count only the layers live on the chart timeframe. Where every layer
# is live the text must equal v62's; otherwise a dead layer prints — and INST / Agree use the live layers only.
V62_SC = {"_currScore": "int(math.round(htf5mScore))", "_swingScore": "int(math.round(htf15mScore))",
          "_instScore": "int(math.round((htf1hScore + htf4hScore) / 2.0))"}
V62_BD = '"C" + str.tostring(_currScore) + " S" + str.tostring(_swingScore) + " I" + str.tostring(_instScore)'
V62_AG = '"Agree " + _si(_agreeCount / 5.0 * 100) + "%"'
sc = {k: next(l.strip().split(" = ", 1)[1] for l in L if l.strip().startswith(f"float {k} = ")) for k in V62_SC}
bd = '"C" + _si(_currScore) + " S" + _si(_swingScore) + " I" + _si(_instScore)'
assert '"C" + _cS + _si(_currScore) + " S" + _sS + _si(_swingScore) + " I" + _iS + _si(_instScore)' in "\n".join(L)
ag = next(l.strip().split(" = ", 1)[1] for l in L if l.strip().startswith("string _agreePct = "))
fa = next(l for l in L if l.startswith("int htfFullAvail = "))
mt = next(l for l in L if l.startswith("int mtfAvail = "))
bad = n = 0
for sec in (60, 300, 900, 3600, 7200, 14400, 86400, 604800):
    for _ in range(300):
        e = P.Env(funcs=env.funcs)
        for k, lim in (("5m", 300), ("15m", 900), ("1h", 3600), ("4h", 14400), ("1d", 86400)):
            e[f"htf{k}Available"] = sec < lim
            e[f"htf{k}Score"] = float(rng.choice([0, 20, 40, 60, 80, 100])) if sec < lim else 50.0
        e["_agreeCount"] = float(rng.randint(0, sum(sec < x for x in (300, 900, 3600, 14400, 86400))))
        P.run([mt, fa], e)
        old = P.Env(funcs=env.funcs, **e)
        for k, x in V62_SC.items():
            old[k] = P.evaluate(x, old)
            e[k] = P.evaluate(sc[k], e)
        live = [e[f"htf{k}Available"] for k in ("5m", "15m", "1h", "4h", "1d")]
        got, want_old = P.evaluate(bd, e), P.evaluate(V62_BD, old)
        n += 2
        if all(live):
            bad += got != want_old
            bad += P.evaluate(ag, e) != P.evaluate(V62_AG, old)
        else:
            exp_inst = (e["htf1hScore"] + e["htf4hScore"]) / 2.0 if live[2] else e["htf4hScore"] if live[3] else None
            want = ("C" + (str(int(e["htf5mScore"])) if live[0] else "—") + " S" + (str(int(e["htf15mScore"])) if live[1] else "—")
                    + " I" + (str(int(P._round(exp_inst))) if exp_inst is not None else "—"))
            bad += got != want
            nl = sum(live)
            bad += P.evaluate(ag, e) != ("Agree " + (str(int(e["_agreeCount"] * 100.0 / nl)) if nl else "—") + "%")
report("MTF C/S/I scores and Agree %: = v62 when every layer is live, live layers only otherwise (8 TFs)", bad, n)

# ---- v64: the valid-feed count is computed once (v63 had _numStab, _numValid and an inline sum of the same six
# flags) and the session literals lose their int((x.0)) wrappers. v63 text frozen here; v64 read from the Master.
VF = ["dxyValid", "yieldValid", "silverValid", "spxValid", "eurusdValid", "tipsValid"]
V63_STAB = (["float _numStab = 0.0"] + [f"_numStab := {v} ? _numStab + 1.0 : _numStab" for v in VF]
            + ["avgStability = _numStab > 0 ? (stabDXY + stabYld + stabSlv + stabSPX + stabEUR + stabTIPS) / _numStab : 0.0"])
V63_CONF = "(((dxyValid ? 1 : 0) + (yieldValid ? 1 : 0) + (silverValid ? 1 : 0) + (spxValid ? 1 : 0) + (eurusdValid ? 1 : 0) + (tipsValid ? 1 : 0)) / 6.0) * 30.0"
V63_SESS = ["sessionQuality = 0",
            "sessionQuality += inKillzone ? int((30.0 + regimeStrength * 20.0)) : inLondon or inNY ? int((25.0)) : inAsian ? int((10.0)) : 0",
            "sessionQuality += (not inAsian or inLondonKZ) ? int((10.0)) : 0"]
a = L.index("float _numValid = 0.0")
v64_stab = L[a:a + 8]
assert v64_stab[-1].startswith("avgStability = _numValid > 0 ? ")
conf = next(l for l in L if l.startswith("macroStrengthConf = int(math.round((_numValid / (5.0 + (_tipsOn ? 1 : 0))) * 30.0"))
V64_CONF = "(_numValid / (5.0 + (_tipsOn ? 1 : 0))) * 30.0"     # v65 (F-A65): = v64's / 6.0 whenever TIPS is its own feed
sess = ["sessionQuality = 0"] + [l for l in L if l.startswith("sessionQuality += inKillzone ? ") or
                                 l.startswith("sessionQuality += (not inAsian or inLondonKZ) ? ")]
bad = n = 0
for _ in range(4000):
    e = P.Env(funcs=env.funcs)
    for v in VF:
        e[v] = rng.random() < 0.7
    for k in ("DXY", "Yld", "Slv", "SPX", "EUR", "TIPS"):
        e["stab" + k] = rng.uniform(0, 2)
    for k in ("inKillzone", "inLondon", "inNY", "inAsian", "inLondonKZ"):
        e[k] = rng.random() < 0.5
    e["regimeStrength"] = rng.choice([0.0, 0.25, 0.5, 1.0])
    e["_tipsOn"] = True
    o, w = P.Env(funcs=env.funcs, **e), P.Env(funcs=env.funcs, **e)
    P.run(V63_STAB + V63_SESS, o)
    P.run(v64_stab + sess, w)
    n += 3
    bad += o["avgStability"] != w["avgStability"]
    bad += P.evaluate(V63_CONF, o) != P.evaluate(V64_CONF, w)
    bad += o["sessionQuality"] != w["sessionQuality"]
report("valid-feed count once (avgStability, macroStrengthConf availability) + session literals (v63 == v64)",
       bad if len(sess) == 3 and V64_CONF in conf else n, n)

# ---- v65: the 36 correlation lines are one f_cc3 call per asset. Expanding each call through the function body
# must give back exactly the v64 lines (read from the v64 commit 28dabac1, not retyped here).
V64 = subprocess.run(["git", "show", "28dabac1:" + M], capture_output=True, text=True, check=True).stdout.split("\n")
h = L.index(next(l for l in L if l.startswith("f_cc3(")))
fbody = [l.strip() for l in L[h + 1:h + 5]]
params = [x.split()[-1] for x in L[h][len("f_cc3("):L[h].index(")")].split(",")]
ok = fbody == ["float x = ta.correlation(g, r, a)", "float y = ta.correlation(g, r, b)", "float z = ta.correlation(g, r, c)",
               "[v and fa ? x : na, v and fb ? y : na, v and fc ? z : na]"]
calls = [l for l in L if re.match(r"^\[corrGold\w+_30, corrGold\w+_60, corrGold\w+_120\] = f_cc3\(", l)]
bad = 0
for c in calls:
    asset = re.match(r"^\[corrGold(\w+)_30", c).group(1)
    args = dict(zip(params, P._split_args(c[c.index("f_cc3(") + 6:-1])))
    for w, ln, fl in (("30", "a", "fa"), ("60", "b", "fb"), ("120", "c", "fc")):
        cc = f"_ccGold{asset}_{w} = ta.correlation({args['g']}, {args['r']}, {args[ln]})"
        gate = f"corrGold{asset}_{w} = {args['v']}{'' if args[fl] == 'true' else ' and ' + args[fl]} ? _ccGold{asset}_{w} : na"
        bad += cc not in V64
        bad += gate not in V64
report("f_cc3 calls expand to exactly the v64 correlation and gating lines (36 lines, from commit 28dabac1)",
       bad if ok and len(calls) == 6 else 36, 36)

# ---- v68 (F-A66): v67's (x ? 1 : 0) -> _b1(x) is UNDONE (the compiler expands each call: it cost tokens, the Master
# hit 100,335). The Master is DERIVED from its v66 commit by fix_v68.transform (single-call dashboard functions inlined,
# _gS/_gC/_gF/tc/_m written out); it must equal that derivation byte for byte, and every expanded helper must use each
# parameter exactly once (so writing it out evaluates the same expression). The arms must equal their v66 commit except
# the v67 engine-stats scorecard row and the stamp. _b1 is still executed (the Master's own display helper).
import fix_v68 as F  # noqa: E402
v66m = subprocess.run(["git", "show", "a5fc12ce:" + M], capture_output=True, text=True, check=True).stdout
P.define(fn("_b1(bool b) =>"), env)
b1ok = all(P.evaluate(f"_b1({str(x).lower()})", P.Env(funcs=env.funcs)) == (1 if x else 0) == P.BUILTINS["_b1"](x)
           for x in (True, False))
derived = F.transform(v66m) == open(M, encoding="utf-8").read()
once = F.params_once(v66m)
arms_bad = 0
for f in ("Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER"):
    path = f"artefacts/XAUUSD_Quantum_5_0_{f}.pine"
    old = [l for l in subprocess.run(["git", "show", "a5fc12ce:" + path], capture_output=True, text=True, check=True).stdout.split("\n")
           if "BUILD STAMP" not in l]
    new = [l.replace(", 2, 11, bgco", ", 2, 10, bgco") for l in open(path, encoding="utf-8").read().split("\n")
           if "BUILD STAMP" not in l and not l.startswith("_fwI(float x) =>") and "engine-stats row" not in l
           and not l.lstrip().startswith('_fwRow(10, "Engine stats (display)"') and "computed but never showed (as the Master" not in l]
    arms_bad += old != new
report("Master == fix_v68.transform(v66 commit), byte for byte; expanded helpers use each parameter once; arms == v66 "
       "+ the v67 scorecard row; _b1 executed", 0 if derived and not once and not arms_bad and b1ok else 1, 1)

# v59's '_gS / _gC / _gF' helpers are written out since v68 (array.get(gDash*, i)); the derivation case proves it.
print(f"RESULT: {'PASS' if fails == 0 else 'FAIL'} -- v56 and v59 Pine text executed side by side; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
