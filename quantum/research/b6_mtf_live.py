"""Phase B6 (EXPLORATORY): does a site signal win more often when the higher timeframes agree? Declared 2026-11-01 and
committed before the first run, at the operator's request ("make further research ... TP will hit first").

Why. The operator's winning trade (29 Oct 2026, SELL at 14:45 UTC) matched SHORT signals on the site's 5m and 15m arms
while the 1-hour signal also pointed down; the losing trade (30 Oct, BUY at 05:10 UTC) went against the 1h / 15m.
"Only trade when the timeframes agree" is the natural rule to test.

    python -m quantum.research.b6_mtf_live <market-data checkout> <out.json> [--registry research/trials.jsonl]

DATA (live window, market-data branch): every signal the site's arms recorded (holdout ledgers and the archive, all
arms, all engine keys), deduplicated by (timeframe, decision time, direction). The engine cannot be replayed over
2020-2023 faithfully: the research history has no volume, so its volume-gated signals could not fire. This window
(2026-09-28 -> 2026-10-30) is the one the site already shows, so nothing here can be validated or registered.
SIGNALS TESTED: 5m and 15m signals. Decision time = entry_time + the timeframe (the bar's close).
CONTEXT (known at the decision time, nothing later):
    h1  the direction of the most recent 1h signal decided at or before it, if within the last 24 hours
    h4  the direction of the most recent 4h signal decided at or before it, if within the last 72 hours
    m15 for a 5m signal: the most recent 15m signal decided at or before it, if within the last 60 minutes
GROUPS: ALL, H1_AGREE, H1_AGAINST, H1_H4_AGREE, M15_AGREE (5m only).
OUTCOME: +$13 before -$13 (the operator's $650 / $650 at 0.5 lot) and +$10 before -$10, from the recorded entry price,
on spot 5-minute paths for one trading day (288 bars), B2's fills; one position at a time within each group.
BASELINE: every spot 5-minute close in the same window, long and short, matched to each group's long / short mix.
Reported: n, success, Wilson 95% interval, z against the matched random rate. Break-even with costs is about 51%.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from ..data import sources, store
from . import b2
from . import harness as H

TF_SEC = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
TARGETS = {"T13": (13.0, 13.0), "T10": (10.0, 10.0)}
H1_MAX, H4_MAX, M15_MAX = 24 * 3600, 72 * 3600, 3600
GROUPS = ("ALL", "H1_AGREE", "H1_AGAINST", "H1_H4_AGREE", "M15_AGREE")


def signals(md: str) -> pd.DataFrame:
    """Every recorded signal, one row per (tf, decision time, direction)."""
    rows = {}
    for f in glob.glob(os.path.join(md, "holdout", "*.json")) + glob.glob(os.path.join(md, "holdout", "archive", "*.json")):
        tf = os.path.basename(f).split("_")[0]
        if tf not in TF_SEC:
            continue
        try:
            with open(f) as fh:
                led = json.load(fh)
        except (OSError, ValueError):
            continue
        for tr in led if isinstance(led, list) else []:
            try:
                t = int(pd.Timestamp(tr["entry_time"]).timestamp()) + TF_SEC[tf]
                d = 1 if tr["dir"] == "LONG" else -1
                rows[(tf, t, d)] = float(tr["entry"])
            except (KeyError, TypeError, ValueError):
                continue
    df = pd.DataFrame([(tf, t, d, p) for (tf, t, d), p in rows.items()], columns=["tf", "t", "dir", "entry"])
    return df.sort_values(["t", "tf"]).reset_index(drop=True)


def context(sig: pd.DataFrame) -> pd.DataFrame:
    """Adds h1, h4, m15: the latest higher-timeframe direction decided at or before each signal (0 = none recent)."""
    out = sig.copy()
    for col, tf, mx in (("h1", "1h", H1_MAX), ("h4", "4h", H4_MAX), ("m15", "15m", M15_MAX)):
        ref = sig[sig["tf"] == tf].sort_values("t")
        rt, rd = ref["t"].to_numpy(np.int64), ref["dir"].to_numpy()
        k = np.searchsorted(rt, out["t"].to_numpy(np.int64), side="right") - 1
        has = k >= 0
        kk = np.where(has, k, 0)
        age = out["t"].to_numpy(np.int64) - (rt[kk] if len(rt) else 0)
        out[col] = np.where(has & (age <= mx) & (len(rt) > 0), rd[kk] if len(rt) else 0, 0)
    return out


def group_mask(df: pd.DataFrame, g: str) -> np.ndarray:
    d = df["dir"].to_numpy()
    if g == "ALL":
        return np.ones(len(df), bool)
    if g == "H1_AGREE":
        return df["h1"].to_numpy() == d
    if g == "H1_AGAINST":
        return df["h1"].to_numpy() == -d
    if g == "H1_H4_AGREE":
        return (df["h1"].to_numpy() == d) & (df["h4"].to_numpy() == d)
    if g == "M15_AGREE":
        return (df["tf"].to_numpy() == "5m") & (df["m15"].to_numpy() == d)
    raise ValueError(g)


def _load_spot(md: str) -> pd.DataFrame:
    return sources.repair_reopen(sources.trading_week_only(sources.drop_offgrid(store.load(md, "XAU/USD_5m"))), 300)


def run(md: str, outp: str, registry: str | None) -> dict:
    sp = _load_spot(md)
    P = b2.Paths(sp)
    sig = context(signals(md))
    sig = sig[sig["tf"].isin(["5m", "15m"])].reset_index(drop=True)
    res = {"set": "B6-explore", "partition": "live-window-2026", "spot_bars": len(sp),
           "window": [str(sp.index[0]), str(sp.index[-1])], "signals": len(sig), "baseline": {}, "groups": []}
    jr, okr = P.locate(P.t + 300)
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        ev = P.evaluate(jr[okr], P.c[okr], np.full(int(okr.sum()), dv), [(np.full(int(okr.sum()), a), np.full(int(okr.sum()), b)) for a, b in TARGETS.values()])
        for tn, e in zip(TARGETS, ev):
            res["baseline"][f"{tn} {dname}"] = float(np.mean(e["out"] == 1))
    t_all, d_all, p_all = sig["t"].to_numpy(np.int64), sig["dir"].to_numpy(float), sig["entry"].to_numpy(float)
    j_all, ok_all = P.locate(t_all)
    for g in GROUPS:
        m = group_mask(sig, g) & ok_all
        i = np.flatnonzero(m)
        for tn, (a, b) in TARGETS.items():
            rec = {"id": f"{g} {tn}", "group": g, "target": tn, "signals": len(i)}
            if len(i):
                e = P.evaluate(j_all[i], p_all[i], d_all[i], [(np.full(len(i), a), np.full(len(i), b))])[0]
                keep = b2.one_position(t_all[i], P.t[np.minimum(e["exit"], len(P.t) - 1)] + 300)
                o, d = e["out"][keep], d_all[i][keep]
                n, w = len(o), int((o == 1).sum())
                nl, ns = int((d > 0).sum()), int((d < 0).sum())
                rnd = (nl * res["baseline"][f"{tn} long"] + ns * res["baseline"][f"{tn} short"]) / n
                p = w / n
                rec.update({"n": n, "long": nl, "short": ns, "wins": w, "losses": int((o == 0).sum()), "open": int((o == -1).sum()),
                            "win_rate": p, "wilson": list(H.wilson(w, n)), "random_same_mix": rnd,
                            "z_vs_random": (p - rnd) / math.sqrt(max(rnd * (1 - rnd), 1e-12) / n)})
            res["groups"].append(rec)
            if registry:
                H.log_trial(registry, {"phase": "B6-explore", "partition": "live-window-2026", **rec})
    with open(outp, "w") as f:
        json.dump(res, f, indent=1, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("out")
    ap.add_argument("--registry", default="research/trials.jsonl")
    a = ap.parse_args(argv)
    r = run(a.md, a.out, a.registry)
    for g in r["groups"]:
        if g.get("n"):
            print(f"{g['id']:18s} n {g['n']:4d}  TP first {g['win_rate']:.1%}  [{g['wilson'][0]:.1%}, {g['wilson'][1]:.1%}]  "
                  f"random {g['random_same_mix']:.1%}  z {g['z_vs_random']:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
