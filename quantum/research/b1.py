"""Phase B1 (research/14): families with a published empirical prior, tested on DEVELOPMENT data only.

Usage (repo root):
    python -m quantum.research.b1 <research-data checkout> <out.json> [--registry research/trials.jsonl]

The grid is declared here, before any run, and is not changed after seeing results.
  Families:
    TSMOM(L)       sign(close[i] - close[i-L])                        Moskowitz, Ooi & Pedersen (2012)
    DONCHIAN(N)    close beyond the prior N-bar high / low              practitioner; Sullivan et al. (1999) family
    ASIA>LON       first London close beyond the completed Asian range   session structure (Andersen & Bollerslev 1997)
    LON>NY         first New York close beyond the London-only range     as above
    TSMOM|VOL(q)   TSMOM(L mid) only in ATR-percentile tercile q          volatility regime (Bollerslev 1986; Kim et al. 2016)
  Event grid: target k in {1, 2} R, horizon h in {4, 16} bars; R = ATR(14); stop 1 R; one position at a time.
  Timeframes: 1h and 15min (lookbacks in the same calendar hours).
  Baselines (logged, reported, not in the family tests): always long, always short.
Costs: the frozen engine model per bar. Every trial is appended to the registry; the multiple-testing statistics
use the whole family. Nothing here opens validation or the holdout.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
import pandas as pd

from .. import sessions, ta
from . import harness as H
from . import history

GRID_K = (1.0, 2.0)
GRID_H = (4, 16)
TSMOM_HOURS = (24, 72, 240)
DONCHIAN_N = (20, 55)
VOL_HOURS = 72
TFS = {"1h": ("1h", 1), "15min": ("15min", 4)}       # interval, bars per hour

# B1b (declared 2026-11-01 before its first run, after B1 showed that intraday 1-ATR targets cannot clear the frozen
# costs): the horizons where the momentum literature has its evidence (days to months). 4h bars resampled from the
# development 1h series on the 17:00 New York grid. Lookbacks in days; horizon 6 bars (1 day) or 30 bars (5 days).
B1B_TSMOM_DAYS = (5, 20, 60)
B1B_DONCHIAN_N = (20, 55)
B1B_K = (1.0, 2.0)
B1B_H = (6, 30)


def signals(df: pd.DataFrame, bph: int) -> dict:
    c, h, l = (df[x].to_numpy(float) for x in ("close", "high", "low"))
    n = len(c)
    out = {}
    for L in TSMOM_HOURS:
        Lb = L * bph
        s = np.zeros(n)
        s[Lb:] = np.sign(c[Lb:] - c[:-Lb])
        out[f"TSMOM({L}h)"] = ("TSMOM", s)
    for N in DONCHIAN_N:
        hi, lo = ta.highest(h, N), ta.lowest(l, N)
        phi, plo = np.concatenate([[np.nan], hi[:-1]]), np.concatenate([[np.nan], lo[:-1]])   # prior N bars only
        s = np.where(c > phi, 1.0, np.where(c < plo, -1.0, 0.0))
        out[f"DONCHIAN({N})"] = ("DONCHIAN", np.nan_to_num(s))
    cal = sessions.calendar(df.index)
    td = cal["trading_date"].to_numpy()
    asia, lon, ny = (cal[k].to_numpy(bool) for k in ("in_asian", "in_london", "in_ny"))
    for name, rng_mask, trade_mask in (("ASIA>LON", asia, lon & ~asia), ("LON>NY", lon & ~ny, ny)):
        s = np.zeros(n)
        cur, hi_, lo_, done = None, -np.inf, np.inf, False
        for i in range(n):
            if td[i] != cur:
                cur, hi_, lo_, done = td[i], -np.inf, np.inf, False
            if rng_mask[i] and not trade_mask[i]:
                hi_, lo_ = max(hi_, h[i]), min(lo_, l[i])          # range built from bars strictly before any signal
            elif trade_mask[i] and not done and math.isfinite(hi_):
                if c[i] > hi_:
                    s[i], done = 1.0, True
                elif c[i] < lo_:
                    s[i], done = -1.0, True
        out[name] = ("SESSION", s)
    atr = ta.atr(h, l, c, 14)
    pr = ta.percentrank(atr / c, 500)                      # previous 500 values only
    Lb = VOL_HOURS * bph
    base = np.zeros(n)
    base[Lb:] = np.sign(c[Lb:] - c[:-Lb])
    for q, (a, b) in {"low": (0, 33.34), "mid": (33.34, 66.67), "high": (66.67, 100.01)}.items():
        m = (pr >= a) & (pr < b)
        out[f"TSMOM({VOL_HOURS}h)|vol {q}"] = ("TSMOM|VOL", np.where(m, base, 0.0))
    out["ALWAYS LONG"] = ("BASELINE", np.ones(n))
    out["ALWAYS SHORT"] = ("BASELINE", -np.ones(n))
    return out


def run(rd: str, outp: str, registry: str) -> dict:
    res = {"partition": "development", "from": str(H.DEV[0]), "to": str(H.DEV[1]), "trials": [], "family": {}}
    daily, weekly, names = {}, {}, []
    for tf, (interval, bph) in TFS.items():
        df = H.partition(history.load(rd, "XAU/USD", interval), "development")
        dh = H.data_hash(df)
        cost = H.cost_pts(df.index)
        days = df.index.normalize()
        for sname, (fam, sig) in signals(df, bph).items():
            for k in GRID_K:
                for hz in GRID_H:
                    tr = H.simulate(df, sig, k=k, h=hz, cost=cost)
                    sm = H.summary(tr)
                    tid = f"{tf} {sname} k{k:g} h{hz}"
                    d = pd.Series(tr["net_r"].to_numpy(), index=days[tr["entry_i"].to_numpy()]).groupby(level=0).sum() if len(tr) else pd.Series(dtype=float)
                    rec = {"id": tid, "tf": tf, "family": fam, "signal": sname, "k": k, "h": hz, "data_hash": dh,
                           "bars": len(df), **{x: sm.get(x) for x in ("n", "gross_r", "gross_t", "net_r", "t", "pf", "win_rate_resolved", "resolved", "ambiguous", "timeouts", "max_dd_r")}}
                    if fam != "BASELINE":
                        daily[tid], weekly[tid] = d, d.groupby(pd.Grouper(freq="W")).sum() if len(d) else d
                        names.append(tid)
                    res["trials"].append(rec)
                    H.log_trial(registry, {"phase": "B1", "partition": "development", **rec})
                    print(f"{tid:42s} n {sm.get('n', 0):6d} gross {sm.get('gross_r', math.nan):+.3f} net {sm.get('net_r', math.nan):+.3f} t {sm.get('t', math.nan):+.2f} win {sm.get('win_rate_resolved', math.nan):.3f}", flush=True)
    # family statistics over the 80 non-baseline trials
    D = pd.DataFrame(daily).fillna(0.0).sort_index()
    W = pd.DataFrame(weekly).fillna(0.0).sort_index()
    rc = H.reality_check(D[names].to_numpy(), B=1000, mean_block=10.0)
    pbo = H.pbo_cscv(W[names].to_numpy(), groups=8)
    sr_d = (D[names].mean() / D[names].std(ddof=1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    best = sr_d.idxmax()
    x = D[best].to_numpy()
    dsr = H.deflated_sharpe(float(sr_d[best]), len(x), float(pd.Series(x).skew()), float(pd.Series(x).kurt() + 3), list(sr_d.values))
    tr_map = {t["id"]: t for t in res["trials"]}
    pv = [H.t_pvalue(tr_map[n_]["t"] if tr_map[n_]["t"] is not None else math.nan, tr_map[n_]["n"]) for n_ in names]
    pv = [1.0 if not math.isfinite(p) else p for p in pv]
    bh = H.benjamini_hochberg(pv, q=0.10)
    res["family"] = {"trials": len(names), "days": len(D), "weeks": len(W),
                     "reality_check": {**rc, "best_id": names[rc["best"]]}, "pbo": pbo,
                     "best_daily_sharpe": {"id": best, "sharpe_daily": float(sr_d[best]), **dsr},
                     "bh_fdr10_passed": [n_ for n_, ok in zip(names, bh) if ok],
                     "t_above_3": [n_ for n_ in names if (tr_map[n_]["t"] or 0) > 3],
                     "gross_t_above_2": [n_ for n_ in names if (tr_map[n_]["gross_t"] or 0) > 2],
                     "note": "BH and t screens are one-sided (H1: mean net R > 0). PBO measures rank stability only; read it with oos_mean_of_is_best."}
    json.dump(res, open(outp, "w"), indent=1, default=float)
    return res


def run_b1b(rd: str, outp: str, registry: str) -> dict:
    from ..data.sources import resample_ny_session
    df1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
    df = resample_ny_session(df1.assign(volume=0.0), 4)[["open", "high", "low", "close"]]
    df = H.partition(df, "development")
    c, h, l = (df[x].to_numpy(float) for x in ("close", "high", "low"))
    n = len(c)
    sig = {}
    for d in B1B_TSMOM_DAYS:
        Lb = d * 6
        s_ = np.zeros(n)
        s_[Lb:] = np.sign(c[Lb:] - c[:-Lb])
        sig[f"TSMOM({d}d)"] = ("TSMOM", s_)
    for N in B1B_DONCHIAN_N:
        hi, lo = ta.highest(h, N), ta.lowest(l, N)
        phi, plo = np.concatenate([[np.nan], hi[:-1]]), np.concatenate([[np.nan], lo[:-1]])
        sig[f"DONCHIAN({N})"] = ("DONCHIAN", np.nan_to_num(np.where(c > phi, 1.0, np.where(c < plo, -1.0, 0.0))))
    sig["ALWAYS LONG"] = ("BASELINE", np.ones(n))
    sig["ALWAYS SHORT"] = ("BASELINE", -np.ones(n))
    cost = H.cost_pts(df.index)
    days = df.index.normalize()
    dh = H.data_hash(df)
    res = {"partition": "development", "set": "B1b 4h", "bars": n, "trials": [], "family": {}}
    daily, weekly, names = {}, {}, []
    for sname, (fam, sg) in sig.items():
        for k in B1B_K:
            for hz in B1B_H:
                tr = H.simulate(df, sg, k=k, h=hz, cost=cost)
                sm = H.summary(tr)
                tid = f"4h {sname} k{k:g} h{hz}"
                rec = {"id": tid, "tf": "4h", "family": fam, "signal": sname, "k": k, "h": hz, "data_hash": dh, "bars": n,
                       **{x: sm.get(x) for x in ("n", "gross_r", "gross_t", "net_r", "t", "pf", "win_rate_resolved", "resolved", "ambiguous", "timeouts", "max_dd_r")}}
                res["trials"].append(rec)
                H.log_trial(registry, {"phase": "B1b", "partition": "development", **rec})
                if fam != "BASELINE":
                    d_ = pd.Series(tr["net_r"].to_numpy(), index=days[tr["entry_i"].to_numpy()]).groupby(level=0).sum()
                    daily[tid], weekly[tid] = d_, d_.groupby(pd.Grouper(freq="W")).sum()
                    names.append(tid)
                print(f"{tid:32s} n {sm.get('n', 0):5d} gross {sm.get('gross_r', math.nan):+.3f} (t {sm.get('gross_t', math.nan):+.2f}) "
                      f"net {sm.get('net_r', math.nan):+.3f} t {sm.get('t', math.nan):+.2f} cost {sm.get('gross_r', 0) - sm.get('net_r', 0):.3f} win {sm.get('win_rate_resolved', math.nan):.3f}", flush=True)
    D = pd.DataFrame(daily).fillna(0.0).sort_index()
    W = pd.DataFrame(weekly).fillna(0.0).sort_index()
    rc = H.reality_check(D[names].to_numpy(), B=1000, mean_block=10.0)
    tr_map = {t["id"]: t for t in res["trials"]}
    pv = [H.t_pvalue(tr_map[x]["t"], tr_map[x]["n"]) for x in names]
    pv = [1.0 if not math.isfinite(p) else p for p in pv]
    res["family"] = {"trials": len(names), "reality_check": {**rc, "best_id": names[rc["best"]]},
                     "pbo": H.pbo_cscv(W[names].to_numpy(), groups=8),
                     "bh_fdr10_passed": [x for x, ok in zip(names, H.benjamini_hochberg(pv, 0.10)) if ok],
                     "t_above_3": [x for x in names if (tr_map[x]["t"] or 0) > 3],
                     "gross_t_above_2": [x for x in names if (tr_map[x]["gross_t"] or 0) > 2]}
    json.dump(res, open(outp, "w"), indent=1, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rd")
    ap.add_argument("out")
    ap.add_argument("--registry", default="research/trials.jsonl")
    ap.add_argument("--set", default="b1", choices=("b1", "b1b"))
    a = ap.parse_args(argv)
    r = (run if a.set == "b1" else run_b1b)(a.rd, a.out, a.registry)
    print(json.dumps(r["family"], indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
