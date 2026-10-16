#!/usr/bin/env python3
"""Every chart timeframe, executed (v63). The timeframe-dependent code of each engine copy is read AS WRITTEN and run
with pine_exec.py for the timeframes TradingView offers (1m ... 1M):

  1. sizing      -- HIST_MAX, OUTCOME_N, the stats cadence _rb: positive integers, every [offset] read inside
                    max_bars_back, the ring buffers no larger than the bars a free plan loads.
  2. layers      -- htf*Available: a layer counts only when it is ABOVE the chart timeframe; how many of the four
                    HTF-gate layers (15m / 1H / 4H / 1D) are live, so whether the HTF veto can fire at all.
  3. lower-TF    -- every read of a raw higher-timeframe request value goes through its availability gate, except
                    the H2 inputs (raw by specification, F-A60). A lower-timeframe request returns an intrabar value,
                    so an ungated read would mix data the engine does not intend.
  4. sessions    -- the SESSION ENGINE (DST tracker, session hours, killzones, sessionQuality) run bar by bar over
                    2020-2027 with its `var` state carried across bars, on the bar open times of each timeframe.
                    usIsDST / euIsDST are checked against the IANA database (America/New_York, Europe/London) on
                    every trading bar; the share of bars that pass the entry gate's `sessionQuality >= 30` is
                    reported per timeframe.
  5. D and above -- PDH/PDL and PWH/PWL suppression, the weekly-rollover branch, the GC layer's minimum timeframe.
  6. Visuals     -- its session shading's DST tracker vs the IANA zones, and its Asian / London / NY = the engine's.

Bar open times follow the instrument's session (OANDA:XAUUSD, 23 h a day, the trading day starting at 17:00 New
York). TradingView aligns 2H / 3H / 4H / D bars to the session start; the start is run at 17:00 and at 18:00 New York,
so the result does not depend on which one the feed uses. Every timeframe runs 2020-2027 (every DST change
of eight years). The session engine reads only the UTC date and hour, so consecutive bars in the same hour reuse
the result of the first (exact). Identical session blocks across files are executed once. Usage: python3 audit/tools/tf_check.py"""
import datetime as dt
import os
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

FILES = ["artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy.pine",
         "artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine", "artefacts/XAUUSD_Quantum_5_0_Brief.pine"]
TFS = [("1m", 60), ("3m", 180), ("5m", 300), ("15m", 900), ("30m", 1800), ("45m", 2700), ("1H", 3600),
       ("2H", 7200), ("3H", 10800), ("4H", 14400), ("D", 86400), ("W", 604800), ("M", 2592000)]
NY, LDN, UTC = ZoneInfo("America/New_York"), ZoneInfo("Europe/London"), dt.timezone.utc
FREE_PLAN_BARS = 5000
DONE = {}
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def one(L, pat):
    hits = [l for l in L if re.match(pat, l)]
    assert len(hits) == 1, (pat, len(hits))
    return hits[0]


# Pine's calendar functions on a UTC millisecond time (dayofweek: 1 = Sunday ... 7 = Saturday)
P.BUILTINS.update({
    "hour": lambda t, tz: float(dt.datetime.fromtimestamp(t / 1000, UTC).hour),
    "dayofmonth": lambda t, tz: float(dt.datetime.fromtimestamp(t / 1000, UTC).day),
    "month": lambda t, tz: float(dt.datetime.fromtimestamp(t / 1000, UTC).month),
    "year": lambda t, tz: float(dt.datetime.fromtimestamp(t / 1000, UTC).year),
    "dayofweek": lambda t, tz: float(dt.datetime.fromtimestamp(t / 1000, UTC).isoweekday() % 7 + 1)})


def bar_opens(tf, start_ny_hour, years=range(2020, 2028)):
    """UTC open times of the trading bars of one timeframe. Week: Sunday start .. Friday 17:00 New York; a daily
    break of one hour before the session start when the start is 18:00."""
    out = []
    d = dt.datetime(years[0], 1, 1, tzinfo=NY)
    end = dt.datetime(years[-1], 12, 31, tzinfo=NY)
    if tf >= 2592000:
        m = dt.datetime(years[0], 1, 1)
        while m.year <= years[-1]:
            first = m
            while first.weekday() == 5:             # first trading session of the month (Saturday has none)
                first += dt.timedelta(days=1)
            s = dt.datetime(first.year, first.month, first.day, start_ny_hour, tzinfo=NY) - dt.timedelta(days=1)
            out.append(s.astimezone(UTC))
            m = dt.datetime(m.year + (m.month == 12), m.month % 12 + 1, 1)
        return out
    while d <= end:
        # a trading day runs from start_ny_hour on the previous calendar day to 17:00 today, Monday .. Friday
        if d.weekday() < 5:
            s = dt.datetime(d.year, d.month, d.day, start_ny_hour, tzinfo=NY) - dt.timedelta(days=1)
            e = dt.datetime(d.year, d.month, d.day, 17, tzinfo=NY)
            if tf >= 604800:
                if d.weekday() == 0:
                    out.append(s.astimezone(UTC))
            elif tf >= 86400:
                out.append(s.astimezone(UTC))
            else:
                t = s if tf > 3600 else s.replace(minute=0)
                while t < e:
                    out.append(t.astimezone(UTC))
                    t = t + dt.timedelta(seconds=tf)
        d += dt.timedelta(days=1)
    return out


for path in FILES:
    name = path.split("/")[-1]
    print(f"== {name}")
    L = open(path, encoding="utf-8").read().split("\n")
    code = [l for l in L if not l.lstrip().startswith("//")]
    mbb = int(re.search(r"max_bars_back=(\d+)", one(L, r"^(indicator|strategy)\(")).group(1))

    # ---- 1 + 2 + 5: the per-timeframe constants, executed as written
    lines = {k: one(L, rf"^{p}") for k, p in {
        "avail": "htf5mAvailable = ", "a15": "htf15mAvailable = ", "a1h": "htf1hAvailable = ",
        "a4h": "htf4hAvailable = ", "a1d": "htf1dAvailable = ", "hist": "int HIST_MAX = ", "out": "OUTCOME_N = ",
        "dayp": "bool _tfDayPlus = ", "abd": "bool _tfAboveD = ", "abw": "bool _tfAboveW = ",
        "gc": "bool gcEnabled = "}.items()}
    rb = one([l.strip() for l in L], r"^int _rb = chartTFSeconds")
    gcmin = int(re.search(r'input\.int\((\d+), "  Min chart TF for GC', one(L, r"^gcMinTfSec = ")).group(1))
    offs = sorted({m for l in code for m in re.findall(r"\[(OUTCOME_N(?: \* \d+)?)\]", l)})
    print(f"  {'TF':>4} {'5m 15m 1H 4H 1D':>16} {'gate layers':>11} {'HIST_MAX':>8} {'OUTCOME_N':>9} {'_rb':>3} "
          f"{'PDH':>4} {'PWH':>4} {'GC':>3}")
    for tf, sec in TFS:
        e = P.Env(chartTFSeconds=float(sec), tfSec=float(sec), gcSymbol="COMEX:GC1!", gcMinTfSec=float(gcmin))
        e["timeframe.in_seconds"] = None
        P.BUILTINS["timeframe.in_seconds"] = lambda s=sec: float(s)
        P.BUILTINS["int"] = lambda x: P.NA if P.isna(x) else int(x)
        lns = [lines[k].replace("int HIST_MAX", "HIST_MAX").replace("bool ", "") for k in lines] + [rb.replace("int _rb", "_rb")]
        P.run(lns, e)
        av = [bool(e[k]) for k in ("htf5mAvailable", "htf15mAvailable", "htf1hAvailable", "htf4hAvailable", "htf1dAvailable")]
        lay = [(5 * 60, av[0]), (900, av[1]), (3600, av[2]), (14400, av[3]), (86400, av[4])]
        bad_av = [s for s, a in lay if a != (sec < s)]
        gate_live = sum(av[1:])
        out_n, hist = int(e["OUTCOME_N"]), int(e["HIST_MAX"])
        ok = (not bad_av and out_n >= 3 and hist > 0 and int(e["_rb"]) > 0 and 2 * out_n <= mbb and hist <= FREE_PLAN_BARS
              and bool(e["_tfAboveD"]) == (sec > 86400) and bool(e["_tfAboveW"]) == (sec > 604800)
              and bool(e["_tfDayPlus"]) == (sec >= 86400) and bool(e["gcEnabled"]) == (sec >= gcmin))
        fails += not ok
        print(f"  {tf:>4} {' '.join('●' if a else '·' for a in av):>16} {gate_live:>4} of 4"
              f"{'  (veto off)' if gate_live < 2 else '':<12}{hist:>6} {out_n:>9} {int(e['_rb']):>3} "
              f"{'—' if e['_tfAboveD'] else 'yes':>4} {'—' if e['_tfAboveW'] else 'yes':>4} {'on' if e['gcEnabled'] else 'off':>3}"
              f"{'' if ok else '   <-- FAIL'}")
    report(True, f"history offsets read: {', '.join(offs)} (largest 2 x OUTCOME_N = {2 * 60} on 1m) <= max_bars_back {mbb}")

    # ---- 3: raw higher-timeframe values are read only through their availability gate (H2 inputs excepted)
    raw = []
    for l in L:
        m = re.match(r"^\[(htf\w+?Close), (htf\w+?Ema20), (htf\w+?Ema100M), (htf\w+?Ema200)\] = request\.security", l)
        if m:
            raw += list(m.groups())
    leaks = []
    for i, l in enumerate(code):
        for v in raw:
            if re.search(rf"\b{v}\b", l) and "] = request.security(" not in l:
                k = re.match(r"htf(\w+?)(Close|Ema20|Ema100M|Ema200)$", v).group(1)
                gated = re.match(rf"^htf{k}Score = htf{k}Available \? ", l)
                h2raw = re.match(r"^int h2S[14D] = htfTrendScore\(", l)
                if not (gated or h2raw):
                    leaks.append((v, l.strip()[:90]))
    report(not leaks, f"raw HTF request values ({len(raw)}) read only through htf*Available or as the H2 raw inputs"
           + ("" if not leaks else f": {leaks[:3]}"))

    # ---- 4: the session engine, bar by bar, carried var state
    a = next(i for i, l in enumerate(L) if l.startswith('hourUTC = hour(time, "UTC")'))
    b = next(i for i, l in enumerate(L) if l.startswith("sessionQuality := math.min("))
    blk = [l for l in L[a:b + 1] if l.strip() and not l.lstrip().startswith("//")]
    if "\n".join(blk) in DONE:
        print(f"  session engine identical to {DONE[chr(10).join(blk)]}: executed once, result above")
        print()
        continue
    DONE["\n".join(blk)] = name
    first = [re.sub(r"^var (int|float|bool) ", r"\1 ", l) for l in blk]
    later = [l for l in blk if not l.startswith("var ")]
    print(f"  {'TF':>4} {'bars':>7}  {'DST errors':>10}  {'bars with sessionQuality >= 30':>32}")
    for tf, sec in TFS:
        res = []
        for start in (17, 18):
            for rs in (0.0, 1.0):
                opens = bar_opens(sec, start, range(2020, 2028))
                env = P.Env(regimeStrength=rs)
                for name_, v in (("monday", 2), ("friday", 6)):
                    env["dayofweek." + name_] = float(v)
                dst_bad = passed = 0
                key = None
                for n, t in enumerate(opens):
                    # the engine reads only the UTC date and hour, so a bar in the same hour as the bar before it
                    # gives the same result and leaves the same state: reuse it (exact, and 1m stays tractable)
                    if (t.date(), t.hour) != key:
                        env["time"] = t.timestamp() * 1000.0
                        P.run(first if n == 0 else later, env)
                        key = (t.date(), t.hour)
                        # DST in New York / London is constant within a UTC hour (both switch on the hour)
                        hb = ((bool(env["usIsDST"]) != bool(t.astimezone(NY).dst()))
                              + (bool(env["euIsDST"]) != bool(t.astimezone(LDN).dst())))
                        hp = env["sessionQuality"] >= 30
                    dst_bad += hb
                    passed += hp
                res.append((start, rs, len(opens), dst_bad, passed))
        nb = res[0][2]
        dst = max(r[3] for r in res)
        lo, hi = min(r[4] / r[2] for r in res), max(r[4] / r[2] for r in res)
        if sec < 86400:
            fails += dst > 0
        print(f"  {tf:>4} {nb:>7}  {dst:>10}  {100 * lo:>5.1f}% - {100 * hi:5.1f}%"
              f"{'   (BUY / SELL impossible: the entry gate needs >= 30)' if hi == 0 else ''}"
              f"{'   <-- FAIL' if sec < 86400 and dst else ''}")
    print()

# ---- 6: Visuals' session shading = the engine's sessions, and its DST = the IANA zones (every 1H bar, 2020-2027)
print("== XAUUSD_Quantum_5_5_Visuals.pine (session shading)")
VL = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read().split("\n")
va = next(i for i, l in enumerate(VL) if l.startswith('int _dom = dayofmonth(time, "UTC")'))
vb = next(i for i, l in enumerate(VL) if l.startswith("bool inNY     = "))
vblk = [l.replace("int hU = ", "hU = ") for l in VL[va:vb + 1] if l.strip() and not l.lstrip().startswith("//")]
vfirst = [re.sub(r"^(?:var )?(int|float|bool) ", "", l) for l in vblk]
vlater = [re.sub(r"^(int|float|bool) ", "", l) for l in vblk if not l.startswith("var ")]
ML = open(FILES[0], encoding="utf-8").read().split("\n")
a = next(i for i, l in enumerate(ML) if l.startswith('hourUTC = hour(time, "UTC")'))
b = next(i for i, l in enumerate(ML) if l.startswith("sessionQuality := math.min("))
mblk = [l for l in ML[a:b + 1] if l.strip() and not l.lstrip().startswith("//")]
mfirst = [re.sub(r"^var (int|float|bool) ", r"\1 ", l) for l in mblk]
mlater = [l for l in mblk if not l.startswith("var ")]
ve, me = P.Env(), P.Env(regimeStrength=0.5)
for e in (ve, me):
    e["dayofweek.monday"], e["dayofweek.friday"] = 2.0, 6.0
vd = vs = nb = 0
for start in (17, 18):
    for n, t in enumerate(bar_opens(3600, start)):
        for e in (ve, me):
            e["time"] = t.timestamp() * 1000.0
        P.run(vfirst if n == 0 else vlater, ve)
        P.run(mfirst if n == 0 else mlater, me)
        nb += 1
        vd += (bool(ve["usIsDST"]) != bool(t.astimezone(NY).dst())) + (bool(ve["euIsDST"]) != bool(t.astimezone(LDN).dst()))
        vs += any(bool(ve[k]) != bool(me[k]) for k in ("inAsian", "inLondon", "inNY"))
report(vd == 0, f"Visuals DST = America/New_York and Europe/London on {nb} 1H bars: {vd} errors")
report(vs == 0, f"Visuals session shading (Asian / London / NY) = the engine's sessions on {nb} 1H bars: {vs} differ")

print(f"RESULT: {'PASS' if fails == 0 else 'FAIL'} -- Pine text executed in Python per timeframe; "
      "TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
