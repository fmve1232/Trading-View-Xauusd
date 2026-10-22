#!/usr/bin/env python3
"""v86: the CHECKS & RISK additions (Visuals), the Master's SIGNAL-cell text and the EdgeCases timing, EXECUTED as written.

Each section runs the Pine lines out of the artefact with pine_exec against an independent reference:
   1 Wilson 95% interval (f_wil) and its text (f_ci) vs an independent implementation + known values
   2 Student-t 97.5% quantile (f_tq) vs exact table values; f_dur vs a reference
   3 cost: Visuals' copy (ckKZ / ckSpread / ckCost) == the Master's own lines (inKillzone, _sessSpread, the round-trip
     cost) EXECUTED side by side, every UTC hour x EU / US DST state x spread / slippage / commission inputs
   4 news calendar: the coded dates decode (Pine loop executed; timestamp() modelled with the IANA zone) to the
     official list typed here from the BLS / Federal Reserve schedules; NFP Friday, CPI 08:30, FOMC 14:00 Tue/Wed;
     DST-correct UTC times
   5 news window + alert, bar by bar on 5m / 15m / 1H / 4H / 1D bars: nwBarIn == "the bar touches ANY event's
     window" (brute force), exactly one alert per touched event
   6 session sample size: the SESSIntel block's body (the byte-locked Treatment function) and v86's outside counter
     run bar by bar on random session paths: ckN == the block's own _sessN on every bar
   7 daily regime, position size, daily cap and the forward-record verdict: executed vs references (incl. the
     pre-registered rule on the website ledger, recomputed from the ledger file when it is reachable)
   8 every new text (panel CHECKS rows, ticker tiles 6 / 7, banner) executed with missing data: no "NaN", all evaluate
   9 the Master's SIGNAL cell: old and new text executed; same numbers, no "%"; only that line and the stamp changed
  10 EdgeCases: assertions at bar 0, table on the last bar, every assertion a pure function of constants
Usage: python3 audit/tools/v86_check.py"""
import datetime as dt
import json
import math
import os
import random
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

VP = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
MP = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
EP = "artefacts/XAUUSD_Quantum_5_0_EdgeCases.pine"
V = open(VP, encoding="utf-8").read()
L = V.split("\n")
M = open(MP, encoding="utf-8").read()
ML = M.split("\n")
fails = 0
rng = random.Random(86)


def report(ok, msg):
    global fails
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    fails += not ok


def fnsrc(head, lines=L):
    a = next(i for i, l in enumerate(lines) if l.startswith(head))
    out = [lines[a]]
    for l in lines[a + 1:]:
        if l.startswith("    ") or not l.strip():
            out.append(l)
        else:
            break
    return [l for l in out if l.strip()]


def line(prefix, lines=L):
    hits = [l for l in lines if l.strip().startswith(prefix)]
    assert len(hits) == 1, (prefix, len(hits))
    return hits[0].strip()


def rhs(prefix, lines=L):
    return line(prefix, lines).split("=", 1)[1].strip()


env = P.Env()
for h in ("f_wil(float k, int n) =>", "f_ci(float pct, int n) =>", "f_tq(int df) =>", "f_dur(float ms) =>",
          "f_tmG(float d) =>", "f_tmC(float d) =>", "_h2p(float _x) =>", "f_sc(float x) =>"):
    P.define(fnsrc(h), env)
P.BUILTINS.setdefault("str.replace_all", lambda s_, a_, b_: s_.replace(a_, b_))
P.BUILTINS.setdefault("str.substring", lambda s_, a_, b_=None: s_[int(a_):] if b_ is None else s_[int(a_):int(b_)])
P.BUILTINS.setdefault("str.length", lambda s_: float(len(s_)))
P.BUILTINS.setdefault("str.startswith", lambda s_, p_: s_.startswith(p_))
P.BUILTINS.setdefault("array.set", lambda a_, i_, x_: a_.__setitem__(int(i_), x_))


def wilson(k, n, z=1.959964):
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z / den * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


# ---- 1 Wilson
bad = n1 = 0
for _ in range(4000):
    n = rng.choice([0, 1, 2, 5, 30, 65, 179, 1000, rng.randint(1, 500)])
    k = rng.randint(0, n) if n else 0
    got = P.evaluate(f"f_wil({float(k)!r}, {n})", P.Env(funcs=env.funcs))
    want = wilson(k, n)
    n1 += 1
    if n == 0:
        bad += not (P.isna(got[0]) and P.isna(got[1]))
    else:
        bad += abs(got[0] - want[0]) > 1e-12 or abs(got[1] - want[1]) > 1e-12 or not (got[0] - 1e-12 <= k / n <= got[1] + 1e-12)
known = P.evaluate("f_wil(22.0, 65)", P.Env(funcs=env.funcs))      # the H4 15m record: 33.8%, Wilson 23.5-46.0% (Phase 1 report)
txt = P.evaluate("f_ci(33.85, 65)", P.Env(funcs=env.funcs))
nat = P.evaluate("f_ci(na, 65)", P.Env(funcs=env.funcs)) == "" and P.evaluate("f_ci(40.0, 0)", P.Env(funcs=env.funcs)) == ""
report(bad == 0 and abs(known[0] - 0.23534) < 1e-4 and abs(known[1] - 0.45962) < 1e-4 and txt == " (24–46) n65" and nat,
       f"1 Wilson 95% (f_wil) vs an independent implementation: {n1} cases, mismatches {bad}; 22/65 -> "
       f"{known[0]:.4f}-{known[1]:.4f} (by hand 0.2353-0.4596); f_ci text '{txt}'; na / n = 0 -> ''")

# ---- 2 t quantile and duration
TQ = {10: 2.228139, 20: 2.085963, 29: 2.045230, 49: 2.009575, 64: 1.997730, 100: 1.983972, 178: 1.973381, 1000: 1.962339}
worst = max(abs(P.evaluate(f"f_tq({d})", P.Env(funcs=env.funcs)) - q) for d, q in TQ.items())


def dur(ms):
    if P.isna(ms):
        return "—"
    m = max(ms, 0) / 60000
    if m >= 1440:
        return f"{math.floor(m / 1440)}d {math.floor(m % 1440 / 60)}h"
    if m >= 60:
        return f"{math.floor(m / 60)}h {math.floor(m % 60):02d}m"
    return f"{math.floor(m)}m"


bd = sum(P.evaluate(f"f_dur({'na' if P.isna(x) else repr(x)})", P.Env(funcs=env.funcs)) != dur(x)
         for x in [P.NA, 0.0, -5.0, 59999.0, 60000.0, 3599999.0, 3600000.0, 3660000.0, 86399999.0, 86400000.0, 1e9]
         + [rng.uniform(0, 4e9) for _ in range(3000)])
report(worst < 2e-4 and bd == 0, f"2 Student-t 97.5% (f_tq) vs exact quantiles, df 10..1000: worst |error| {worst:.6f} "
       f"(< 0.0002); f_dur vs reference: 3011 cases (na -> —), mismatches {bd}")

# ---- 3 cost: Visuals' copy == the Master's lines, both executed
mk = ML.index(next(l for l in ML if l.startswith("int effLondonOpen = euIsDST ? 7 : 8")))
m_kz = ML[mk:mk + 6]
assert m_kz[-1].startswith("inKillzone = ")
m_spread = line("float _sessSpread = ", ML)
m_cost = next(l.strip() for l in ML if l.strip().startswith("float _costPts = (_sessSpread + 2.0 * slippagePts)"))
m_ses = [line("int londonClose = ", ML), line("int nyOpen = ", ML), line("inLondon = ", ML), line("inNY = ", ML)]
v_ses = [line("int londonClose = euIsDST"), line("int nyOpen      = usIsDST"), line("int nyClose     = usIsDST"), line("bool inLondon = "), line("bool inNY     = ")]
v_lines = [line("int ckLo = "), line("bool ckKZ = "), line("float ckSpread = "), line("float ckCost = ")]
bad3 = n3 = 0
for hh in range(24):
    for eu in (False, True):
        for us in (False, True):
            for sc, sl, cm, pv in ((0.3, 0.2, 7.0, 100.0), (0.1, 0.0, 0.0, 100.0), (0.6, 0.5, 12.0, 50.0), (0.2, 0.1, 3.5, 1.0)):
                base = dict(euIsDST=eu, usIsDST=us, spreadCost=sc, slippagePts=sl, commissionL=cm, pointValue=pv,
                            londonOpen=7.0)
                em = P.Env(hourUTC=float(hh), **base)
                P.run(["int londonOpen = 7"] + m_ses + m_kz + [m_spread, m_cost], em)
                ev = P.Env(hU=float(hh), **base)
                P.run(["int londonOpen  = 7"] + v_ses + v_lines, ev)
                n3 += 1
                bad3 += bool(em["inKillzone"]) != bool(ev["ckKZ"]) or abs(em["_sessSpread"] - ev["ckSpread"]) > 1e-12 \
                    or abs(em["_costPts"] - ev["ckCost"]) > 1e-12
lv = rhs("int ckCostLv")
lv_ok = all(P.evaluate(lv, P.Env(ckCostPct=x)) == w for x, w in ((P.NA, 0), (10.0, 0), (15.0, 0), (15.01, 1), (25.0, 1), (25.01, 2)))
report(bad3 == 0 and lv_ok, f"3 cost: Visuals' ckKZ / ckSpread / ckCost == the Master's inKillzone / _sessSpread / round-trip "
       f"cost, both executed: {n3} cases (24 h x EU / US DST x 4 input sets), mismatches {bad3}; levels >15% / >25%")

# ---- 4 calendar: the official list (BLS Employment Situation + CPI schedules, Federal Reserve FOMC 2026 / 2027
# calendars, as published on 2026-10-22). Statement days only (2nd day of each FOMC meeting).
OFFICIAL = {
    "NFP": ["2026-11-06", "2026-12-04", "2027-01-08", "2027-02-05", "2027-03-05", "2027-04-02", "2027-05-07", "2027-06-04",
            "2027-07-02", "2027-08-06", "2027-09-03", "2027-10-08", "2027-11-05", "2027-12-03"],
    "CPI": ["2026-11-10", "2026-12-10", "2027-01-13", "2027-02-11", "2027-03-10", "2027-04-13", "2027-05-12", "2027-06-10",
            "2027-07-14", "2027-08-11", "2027-09-14", "2027-10-14", "2027-11-10", "2027-12-10"],
    "FOMC": ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15",
             "2027-10-27", "2027-12-08"],
}
NY, UTC = ZoneInfo("America/New_York"), dt.timezone.utc


def ts(tz, y, mo, d, h, mi):
    return float(dt.datetime(int(y), int(mo), int(d), int(h), int(mi), tzinfo=ZoneInfo(tz)).timestamp() * 1000)


P.BUILTINS["timestamp"] = ts
codes = [l for l in L if l.startswith("var int[] nwCode = ") or l.startswith("var string[] nwName = ")
         or l.startswith("var int[] nwT = ")]
li = L.index("var int[] nwT = array.new_int()") + 1
loop = [L[li]] + [l for l in L[li + 1:li + 4] if l.startswith("    ")]   # the calendar loop
assert any("timestamp(" in l for l in loop), loop
e4 = P.Env(funcs=env.funcs, **{"barstate.isfirst": True})
P.BUILTINS.setdefault("array.new_int", lambda n=0, v=0: [v] * int(n))
P.run([l.replace("var ", "", 1) for l in codes] + loop, e4)
got = [(nm, dt.datetime.fromtimestamp(t / 1000, NY)) for nm, t in zip(e4["nwName"], e4["nwT"], strict=True)]
want = sorted((dt.datetime.strptime(d, "%Y-%m-%d").replace(hour=14 if nm == "FOMC" else 8, minute=0 if nm == "FOMC" else 30,
                                                             tzinfo=NY), nm) for nm, ds in OFFICIAL.items() for d in ds)
same = [(nm, t) for nm, t in got] == [(nm, t) for t, nm in want]
rules = all((nm == "NFP" and t.weekday() == 4 and (t.hour, t.minute) == (8, 30)) or (nm == "CPI" and (t.hour, t.minute) == (8, 30))
            or (nm == "FOMC" and t.weekday() in (1, 2) and (t.hour, t.minute) == (14, 0)) for nm, t in got)
order = all(a[1] < b[1] for a, b in zip(got, got[1:]))
utc = {(nm, t.date().isoformat()): t.astimezone(UTC).strftime("%H:%M") for nm, t in got}
dst_ok = utc[("FOMC", "2026-10-28")] == "18:00" and utc[("NFP", "2026-11-06")] == "13:30" and utc[("CPI", "2027-03-10")] == "13:30" \
    and utc[("FOMC", "2027-03-17")] == "18:00" and utc[("NFP", "2027-04-02")] == "12:30"     # US DST 2027: 03-14 .. 11-07
ends = got[-1][1].date().isoformat() == "2027-12-10" and "The list ends 2027-12-10" in V
report(same and rules and order and dst_ok and ends,
       f"4 calendar: {len(got)} coded events decode (Pine loop executed) to the official BLS / Fed list; NFP Fridays, CPI 08:30, "
       f"FOMC 14:00 Tue/Wed; in date order; DST-correct UTC (FOMC 10-28 18:00, NFP 11-06 13:30, CPI 2027-03-10 13:30 before "
       f"the 03-14 switch, FOMC 03-17 18:00 and NFP 04-02 12:30 after); "
       f"ends 2027-12-10 as the tooltip says")

# ---- 5 window + alert, bar by bar
a5 = L.index("var int nwI = 0")
b5 = next(i for i in range(a5, len(L)) if L[i].startswith("bgcolor(nwShade"))
step5 = [l for l in L[a5 + 1:b5] if l.strip()]
al = next(i for i, l in enumerate(L) if l.startswith("if alertOnNews and nwBarIn"))
cond5 = L[al][3:].strip()
bad5 = bars5 = alerts_bad = 0
for tfm in (5, 15, 60, 240, 1440):
    for before, after in ((30, 30), (0, 0), (120, 15)):
        e5 = P.Env(funcs=env.funcs, nwT=e4["nwT"], nwShow=True, nwBefore=float(before), nwAfter=float(after), nwI=0.0)
        hist_in, hist_i, fired = [], [], set()
        # bars from a day before to a day after each event (the gaps between are like weekend gaps on a chart: the
        # pointer catches up); bar opens aligned to the timeframe as on TradingView
        step = tfm * 60000.0
        opens = sorted({math.floor((ev - 86400000) / step) * step + j * step for ev in e4["nwT"]
                        for j in range(int(2 * 86400000 / step) + 2)})
        for t in opens:
            e5.update({"time": t, "time_close": t + tfm * 60000.0})
            P.run(step5, e5)
            ins = bool(e5["nwBarIn"])
            touch = [j for j, ev in enumerate(e4["nwT"]) if t <= ev + after * 60000 and t + tfm * 60000 > ev - before * 60000]
            bad5 += ins != bool(touch)
            hist_in.append(ins)
            hist_i.append(e5["nwI"])
            e5c = P.Env(funcs=env.funcs, alertOnNews=True, nwBarIn=ins, nwI=e5["nwI"])
            e5c["nwBarIn"] = P.Series(hist_in)
            e5c["nwI"] = P.Series(hist_i)
            if P._T(P.evaluate(cond5, e5c)):
                if int(e5["nwI"]) in fired:
                    alerts_bad += 1
                fired.add(int(e5["nwI"]))
            bars5 += 1
        touched = {j for j, ev in enumerate(e4["nwT"])}
        alerts_bad += fired != touched
report(bad5 == 0 and alerts_bad == 0, f"5 news window: nwBarIn == 'bar touches any event window' (brute force) on 5m / 15m / 1H / "
       f"4H / 1D bars x 3 window settings: {bars5} bars, mismatches {bad5}; exactly one alert per event: violations {alerts_bad}")

# ---- 6 session sample size: the SESSIntel body vs v86's counter, bar by bar
sa = L.index("f_sessionIntel() =>")
sb = next(i for i in range(sa, len(L)) if L[i].startswith("    [sessId, curSessId"))
body = [l[4:] for l in L[sa + 1:sb] if l.strip() and not l.strip().startswith("//")]
VARS6 = [l.replace("var ", "", 1) for l in body if l.startswith("var ")]
STEP6 = [l for l in body if not l.startswith("var ")]
cnt = [l for l in L if l.startswith("var int[] ckSessN")]
ci = next(i for i, l in enumerate(L) if l.startswith("if barstate.isconfirmed and not na(curSessId[1])"))
CNT = [L[ci], L[ci + 1]]
CKN = line("int ckN = ")
bad6 = n6 = 0
for trial in range(150):
    e6 = P.Env()
    P.run(VARS6, e6)
    ec = P.Env()
    P.run([cnt[0].replace("var ", "", 1)], ec)
    hc, hh_, cl = [], [], []
    px = 4100.0
    sess = rng.choice([0, 1, 2, 3])
    for k in range(rng.randint(60, 400)):
        if rng.random() < 0.12:
            sess = rng.choice([0, 1, 2, 3])
        o = px
        c = o + rng.gauss(0, 3)
        px = c
        cl.append(c)
        e6.update({"inAsian": sess == 0, "inLondon": sess == 1, "inNY": sess == 2, "open": o, "close": P.Series(cl),
                   "high": max(o, c) + abs(rng.gauss(0, 1)), "low": min(o, c) - abs(rng.gauss(0, 1)),
                   "barstate.isconfirmed": rng.random() < 0.9})
        P.run(STEP6, e6)
        hc.append(e6["curSessId"])
        hh_.append(e6["sesHi"])
        ec.update({"barstate.isconfirmed": e6["barstate.isconfirmed"], "curSessId": P.Series(hc), "sesHi": P.Series(hh_)})
        P.run(CNT, ec)
        ckn = P.evaluate(CKN.split("=", 1)[1], ec)
        n6 += 1
        bad6 += int(ckn) != int(e6["_sessN"])
report(bad6 == 0 and n6 > 10000, f"6 session n: the SESSIntel body (Treatment function, executed) and v86's outside counter, bar by "
       f"bar on 150 random session paths: {n6} bars, ckN != the block's _sessN on {bad6}")

# ---- 7 regime, risk, cap, verdict
rg = [line(p) for p in ("float rgRet12 = ", "bool rgUp = ", "bool rgDn = ", "float rgRyD = ", "float rgDxD = ", "int rgMac = ",
                        "string rgTxt = ", "string rgMacTxt = ")]
bad7 = 0
for _ in range(4000):
    na_ = lambda x: P.NA if rng.random() < 0.15 else x
    st = dict(rgM1=na_(rng.uniform(1500, 3000)), rgM13=na_(rng.uniform(1500, 3000)), rgSma1=na_(rng.uniform(1800, 2800)),
              rgC1=na_(rng.uniform(1800, 2800)), rgRy1=na_(rng.uniform(1, 2.5)), rgRy21=na_(rng.uniform(1, 2.5)),
              rgDx1=na_(rng.uniform(95, 110)), rgDx21=na_(rng.uniform(95, 110)), brRySym=rng.choice(["FRED:DFII10", ""]),
              rgDxySym=rng.choice(["TVC:DXY", ""]))
    e7 = P.Env(**st)
    P.run(rg, e7)
    r12 = None if P.isna(st["rgM1"]) or P.isna(st["rgM13"]) else (st["rgM1"] / st["rgM13"] - 1) * 100
    up = r12 is not None and not P.isna(st["rgSma1"]) and not P.isna(st["rgC1"]) and r12 > 0 and st["rgC1"] > st["rgSma1"]
    dn = r12 is not None and not P.isna(st["rgSma1"]) and not P.isna(st["rgC1"]) and r12 < 0 and st["rgC1"] < st["rgSma1"]
    ry = None if not st["brRySym"] or P.isna(st["rgRy1"]) or P.isna(st["rgRy21"]) else st["rgRy1"] - st["rgRy21"]
    dx = None if not st["rgDxySym"] or P.isna(st["rgDx1"]) or P.isna(st["rgDx21"]) else st["rgDx1"] - st["rgDx21"]
    mac = 0 if ry is None or dx is None else 1 if ry < 0 and dx < 0 else -1 if ry > 0 and dx > 0 else 0
    bad7 += (bool(e7["rgUp"]), bool(e7["rgDn"]), int(e7["rgMac"]), e7["rgTxt"]) != (up, dn, mac, "▲ LONG" if up else "▼ SHORT" if dn else "◆ FLAT")
    bad7 += ("no data" in e7["rgMacTxt"]) != (ry is None or dx is None)
rk = [line(p) for p in ("float rkStopD = ", "float rkRisk = ", "float rkPerLot = ", "float rkLots = ", "bool rkLocked = ")]
bad7r = 0
for _ in range(4000):
    st = dict(rkStop=rng.choice([0.0, rng.uniform(0.5, 30)]), atr14=rng.uniform(0.5, 25), rkEquity=rng.choice([100.0, 5000.0, 1e4, 2.5e5]),
              rkPct=rng.choice([0.05, 0.25, 0.5, 1.0, 5.0]), ckCost=rng.uniform(0.3, 1.2), pointValue=rng.choice([1.0, 100.0]),
              rkToday=rng.uniform(-4, 3), rkCap=rng.choice([-0.5, -2.0, -3.0]))
    e7 = P.Env(**st)
    P.run(rk, e7)
    stop = st["rkStop"] if st["rkStop"] > 0 else st["atr14"]
    risk = st["rkEquity"] * st["rkPct"] / 100
    lots = math.floor(risk / ((stop + st["ckCost"]) * st["pointValue"]) * 100) / 100
    loss_at_stop = lots * (stop + st["ckCost"]) * st["pointValue"]
    bad7r += abs(e7["rkLots"] - lots) > 1e-9 or loss_at_stop > risk + 1e-9 or bool(e7["rkLocked"]) != (st["rkToday"] <= st["rkCap"])
lg = [line(p) for p in ("float lgSe = ", "float lgT = ", "float lgLo = ", "float lgHi = ", "[lgWlo, lgWhi] = ", "string lgVerdict = ",
                        "int lgLv = ")]


def tq_exact(df):
    """97.5% Student-t quantile by bisection on the CDF (regularised incomplete beta by continued fraction)."""
    def betacf(a, b, x):
        qab, qap, qam, c, d = a + b, a + 1, a - 1, 1.0, 1 - (a + b) * x / (a + 1)
        d = 1 / d
        h = d
        for m in range(1, 300):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d, c = 1 / (1 + aa * d), 1 + aa / c
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d, c = 1 / (1 + aa * d), 1 + aa / c
            h *= d * c
        return h

    def cdf(t):
        x = df / (df + t * t)
        lb = math.lgamma(df / 2 + 0.5) - math.lgamma(df / 2) - math.lgamma(0.5)
        ib = math.exp(lb + df / 2 * math.log(x) + 0.5 * math.log(1 - x)) * betacf(df / 2, 0.5, x) / (df / 2)
        return 1 - 0.5 * ib
    lo, hi = 1.9, 15.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < 0.975 else (lo, mid)
    return (lo + hi) / 2


def verdict(n_, mean, sd, pf):
    if n_ < 50:
        return "UNDECIDED · N < 50"
    se = sd / math.sqrt(n_)
    t = tq_exact(n_ - 1)
    lo_, hi_ = mean - t * se, mean + t * se
    if lo_ > 0 and pf >= 1.2:
        return "EDGE SHOWN"
    if lo_ > 0:
        return "NO EDGE SHOWN · PF < 1.2"
    return "NO EDGE · interval below 0" if hi_ < 0 else "NO EDGE SHOWN · interval spans 0"


bad7v = n7v = 0
for _ in range(1500):
    n_ = rng.choice([0, 1, 10, 49, 50, 65, 179, 400])
    mean = rng.choice([-0.3, -0.05, 0.0, 0.05, 0.12, 0.3, rng.uniform(-0.5, 0.5)])
    sd = rng.choice([0.5, 0.68, 1.0, 1.5])
    pf = rng.choice([0.43, 1.0, 1.19, 1.2, 2.0])
    e7 = P.Env(funcs=env.funcs, lgN=float(n_), lgW=float(n_ // 3), lgMean=mean, lgSd=sd, lgPF=pf)
    P.run(lg, e7)
    want = verdict(n_, mean, sd, pf) if n_ > 1 else "UNDECIDED · N < 50"
    if n_ >= 50:      # near a boundary the Cornish-Fisher t (error < 2e-4) may legitimately differ: skip |margin| < 1e-3
        se = sd / math.sqrt(n_)
        if min(abs(mean - tq_exact(n_ - 1) * se), abs(mean + tq_exact(n_ - 1) * se)) < 1e-3:
            continue
    n7v += 1
    bad7v += e7["lgVerdict"] != want
e7 = P.Env(funcs=env.funcs, lgN=65.0, lgW=22.0, lgMean=-0.2268, lgSd=0.6796, lgPF=0.4292)
P.run(lg, e7)
defaults = (int(re.search(r'lgN = input\.int\((\d+),', V).group(1)), int(re.search(r'lgW = input\.int\((\d+),', V).group(1)),
            float(re.search(r'lgMean = input\.float\(([-\d.]+),', V).group(1)), float(re.search(r'lgSd = input\.float\(([-\d.]+),', V).group(1)),
            float(re.search(r'lgPF = input\.float\(([-\d.]+),', V).group(1)))
ledger = "NOT RUN (forward-ledger branch not reachable)"
try:
    rows = json.loads(subprocess.run(["git", "show", "origin/forward-ledger:holdout/15m_h4.json"], capture_output=True, text=True,
                                     check=True).stdout)
    r_ = [t["r"] for t in rows if isinstance(t, dict) and not t.get("open") and t["recorded_utc"] <= "2026-10-21T23:04:44.5"]
    mu = sum(r_) / len(r_)
    sdv = math.sqrt(sum((x - mu) ** 2 for x in r_) / (len(r_) - 1))
    pfv = sum(x for x in r_ if x > 0) / -sum(x for x in r_ if x < 0)
    led_ok = (len(r_), sum(x > 0 for x in r_)) == defaults[:2] and abs(mu - defaults[2]) < 5e-5 and abs(sdv - defaults[3]) < 5e-5 \
        and abs(pfv - defaults[4]) < 5e-5
    ledger = f"defaults == the ledger file (N {len(r_)}, wins {sum(x > 0 for x in r_)}, mean {mu:.4f}, sd {sdv:.4f}, PF {pfv:.4f}): {led_ok}"
except (subprocess.CalledProcessError, KeyError, ZeroDivisionError, json.JSONDecodeError):
    led_ok = True
ex_lo, ex_hi = -0.2268 - tq_exact(64) * 0.6796 / math.sqrt(65), -0.2268 + tq_exact(64) * 0.6796 / math.sqrt(65)
report(bad7 == 0 and bad7r == 0 and bad7v == 0 and e7["lgVerdict"] == "NO EDGE · interval below 0" and led_ok
       and abs(e7["lgLo"] - ex_lo) < 1e-4 and abs(e7["lgHi"] - ex_hi) < 1e-4,
       f"7 regime (4000 cases, mismatches {bad7}); lots = floor(risk / ((stop + cost) x $/pt) to 0.01), never above the risk, "
       f"cap lock (4000, mismatches {bad7r}); verdict vs the pre-registered rule with the exact t ({n7v} cases, mismatches "
       f"{bad7v}); default record -> {e7['lgVerdict']}, CI {e7['lgLo']:.3f} … {e7['lgHi']:.3f} (exact {ex_lo:.3f} … {ex_hi:.3f}); "
       f"{ledger}")

# ---- 8 every new text with missing data. The derived values come from the Pine's own lines run on random primitive
# inputs (some na), so a state the script cannot reach is never tested and every reachable one can be.
ck0 = L.index(next(l for l in L if l.strip() == "if ckPanel"))
ck1 = next(i for i in range(ck0 + 1, len(L)) if not L[i].startswith("        ") and L[i].strip())
rows8 = [l.strip() for l in L[ck0 + 1:ck1] if l.strip().startswith("_tmRow(r, ")]
tk0 = L.index(next(l for l in L if l.strip() == "int _c = 6"))
tk_lines = [l.strip() for l in L[tk0:tk0 + 14] if l.strip()]


def args(s, name):
    """quote-aware argument split (commas and brackets inside strings are text)"""
    s = s[s.index(name + "(") + len(name) + 1:s.rindex(")")]
    out, d, cur, q = [], 0, "", False
    for c in s:
        if c == '"':
            q = not q
        if not q and c in "([":
            d += 1
        if not q and c in ")]":
            d -= 1
        if c == "," and d == 0 and not q:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
    return out + [cur.strip()]


texts = []
for r_ in rows8:
    a_ = args(r_, "_tmRow")
    texts.append(("panel " + a_[1], a_[2]))
for l in tk_lines:
    if l.startswith("f_tk(_c, "):
        a_ = args(l, "f_tk")
        texts += [("tile " + a_[0] + " #" + str(k), a_[k]) for k in (1, 3, 4)]
    if l.startswith("table.cell(tkT, 0, 0, "):
        texts.append(("banner", args(l, "table.cell")[3]))
n0 = L.index("int nwK = -1")
n1 = next(i for i in range(n0, len(L)) if L[i].startswith("int nwLv = "))
NW = [l for l in L[n0:n1 + 1] if l.strip()]
DER = ([line(p) for p in ("float ckCostPct = ", "int ckCostLv = ", "bool ckChurn = ")] + rk + rg + lg + [line("string lgTxt = ")]
       + [l.strip() for l in L if l.strip().startswith("int _ckLv = ") or l.strip().startswith("string _ckTx = ")])
nan8, err8, n8 = [], set(), 0
for _ in range(1500):
    na_ = lambda x: P.NA if rng.random() < 0.25 else x
    st = dict(_cmp=rng.random() < .5, _amb="A", _tmUp="U", _tmDn="D", _tmV="V", _tmK="K", _tmS="S",
              nwShow=rng.random() < .9, nwT=e4["nwT"], nwName=e4["nwName"], nwBefore=30.0, nwAfter=30.0,
              nwI=float(rng.choice([0, 5, 37, 38])), timenow=rng.uniform(e4["nwT"][0] - 9e8, e4["nwT"][-1] + 9e8),
              **{"barstate.islast": True},
              ckCost=rng.uniform(0.3, 1.2), atr14=na_(rng.uniform(0.5, 20)), ckFlips=float(rng.choice([0, 1, 2, 5])),
              ckER=na_(rng.uniform(0, 1)), rkStop=rng.choice([0.0, 4.0]), rkEquity=1e4, rkPct=0.5, pointValue=100.0,
              rkToday=rng.uniform(-3, 2), rkCap=-2.0, rgM1=na_(2600.0), rgM13=na_(2300.0), rgSma1=na_(2500.0), rgC1=na_(2600.0),
              rgRy1=na_(1.8), rgRy21=na_(1.9), rgDx1=na_(99.0), rgDx21=na_(100.0), brRySym=rng.choice(["FRED:DFII10", ""]),
              rgDxySym=rng.choice(["TVC:DXY", ""]), sessManipProb=na_(34.0), sessContProb=na_(51.0), ckN=float(rng.choice([0, 42])),
              lgShow=True, lgArm="H4 · 15m (deciding)", lgAsof="2026-10-21 23:04 UTC", lgN=float(rng.choice([0, 1, 30, 65])),
              lgW=float(rng.choice([0, 22, 70])), lgMean=-0.2268, lgSd=rng.choice([0.0, 0.6796]), lgPF=0.4292,
              lgNote=rng.choice(["", "note"]))
    e8 = P.Env(funcs=env.funcs, **st)
    P.BUILTINS["str.format_time"] = lambda t_, f_, z_: "10-28 14:00"
    try:
        P.run(NW + DER, e8)
    except Exception as ex:          # noqa: BLE001
        err8.add(("derive", str(ex)[:70]))
        continue
    for who, src in texts:
        n8 += 1
        try:
            out = P.evaluate(src, e8)
            if not isinstance(out, str) or "NaN" in out:
                nan8.append((who, str(out)[:60]))
        except Exception as ex:          # noqa: BLE001
            err8.add((who, str(ex)[:60]))
report(not nan8 and not err8 and len(rows8) == 9 and len(texts) == 16,
       f"8 new texts (panel CHECKS rows {len(rows8)}, tiles 6 / 7, banner) executed with missing data, every derived value from "
       f"the Pine's own lines: {len(texts)} texts, {n8} evaluations, {len(nan8)} showed NaN, {len(err8)} could not be evaluated"
       + (f" -- e.g. {nan8[:2]} {sorted(err8)[:2]}" if nan8 or err8 else ""))

# ---- 9 the Master's SIGNAL cell
import fix_v86 as F86  # noqa: E402
P.define(fnsrc("_si(", ML) if any(l.startswith("_si(") for l in ML) else ["_si(float x) => str.tostring(math.round(x))"], env)
old_e = F86.OLD.split("=", 1)[1].strip()
new_e = F86.NEW.split("=", 1)[1].strip()
bad9 = 0
for _ in range(2000):
    st = dict(_confDirLabel=rng.choice(["WAIT", "BUY", "SELL"]), fBullScore=P.NA if rng.random() < .1 else float(rng.randint(0, 100)),
              fBearScore=P.NA if rng.random() < .1 else float(rng.randint(0, 100)), fRngScore=P.NA if rng.random() < .1 else float(rng.randint(0, 100)))
    o = P.evaluate(old_e, P.Env(funcs=env.funcs, **st))
    nw = P.evaluate(new_e, P.Env(funcs=env.funcs, **st))
    bad9 += re.findall(r"\d+", o) != re.findall(r"\d+", nw) or "%" in nw or "score" not in nw or "NaN" in nw
prev = subprocess.run(["git", "show", "HEAD:" + MP], capture_output=True, text=True).stdout.split("\n")
diff = [i for i, (x, y) in enumerate(zip(prev, ML, strict=True)) if x != y] if len(prev) == len(ML) else ["length"]
only = len(diff) == 2 and "BUILD STAMP" in ML[diff[0]] and ML[diff[1]].strip() == F86.NEW if prev != ML else True
report(bad9 == 0 and only, f"9 Master SIGNAL cell: v83 and v86 text executed, 2000 cases: same numbers, no '%', 'score' shown, "
       f"mismatches {bad9}; vs the last commit only the stamp and that line differ ({len(diff) if prev != ML else 0} lines)")

# ---- 10 EdgeCases
E = open(EP, encoding="utf-8").read()
EL = E.split("\n")
firsts = [i for i, l in enumerate(EL) if l.startswith("if barstate.isfirst")]
lasts = [i for i, l in enumerate(EL) if l.startswith("if barstate.islast")]
pure = True
for i in firsts:
    j = i + 1
    while j < len(EL) and (EL[j].startswith("    ") or not EL[j].strip()):
        code = EL[j].split("//")[0]
        code = re.sub(r'"[^"]*"', '""', code)
        if re.search(r"\b(close|open|high|low|volume|time|bar_index|timenow|hl2|hlc3|ohlc4)\b", code):
            pure = False
        j += 1
render = len(lasts) == 1 and "int _n = array.size(tName)" in EL[lasts[0] + 1]
report(len(firsts) == 12 and render and "islastconfirmedhistory\n" not in E.replace("barstate.islastconfirmedhistory`", "") and pure
       and E.count("    chk(") == 99,
       f"10 EdgeCases: {len(firsts)} assertion blocks at bar 0, the table on the last bar, 99 assertions, each a pure "
       f"function of constants: {pure}")

print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text executed in Python (timestamp() modelled with the IANA zone); "
      "TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
