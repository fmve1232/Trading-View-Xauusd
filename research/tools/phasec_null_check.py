"""Phase C null check: B28 and B29 (quantum.research.b28.run / b29.run) on synthetic random walks, which have no edge
by construction. Any configuration flagged is a false positive of the framework; crashes show up here first.

  python research/tools/phasec_null_check.py <out dir> [B28,B29]
"""
import sys
import time
import types

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.data import sources
from quantum.research import b27, b28, b29
from quantum.research import harness as H


def walk5(start, end, seed):
    """A path-consistent random walk: 1-minute steps aggregated to 5m bars (highs / lows are the path's own extremes),
    market-shut minutes removed. Independent-noise wicks are not a valid null for exit geometry (B29 amendment 3)."""
    idx = pd.date_range(start, end, freq="1min", tz="UTC", inclusive="left")
    idx = idx[~sources.gold_shut(idx)]
    rng = H.seeded_rng(seed)
    x = 4000 + np.cumsum(rng.normal(0, 0.95, len(idx)))
    m1 = pd.DataFrame({"open": np.r_[4000.0, x[:-1]], "close": x}, index=idx)
    m1["high"], m1["low"] = m1[["open", "close"]].max(axis=1), m1[["open", "close"]].min(axis=1)
    m5 = m1.resample("5min", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    m5["volume"] = np.nan
    return m5


def pops(*_a, **_k):
    d5 = walk5("2020-03-01", "2021-04-15", 1)
    y5 = walk5("2026-01-01", "2026-11-07", 2)
    return {"DEV": {"m15": sources.resample_ohlc(d5, "15min"), "h1": sources.resample_ohlc(d5, "1h"),
                    "score_from": pd.Timestamp("2020-04-01", tz="UTC"), "scale": True},
            "Y2026": {"m15": sources.resample_ohlc(y5, "15min"), "h1": sources.resample_ohlc(y5, "1h"),
                      "score_from": pd.Timestamp("2026-03-01", tz="UTC"), "scale": False, "df5": y5[y5.index >= "2026-09-10"]}}


if __name__ == "__main__":
    b27.load_pops = pops
    args = types.SimpleNamespace(rd=None, store5=None, store60=None)
    want = sys.argv[2].split(",") if len(sys.argv) > 2 else ["B28", "B29"]
    for name, mod in (("B28", b28), ("B29", b29)):
        if name not in want:
            continue
        t = time.time()
        out = mod.run(args, log=lambda m: print(m, flush=True))
        mod.write(out, f"{sys.argv[1]}/{name.lower()}", None)
        print(name, "null check ok", round(time.time() - t), "s", out["counts"], flush=True)
