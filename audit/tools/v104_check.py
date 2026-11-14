#!/usr/bin/env python3
"""v104: the Master's H2 text re-wrapped into its DECISION footer (row 3 removed); the POC number shown once (Visuals).

  1 the Master's h2Plan / h2Last / h2Line run AS WRITTEN on worst-case states (BUY and SELL, 5-digit MT5 prices, MIXED,
    "none yet", the MT5 offset): at most 4 lines, each <= 32 characters (the v39 / v55 clip limit), every value present
    (trend, time, swept level, side, entry, SL, TP1, TP2), the POC number NOT repeated there
  2 the DECISION footer cell (8, 2) carries the footer + the H2 text in the H2 colour; no desktop cell writes row 3
  3 Visuals' strip cell under PRICE ("VALUE · POC") prints the POC number, executed, MT5 prices (_h2p), and no NaN
  4 controls: the v103 h2Line (6 lines, POC repeated) fails 1
Usage: python3 audit/tools/v104_check.py"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

M = open("artefacts/XAUUSD_Quantum_5_0_Master.pine", encoding="utf-8").read().split("\n")
V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def h2_lines(L):
    a = next(i for i, l in enumerate(L) if l.startswith("string h2Plan = "))
    b = next(i for i, l in enumerate(L) if l.startswith("string h2Line = "))
    return [l for l in L[a:b + 1] if l.strip() and not l.lstrip().startswith("//")]


P.BUILTINS["str.format_time"] = lambda t, f, z: "11-12 18:30"


def run(lines, st):
    first = [l[4:] if l.startswith("var ") else l for l in lines]
    e = P.Env(**st)
    P.run(first, e)
    return e["h2Line"]


def check(lines):
    bad, n = [], 0
    for side in ("BUY", "SELL", None):
        for trend in ((True, False), (False, True), (False, False)):
            for px in (3884.01, 10123.45):
                st = dict(h2Long=side == "BUY", h2Short=side == "SELL", close=px, mt5Offset=0.37, h2Sl=px + 5.07,
                          h2Tp1=px - 10.2, h2Tp2=px - 25.64, h2SweptLvl=px + 0.77, time=0.0, h2TrendUp=trend[0],
                          h2TrendDn=trend[1], h2Poc=px - 1.79)
                txt = run(lines, st)
                n += 1
                rows = txt.split("\n")
                need = ["H2 ", "last "] + ([side, "entry ", "SL ", "TP1 ", "TP2 ", "swept "] if side else ["none yet"])
                poc = P._tostr(px - 1.79 + 0.37, "#.##")
                if len(rows) > 4 or max(len(r) for r in rows) > 32 or any(k not in txt for k in need) or poc in txt:
                    bad.append((side, trend, px, rows))
    return n, bad


n, bad = check(h2_lines(M))
report(not bad, f"1 the Master's H2 text, executed on {n} worst-case states: <= 4 lines of <= 32 characters, every value "
       "present, the POC number not repeated" + ("" if not bad else f"; e.g. {bad[:1]}"))

cell = [l.strip() for l in M if l.strip().startswith("tcb(8, 2, ")]
row3 = [l.strip() for l in M if re.match(r"^\s*tcb\(\d, 3, ", l)]
report(cell == ['tcb(8, 2, _decFoot + "\\n" + h2Line, h2Long ? cBloomBull : h2Short ? cBloomBear : C_TEXT, _cn, _seSize, _w8)'] and not row3,
       f"2 DECISION footer cell = footer + H2 text in the H2 colour; desktop cells in row 3: {len(row3)}")

tile = next(l.strip() for l in V if l.strip().startswith('f_tk(1, 5, "VALUE · POC", '))
val = P.split_args(tile[5:-1])[3] if hasattr(P, "split_args") else None
if val is None:
    i = tile.index('na(h2Poc) ? "building"')
    j = tile.index(", na(h2Poc) ? _tmV")
    val = tile[i:j]
env = P.Env(h2Mt5=0.37)                 # _h2p reads h2Mt5 from its defining scope
P.define(["_h2p(float _x) => na(_x) ? \"—\" : str.tostring(_x + h2Mt5, \"#.##\")"], env)
okv, nanv = True, False
for poc, c, vl, vh in ((3882.22, 3880.0, 3870.0, 3895.0), (3882.22, 3900.0, 3870.0, 3895.0), (P.NA, 3880.0, P.NA, P.NA),
                       (3882.22, 3884.0, 3870.0, 3895.0), (3882.22, 3860.0, 3870.0, 3895.0)):
    e = P.Env(funcs=env.funcs, h2Poc=poc, close=c, h2Val=vl, h2Vah=vh, h2Mt5=0.37)
    out = P.evaluate(val, e)
    nanv |= "NaN" in out
    if not P.isna(poc):
        okv &= P._tostr(poc + 0.37, "#.##") in out
report(okv and not nanv, "3 Visuals' strip cell under PRICE prints the POC number (MT5 price), executed on 5 states incl. no profile; no NaN")

old = subprocess.run(["git", "show", "2801317ff:artefacts/XAUUSD_Quantum_5_0_Master.pine"], capture_output=True, text=True, check=True).stdout.split("\n")
_, bad_old = check(h2_lines(old))
report(bool(bad_old), f"4 control: the v103 H2 text fails rule 1 ({len(bad_old)} states: 6 lines, POC repeated)")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text executed in Python; TradingView rendering NOT checked")
sys.exit(1 if fails else 0)
