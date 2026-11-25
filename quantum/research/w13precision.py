"""B31b-W13 (research only; production never imports this module): every registered entry mechanism on one yardstick,
and a revalidation of B31b-W12 from its trade-level data. research/registrations/B31b-W13.json fixes every rule.

  trades     each study's own counted development trades: W3 / W7 / W8 / W12 re-run in memory from their unchanged code
             (W3 and W7 must reproduce their committed counts), W4 / W5 from their committed trade files ('counted')
  cost       every trade re-costed at the B31b-W8 decision cost of the session it filled in: g = R (D + c_old) + c_old,
             R_new = (g - c_new) / (D + c_new); sensitivity x1.5
  metrics    +$10 / +$15 / +$20-first and stop-first (Wilson 95%), MFE / MAE, net R and USD per trade (day-clustered
             bootstrap 95%) and per week, profit factor, maximum drawdown at $650 per trade, 6 walk-forward folds, years,
             volatility regimes; SUPPORTED by the registered rule, Holm over every mechanism of the six families

Development partition only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import sessions, ta
from . import harness as H
from . import w3liq as W
from . import w7breakout as X
from . import w8quality as Q
from . import w12session as Z

REG = "B31b-W13"
TPS = (10, 15, 20)
USD_R = 650.0
BOOT = 2000
FOLDS = 6
MIN_DECIDED = 100
W5_METHODS = ("A0", "A1", "B0.236", "B0.382", "B0.5", "B0.618", "B0.786", "B0.3", "B0.45", "B0.55", "B0.7", "C", "E", "F", "G20",
              "G50", "H", "I", "J", "K")
OPEN_SESS = ("LDN_OPEN", "NY_OPEN")
FAMILIES = {
    "1 sweep + displacement": [("W3", "A-DISP", "M15"), ("W3", "A-DISP", "M30"), ("W4", "A5", None), ("W4", "B2", None)],
    "2 structure shift 5M/15M": [("W3", "A-MSS", "M15"), ("W3", "A-MSS", "M30"), ("W3", "A-M5MSS", "M15"), ("W3", "A-M5MSS", "M30"),
                                 ("W4", "A3", None), ("W4", "B3", None), ("W4", "B4", None)],
    "3 sweep, reclaim, retest": [("W3", "A-RETEST", "M15"), ("W3", "A-RETEST", "M30"), ("W4", "B1", None)],
    "4 breakout, then retest": [("W3", "B-RETEST", "M15"), ("W3", "B-RETEST", "M30"), ("W4", "C1", None), ("W4", "C2", None),
                                ("W4", "A4", None), ("W7", "E2", "M15"), ("W7", "E2", "M30")],
    "5 session continuation (London / NY open)": [("W3s", "B-ACC", "M15"), ("W3s", "B-ACC", "M30"), ("W7s", "E1", "M15"), ("W7s", "E1", "M30")],
    "6 entry timing / structural stops": [("W5", m, None) for m in W5_METHODS] + [("W4", m, None) for m in ("T1", "T4", "T6")]
                                          + [("W7", "E3", "M15"), ("W7", "E3", "M30")],
}
BASELINES = [("W3", "A-IMM", "M15"), ("W3", "A-IMM", "M30"), ("W12", "H1", None), ("W12x", "H1", None), ("W7", "E0", "M15"),
             ("W7", "E0", "M30"), ("W7", "E1", "M15"), ("W7", "E1", "M30"), ("W8", "E0", "M15"), ("W8", "E0", "M30"),
             ("W8", "E1", "M15"), ("W8", "E1", "M30"), ("W5", "B_rand", None)]


# ---------------- cost and calendar ----------------
def sess_at(t: np.ndarray) -> np.ndarray:
    """The W3 session bucket of the 15m bar holding each epoch second."""
    t = np.asarray(t, np.int64)
    bar = t - t % 900
    return W.sess_bucket(sessions.calendar(pd.DatetimeIndex(pd.to_datetime(bar, unit="s", utc=True))))


def recost(r_old: float, D: float, c_old: float, c_new: float) -> float:
    """The same trade's net R at another round-trip cost (gross move g = R (D + c) + c)."""
    if not (np.isfinite(r_old) and np.isfinite(D) and D > 0):
        return math.nan
    g = r_old * (D + c_old) + c_old
    return (g - c_new) / (D + c_new)


def vol_regime(m15: pd.DataFrame) -> dict:
    """{trading date: HIGH / NORMAL / LOW}: the previous trading day's M15 range against the median of the 60 trading
    days before it (HIGH > 1.25x, LOW < 0.80x)."""
    cal = sessions.calendar(m15.index)
    td = cal["trading_date"].to_numpy()
    g = pd.DataFrame({"td": td, "h": m15["high"].to_numpy(), "l": m15["low"].to_numpy()}).groupby("td")
    rng = (g["h"].max() - g["l"].min()).sort_index()
    prev = rng.shift(1)
    med = rng.shift(2).rolling(60, min_periods=40).median()
    out = {}
    for d in rng.index:
        p, m = prev.get(d), med.get(d)
        out[d] = "NA" if not (np.isfinite(p) and np.isfinite(m)) else ("HIGH" if p > 1.25 * m else "LOW" if p < 0.80 * m else "NORMAL")
    return out


# ---------------- uniform rows ----------------
def uniform(rows: list[dict], cost_map: dict, mfe_key="mfe", mae_key="mae") -> list[dict]:
    """t (fill), d, D, sess, outcomes, net R at the decision cost (and x1.5), MFE / MAE."""
    if not rows:
        return []
    t = np.array([int(r["t_fill"]) for r in rows], np.int64)
    ss = sess_at(t)
    out = []
    for r, s, tt in zip(rows, ss, t):
        c_new = float(cost_map[str(s)])
        u = {"t": int(tt), "d": int(r["d"]), "D": float(r["D"]), "sess": str(s), "cost": c_new,
             "mfe": float(r[mfe_key]) if r.get(mfe_key) is not None and np.isfinite(float(r[mfe_key])) else math.nan,
             "mae": float(r[mae_key]) if r.get(mae_key) is not None and np.isfinite(float(r[mae_key])) else math.nan}
        for T in TPS:
            k = f"tp{T}"
            u[k] = str(r.get(k))
            u[k + "_r"] = recost(float(r[k + "_r"]), float(r["D"]), float(r["cost"]), c_new)
            u[k + "_r15"] = recost(float(r[k + "_r"]), float(r["D"]), float(r["cost"]), 1.5 * c_new)
        out.append(u)
    return out


DECIDED = ("TP", "SL", "AMBIGUOUS", "TIMEOUT", "TO")


def boot(x: np.ndarray, days: np.ndarray, seed: int = 21) -> tuple[list[float], float]:
    """Day-clustered bootstrap of the mean: 95% interval and one-sided p(mean <= 0)."""
    u, inv = np.unique(days, return_inverse=True)
    s, n = np.bincount(inv, weights=x), np.bincount(inv)
    rng = np.random.default_rng(seed)
    p = rng.integers(0, len(u), size=(BOOT, len(u)))
    bm = s[p].sum(1) / n[p].sum(1)
    return [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))], float((bm <= 0).mean())


def max_dd(rs: np.ndarray, ts: np.ndarray) -> float:
    eq = np.cumsum(USD_R * rs[np.argsort(ts, kind="stable")])
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    return float(np.max(peak - eq)) if len(eq) else 0.0


def metrics(rows: list[dict], weeks: float, lo: int, hi: int, vol: dict, td_of) -> dict:
    rows = [r for r in rows if r["tp10"] in DECIDED and np.isfinite(r["tp10_r"])]
    n = len(rows)
    out = {"trades": n, "per_week": n / weeks}
    if not n:
        return out
    t = np.array([r["t"] for r in rows])
    days = t // 86400
    for T in TPS:
        k = f"tp{T}"
        oc = np.array([r[k] for r in rows])
        kk, ks = int((oc == "TP").sum()), int(np.isin(oc, ("SL", "AMBIGUOUS")).sum())
        out[f"tp{T}_first"] = {"rate": kk / n, "wilson95": list(H.wilson(kk, n))}
        if T == 10:
            out["stop_first"] = {"rate": ks / n, "wilson95": list(H.wilson(ks, n))}
    r10 = np.array([r["tp10_r"] for r in rows])
    ci, p = boot(r10, days)
    pos, neg = r10[r10 > 0].sum(), -r10[r10 < 0].sum()
    out.update(net_r=float(r10.mean()), net_r_day95=ci, p_one_sided=p, usd_per_trade=float(r10.mean() * USD_R),
               usd_per_week=float(r10.mean() * USD_R * n / weeks), profit_factor=float(pos / neg) if neg > 0 else math.inf,
               max_drawdown_usd=max_dd(r10, t), net_r_x15=float(np.nanmean([r["tp10_r15"] for r in rows])),
               break_even=float(np.mean([(r["D"] + r["cost"]) / (10 + r["D"]) for r in rows])),
               median_stop=float(np.median([r["D"] for r in rows])))
    for T in (15, 20):
        out[f"net_r_tp{T}"] = float(np.nanmean([r[f"tp{T}_r"] for r in rows]))
    mf = np.array([r["mfe"] for r in rows])
    ma = np.array([r["mae"] for r in rows])
    if np.isfinite(mf).any():
        out["mfe_mean"], out["mfe_median"] = float(np.nanmean(mf)), float(np.nanmedian(mf))
        out["mae_mean"], out["mae_median"] = float(np.nanmean(ma)), float(np.nanmedian(ma))
    edges = np.linspace(lo, hi, FOLDS + 1)
    out["folds"] = [float(r10[(t >= edges[f]) & (t < edges[f + 1])].mean()) if ((t >= edges[f]) & (t < edges[f + 1])).any()
                    else None for f in range(FOLDS)]
    yrs = np.array([datetime.fromtimestamp(x, timezone.utc).year for x in t])
    out["years"] = {str(y): {"n": int((yrs == y).sum()), "net_r": float(r10[yrs == y].mean())} for y in sorted(set(yrs.tolist()))}
    vr = np.array([vol.get(td_of(x), "NA") for x in t])
    out["vol"] = {v: {"n": int((vr == v).sum()), "net_r": float(r10[vr == v].mean())} for v in ("LOW", "NORMAL", "HIGH") if (vr == v).any()}
    return out


def supported(m: dict, holm_p: float | None) -> bool:
    if m.get("trades", 0) < MIN_DECIDED or holm_p is None:
        return False
    folds_pos = sum(1 for f in m["folds"] if f is not None and f > 0)
    years_ok = all(m["years"].get(str(y), {}).get("net_r", -1) > 0 for y in (2020, 2021, 2022))
    return bool(m["net_r"] > 0 and m["net_r_day95"][0] > 0 and holm_p < 0.05 and folds_pos >= 5 and years_ok)


def holm(ps: dict) -> dict:
    items = sorted((p, k) for k, p in ps.items() if p is not None and np.isfinite(p))
    m_, out, run = len(items), {}, 0.0
    for r, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m_ - r) * p))
        out[k] = run
    return out


# ---------------- sources ----------------
def load_all(rd: str, w4_csv: str, w5_csv: str, cost_file: str, log=print) -> dict:
    cost_map = Z.load_cost(cost_file)
    src: dict = {}
    log("W3 ...")
    res3 = W.run_part(rd, "development", None, log=lambda *a, **k: None)
    V = W.variants(res3)
    for (m, tf), v in V.items():
        src[("W3", m, tf)] = uniform(v["kept"], cost_map)
        if m == "B-ACC":
            src[("W3s", m, tf)] = [r for r in src[("W3", m, tf)] if r["sess"] in OPEN_SESS]
    meta = res3["meta"]
    log("W7 / W8 ...")
    m15, h1, m5, score_from = W.load(rd, "development", None)
    res7 = X.build(m15, h1, m5, score_from)
    for m in ("E0", "E1", "E2", "E3", "E4"):
        for tf in ("M15", "M30"):
            src[("W7", m, tf)] = uniform(X.counted(res7["rows"], m, tf), cost_map)
            if m == "E1":
                src[("W7s", m, tf)] = [r for r in src[("W7", m, tf)] if r["sess"] in OPEN_SESS]
    res8 = Q.build(m15, h1, m5, score_from, Q.load_cost(cost_file, "2026-11-25"))
    sel8 = [r for r in res8["rows"] if r.get("selected")]
    for m in ("E0", "E1"):
        for tf in ("M15", "M30"):
            src[("W8", m, tf)] = uniform(X.counted(sel8, m, tf), cost_map)
    for name, path in (("W4", w4_csv), ("W5", w5_csv)):
        df = pd.read_csv(path)
        df = df[df["counted"] == 1]
        for m, g in df.groupby("m"):
            src[(name, m, None)] = uniform(g.to_dict("records"), cost_map)
    log("W12 ...")
    eu = Z.history.load(rd, "EUR/USD", "15min")
    eu = H.partition(eu, "development") if eu is not None else None
    res12 = Z.build(m15, h1, m5, eu, score_from, cost_map)
    h1rows = [r for r in res12["rows"] if r["H1"]]
    fp = Z.fine_path(m15, m5)
    for r in h1rows:
        r.update(path_stats(fp, r))
    src[("W12", "H1", None)] = uniform([{**r, "t_fill": r["t0"]} for r in h1rows], cost_map, "mfe24", "mae24")
    src[("W12x", "H1", None)] = uniform([{**r, "t_fill": r["t0"]} for r in one_at_a_time(h1rows)], cost_map, "mfe24", "mae24")
    return {"src": src, "w3_meta": meta, "w7_counts": {f"{m}:{tf}": len(src[("W7", m, tf)]) for m in ("E0", "E1") for tf in ("M15", "M30")},
            "w3_counts": {f"{m}|{tf}": len(src[("W3", m, tf)]) for m in ("A-IMM", "A-DISP", "B-ACC") for tf in ("M15", "M30")},
            "m15": m15, "score_from": score_from, "w12_rows": res12["rows"], "cost_map": cost_map}


# ---------------- W12 revalidation ----------------
def path_stats(fp: dict, r: dict) -> dict:
    """For one W12 trade (entry r['entry'] at r['t0'], stop r['stop'], dir r['d']): the +$10 race's exit time, minutes to
    the stop, MFE / MAE over the trade and over 24 h ($ at $4,000), and whether a stopped trade later reached +$10."""
    s = r["entry"] / 4000.0
    d, e, stop = r["d"], r["entry"], r["stop"]
    i0 = int(np.searchsorted(fp["t"], r["t0"], side="left"))
    i1 = int(np.searchsorted(fp["t"], r["t0"] + Z.HOLD_SEC, side="left"))
    h, l, t = fp["h"][i0:i1], fp["l"][i0:i1], fp["t"][i0:i1]
    out = {"exit10": None, "min_to_stop": None, "mfe24": math.nan, "mae24": math.nan, "beyond_wick": None, "stopped_then_right": None,
           "mae_to_exit": None}
    if not len(t):
        return out
    fav = (h - e) * d if d == 1 else (e - l)
    adv = (e - l) if d == 1 else (h - e)
    out["mfe24"], out["mae24"] = float(np.max(fav) / s), float(np.max(adv) / s)
    tg = e + d * 10 * s
    hit_s = (l <= stop) if d == 1 else (h >= stop)
    hit_t = (h >= tg) if d == 1 else (l <= tg)
    ks = int(np.argmax(hit_s)) if hit_s.any() else None
    kt = int(np.argmax(hit_t)) if hit_t.any() else None
    if ks is not None and (kt is None or ks <= kt):
        out["exit10"] = int(t[ks]) + 300
        out["min_to_stop"] = float((t[ks] + 300 - r["t0"]) / 60.0)
        beyond = (stop - l[ks]) if d == 1 else (h[ks] - stop)
        out["beyond_wick"] = float(max(beyond, 0.0) / s)
        out["stopped_then_right"] = bool(hit_t[ks + 1:].any()) if ks + 1 < len(t) else False
    elif kt is not None:
        out["exit10"] = int(t[kt]) + 300
        out["mae_to_exit"] = float(np.max(adv[:kt + 1]) / s)
    else:
        out["exit10"] = int(t[-1]) + 300
    return out


def one_at_a_time(rows: list[dict]) -> list[dict]:
    out, busy = [], -1
    for r in sorted(rows, key=lambda x: x["t0"]):
        if r["t0"] < busy:
            continue
        out.append(r)
        busy = r.get("exit10") or r["t0"]
    return out


def w12_revalidation(rows: list[dict], lo: int, hi: int, vol: dict, td_of, seed: int = 13) -> dict:
    h = [r for r in rows if r["H1"]]
    out = {}
    iv = sorted((r["t0"], r.get("exit10") or r["t0"]) for r in h)
    open_at = [sum(1 for a, b in iv if a <= t0 < b) for t0, _ in iv]
    days = {r["t0"] // 86400 for r in h}
    oat = one_at_a_time(h)
    out["independence"] = {"trades": len(h), "distinct_days": len(days), "overlapping_at_entry": sum(1 for x in open_at if x > 1),
                           "max_open_together": max(open_at) if open_at else 0, "one_at_a_time_trades": len(oat)}
    sl = [r for r in h if r["tp10"] == "SL" and r.get("min_to_stop") is not None]
    mts = np.array([r["min_to_stop"] for r in sl])
    out["entry_timing"] = {"stop_first": len(sl), "within_first_m5_bar": float((mts <= 5).mean()), "within_15_min": float((mts <= 15).mean()),
                           "within_1_h": float((mts <= 60).mean()), "median_min_to_stop": float(np.median(mts)),
                           "beyond_wick_under_1": float(np.mean([r["beyond_wick"] < 1.0 for r in sl])),
                           "stopped_then_reached_10": float(np.mean([bool(r["stopped_then_right"]) for r in sl])),
                           "beyond_wick_under_1_and_then_10": float(np.mean([r["beyond_wick"] < 1.0 and bool(r["stopped_then_right"]) for r in sl]))}
    D = np.array([r["D"] for r in h])
    tp = [r for r in h if r["tp10"] == "TP"]
    out["stop_width"] = {"median": float(np.median(D)), "quartiles": [float(np.percentile(D, 25)), float(np.percentile(D, 75))],
                         "winners_mae_over_stop_median": float(np.median([r["mae_to_exit"] / r["D"] for r in tp if r.get("mae_to_exit") is not None]))
                         if tp else None,
                         "winners_within_25pct_of_stop": float(np.mean([r["mae_to_exit"] >= 0.75 * r["D"] for r in tp if r.get("mae_to_exit") is not None]))
                         if tp else None}
    dec = [r for r in h if r["tp10"] in ("TP", "SL") and r["c3"] is not None]
    y = np.array([r["tp10"] == "TP" for r in dec], float)
    c3 = np.array([bool(r["c3"]) for r in dec])
    yr = np.array([datetime.fromtimestamp(r["t0"], timezone.utc).year for r in dec])
    obs = y[c3].mean() - y[~c3].mean()
    rng = np.random.default_rng(seed)
    perm = np.empty(10000)
    for b in range(10000):
        lab = c3.copy()
        for yy in np.unique(yr):
            m = yr == yy
            lab[m] = rng.permutation(lab[m])
        perm[b] = y[lab].mean() - y[~lab].mean()
    t = np.array([r["t0"] for r in dec])
    edges = np.linspace(lo, hi, FOLDS + 1)
    fold = []
    for f in range(FOLDS):
        m = (t >= edges[f]) & (t < edges[f + 1])
        fold.append(float(y[m & c3].mean() - y[m & ~c3].mean()) if (m & c3).any() and (m & ~c3).any() else None)
    nyo = np.array([r["boundary"] == "NY_OPEN" for r in dec])
    out["dollar_filter"] = {"n_with": int(c3.sum()), "n_without": int((~c3).sum()), "diff": float(obs),
                            "permutation_p": float((perm >= obs).mean()),
                            "folds": fold, "years": {str(int(yy)): float(y[(yr == yy) & c3].mean() - y[(yr == yy) & ~c3].mean())
                                                     for yy in np.unique(yr)},
                            "within_NY_OPEN": float(y[nyo & c3].mean() - y[nyo & ~c3].mean()) if (nyo & c3).any() and (nyo & ~c3).any() else None,
                            "folds_positive": sum(1 for f in fold if f is not None and f > 0)}
    return out


# ---------------- run ----------------
def evaluate(L: dict) -> dict:
    src, m15 = L["src"], L["m15"]
    lo, hi = int(L["score_from"]), int(H.DEV[1].timestamp())
    weeks = (hi - lo) / 604800.0
    vol = vol_regime(m15)
    cal = sessions.calendar(m15.index)
    td_by_bar = dict(zip(ta.epoch_s(m15.index).astype(np.int64).tolist(), cal["trading_date"].to_numpy()))

    def td_of(t):
        return td_by_bar.get(int(t - t % 900))
    out = {"weeks": weeks, "families": {}, "baselines": {}}
    ps = {}
    for fam, keys in FAMILIES.items():
        for key in keys:
            name = " ".join(x for x in key if x)
            mm = metrics(src.get(key, []), weeks, lo, hi, vol, td_of)
            out["families"].setdefault(fam, {})[name] = mm
            ps[name] = mm.get("p_one_sided")
    hp = holm(ps)
    best = None
    for fam, d in out["families"].items():
        for name, mm in d.items():
            mm["holm_p"] = hp.get(name)
            mm["supported"] = supported(mm, hp.get(name))
            if mm["supported"] and (best is None or mm["net_r_day95"][0] > best[1]):
                best = (name, mm["net_r_day95"][0])
    for key in BASELINES:
        name = " ".join(x for x in key if x) + (" (one at a time)" if key[0] == "W12x" else "")
        out["baselines"][name] = metrics(src.get(key, []), weeks, lo, hi, vol, td_of)
    allm = [(n, mm) for d in out["families"].values() for n, mm in d.items() if mm.get("trades")]
    out["strongest_by_lower_bound"] = sorted(((n, mm["net_r_day95"][0], mm["net_r"], mm["trades"]) for n, mm in allm
                                              if mm["trades"] >= MIN_DECIDED), key=lambda x: -x[1])[:10]
    out["verdict"] = f"SUPPORTED: {best[0]}" if best else "NO SUPPORTED MECHANISM"
    out["w12_revalidation"] = w12_revalidation(L["w12_rows"], lo, hi, vol, td_of)
    w12 = out["baselines"]
    out["w12_revalidation"]["regimes"] = {k: {"years": w12[k].get("years"), "vol": w12[k].get("vol")} for k in ("W12 H1",)}
    out["w12_revalidation"]["expectancy"] = {k: {x: w12[k].get(x) for x in ("net_r", "net_r_day95", "usd_per_trade", "usd_per_week",
                                                                               "net_r_x15", "profit_factor", "max_drawdown_usd")}
                                             for k in ("W12 H1", "W12x H1 (one at a time)")}
    out["reproduction"] = {"w3_counts": L["w3_counts"], "w7_counts": L["w7_counts"]}
    return out


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 6)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rd", required=True)
    ap.add_argument("--w4", required=True)
    ap.add_argument("--w5", required=True)
    ap.add_argument("--cost", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    L = load_all(a.rd, a.w4, a.w5, a.cost)
    out = evaluate(L)
    with open(__file__, "rb") as f:
        out.update(registration=REG, part="development", code_sha256=hashlib.sha256(f.read()).hexdigest(),
                   data_hash=H.data_hash(L["m15"]), created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with open(a.out, "w") as f:
        json.dump(_clean(out), f, indent=1)
    print(json.dumps({"verdict": out["verdict"], "strongest": out["strongest_by_lower_bound"][:3]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
