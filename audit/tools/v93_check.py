#!/usr/bin/env python3
"""v93 BRACKET TRACKER (Visuals, display only), EXECUTED as written (pine_exec).

1 units: the SL / TP price distances from Visuals' own lines: $500 / $1000 at 0.5 lot (pointValue 100) = $10 / $20;
  500 / 1000 MT5 points at 0.01 = $5 / $10
2 the race, bar by bar on random price paths with random H2 signals, vs an independent Python reference of the rule
  in the comment: entry at the signal bar's close, scored from the NEXT bar, SL first on a bar touching both, every
  signal counted, net $ = wins x (TP - cost) - losses x (SL + cost) at the lot, cost at the bar the race resolved
3 the real data: Visuals' block run on the website's XAU 5m bars (market-data, 2026-09-09 .. 10-31) with the forward
  record's H3 5m signals (H3 = the H2 rule) as the triggers, $500 / $1000 at 0.5 lot: the tracker must report what an
  independent count of the same trades reports (the audit measured 8 / 14 TP first)
4 the row: the BRACKET text has no NaN with zero closed signals (v86_check 8 executes it with missing data too) and its
  colour is UP only when the 95% lower bound is above break-even, DOWN only when the upper bound is below it
5 Visuals == fix_v93.visuals(v92), byte for byte
Usage: python3 audit/tools/v93_check.py"""
import bisect, csv, io, json, os, random, subprocess, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

P.BUILTINS.setdefault("array.remove", lambda a, i: a.pop(int(i)))
P.BUILTINS.setdefault("array.new_int", lambda n=0, v=0: [v] * int(n))
VL = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg)
    fails += not ok


def line(prefix):
    return next(l.strip() for l in VL if l.strip().startswith(prefix))


a = next(i for i, l in enumerate(VL) if l.startswith("if trkShow and barstate.isconfirmed"))
b = next(i for i in range(a, len(VL)) if VL[i].strip().startswith("array.push(trkDir, h2Long ? 1 : -1)"))
RACE = [l.replace("barstate.isconfirmed", "isConf") for l in VL[a:b + 1] if l.strip() and not l.strip().startswith("//")]
DIST = [line("float trkSLd = "), line("float trkTPd = ")]

# ---- 1
def dists(unit, sl, tp, lot, pt=0.01):
    e = P.Env(trkUnit=unit, trkSL=sl, trkTP=tp, trkLot=lot, trkPt=pt, pointValue=100.0)
    P.run(DIST, e)
    return e["trkSLd"], e["trkTPd"]
m = dists("Money ($)", 500.0, 1000.0, 0.5)
pt = dists("MT5 points", 500.0, 1000.0, 0.5)
report(abs(m[0] - 10) < 1e-12 and abs(m[1] - 20) < 1e-12 and abs(pt[0] - 5) < 1e-12 and abs(pt[1] - 10) < 1e-12,
       f"1 units: $500 / $1000 at 0.5 lot = ${m[0]:.2f} / ${m[1]:.2f} of price; 500 / 1000 MT5 points = ${pt[0]:.2f} / ${pt[1]:.2f}")


def run_pine(bars, sigs, sld, tpd, lot, costs):
    env = P.Env(trkShow=True, isConf=True, trkSLd=sld, trkTPd=tpd, trkLot=lot, pointValue=100.0,
                trkE=[], trkDir=[], trkW=0.0, trkL=0.0, trkNet=0.0)
    for i, (h, l, c) in enumerate(bars):
        s = sigs.get(i, 0)
        env.update(high=h, low=l, close=c, h2Long=s > 0, h2Short=s < 0, ckCost=costs[i])
        P.run(RACE, env)
    return env


def run_ref(bars, sigs, sld, tpd, lot, costs):
    w = lo = 0
    net = 0.0
    for i, s in sigs.items():
        e = bars[i][2]
        for j in range(i + 1, len(bars)):
            h, l, _ = bars[j]
            hit_sl = l <= e - sld if s > 0 else h >= e + sld
            hit_tp = h >= e + tpd if s > 0 else l <= e - tpd
            if hit_sl:
                lo += 1; net -= (sld + costs[j]) * lot * 100.0; break
            if hit_tp:
                w += 1; net += (tpd - costs[j]) * lot * 100.0; break
    return w, lo, net

# ---- 2
rng = random.Random(93)
bad2 = runs = 0
for _ in range(300):
    n = rng.randint(30, 400)
    px, bars = 2000.0, []
    for _k in range(n):
        o = px; px += rng.gauss(0, 3)
        bars.append((max(o, px) + abs(rng.gauss(0, 2)), min(o, px) - abs(rng.gauss(0, 2)), px))
    sigs = {i: rng.choice([1, -1]) for i in range(n) if rng.random() < 0.08}
    sld, tpd = rng.choice([(10.0, 20.0), (5.0, 10.0), (rng.uniform(1, 15), rng.uniform(1, 30))])
    costs = [rng.choice([0.77, 0.97, 2.17]) for _k in range(n)]
    e = run_pine(bars, sigs, sld, tpd, 0.5, costs)
    w, lo, net = run_ref(bars, sigs, sld, tpd, 0.5, costs)
    runs += 1
    bad2 += int(e["trkW"]) != w or int(e["trkL"]) != lo or abs(e["trkNet"] - net) > 1e-6
report(bad2 == 0, f"2 race: Visuals' tracker block vs an independent reference, {runs} random paths (random signals both ways, "
       f"brackets incl. $10 / $20 and $5 / $10, varying cost): mismatches {bad2}")

# ---- 3
rows = {}
for f in subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/market-data"], capture_output=True, text=True).stdout.split():
    if f.startswith("XAU_USD_5m/"):
        for r in csv.DictReader(io.StringIO(subprocess.run(["git", "show", "origin/market-data:" + f], capture_output=True, text=True).stdout)):
            rows[r["datetime"]] = (float(r["high"]), float(r["low"]), float(r["close"]))
if not rows:
    print("NOT RUN  3 real data: market-data branch not reachable")
else:
    K = sorted(rows); T = [datetime.fromisoformat(k) for k in K]; B = [rows[k] for k in K]
    led = json.loads(subprocess.run(["git", "show", "origin/forward-ledger:holdout/5m_h3.json"], capture_output=True, text=True, check=True).stdout)
    sigs = {}
    for x in led:
        if isinstance(x, dict) and not x.get("open"):
            et = datetime.fromisoformat(x["entry_time"].replace("Z", "+00:00")); i = bisect.bisect_left(T, et)
            if i < len(T) and abs((T[i] - et).total_seconds()) <= 900:
                sigs[i] = 1 if x["dir"] in ("LONG", "long", "BUY", 1) else -1
                B[i] = (B[i][0], B[i][1], x["entry"])          # the race starts at the record's entry price
    costs = [0.77] * len(B)
    e = run_pine(B, sigs, 10.0, 20.0, 0.5, costs)
    w, lo, net = run_ref(B, sigs, 10.0, 20.0, 0.5, costs)
    report(int(e["trkW"]) == w and int(e["trkL"]) == lo and w + lo > 0,
           f"3 real data: the tracker on XAU 5m with the forward record's {len(sigs)} H3 5m signals, $500 / $1000 at 0.5 lot: "
           f"TP first {int(e['trkW'])} / {int(e['trkW'] + e['trkL'])}, net ${e['trkNet']:+,.0f} (reference {w} / {w + lo}); "
           f"open {len(e['trkE'])}")

# ---- 4
DER = [line(p) for p in ("int trkN = ", "float trkBE = ", "[trkLo, trkHi] = ", "float trkEqPct = ", "int trkLv = ", "string trkTxt = ")]
env = P.Env()
fl = [l for l in VL]
fa = next(i for i, l in enumerate(fl) if l.startswith("f_wil(float k, int n) =>"))
fb = next(i for i in range(fa + 1, len(fl)) if fl[i] and not fl[i].startswith(" "))
P.define([l for l in fl[fa:fb] if l.strip()], env)
bad4 = 0
for _ in range(3000):
    st = dict(trkW=float(rng.choice([0, 1, 5, 40])), trkL=float(rng.choice([0, 2, 9, 60])), trkNet=rng.uniform(-9e3, 9e3),
              trkSLd=rng.choice([10.0, 5.0, 0.0001]), trkTPd=rng.choice([20.0, 10.0, 0.0001]), ckCost=rng.choice([0.77, 2.3]),
              trkLot=rng.choice([0.5, 0.01]), pointValue=100.0, rkEquity=rng.choice([25000.0, 100.0]), trkUnit=rng.choice(["Money ($)", "MT5 points"]),
              trkSL=500.0, trkTP=1000.0, trkE=[1.0] * rng.choice([0, 3]))
    e4 = P.Env(funcs=env.funcs, **st)
    P.run(DER, e4)
    txt, lv = e4["trkTxt"], e4["trkLv"]
    want = 0 if e4["trkN"] < 1 else 1 if e4["trkLo"] > e4["trkBE"] else -1 if e4["trkHi"] < e4["trkBE"] else 0
    bad4 += "NaN" in txt or lv != want
report(bad4 == 0, f"4 the BRACKET row: 3000 states incl. zero closed signals: no NaN, colour UP / DOWN only when the 95% range clears "
       f"break-even: mismatches {bad4}")
import fix_v93 as F93  # noqa: E402
v92v = subprocess.run(["git", "show", "8453d1373:artefacts/XAUUSD_Quantum_5_5_Visuals.pine"], capture_output=True, text=True, check=True).stdout
report(F93.visuals(v92v) == "\n".join(VL), "5 Visuals == fix_v93.visuals(v92 Visuals @ 8453d1373), byte for byte")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
