"""Phase B5 (EXPLORATORY): an order-flow PROXY from the stored COMEX gold-futures bars, on the operator's -$10 stop
with +$10 / +$15 / +$20 targets. Declared 2026-11-01, committed before the first run, not changed after seeing results.

    python -m quantum.research.b5_flow_proxy <market-data checkout> <out.json> [--registry research/trials.jsonl]

WHY A PROXY. Real order flow (aggressor-signed trades, order-flow imbalance at the best bid / ask) for gold exists only
on COMEX futures (GC / MGC) and needs paid CME data (research/ORDER_FLOW_RESEARCH.md). Spot XAUUSD trades over the
counter, with no consolidated book. The site's store already holds Yahoo GC=F 5-minute bars WITH exchange volume
(2026-07-17 onward), so a free proxy can say whether paying for real order-flow data is worth it. It cannot prove or
disprove order flow: bar-level classification is a coarse estimate of who traded aggressively.

DATA (market-data branch, NOT the research partitions): GC=F 5-minute bars (signals); spot XAU/USD 5-minute bars
(Twelve Data; paths and entry prices). Window: where both exist (spot from 2026-09-09).
PROXY: bulk volume classification (Easley, Lopez de Prado & O'Hara 2012): a bar's buy share = Phi(dP / sigma), sigma =
standard deviation of the previous 100 five-minute GC price changes; bars moving more than 8 sigma (contract rolls)
are excluded (volume and sign set to 0).
IMBALANCE: sum((2 Phi - 1) x V) / sum(V) over the last 12 GC bars (1 hour), in [-1, 1], known at the GC bar's close.
SIGNAL: |imbalance| at or above its own trailing 90th percentile (the previous 2,000 bars, the current one excluded).
RULES: FLOW_CONT trades in the imbalance's sign (the literature's direction: order flow moves price, Cont, Kukanov &
       Stoikov 2014); FLOW_REV the opposite, reported for completeness.
TRADES: entry at the spot close of the same 5-minute bar; targets +$10 / +$15 / +$20 before -$10 scaled to $4,000;
spot 5-minute paths, 1 trading day (288 bars); B2's fills, costs (scaled) and one-position rule.
BASELINE: every 3rd spot 5-minute close, long and short, same targets; matched to each rule's direction mix.
6 trials, logged with partition 'live-window-2026'. EXPLORATORY: this window cannot be validated (it is the window
the site's panels already show), so B2's five-part rule is reported but no result here can be registered.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
import pandas as pd

from .. import ta
from ..data import sources, store
from . import b2
from . import harness as H

TARGETS = {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
SIGMA_BARS, WINDOW_BARS, ROLL_SIGMA = 100, 12, 8.0
PCT, PCT_BARS = 0.90, 2000
RANDOM_STEP = 3


def _phi(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def bvc_imbalance(c: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Hourly bulk-volume-classified imbalance at each bar's close (uses bars <= i only)."""
    dp = np.r_[np.nan, np.diff(c)]
    sd = pd.Series(dp).shift(1).rolling(SIGMA_BARS, min_periods=SIGMA_BARS).std().to_numpy()
    z = np.where(sd > 0, dp / sd, np.nan)
    roll = np.abs(z) > ROLL_SIGMA
    sign = np.where(np.isfinite(z) & ~roll, 2.0 * _phi(np.nan_to_num(z)) - 1.0, 0.0)
    vol = np.where(np.isfinite(z) & ~roll, np.nan_to_num(v), 0.0)
    num = pd.Series(sign * vol).rolling(WINDOW_BARS, min_periods=WINDOW_BARS).sum().to_numpy()
    den = pd.Series(vol).rolling(WINDOW_BARS, min_periods=WINDOW_BARS).sum().to_numpy()
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)


def signals(imb: np.ndarray) -> np.ndarray:
    """+1 / -1 where |imbalance| reaches its trailing 90th percentile (previous PCT_BARS bars, current excluded)."""
    a = pd.Series(np.abs(imb))
    thr = a.shift(1).rolling(PCT_BARS, min_periods=PCT_BARS).quantile(PCT).to_numpy()
    on = np.isfinite(imb) & np.isfinite(thr) & (np.abs(imb) >= thr) & (imb != 0)
    return np.where(on, np.sign(imb), 0.0)


def _load(md: str):
    gc = sources.trading_week_only(sources.drop_offgrid(store.load(md, "GC=F_5m")))
    sp = sources.repair_reopen(sources.trading_week_only(sources.drop_offgrid(store.load(md, "XAU/USD_5m"))), 300)
    return gc, sp


def run(md: str, outp: str, registry: str) -> dict:
    gc, sp = _load(md)
    P = b2.Paths(sp)
    imb = bvc_imbalance(gc["close"].to_numpy(float), gc["volume"].to_numpy(float))
    s = signals(imb)
    t_close = ta.epoch_s(gc.index) + 300
    spot_close = pd.Series(sp["close"].to_numpy(float), index=ta.epoch_s(sp.index) + 300)
    cost_sp = pd.Series(H.cost_pts(sp.index), index=ta.epoch_s(sp.index) + 300)
    res = {"set": "B5-explore", "partition": "live-window-2026", "gc_bars": len(gc), "spot_bars": len(sp),
           "window": [str(sp.index[0]), str(sp.index[-1])], "signals": int((s != 0).sum()), "baseline": {}, "trials": []}
    # random baseline on the spot paths
    k = np.arange(0, len(P.t), RANDOM_STEP)
    j, ok = P.locate(P.t[k] + b2.PATH_SEC)
    jr, pr = j[ok], P.c[k][ok]
    sc = pr / b2.REF_PRICE
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        ev = P.evaluate(jr, pr, np.full(len(jr), dv), [(a * sc, b * sc) for a, b in TARGETS.values()])
        for (tn, _), e in zip(TARGETS.items(), ev):
            res["baseline"][f"{tn} {dname}"] = float(np.mean(e["out"] == 1))
    i = np.flatnonzero(s != 0)
    i = i[np.isin(t_close[i], spot_close.index.to_numpy())]
    t_dec = t_close[i]
    p = spot_close.loc[t_dec].to_numpy(float)
    cst = cost_sp.loc[t_dec].to_numpy(float)
    names, pv = [], []
    for rule, sgn in (("FLOW_CONT", 1.0), ("FLOW_REV", -1.0)):
        d = s[i] * sgn
        jj, okk = P.locate(t_dec)
        jj, pp, dd, tt, cc = jj[okk], p[okk], d[okk], t_dec[okk], cst[okk]
        scl = pp / b2.REF_PRICE
        ev = P.evaluate(jj, pp, dd, [(a * scl, b * scl) for a, b in TARGETS.values()])
        for q, (tn, (a, b)) in enumerate(TARGETS.items()):
            e = ev[q]
            keep = b2.one_position(tt, P.t[np.minimum(e["exit"], len(P.t) - 1)] + b2.PATH_SEC)
            st = b2._stats(e["out"][keep], e["pnl"][keep], cc[keep] * scl[keep], a * scl[keep], b * scl[keep], dd[keep])
            if st["n"]:
                rnd = (st["long"] * res["baseline"][f"{tn} long"] + st["short"] * res["baseline"][f"{tn} short"]) / st["n"]
                z = (st["win_rate"] - rnd) / math.sqrt(max(rnd * (1 - rnd), 1e-12) / st["n"])
            else:
                rnd = z = math.nan
            tid = f"5min {rule} {tn}"
            rec = {"id": tid, "rule": rule, "target": tn, **{x: st.get(x) for x in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "t")},
                   "random_same_mix": rnd, "z_vs_random": z, "usd_per_trade_0p5lot": st["net_r"] * b * 50 if st["n"] else None}
            res["trials"].append(rec)
            H.log_trial(registry, {"phase": "B5-explore", "partition": "live-window-2026", **rec})
            names.append(tid)
            pv.append(H.t_pvalue(st["t"], st["n"]) if st["n"] and st["t"] is not None and math.isfinite(st["t"]) else 1.0)
            print(f"{tid:22s} n {st.get('n', 0):4d} win {st.get('win_rate', math.nan):.3f} rand {rnd:.3f} z {z:+.2f} "
                  f"be {st.get('break_even', math.nan):.3f} net {st.get('net_r', math.nan):+.3f}R t {st.get('t', math.nan):+.2f}", flush=True)
    res["bh_fdr10_passed"] = [n_ for n_, okb in zip(names, H.benjamini_hochberg(pv, 0.10)) if okb]
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
    print(json.dumps({k: r[k] for k in ("window", "signals", "baseline", "bh_fdr10_passed")}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
