"""Census of revised closed bars between consecutive store snapshots, volume separated from price (read-only).

Usage: python audit/tools/aux_revision_census.py <snapshot dir>:<epoch> [<snapshot dir>:<epoch> ...]
Snapshots in time order; <epoch> is the snapshot's store commit time. For each consecutive pair (A, B) and each series,
only bars that had CLOSED by A's time and exist in both are compared (a forming bar finishing is not a revision):
  price_changed   bars whose open / high / low / close differ (|d| > 1e-6)
  volume_changed  bars whose volume differs (|d| > 1e-6)
  volume_only     bars whose volume differs while all four prices are equal
  removed         closed bars of A missing from B
with the largest relative close change and the median / largest relative volume change. Prints JSON.
Unlike quantum/manifest.py (which records price columns only), volume is counted here."""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from quantum.data import store  # noqa: E402

BAR = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "1d": 86400}
PRICE = ["open", "high", "low", "close"]


def series(d):
    return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)) and x.rsplit("_", 1)[-1] in BAR)


def compare(a_dir, a_t, b_dir):
    out = {}
    for nm in series(a_dir):
        if not os.path.isdir(os.path.join(b_dir, nm)):
            continue
        a, b = store.load(a_dir, nm), store.load(b_dir, nm)
        if a is None or b is None:
            continue
        sec = BAR[nm.rsplit("_", 1)[-1]]
        epoch = (a.index - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)   # unit-safe (the store is in us)
        closed = a.index[epoch + sec <= a_t]
        com = closed.intersection(b.index)
        pc = [c for c in PRICE if c in a.columns and c in b.columns]
        A, B = a.loc[com, pc].astype(float), b.loc[com, pc].astype(float)
        dp = ~np.isclose(A.to_numpy(), B.to_numpy(), rtol=0, atol=1e-6, equal_nan=True)
        p_ch = dp.any(axis=1)
        if "volume" in a.columns and "volume" in b.columns:
            va, vb = a.loc[com, "volume"].astype(float).to_numpy(), b.loc[com, "volume"].astype(float).to_numpy()
            dv = ~np.isclose(va, vb, rtol=0, atol=1e-6, equal_nan=True)
            rel = np.abs(vb - va) / np.where(np.abs(va) > 0, np.abs(va), np.nan)
            relc = rel[dv & ~np.isnan(rel)]
        else:
            dv, relc = np.zeros(len(com), bool), np.array([])
        cr = (np.abs(B["close"] - A["close"]) / A["close"].abs()).to_numpy() if "close" in pc else np.array([0.0])
        out[nm] = {"closed_compared": int(len(com)), "price_changed": int(p_ch.sum()), "volume_changed": int(dv.sum()),
                   "volume_only": int((dv & ~p_ch).sum()), "removed": int(len(closed.difference(b.index))),
                   "max_rel_close_pct": round(float(np.nanmax(cr)) * 100, 4) if len(cr) else 0.0,
                   "median_rel_volume_pct": round(float(np.median(relc)) * 100, 2) if len(relc) else 0.0,
                   "max_rel_volume_pct": round(float(np.max(relc)) * 100, 1) if len(relc) else 0.0,
                   "newest_changed_bar": (str(com[p_ch | dv].max()) if (p_ch | dv).any() else None)}
    return out


def main():
    snaps = [(p.rsplit(":", 1)[0], int(p.rsplit(":", 1)[1])) for p in sys.argv[1:]]
    res = []
    for (a, at), (b, bt) in zip(snaps, snaps[1:]):
        res.append({"from": os.path.basename(a), "to": os.path.basename(b), "hours": round((bt - at) / 3600, 2),
                    "series": compare(a, at, b)})
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
