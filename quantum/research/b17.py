"""Phase B17 (research/registrations/B17.json, approved; written after the registration was committed).

Quality over quantity: a B16 setup taken only when all four confirmations agree (quantum.notify.setup_checks):
a previous day / week / month level, all three trend votes, the engine's own bias, and a London / New York close.
+$15 before -$13 (primary), as B16. Also the ladder from every setup to the fully confirmed ones.
Research code: never imported by production (tests/test_integrity.py).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config, engine, notify, ta
from ..data import sources
from ..features import compute as compute_features
from . import b10, b13, b16
from . import harness as H

REG = "B17"
T_ALL = (13.0, 15.0, 20.0)
LADDER = (("all B16 setups", ()), ("+ major level", ("major",)), ("+ trend 3 of 3", ("major", "trend")),
          ("+ engine bias", ("major", "trend", "bias")), ("+ London / New York (confirmed)", ("major", "trend", "bias", "session")))


def _chart(df: pd.DataFrame) -> dict:
    return {"t": ta.epoch_s(df.index).astype(np.int64).tolist(), "h": df["high"].astype(float).tolist(),
            "l": df["low"].astype(float).tolist(), "c": df["close"].astype(float).tolist()}


def run(rd: str, log=print) -> dict:
    m15, h1 = b13.load(rd, "development")
    cfg = config.DEFAULT
    m = b10.make_market(m15, h1, "15m", 900)
    F = compute_features(m, cfg)
    F2 = dict(F)
    F2["v"] = np.ones(len(np.asarray(F["v"])))                     # as B16 (no volume stored for these data)
    log(f"[B17] engine on {len(m15)} 15m bars")
    R = engine.run(m, cfg, "treatment", F2).rows
    idx = pd.DatetimeIndex(F["index"])
    t = ta.epoch_s(idx).astype(np.int64).tolist()
    h, lo_, c = b16._none(F["h"]), b16._none(F["l"]), b16._none(F["c"])
    c1, c4 = _chart(h1), _chart(sources.resample_ny_session(h1, 4))
    lv = notify.setup_levels(t, h, lo_, c1, c4)
    for k in ("pdh", "pdl", "pwh", "pwl"):
        lv[k.upper()] = b16._none(R[k])
    z = {k: b16._none(R[k]) for k in b16.ZKEYS}
    scored = np.flatnonzero(idx >= b13.SCORE_FROM).tolist()
    ev = notify.setup_events(t, h, lo_, c, lv, z, scored, {}, scale=True)
    votes = notify.trend_votes(t, c1, c4)
    bull, bear = b16._none(R["bull"]), b16._none(R["bear"])
    for e in ev:
        e["checks"] = notify.setup_checks(e, votes, bull, bear)
    c_arr = np.asarray(F["c"], float)
    t_close = np.asarray(t, np.int64) + 900
    cost = H.cost_pts(idx)
    every3 = np.asarray(scored[::3], int)
    rnd = {T: b13.random_rates(m15, idx, c_arr, every3, T, b13.S_STOP) for T in T_ALL}
    res = {"registration": REG, "stage": "development", "bars": len(idx), "window": [str(idx[0]), str(idx[-1])],
           "setups": len(ev), "random": {f"T{T:g}": {"long": v["long"], "short": v["short"]} for T, v in rnd.items()},
           "trials": {}, "ladder": {}}

    def measure(es, T, S=b13.S_STOP):
        ii = np.asarray([e["i"] for e in es], int)
        dd = np.asarray([e["dir"] for e in es], int)
        r = b13.race(m15, t_close[ii], c_arr[ii], dd, T, S)
        base = np.where(dd > 0, rnd[T]["long"], rnd[T]["short"]) if S == b13.S_STOP else np.zeros(len(ii))
        return b13.stats(r, dd, cost[ii], T, S, base), r

    for name, need in LADDER:
        es = [e for e in ev if all(e["checks"][k] for k in need)]
        st, _ = measure(es, 15.0)
        res["ladder"][name] = {k: st[k] for k in ("n", "rate", "wilson", "random", "z", "mean_net_usd_per_oz_at_4000", "t")}
        log(f"[B17] {name}: n {st['n']} rate {st['rate']}")
    conf = [e for e in ev if all(e["checks"].values())]
    for T in T_ALL:
        st, _ = measure(conf, T)
        res["trials"][f"B17 confirmed T{T:g}"] = st
    if conf:
        _, r = measure(conf, 15.0, 1e9)
        res["trials"]["B17 confirmed T15"]["moved_15_within_day_ignoring_stop"] = float(r["win"][r["ok"]].mean()) if r["ok"].any() else None
    for kind in ("SWEEP", "BREAKOUT"):
        st, _ = measure([e for e in conf if e["kind"] == kind], 15.0)
        res["trials"][f"B17 confirmed {kind} T15 (secondary)"] = st
    pr = res["trials"]["B17 confirmed T15"]
    res["primary"] = {"B17": ("INSUFFICIENT" if pr["n"] < b13.MIN_N else
                              "PASS" if (pr["p_one_sided"] <= 0.05 and math.isfinite(pr["t"]) and pr["t"] >= 1.645) else "FAIL")}
    res["per_year"] = round(len(conf) / max(1e-9, (idx[-1] - b13.SCORE_FROM).days / 365.25), 1)
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
            rec = {"phase": "B17", "partition": "development", "id": nm, **b13._clean(s)}
            if nm == "B17 confirmed T15":
                rec["primary"], rec["verdict"] = "B17", res["primary"]["B17"]
            H.log_trial(a.trials, rec)
        for nm, s in res["ladder"].items():
            H.log_trial(a.trials, {"phase": "B17", "partition": "development", "id": f"B17 ladder {nm} T15", **b13._clean(s)})
    print(json.dumps(res["primary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
