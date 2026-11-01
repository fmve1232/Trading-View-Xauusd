"""Operator target (2026-11-01): "more than 90% of trades move at least $10-20 in the same direction after the
decision trigger". Measured, not tuned. Read-only; nothing is changed.

Usage (repo root):
    TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/target_move_study.py <market-data copy> <forward-ledger checkout> out.json

Event, for a trigger at price P with direction d (the close of the trigger bar):
    WIN   price reaches P + d*a (a = $10, $15, $20) BEFORE it reaches P - d*b (the room allowed against the trade)
    LOSS  the adverse level first; a 5-minute bar touching both counts as LOSS (no ticks; conservative)
    OPEN  neither within the horizon (1 day = 288 five-minute bars; 3 days)
Paths are walked on 5-minute bars (the finest stored data) from the first bar opening at or after the trigger bar's
close. A bar reaching both levels counts as LOSS unless it opened beyond the target. Triggers whose horizon runs past
the end of the stored window are not counted (no partial paths).

Driftless benchmark (gambler's ruin): P(+a before -b) = b / (a + b). A direction-matched random baseline is measured
on the same 5-minute window: every 5-minute close as an entry, long and short separately.

Trigger sources (all on the stored window, in-sample except the recorded forward trades):
    engine treatment / control / challenger, H2, H3, H4, H5, H6 signals on 15m and 5m; the recorded web.6 forward
    trades (archived ledger, real time).
"""
import glob
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from quantum.data import market as mk, sources as _src  # noqa: E402


def _off(*a, **k):
    raise _src.FetchError("offline audit run")


_src._get = _off
from quantum import arm_h2, arm_h3, arm_h4, arm_h5, arm_h6, engine  # noqa: E402
from quantum.config import DEFAULT  # noqa: E402

A = (2.0, 5.0, 10.0, 15.0, 20.0)
B = (5.0, 10.0, 15.0, 20.0, 30.0, 50.0, 90.0)
HZ = {"1d": 288, "3d": 864}
TF_SEC = {"5m": 300, "15m": 900}


def wilson(k, n, z=1.959964):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


class Path:
    def __init__(self, m5):
        self.t = m5.index.tz_convert("UTC").tz_localize(None).to_numpy().astype("datetime64[s]").astype(np.int64)
        self.o, self.h, self.l = (m5[x].to_numpy(float) for x in ("open", "high", "low"))

    def excursions(self, t_close, p, d, H):
        """Running maximum favourable / adverse excursion (in $) over the next H five-minute bars, and the opens."""
        j = int(np.searchsorted(self.t, t_close))
        if j >= len(self.t) or j + H > len(self.t):
            return None                                      # not fully covered by the stored window
        h, l, o = self.h[j:j + H], self.l[j:j + H], self.o[j:j + H]
        fav = (h - p) if d > 0 else (p - l)
        adv = (p - l) if d > 0 else (h - p)
        return np.maximum.accumulate(fav), np.maximum.accumulate(adv), (o - p) * d

    @staticmethod
    def outcome(ex, a, b):
        """1 WIN, 0 LOSS, -1 OPEN. A bar reaching both levels is a LOSS unless it OPENED beyond the target."""
        cf, ca, od = ex
        ia, ib = int(np.searchsorted(cf, a, "left")), int(np.searchsorted(ca, b, "left"))
        n = len(cf)
        if ia >= n and ib >= n:
            return -1
        if ia < ib:
            return 1
        if ib < ia:
            return 0
        return 1 if od[ia] >= a else 0


def table(path, trig, label):
    """trig: list of (t_close_epoch, price, dir)."""
    out = {"label": label, "n_triggers": len(trig), "long": sum(1 for x in trig if x[2] > 0), "short": sum(1 for x in trig if x[2] < 0), "cells": {}}
    for hz, H in HZ.items():
        exs = [e for e in (path.excursions(t, p, d, H) for t, p, d in trig) if e is not None]
        for a in A:
            for b in B:
                res = [path.outcome(e, a, b) for e in exs]
                w, l_, op = sum(1 for r in res if r == 1), sum(1 for r in res if r == 0), sum(1 for r in res if r == -1)
                n = w + l_ + op
                lo, hi = wilson(w, n)
                out["cells"][f"{hz} a{a:g} b{b:g}"] = {"n": n, "win": w, "loss": l_, "open": op, "win_pct": 100 * w / n if n else None,
                                                     "wilson": [100 * lo, 100 * hi], "theory_pct": 100 * b / (a + b)}
    return out


def main(store, ledger, outp):
    dl = mk.download_all(store, ("5m", "15m", "60m"))
    m5 = mk.build_market("5m", dl)
    path = Path(m5.base)
    res = {"window_5m": [str(m5.base.index[0]), str(m5.base.index[-1])], "price_source": m5.price_source, "sources": {}}
    for tf in ("15m", "5m"):
        m = mk.build_market(tf, dl)
        t_close = m.base.index.tz_convert("UTC").tz_localize(None).to_numpy().astype("datetime64[s]").astype(np.int64) + TF_SEC[tf]
        c = m.base["close"].to_numpy(float)
        F = None
        runs = {}
        for arm in ("treatment", "control", "challenger"):
            r = engine.run(m, DEFAULT, arm, F)
            F = r.F
            runs[arm] = r
            if arm == "treatment":
                tre = r
        evs = {"engine treatment": tre.rows, "engine control": runs["control"].rows, "engine challenger": runs["challenger"].rows,
               "H2": arm_h2.evaluate(tre), "H3": arm_h3.evaluate(tre, m), "H4 playbook": arm_h4.evaluate(tre),
               "H5": arm_h5.evaluate(tre, m.tf_sec), "H6": arm_h6.evaluate(tre, DEFAULT)}
        for name, ev in evs.items():
            eb, es = np.asarray(ev["exec_buy"], float), np.asarray(ev["exec_sell"], float)
            trig = [(int(t_close[i]), float(c[i]), 1 if eb[i] == 1 else -1) for i in range(len(c)) if (eb[i] == 1 or es[i] == 1) and t_close[i] >= path.t[0]]
            res["sources"][f"{tf} {name}"] = table(path, trig, f"{tf} {name} (in-sample, stored window)")
            print(tf, name, len(trig), flush=True)
    # recorded forward trades (real time), web.6 archive and any web.7 live trades
    fw = []
    for f in glob.glob(os.path.join(ledger, "holdout", "archive", "*.json")) + glob.glob(os.path.join(ledger, "holdout", "*_*.json")):
        if "manifest" in f:
            continue
        tf = os.path.basename(f).split("_")[0]
        if tf not in TF_SEC:
            continue
        for t in json.load(open(f)):
            if not isinstance(t, dict) or "6f3964ad97813cc9" not in str(t.get("freeze_key", "")) and "60bb01794d03c9ac" not in str(t.get("freeze_key", "")):
                continue
            ts = int(pd.Timestamp(t["entry_time"]).timestamp()) + TF_SEC[tf]
            fw.append((ts, float(t["entry"]), 1 if t["dir"] == "LONG" else -1))
    fw = sorted(set(fw))
    res["sources"]["forward (recorded, web.6 + web.7, all arms, 5m+15m)"] = table(path, fw, "recorded forward trades")
    # random baseline: every 5-minute close, long and short separately (same window)
    t5 = path.t + 300
    c5 = m5.base["close"].to_numpy(float)
    rng = np.random.default_rng(3)
    idx = np.sort(rng.choice(len(c5), size=min(4000, len(c5)), replace=False))
    for d, nm in ((1, "random LONG"), (-1, "random SHORT")):
        res["sources"][nm] = table(path, [(int(t5[i]), float(c5[i]), d) for i in idx], f"{nm}: 4,000 random 5-minute closes")
    json.dump(res, open(outp, "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
