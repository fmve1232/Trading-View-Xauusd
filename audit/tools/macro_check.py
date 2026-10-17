#!/usr/bin/env python3
"""Macro correlations pair returns over the SAME completed bar (v64, F-A64).

  A. structure (every engine copy, read as written; since v65 each f_cc3 call is expanded through the function body,
     which is checked): each `_ccGold<X>_<w> = ta.correlation(G, R, L)` is traced from
     R back through `R = ... safeDiv(C, C[1]) - 1`, `C = cached<X>`, `cached<X> := _raw<X>` to the request.security
     call that feeds it, and its timeframe and lookahead are read off that call. Then:
       - an asset requested on the chart timeframe (timeframe.period) is paired with goldRetL = goldRet[1];
       - an asset requested on macroTF is paired with goldRetM, built from a request of the chart symbol with the
         SAME timeframe, the same `close[1]` and the same lookahead; its window is the macroTF-bar window (x _kM)
         and its result is gated by the window-fits flag of that length;
       - nothing is paired with goldRet itself (this bar's return against the asset's previous bar).
  B. model (Python, NOT the Pine runtime): bars with a known true same-period correlation, run through the request
     semantics (close[1]; lookahead_on on a higher timeframe, held between its bars) and the pairing above, on 15M
     and 1H charts. The v64 pairing must recover the true correlation; the v63 pairing must not (so B discriminates).

  C. each factor once (v65, F-A65), executed (pine_exec) on the engine's own lines in every copy: with DXY valid,
     EURUSD never moves a vote, a weight or the score; EURUSD is the USD vote only when DXY has no data; a TIPS
     symbol equal to the 10Y yield's never contributes; the majority is ceil(pool / 2) over USD / 10Y / SPX / silver
     (+ TIPS when its own feed, + GC when valid).

  D. the Brief's five display-only drivers (v65, option 4), executed as written: each arrow points the way the driver
     moves gold (USDJPY / real yield / US 2Y rising = down; oil / breakeven rising = up), flat = neutral, no data = —,
     and USDJPY / oil are neutral when |r| <= 0.25, as the engine's DXY arrow.

Usage: python3 audit/tools/macro_check.py [file ...]     (default: the engine copies)"""
import math
import random
import re
import statistics as st
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import pine_exec as P  # noqa: E402

A = "artefacts/XAUUSD_Quantum_5_0_"
FILES = sys.argv[1:] or [A + f + ".pine" for f in ("Master", "Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER",
                                                  "Diagnostics", "Brief")]
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def req_of(L, raw):
    """(timeframe, lookahead, expression) of the request.security call whose tuple / variable includes `raw`."""
    for l in L:
        m = re.match(r"^(?:float |int )?(\[[^\]]*\]|\w+) = (?:.*\? )?request\.security\(([^,]+), ([^,]+), (.*)$", l)
        if m and re.search(rf"\b{re.escape(raw)}\b", m.group(1)):
            names = [x.strip() for x in m.group(1).strip("[]").split(",")]
            rest = m.group(4)
            parts = P._split_args(rest)             # bracket-aware: [close[1], ta.ema(close[1], 10), ...]
            expr = P._split_args(parts[0].strip()[1:-1]) if parts[0].strip().startswith("[") else [parts[0]]
            look = "on" if "lookahead_on" in rest else "off"
            return m.group(3).strip(), look, expr[names.index(raw)].strip()
    return None


for path in FILES:
    print(f"== {path.split('/')[-1]}")
    L = open(path, encoding="utf-8").read().split("\n")
    code = [l for l in L if not l.lstrip().startswith("//")]
    # v65: the correlations are f_cc3 calls; expand each through the function body (checked to be the expected shape)
    fh = next((i for i, l in enumerate(code) if l.startswith("f_cc3(")), None)
    if fh is not None:
        body = [l.strip() for l in code[fh + 1:fh + 5]]
        report(body == ["float x = ta.correlation(g, r, a)", "float y = ta.correlation(g, r, b)",
                        "float z = ta.correlation(g, r, c)", "[v and fa ? x : na, v and fb ? y : na, v and fc ? z : na]"],
               "f_cc3: three ta.correlation(g, r, window) computed every bar, each gated after by v and its fit flag")
        prm = [x.split()[-1] for x in code[fh][6:code[fh].index(")")].split(",")]
        for l in [l for l in code if re.match(r"^\[corrGold\w+_30, corrGold\w+_60, corrGold\w+_120\] = f_cc3\(", l)]:
            asset = re.match(r"^\[corrGold(\w+)_30", l).group(1)
            g = dict(zip(prm, P._split_args(l[l.index("f_cc3(") + 6:-1])))
            for w, ln, fl in (("30", "a", "fa"), ("60", "b", "fb"), ("120", "c", "fc")):
                code.append(f"_ccGold{asset}_{w} = ta.correlation({g['g']}, {g['r']}, {g[ln]})")
                code.append(f"corrGold{asset}_{w} = {g['v']} and {g[fl]} ? _ccGold{asset}_{w} : na")
    cc = [(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)) for l in code
          for m in [re.match(r"^_ccGold(\w+?)_(\d+) = ta\.correlation\((\w+), (\w+), (\w+)\)$", l)] if m]
    report(len(cc) == 18, f"{len(cc)} correlation lines (6 assets x 3 windows)")
    gm = req_of(code, "_gM")
    gl = next((l for l in code if l.startswith("float goldRetL = ")), "")
    gmr = next((l for l in code if l.startswith("float goldRetM = ")), "")
    report(gl == "float goldRetL = goldRet[1]", "goldRetL is gold's previous-bar return (goldRet[1])")
    report(gm is not None and gm[2] == "close[1]" and "safeDiv(_gM, _gM[1]) - 1" in gmr,
           f"goldRetM is the return of the chart symbol requested as {gm} ")
    bad = []
    for asset, w, g, ret, ln in cc:
        d = next((l for l in code if l.startswith(f"{ret} = ")), None)
        c = re.search(r"safeDiv\((\w+), \1\[1\]\) - 1", d or "")
        cl = next((l for l in code if c and l.startswith(f"{c.group(1)} = ")), "")
        cached = cl.split(" = ", 1)[1].strip() if cl else None
        rawl = next((l for l in code if cached and l.strip().startswith(f"{cached} := ")), "")
        raw = rawl.split(":=", 1)[1].strip() if rawl else None
        rq = req_of(code, raw) if raw else None
        if rq is None:
            bad.append(f"{asset}_{w}: cannot trace {ret} to its request")
            continue
        tf, look, expr = rq
        if g == "goldRet":
            bad.append(f"{asset}_{w}: gold THIS bar vs {ret} built from {expr} (the bar before)")
        elif tf == "timeframe.period":
            if g != "goldRetL" or expr != "close[1]":
                bad.append(f"{asset}_{w}: chart-TF asset ({expr}) paired with {g}")
        else:
            gate = next((l for l in code if l.startswith(f"corrGold{asset}_{w} = ")), "")
            wl = next((l for l in code if l.startswith(f"int {ln} = math.min(")), "")
            fit = re.search(r"and (\w+) \?", gate)
            fl = next((l for l in code if fit and l.startswith(f"bool {fit.group(1)} = ")), "")
            base = re.search(r"math\.min\((\w+) \* _kM, (\d+)\)", wl)
            if g != "goldRetM" or gm is None or (tf, look) != gm[:2] or expr != "close[1]":
                bad.append(f"{asset}_{w}: {tf}/{look} asset paired with {g} ({gm})")
            elif not base or not fl or fl.split(" = ", 1)[1] != f"{base.group(1)} * _kM <= {base.group(2)}":
                bad.append(f"{asset}_{w}: window {ln} not the fitted macroTF-bar window ({wl!r}, {fl!r})")
    report(not bad, "every correlation pairs gold and the asset over the same completed bar, macroTF windows in "
                    "macroTF bars" + "".join("\n        " + b for b in bad[:6]))

# ---- C: each factor once, executed on the engine's own lines (pine_exec)
print("== each macro factor counted once (executed)")
for path in FILES:
    L = open(path, encoding="utf-8").read().split("\n")
    def ln(pre):
        h = [l for l in L if l.startswith(pre)]
        assert len(h) == 1, (path, pre, len(h))
        return h[0]
    try:
        tl = [ln("bool _tipsOn = "), ln("tipsValid = ")]
        votes = [ln("macroBullVotes = "), ln("macroBearVotes = "), ln("int _macroPool = "), ln("int _macroNeed = "),
                 ln("macroBull = "), ln("macroBear = ")]
    except AssertionError as err:
        report(False, f"{path.split('/')[-1]}: no factor-once structure ({err.args[0][1]!r} missing)")
        continue
    a = next(i for i, l in enumerate(L) if l.startswith("_wDXYr = "))
    b = next(i for i, l in enumerate(L) if l.startswith("macroStrengthScore = "))
    chain = [l for l in L[a:b + 1] if l.strip() and not l.lstrip().startswith("//")]
    P.BUILTINS["math.ceil"] = lambda x: float(math.ceil(x))
    rng2 = random.Random(65)
    bad = {"eur moves score/vote with DXY valid": 0, "eur not the USD vote without DXY": 0,
           "duplicate TIPS contributes": 0, "majority rule": 0}
    n = 0
    for _ in range(3000):
        e = P.Env(MACRO_STALE_MAX=2.0, tipsStaleCount=0.0, tipsClose=1.0, _rawTIPSFast=1.0, _rawTIPSSlow=1.0,
                  yieldSymbol="TVC:US10Y", tipsSymbol=rng2.choice(["TVC:US10Y", "FRED:DFII10", ""]))
        P.run(tl, e)
        B = lambda: rng2.random() < 0.5
        for k in ("dxyValid", "yieldValid", "spxValid", "silverValid", "eurusdValid", "gcValid"):
            e[k] = rng2.random() < 0.8
        for up, dn, v in (("dxyBull", "dxyBear", "dxyValid"), ("eurusdBull", "eurusdBear", "eurusdValid"),
                          ("yieldRising", "yieldFalling", "yieldValid"), ("spxBull", "spxBear", "spxValid"),
                          ("silverBull", "silverBear", "silverValid"), ("tipsRising", "tipsFalling", "tipsValid"),
                          ("gcConfirmsBull", "gcConfirmsBear", "gcValid")):
            x = B() if e[v] else False
            e[up], e[dn] = x, (not x and B()) if e[v] else False
        for k in ("avgCorrDXY", "avgCorrYld", "avgCorrSlv", "avgCorrSPX", "avgCorrEUR", "avgCorrTIPS"):
            e[k] = rng2.uniform(-0.9, 0.9) if B() else 0.0
        e.update(silverClose=1.0 + rng2.choice([-0.1, 0, 0.1]), silverEMA=1.0, dxyMomBear=B(), dxyMomBull=False,
                 ratePressureDown=B(), ratePressureUp=False, eurusdROC=rng2.choice([-0.3, 0.0, 0.3]), invertYield=False)
        def run(env):
            q = P.Env(funcs={}, **env)
            P.run(votes + chain, q)
            return q
        base = run(e)
        n += 1
        flip = dict(e, eurusdBull=not e["eurusdBull"] and e["eurusdValid"], eurusdBear=e["eurusdBull"] and e["eurusdValid"],
                    eurusdROC=-e["eurusdROC"], avgCorrEUR=-e["avgCorrEUR"] if e["avgCorrEUR"] else 0.5)
        other = run(flip)
        moved = any(base[k] != other[k] for k in ("macroBullVotes", "macroBearVotes", "macroStrengthScore"))
        if e["dxyValid"]:
            bad["eur moves score/vote with DXY valid"] += moved
        elif e["eurusdValid"]:
            want = (1 if e["gcConfirmsBull"] else 0) + (1 if e["eurusdBull"] else 0) + (1 if e["yieldFalling"] else 0) + \
                   (1 if e["spxBull"] else 0) + (1 if e["silverBull"] else 0) + (1 if e["tipsFalling"] else 0)
            bad["eur not the USD vote without DXY"] += base["macroBullVotes"] != want
        if e["tipsSymbol"] == e["yieldSymbol"]:
            bad["duplicate TIPS contributes"] += bool(e["tipsValid"]) or bool(base["msTIPS"])
        pool = 4 + (e["tipsSymbol"] != e["yieldSymbol"]) + bool(e["gcValid"])
        bad["majority rule"] += base["_macroPool"] != pool or base["_macroNeed"] != math.ceil(pool / 2) or \
            bool(base["macroBull"]) != (base["macroBullVotes"] >= math.ceil(pool / 2))
    report(not any(bad.values()), f"{path.split('/')[-1]}: {n} states; " + ", ".join(f"{k} {v}" for k, v in bad.items()))

# ---- D: the Brief's five display-only drivers, executed as written
print("== Brief: five display-only drivers (executed)")
BP = "artefacts/XAUUSD_Quantum_5_0_Brief.pine"
BL = open(BP, encoding="utf-8").read().split("\n")
benv = P.Env(funcs={}, _fM=True)       # f_brRv reads the global fit flag (its defining scope)
for head in ("f_brS(bool up, bool dn) =>", "f_brM(bool v, bool up, bool dn, float r) =>", "f_brUp(float c, float f, float s) =>",
             "f_brDn(float c, float f, float s) =>", "f_brRv(bool v, float r) =>"):
    P.define([next(l for l in BL if l.startswith(head))], benv)
P.BUILTINS["nz"] = lambda x, y=0.0: y if P.isna(x) else x
cells = {}
for l in BL:
    m = re.match(r'^\s+f_brA\((2[4-8]), "([^"]+)", (.*)\)$', l)
    if m:
        cells[m.group(2)] = P._split_args(m.group(3))[0]
# driver -> (close, ema10, ema20 names, valid name, corr name or None, +1 if RISING supports gold up)
DRV = {"USDJPY": ("brJ", "brJv", "brJr", -1), "OIL": ("brO", "brOv", "brOr", 1), "REAL YLD": ("brR", "brRv", None, -1),
       "BREAKEVEN": ("brB", "brBv", None, 1), "US 2Y": ("br2", "br2v", None, -1)}
bad, n = [], 0
for name, (pre, vv, rr, sign) in DRV.items():
    if name not in cells:
        bad.append(f"{name}: cell missing")
        continue
    for state, (c, f, s_) in (("rising", (3.0, 2.0, 1.0)), ("falling", (1.0, 2.0, 3.0)), ("flat", (2.0, 2.5, 2.0))):
        for valid in (True, False):
            for r in ((0.6, 0.3, 0.1) if rr else (None,)):
                e = P.Env(funcs=benv.funcs, _fM=True)
                e.update({pre + "c": c, pre + "f": f, pre + "s": s_, vv: valid})
                if rr:
                    e[rr] = r
                d = P.evaluate(cells[name], e)
                n += 1
                want = None if not valid else 0.0 if state == "flat" else (sign if state == "rising" else -sign)
                if want and rr:
                    want *= 2.0 if r > 0.5 else 1.0 if r > 0.25 else 0.0
                ok = P.isna(d) if want is None else (not P.isna(d) and d == want)
                if not ok:
                    bad.append(f"{name} {state} valid={valid} r={r}: d={d}, want {want}")
report(not bad and len(cells) == 5, f"5 drivers, {n} cases: impact direction, strength by |r|, flat neutral, no data —"
       + "".join("\n        " + b for b in bad[:5]))

# ---- B: model of the request semantics (Python; the TradingView runtime is NOT exercised)
print("== model: known true correlation through the request semantics")
rng = random.Random(64)


def corr(a, b):
    ma, mb = st.fmean(a), st.fmean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else 0.0


def windows(a, b, n):
    return st.fmean(corr(a[i - n:i], b[i - n:i]) for i in range(n, len(a), n))


for k, label in ((1, "chart TF = macroTF (or same-TF asset)"), (4, "15M chart, 1H macroTF")):
    for rho in (0.8, -0.6):
        H = 3000                                           # macroTF bars
        G, X = [1.0], [1.0]
        for _ in range(H * k):
            z1 = rng.gauss(0, 1)
            z2 = rho * z1 + math.sqrt(1 - rho * rho) * rng.gauss(0, 1)
            G.append(G[-1] * math.exp(0.001 * z1))
            X.append(X[-1] * math.exp(0.001 * z2))
        # value on chart bar t of a macroTF request of close[1], lookahead_on: the close of the macroTF bar before
        # the one containing t, i.e. the chart close at index k*(t//k)  (for k = 1 that is close[1] of the chart)
        held = (lambda S: [S[k * (t // k)] if k > 1 else S[t - 1] for t in range(len(S))])
        Gm, Xm = held(G), held(X)
        T = range(2 * k + 2, len(G))
        xr = [Xm[t] / Xm[t - 1] - 1 for t in T]
        v64 = [Gm[t] / Gm[t - 1] - 1 for t in T]            # goldRetM (k = 1: equals goldRet[1])
        v63 = [G[t] / G[t - 1] - 1 for t in T]              # goldRet: this bar
        r64, r63 = windows(v64, xr, 60 * k), windows(v63, xr, 60 * k)
        report(abs(r64 - rho) < 0.05 and abs(r63 - rho) > 0.3,
               f"{label}, true r {rho:+.2f}: v64 pairing {r64:+.3f}, v63 pairing {r63:+.3f}")

print(f"RESULT: {'PASS' if fails == 0 else 'FAIL'} -- A read from the Pine as written; B is a Python model of the "
      "request semantics; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
