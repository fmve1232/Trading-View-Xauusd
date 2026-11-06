"""Phase B16 (research/registrations/B16.json, approved; written after the registration and its amendment were committed).

The operator's level rules, exactly as the live SETUP alerts apply them (quantum.notify.setup_levels / setup_events):
liquidity SWEEPs of the previous day / week / month, today's, last-4h and last-1h highs and lows at an order block,
the value-area edge or the POC, and BREAKOUTs of the same levels beyond the value area. +$15 before -$13 (primary),
dollars at $4,000 scaled by entry / 4000, on 15-minute bars for one trading day (quantum.research.b13.race).

Development data carry no volume, so the frozen engine runs with each bar's volume set to 1 (a time-at-price profile;
the registration's amendment). Research code: never imported by production (tests/test_integrity.py).
"""
from __future__ import annotations

import argparse
import collections
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config, engine, notify, ta
from ..data import sources
from ..features import compute as compute_features
from . import b10, b13
from . import harness as H

REG = "B16"
T_ALL = (13.0, 15.0, 20.0)
ZKEYS = ("ob_bull_lo", "ob_bull_hi", "ob_bear_lo", "ob_bear_hi", "vah", "val", "vpoc")


def _none(a) -> list:
    return [None if (x is None or (isinstance(x, float) and math.isnan(x))) else float(x) for x in np.asarray(a, float).tolist()]


def _chart(df: pd.DataFrame) -> dict:
    return {"t": ta.epoch_s(df.index).astype(np.int64).tolist(), "h": df["high"].astype(float).tolist(),
            "l": df["low"].astype(float).tolist()}


def run(rd: str, log=print) -> dict:
    m15, h1 = b13.load(rd, "development")
    cfg = config.DEFAULT
    m = b10.make_market(m15, h1, "15m", 900)
    F = compute_features(m, cfg)
    F2 = dict(F)
    F2["v"] = np.ones(len(np.asarray(F["v"])))                     # amendment: time-at-price profile (no volume stored)
    log(f"[B16] engine on {len(m15)} 15m bars (volume 1 per bar)")
    R = engine.run(m, cfg, "treatment", F2).rows
    idx = pd.DatetimeIndex(F["index"])
    t = ta.epoch_s(idx).astype(np.int64).tolist()
    h, lo_, c = _none(F["h"]), _none(F["l"]), _none(F["c"])
    lv = notify.setup_levels(t, h, lo_, _chart(h1), _chart(sources.resample_ny_session(h1, 4)))
    for k in ("pdh", "pdl", "pwh", "pwl"):
        lv[k.upper()] = _none(R[k])
    z = {k: _none(R[k]) for k in ZKEYS}
    scored = np.flatnonzero(idx >= b13.SCORE_FROM).tolist()
    ev = notify.setup_events(t, h, lo_, c, lv, z, scored, {}, scale=True)
    log(f"[B16] {len(ev)} setups: {dict(collections.Counter((e['kind'], e['dir']) for e in ev))}")
    c_arr = np.asarray(F["c"], float)
    t_close = np.asarray(t, np.int64) + 900
    cost = H.cost_pts(idx)
    every3 = np.asarray(scored[::3], int)
    rnd = {T: b13.random_rates(m15, idx, c_arr, every3, T, b13.S_STOP) for T in T_ALL}
    res = {"registration": REG, "stage": "development", "bars": len(idx), "window": [str(idx[0]), str(idx[-1])],
           "setups": len(ev), "random": {f"T{T:g}": {"long": v["long"], "short": v["short"]} for T, v in rnd.items()},
           "profile": "time-at-price (volume 1 per bar; amendment)", "trials": {}, "breakdown": {}}

    def measure(es, T):
        ii = np.asarray([e["i"] for e in es], int)
        dd = np.asarray([e["dir"] for e in es], int)
        r = b13.race(m15, t_close[ii], c_arr[ii], dd, T, b13.S_STOP)
        return b13.stats(r, dd, cost[ii], T, b13.S_STOP, np.where(dd > 0, rnd[T]["long"], rnd[T]["short"])), ii, dd

    for kind in ("SWEEP", "BREAKOUT"):
        es = [e for e in ev if e["kind"] == kind]
        for T in T_ALL:
            st, ii, dd = measure(es, T)
            res["trials"][f"B16 {kind} T{T:g}"] = st
        if es:                                                     # the operator's literal ask: +$15 at any time in the day
            r = b13.race(m15, t_close[ii], c_arr[ii], dd, 15.0, 1e9)
            ok = r["ok"]
            res["trials"][f"B16 {kind} T15"]["moved_15_within_day_ignoring_stop"] = float(r["win"][ok].mean()) if ok.any() else None
        # secondary: by first level and by zone type
        for key, fn in (("level", lambda e: e["levels"][0][0]),
                        ("zone", lambda e: e["zones"][0].split(" ")[0] if e["zones"] else "?"),
                        ("direction", lambda e: "BUY" if e["dir"] > 0 else "SELL")):
            grp = collections.defaultdict(list)
            for e in es:
                grp[fn(e)].append(e)
            res["breakdown"][f"{kind} by {key}"] = {g_: {k: v for k, v in measure(lst, 15.0)[0].items()
                                                          if k in ("n", "rate", "random", "z", "mean_net_usd_per_oz_at_4000")}
                                                     for g_, lst in sorted(grp.items())}
        log(f"[B16] {kind}: {len(es)} setups; T15 {res['trials'][f'B16 {kind} T15']['rate']}")
    prim = {k: res["trials"][f"B16 {k} T15"] for k in ("SWEEP", "BREAKOUT")}
    p1 = b13.holm({k: v["p_one_sided"] for k, v in prim.items()})
    res["primary"] = {"holm_p1": p1, "verdict": {
        k: ("INSUFFICIENT" if v["n"] < b13.MIN_N else "PASS" if (p1[k] and math.isfinite(v["t"]) and v["t"] >= 1.645) else "FAIL")
        for k, v in prim.items()}}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    res = {"utc": datetime.now(timezone.utc).isoformat(), **run(a.rd)}
    with open(a.out, "w") as f:
        json.dump(b13._clean(res), f, indent=1, allow_nan=False)
    if a.trials:
        for nm, s in res["trials"].items():
            rec = {"phase": "B16", "partition": "development", "id": nm, **b13._clean(s)}
            kind = nm.split(" ")[1]
            if nm.endswith(" T15"):
                rec["primary"], rec["verdict"] = f"B16 {kind}", res["primary"]["verdict"][kind]
            H.log_trial(a.trials, rec)
    print(json.dumps(b13._clean(res["primary"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
