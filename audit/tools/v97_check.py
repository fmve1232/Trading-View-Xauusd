#!/usr/bin/env python3
"""v97: Visuals' BRACKET tracker with three targets on one stop and the website's B3 confirmation entry, EXECUTED as
written (pine_exec) against an independent reference.

1 defaults: SL $500 / TP1 $500 / TP2 $750 / TP3 $1,000 at 0.5 lot = -$10 / +$10 / +$15 / +$20 of price; confirmation
  $3 at $4,000 gold (scaled with the price, as B3) within 120 minutes (= B3's 2 hours)
2 the race on random price paths: each target scored on its own (touched before the stop; a bar touching both = the
  stop), a race ending at the stop or after all three; confirmation: the first later close at least trkCfD my way
  enters at that close, a close that far against or the end of the window cancels; vs an independent reference
2c positive control: a copy that ignores the "close against cancels" rule is detected
3 real data: the website's XAU 5m bars (market-data) with the forward record's Treatment 5m signals, the operator's
  bracket and B3's confirmation: the tracker's counts == the reference's
4 Visuals == fix_v97.visuals(v96 Visuals), byte for byte
NOT RUN: the chart. Usage: python3 audit/tools/v97_check.py"""
import bisect, csv, io, json, math, os, random, re, subprocess, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402
import fix_v97 as F97  # noqa: E402

P.BUILTINS.setdefault("array.remove", lambda a, i: a.pop(int(i)))
P.BUILTINS.setdefault("array.new_int", lambda n=0, v=0: [v] * int(n))
VF = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
VL = open(VF, encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg)
    fails += not ok


def default(name):
    m = re.search(rf"^{name} = input\.(?:float|int)\(([\d.]+),", "\n".join(VL), re.M)
    return float(m.group(1))
d = {k: default(k) for k in ("trkSL", "trkTP1", "trkTP2", "trkTP", "trkLot", "trkCf", "trkCfMin")}
dist = [d[k] / (d["trkLot"] * 100.0) for k in ("trkSL", "trkTP1", "trkTP2", "trkTP")]
report(dist == [10.0, 10.0, 15.0, 20.0] and d["trkCf"] == 3.0 and d["trkCfMin"] == 120.0,
       f"1 defaults: stop / TP1 / TP2 / TP3 = ${dist[0]:g} / ${dist[1]:g} / ${dist[2]:g} / ${dist[3]:g} of price at {d['trkLot']:g} lot; "
       f"confirmation ${d['trkCf']:g} within {d['trkCfMin']:g} min (B3: $3, 2 hours)")

a = next(i for i, l in enumerate(VL) if l.startswith("if trkShow and barstate.isconfirmed"))
b = next(i for i, l in enumerate(VL) if l.startswith("int trkN1 = "))
RACE = [l.replace("barstate.isconfirmed", "isConf") for l in VL[a:b] if l.strip() and not l.strip().startswith("//")]


def pine(bars, sigs, sl, tps, cfd, cfn, cost=0.77, race=RACE):
    env = P.Env(trkShow=True, isConf=True, trkSLd=sl, trkTP1d=tps[0], trkTP2d=tps[1], trkTPd=tps[2], trkLot=0.5, pointValue=100.0,
                trkCf=1.0 if cfd > 0 else 0.0, trkCfD=cfd, trkCfN=float(cfn), ckCost=cost,
                trkE=[], trkDir=[], trkH1=[], trkH2=[], trkH3=[], trkQe=[], trkQd=[], trkQb=[],
                trkW1=0.0, trkL1=0.0, trkNet1=0.0, trkW2=0.0, trkL2=0.0, trkNet2=0.0, trkW=0.0, trkL=0.0, trkNet=0.0)
    for i, (h, l, c) in enumerate(bars):
        s = sigs.get(i, 0)
        env.update(high=h, low=l, close=c, bar_index=float(i), trkLongSig=s > 0, trkShortSig=s < 0)
        P.run(race, env)
    return [(int(env[w]), int(env[x]), env[n]) for w, x, n in (("trkW1", "trkL1", "trkNet1"), ("trkW2", "trkL2", "trkNet2"), ("trkW", "trkL", "trkNet"))]


def ref(bars, sigs, sl, tps, cfd, cfn, cost=0.77):
    out = [[0, 0, 0.0] for _ in tps]
    for i, dd in sorted(sigs.items()):
        e, j0 = bars[i][2], i
        if cfd > 0:                                   # B3: a close cfd my way before one against, within cfn bars
            j0 = None
            for j in range(i + 1, min(i + cfn + 1, len(bars))):    # ages 1 .. cfn bars after the signal
                c = bars[j][2]
                if (c >= e + cfd) if dd > 0 else (c <= e - cfd):
                    j0, e = j, c
                    break
                if (c <= e - cfd) if dd > 0 else (c >= e + cfd):
                    break
            if j0 is None:
                continue
        hit = [False] * len(tps)
        for j in range(j0 + 1, len(bars)):
            h, l, _c = bars[j]
            if (l <= e - sl) if dd > 0 else (h >= e + sl):
                for k in range(len(tps)):
                    if not hit[k]:
                        out[k][1] += 1; out[k][2] -= (sl + cost) * 50.0
                break
            for k, tp in enumerate(tps):
                if not hit[k] and ((h >= e + tp) if dd > 0 else (l <= e - tp)):
                    hit[k] = True; out[k][0] += 1; out[k][2] += (tp - cost) * 50.0
            if all(hit):
                break
    return [tuple(x) for x in out]


def same(p_, r_):
    return all(a_[0] == b_[0] and a_[1] == b_[1] and abs(a_[2] - b_[2]) < 1e-6 for a_, b_ in zip(p_, r_))


rng = random.Random(97)
def path(n):
    px, out = 2000.0, []
    for _ in range(n):
        o = px; px += rng.gauss(0, 3)
        out.append((max(o, px) + abs(rng.gauss(0, 2)), min(o, px) - abs(rng.gauss(0, 2)), px))
    return out
bad2 = runs = 0
for _ in range(250):
    n = rng.randint(30, 300); bars = path(n)
    sigs = {i: rng.choice([1, -1]) for i in range(n) if rng.random() < .06}
    tps = rng.choice([(10.0, 15.0, 20.0), (5.0, 10.0, 15.0), (20.0, 10.0, 15.0)])
    cfd, cfn = rng.choice([(0.0, 24), (3.0, 24), (3.0, 8), (6.0, 30)])
    bad2 += not same(pine(bars, sigs, 10.0, tps, cfd, cfn), ref(bars, sigs, 10.0, tps, cfd, cfn)); runs += 1
report(bad2 == 0, f"2 race: three targets + confirmation, {runs} random paths (targets in and out of order, confirmation off / $3 / $6, "
       f"windows 8-30 bars) vs an independent reference: mismatches {bad2}")
MUT = [l.replace("bool _qno = (_qd > 0 ? close <= _qe - trkCfD : close >= _qe + trkCfD) or ", "bool _qno = ") for l in RACE]
assert MUT != RACE
ctl = sum(not same(pine(b_, s_, 10.0, (10.0, 15.0, 20.0), 3.0, 24, race=MUT), ref(b_, s_, 10.0, (10.0, 15.0, 20.0), 3.0, 24))
          for b_, s_ in ((bb, {i: rng.choice([1, -1]) for i in range(len(bb)) if rng.random() < .08}) for bb in (path(250) for _ in range(40))))
report(ctl > 0, f"2c positive control: a copy without B3's 'a close against cancels' rule is detected in {ctl} / 40 runs")

rows = {}
for f in subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/market-data"], capture_output=True, text=True).stdout.split():
    if f.startswith("XAU_USD_5m/"):
        for r in csv.DictReader(io.StringIO(subprocess.run(["git", "show", "origin/market-data:" + f], capture_output=True, text=True).stdout)):
            rows[r["datetime"]] = (float(r["high"]), float(r["low"]), float(r["close"]))
if not rows:
    print("NOT RUN  3 real data: market-data not reachable")
else:
    K = sorted(rows); T = [datetime.fromisoformat(k) for k in K]; B = [rows[k] for k in K]
    led = json.loads(subprocess.run(["git", "show", "origin/forward-ledger:holdout/5m_treatment.json"], capture_output=True, text=True, check=True).stdout)
    sigs = {}
    for x in led:
        if isinstance(x, dict) and not x.get("open"):
            i = bisect.bisect_left(T, datetime.fromisoformat(x["entry_time"].replace("Z", "+00:00")))
            if i < len(T):
                sigs[i] = 1 if x["dir"] in ("LONG", "long", "BUY", 1) else -1
                B[i] = (B[i][0], B[i][1], x["entry"])
    cfd = 3.0 * B[-1][2] / 4000.0
    pp = pine(B, sigs, 10.0, (10.0, 15.0, 20.0), cfd, 24)
    rr = ref(B, sigs, 10.0, (10.0, 15.0, 20.0), cfd, 24)
    report(same(pp, rr) and sum(x[0] + x[1] for x in pp) > 0,
           f"3 real data: Treatment 5m's {len(sigs)} signals, -$10 stop, B3 confirmation (${cfd:.2f}, 2 h): tracker TP1 {pp[0][0]}/{pp[0][0] + pp[0][1]}, "
           f"TP2 {pp[1][0]}/{pp[1][0] + pp[1][1]}, TP3 {pp[2][0]}/{pp[2][0] + pp[2][1]} == the reference")

v96v = subprocess.run(["git", "show", "eb8e08269:" + VF], capture_output=True, text=True, check=True).stdout
report(F97.visuals(v96v) == "\n".join(VL), "4 Visuals == fix_v97.visuals(v96 @ eb8e08269), byte for byte")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
