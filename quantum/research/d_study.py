"""Phase D, Workstreams C-F: the controlled comparison of Baseline / A / B / C / D on the unchanged +-$15 benchmark
(research/registrations/PHASE_D.json). Research only: never imported by the engine, the arms or the site.

LABELS. B26's race, unchanged (quantum/research/b26.py via b27.labels): three classes TP / SL (AMBIGUOUS counts as SL,
worst case) / NEITHER (TIMEOUT or CLOSURE); OPEN rows are excluded. Costs: ENG (primary), as B26.
MODELS. The five registered feature sets x four algorithms (LR, RF, LGBM, GB = sklearn HistGradientBoosting; b22's
settings, unchanged), each a MULTINOMIAL classifier on one row per (decision bar, direction), direction-signed features
as B27. Calibration: one temperature per fit, from the training window's own last 20% (b27.split_fit_cal), never from a
test or sealed row. P(TP) + P(SL) + P(NEITHER) = 1 by construction.
WALK-FORWARD. Quarterly folds from 2021-01-01 (b22.quarters); a training row must have EXITED a day before its fold
starts; identical folds and rows for every set and algorithm.
DECISION RULES (registered, no tuned threshold). E[net] = P(TP) W + P(SL) L + P(NEITHER) N, with W / L / N the mean net
(USD / oz, ENG) of each class among the fit rows of the same direction. EV0: trade when E[net] > 0. Q10 / Q05 / Q02:
the top 10 / 5 / 2% of E[net], thresholds per direction from the training window's calibration rows. One position per
direction at a time (b27.seq_rows), so every trade counted is independent of the previous one.
INCREMENTAL VALUE. Per set vs Baseline, same algorithm and rows: the out-of-sample log-loss difference, averaged per New
York trading day, with a stationary block bootstrap (mean block 5 days) for its interval and one-sided p. A higher AUC
alone is never reported as value: net expectancy, PF, drawdown and trade frequency sit next to every score.
FAMILY. Every (set, algorithm, rule) strategy: BH at q = 0.10 on the one-sided p against matched random (direction x
session x month, b27.base_rates), and White's Reality Check on the daily net (R units) against no trade.
ACCEPTANCE C1-C6 (registration section "acceptance"); QUALIFIES only when all six hold.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

from . import b22, b26, b27
from . import d_features as DF
from . import harness as H

SETS = ("BASELINE", "A", "B", "C", "D")
ALGOS = ("LR", "RF", "LGBM", "GB")
CLASSES = ("TP", "SL", "NEITHER")
RULES = (("EV0", None), ("Q10", 0.10), ("Q05", 0.05), ("Q02", 0.02))
WF_START = "2021-01-01"
MIN_TRAIN = 5000
R_USD = b26.MOVE                    # 1R = the benchmark's stop distance, $15 (4000-equivalent in development)
C5_MIN, C5_PREFERRED = 300, 500
C6_DD_R, C6_TRADES, C6_P, C6_PATHS, C6_BLOCK = 15.0, 250, 0.05, 2000, 10
BH_Q, RC_P, HOLM_P = 0.10, 0.05, 0.05
MIN_STRATA = 30
SEED = 41


class NotAvailable(RuntimeError):
    """A registered input does not exist (e.g. no intermarket data): the set is reported NOT RUN, never substituted."""


# ---------------- labels and design ----------------
def y3(outcome: np.ndarray) -> np.ndarray:
    o = np.asarray(outcome)
    return np.where(o == "TP", 0, np.where(np.isin(o, ["SL", "AMBIGUOUS"]), 1, np.where(np.isin(o, ["TIMEOUT", "CLOSURE"]), 2, -1)))


def set_columns(F: pd.DataFrame, name: str, of_cols: list[str], im_cols: list[str]) -> list[str]:
    base = DF.select(F, DF.BASELINE_FAMILIES, b27.family)
    a = DF.select(F, DF.A_FAMILIES, b27.family)
    if name in ("B", "D") and not of_cols:
        raise NotAvailable("no order-flow columns")
    if name in ("C",) and not im_cols:
        raise NotAvailable("no intermarket data")
    cols = {"BASELINE": base, "A": a, "B": base + of_cols, "C": base + im_cols, "D": a + of_cols + im_cols}[name]
    return list(dict.fromkeys(cols))


def design(F: pd.DataFrame, L: pd.DataFrame, cols: list[str]) -> np.ndarray:
    i = L["dec_i"].to_numpy()
    d = L["d"].to_numpy(float)[:, None]
    nd = [c for c in cols if c.startswith("nd_")]
    sg = [c for c in cols if c.startswith("sg_")]
    parts = []
    if nd:
        parts.append(F[nd].to_numpy(float)[i])
    if sg:
        parts.append(F[sg].to_numpy(float)[i] * d)
    parts.append(d)
    return np.column_stack(parts)


def make(algo: str):
    return b22.make({"GB": "HGB"}.get(algo, algo))


def fit(algo: str, X: np.ndarray, y: np.ndarray):
    m = make(algo)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.fit(np.nan_to_num(X) if algo in ("LR", "RF") else X, y)
    return m


def proba(algo: str, m, X: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = m.predict_proba(np.nan_to_num(X) if algo in ("LR", "RF") else X)
    cls = list(getattr(m, "classes_", None) if not hasattr(m, "steps") else m.steps[-1][1].classes_)
    out = np.zeros((len(X), 3))
    for j, c in enumerate(cls):
        out[:, int(c)] = p[:, j]
    return out


def temperature(P: np.ndarray, y: np.ndarray) -> float:
    """The single temperature minimising the calibration rows' multinomial log-loss (bounded 0.05 .. 20)."""
    from scipy.optimize import minimize_scalar
    lp = np.log(np.clip(P, 1e-12, 1.0))

    def nll(T):
        z = lp / T
        z = z - z.max(axis=1, keepdims=True)
        q = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
        return -float(np.mean(np.log(np.clip(q[np.arange(len(y)), y], 1e-12, 1.0))))
    return float(minimize_scalar(nll, bounds=(0.05, 20.0), method="bounded").x) if len(y) else 1.0


def apply_temperature(P: np.ndarray, T: float) -> np.ndarray:
    z = np.log(np.clip(P, 1e-12, 1.0)) / T
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def class_means(y: np.ndarray, net: np.ndarray, d: np.ndarray) -> dict:
    """W / L / N: the mean net of TP / SL / NEITHER rows per direction (a missing class counts 0)."""
    out = {}
    for dd in (1, -1):
        m = d == dd
        out[dd] = np.array([float(net[m & (y == c)].mean()) if (m & (y == c)).any() else 0.0 for c in range(3)])
    return out


def expected_net(P: np.ndarray, d: np.ndarray, means: dict) -> np.ndarray:
    E = np.full(len(P), np.nan)
    for dd in (1, -1):
        m = d == dd
        E[m] = P[m] @ means[dd]
    return E


# ---------------- walk-forward ----------------
def walk_forward(F: pd.DataFrame, L: pd.DataFrame, cols: list[str], algo: str, start: str = WF_START, min_train: int = MIN_TRAIN,
                 months: int = 3, log=print, y: np.ndarray | None = None) -> dict:
    """y: the class of each row (0 / 1 / 2, -1 = excluded); default the benchmark's TP / SL / NEITHER."""
    t_fill, t_exit = L["fill_utc"].to_numpy(), L["exit_utc"].to_numpy()
    y = y3(L["outcome"].to_numpy()) if y is None else np.asarray(y)
    d = L["d"].to_numpy()
    net = L["net_usd_oz"].to_numpy(float)
    X = design(F, L, cols)
    n = len(L)
    out = {"P": np.full((n, 3), np.nan), "E": np.full(n, np.nan), "thr": {}, "folds": []}
    end = pd.Timestamp(int(t_fill.max()), unit="s", tz="UTC") + pd.Timedelta(seconds=1)
    cur = pd.Timestamp(start, tz="UTC")
    while cur < end:
        nxt = min(cur + pd.DateOffset(months=months), end)
        s0, s1 = int(cur.timestamp()), int(nxt.timestamp())
        te = (t_fill >= s0) & (t_fill < s1) & (y >= 0)
        usable = (t_exit < s0 - 86400) & (y >= 0)
        if te.sum() and usable.sum() >= min_train:
            fit_m, cal_m = b27.split_fit_cal(t_fill, t_exit, usable)
            m = fit(algo, X[fit_m], y[fit_m])
            T = temperature(proba(algo, m, X[cal_m]), y[cal_m])
            p_cal, p_te = apply_temperature(proba(algo, m, X[cal_m]), T), apply_temperature(proba(algo, m, X[te]), T)
            means = class_means(y[fit_m], net[fit_m], d[fit_m])
            e_cal = expected_net(p_cal, d[cal_m], means)
            out["P"][te], out["E"][te] = p_te, expected_net(p_te, d[te], means)
            for dd in (1, -1):
                for _, q in RULES[1:]:
                    sel = e_cal[d[cal_m] == dd]
                    out["thr"].setdefault((dd, q), []).append((s0, float(np.quantile(sel, 1 - q)) if len(sel) else math.inf))
            out["folds"].append({"start": str(cur.date()), "test": int(te.sum()), "fit": int(fit_m.sum()), "calibrate": int(cal_m.sum()),
                                 "temperature": T})
            log(f"[D] {algo} fold {cur.date()}: test {int(te.sum())}, fit {int(fit_m.sum())}, calibrate {int(cal_m.sum())}, T {T:.2f}")
        cur = nxt
    return out


def selected(L: pd.DataFrame, wf: dict, rule: str) -> np.ndarray:
    E, d, t = wf["E"], L["d"].to_numpy(), L["fill_utc"].to_numpy()
    q = dict(RULES)[rule]
    if q is None:
        return np.flatnonzero(~np.isnan(E) & (E > 0))
    keep = np.zeros(len(L), bool)
    for dd in (1, -1):
        lst = wf["thr"].get((dd, q), [])
        thr = np.full(len(L), np.nan)
        for j, (s0, v) in enumerate(lst):
            s1 = lst[j + 1][0] if j + 1 < len(lst) else 10 ** 12
            thr[(t >= s0) & (t < s1)] = v
        keep |= (d == dd) & ~np.isnan(E) & ~np.isnan(thr) & (E >= thr)
    return np.flatnonzero(keep)


# ---------------- scores ----------------
def metrics(L: pd.DataFrame, P: np.ndarray, y: np.ndarray | None = None) -> dict:
    y = y3(L["outcome"].to_numpy()) if y is None else np.asarray(y)
    m = (y >= 0) & ~np.isnan(P).any(axis=1)
    if not m.any():
        return {"rows": 0}
    yy, pp = y[m], P[m]
    oh = np.eye(3)[yy]
    ll = -np.log(np.clip(pp[np.arange(len(yy)), yy], 1e-12, 1.0))
    dec = yy < 2
    rel = {c: _ece(oh[:, j], pp[:, j]) for j, c in enumerate(CLASSES)}
    return {"rows": int(m.sum()), "logloss": float(ll.mean()), "brier": float(((pp - oh) ** 2).sum(axis=1).mean()),
            "auc_tp_vs_rest": b27.auc((yy == 0).astype(int), pp[:, 0]),
            "auc_tp_vs_sl_decided": b27.auc((yy[dec] == 0).astype(int), pp[dec, 0] / np.clip(pp[dec, 0] + pp[dec, 1], 1e-12, None)),
            "mean_p": dict(zip(CLASSES, pp.mean(axis=0).round(6).tolist(), strict=True)),
            "observed": dict(zip(CLASSES, oh.mean(axis=0).round(6).tolist(), strict=True)),
            "ece": {c: v["ece"] for c, v in rel.items()}, "reliability_tp": rel["TP"]["bins"],
            "max_abs_sum_minus_1": float(np.abs(pp.sum(axis=1) - 1).max())}


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict:
    edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    b = np.clip(np.digitize(p, edges[1:-1]), 0, max(len(edges) - 2, 0))
    rows = [{"p_mean": float(p[b == k].mean()), "observed": float(y[b == k].mean()), "n": int((b == k).sum()),
             "ci95": list(H.wilson(int(y[b == k].sum()), int((b == k).sum())))} for k in np.unique(b)]
    ece = float(sum(r["n"] * abs(r["p_mean"] - r["observed"]) for r in rows) / len(p)) if len(p) else math.nan
    return {"ece": ece, "bins": rows}


def _day_mean(L: pd.DataFrame, x: np.ndarray, m: np.ndarray) -> np.ndarray:
    return pd.Series(x[m]).groupby(L["nyday"].to_numpy()[m]).mean().to_numpy()


def incremental(L: pd.DataFrame, P_base: np.ndarray, P_x: np.ndarray, B: int = 2000, block: float = 5.0, seed: int = SEED,
                y: np.ndarray | None = None) -> dict:
    """Out-of-sample log-loss improvement of a set over Baseline on the same rows, per New York day; stationary bootstrap.
    p = one-sided (H0: no improvement)."""
    y = y3(L["outcome"].to_numpy()) if y is None else np.asarray(y)
    m = (y >= 0) & ~np.isnan(P_base).any(axis=1) & ~np.isnan(P_x).any(axis=1)
    if m.sum() < 100:
        return {"rows": int(m.sum()), "delta_logloss": None, "ci95": [None, None], "p": None}
    idx = np.arange(len(y))[m]
    lb = -np.log(np.clip(P_base[idx, y[m]], 1e-12, 1.0))
    lx = -np.log(np.clip(P_x[idx, y[m]], 1e-12, 1.0))
    full = np.zeros(len(y))
    full[idx] = lb - lx
    daily = _day_mean(L, full, m)
    obs = float(daily.mean())
    rng = H.seeded_rng(seed)
    boots = np.array([daily[H.stationary_bootstrap_idx(len(daily), block, rng)].mean() for _ in range(B)])
    p = float(np.mean(boots - obs >= obs)) if obs > 0 else 1.0
    return {"rows": int(m.sum()), "days": len(daily), "delta_logloss": obs, "ci95": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
            "p": p, "auc_tp_base": b27.auc((y[m] == 0).astype(int), P_base[m, 0]), "auc_tp_set": b27.auc((y[m] == 0).astype(int), P_x[m, 0])}


# ---------------- strategies ----------------
def series(L: pd.DataFrame, rows: np.ndarray) -> pd.DataFrame:
    """The independent (non-overlapping per direction) trades among the selected rows."""
    if len(rows) == 0:
        return L.iloc[:0]
    sub = L.iloc[rows]
    parts = []
    for dd in (1, -1):
        s = sub[sub["d"] == dd]
        if len(s):
            parts.append(s.iloc[b27.seq_rows(s["dec_i"].to_numpy(), s["exit_bar"].to_numpy(), s["outcome"].to_numpy())])
    return pd.concat(parts).sort_values("fill_utc") if parts else L.iloc[:0]


def risk(net_r: np.ndarray, seed: int = SEED) -> dict:
    """Block bootstrap (blocks of 10 consecutive trades) of 250-trade paths in R units: the drawdown distribution."""
    if len(net_r) < C6_BLOCK * 2:
        return {"p_dd_ge_15R_in_250": None, "dd95_R": None}
    rng = H.seeded_rng(seed)
    nb = math.ceil(C6_TRADES / C6_BLOCK)
    starts = rng.integers(0, len(net_r), size=(C6_PATHS, nb))
    pick = (starts[:, :, None] + np.arange(C6_BLOCK)[None, None, :]) % len(net_r)
    paths = net_r[pick.reshape(C6_PATHS, -1)[:, :C6_TRADES]]
    cum = np.cumsum(paths, axis=1)
    dd = (np.maximum.accumulate(np.concatenate([np.zeros((C6_PATHS, 1)), cum], axis=1), axis=1)[:, 1:] - cum).max(axis=1)
    run = longest_losing_run(net_r)
    return {"p_dd_ge_15R_in_250": float(np.mean(dd >= C6_DD_R)), "dd95_R": float(np.quantile(dd, 0.95)), "longest_losing_run": run}


def longest_losing_run(x: np.ndarray) -> int:
    best = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return best


def _by(t: pd.DataFrame, col: str) -> dict:
    return {str(k): {"n": len(g), "exp_oz": float(g["net_usd_oz"].mean())} for k, g in t.groupby(col)} if len(t) else {}


def strategy_stats(t: pd.DataFrame, rates: dict, weeks: float, seed: int = SEED) -> dict:
    out = t["outcome"].to_numpy()
    net = t["net_usd_oz"].to_numpy(float)
    s = b27.stats_of(out, net, t["minutes"].to_numpy(float), t["cost_usd_oz"].to_numpy(float), t["d"].to_numpy(),
                     t["session"].to_numpy(), t["ym"].to_numpy(), t["nyday"].to_numpy(), rates, weeks)
    s.pop("_seq", None)
    year = pd.to_datetime(t["fill_utc"], unit="s", utc=True).dt.year.astype(str).to_numpy() if len(t) else np.array([])
    tt = t.assign(year=year)
    s.update({"by_year": _by(tt, "year"), "by_vol_tercile": _by(t, "vol_tercile"), "by_trend": _by(t, "trend_state"),
              "by_direction": _by(t, "dir"), "minutes_tp_median": float(t.loc[t["outcome"] == "TP", "minutes"].median()) if (out == "TP").any() else None,
              "minutes_sl_median": float(t.loc[np.isin(out, ["SL", "AMBIGUOUS"]), "minutes"].median()) if np.isin(out, ["SL", "AMBIGUOUS"]).any() else None,
              **risk(net / R_USD, seed)})
    return s


def daily_r(t: pd.DataFrame, days: np.ndarray) -> np.ndarray:
    """Net R per New York day over `days` (0 on days without a trade): the Reality Check's per-period series."""
    if not len(t):
        return np.zeros(len(days))
    s = (t["net_usd_oz"] / R_USD).groupby(t["nyday"]).sum()
    return s.reindex(days).fillna(0.0).to_numpy()


def criteria(dev: dict, y26: dict | None, bh_ok: bool, rc_p: float | None, holm_p: float | None) -> dict:
    """C1-C6 (registration "acceptance"). y26 = the frozen check on 2026 (None when not run: the criteria needing it fail)."""
    y = y26 or {}
    yrs = [v["exp_oz"] for v in dev.get("by_year", {}).values() if v["n"] >= MIN_STRATA]
    vol = [v["exp_oz"] for k, v in dev.get("by_vol_tercile", {}).items() if k != "NA" and v["n"] >= MIN_STRATA]
    trd = [v["exp_oz"] for k, v in dev.get("by_trend", {}).items() if k != "NA" and v["n"] >= MIN_STRATA]
    c = {"C1_positive_expectancy_dev_and_oos": bool((dev.get("exp_oz") or -1) > 0 and (y.get("exp_oz") or -1) > 0),
         "C2_beats_matched_random": bool(_lo(dev) > (dev.get("matched_random") or 1) and _lo(y) > (y.get("matched_random") or 1)),
         "C3_bh_and_reality_check": bool(bh_ok and rc_p is not None and rc_p < RC_P and holm_p is not None and holm_p < HOLM_P),
         "C4_stable": bool(yrs and all(e > 0 for e in yrs) and (y.get("exp_oz") or -1) > 0 and sum(e > 0 for e in vol) >= 2
                           and sum(e > 0 for e in trd) >= 2),
         "C5_independent_trades": bool((dev.get("n_trades") or 0) >= C5_MIN),
         "C6_drawdown_ruin": bool(dev.get("p_dd_ge_15R_in_250") is not None and dev["p_dd_ge_15R_in_250"] <= C6_P)}
    c["C5_preferred_500"] = bool((dev.get("n_trades") or 0) >= C5_PREFERRED)
    c["QUALIFIES"] = all(v for k, v in c.items() if k.startswith("C") and k != "C5_preferred_500")
    return c


def _lo(s: dict) -> float:
    ci = s.get("ci95") or [None]
    return ci[0] if ci and ci[0] is not None and not (isinstance(ci[0], float) and math.isnan(ci[0])) else -1.0


# ---------------- the study ----------------
def final_fit(F: pd.DataFrame, L: pd.DataFrame, cols: list[str], algo: str) -> dict:
    """Refit on all development (calibration = its own last 20%); the frozen model and thresholds applied once to 2026."""
    y, d = y3(L["outcome"].to_numpy()), L["d"].to_numpy()
    X = design(F, L, cols)
    fit_m, cal_m = b27.split_fit_cal(L["fill_utc"].to_numpy(), L["exit_utc"].to_numpy(), y >= 0)
    m = fit(algo, X[fit_m], y[fit_m])
    T = temperature(proba(algo, m, X[cal_m]), y[cal_m])
    means = class_means(y[fit_m], L["net_usd_oz"].to_numpy(float)[fit_m], d[fit_m])
    e_cal = expected_net(apply_temperature(proba(algo, m, X[cal_m]), T), d[cal_m], means)
    thr = {(dd, q): float(np.quantile(e_cal[d[cal_m] == dd], 1 - q)) for dd in (1, -1) for _, q in RULES[1:]}
    return {"model": m, "T": T, "means": means, "thr": thr, "cols": cols, "algo": algo}


def apply_frozen(FM: dict, F: pd.DataFrame, L: pd.DataFrame) -> dict:
    X = design(F, L, FM["cols"])
    P = apply_temperature(proba(FM["algo"], FM["model"], X), FM["T"])
    E = expected_net(P, L["d"].to_numpy(), FM["means"])
    thr = {k: [(0, v)] for k, v in FM["thr"].items()}
    return {"P": P, "E": E, "thr": thr}


def run(F: pd.DataFrame, L: pd.DataFrame, of_cols: list[str], im_cols: list[str], Fy: pd.DataFrame | None = None,
        Ly: pd.DataFrame | None = None, sets=SETS, algos=ALGOS, wf_start: str = WF_START, min_train: int = MIN_TRAIN,
        months: int = 3, log=print) -> dict:
    rates, weeks = b27.base_rates(L), b27.weeks_of(L)
    days = np.unique(L["nyday"].to_numpy())
    res = {"sets": {}, "not_run": {}, "strategies": [], "incremental": {}}
    wfs = {}
    for name in sets:
        try:
            cols = set_columns(F, name, of_cols, im_cols)
        except NotAvailable as e:
            res["not_run"][name] = str(e)
            continue
        res["sets"][name] = {"columns": cols, "n_columns": len(cols)}
        for algo in algos:
            wf = walk_forward(F, L, cols, algo, wf_start, min_train, months, log)
            wfs[(name, algo)] = wf
            res["sets"][name][algo] = {"metrics": metrics(L, wf["P"]), "folds": wf["folds"]}
            for rule, _ in RULES:
                rows = selected(L, wf, rule)
                t = series(L, rows)
                st = strategy_stats(t, rates, weeks)
                res["strategies"].append({"id": f"{name}/{algo}/{rule}", "set": name, "algo": algo, "rule": rule, "dev": st,
                                          "_daily": daily_r(t, days), "_rows_dev": rows})
    for (name, algo), wf in wfs.items():
        if name != "BASELINE" and ("BASELINE", algo) in wfs:
            res["incremental"][f"{name}/{algo}"] = incremental(L, wfs[("BASELINE", algo)]["P"], wf["P"])
    for name in {k.split("/")[0] for k in res["incremental"]}:
        keys = [k for k in res["incremental"] if k.split("/")[0] == name and res["incremental"][k].get("p") is not None]
        for k, hp in zip(keys, b27.holm([res["incremental"][k]["p"] for k in keys]), strict=True):
            res["incremental"][k]["p_holm_over_algorithms"] = hp                # H-D1: Holm over the algorithms of a set
    S = res["strategies"]
    ps = [s["dev"].get("p_vs_random", 1.0) for s in S]
    bh = H.benjamini_hochberg(ps, BH_Q) if S else []
    rc = H.reality_check(np.column_stack([s["_daily"] for s in S]), B=1000) if S else {"p_value": None}
    for s, ok in zip(S, bh, strict=True):
        s["bh_q010"] = bool(ok)
    res["family"] = {"strategies": len(S), "bh_q": BH_Q, "bh_passed": int(sum(bh)), "reality_check": rc}
    frozen = [s for s in S if s["bh_q010"] and (s["dev"].get("exp_oz") or -1) > 0 and (s["dev"].get("n_trades") or 0) >= C5_MIN]
    res["frozen"] = [s["id"] for s in frozen]
    if Fy is not None and Ly is not None and frozen:
        rates_y, weeks_y = b27.base_rates(Ly), b27.weeks_of(Ly)
        for s in frozen:
            FM = final_fit(F, L, res["sets"][s["set"]]["columns"], s["algo"])
            ap = apply_frozen(FM, Fy, Ly)
            s["_rows_y2026"] = selected(Ly, ap, s["rule"])
            s["y2026"] = strategy_stats(series(Ly, s["_rows_y2026"]), rates_y, weeks_y)
        holm = b27.holm([s["y2026"].get("p_vs_random", 1.0) for s in frozen])
        for s, hp in zip(frozen, holm, strict=True):
            s["y2026_holm_p"] = hp
    for s in S:
        s["criteria"] = criteria(s["dev"], s.get("y2026"), s["bh_q010"], rc.get("p_value"), s.get("y2026_holm_p"))
        s.pop("_daily", None)
    q = [s["id"] for s in S if s["criteria"]["QUALIFIES"]]
    res["qualified"] = q
    res["verdict"] = "QUALIFIES FOR FURTHER VALIDATION" if q else "NO QUALIFIED STRATEGY"
    return res


# ---------------- descriptive questions (Workstream A; registered as descriptive, not strategies) ----------------
FAV_X = (5.0, 10.0, 15.0, 20.0)
FAV_BARS = 16                       # the next four hours of 15-minute bars from the fill
Q_SETS, Q_ALGOS = ("BASELINE", "B", "D"), ("LR", "LGBM")
INCONCLUSIVE_AMB = 0.02             # B29: a bracket whose AMBIGUOUS share exceeds 2% is only bounded at 15 minutes


def favourable(L: pd.DataFrame, m15: pd.DataFrame, x: float, bars: int = FAV_BARS) -> np.ndarray:
    """0 when the trigger side reaches +x (x k) from the fill within `bars` bars of the fill bar, else 1; -1 at the end of
    the data. Not a race (the adverse side is ignored): P(favourable move)."""
    h, lo = m15["high"].to_numpy(float), m15["low"].to_numpy(float)
    n = len(h)
    hf = pd.Series(h[::-1]).rolling(bars, min_periods=bars).max().to_numpy()[::-1]
    lf = pd.Series(lo[::-1]).rolling(bars, min_periods=bars).min().to_numpy()[::-1]
    f = L["dec_i"].to_numpy() + 1
    ok = f + bars <= n
    fc = np.clip(f, 0, n - 1)
    k, d, fill = L["k"].to_numpy(float), L["d"].to_numpy(), L["fill_px"].to_numpy(float)
    half = L["spread"].to_numpy(float) * k / 2.0
    fav = np.where(d > 0, (hf[fc] - half) - fill, fill - (lf[fc] + half))
    return np.where(ok, np.where(fav >= x * k, 0, 1), -1)


def adverse_first(L: pd.DataFrame, m15: pd.DataFrame, x: float, path_m1=None) -> tuple[np.ndarray, dict]:
    """The +-x race from the same fill (ENG): class 0 = favourable first, 1 = adverse first (AMBIGUOUS = adverse at
    15 minutes), 2 = neither. With a one-minute path (d_m1.M1Path, Dukascopy or MT5) the race is run there instead."""
    from . import d_m1
    k, d, fill, dec = L["k"].to_numpy(float), L["d"].to_numpy(), L["fill_px"].to_numpy(float), L["dec_i"].to_numpy()
    spread = L["spread"].to_numpy(float)
    if path_m1 is not None:
        P15 = b26.make_path(m15, 900)
        t15 = np.asarray(P15.t, dtype=np.int64)
        t_end = np.where(dec + 1 + 191 < len(t15), t15[np.clip(dec + 1 + 191, 0, len(t15) - 1)] + 900, 2 ** 62)
        y, amb = np.full(len(L), -1), 0
        for dd in (1, -1):
            m = d == dd
            br = d_m1.bracket(path_m1, L["fill_utc"].to_numpy()[m], t_end[m], dd, x, x, k[m], si=0.20, so=0.20, cm=0.07)
            o = br["outcome"].to_numpy()
            y[np.flatnonzero(m)] = np.where(o == "TP", 0, np.where(np.isin(o, ["SL", "AMBIGUOUS"]), 1,
                                                                  np.where(np.isin(o, ["TIMEOUT", "CLOSURE"]), 2, -1)))
            amb += int((o == "AMBIGUOUS").sum())
        return y, {"resolution": "one minute (" + path_m1.source + ")", "ambiguous_share": amb / max(int((y >= 0).sum()), 1)}
    P = b26.make_path(m15, 900)
    y, amb = np.full(len(L), -1), 0
    for r in range(len(L)):
        oc = b27.race_fill(P, int(dec[r]) + 1, float(fill[r]), int(d[r]), float(spread[r] * k[r]), float(0.20 * k[r]),
                           float(k[r] * x / b26.MOVE), b26.HORIZON["15m"])[0]
        y[r] = {"TP": 0, "SL": 1, "AMBIGUOUS": 1, "TIMEOUT": 2, "CLOSURE": 2}.get(oc, -1)
        amb += oc == "AMBIGUOUS"
    share = amb / max(int((y >= 0).sum()), 1)
    return y, {"resolution": "15 minutes (worst case)", "ambiguous_share": share, "inconclusive_at_15m": bool(share > INCONCLUSIVE_AMB)}


def time_by_quintile(L: pd.DataFrame, P: np.ndarray) -> list[dict]:
    """Median minutes to TP and to SL by quintile of P(TP) (out of sample): the expected-time question."""
    y = y3(L["outcome"].to_numpy())
    m = (y >= 0) & ~np.isnan(P[:, 0])
    if m.sum() < 50:
        return []
    q = pd.qcut(P[m, 0], 5, labels=False, duplicates="drop")
    mins, yy = L["minutes"].to_numpy(float)[m], y[m]
    return [{"quintile": int(b), "p_tp_mean": float(P[m, 0][q == b].mean()), "n": int((q == b).sum()),
             "minutes_tp_median": float(np.median(mins[(q == b) & (yy == 0)])) if ((q == b) & (yy == 0)).any() else None,
             "minutes_sl_median": float(np.median(mins[(q == b) & (yy == 1)])) if ((q == b) & (yy == 1)).any() else None}
            for b in np.unique(q)]


def delay_effect(L: pd.DataFrame, F: pd.DataFrame, col: str = "sg_of_ofi15") -> dict:
    """Entering one bar later (decision i+1 instead of i, same direction): the paired net difference, split by whether
    the order flow at i is with or against the trade. Descriptive; day-clustered intervals (b26.cluster_ci)."""
    if col not in F.columns:
        return {"not_run": f"{col} not available"}
    out = {}
    for dd in (1, -1):
        s = L[(L["d"] == dd) & (L["outcome"] != "OPEN")].set_index("dec_i")
        nxt = s.reindex(s.index + 1)
        ok = nxt["net_usd_oz"].notna().to_numpy()
        diff = (nxt["net_usd_oz"].to_numpy() - s["net_usd_oz"].to_numpy())[ok]
        flow = (F[col].to_numpy(float)[s.index.to_numpy()] * dd)[ok]
        day = s["nyday"].to_numpy()[ok]
        for lab, m in (("flow_with", flow > 0), ("flow_against", flow < 0)):
            if m.sum() >= 100:
                out[f"{b26.DIRS[dd]}_{lab}"] = {"n": int(m.sum()), "mean_net_change_oz": float(diff[m].mean()),
                                                "ci95": b26.cluster_ci(diff[m], day[m])}
    return out


def questions(F: pd.DataFrame, L: pd.DataFrame, m15: pd.DataFrame, of_cols: list[str], im_cols: list[str], path_m1=None,
              sets=Q_SETS, algos=Q_ALGOS, wf_start: str = WF_START, min_train: int = MIN_TRAIN, months: int = 3, log=print) -> dict:
    labels = {f"FAV{int(x)}": (favourable(L, m15, x), {"resolution": "15 minutes (exact: no race)"}) for x in FAV_X}
    for x in FAV_X:
        labels[f"ADV_FIRST{int(x)}"] = adverse_first(L, m15, x, path_m1)
    out = {"labels": {}, "delay": delay_effect(L, F)}
    for lab, (y, info) in labels.items():
        rec = {"info": info, "base_rate_class0": float(np.mean(y[y >= 0] == 0)) if (y >= 0).any() else None, "sets": {}}
        P = {}
        for name in sets:
            try:
                cols = set_columns(F, name, of_cols, im_cols)
            except NotAvailable as e:
                rec["sets"][name] = {"not_run": str(e)}
                continue
            for algo in algos:
                wf = walk_forward(F, L, cols, algo, wf_start, min_train, months, log, y=y)
                P[(name, algo)] = wf["P"]
                rec["sets"].setdefault(name, {})[algo] = metrics(L, wf["P"], y)
        for (name, algo), p in P.items():
            if name != "BASELINE" and ("BASELINE", algo) in P:
                rec.setdefault("incremental", {})[f"{name}/{algo}"] = incremental(L, P[("BASELINE", algo)], p, y=y)
        out["labels"][lab] = rec
    return out
