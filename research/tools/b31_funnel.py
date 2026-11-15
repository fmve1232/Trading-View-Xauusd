"""B31 diagnostic (after the run, development data only, no rule changed): the A / B funnel from rejected sweeps
to setups, the density of the frozen engine's structure events and FVGs without volume, and the A / B stop distances.

  python research/tools/b31_funnel.py <research-data dir>
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, ".")
from quantum import engine
from quantum.config import DEFAULT
from quantum.features import compute as compute_features
from quantum.research import b31, b10, history, harness as H
rd = sys.argv[1]
m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
m = b10.make_market(m15, h1, "15m", 900); F = compute_features(m, DEFAULT); res = engine.run(m, DEFAULT, "treatment", F)
X = b31.make_ctx(m15, h1, res, F)
n = len(X.c)
print("bars", n, "struct events/1000 bars: any up", round(X.up_any.sum() / n * 1000, 1), "shift up", round(X.up_shift.sum() / n * 1000, 1),
      "| FVG bull bars/1000", round(sum(b31.fvg_at(X, i, 1) is not None for i in range(n)) / n * 1000, 1))
evs = [e for e in b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE) if e["status"] == "REJECTED"]
f = dict(rejected=len(evs), any_struct=0, shift_struct=0, A_misaligned=0, B_aligned=0, zone_fvg=0, zone_ob=0)
D = []
for ev in evs:
    d, j = ev["dir"], ev["j"]
    w = range(ev["k"], min(j + b31.SHIFT_BARS, n - 1) + 1)
    anyb = [mm for mm in w if (X.up_any[mm] if d == 1 else X.dn_any[mm])]
    shb = [mm for mm in w if (X.up_shift[mm] if d == 1 else X.dn_shift[mm])]
    f["any_struct"] += bool(anyb); f["shift_struct"] += bool(shb)
    for need in ("A", "B"):
        s = b31.seq_sweep(X, ev, need)
        if s:
            f["A_misaligned" if need == "A" else "B_aligned"] += 1
            f["zone_fvg" if s["entry_type"] == "FVG" else "zone_ob"] += 1
            e = s["limit"]; D.append((e - s["stop"]) * d / (e / 4000))
print(f)
D = np.array(D)
if len(D):
    print("A/B stop distance $ (scaled): median", round(float(np.median(D)), 2), "quartiles", np.round(np.percentile(D, [25, 75]), 2).tolist(),
          "share in [5, 8.4]:", round(float(((D >= 5) & (D <= 8.4)).mean()), 3))
pen = np.array([e["pen"] / (e["lv"] / 4000) for e in evs])
print("sweep penetration $: median", round(float(np.median(pen)), 2), "| rejected on the 1st bar", round(float(np.mean([e["bars"] == 1 for e in evs])), 3))
