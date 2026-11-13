"""Stage-2 correction: the VIX regime split of xasset_corr.py with a 2026-only threshold (read-only).

  python3 -I audit/tools/v2_vix_regime.py <research-data dir> <market-data store dir> <out.json>

Stage 1 split hours by "VIX above its past median" using an expanding median over VIX closes from 2016, which includes
the sealed 2023-01-24 .. 2026-01-01 span. Here the median expands over 2026 closes only (from the 20th close on), each
hour compared with the previous day's close."""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xasset_corr as X  # noqa: E402

RD, STORE, OUT = sys.argv[1:4]
CUT = pd.Timestamp("2026-01-01", tz="UTC")
x15 = X.load(os.path.join(RD, "TD_XAU_USD_15min"))
s15 = X.load(os.path.join(STORE, "XAU_USD_15m"))
x = pd.concat([x15, s15[s15.index > x15.index[-1]]]).sort_index()
px = X.xau_price(x[x.index >= CUT - pd.Timedelta(minutes=15)])
vix = X.load(os.path.join(STORE, "_VIX_1d"))["close"]
v = pd.Series(vix.to_numpy(float), index=vix.index.normalize())
v = v[v.index >= CUT]
med = v.expanding(min_periods=20).median()
res = {}
for name, folder in X.SERIES.items():
    df = X.load(os.path.join(STORE, folder))
    sp = X.spans(df[df.index >= CUT])
    g = np.log(X.p_at(px, pd.DatetimeIndex(sp["end"])) / X.p_at(px, pd.DatetimeIndex(sp["start"])))
    day = sp["start"].dt.normalize() - pd.Timedelta(days=1)
    pv = v.reindex(day, method="ffill").to_numpy()
    pm = med.reindex(day, method="ffill").to_numpy()
    r = sp["r"].to_numpy()
    ok = ~np.isnan(g) & ~np.isnan(r) & ~np.isnan(pv) & ~np.isnan(pm)
    hi, lo = ok & (pv > pm), ok & (pv <= pm)
    res[name] = {"above": {"n": int(hi.sum()), "r": X.pear(r[hi], g[hi])}, "at_or_below": {"n": int(lo.sum()), "r": X.pear(r[lo], g[lo])}}
    print(f"{name:13s} VIX above its 2026 median: r {res[name]['above']['r']:+.3f} (n {res[name]['above']['n']}) | at or below: r {res[name]['at_or_below']['r']:+.3f} (n {res[name]['at_or_below']['n']})")
json.dump(res, open(OUT, "w"), indent=1)
