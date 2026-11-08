"""B27 null check: the whole framework (quantum.research.b27.run) on synthetic random walks, which have no edge by
construction. Every configuration should fail; any that passes is a false positive of the framework.

  python research/tools/b27_null_check.py <out dir>
"""
import sys
import time
import types

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.data import sources
from quantum.research import b27
from quantum.research import harness as H


def walk5(start, end, seed):
    idx = pd.date_range(start, end, freq="5min", tz="UTC", inclusive="left")
    idx = idx[~sources.gold_shut(idx)]
    rng = H.seeded_rng(seed)
    c = 4000 + np.cumsum(rng.normal(0, 2.1, len(idx)))
    o = np.r_[4000.0, c[:-1]]
    hi = np.maximum(o, c) + np.abs(rng.normal(0, .8, len(idx))); lo = np.minimum(o, c) - np.abs(rng.normal(0, .8, len(idx)))
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": np.nan}, index=idx)

def pops(*_a, **_k):
    d5 = walk5("2020-03-01", "2021-04-15", 1)
    m15d, h1d = sources.resample_ohlc(d5, "15min"), sources.resample_ohlc(d5, "1h")
    y5 = walk5("2026-01-01", "2026-11-07", 2)
    m15y, h1y = sources.resample_ohlc(y5, "15min"), sources.resample_ohlc(y5, "1h")
    return {"DEV": {"m15": m15d, "h1": h1d, "score_from": pd.Timestamp("2020-04-01", tz="UTC"), "scale": True},
            "Y2026": {"m15": m15y, "h1": h1y, "score_from": pd.Timestamp("2026-03-01", tz="UTC"), "scale": False,
                      "df5": y5[y5.index >= "2026-09-10"]}}

b27.load_pops = pops
t = time.time()
out = b27.run(types.SimpleNamespace(rd=None, store5=None, store60=None, md=None), log=lambda m: print(m, flush=True))
b27.write(out, sys.argv[1], None)
print("smoke ok", round(time.time() - t), "s", out["counts"])
