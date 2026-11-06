"""Phase B14 (research/registrations/B14.json, approved; written after the registration was committed).

A break of a previous-day / previous-week high (low), confirmed on BOTH 15min and 1h on the same New York trading day,
while the frozen engine's 15min higher-timeframe gate blocks that direction: the live A2 trend-change condition.

  B14-a  gate ON (primary)      B14-b  gate OFF (secondary)      B14-c  all two-timeframe breaks (secondary)

Traded in the break's direction from the 15min close at which both timeframes have broken; once per direction per
trading day. Outcome +15 before -13 (and +10 / +13 / +20), dollars at $4,000 scaled by entry / 4000, on 15min bars for
96 bars (quantum.research.b13.race). Research code: never imported by production (tests/test_integrity.py).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config, engine, ta
from ..features import compute as compute_features
from . import b10, b13
from . import harness as H

REG = "B14"
POOLS = (("PDH", "pdh", 1), ("PWH", "pwh", 1), ("PDL", "pdl", -1), ("PWL", "pwl", -1))
T_ALL = (10.0, 13.0, 15.0, 20.0)


def breaks(R: dict, c: np.ndarray) -> list[tuple[int, str, float, int]]:
    """(bar, pool, level, direction) where a close crossed a pool the bar before had not closed beyond (the alerts'
    BREAK rule: c[k] > lv >= c[k-1] for a high, mirrored for a low; lv = the level on bar k)."""
    out = []
    for name, key, d in POOLS:
        lv = np.asarray(R[key], float)
        for k in range(1, len(c)):
            x = lv[k]
            if not np.isfinite(x) or not np.isfinite(c[k]) or not np.isfinite(c[k - 1]):
                continue
            if (d > 0 and c[k] > x >= c[k - 1]) or (d < 0 and c[k] < x <= c[k - 1]):
                out.append((k, name, round(float(x), 2), d))
    return out


def events(idx15, c15, R15, F15, idx1, c1, R1) -> list[dict]:
    """Two-timeframe breaks: per trading day and pool, the 15min close at which both 15min and 1h have broken it."""
    t15 = ta.epoch_s(idx15).astype(np.int64) + 900
    t1 = ta.epoch_s(idx1).astype(np.int64) + 3600
    d15, d1 = b13.tday(idx15), b13.tday(idx1)
    first15, first1 = {}, {}
    for k, nm, lv, d in breaks(R15, c15):
        first15.setdefault((d15[k], nm, lv, d), int(t15[k]))
    for k, nm, lv, d in breaks(R1, c1):
        first1.setdefault((d1[k], nm, lv, d), int(t1[k]))
    bear, bull = np.asarray(F15["htf_bear_gate"], bool), np.asarray(F15["htf_bull_gate"], bool)
    out = []
    for key, ta15 in first15.items():
        if key not in first1:
            continue
        when = max(ta15, first1[key])
        k = int(np.searchsorted(t15, when))                       # the 15min bar closing at / after that moment
        if k >= len(t15) or d15[k] != key[0]:
            continue
        gate = bool(bear[k]) if key[3] > 0 else bool(bull[k])
        out.append({"k": k, "day": key[0], "pool": key[1], "level": key[2], "dir": key[3], "gate_on": gate})
    return sorted(out, key=lambda e: e["k"])


def once_per_day(ev: list[dict]) -> list[dict]:
    seen, out = set(), []
    for e in ev:
        if (e["day"], e["dir"]) not in seen:
            seen.add((e["day"], e["dir"]))
            out.append(e)
    return out


def run(rd: str, log=print) -> dict:
    m15, h1 = b13.load(rd, "development")
    cfg = config.DEFAULT
    m_a = b10.make_market(m15, h1, "15m", 900)
    F15 = compute_features(m_a, cfg)
    log(f"[B14] 15min engine on {len(m15)} bars")
    R15 = engine.run(m_a, cfg, "treatment", F15).rows
    m_b = b10.make_market(h1, h1, "1h", 3600)
    F1 = compute_features(m_b, cfg)
    log(f"[B14] 1h engine on {len(h1)} bars")
    R1 = engine.run(m_b, cfg, "treatment", F1).rows
    idx15, idx1 = pd.DatetimeIndex(F15["index"]), pd.DatetimeIndex(F1["index"])
    c15, c1 = np.asarray(F15["c"], float), np.asarray(F1["c"], float)
    ev = events(idx15, c15, R15, F15, idx1, c1, R1)
    scored = idx15 >= b13.SCORE_FROM
    ev = [e for e in ev if scored[e["k"]]]
    t_close = ta.epoch_s(idx15).astype(np.int64) + 900
    cost = H.cost_pts(idx15)
    every3 = np.flatnonzero(scored)[::3]
    rnd = {T: b13.random_rates(m15, idx15, c15, every3, T, b13.S_STOP) for T in T_ALL}
    res = {"registration": REG, "stage": "development", "bars_15m": len(idx15), "bars_1h": len(idx1),
           "window": [str(idx15[0]), str(idx15[-1])], "two_tf_breaks_all": len(ev),
           "random": {f"T{T:g}": {"long": v["long"], "short": v["short"]} for T, v in rnd.items()}, "trials": {}}
    sets = {"B14-a": once_per_day([e for e in ev if e["gate_on"]]), "B14-b": once_per_day([e for e in ev if not e["gate_on"]]),
            "B14-c": once_per_day(ev)}
    for nm, es in sets.items():
        ii = np.asarray([e["k"] for e in es], int)
        dd = np.asarray([e["dir"] for e in es], int)
        for T in T_ALL:
            r = b13.race(m15, t_close[ii], c15[ii], dd, T, b13.S_STOP)
            base = np.where(dd > 0, rnd[T]["long"], rnd[T]["short"])
            st = b13.stats(r, dd, cost[ii], T, b13.S_STOP, base)
            st["pools"] = dict(pd.Series([e["pool"] for e in es]).value_counts()) if es else {}
            res["trials"][f"{nm} T{T:g}"] = st
        log(f"[B14] {nm}: {len(es)} events; T15 {res['trials'][f'{nm} T15']['rate']}")
    a = res["trials"]["B14-a T15"]
    verdict = ("INSUFFICIENT" if a["n"] < b13.MIN_N else
               "PASS" if (a["p_one_sided"] <= 0.05 and math.isfinite(a["t"]) and a["t"] >= 1.645) else "FAIL")
    res["primary"] = {"B14-a": verdict}
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
            rec = {"phase": "B14", "partition": "development", "id": nm, **b13._clean(s)}
            if nm == "B14-a T15":
                rec["primary"], rec["verdict"] = "B14-a", res["primary"]["B14-a"]
            H.log_trial(a.trials, rec)
    print(json.dumps(res["primary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
