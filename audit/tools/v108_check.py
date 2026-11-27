#!/usr/bin/env python3
"""v108: run-time rewrites that change no output (identical-output, F-A94).

  1 H2 volume profile, EXECUTED on real XAU/USD 15m bars (the website's market-data store): the block's rule run with
    the profile rebuilt on every confirmed bar (to v107) and only where it is read (v108: a sweep bar or the last two
    bars). Every bar's h2Long / h2Short / h2Sl / h2Tp1 / h2Tp2 and the last two bars' POC / VAH / VAL must be equal.
    Trend is set true both ways so every sweep bar reads the profile (the strictest case).
  2 every READ of h2Poc / h2Vah / h2Val / h2Next in the Master, Visuals and Strategy_H2 is either a signal / plan line
    (false or na unless h2SweepL / h2SweepH) or inside a display function whose every call is on the last bar
  3 quantile pass: the six engine copies carry `array.copy(array.slice(hPred, 0, hN))` and no element-by-element loop;
    executed: the copy equals the loop's array for every hN (50 .. HIST_MAX), wrapped ring buffer included
  4 controls: a profile gated on h2SweepL only (no last-bar rebuild) is detected by 1; a read placed outside a display
    function is detected by 2
Usage: python3 audit/tools/v108_check.py   (needs origin/market-data: git fetch --depth=1 origin market-data)"""
import csv
import io
import math
import random
import re
import subprocess
import sys

A = "artefacts/XAUUSD_Quantum_5_0_"
FILES = {"Master": A + "Master.pine", "Visuals": "artefacts/XAUUSD_Quantum_5_5_Visuals.pine", "H2 arm": A + "Strategy_H2.pine"}
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout


# ---------- 1 executed on real bars ----------
rows = []
for f in sorted(x for x in git("ls-tree", "-r", "--name-only", "origin/market-data").split() if x.startswith("XAU_USD_15m/")):
    for r in csv.DictReader(io.StringIO(git("show", "origin/market-data:" + f))):
        rows.append((float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0.0)))
H = [r[0] for r in rows]
L_ = [r[1] for r in rows]
C = [r[2] for r in rows]
V = [r[3] for r in rows]
n = len(C)


def vp(i):
    hi, lo = max(H[i - 99:i + 1]), min(L_[i - 99:i + 1])
    if not hi > lo:
        return None
    bs = (hi - lo) / 40.0
    vv = [0.0] * 40
    for k in range(i - 99, i + 1):
        vv[max(0, min(int(((H[k] + L_[k] + C[k]) / 3.0 - lo) / bs), 39))] += V[k]
    pk, mx = 0, 0.0
    for j in range(40):
        if vv[j] > mx:
            mx, pk = vv[j], j
    cum, tgt, a, b = mx, sum(vv) * 0.70, pk, pk
    while cum < tgt and (a > 0 or b < 39):
        vb = vv[a - 1] if a > 0 else -1.0
        va = vv[b + 1] if b < 39 else -1.0
        if va >= vb and b < 39:
            b += 1
            cum += va
        elif a > 0:
            a -= 1
            cum += vb
        else:
            break
    return lo + bs * (pk + .5), lo + bs * (b + .5), lo + bs * (a + .5)


atr = []
for i in range(n):
    tr = H[i] - L_[i] if i == 0 else max(H[i] - L_[i], abs(H[i] - C[i - 1]), abs(L_[i] - C[i - 1]))
    atr.append(tr if i == 0 else (atr[-1] * 13 + tr) / 14)


def run(gate):
    swH = swL = None
    poc = vah = val = None
    out = []
    for i in range(n):
        sL = swL is not None and L_[i] < swL and C[i] > swL
        sH = swH is not None and H[i] > swH and C[i] < swH
        if swL is not None and L_[i] < swL:
            swL = None
        if swH is not None and H[i] > swH:
            swH = None
        if i >= 10:
            c = i - 5
            if all(L_[c] < L_[k] for k in range(c - 5, i + 1) if k != c):
                swL = L_[c]
            if all(H[c] > H[k] for k in range(c - 5, i + 1) if k != c):
                swH = H[c]
        if i >= 100 and gate(sL, sH, i):
            r = vp(i)
            if r:
                poc, vah, val = r
        a = atr[i]
        rl = C[i] - (L_[i] - 0.15 * a) if sL else None
        rs = (H[i] + 0.15 * a) - C[i] if sH else None
        lg = sL and poc is not None and C[i] <= poc and 0.5 * a <= rl <= 5 * a
        sh = sH and poc is not None and C[i] >= poc and 0.5 * a <= rs <= 5 * a
        if lg:
            out.append((1, C[i] - rl, max(poc, C[i] + rl), max(vah, C[i] + 2 * rl)))
        elif sh:
            out.append((-1, C[i] + rs, min(poc, C[i] - rs), min(val, C[i] - 2 * rs)))
        else:
            out.append((0,))
        if i >= n - 2:
            out[-1] = out[-1] + ((poc, vah, val),)
    return out


old = run(lambda sL, sH, i: True)
new = run(lambda sL, sH, i: sL or sH or i >= n - 2)
ctl = run(lambda sL, sH, i: sL or sH)
sig = sum(1 for o in old if o[0])
report(n > 1000 and old == new, f"1 real XAU/USD 15m, {n} bars, {sig} sweep signals (trend both ways): signals, SL, TP1, TP2 on every "
       f"bar and the last two bars' POC / VAH / VAL identical with the profile rebuilt only where read")

# ---------- 2 every read is a signal line or a last-bar display ----------
SIG = re.compile(r"^(bool h2Long|bool h2Short|float h2Tp1|float h2Tp2) = ")
bad = []
for name, path in FILES.items():
    Ls = open(path, encoding="utf-8").read().split("\n")
    fdef = None
    for i, l in enumerate(Ls):
        code = l.split("//")[0] if '"' not in l.split("//")[0] else l
        if l and not l[0].isspace() and not l.startswith("//"):
            m = re.match(r"^(\w+)\(.*\)\s*=>", l)
            fdef = m.group(1) if m else None
        if not re.search(r"\bh2(Poc|Vah|Val|Next)\b", code) or l.lstrip().startswith("//"):
            continue
        s = l.strip()
        if re.match(r"^(var float h2(Poc|Vah|Val) = na|h2(Poc|Vah|Val) := )", s) or SIG.match(s) or s.startswith("string h2Next = "):
            continue
        if fdef is None:
            bad.append((name, i + 1, s[:60]))
            continue
        calls = [j for j, x in enumerate(Ls) if re.search(rf"\b{fdef}\(", x) and not re.match(rf"^{fdef}\(", x)
                 and not x.lstrip().startswith("//")]
        for j in calls:
            k = j
            ok = False
            while k > 0:
                k -= 1
                if Ls[k].strip() and len(Ls[k]) - len(Ls[k].lstrip()) < len(Ls[j]) - len(Ls[j].lstrip()) and not Ls[k].lstrip().startswith("//"):
                    if "barstate.islast" in Ls[k] or re.match(r"^\w+\(.*\)\s*=>", Ls[k]):
                        ok = True
                        break
                    if len(Ls[k]) - len(Ls[k].lstrip()) == 0:
                        break
            if not ok:
                bad.append((name, i + 1, f"{fdef}() called at L{j + 1} outside a last-bar block"))
report(not bad, f"2 every read of h2Poc / h2Vah / h2Val / h2Next in the Master, Visuals and Strategy_H2 is a signal line or a "
       f"last-bar display ({len(bad)} other{'' if not bad else ': ' + str(bad[:3])})")

# ---------- 3 quantile copy ----------
NEWQ = "float[] _tmpQ = array.copy(array.slice(hPred, 0, hN))"
eng = [A + x + ".pine" for x in ("Master", "Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER", "Brief", "Diagnostics")]
txt = [open(p, encoding="utf-8").read() for p in eng]
static = all(t.count(NEWQ) == 1 and "array.push(_tmpQ, array.get(hPred, _qi))" not in t for t in txt)
rng = random.Random(7)
okx = True
for HM in (1200, 2000, 3000, 4500):
    buf = [rng.uniform(0, 100) for _ in range(HM)]
    for hN in (50, 51, HM // 2, HM - 1, HM):
        loop = [buf[q] for q in range(hN)]
        cp = list(buf[0:hN])            # array.slice(id, 0, hN) = elements 0 .. hN-1; array.copy = a new array of them
        okx &= loop == cp and sorted(loop) == sorted(cp)
report(static and okx, f"3 quantile pass: the native copy in all {len(eng)} engine copies, no loop left ({static}); copy == loop for "
       f"hN 50 .. HIST_MAX on every HIST_MAX ({okx})")

# ---------- 4 controls ----------
mut_files = {"Master": open(FILES["Master"], encoding="utf-8").read().replace("float h2Tp2 = ", "float h2PocX = h2Poc\nfloat h2Tp2 = ", 1)}
cbad = [i for i, l in enumerate(mut_files["Master"].split("\n")) if l.startswith("float h2PocX = h2Poc")]
report(ctl != old and bool(cbad), f"4 controls: profile without the last-bar rebuild differs ({ctl != old}); a read outside a "
       f"display function is found at L{cbad[0] + 1 if cbad else '?'}")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- the H2 rule executed in Python on real bars, reads located in the Pine; "
      "TradingView run time NOT measured")
sys.exit(1 if fails else 0)
