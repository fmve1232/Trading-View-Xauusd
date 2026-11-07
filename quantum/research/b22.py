"""Phase B22 (research/registrations/B22.json, approved 2026-11-07; written after the registration was committed).

Every confirmation family the system has, as decision-time features of every 15m close taken as a BUY and as a SELL,
in seven model families (logistic, Gaussian naive Bayes, random forest, histogram gradient boosting, XGBoost, LightGBM
and their ensemble), each raw and with isotonic and Platt calibration, scored out of sample by a quarterly purged
walk-forward on the development data. Labels: +$15 / +$20 before -$13 (quantum.research.b13.race). The HMM regime uses
only the forward filter (no smoothing) with parameters fitted on each training window. Research code: never imported
by production; xgboost / lightgbm / hmmlearn are research-only installs.
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config, engine, sessions, ta
from ..data import sources
from ..features import compute as compute_features
from . import b10, b13, b19, b20
from . import harness as H

REG = "B22"
T_ALL = (15.0, 20.0)
S = 13.0
NBARS = 96
REGIMES = ("ABNORMAL", "COMPRESS", "EXPANSION", "RANGE", "STRONG TR", "WEAK TR")
TOPS = (0.10, 0.05, 0.01, 0.005, 0.001)
MODELS = ("LR", "NB", "RF", "HGB", "XGB", "LGBM")
CALS = ("raw", "isotonic", "platt")


# ---------------- causal helpers ----------------
def asof(src_close_t: np.ndarray, values: np.ndarray, at_t: np.ndarray) -> np.ndarray:
    """values of the last source bar CLOSED at or before each time in at_t (NaN before the first)."""
    j = np.searchsorted(src_close_t, at_t, side="right") - 1
    out = np.where(j >= 0, np.asarray(values, float)[np.maximum(j, 0)], np.nan)
    return out


def htf_trend(df: pd.DataFrame, sec: int, fast: int, slow: int, at_t: np.ndarray) -> np.ndarray:
    c = df["close"].to_numpy(float)
    sign = np.sign(ta.ema(c, fast) - ta.ema(c, slow))
    return asof(ta.epoch_s(df.index).astype(np.int64) + sec, sign, at_t)


def hmm_filter(model, X: np.ndarray) -> np.ndarray:
    """Forward-filtered state probabilities P(state_t | x_1..x_t): no smoothing, so no look-ahead."""
    logb = model._compute_log_likelihood(X)
    A = model.transmat_
    out = np.zeros((len(X), model.n_components))
    alpha = model.startprob_ * np.exp(logb[0] - logb[0].max())
    alpha /= alpha.sum()
    out[0] = alpha
    for t in range(1, len(X)):
        a = (alpha @ A) * np.exp(logb[t] - logb[t].max())
        s = a.sum()
        alpha = a / s if s > 0 else np.full(model.n_components, 1.0 / model.n_components)
        out[t] = alpha
    return out


def cusum(r: np.ndarray, win: int = 24, sig_win: int = 100) -> np.ndarray:
    """Signed sum of sigma-scaled returns over the last `win` closed bars / sqrt(win) (sigma from the previous sig_win)."""
    sd = pd.Series(r).shift(1).rolling(sig_win, min_periods=30).std().to_numpy()
    z = r / sd
    return pd.Series(z).rolling(win, min_periods=win).sum().to_numpy() / math.sqrt(win)


def drift_for(p: float, a: float, b: float) -> float:
    """kappa = 2 mu / sigma^2 such that a drifting Brownian motion hits +a before -b with probability p:
    p = (1 - exp(-kappa b)) / (1 - exp(-kappa (a + b))). Bisection; kappa 0 gives b / (a + b)."""
    def f(k):
        return (1 - math.exp(-k * b)) / (1 - math.exp(-k * (a + b))) - p if k > 1e-12 else b / (a + b) - p
    lo, hi = 1e-9, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ---------------- the feature table ----------------
def base_features(m15: pd.DataFrame, h1: pd.DataFrame, log=print) -> tuple[pd.DataFrame, dict]:
    """Direction-free and signed features per 15m close, all from data closed at or before it."""
    cfg = config.DEFAULT
    m = b10.make_market(m15, h1, "15m", 900)
    F = compute_features(m, cfg)
    res = engine.run(m, cfg, "treatment", F)
    R = res.rows
    log(f"[B22] engine on {len(m15)} 15m bars")
    o, h, lo_, c = (m15[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    t_close = ta.epoch_s(m15.index).astype(np.int64) + 900
    atr = ta.atr(h, lo_, c, 14)
    sh = lambda x, k: np.concatenate([np.full(k, np.nan), x[:-k]])
    e20, e100, e200 = ta.ema(c, 20), ta.ema(c, 100), ta.ema(c, 200)
    basis, sd = ta.sma(c, 20), ta.stdev(c, 20)
    macd = ta.ema(c, 12) - ta.ema(c, 26)
    hist = macd - ta.ema(macd, 9)
    B = b20.features(m15, h1)
    up, dn = b19.struct_arrays(res, n)

    def since(flag):
        out, last = np.full(n, 96.0), -10 ** 9
        for i in range(n):
            if flag[i]:
                last = i
            out[i] = min(96, i - last) if last > -10 ** 8 else 96
        return out

    sweep = np.zeros(n)
    sig = np.zeros(n)
    for e in res.events:
        if e.get("dir") in (1, -1) and 0 <= e["i"] < n:
            if e["type"] == "SWEEP":
                sweep[e["i"]] = e["dir"]
            elif e["type"] == "SIGNAL":
                sig[e["i"]] = e["dir"]
    grab, brk = np.zeros(n), np.zeros(n)
    for kind, arr_ in (("GRAB", grab), ("BREAK", brk)):
        ii, dd = b10.liquidity_events(res, F, kind, None)
        arr_[ii] = dd
    day = b13.tday(m15.index)
    hi_so_far = pd.Series(h, index=m15.index).groupby(day.values).cummax().to_numpy()
    lo_so_far = pd.Series(lo_, index=m15.index).groupby(day.values).cummin().to_numpy()
    cal = sessions.calendar(m15.index)
    hour = m15.index.hour.to_numpy() + m15.index.minute.to_numpy() / 60
    reg = np.asarray(R["regime_label"], object)
    nd = {   # direction-free
        "atr_pct": atr / c, "atr_rank": ta.percentrank(atr, 2880), "range_atr": (h - lo_) / atr, "body_atr": np.abs(c - o) / atr,
        "bb_width": 4 * sd / atr, "rsi_abs": np.abs(ta.rsi(c, 14) - 50), "run_length": np.minimum(B["run_length"].to_numpy(float), 10),
        "tq": np.asarray(R["tq"], float), "sess_q": np.asarray(F["session_quality"], float),
        "hour_sin": np.sin(2 * np.pi * hour / 24), "hour_cos": np.cos(2 * np.pi * hour / 24), "weekday": m15.index.weekday.to_numpy(float),
        "london": cal["in_london"].to_numpy(float), "ny": cal["in_ny"].to_numpy(float),
        "day_pos": (c - lo_so_far) / np.where(hi_so_far > lo_so_far, hi_so_far - lo_so_far, np.nan),
        "fvg": np.nan_to_num(np.asarray(R["fvg_bull"], float), nan=0.0),
    }
    for r_ in REGIMES:
        nd[f"reg_{r_}"] = (reg == r_).astype(float)
    sg = {   # signed: multiplied by the row's direction
        "d_e20": (c - e20) / atr, "d_e100": (c - e100) / atr, "d_e200": (c - e200) / atr,
        "slope20": (e20 - sh(e20, 4)) / atr, "slope100": (e100 - sh(e100, 4)) / atr,
        "trend_1h": htf_trend(h1, 3600, 20, 100, t_close),
        "trend_4h": htf_trend(sources.resample_ny_session(h1, 4), 14400, 20, 100, t_close),
        "trend_1d": htf_trend(sources.daily_ny_session(h1), 86400, 20, 50, t_close),
        "d_vwap": (c - np.asarray(F["vwap"], float)) / atr, "pct_b": (c - (basis - 2 * sd)) / (4 * sd) - 0.5,
        "rsi": ta.rsi(c, 14) - 50, "macd_hist": hist / atr,
        "ret1": (c - sh(c, 1)) / atr, "ret4": (c - sh(c, 4)) / atr, "ret16": (c - sh(c, 16)) / atr,
        "wick_skew": ((np.minimum(o, c) - lo_) - (h - np.maximum(o, c))) / atr,
        "run_size": np.clip(B["run_size"].to_numpy(float) * B["d"].to_numpy(float), -60, 60) / 10,
        "since_up_minus_dn": (since(dn) - since(up)) / 96, "sweep": sweep, "grab": grab, "break": brk, "signal": sig,
        "bull_minus_bear": (np.asarray(R["bull"], float) - np.asarray(R["bear"], float)) / 100,
        "d_pdh": (c - np.asarray(R["pdh"], float)) / atr, "d_pdl": (c - np.asarray(R["pdl"], float)) / atr,
        "d_pwh": (c - np.asarray(R["pwh"], float)) / atr, "d_pwl": (c - np.asarray(R["pwl"], float)) / atr,
        "day_pos_c": (c - lo_so_far) / np.where(hi_so_far > lo_so_far, hi_so_far - lo_so_far, np.nan) - 0.5,
    }
    df = pd.DataFrame({**{f"nd_{k}": v for k, v in nd.items()}, **{f"sg_{k}": v for k, v in sg.items()}}, index=m15.index)
    df["t_close"] = t_close
    df["close"] = c
    df["day"] = day.values
    df["regime"] = reg
    df["session"] = B["session"].to_numpy()
    return df, {"h1": h1, "cost": H.cost_pts(m15.index)}


def hmm_features(h1: pd.DataFrame, train_end_t: int, t_close: np.ndarray, seed: int = 7) -> np.ndarray:
    """3-state Gaussian HMM on 1h [log return, |log return|], fitted on 1h bars closed before train_end_t; forward-
    filtered probabilities on the last 1h bar closed by each 15m close."""
    from hmmlearn.hmm import GaussianHMM

    c1 = h1["close"].to_numpy(float)
    r = np.diff(np.log(c1), prepend=np.nan) * 100
    X = np.column_stack([np.nan_to_num(r), np.abs(np.nan_to_num(r))])
    ct = ta.epoch_s(h1.index).astype(np.int64) + 3600
    tr = ct < train_end_t
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mdl = GaussianHMM(n_components=3, covariance_type="diag", n_iter=50, random_state=seed).fit(X[tr][1:])
    probs = hmm_filter(mdl, X)
    order = np.argsort(mdl.means_[:, 1])                    # states sorted by |return| (calm -> wild), stable labels
    probs = probs[:, order]
    cus = cusum(np.nan_to_num(r))
    return np.column_stack([asof(ct, probs[:, k], t_close) for k in range(3)] + [asof(ct, cus, t_close)])


def rows_for(df: pd.DataFrame, hmm: np.ndarray, sel: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Two rows per selected bar (BUY, SELL): direction-free features, signed features x direction, HMM probabilities,
    CUSUM x direction, and the direction."""
    ndc = [c for c in df.columns if c.startswith("nd_")]
    sgc = [c for c in df.columns if c.startswith("sg_")]
    A = df[ndc].to_numpy(float)[sel]
    Sg = df[sgc].to_numpy(float)[sel]
    Hm = hmm[sel]
    Xs, Ds = [], []
    for D in (1, -1):
        Xs.append(np.column_stack([A, Sg * D, Hm[:, :3], Hm[:, 3:4] * D, np.full(len(A), D)]))
        Ds.append(np.full(len(A), D))
    names = ndc + sgc + ["hmm_calm", "hmm_mid", "hmm_wild", "cusum_signed", "direction"]
    return np.vstack(Xs), np.concatenate(Ds), names


# ---------------- models ----------------
def make(name: str):
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import GaussianNB
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if name == "LR":
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    if name == "NB":
        return make_pipeline(StandardScaler(), GaussianNB())
    if name == "RF":
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=200, max_features="sqrt", n_jobs=-1, random_state=7)
    if name == "HGB":
        return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200, random_state=7)
    if name == "XGB":
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                             n_jobs=4, random_state=7, verbosity=0)
    if name == "LGBM":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=400, num_leaves=31, learning_rate=0.05, min_child_samples=200, subsample=0.8,
                              subsample_freq=1, colsample_bytree=0.8, n_jobs=4, random_state=7, verbose=-1)
    raise ValueError(name)


def calibrate(p_cal: np.ndarray, y_cal: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p_cal, y_cal)
    lg = lambda x: np.log(np.clip(x, 1e-6, 1 - 1e-6) / (1 - np.clip(x, 1e-6, 1 - 1e-6)))
    pl = LogisticRegression(C=1e6, max_iter=1000).fit(lg(p_cal)[:, None], y_cal)
    return {"raw": p, "isotonic": iso.predict(p), "platt": pl.predict_proba(lg(p)[:, None])[:, 1],
            "thr_cal": p_cal}


# ---------------- evaluation ----------------
def clustered_ci(y: np.ndarray, day: np.ndarray) -> tuple[float, float, float]:
    n = len(y)
    if n < 2:
        return math.nan, math.nan, math.nan
    m = float(y.mean())
    g = pd.Series(y - m).groupby(day).sum().to_numpy(float)
    se = math.sqrt(float((g ** 2).sum())) / n
    return m, m - 1.96 * se, m + 1.96 * se


def evaluate(p: np.ndarray, y: np.ndarray, d: np.ndarray, day: np.ndarray, cost: np.ndarray, quarter: np.ndarray, T: float,
             thr_causal: dict | None = None) -> dict:
    from sklearn.metrics import log_loss, roc_auc_score

    pc = np.clip(p, 1e-6, 1 - 1e-6)
    base = float(y.mean())
    out = {"n": len(y), "base_rate": base, "auc": float(roc_auc_score(y, p)), "log_loss": float(log_loss(y, pc)),
           "log_loss_base": float(log_loss(y, np.full(len(y), base))), "brier": float(np.mean((p - y) ** 2)),
           "brier_base": float(np.mean((base - y) ** 2))}
    q = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False)
    out["reliability"] = [{"decile": int(k) + 1, "predicted": float(p[q == k].mean()), "observed": float(y[q == k].mean()),
                           "n": int((q == k).sum())} for k in range(10)]
    net = np.where(y == 1, T, -S) - cost
    out["top"] = {}
    for f in TOPS:
        sel = np.zeros(len(p), bool)
        for qq in np.unique(quarter):                         # the registered version: the top fraction within each quarter
            m = quarter == qq
            if m.sum():
                sel[m] = p[m] >= np.quantile(p[m], 1 - f)
        m_, lo, hi = clustered_ci(y[sel].astype(float), day[sel])
        rec = {"n": int(sel.sum()), "precision": m_, "ci95": [lo, hi], "net_usd_per_oz": float(net[sel].mean()) if sel.any() else None,
               "buy_precision": float(y[sel & (d > 0)].mean()) if (sel & (d > 0)).any() else None,
               "sell_precision": float(y[sel & (d < 0)].mean()) if (sel & (d < 0)).any() else None}
        if thr_causal is not None:                             # the causal version: thresholds from each training slice
            selc = p >= np.array([thr_causal[qq][f] for qq in quarter])
            m2, lo2, hi2 = clustered_ci(y[selc].astype(float), day[selc])
            rec["causal"] = {"n": int(selc.sum()), "precision": m2, "ci95": [lo2, hi2],
                             "net_usd_per_oz": float(net[selc].mean()) if selc.any() else None}
        out["top"][f"{f:g}"] = rec
    order = np.argsort(-p, kind="stable")
    cum = np.cumsum(y[order]) / np.arange(1, len(y) + 1)
    k = int(np.argmax(cum[29:])) + 30 if len(y) >= 30 else 0
    lo, hi = H.wilson(int(y[order][:k].sum()), k) if k else (math.nan, math.nan)
    out["best_any_threshold_n30"] = {"n": k, "precision": float(cum[k - 1]) if k else None, "wilson95": [lo, hi]}
    out["precision_at_n"] = {str(nn): float(cum[nn - 1]) for nn in (30, 100, 300, 1000) if len(y) >= nn}
    return out


def quarters(start: str, end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    qs, cur = [], pd.Timestamp(start, tz="UTC")
    while cur < end:
        nxt = cur + pd.DateOffset(months=3)
        qs.append((cur, min(nxt, end)))
        cur = nxt
    return qs


def run(rd: str, log=print) -> dict:
    m15, h1 = b13.load(rd, "development")
    df, aux = base_features(m15, h1, log)
    cost = aux["cost"]
    t_close = df["t_close"].to_numpy(np.int64)
    scored = np.flatnonzero(df.index >= b13.SCORE_FROM)
    labels = {}
    for T in T_ALL:
        rb = b13.race(m15, t_close[scored], df["close"].to_numpy(float)[scored], np.ones(len(scored), int), T, S, nbars=NBARS)
        rs = b13.race(m15, t_close[scored], df["close"].to_numpy(float)[scored], -np.ones(len(scored), int), T, S, nbars=NBARS)
        labels[T] = (rb, rs)
    qs = quarters("2021-01-01", m15.index[-1] + pd.Timedelta(minutes=15))
    out = {"registration": REG, "window": [str(m15.index[0]), str(m15.index[-1])], "folds": [[str(a), str(b)] for a, b in qs],
           "features": None, "results": {}, "engine_baseline": {}, "drift": {}}
    for T in T_ALL:
        rb, rs = labels[T]
        y_all = np.concatenate([rb["win"], rs["win"]]).astype(int)
        dec_all = np.concatenate([rb["win"] | rb["loss"], rs["win"] | rs["loss"]])
        preds = {(mn, cn): [] for mn in MODELS + ("ENS",) for cn in CALS}
        thr = {(mn, cn): {} for mn in MODELS + ("ENS",) for cn in CALS}
        Y, Dd, DAY, COST, QQ, SIG = [], [], [], [], [], []
        for qi, (qa, qb) in enumerate(qs):
            te_bars = scored[(df.index[scored] >= qa) & (df.index[scored] < qb)]
            first_te = int(te_bars[0])
            tr_bars = scored[scored + NBARS < first_te]                 # purge: training labels end before the test quarter
            hm = hmm_features(h1, int(df["t_close"].iloc[first_te]) - 900, t_close)
            Xtr, _, names = rows_for(df, hm, tr_bars)
            Xte, _, _ = rows_for(df, hm, te_bars)
            out["features"] = names
            pos_tr = np.concatenate([np.searchsorted(scored, tr_bars), len(scored) + np.searchsorted(scored, tr_bars)])
            pos_te = np.concatenate([np.searchsorted(scored, te_bars), len(scored) + np.searchsorted(scored, te_bars)])
            ktr, kte = dec_all[pos_tr], dec_all[pos_te]
            Xtr, ytr = np.nan_to_num(Xtr[ktr], nan=0.0, posinf=0.0, neginf=0.0), y_all[pos_tr][ktr]
            Xte, yte = np.nan_to_num(Xte[kte], nan=0.0, posinf=0.0, neginf=0.0), y_all[pos_te][kte]
            n_fit = int(len(ytr) * 0.8)
            # rows are [BUY block, SELL block]; split each block 80 / 20 in time
            half = int(ktr[: len(tr_bars)].sum())
            idx_b, idx_s = np.arange(half), np.arange(half, len(ytr))
            fit_i = np.concatenate([idx_b[: int(len(idx_b) * 0.8)], idx_s[: int(len(idx_s) * 0.8)]])
            cal_i = np.concatenate([idx_b[int(len(idx_b) * 0.8):], idx_s[int(len(idx_s) * 0.8):]])
            del n_fit
            ens_te, ens_cal = [], []
            for mn in MODELS:
                mdl = make(mn).fit(Xtr[fit_i], ytr[fit_i])
                p_cal, p_te = mdl.predict_proba(Xtr[cal_i])[:, 1], mdl.predict_proba(Xte)[:, 1]
                if mn != "NB":
                    ens_te.append(p_te)
                    ens_cal.append(p_cal)
                cl = calibrate(p_cal, ytr[cal_i], p_te)
                clc = calibrate(p_cal, ytr[cal_i], p_cal)
                for cn in CALS:
                    preds[(mn, cn)].append(cl[cn])
                    thr[(mn, cn)][qi] = {f: float(np.quantile(clc[cn], 1 - f)) for f in TOPS}
                log(f"[B22] T{T:g} {qa.date()} {mn}: train {len(ytr)} test {len(yte)}")
            pe, pc = np.mean(ens_te, axis=0), np.mean(ens_cal, axis=0)
            cl, clc = calibrate(pc, ytr[cal_i], pe), calibrate(pc, ytr[cal_i], pc)
            for cn in CALS:
                preds[("ENS", cn)].append(cl[cn])
                thr[("ENS", cn)][qi] = {f: float(np.quantile(clc[cn], 1 - f)) for f in TOPS}
            n_b = int(kte[: len(te_bars)].sum())
            Y.append(yte)
            Dd.append(np.concatenate([np.ones(n_b), -np.ones(len(yte) - n_b)]))
            dd_days = df["day"].to_numpy()[te_bars]
            DAY.append(np.concatenate([dd_days[kte[: len(te_bars)]], dd_days[kte[len(te_bars):]]]))
            cc = cost[te_bars]
            COST.append(np.concatenate([cc[kte[: len(te_bars)]], cc[kte[len(te_bars):]]]))
            QQ.append(np.full(len(yte), qi))
            sg = df["sg_signal"].to_numpy()[te_bars]
            SIG.append(np.concatenate([(sg == 1)[kte[: len(te_bars)]], (sg == -1)[kte[len(te_bars):]]]))
        Y, Dd, DAY, COST, QQ, SIG = (np.concatenate(a) for a in (Y, Dd, DAY, COST, QQ, SIG))
        res_T = {}
        for (mn, cn), plist in preds.items():
            p = np.concatenate(plist)
            res_T[f"{mn} {cn}"] = evaluate(p, Y, Dd, DAY, COST, QQ, T, thr[(mn, cn)])
        out["results"][f"T{T:g}"] = res_T
        m_, lo, hi = clustered_ci(Y[SIG].astype(float), DAY[SIG])
        out["engine_baseline"][f"T{T:g}"] = {"n": int(SIG.sum()), "precision": m_, "ci95": [lo, hi], "base_rate": float(Y.mean())}
    # selection by the lowest walk-forward log loss at T = 15
    best = min(out["results"]["T15"].items(), key=lambda kv: kv[1]["log_loss"])[0]
    out["selected"] = best
    top5 = out["results"]["T15"][best]["top"]["0.05"]
    be = float(np.mean((S + cost[scored]) / (S + 15.0)))
    base = out["results"]["T15"][best]["base_rate"]
    lo_reg, lo_c = top5["ci95"][0], top5.get("causal", {}).get("ci95", [math.nan])[0]
    out["development_pass"] = {"break_even": be, "base_rate": base, "top5_lower95": lo_reg, "top5_causal_lower95": lo_c,
                               "pass": bool(lo_reg > max(be, base) and lo_c > max(be, base))}
    # the 90% question: the drift a Brownian motion needs to hit +15 before -13 with p = 0.9
    dc = np.diff(m15["close"].to_numpy(float)[scored]) * (4000.0 / m15["close"].to_numpy(float)[scored][1:])
    var_bar = float(np.var(dc[np.isfinite(dc)]))
    for p in (0.5, 0.6, 0.7, 0.8, 0.9):
        k = drift_for(p, 15.0, S)
        mu = k * var_bar / 2
        out["drift"][f"{p:g}"] = {"kappa": k, "drift_usd_per_15m": mu, "drift_usd_per_hour": 4 * mu, "drift_usd_per_day": 96 * mu}
    out["sigma_usd_per_15m"] = math.sqrt(var_bar)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    out = run(a.rd)
    out["utc"] = datetime.now(timezone.utc).isoformat()
    with open(a.out, "w") as f:
        json.dump(b13._clean(out), f, indent=1, allow_nan=False)
    if a.trials:
        for tk, res in out["results"].items():
            for k, v in res.items():
                H.log_trial(a.trials, {"phase": REG, "partition": "development", "id": f"B22 {tk} {k}", "auc": v["auc"],
                                       "log_loss": v["log_loss"], "log_loss_base": v["log_loss_base"],
                                       "top5_precision": v["top"]["0.05"]["precision"], "top5_net": v["top"]["0.05"]["net_usd_per_oz"],
                                       "best_any_threshold_n30": v["best_any_threshold_n30"]})
    print(json.dumps({"selected": out["selected"], "development_pass": out["development_pass"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
