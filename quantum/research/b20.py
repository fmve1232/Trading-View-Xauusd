"""Phase B20 (research/registrations/B20.json, approved 2026-11-07; written after the registration was committed).

Run continuation calibration. Every 15m close is an event traded in the direction d of its own close-to-close change
(continuation, never reversed); the outcome is +T before -13 (T = 15, 20; $ at $4,000 scaled by price / 4000) on the
next 96 15m bars. Fixed features at the close (run length, run size, last candle body / ATR, session, the 1h trend on
the last CLOSED 1h bar, the move since the New York day's open) give one-way calibration tables against the matched
random base, a declared combined rule, and a purged logistic model with a reliability table. Significance is clustered
by New York trading day because neighbouring closes share their future path. Research code: never imported by
production.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import sessions, ta
from . import b13
from . import harness as H

REG = "B20"
T_ALL = (15.0, 20.0)
S = 13.0
NBARS = 96
BINS = {
    "run_length": ([1, 2, 3, 4, 5, 6], ["1", "2", "3", "4", "5", "6+"]),
    "run_size": ([-np.inf, 5, 10, 15, 20, 30], ["<5", "5-10", "10-15", "15-20", "20-30", ">=30"]),
    "last_candle_body": ([-np.inf, 0.5, 1.0, 1.5, 2.5], ["<0.5", "0.5-1.0", "1.0-1.5", "1.5-2.5", ">=2.5"]),
    "day_move": ([-np.inf, 0, 10, 20, 40], ["<0", "0-10", "10-20", "20-40", ">=40"]),
}
SESSIONS = ("London only", "London + New York", "New York only", "Asia / off")


def features(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    """One row per 15m close; every value uses bars closed at or before it."""
    o, h, lo_, c = (m15[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    s = c / 4000.0
    dc = np.diff(c, prepend=np.nan)
    d = np.sign(dc)
    d[~np.isfinite(d)] = 0
    k = np.zeros(n, int)
    start = np.arange(n)
    for i in range(n):                                     # consecutive closes in d ending at i
        if d[i] == 0:
            continue
        if i > 0 and d[i - 1] == d[i]:
            k[i], start[i] = k[i - 1] + 1, start[i - 1]
        else:
            k[i], start[i] = 1, i
    base_close = np.where(start > 0, c[np.maximum(start - 1, 0)], np.nan)   # the close before the run's first candle
    run_size = (c - base_close) * d / s
    atr = ta.atr(h, lo_, c, 14)
    body = np.abs(c - o) / atr
    cal = sessions.calendar(m15.index)
    lon, ny = cal["in_london"].to_numpy(bool), cal["in_ny"].to_numpy(bool)
    sess = np.where(lon & ny, SESSIONS[1], np.where(lon, SESSIONS[0], np.where(ny, SESSIONS[2], SESSIONS[3])))
    # the 1h trend on the last 1h bar closed by this 15m close
    hc = h1["close"].to_numpy(float)
    e20, e100 = ta.ema(hc, 20), ta.ema(hc, 100)
    h_close_t = ta.epoch_s(h1.index).astype(np.int64) + 3600
    t_close = ta.epoch_s(m15.index).astype(np.int64) + 900
    j = np.searchsorted(h_close_t, t_close, side="right") - 1
    ok = j >= 0
    up = np.where(ok, e20[np.maximum(j, 0)] > e100[np.maximum(j, 0)], False)
    trend_ok = ok & np.isfinite(np.where(ok, e100[np.maximum(j, 0)], np.nan))
    trend_agree = trend_ok & (np.where(up, 1, -1) == d)
    # the New York trading day's first open
    day = b13.tday(m15.index)
    first_open = pd.Series(o, index=m15.index).groupby(day.values).transform("first").to_numpy(float)
    day_move = (c - first_open) * d / s
    return pd.DataFrame({"t_close": t_close, "close": c, "d": d.astype(int), "run_length": k, "run_size": run_size,
                         "last_candle_body": body, "session": sess, "trend_1h_agrees": trend_agree, "trend_known": trend_ok,
                         "day_move": day_move, "atr_pct": atr / c, "day": day.values}, index=m15.index)


def bin_of(x: np.ndarray, name: str) -> np.ndarray:
    edges, labels = BINS[name]
    if name == "run_length":
        return np.array([labels[min(int(v), 6) - 1] if v >= 1 else "" for v in x], object)
    idx = np.searchsorted(np.asarray(edges[1:], float), x, side="right")
    return np.array([labels[i] if np.isfinite(v) else "" for i, v in zip(idx, x)], object)


def clustered(w: np.ndarray, base: np.ndarray, day: np.ndarray) -> tuple[float, float, float]:
    """Mean of (w - base), its day-clustered standard error (CR0) and the one-sided p of mean > 0."""
    x = w.astype(float) - base
    n = len(x)
    if n < 3:
        return math.nan, math.nan, math.nan
    m = float(x.mean())
    g = pd.Series(x - m).groupby(day).sum().to_numpy(float)
    se = math.sqrt(float((g ** 2).sum())) / n
    return m, se, (1 - H._norm_cdf(m / se)) if se > 0 else math.nan


def outcomes(m15: pd.DataFrame, F: pd.DataFrame, T: float) -> dict:
    r = b13.race(m15, F["t_close"].to_numpy(np.int64), F["close"].to_numpy(float), F["d"].to_numpy(int), T, S, nbars=NBARS)
    return r


def table(F: pd.DataFrame, r: dict, base_l: float, base_s: float, cost: np.ndarray, T: float, mask: np.ndarray) -> dict:
    dec = (r["win"] | r["loss"]) & mask
    n = int(dec.sum())
    if n == 0:
        return {"n": 0}
    w = r["win"][dec]
    d = F["d"].to_numpy(int)[dec]
    base = np.where(d > 0, base_l, base_s)
    m, se, p = clustered(w, base, F["day"].to_numpy()[dec])
    rate = float(w.mean())
    net = np.where(w, T, -S) - cost[dec]
    be = float(np.mean((S + cost[dec]) / (S + T)))
    return {"n": n, "rate": rate, "base": float(base.mean()), "diff": m, "se_clustered": se, "z": m / se if se and se > 0 else math.nan,
            "p_one_sided": p, "rate_lo_clustered": rate - 1.645 * se if math.isfinite(se) else math.nan,
            "break_even": be, "mean_net_usd_per_oz": float(net.mean()), "days": len(np.unique(F["day"].to_numpy()[dec])),
            "buy_share": float(np.mean(d > 0))}


def holm_adjusted(ps: dict) -> dict:
    items = sorted(ps.items(), key=lambda kv: (kv[1] if math.isfinite(kv[1]) else 1.0))
    m, run_max, out = len(items), 0.0, {}
    for i, (k, p) in enumerate(items):
        pp = p if math.isfinite(p) else 1.0
        run_max = max(run_max, min(1.0, (m - i) * pp))
        out[k] = run_max
    return out


def model(F: pd.DataFrame, r: dict, base_l: float, base_s: float, cost: np.ndarray, T: float, rows: np.ndarray) -> dict:
    """Purged time-ordered 5-fold logistic regression; reliability by decile; the top decile's success and net."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    dec = (r["win"] | r["loss"]) & rows & F["trend_known"].to_numpy(bool)
    ii = np.flatnonzero(dec)
    X = np.column_stack([np.minimum(F["run_length"].to_numpy(float), 10)[ii], np.clip(F["run_size"].to_numpy(float), -60, 60)[ii],
                         np.clip(F["last_candle_body"].to_numpy(float), 0, 5)[ii], F["trend_1h_agrees"].to_numpy(float)[ii],
                         np.clip(F["day_move"].to_numpy(float), -100, 100)[ii], F["atr_pct"].to_numpy(float)[ii] * 1000,
                         F["d"].to_numpy(float)[ii]]
                        + [(F["session"].to_numpy() == s_)[ii].astype(float) for s_ in SESSIONS[:3]])
    y = r["win"][ii].astype(int)
    X = np.nan_to_num(X)
    pred = np.full(len(ii), np.nan)
    for tr, te in H.purged_folds(len(ii), 5, NBARS, NBARS):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-12
        clf = LogisticRegression(C=1.0, max_iter=1000).fit((X[tr] - mu) / sd, y[tr])
        pred[te] = clf.predict_proba((X[te] - mu) / sd)[:, 1]
    auc = float(roc_auc_score(y, pred))
    q = pd.qcut(pred, 10, labels=False, duplicates="drop")
    rel = [{"decile": int(g) + 1, "predicted": float(pred[q == g].mean()), "observed": float(y[q == g].mean()), "n": int((q == g).sum())}
           for g in sorted(set(q.tolist()))]
    top = np.zeros(len(F), bool)
    top[ii[q == q.max()]] = True
    return {"n": len(ii), "auc": auc, "brier": float(np.mean((pred - y) ** 2)),
            "brier_base_rate": float(np.mean((y.mean() - y) ** 2)), "reliability": rel,
            "top_decile": table(F, r, base_l, base_s, cost, T, top)}


def run(rd: str, part: str = "development", rules: list[str] | None = None, log=print) -> dict:
    m15, h1 = b13.load(rd, part) if part == "development" else (H.partition(b13.history.load(rd, "XAU/USD", "15min"), part, REG),
                                                                  H.partition(b13.history.load(rd, "XAU/USD", "1h"), part, REG))
    score_from = b13.SCORE_FROM if part == "development" else m15.index[0] + pd.Timedelta(days=67)
    F = features(m15, h1)
    rows = (F.index >= score_from) & (F["d"].to_numpy() != 0)
    cost = H.cost_pts(m15.index)
    srows = np.flatnonzero(F.index >= score_from)
    out = {"registration": REG, "part": part, "window": [str(m15.index[0]), str(m15.index[-1])], "scored_from": str(score_from),
           "events": int(rows.sum()), "targets": {}}
    for T in T_ALL:
        rnd = b13.random_rates(m15, m15.index, m15["close"].to_numpy(float), srows, T, S)
        r = outcomes(m15, F, T)
        res = {"base_long": rnd["long"], "base_short": rnd["short"], "geometry": S / (S + T), "tables": {}}
        res["all_events"] = table(F, r, rnd["long"], rnd["short"], cost, T, rows)
        for name in BINS:
            lab = bin_of(F[name].to_numpy(float), name)
            res["tables"][name] = {b: table(F, r, rnd["long"], rnd["short"], cost, T, rows & (lab == b)) for b in BINS[name][1]}
        res["tables"]["session"] = {s_: table(F, r, rnd["long"], rnd["short"], cost, T, rows & (F["session"].to_numpy() == s_))
                                    for s_ in SESSIONS}
        tk, ta_ = F["trend_known"].to_numpy(bool), F["trend_1h_agrees"].to_numpy(bool)
        res["tables"]["trend_1h"] = {"agrees": table(F, r, rnd["long"], rnd["short"], cost, T, rows & tk & ta_),
                                     "disagrees": table(F, r, rnd["long"], rnd["short"], cost, T, rows & tk & ~ta_)}
        confirmed_run = rows & (F["run_length"].to_numpy() >= 3) & (F["run_size"].to_numpy(float) >= 15) & tk & ta_
        res["combined_rule"] = table(F, r, rnd["long"], rnd["short"], cost, T, confirmed_run)
        if part == "development":
            res["model"] = model(F, r, rnd["long"], rnd["short"], cost, T, rows)
        out["targets"][f"T{T:g}"] = res
        log(f"[B20] T{T:g}: all {res['all_events']['rate']:.3f} vs base {res['all_events']['base']:.3f}; "
            f"confirmed run {res['combined_rule'].get('rate')} n {res['combined_rule'].get('n')}")
    # the primary family: every one-way bin and the combined rule, both targets
    ps = {}
    for tk_, res in out["targets"].items():
        for name, tb in res["tables"].items():
            for b, v in tb.items():
                ps[f"{tk_} {name} {b}"] = v.get("p_one_sided", math.nan) if v.get("n", 0) else math.nan
        ps[f"{tk_} combined_rule"] = res["combined_rule"].get("p_one_sided", math.nan)
    hol = holm_adjusted(ps)
    out["holm"] = hol
    cands = []
    for key, hp in hol.items():
        tk_, rest = key.split(" ", 1)
        res = out["targets"][tk_]
        v = res["combined_rule"] if rest == "combined_rule" else res["tables"][rest.split(" ", 1)[0]][rest.split(" ", 1)[1]]
        if v.get("n", 0) >= 300 and v["rate"] - v["base"] >= 0.02 and hp <= 0.05 and v["mean_net_usd_per_oz"] > 0:
            cands.append((v["z"], key))
    for tk_, res in out["targets"].items():
        top = (res.get("model") or {}).get("top_decile") or {}
        if top.get("n", 0) >= 300 and top["rate"] - top["base"] >= 0.02 and (top.get("p_one_sided") or 1) <= 0.05 / max(len(ps), 1) \
                and top["mean_net_usd_per_oz"] > 0:
            cands.append((top["z"], f"{tk_} model top decile"))
    out["candidates"] = [k for _, k in sorted(cands, reverse=True)[:3]]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--part", default="development", choices=("development", "validation"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    out = run(a.rd, a.part)
    out["utc"] = datetime.now(timezone.utc).isoformat()
    with open(a.out, "w") as f:
        json.dump(b13._clean(out), f, indent=1, allow_nan=False)
    if a.trials:
        for tk_, res in out["targets"].items():
            for name, tb in res["tables"].items():
                for b, v in tb.items():
                    H.log_trial(a.trials, {"phase": REG, "partition": a.part, "id": f"B20 {tk_} {name} {b}",
                                           "holm_p": out["holm"].get(f"{tk_} {name} {b}"), **b13._clean(v)})
            H.log_trial(a.trials, {"phase": REG, "partition": a.part, "id": f"B20 {tk_} combined_rule (>=3 candles, >=$15, 1h trend agrees)",
                                   "holm_p": out["holm"].get(f"{tk_} combined_rule"), **b13._clean(res["combined_rule"])})
    print(json.dumps({"candidates": out["candidates"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
