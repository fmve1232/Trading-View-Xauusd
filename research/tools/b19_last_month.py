"""B19 on the last month of the site's own data (exploratory and descriptive; operator request 2026-11-07: "consider the
data of last 1 month and give me this confirm trade plan with the best strategy").

The B19 rules run unchanged (quantum/research/b19.py, research/registrations/B19.json) on the market-data store's 15m
and 1h bars: triggers in the window, the confirmation state machine on 15m closes, entry at the confirming close, stop
-$13, target +$15 or +$20. Random entries at every 15m close are the baseline. The path is padded after the last bar so
recent triggers keep their windows: anything still undecided at the data's end is reported as PENDING / OPEN, never
guessed. Every configuration run here is logged (phase B19-month) because picking the best of several on one month is
a selection, and the report says so.

  python research/tools/b19_last_month.py STORE 2026-10-07 OUT.json [--trials research/trials.jsonl]
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum.data import sources
from quantum.data import store as ST
from quantum.research import b13, b19
from quantum.research import harness as H

TARGETS = (15.0, 20.0)
PAD = 400


def mt5(t: int) -> str:
    return (datetime.fromtimestamp(int(t), timezone.utc) + timedelta(hours=2)).strftime("%a %d %b %H:%M")


def load(store: str):
    m15 = sources.trading_week_only(sources.drop_offgrid(ST.load(store, "XAU/USD_15m")))[["open", "high", "low", "close", "volume"]]
    h1 = sources.trading_week_only(sources.drop_offgrid(ST.load(store, "XAU/USD_60m")))[["open", "high", "low", "close", "volume"]]
    return m15, h1


def padded(m15: pd.DataFrame) -> pd.DataFrame:
    idx = pd.date_range(m15.index[-1] + pd.Timedelta(minutes=15), periods=PAD, freq="15min")
    return pd.concat([m15, pd.DataFrame({k: np.nan for k in m15.columns}, index=idx)])


def stats(net: np.ndarray, out: np.ndarray) -> dict:
    dec = np.isfinite(net)
    n = int(dec.sum())
    x = net[dec]
    wins, losses = x[x > 0].sum(), -x[x < 0].sum()
    sd = float(np.std(x, ddof=1)) if n > 2 else 0.0
    return {"trades": n, "open": int((~dec).sum()), "tp_first": float(np.mean(out[dec] == "TP")) if n else None,
            "sl_first": float(np.mean(np.isin(out[dec], ("SL", "AMBIGUOUS")))) if n else None,
            "net_usd_per_oz": float(x.mean()) if n else None, "t": float(x.mean() / (sd / math.sqrt(n))) if sd > 1e-9 else None,
            "profit_factor": float(wins / losses) if losses > 0 else None, "usd_at_0p10_lot": float(x.sum() * 10) if n else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("store")
    ap.add_argument("start")
    ap.add_argument("out")
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    m15, h1 = load(a.store)
    t_from = int(pd.Timestamp(a.start, tz="UTC").timestamp())
    n_real = len(m15)
    runs = b19.engine_runs(m15, h1, log=lambda *_: None)
    up, dn = b19.struct_arrays(runs["15m"][0], n_real)
    pad = np.zeros(PAD, bool)
    P = b19.make_path(padded(m15), np.concatenate([up, pad]), np.concatenate([dn, pad]))
    res = {"window": [a.start, str(m15.index[-1])], "rules": "research/registrations/B19.json, unchanged", "baseline": {},
           "configs": {}, "trades": {}, "pending": [], "note": ("exploratory and descriptive; one month; the engine runs on the research Market "
                                                                  "(no macro / volume inputs), as in B19; distances at $4,000 scaled by price / 4000")}
    # baseline: random entries at every 15m close of the window, both directions
    rows = np.flatnonzero(P.t[:n_real] >= t_from)
    for T in TARGETS:
        for nm, sgn in (("BUY", 1), ("SELL", -1)):
            r = b13.race(padded(m15), P.t[rows] + 900, P.c[rows], np.full(len(rows), sgn), T, 13.0, nbars=b19.HOLD)
            dec = r["win"] | r["loss"]
            res["baseline"][f"random {nm} +{T:g} before -13"] = {"entries": int(dec.sum()), "tp_first": float(r["win"][dec].mean())}
    fams = {}
    for kind in ("ENG", "STR"):
        trig = [x for tf, (run, F) in runs.items() for x in b19.triggers_from_run(run, F, tf, kind)]
        trig = b19.dedupe([x for x in trig if x["t_close"] >= t_from])
        fams[kind] = b19.attach(trig, P)
    for kind, A in fams.items():
        if not len(A["d"]):
            continue
        for conf in b19.CONFS:
            C = b19.confirm(P, A, conf)
            end_real = A["j0"] + b19.WIN > n_real                   # the confirmation window runs past the last bar
            if conf != "none":
                for x in np.flatnonzero((C["status"] == "EXPIRED") & end_real):
                    C["status"][x] = "PENDING"
            targets = TARGETS + ((13.0,) if conf == "none" else ())
            for T in targets:
                T_ = b19.plan_and_exit(P, A, C, conf, "E1", "S13", T, rules=(T != 13.0))
                ex = T_["execute"]
                key = f"{kind} {conf} S13 T{T:g}" if T != 13.0 else f"{kind} as alerted 13/13"
                st = stats(T_["net"][ex], T_["outcome"][ex])
                st.update(triggers=len(A["d"]), confirmed=int((C["status"] == "CONFIRMED").sum()),
                          invalidated=int((C["status"] == "INVALIDATED").sum()), pending=int((C["status"] == "PENDING").sum()),
                          expired=int((C["status"] == "EXPIRED").sum()))
                res["configs"][key] = st
                lst = []
                for x in np.flatnonzero(ex):
                    tr = A["trig"][x]
                    lst.append({"trigger": f"{tr['tf']} {'BUY' if tr['dir'] > 0 else 'SELL'} {mt5(tr['t_close'])} MT5 at {tr['p0']:.2f}",
                                "confirmed": mt5(P.t[C['k'][x]] + 900) if C["k"][x] >= 0 else None,
                                "entry": round(float(T_["entry"][x]), 2), "result": T_["outcome"][x] if np.isfinite(T_["net"][x]) else "OPEN",
                                "net_usd_per_oz": None if not np.isfinite(T_["net"][x]) else round(float(T_["net"][x]), 2)})
                res["trades"][key] = lst
            if conf == "X15F0":                                     # Monday's watch list: triggers still waiting
                for x in np.flatnonzero(C["status"] == "PENDING"):
                    tr, s = A["trig"][x], A["p0"][x] / 4000.0
                    d = int(A["d"][x])
                    res["pending"].append({"family": kind, "trigger": f"{tr['tf']} {'BUY' if d > 0 else 'SELL'} {mt5(tr['t_close'])} MT5",
                                           "trigger_price": round(tr["p0"], 2), "confirm_at_close_beyond": round(tr["p0"] + d * 15 * s, 2),
                                           "invalid_at": round(tr["p0"] - d * 13 * s, 2), "bars_left": int(A["j0"][x] + b19.WIN - n_real)})
    with open(a.out, "w") as f:
        json.dump(b13._clean(res), f, indent=1, allow_nan=False)
    if a.trials:
        for k, v in res["configs"].items():
            H.log_trial(a.trials, {"phase": "B19-month", "partition": "recent", "id": f"B19 last month {a.start} {k}",
                                   "note": "exploratory, one month, several configurations compared", **b13._clean(v)})
    for k, v in res["baseline"].items():
        print(f"{k}: {v['tp_first']:.1%} of {v['entries']}")
    def fmt(x, spec):
        return "-" if x is None else format(x, spec)

    for k, v in res["configs"].items():
        print(f"{k:28s} trig {v['triggers']:3d} conf {v['confirmed']:3d} inv {v['invalidated']:3d} pend {v['pending']:2d} | "
              f"trades {v['trades']:3d} open {v['open']} TP {fmt(v['tp_first'], '.0%')} net {fmt(v['net_usd_per_oz'], '+.2f')} "
              f"PF {fmt(v['profit_factor'], '.2f')}")
    print("pending:", res["pending"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
