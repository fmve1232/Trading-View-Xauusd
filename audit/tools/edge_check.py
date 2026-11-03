#!/usr/bin/env python3
"""Edge cases E3 / E4 / E7 / E8 of the v90 audit (Report 11), EXECUTED where Pine can be run (v100).

  E3  every macro feed missing or stale: the Master's stale tracker, validity flags, weights, ms* terms,
      macroStrengthScore and macroIntelLabel run AS WRITTEN over bars with every request na and the trend flags random
      (even all bullish): the score is 0, the label "N/A", nothing reaches the evidence lines (evMacroBull / Bear 0).
      A missing request (its close and EMAs na together) drops that feed on the same bar; it counts again on return.
      F-A91 (INFO): the stale cache cannot take effect, and gaps_off requests are na only before their first value, so
      a feed that stops updating stays valid on its frozen value (the website ages macro values out after 5 days).
      F-A89 (INFO, both engines): macroIntelValid leaves TIPS out, so a TIPS-only state shows "N/A" with a score.
  E4  a +/-3% weekend gap: the Master's return clamp, z-score and ABNORMAL test run as written on the gap bar of a
      quiet 5-minute series (the ta.sma / ta.stdev inputs computed per bar here): the return is clamped to the 6-sigma
      window (>= 0.2%, <= 5%), |z| > 3 makes the regime ABNORMAL, nothing is NaN, and the bars after the gap are not
      ABNORMAL from the gap alone.
  E7  rapid signals: the DECISION line and the BUY / SELL alert() conditions run as written on random signal sequences
      (runs of 1-9 bars, vetoes, the risk lock, flips within 3 bars): exactly one BUY / SELL alert per run, on its first
      bar, never both on a bar, and a flip alerts the new side at once. Control: the v99 condition (no [1] term) repeats.
      (Real data, recorded in fix_v100.py: the website engine on 15m had 29 of 36 BUY alerts repeating a run.)
  E8  runtime errors from input extremes and empty arrays: every `for i = a to array.size(A) - 1` in every file has an
      enclosing size guard or a triaged reason below (a Pine `for 0 to -1` runs i = 0 and -1 on an empty array); every
      input-bounded loop / array size is evaluated at the input's minval / maxval: sizes >= 1, loop ends >= the start.
Usage: python3 audit/tools/edge_check.py"""
import glob
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

MF = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
M = open(MF, encoding="utf-8").read().split("\n")
rng = random.Random(100)
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def span(L, start, end):
    a = next(i for i, l in enumerate(L) if l.startswith(start))
    b = next(i for i in range(a, len(L)) if L[i].startswith(end))
    return [l for l in L[a:b + 1] if l.strip() and not l.lstrip().startswith("//")]


def one(L, start):
    h = [l for l in L if l.startswith(start)]
    assert len(h) == 1, (start, len(h))
    return h[0]


# ---------------- E3
STALE = span(M, "var float cachedDXY = na", "tipsValid = _tipsOn and ")
NUMV = span(M, "float _numValid = 0.0", "_numValid := tipsValid ? ")
WEIGHTS = span(M, "_wDXYr = math.min(", "wTIPS = _wTot > 0 ? ")
TERMS = span(M, "msDXY = dxyValid ? ", "macroStrengthScore = int(")
TAIL = [one(M, "macroIntelScore = macroStrengthScore"), one(M, "macroIntelValid = "), one(M, "string macroIntelLabel = "),
        one(M, "float evMacroBull = "), one(M, "float evMacroBear = ")]
FEEDS = ("DXY", "Yield", "Silver", "EURUSD", "SPX", "TIPS")
RAW = {"DXY": ["_rawDXY", "_rawDXYFast", "_rawDXYSlow"], "Yield": ["_rawYield", "_rawYieldFast", "_rawYieldSlow"],
       "Silver": ["_rawSilver", "_rawSilverEMA"], "EURUSD": ["_rawEURUSD", "_rawEURFast", "_rawEURSlow"],
       "SPX": ["_rawSPX", "_rawSPXFast", "_rawSPXSlow"], "TIPS": ["_rawTIPS", "_rawTIPSFast", "_rawTIPSSlow"]}
FLAGS = ["dxyBear", "dxyBull", "yieldFalling", "yieldRising", "spxBull", "spxBear", "eurusdBull", "eurusdBear", "tipsFalling",
         "tipsRising", "dxyMomBear", "dxyMomBull", "ratePressureDown", "ratePressureUp"]


def macro_env(bull_all):
    e = P.Env(tipsSymbol="TVC:US10Y", yieldSymbol="TVC:US10Y")   # the defaults' case: TIPS off unless set apart
    for f in FLAGS:
        e[f] = (f.endswith(("Bear", "Falling", "Down")) if bull_all else rng.random() < .5) if not f.startswith(("dxyBull", "dxyMomBull", "yieldRising", "spxBear", "eurusdBear", "tipsRising", "ratePressureUp")) or not bull_all else False
    e["spxBull"] = True if bull_all else e["spxBull"]
    e["eurusdBull"] = True if bull_all else e["eurusdBull"]
    for k in ("avgCorrDXY", "avgCorrYld", "avgCorrSlv", "avgCorrSPX", "avgCorrEUR", "avgCorrTIPS"):
        e[k] = rng.uniform(-.9, .9)
    e.update(silverEMA=30.0, eurusdROC=rng.uniform(-1, 1), stabDXY=.5, stabYld=.5, stabSlv=.5, stabSPX=.5, stabEUR=.5, stabTIPS=.5)
    return e


def run_macro(bars, bull_all, tips_on=False):
    """bars: list of {feed: present?}; returns per-bar (score, label, evBull, evBear, valid flags)"""
    e = macro_env(bull_all)
    if tips_on:
        e["tipsSymbol"] = "TVC:TIPS"
    first = [l[4:] if l.startswith("var ") else l for l in STALE]
    later = [l for l in STALE if not l.startswith("var ")]
    out = []
    for n, present in enumerate(bars):
        for f in FEEDS:
            for k in RAW[f]:
                e[k] = (2000.0 + rng.random() if present.get(f) else P.NA)
        e["silverClose"] = None
        P.run(first if n == 0 else later, e)
        e["silverClose"] = e["cachedSilver"]
        P.run(NUMV + WEIGHTS + TERMS + TAIL, e)
        out.append((e["macroStrengthScore"], e["macroIntelLabel"], e["evMacroBull"], e["evMacroBear"],
                    {f: bool(e[{"Yield": "yield", "EURUSD": "eurusd", "SPX": "spx", "TIPS": "tips", "Silver": "silver",
                                "DXY": "dxy"}[f] + "Valid"]) for f in FEEDS}))
    return out


# ---------------- E4
E4L = [one(M, "float _rawGoldRet = "), one(M, "float _retClampW = "), one(M, "goldRet = math.min(math.max(_rawGoldRet"),
       one(M, "float retZScoreRaw = ")]
ABN = next(l.strip() for l in M if l.strip().startswith("bool regAbnormal = "))


def sma(x):
    return sum(x) / len(x)


def sd(x):
    m = sma(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / len(x))     # Pine ta.stdev: population (biased) by default


def run_gap(gap, n=400, sig=0.0005):
    closes, raw, gold, res = [2000.0], [0.0], [0.0], []
    for k in range(1, n + 1):
        c = closes[-1] * (1 + (gap if k == n - 20 else rng.gauss(0, sig)))
        closes.append(c)
        rr = c / closes[-2] - 1
        raw.append(rr)
        e = P.Env(close=c, funcs={})
        e["safeDiv"] = None
        P.BUILTINS["safeDiv"] = lambda a, b: P.NA if P.isna(a) or P.isna(b) or b == 0 else a / b
        e["close[1]"] = closes[-2]
        P.BUILTINS["ta.stdev"] = lambda *a, k_=k: sd(raw[max(0, k_ - 100):k_]) if k_ > 1 else P.NA
        P.BUILTINS["ta.sma"] = lambda *a, k_=k: sma(gold[max(0, k_ - 100):k_])
        lines = [l.replace("close[1]", "_c1").replace("ta.stdev(_rawGoldRet, 100)[1]", "ta.stdev(_rawGoldRet, 100)")
                 .replace("ta.sma(goldRet[1], 100)", "ta.sma(goldRet, 100)") for l in E4L]
        e["_c1"] = closes[-2]
        P.run(lines[:3], e)
        gold.append(e["goldRet"])
        P.BUILTINS["ta.stdev"] = lambda *a, k_=k: sd(gold[max(0, k_ - 100):k_])
        e["retMean100"] = sma(gold[max(0, k - 100):k])
        e["retStd100"] = sd(gold[max(0, k - 100):k])
        P.run([lines[3]], e)
        e.update(newsWindow=False, atrSma100R=1.0, adaptiveATR=1.0)
        res.append((rr, e["_retClampW"], e["goldRet"], e["retZScoreRaw"], P.evaluate(ABN.split(" = ", 1)[1], e)))
    return res, n - 20 - 1


# ---------------- E7
DEC = next(l.strip() for l in M if l.strip().startswith("_confDirLabel := _rkBlockedConf ? "))
CONF = [l.strip() for l in M if re.match(r"^\s+bool _(rk|tq)BlockedConf = ", l)]
ALB = next(l.strip() for l in M if l.startswith("if shouldBuy and not tqVeto and barstate.isconfirmed and not perfMode"))
ALS = next(l.strip() for l in M if l.startswith("if shouldSell and not tqVeto and barstate.isconfirmed and not perfMode"))


def run_alerts(cb, cs, T=4000, seed=7):
    r = random.Random(seed)
    prev, sent, bars = "WAIT", [], []
    sb = ss = False
    left = 0
    for t in range(T):
        if left == 0:
            u = r.random()
            sb, ss = (u < .12), (.12 <= u < .24)
            left = r.randint(1, 9) if (sb or ss) else r.randint(1, 4)
        left -= 1
        tq = r.random() < .08
        rk = r.random() < .03
        e = P.Env(shouldBuy=sb, shouldSell=ss, useRiskLimits=True, riskLock=rk, perfMode=False, _statsWarm=True,
                  _tqBlockedRaw=tq)
        e["barstate.isconfirmed"] = True
        e["tqVeto"] = tq or rk
        for l in CONF:
            P.run([l.replace("bool ", "", 1)], e)
        P.run([DEC.replace(":=", "=", 1)], e)
        e["_prevDec"] = prev
        b = P.evaluate(cb[3:].replace('_confDirLabel[1]', "_prevDec"), e)
        s = P.evaluate(cs[3:].replace('_confDirLabel[1]', "_prevDec"), e)
        sent.append((bool(b), bool(s)))
        bars.append(e["_confDirLabel"])
        prev = e["_confDirLabel"]
    return bars, sent


def expected(bars):
    return [(d == "BUY" and (i == 0 or bars[i - 1] != "BUY"), d == "SELL" and (i == 0 or bars[i - 1] != "SELL")) for i, d in enumerate(bars)]


# ---------------- E8
TRIAGE = {   # (array name): why `for 0 to array.size(A) - 1` cannot run on an empty A
    "_slC": "array.from(...) of 7 stop candidates: never empty",
    "_tpLvls": "array.from(...) of 10 target candidates: never empty",
    "_tpIdx": "array.sort_indices(_tpD) inside `if array.size(_tpD) > 0`: same size, never empty",
    "nwT": "the loop starts at nwI under `nwI < array.size(nwT)`",
}


def loop_scan():
    def ind(l):
        return len(l) - len(l.lstrip())
    bad, n = [], 0
    for f in sorted(glob.glob("artefacts/*.pine")):
        L = open(f, encoding="utf-8").read().split("\n")
        for i, l in enumerate(L):
            s = l.strip()
            m = re.match(r"for (\w+) = (\S+) to (.+?)(?: by .*)?$", s)
            if not m:
                continue
            a = re.fullmatch(r"array\.size\((\w+)\)\s*-\s*1", m.group(3)) or re.fullmatch(r"(\w+)\.size\(\)\s*-\s*1", m.group(3))
            if not a:
                continue
            n += 1
            arr, k, guard = a.group(1), ind(l), False
            for j in range(i - 1, max(-1, i - 80), -1):
                lj = L[j]
                if not lj.strip() or lj.strip().startswith("//"):
                    continue
                if ind(lj) < k:
                    if re.search(rf"(array\.size\({arr}\)|{arr}\.size\(\))\s*(>\s*0|>=\s*1|!=\s*0)", lj):
                        guard = True
                        break
                    k = ind(lj)
                    if k == 0:
                        break
            if not guard and arr not in TRIAGE:
                bad.append((f.split("/")[-1], i + 1, arr))
    return n, bad


def input_bounds():
    out = []
    for f in sorted(glob.glob("artefacts/*.pine")):
        L = open(f, encoding="utf-8").read().split("\n")
        inp = {}
        for l in L:
            m = re.match(r"^(\w+)\s*=\s*input\.int\((-?\d+).*?minval\s*=\s*(-?\d+).*?maxval\s*=\s*(-?\d+)", l)
            if m:
                inp[m.group(1)] = (int(m.group(3)), int(m.group(4)))
        for i, l in enumerate(L):
            s = l.strip()
            if s.startswith("//"):
                continue
            for m in re.finditer(r"array\.new_?\w*(?:<\w+>)?\(([^,)]+)", s):
                ids = set(re.findall(r"[A-Za-z_]\w*", m.group(1))) & set(inp)
                for v in ids:
                    for x in inp[v]:
                        val = P.evaluate(m.group(1), P.Env(**{v: float(x)}))
                        out.append((f.split("/")[-1], i + 1, f"size {m.group(1).strip()} at {v}={x}", val >= 1))
            m = re.match(r"for \w+ = (.+?) to (.+?)(?: by .*)?$", s)
            if m:
                ids = set(re.findall(r"[A-Za-z_]\w*", m.group(1) + " " + m.group(2))) & set(inp)
                for v in ids:
                    for x in inp[v]:
                        e = P.Env(**{v: float(x)})
                        try:
                            a_, b_ = P.evaluate(m.group(1), e), P.evaluate(m.group(2), e)
                        except Exception:          # noqa: BLE001  the bound also reads a non-input: not this check's case
                            continue
                        out.append((f.split("/")[-1], i + 1, f"loop {m.group(1)} to {m.group(2)} at {v}={x}", b_ >= a_))
    return out


if __name__ == "__main__":
    print("== E3  every macro feed missing / stale")
    T = 30
    for bull in (False, True):
        r = run_macro([{}] * T, bull)
        ok = all(s == 0 and lab == "N/A" and eb == 0 and er == 0 and not any(v.values()) for s, lab, eb, er, v in r)
        report(ok, f"all six feeds na for {T} bars, trend flags {'ALL bullish' if bull else 'random'}: score "
               f"{sorted({x[0] for x in r})}, label {sorted({x[1] for x in r})}, evidence bull / bear {sorted({x[2] for x in r})} / {sorted({x[3] for x in r})}")
    allp = {f: True for f in FEEDS}
    seq = [allp] * 5 + [{**allp, "DXY": False}] + [{**allp, "DXY": False}] + [allp]
    r = run_macro(seq, True)
    v = [x[4]["DXY"] for x in r]
    report(v == [True] * 5 + [False, False, True], f"DXY request missing (close and EMAs na together, as one request returns "
           f"them) drops the feed on that bar, back when it returns: valid per bar {v}")
    print("  INFO  F-A91: the one-bar stale cache never takes effect (the EMAs have no cache), and with barmerge.gaps_off a "
          "request is na only before its first value: a feed that STOPS updating stays frozen and valid, while the website "
          "drops a macro value older than 5 days (features.py MACRO_STALE_DAYS)")
    r = run_macro([{"TIPS": True}] * 5, True, tips_on=True)
    print(f"  INFO  F-A89 (both engines, the website's macro_valid_any omits TIPS too): TIPS the only live feed -> label "
          f"{r[-1][1]!r} with score {r[-1][0]} (the score still feeds the evidence lines: {r[-1][2]} / {r[-1][3]})")
    print("== E4  a +/-3% gap on a quiet 5-minute series")
    for g in (0.03, -0.03):
        res, gi = run_gap(g)
        rr, cw, gr, z, ab = res[gi]
        after = [x[4] for x in res[gi + 1:gi + 6]]
        nan = any(any(isinstance(v, float) and math.isnan(v) for v in x[:4]) for x in res[1:])
        report(abs(gr) == cw and 0.002 <= cw <= 0.05 and abs(z) > 3 and ab and not nan and not any(after),
               f"gap {g:+.0%}: raw return {rr:+.4f} clamped to {gr:+.4f} (window {cw:.4f}), z {z:+.1f} -> ABNORMAL {ab}; "
               f"the next 5 bars ABNORMAL {after}; NaN anywhere: {nan}")
    print("== E7  rapid signals: one BUY / SELL alert per run, on its first bar")
    bars, sent = run_alerts(ALB, ALS)
    want = expected(bars)
    runs_b = sum(want_[0] for want_ in want)
    flips = sum(1 for i in range(1, len(bars)) if {bars[i], bars[i - 1]} == {"BUY", "SELL"})
    report(sent == want and not any(b and s for b, s in sent),
           f"4000 bars, {runs_b} BUY runs, {sum(w[1] for w in want)} SELL runs, {flips} direct flips: alerts == the first bar "
           f"of each run: {sent == want}; both on one bar: {any(b and s for b, s in sent)}")
    old_b = ALB.replace(' and _confDirLabel[1] != "BUY"', "")
    old_s = ALS.replace(' and _confDirLabel[1] != "SELL"', "")
    assert old_b != ALB and old_s != ALS
    b2, s2 = run_alerts(old_b, old_s)
    rep = sum(x[0] for x in s2) - sum(w[0] for w in expected(b2))
    report(rep > 0, f"control: the v99 condition (no [1] term) sends {rep} repeated BUY alerts on the same bars")
    print("== E8  runtime errors: empty-array loops and input extremes")
    n, bad = loop_scan()
    report(not bad, f"{n} loops `for .. to array.size(A) - 1` in 9 files: every one size-guarded or triaged "
           f"({', '.join(sorted(TRIAGE))})" + ("" if not bad else f"; UNGUARDED: {bad}"))
    ib = input_bounds()
    report(all(x[3] for x in ib) and len(ib) > 0, f"{len(ib)} input-bounded sizes / loop ends at minval and maxval: "
           + ("all valid" if all(x[3] for x in ib) else str([x for x in ib if not x[3]])))
    print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- the Master's / Visuals' lines executed in Python; "
          "TradingView runtime NOT exercised")
    sys.exit(1 if fails else 0)
