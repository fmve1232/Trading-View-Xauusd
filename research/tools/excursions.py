"""Section 9 of the operator's master instruction (2026-11-07): the metrics the earlier studies did not report, i.e.
average favourable / adverse excursion, realised reward / risk, BUY / SELL split, stop-hit rate, expectancy, profit
factor, maximum drawdown and the trades that reached neither level, for every trigger type at +$15 / +$20 before -$13.

DESCRIPTIVE, DEVELOPMENT DATA ONLY (2020-01-24 -> 2023-01-24, scored from 2020-04-01): the populations and the plan
are the registered ones (B19 ENG, B21 GRAB / BREAK / SWEEP / BREAKOUT, B21 N2 random triggers; confirmation none or
X15F0; entry E1; stop S13), nothing is selected or tuned, and no sealed partition is read. Outcomes come from
quantum/research/b19.py; the excursions from quantum/confirm_panel.exit_one, the function the live panel uses, and
the script stops if the two disagree on any trade's outcome or net result (live and historical calculations must
agree). Distances are scaled by price / 4000 as in the studies; excursions are reported in those $ (at $4,000).

  python research/tools/excursions.py --rd <research-data dir> --out research/results/excursions_development_2026-11-07.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum import confirm_panel as cp
from quantum.research import b13, b19, b21

FAMS = ("ENG", "GRAB", "BREAK", "SWEEP", "BREAKOUT", "N2")
CONFS = ("none", "X15F0")
TS = (15.0, 20.0)
FIXED = 96                        # "expected movement": the largest move for / against within the next 96 15m bars


def wilson(k: int, n: int) -> list:
    if not n:
        return [None, None]
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [mid - half, mid + half]


def pdict(P: b19.Path15) -> dict:
    return {"t": P.t.tolist(), "o": P.o, "h": P.h, "l": P.l, "c": P.c, "up": P.up_evt, "dn": P.dn_evt}


def measure(P: b19.Path15, Pd: dict, A: dict, conf: str, T: float) -> dict:
    C = b19.confirm(P, A, conf)
    R = b19.plan_and_exit(P, A, C, conf, "E1", "S13", T)
    ex = np.flatnonzero(R["execute"])
    d, p0 = A["d"], A["p0"]
    s = p0 / 4000.0
    k = C["k"]                                              # "none": j0 - 1, the trade starts on bar j0 at the trigger price
    mfe, mae = np.zeros(len(ex)), np.zeros(len(ex))
    for n_, x in enumerate(ex):
        e = cp.exit_one(Pd, int(k[x]), int(d[x]), T, float(s[x]), entry=float(R["entry"][x]))
        if e["out"] != R["outcome"][x] or abs(e["usd"] / s[x] - (R["net"][x] + R["cost"][x])) > 1e-6:
            raise SystemExit(f"live / research disagree: {conf} T{T:g} trade {x}: {e['out']} vs {R['outcome'][x]}")
        mfe[n_], mae[n_] = e["mfe"] / s[x], e["mae"] / s[x]
    out, net, r = R["outcome"][ex], R["net"][ex], R["r"][ex]
    order = np.argsort(R["t_entry"][ex], kind="stable")
    ent = R["entry"][ex]
    b0 = (k[ex] + 1).astype(int)
    hh, ll = sliding_window_view(P.h, FIXED)[b0], sliding_window_view(P.l, FIXED)[b0]
    dd = d[ex][:, None]
    fav_fix = np.nanmax(np.where(dd > 0, hh - ent[:, None], ent[:, None] - ll), axis=1) / s[ex]
    adv_fix = np.nanmax(np.where(dd > 0, ent[:, None] - ll, hh - ent[:, None]), axis=1) / s[ex]
    n = len(ex)
    wins, losses = net[net > 0], net[net < 0]
    tp = int((out == "TP").sum())
    buy, sell = d[ex] > 0, d[ex] < 0
    res = {"trades": n, "triggers": len(A["d"]), "confirmed": int((C["status"] == "CONFIRMED").sum()) if conf != "none" else None,
           "tp_first": tp / n if n else None, "tp_first_ci95": wilson(tp, n),
           "stop_first": float(np.mean((out == "SL") | (out == "AMBIGUOUS"))) if n else None,
           "of_which_ambiguous": float(np.mean(out == "AMBIGUOUS")) if n else None,
           "neither_in_192_bars": float(np.mean(out == "TIMEOUT")) if n else None,
           "buy": {"n": int(buy.sum()), "tp_first": float(np.mean(out[buy] == "TP")) if buy.any() else None},
           "sell": {"n": int(sell.sum()), "tp_first": float(np.mean(out[sell] == "TP")) if sell.any() else None},
           "avg_mfe_usd": float(mfe.mean()) if n else None, "median_mfe_usd": float(np.median(mfe)) if n else None,
           "avg_mae_usd": float(mae.mean()) if n else None, "median_mae_usd": float(np.median(mae)) if n else None,
           "fixed96_avg_favourable_usd": float(np.nanmean(fav_fix)) if n else None,
           "fixed96_avg_adverse_usd": float(np.nanmean(adv_fix)) if n else None,
           "fixed96_reached_target_share": float(np.mean(fav_fix >= T - 1e-9)) if n else None,
           "avg_win_usd": float(wins.mean()) if len(wins) else None, "avg_loss_usd": float(losses.mean()) if len(losses) else None,
           "realised_reward_risk": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else None,
           "expectancy_usd_per_oz": float(net.mean()) if n else None,
           "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,
           "max_drawdown_r": b19.max_drawdown(r[order]), "avg_cost_usd_per_oz": float(R["cost"][ex].mean()) if n else None,
           "avg_hold_min": float(np.mean(R["hold_min"][ex])) if n else None}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    m15, h1, score_from = b19.load_part(a.rd, "development")
    runs = b19.engine_runs(m15, h1)
    up, dn = b19.struct_arrays(runs["15m"][0], len(m15))
    P = b19.make_path(m15, up, dn)
    Pd = pdict(P)
    t_from = int(score_from.timestamp())
    eng = b19.dedupe([x for tf, (res, F) in runs.items() for x in b19.triggers_from_run(res, F, tf, "ENG") if x["t_close"] >= t_from])
    trig, P21 = b21.alerts(m15, h1, score_from)
    assert np.array_equal(P21.up_evt, P.up_evt) and np.array_equal(P21.c, P.c)       # the same 15m path and structure
    rows = np.flatnonzero(P.t >= t_from)[::8]
    rows = rows[(rows >= b19.SSTR_LOOKBACK) & (rows + 1 + b19.WIN + b19.HOLD + b19.LIMIT_BARS < len(P.t))]
    n2 = [{"tf": "15m", "kind": "N2", "i": int(i), "t_close": int(P.t[i]) + 900, "dir": sg, "p0": float(P.c[i])} for i in rows for sg in (1, -1)]
    fams = {"ENG": b19.attach(eng, P), "N2": b19.attach(n2, P), **{k: b19.attach(v, P) for k, v in trig.items()}}
    out = {"what": "master instruction section 9: excursions and the other unreported metrics (descriptive, development only)",
           "window": [str(m15.index[0]), str(m15.index[-1])], "scored_from": str(score_from), "plan": "entry E1, stop S13, ties = loss",
           "scale": "distances and excursions in $ at $4,000 (price / 4000)", "results": {}}
    for f in FAMS:
        for conf in CONFS:
            for T in TS:
                out["results"][f"{f} {conf} T{T:g}"] = measure(P, Pd, fams[f], conf, T)
                print(f, conf, T, {k: out["results"][f"{f} {conf} T{T:g}"][k] for k in ("trades", "tp_first", "avg_mfe_usd", "avg_mae_usd")}, flush=True)
    out["utc"] = datetime.now(timezone.utc).isoformat()
    with open(a.out, "w") as fh:
        json.dump(b13._clean(out), fh, indent=1, allow_nan=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
