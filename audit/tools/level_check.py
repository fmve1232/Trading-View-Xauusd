#!/usr/bin/env python3
"""The liquidity levels, EXECUTED bar by bar (v99; v90 mutation gaps m09 / m17).

The Master's NY-day / NY-week block (prevNyDailyHigh / Low = PDH / PDL, prevNyWeeklyHigh / Low = PWH / PWL) and its
current-day block (cdh / cdl = CDH / CDL), with the pool lines the plan reads (poolPdH ... poolPwL), are read AS WRITTEN and run with pine_exec, `var` state carried across bars,
and compared on EVERY bar with a reference built from the calendar alone:

    trading day  = the New York date of (bar open + 7 h)       (the day rolls at 17:00 America/New_York, IANA DST)
    trading week = the ISO week of that date                     (the week rolls at Sunday 17:00 New York)
    PDH / PDL    = the extreme of the bars of the previous trading day seen in the data (na before the first roll)
    PWH / PWL    = the same for the previous trading week
    CDH / CDL    = the extreme of the current trading day's bars so far

TWO references. The GATE is the system of record's semantics (quantum/engine.py lines ~294-306, read on the website's
default branch): there, a bar that starts a new trading day but not a new week is NOT added to the week's high / low
(F-A88, open, found by this tool: the same structure as the Pine). The calendar-true values (every bar counted) are
reported beside it as F-A88's measured size; they become the gate once the website fixes its engine.

Data: (1) the real XAU/USD 5m, 15m and 1h bars on the market-data branch, with the website's closure mask applied
(no bars Friday 17:00 -> Sunday 18:00 New York or in the Monday-Thursday 17:00-18:00 break: what the TradingView feed
and the website's engine see; the feed's weekend quote fill is not a trade, PLATFORM.md D-09 / web.4);
(2) generated bar opens for 5m / 1H / 2H / 3H / 4H over 2024-2025 (every DST change, sessions starting 17:00 and
18:00 New York; the F-004 wrap case is 2H under EST and 3H under EDT) with random-walk prices.
Positive controls (each must FAIL against the reference): m09 PDH reads the day's LOW; m17 CDH / CDL never reset;
F-004 undone (`<=` in the wrap branch).
D and above are tf_check 5's (suppression / timeframe.change), not repeated here.
Usage: python3 audit/tools/level_check.py"""
import csv
import datetime as dt
import io
import os
import random
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

NY, UTC = ZoneInfo("America/New_York"), dt.timezone.utc
M = open("artefacts/XAUUSD_Quantum_5_0_Master.pine", encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


FILES = ["artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy.pine",
         "artefacts/XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine",
         "artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine", "artefacts/XAUUSD_Quantum_5_0_Brief.pine",
         "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"]
POOL_STARTS = ("bool _tfAboveD = ", "poolPdH := ", "poolPdL := ", "bool _tfAboveW = ", "poolPwH := ", "poolPwL := ")


def block_of(L):
    """the NY-day / NY-week block and the CDH / CDL block of one file, comments dropped, plus its pool lines (the plan's
    SL / TP candidates and the liquidity map read these; `:=` on a global declared elsewhere becomes `=`). Visuals has
    no pools: its prev* values are compared instead."""
    def span(start, end_line):
        a = next(i for i, l in enumerate(L) if l.startswith(start))
        b = next(i for i in range(a, len(L)) if L[i] == end_line)
        return [l for l in L[a:b + 1] if l.strip() and not l.lstrip().startswith("//")]
    blk = (span("int _nyMsOfDay  = ", "    nyWeeklyLow := math.min(nz(nyWeeklyLow, low), low)")
           + span("var float cdh = na", "    cdl := math.min(nz(cdl, low), low)"))
    pools = [l.replace(" := ", " = ", 1) for l in L if l.startswith(POOL_STARTS)]
    assert len(pools) == 6 or not any(l.startswith("poolPd") for l in pools), pools   # Visuals: no pools
    assert sum(l.startswith("bool crossedNYWeek = ") for l in blk) == 1 and any("cdh := high" in l for l in blk)
    return blk + pools if len(pools) == 6 else blk


BLOCK = block_of(M)


def tz_of(z):
    return UTC if z in (None, "UTC") else ZoneInfo(z)


P.BUILTINS.update({
    "hour": lambda t, z=None: float(dt.datetime.fromtimestamp(t / 1000, tz_of(z)).hour),
    "minute": lambda t, z=None: float(dt.datetime.fromtimestamp(t / 1000, tz_of(z)).minute),
    "dayofweek": lambda t, z=None: float(dt.datetime.fromtimestamp(t / 1000, tz_of(z)).isoweekday() % 7 + 1),
    "int": lambda x: P.NA if P.isna(x) else int(x),
    "timeframe.change": lambda *a: False})        # intraday only here: the ternary takes the NY-anchored branch


HIST = ("_tdKey",)          # script variables read with [1]: pine_exec keeps no history, so x[1] is modelled exactly
                            # as the value x had at the end of the previous bar (na on bar 0)


def run_pine(block, bars, sec):
    for v in HIST:
        block = [re.sub(rf"\b{v}\[1\]", f"_prev{v}", l) for l in block]
    first = [l[4:] if l.startswith("var ") else l for l in block]
    later = [l for l in block if not l.startswith("var ")]
    P.BUILTINS["timeframe.in_seconds"] = lambda *a: float(sec)
    T, H, L = P.Series(), P.Series(), P.Series()
    env = P.Env(msInDay=86400000.0, time=T, high=H, low=L, chartTFSeconds=float(sec))
    env["dayofweek.friday"] = 6.0
    for v in HIST:
        env["_prev" + v] = P.NA
    out = []
    for n, (t, h, l) in enumerate(bars):
        T.append(t)
        H.append(h)
        L.append(l)
        P.run(first if n == 0 else later, env)
        for v in HIST:
            env["_prev" + v] = env.get(v, P.NA)
        pools = "poolPdH" in env
        out.append(tuple(env[k] for k in (("poolPdH", "poolPdL", "poolPwH", "poolPwL") if pools else
                                          ("prevNyDailyHigh", "prevNyDailyLow", "prevNyWeeklyHigh", "prevNyWeeklyLow"))
                         + ("cdh", "cdl")))
    return out


def reference(bars, web=True):
    """web=True: the system of record's semantics (a new-day, same-week bar is left out of the week's extremes)."""
    out, dayx, weekx = [], {}, {}
    days, weeks = [], []
    for t, h, l in bars:
        d = (dt.datetime.fromtimestamp(t / 1000, NY) + dt.timedelta(hours=7)).date()
        w = tuple(d.isocalendar())[:2]
        new_day = bool(days) and days[-1] != d
        for key, store, order in ((d, dayx, days), (w, weekx, weeks)):
            new = not order or order[-1] != key
            if new:
                order.append(key)
            if web and store is weekx and new_day and not new:
                continue
            hi, lo = store.get(key, (h, l))
            store[key] = (max(hi, h), min(lo, l))
        pd_ = dayx[days[-2]] if len(days) > 1 else (P.NA, P.NA)
        pw_ = weekx[weeks[-2]] if len(weeks) > 1 else (P.NA, P.NA)
        out.append((pd_[0], pd_[1], pw_[0], pw_[1], dayx[d][0], dayx[d][1]))
    return out


NAMES = ("PDH", "PDL", "PWH", "PWL", "CDH", "CDL")


def compare(got, want):
    bad = [0] * 6
    first = [None] * 6
    for i, (g, w) in enumerate(zip(got, want)):
        for k in range(6):
            if not ((P.isna(g[k]) and P.isna(w[k])) or (not P.isna(g[k]) and not P.isna(w[k]) and g[k] == w[k])):
                bad[k] += 1
                first[k] = first[k] if first[k] is not None else i
    return bad, first


def closed(t):
    """the website's closure mask (quantum/data/sources.py): Friday 17:00 -> Sunday 18:00 and 17:00-18:00 Mon-Thu, NY"""
    n = dt.datetime.fromtimestamp(t / 1000, NY)
    wd, hr = n.weekday(), n.hour
    return (wd == 4 and hr >= 17) or wd == 5 or (wd == 6 and hr < 18) or (wd < 4 and hr == 17)


def market(folder):
    rows = {}
    ls = subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/market-data"], capture_output=True, text=True).stdout
    for f in ls.split():
        if f.startswith(folder + "/"):
            txt = subprocess.run(["git", "show", "origin/market-data:" + f], capture_output=True, text=True).stdout
            for r in csv.DictReader(io.StringIO(txt)):
                rows[r["datetime"]] = (float(r["high"]), float(r["low"]))
    bars = [(dt.datetime.fromisoformat(k).timestamp() * 1000.0, *rows[k]) for k in sorted(rows)]
    return [b for b in bars if not closed(b[0])]


def gen_opens(sec, start_ny_hour, years=(2024, 2025)):
    out = []
    d = dt.datetime(years[0], 1, 1, tzinfo=NY)
    while d.year <= years[-1]:
        if d.weekday() < 5:
            s = dt.datetime(d.year, d.month, d.day, start_ny_hour, tzinfo=NY) - dt.timedelta(days=1)
            e = dt.datetime(d.year, d.month, d.day, 17, tzinfo=NY)
            t = s if sec > 3600 else s.replace(minute=0)
            while t < e:
                out.append(t.astimezone(UTC))
                t += dt.timedelta(seconds=sec)
        d += dt.timedelta(days=1)
    return out


def gen_bars(opens, rng):
    px, out = 2000.0, []
    for t in opens:
        o = px
        px = o + rng.gauss(0, 3)
        out.append((t.timestamp() * 1000.0, max(o, px) + abs(rng.gauss(0, 1)), min(o, px) - abs(rng.gauss(0, 1))))
    return out


def detail(bad, first, got, want, bars):
    msg = []
    for k in range(6):
        if bad[k]:
            i = first[k]
            when = dt.datetime.fromtimestamp(bars[i][0] / 1000, NY).strftime("%Y-%m-%d %H:%M NY")
            msg.append(f"{NAMES[k]} {bad[k]} bars (first {when}: Pine {got[i][k]} vs reference {want[i][k]})")
    return "; ".join(msg)


V98 = ["bool crossedNYDay = false", "if not na(time[1])", "    int tMod = time % msInDay", "    int t1Mod = time[1] % msInDay",
       "    if tMod > t1Mod", "        crossedNYDay := t1Mod < nyCloseDayMs and tMod >= nyCloseDayMs", "    else",
       "        crossedNYDay := t1Mod < nyCloseDayMs or tMod >= nyCloseDayMs"]
V99 = ["int _tdKey = math.floor((time - nyCloseDayMs) / msInDay)",
       "bool crossedNYDay = not na(time[1]) and _tdKey != _tdKey[1]"]


def mutate(block, old, new):
    """replace the consecutive lines `old` (stripped match) with `new`; asserts the anchor exists exactly once"""
    st = [l.strip() for l in block]
    olds = [x.strip() for x in old]
    hits = [i for i in range(len(st)) if st[i:i + len(olds)] == olds]
    assert len(hits) == 1, (old[0], len(hits))
    i = hits[0]
    ind = len(block[i]) - len(block[i].lstrip())
    return block[:i] + [" " * ind + x for x in new] + block[i + len(olds):]


MUT = {
    "m09 PDH reads the day's LOW": (["prevNyDailyHigh := nyDailyHigh"], ["prevNyDailyHigh := nyDailyLow"]),
    "m09' PDH pool reads the previous day's LOW (v90_mutation m09)": (["poolPdH = _tfAboveD ? na : prevNyDailyHigh"],
                                                                     ["poolPdH = _tfAboveD ? na : prevNyDailyLow"]),
    "m17 CDH / CDL never reset": (["cdh := high"], ["cdh := math.max(nz(cdh, high), high)"]),
    "F-A87 regression: the v98 time-of-day rollover": (V99, V98),
    "F-004 regression: v98 rollover with <= in the wrap branch": (V99, V98[:-1] + [V98[-1].replace("t1Mod <", "t1Mod <=")]),
}

if __name__ == "__main__":
    rng = random.Random(99)
    print("== real XAU/USD bars (market-data branch)")
    cases = []
    for folder, sec in (("XAU_USD_5m", 300), ("XAU_USD_15m", 900), ("XAU_USD_60m", 3600)):
        bars = market(folder)
        if not bars:
            print(f"  NOT RUN  {folder}: market-data not reachable")
            fails += 1
            continue
        cases.append((folder, sec, bars))
    print("== generated bar opens 2024-2025, sessions at 17:00 and 18:00 New York")
    for name, sec in (("5m", 300), ("1H", 3600), ("2H", 7200), ("3H", 10800), ("4H", 14400)):
        for st in (17, 18):
            cases.append((f"gen {name} start {st}:00", sec, gen_bars(gen_opens(sec, st), rng)))
    results, f88, done = {}, [], {}
    wants = {name: (reference(bars), reference(bars, web=False)) for name, sec, bars in cases}
    for path in FILES:
        blk = block_of(open(path, encoding="utf-8").read().split("\n"))
        fname = path.split("/")[-1]
        key = "\n".join(blk)
        if key in done:
            print(f"== {fname}: level block identical to {done[key]}'s, result above")
            continue
        done[key] = fname
        print(f"== {fname}" + ("" if "poolPdH = _tfAboveD ? na : prevNyDailyHigh" in blk else " (no pools: prev* compared)"))
        for name, sec, bars in cases:
            got, (want, true_) = run_pine(blk, bars, sec), wants[name]
            bad, first = compare(got, want)
            report(sum(bad) == 0, f"{name}: {len(bars)} bars, PDH / PDL / PWH / PWL / CDH / CDL == the system of record's "
                   "semantics on every bar" + ("" if not sum(bad) else ": " + detail(bad, first, got, want, bars)))
            if path == FILES[0]:
                results[name] = (bars, sec, want)
                tb, _ = compare(got, true_)
                f88.append((name, tb[2], tb[3], len(bars)))
    print("== F-A88 (open, website engine first): bars where PWH / PWL differ from the calendar-true week extremes")
    for name, a_, b_, n_ in f88:
        print(f"  INFO  {name}: PWH {a_}, PWL {b_} of {n_} bars")
    print("== D / W / M bars: the day rolls on every bar (the old test did there; P1-LVL-002), weekly branch untouched")
    ri = [i for i, l in enumerate(BLOCK) if l.startswith("bool crossedNYDay = ")][0]
    for name, sec in (("D", 86400), ("W", 604800), ("M", 2592000)):
        opens = gen_opens(86400, 18)
        opens = (opens if sec == 86400 else [t for t in opens if t.astimezone(NY).weekday() == 6] if sec == 604800
                 else [t for k, t in enumerate(opens) if k == 0 or t.astimezone(NY).month != opens[k - 1].astimezone(NY).month])
        bars = gen_bars(opens, rng)
        P.BUILTINS["timeframe.in_seconds"] = lambda *a, s_=sec: float(s_)
        T, H, L_ = P.Series(), P.Series(), P.Series()
        env = P.Env(msInDay=86400000.0, time=T, high=H, low=L_, _prev_tdKey=P.NA)
        env["dayofweek.friday"] = 6.0
        lines = [re.sub(r"\b_tdKey\[1\]", "_prev_tdKey", l) for l in BLOCK[:ri + 1]]
        miss = 0
        for k, (t, h, l) in enumerate(bars):
            T.append(t); H.append(h); L_.append(l)
            P.run(lines, env)
            miss += (k > 0) and not env["crossedNYDay"]
            env["_prev_tdKey"] = env["_tdKey"]
        report(miss == 0, f"{name}: {len(bars)} bars, crossedNYDay on every bar after the first: missed {miss}")
    print("== positive controls on the Master (each mutant must be detected)")
    for mname, (o, n) in MUT.items():
        mb = mutate(BLOCK, o, n)
        hit = 0
        for name, (bars, sec, want) in results.items():
            b, _ = compare(run_pine(mb, bars, sec), want)
            hit += sum(b) > 0
        report(hit > 0, f"control {mname}: detected on {hit} of {len(results)} data sets")
    print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- the Master's level blocks executed in Python bar by bar; "
          "TradingView runtime NOT exercised")
    sys.exit(1 if fails else 0)
