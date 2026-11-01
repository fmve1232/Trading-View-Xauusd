#!/usr/bin/env python3
"""v94 LINK (Master -> Visuals, operator 2026-10-31 "Allow the link"), EXECUTED as written (pine_exec).

1 the Master's published series: its plot expression executed in every DECISION state: +plan SL on BUY, -plan SL on
  SELL, 0 on WAIT / NO TRADE / RISK LOCK / WARMUP; the plan is long exactly when shouldBuy (tpIsLong line, executed),
  so the sign and the stop's side agree
2 the Master's identical-output rewrites: nz(x, 50) == (na(x) ? 50 : x) incl. na; f_dashRender differs from v93 only by
  `color _cn = color(na)` and color(na) -> _cn (15 arguments); Master == fix_v94.master(v93 Master), byte for byte
3 Visuals' link decoding, bar by bar: an unlinked source (`close`, > 0 every bar) never switches the link on and the
  tracker keeps scoring H2; a linked series (0 on WAIT bars) switches it on at the first 0; a trigger fires only on the
  bar the DECISION changes to BUY or SELL (a run of BUY bars is ONE trigger, a BUY -> SELL flip is a new one);
  lkSLp = |series| while a DECISION is live
4 end to end: a random Master DECISION sequence -> the Master's plot -> Visuals' decoding -> Visuals' tracker block, on
  random prices with the operator's $10 / $20 bracket, vs an independent reference that races each DECISION change
5 Visuals == fix_v94.visuals(v93 Visuals), byte for byte; 4c a positive control (the stop / lots text: v86_check 7 / 8 execute it)
Lines are executed as written except `nz(lkD[1])`, read as the harness's previous-bar value (pine_exec has no
history operator for a scalar defined on the same bar); `barstate.isconfirmed` is true on every bar here.
Usage: python3 audit/tools/v94_check.py"""
import os, random, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402
import fix_v94 as F94  # noqa: E402

P.BUILTINS.setdefault("array.remove", lambda a, i: a.pop(int(i)))
P.BUILTINS.setdefault("array.new_int", lambda n=0, v=0: [v] * int(n))
M, V, V93 = "artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_5_Visuals.pine", "ee6085672"
ML = open(M, encoding="utf-8").read().split("\n")
VL = open(V, encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg)
    fails += not ok


plot_e = next(l for l in ML if l.startswith('plot(_confDirLabel == "BUY"')).split("(", 1)[1].rsplit(", \"LINK", 1)[0]
islong = next(l.strip() for l in ML if l.strip().startswith("bool tpIsLong = ")).split("=", 1)[1].strip()
rng = random.Random(94)
# ---- 1
bad1 = 0
for lab in ("BUY", "SELL", "WAIT", "NO TRADE", "RISK LOCK", "WARMUP"):
    for sl in (1990.5, P.NA):
        v = P.evaluate(plot_e, P.Env(_confDirLabel=lab, tpSL=sl))
        want = (sl if lab == "BUY" else -sl if lab == "SELL" else 0.0) if not (P.isna(sl) and lab in ("BUY", "SELL")) else P.NA
        bad1 += not ((P.isna(v) and P.isna(want)) or v == want)
side = all(P.evaluate(islong, P.Env(shouldBuy=b, shouldSell=s_, bullScore=40.0, bearScore=60.0)) == (True if b else False if s_ else False)
           for b, s_ in ((True, False), (False, True), (False, False)))
report(bad1 == 0 and side, f"1 the Master's LINK series: +SL on BUY, -SL on SELL, 0 otherwise (na stop -> na) in all 6 DECISION states: "
       f"mismatches {bad1}; plan long exactly when shouldBuy: {side}")

# ---- 2
v93m = subprocess.run(["git", "show", f"{V93}:{M}"], capture_output=True, text=True, check=True).stdout
bad2 = sum(not ((P.isna(x) and P.isna(y)) or x == y)
           for x, y in ((P.evaluate("nz(a, 50)", P.Env(a=a)), P.evaluate("na(a) ? 50 : a", P.Env(a=a))) for a in (P.NA, 0.0, 49.5, 100.0)))
def fbody(t):
    L = t.split("\n"); a = next(i for i, l in enumerate(L) if l.startswith("f_dashRender() =>")); b = a + 1
    while b < len(L) and (L[b].startswith(" ") or not L[b].strip()):
        b += 1
    return L[a:b]
old, new = fbody(v93m), [l for l in fbody("\n".join(ML)) if "color _cn = color(na)" not in l and "v94: one transparent colour" not in l]
NZ = (("na(avgCorrHealth) ? 50 : avgCorrHealth", "nz(avgCorrHealth, 50)"), ("na(liqReachScore) ? 50 : liqReachScore", "nz(liqReachScore, 50)"))
def _v94(o):
    o = o.replace("color(na)", "_cn")
    for x, y in NZ:
        o = o.replace(x, y)
    return o
same = len(old) == len(new) and all(_v94(o) == n for o, n in zip(old, new))
report(bad2 == 0 and same and F94.master(v93m) == "\n".join(ML),
       f"2 the Master's rewrites: nz(x, 50) == na(x) ? 50 : x (na incl.): mismatches {bad2}; f_dashRender == v93 with color(na) -> _cn and the 2 nz rewrites, nothing else: {same}; "
       "Master == fix_v94.master(v93 @ ee6085672), byte for byte")

# ---- 3 / 4
DEC = [l.strip().replace("nz(lkD[1])", "lkDprev").replace("barstate.isconfirmed", "isConf") for l in VL
       if l.strip().startswith(("int lkD = ", "float lkSLp = ", "bool lkTrig = ", "bool trkLongSig = ", "bool trkShortSig = "))]
ON = ["if not lkOn and lkDec == 0", "    lkOn := true"]
a = next(i for i, l in enumerate(VL) if l.startswith("if trkShow and barstate.isconfirmed"))
b = next(i for i in range(a, len(VL)) if VL[i].strip().startswith("array.push(trkDir, trkLongSig ? 1 : -1)"))
RACE = [l.replace("barstate.isconfirmed", "isConf") for l in VL[a:b + 1] if l.strip() and not l.strip().startswith("//")]
assert len(DEC) == 5 and all(any(x.strip() == l.strip() for l in VL) for x in ON)


def visuals_run(series, bars, h2, sld=10.0, tpd=20.0):
    env = P.Env(lkOn=False, isConf=True, trkShow=True, trkSLd=sld, trkTPd=tpd, trkLot=0.5, pointValue=100.0, ckCost=0.77,
                trkE=[], trkDir=[], trkW=0.0, trkL=0.0, trkNet=0.0)
    prev, trig, slp = 0, [], []
    for i, ((h, l, c), v) in enumerate(zip(bars, series)):
        env.update(lkDec=v, lkDprev=prev, close=c, high=h, low=l, h2Long=h2.get(i, 0) > 0, h2Short=h2.get(i, 0) < 0)
        P.run(ON + DEC, env)
        P.run(RACE, env)
        prev = int(env["lkD"])
        trig.append(1 if env["trkLongSig"] else -1 if env["trkShortSig"] else 0)
        slp.append(env["lkSLp"])
    return env, trig, slp


def path(n):
    px, out = 2000.0, []
    for _ in range(n):
        o = px; px += rng.gauss(0, 3)
        out.append((max(o, px) + abs(rng.gauss(0, 2)), min(o, px) - abs(rng.gauss(0, 2)), px))
    return out


bad3 = 0
for _ in range(200):
    n = rng.randint(20, 200); bars = path(n)
    h2 = {i: rng.choice([1, -1]) for i in range(n) if rng.random() < .1}
    e, trig, _s = visuals_run([c for _h, _l, c in bars], bars, h2)                     # unlinked: the source is close
    bad3 += e["lkOn"] or trig != [h2.get(i, 0) for i in range(n)]
    labs, k = [], 0
    while len(labs) < n:
        lab = rng.choice(["WAIT", "BUY", "SELL", "NO TRADE"]); labs += [lab] * rng.randint(1, 6)
    labs = labs[:n]
    ser = [P.evaluate(plot_e, P.Env(_confDirLabel=lab, tpSL=c - 5.0 if lab == "BUY" else c + 5.0)) for lab, (_h, _l, c) in zip(labs, bars)]
    e, trig, slp = visuals_run(ser, bars, h2)
    want = [0] * n
    first0 = next((i for i, v in enumerate(ser) if v == 0), n)
    for i in range(n):
        d = 1 if labs[i] == "BUY" else -1 if labs[i] == "SELL" else 0
        dp = 0 if i == 0 else (1 if labs[i - 1] == "BUY" else -1 if labs[i - 1] == "SELL" else 0)
        on = i >= first0
        if not on:
            want[i] = h2.get(i, 0)
        elif d != 0 and (d != dp or i - 1 < first0):
            want[i] = d
    slok = all((P.isna(s_) and labs[i] not in ("BUY", "SELL")) or (i < first0) or (abs(s_ - abs(ser[i])) < 1e-9) for i, s_ in enumerate(slp))
    bad3 += trig != want or not slok
report(bad3 == 0, f"3 Visuals' link decoding: 200 unlinked runs (source = close: the link stays off, the tracker scores H2) and 200 linked "
       f"runs (one trigger per DECISION change to BUY / SELL, flips counted, plan stop = |series|): mismatches {bad3}")

bad4 = 0
for _ in range(300):
    n = rng.randint(40, 300); bars = path(n)
    labs = []
    while len(labs) < n:
        labs += [rng.choice(["WAIT", "WAIT", "BUY", "SELL"])] * rng.randint(1, 8)
    labs = ["WAIT"] + labs[:n - 1]
    ser = [P.evaluate(plot_e, P.Env(_confDirLabel=lab, tpSL=c - 7.0 if lab == "BUY" else c + 7.0)) for lab, (_h, _l, c) in zip(labs, bars)]
    e, _t, _s = visuals_run(ser, bars, {})
    w = lo = 0
    for i in range(1, n):
        d = 1 if labs[i] == "BUY" else -1 if labs[i] == "SELL" else 0
        dp = 1 if labs[i - 1] == "BUY" else -1 if labs[i - 1] == "SELL" else 0
        if d == 0 or d == dp:
            continue
        ent = bars[i][2]
        for j in range(i + 1, n):
            h, l, _c = bars[j]
            if (l <= ent - 10 if d > 0 else h >= ent + 10):
                lo += 1; break
            if (h >= ent + 20 if d > 0 else l <= ent - 20):
                w += 1; break
    bad4 += int(e["trkW"]) != w or int(e["trkL"]) != lo
report(bad4 == 0, f"4 end to end: Master DECISION sequence -> its LINK series -> Visuals' decoding -> the tracker, 300 random runs, $10 / $20 "
       f"bracket, vs an independent race per DECISION change: mismatches {bad4}")

# positive control: a copy that triggers on EVERY BUY / SELL bar (no change test) must disagree with the reference
_dec_ok = DEC
DEC = [l.replace(" and lkD != lkDprev", "") for l in DEC]
assert DEC != _dec_ok
ctl = 0
for _ in range(60):
    n = rng.randint(40, 200); bars = path(n)
    labs = ["WAIT"] + [rng.choice(["WAIT", "BUY", "BUY", "SELL"]) for _k in range(n - 1)]
    ser = [P.evaluate(plot_e, P.Env(_confDirLabel=lab, tpSL=c - 7.0 if lab == "BUY" else c + 7.0)) for lab, (_h, _l, c) in zip(labs, bars)]
    e, trig, _s = visuals_run(ser, bars, {})
    chg = sum(1 for i in range(1, n) if labs[i] in ("BUY", "SELL") and labs[i] != labs[i - 1])
    ctl += sum(1 for t in trig if t) != chg
DEC = _dec_ok
report(ctl > 0, f"4c positive control: a copy that fires on every BUY / SELL bar is detected ({ctl} / 60 runs differ)")

v93v = subprocess.run(["git", "show", f"{V93}:{V}"], capture_output=True, text=True, check=True).stdout
report(F94.visuals(v93v) == "\n".join(VL), "5 Visuals == fix_v94.visuals(v93 @ ee6085672), byte for byte")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text executed in Python; TradingView runtime (input.source wiring) NOT exercised")
sys.exit(1 if fails else 0)
