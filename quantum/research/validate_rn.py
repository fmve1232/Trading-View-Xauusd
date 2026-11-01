"""One validation run of registration B4-RN-V1 (research/registrations/B4-RN-V1.json): round-number crossing
continuation, 15-minute closes through a $100 level, +$15 / -$10. Run ONCE, only after the operator has approved the
registration (harness.partition refuses the validation data until "approved_by_operator" is true). The result is final
for this hypothesis.

    python -m quantum.research.validate_rn <research-data checkout> <out.json> [--registry research/trials.jsonl]

The rule is B4's, unchanged; this module refuses to run if the registration's numbers differ from the ones coded here.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from .. import ta
from . import b2, b4, history
from . import harness as H

REG_ID = "B4-RN-V1"
PRIMARY = {"level": 100.0, "tp": 15.0, "sl": 10.0}
SECONDARY = [("$100 cross +$10", "15min", 100.0, 10.0), ("$100 cross +$20", "15min", 100.0, 20.0),
             ("$50 cross +$15", "15min", 50.0, 15.0), ("1h $100 cross +$20", "1h", 100.0, 20.0)]
Z_CRIT = 1.645


def registration() -> dict:
    with open(os.path.join(H.REG_DIR, f"{REG_ID}.json")) as f:
        reg = json.load(f)
    r = reg["rule"]
    if (r["take_profit_usd_at_4000"], r["stop_loss_usd_at_4000"]) != (PRIMARY["tp"], PRIMARY["sl"]) or "round_cross(close, 100.0)" not in r["signal"]:
        raise RuntimeError("registration and code disagree; refusing to run")
    return reg


def _random_rates(P: b2.Paths, tp: float, sl: float) -> dict:
    j, ok = P.locate(P.t + b2.PATH_SEC)
    jr, pr = j[ok], P.c[ok]
    sc = pr / b2.REF_PRICE
    out = {}
    for name, dv in (("long", 1.0), ("short", -1.0)):
        ev = P.evaluate(jr, pr, np.full(len(jr), dv), [(tp * sc, sl * sc)])[0]
        out[name] = float(np.mean(ev["out"] == 1))
    return out


def test_rule(P: b2.Paths, df: pd.DataFrame, tf_sec: int, level: float, tp: float, sl: float, rnd: dict) -> dict:
    c = df["close"].to_numpy(float)
    s = b4.round_cross(c, level)
    t_close = ta.epoch_s(df.index) + tf_sec
    i = np.flatnonzero(s != 0)
    j, ok = P.locate(t_close[i])
    i, j = i[ok], j[ok]
    p, d = c[i], s[i]
    sc = p / b2.REF_PRICE
    e = P.evaluate(j, p, d, [(tp * sc, sl * sc)])[0]
    keep = b2.one_position(t_close[i], P.t[np.minimum(e["exit"], len(P.t) - 1)] + b2.PATH_SEC)
    cost = H.cost_pts(df.index)[i] * sc
    st = b2._stats(e["out"][keep], e["pnl"][keep], cost[keep], tp * sc[keep], sl * sc[keep], d[keep])
    if not st["n"]:
        return {"n": 0}
    pr = (st["long"] * rnd["long"] + st["short"] * rnd["short"]) / st["n"]
    z = (st["win_rate"] - pr) / math.sqrt(max(pr * (1 - pr), 1e-12) / st["n"])
    t_entry = pd.to_datetime(t_close[i][keep], unit="s", utc=True)
    half = np.where(t_entry.month <= 6, t_entry.year.astype(str) + "H1", t_entry.year.astype(str) + "H2")
    out = e["out"][keep]
    dk = d[keep]
    return {**{k: st.get(k) for k in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "gross_r", "t")},
            "random_same_mix": pr, "z_vs_random": z, "p_one_sided": 0.5 * math.erfc(z / math.sqrt(2)),
            "usd_per_trade_0p5lot": st["net_r"] * sl * 50,
            "by_half": {h: {"n": int((half == h).sum()), "win_rate": float(np.mean(out[half == h] == 1))} for h in sorted(set(half))},
            "by_dir": {nm: {"n": int((dk == v).sum()), "win_rate": float(np.mean(out[dk == v] == 1)) if (dk == v).any() else None}
                       for nm, v in (("long", 1), ("short", -1))}}


def already_run(registry: str) -> bool:
    """One time only: a validation record for this registration in the trial registry closes it."""
    if not os.path.exists(registry):
        return False
    with open(registry) as f:
        return any(f'"registration": "{REG_ID}"' in line and '"partition": "validation"' in line for line in f)


def run(rd: str, outp: str, registry: str) -> dict:
    reg = registration()
    if already_run(registry):
        raise RuntimeError(f"{REG_ID} has already been run once (see {registry}); the result is final")
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "validation", REG_ID)   # raises unless approved
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "validation", REG_ID)
    P = b2.Paths(m15)
    res = {"registration": REG_ID, "partition": "validation", "from": str(H.VAL[0]), "to": str(H.VAL[1]),
           "bars_15m": len(m15), "data_hash_15m": H.data_hash(m15), "random": {}, "primary": None, "secondary": {}}
    rnd = {}
    for tp in sorted({PRIMARY["tp"], *[x[3] for x in SECONDARY]}):
        rnd[tp] = _random_rates(P, tp, PRIMARY["sl"])
        res["random"][f"+{tp:g}/-{PRIMARY['sl']:g}"] = rnd[tp]
    prim = test_rule(P, m15, 900, PRIMARY["level"], PRIMARY["tp"], PRIMARY["sl"], rnd[PRIMARY["tp"]])
    prim["P1_pass"] = bool(prim.get("n") and prim["z_vs_random"] >= Z_CRIT)
    prim["P2_pass"] = bool(prim.get("n") and prim["net_r"] > 0 and (prim["t"] or 0) >= Z_CRIT)
    prim["verdict"] = "PASS" if prim["P1_pass"] and prim["P2_pass"] else "FAIL"
    res["primary"] = prim
    for name, tf, level, tp in SECONDARY:
        df, sec = (m15, 900) if tf == "15min" else (h1, 3600)
        res["secondary"][name] = test_rule(P, df, sec, level, tp, PRIMARY["sl"], rnd[tp])
    H.log_trial(registry, {"phase": "B4-V", "partition": "validation", "registration": REG_ID, "id": "15min RN_CROSS_100 T15 (validation)",
                           "data_hash": res["data_hash_15m"],
                           **{k: prim.get(k) for k in ("n", "win_rate", "wilson", "break_even", "net_r", "t", "random_same_mix", "z_vs_random", "verdict")}})
    res["registration_record"] = reg
    with open(outp, "w") as f:
        json.dump(res, f, indent=1, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rd")
    ap.add_argument("out")
    ap.add_argument("--registry", default="research/trials.jsonl")
    a = ap.parse_args(argv)
    r = run(a.rd, a.out, a.registry)
    print(json.dumps({"primary": r["primary"], "secondary": r["secondary"], "random": r["random"]}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
