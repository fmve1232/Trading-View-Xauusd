"""Phase B18 (research/registrations/B18.json, approved; written after the registration was committed).

The operator's 4h candle breakout (a close above the previous 4h high / below its low) with all four confirmations,
exactly as the live alert applies it (quantum.notify.h4_events). +$15 before -$13 from the 4h close (primary), on 15m
bars for one trading day (quantum.research.b13.race). Research code: never imported by production.
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
from . import b10, b13, b16, b17
from . import harness as H

REG = "B18"
T_ALL = (13.0, 15.0, 20.0)
LADDER = (("every 4h breakout", ()), ("+ day / week / month level", ("major",)), ("+ trend 3 of 3", ("major", "trend")),
          ("+ engine bias", ("major", "trend", "bias")), ("+ London / New York (all four)", ("major", "trend", "bias", "session")))


def run(rd: str, log=print) -> dict:
    m15, h1 = b13.load(rd, "development")
    h4 = sources.resample_ny_session(h1, 4)
    cfg = config.DEFAULT
    m = b10.make_market(h4, h1, "4h", 14400)
    F = compute_features(m, cfg)
    F2 = dict(F)
    F2["v"] = np.ones(len(np.asarray(F["v"])))                     # as B16 (no volume stored for these data)
    log(f"[B18] engine on {len(h4)} 4h bars")
    R = engine.run(m, cfg, "treatment", F2).rows
    idx = pd.DatetimeIndex(F["index"])
    t4 = ta.epoch_s(idx).astype(np.int64).tolist()
    h, lo_, c = b16._none(F["h"]), b16._none(F["l"]), b16._none(F["c"])
    c1, c4 = b17._chart(h1), b17._chart(h4)
    lv = notify.setup_levels(t4, h, lo_, c1, c4)
    for k in ("pdh", "pdl", "pwh", "pwl"):
        lv[k.upper()] = b16._none(R[k])
    votes = notify.trend_votes([x + 14400 for x in t4], c1, c4)
    rows = np.flatnonzero(idx >= b13.SCORE_FROM).tolist()
    ev = notify.h4_events(t4, h, lo_, c, b16._none(R["bull"]), b16._none(R["bear"]), lv, votes, rows)
    # outcomes on the 15m path from each 4h close
    i15 = m15.index
    c15 = m15["close"].to_numpy(float)
    t15 = ta.epoch_s(i15).astype(np.int64)
    cost15 = H.cost_pts(i15)
    s15 = np.flatnonzero(i15 >= b13.SCORE_FROM)
    rnd = {T: b13.random_rates(m15, i15, c15, s15[::3], T, b13.S_STOP) for T in T_ALL}
    tc_all = np.asarray([x + 14400 for x in t4], np.int64)
    c_all = np.asarray(c, dtype=float)
    res = {"registration": REG, "stage": "development", "bars_4h": len(idx), "window": [str(idx[0]), str(idx[-1])],
           "breakouts": len(ev), "random": {f"T{T:g}": {"long": v["long"], "short": v["short"]} for T, v in rnd.items()},
           "trials": {}, "ladder": {}}
    # 4h-close random baseline (secondary): every scored 4h close, both directions
    r4 = {}
    for nm, sgn in (("long", 1), ("short", -1)):
        rr = b13.race(m15, tc_all[rows], c_all[rows], np.full(len(rows), sgn), 15.0, b13.S_STOP)
        dec = rr["win"] | rr["loss"]
        r4[nm] = float(rr["win"][dec].mean()) if dec.any() else None
    res["random_4h_closes_T15"] = r4

    def measure(es, T, S=b13.S_STOP):
        tc = np.asarray([e["t_close"] for e in es], np.int64)
        px = np.asarray([e["close"] for e in es], float)
        dd = np.asarray([e["dir"] for e in es], int)
        j = np.searchsorted(t15, tc)
        cst = cost15[np.minimum(j, len(cost15) - 1)] if len(j) else np.zeros(0)
        r = b13.race(m15, tc, px, dd, T, S)
        base = np.where(dd > 0, rnd[T]["long"], rnd[T]["short"]) if S == b13.S_STOP else np.zeros(len(dd))
        return b13.stats(r, dd, cst, T, S, base), r

    for name, need in LADDER:
        es = [e for e in ev if all(e["checks"][k] for k in need)]
        st, _ = measure(es, 15.0)
        res["ladder"][name] = {k: st[k] for k in ("n", "rate", "wilson", "random", "z", "mean_net_usd_per_oz_at_4000", "t")}
        log(f"[B18] {name}: n {st['n']} rate {st['rate']}")
    conf = [e for e in ev if e["confirmed"]]
    for T in T_ALL:
        st, _ = measure(conf, T)
        res["trials"][f"B18 confirmed T{T:g}"] = st
    if conf:
        _, r = measure(conf, 15.0, 1e9)
        res["trials"]["B18 confirmed T15"]["moved_15_within_day_ignoring_stop"] = float(r["win"][r["ok"]].mean()) if r["ok"].any() else None
    pr = res["trials"]["B18 confirmed T15"]
    res["primary"] = {"B18": ("INSUFFICIENT" if pr["n"] < b13.MIN_N else
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
            rec = {"phase": "B18", "partition": "development", "id": nm, **b13._clean(s)}
            if nm == "B18 confirmed T15":
                rec["primary"], rec["verdict"] = "B18", res["primary"]["B18"]
            H.log_trial(a.trials, rec)
        for nm, s in res["ladder"].items():
            H.log_trial(a.trials, {"phase": "B18", "partition": "development", "id": f"B18 ladder {nm} T15", **b13._clean(s)})
    print(json.dumps(res["primary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
