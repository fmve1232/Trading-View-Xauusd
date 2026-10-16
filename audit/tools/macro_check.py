#!/usr/bin/env python3
"""Macro correlations pair returns over the SAME completed bar (v64, F-A64).

  A. structure (every engine copy, read as written): each `_ccGold<X>_<w> = ta.correlation(G, R, L)` is traced from
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
