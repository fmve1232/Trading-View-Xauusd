"""Phase B13 (research/registrations/B13.json, approved 2026-11-05; written after the registration was committed).

The operator's target: +$10 to +$20 (ideal +$15) in the trade's direction before a -$13 stop ($650 at 0.5 lot).

  B13-0   random entries vs the driftless value S / (T + S) (optional stopping): a labeller audit, descriptive
  B13-2a  overnight BUY 13:30 -> 08:30 New York (Blose, Gondhalekar & Kort 2018)          development, primary
  B13-2b  day SELL 08:30 -> 13:30 New York                                               development, primary
  B13-3   intraday momentum: the opening return at 09:00 New York, held to 13:30 (Gao et al. 2018)   development
  B13-4   a gradient-boosted direction model with purged walk-forward folds              development, primary
  B13-1   the B10 lead (the frozen engine's own 15m signals) on the sealed validation partition, opened once
  (prop-firm pass probabilities, arithmetic with no market data: research/tools/b13_prop_pass.py)

Outcome: +T before -S, dollars at $4,000 scaled by entry / 4000, on 15-minute bars of the same partition; a bar reaching
both levels is a loss unless it opened beyond the target. Net results are reported in dollars at $4,000 (T - cost or
-S - cost, with harness.cost_pts read as the frozen model's cost at today's price), and with the operator's measured
$0.26 round trip as a secondary. Research code: never imported by production (tests/test_integrity.py).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .. import config, engine, sessions, ta
from ..data import sources
from ..features import compute as compute_features
from . import b10, history
from . import harness as H

REG = "B13"
NY = "America/New_York"
S_STOP, T_MAIN = 13.0, 15.0
T_ALL = (10.0, 13.0, 15.0, 20.0)
S_GRID = (10.0, 13.0, 15.0, 20.0, 26.0, 30.0)
PATH_BARS = 96
SCORE_FROM = pd.Timestamp("2020-04-01", tz="UTC")
MIN_N = 30
OP_COST = 0.26                      # the operator's measured round trip per oz (spread + commission), secondary
BLOCKS, PURGE, Q_THR = 6, 96, 0.90


# ---------------- the barrier race ----------------
def race(path: pd.DataFrame, t_close: np.ndarray, price: np.ndarray, d: np.ndarray, T: float, S: float,
         nbars: int = PATH_BARS, end_t: np.ndarray | None = None, scale: bool = True, chunk: int = 20000) -> dict:
    """+T before -S from each decision close on the path bars opening at / after it: at most nbars of them, and only
    bars opening before end_t[x] when end_t is given. Distances are scaled by entry / 4000 when scale. Returns boolean
    win / loss / tie (a two-level bar counted as a loss) / ok, j (first path bar) and k (deciding bar in the window,
    nbars when neither level was reached)."""
    t = ta.epoch_s(path.index).astype(np.int64)
    o, h, lo_ = (path[x].to_numpy(float) for x in ("open", "high", "low"))
    m = len(t_close)
    j = np.searchsorted(t, np.asarray(t_close, np.int64))
    ok = (j + nbars <= len(t)) & np.isfinite(price) & (d != 0)
    win, loss, tie = np.zeros(m, bool), np.zeros(m, bool), np.zeros(m, bool)
    k = np.full(m, nbars)
    if len(t) < nbars:
        return {"ok": ok & False, "win": win, "loss": loss, "tie": tie, "j": j, "k": k}
    Wt, Wo, Wh, Wl = (sliding_window_view(a, nbars) for a in (t, o, h, lo_))
    idx = np.flatnonzero(ok)
    for c0 in range(0, len(idx), chunk):
        ii = idx[c0:c0 + chunk]
        jj = j[ii]
        p, dd = price[ii][:, None], d[ii][:, None]
        s = (price[ii] / 4000.0 if scale else np.ones(len(ii)))[:, None]
        a, b = T * s, S * s
        hh, ll = Wh[jj], Wl[jj]
        fav = np.where(dd > 0, hh - p, p - ll)
        adv = np.where(dd > 0, p - ll, hh - p)
        valid = Wt[jj] < np.asarray(end_t)[ii][:, None] if end_t is not None else np.ones(fav.shape, bool)
        ht = (fav >= a - 1e-9) & valid
        hs = (adv >= b - 1e-9) & valid
        it = np.where(ht.any(1), ht.argmax(1), nbars)
        is_ = np.where(hs.any(1), hs.argmax(1), nbars)
        w, ls = it < is_, is_ < it
        both = np.flatnonzero((it == is_) & (it < nbars))
        if len(both):
            beyond = (Wo[jj[both], it[both]] - p[both, 0]) * dd[both, 0] >= a[both, 0] - 1e-9
            w[both], ls[both] = beyond, ~beyond
            tie[ii[both]] = ~beyond
        win[ii], loss[ii], k[ii] = w, ls, np.minimum(it, is_)
    return {"ok": ok, "win": win, "loss": loss, "tie": tie, "j": j, "k": k}


def stats(r: dict, d: np.ndarray, cost: np.ndarray, T: float, S: float, base: np.ndarray) -> dict:
    """base: the random success rate for each trade (direction-matched, or time-matched for clock rules)."""
    dec = r["win"] | r["loss"]
    n, wins = int(dec.sum()), int(r["win"].sum())
    rate = wins / n if n else math.nan
    mix = float(np.mean(base[dec])) if n else math.nan
    z = (rate - mix) / math.sqrt(mix * (1 - mix) / n) if n and 0 < mix < 1 else math.nan
    net = np.where(r["win"], T - cost, -S - cost)[dec]
    net_op = np.where(r["win"], T - OP_COST, -S - OP_COST)[dec]

    def tstat(x):
        sd = float(np.std(x, ddof=1)) if len(x) > 2 else 0.0
        return float(np.mean(x) / (sd / math.sqrt(len(x)))) if sd > 0 else math.nan

    lo, hi = H.wilson(wins, n)
    return {"n": n, "wins": wins, "long": int(((d > 0) & dec).sum()), "short": int(((d < 0) & dec).sum()),
            "open": int((r["ok"] & ~dec).sum()), "ties_counted_loss": int((r["tie"] & dec).sum()),
            "rate": rate, "wilson": [lo, hi], "random": mix, "theory_driftless": S / (T + S), "z": z,
            "p_one_sided": 1 - H._norm_cdf(z) if math.isfinite(z) else math.nan,
            "break_even_model_cost": float(np.mean((S + cost[dec]) / (T + S))) if n else math.nan,
            "break_even_operator_cost": (S + OP_COST) / (T + S),
            "mean_net_usd_per_oz_at_4000": float(np.mean(net)) if n else math.nan, "t": tstat(net) if n else math.nan,
            "mean_net_operator_cost": float(np.mean(net_op)) if n else math.nan, "t_operator_cost": tstat(net_op) if n else math.nan,
            "usd_per_trade_0p5lot_at_4000": float(np.mean(net)) * 50 if n else math.nan}


def holm(ps: dict, alpha: float = 0.05) -> dict:
    return b10.holm(ps, alpha)


def _clean(x):
    return b10._clean(x)


# ---------------- data ----------------
def load(rd: str, part: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    m15 = history.load(rd, "XAU/USD", "15min")
    h1 = history.load(rd, "XAU/USD", "1h")
    if part == "development":
        return H.partition(m15, "development"), H.partition(h1, "development")
    return H.partition(m15, part, REG), H.partition(h1, part, REG)


def tday(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """New York trading day (17:00 roll) of each bar open, naive midnight."""
    return (idx.tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)).normalize()


def random_rates(path: pd.DataFrame, idx: pd.DatetimeIndex, c: np.ndarray, rows: np.ndarray, T: float, S: float,
                 tf_sec: int = 900, nbars: int = PATH_BARS, scale: bool = True) -> dict:
    t_close = ta.epoch_s(idx).astype(np.int64) + tf_sec
    out = {}
    for nm, s in (("long", 1), ("short", -1)):
        r = race(path, t_close[rows], c[rows], np.full(len(rows), s), T, S, nbars, scale=scale)
        dec = r["win"] | r["loss"]
        out[nm] = float(r["win"][dec].mean()) if dec.any() else math.nan
        out[f"{nm}_n"] = int(dec.sum())
        out[f"{nm}_ties"] = int((r["tie"] & dec).sum())
        out[f"{nm}_r"] = r
    return out


# ---------------- B13-0: geometry ----------------
def geometry(path: pd.DataFrame, c: np.ndarray, rows: np.ndarray, tf_sec: int, nbars: int, scale: bool) -> dict:
    idx = path.index
    cal = sessions.calendar(idx)
    lon, nyf = cal["in_london"].to_numpy(bool), cal["in_ny"].to_numpy(bool)
    sess = np.where(nyf, "New York", np.where(lon, "London", "Asia / off"))
    t = ta.epoch_s(idx).astype(np.int64)
    t_close = t + tf_sec
    grid = {}
    for T in T_ALL:
        for S in S_GRID:
            rr = random_rates(path, idx, c, rows, T, S, tf_sec, nbars, scale)
            avg = (rr["long"] + rr["short"]) / 2
            ties = (rr["long_ties"] + rr["short_ties"]) / max(1, rr["long_n"] + rr["short_n"])
            cell = {"long": rr["long"], "short": rr["short"], "average": avg, "theory": S / (T + S),
                    "gap_pp": 100 * (avg - S / (T + S)), "tie_share": ties, "n": rr["long_n"] + rr["short_n"]}
            if T == T_MAIN and S == S_STOP:
                mins = {}
                for side in ("long", "short"):
                    r = rr[f"{side}_r"]
                    dec = r["win"] | r["loss"]
                    sel = np.flatnonzero(dec)
                    at = t[np.minimum(r["j"][sel] + r["k"][sel], len(t) - 1)] + tf_sec
                    mins[side] = ((at - t_close[rows][sel]) / 60.0, sess[rows][sel])
                allm = np.concatenate([mins["long"][0], mins["short"][0]])
                alls = np.concatenate([mins["long"][1], mins["short"][1]])
                cell["minutes_to_resolution_median"] = {s: float(np.median(allm[alls == s])) for s in np.unique(alls)}
                cell["minutes_to_resolution_median"]["all"] = float(np.median(allm))
            grid[f"T{T:g}/S{S:g}"] = cell
    return grid


# ---------------- B13-2 / 3: clock rules ----------------
def clock_rules(m15: pd.DataFrame, scored: np.ndarray) -> dict:
    """Decision rows, directions and window ends (epoch) for 2a, 2b and 3."""
    idx = m15.index
    t = ta.epoch_s(idx).astype(np.int64)
    ny_close = (idx + pd.Timedelta(minutes=15)).tz_convert(NY)
    hm = ny_close.hour * 100 + ny_close.minute
    c = m15["close"].to_numpy(float)
    i1330 = np.flatnonzero(hm == 1330)
    i0830 = np.flatnonzero(hm == 830)
    i0900 = np.flatnonzero(hm == 900)
    t1330, t0830 = t[i1330] + 900, t[i0830] + 900               # the closes of those bars
    out = {}
    # 2a: BUY at 13:30, window to the next 08:30 close (bars opening before it)
    nx = np.searchsorted(t0830, t[i1330] + 900, side="right")
    keep = nx < len(t0830)
    rows = i1330[keep]
    out["B13-2a"] = (rows, np.ones(len(rows), int), t0830[nx[keep]])
    # 2b: SELL at 08:30, window to the same trading day's 13:30 close
    nx = np.searchsorted(t1330, t[i0830] + 900, side="right")
    keep = (nx < len(t1330)) & ((t1330[np.minimum(nx, len(t1330) - 1)] - (t[i0830] + 900)) <= 6 * 3600)
    rows = i0830[keep]
    out["B13-2b"] = (rows, -np.ones(len(rows), int), t1330[nx[keep]])
    # 3: at 09:00, the sign of close(09:00) - close(previous 13:30), window to the same day's 13:30 close
    pv = np.searchsorted(t1330, t[i0900] + 900, side="right") - 1
    nx = pv + 1
    keep = (pv >= 0) & (nx < len(t1330)) & ((t1330[np.minimum(nx, len(t1330) - 1)] - (t[i0900] + 900)) <= 6 * 3600)
    rows = i0900[keep]
    ret = c[rows] - c[i1330[pv[keep]]]
    d = np.sign(ret).astype(int)
    out["B13-3"] = (rows[d != 0], d[d != 0], t1330[nx[keep]][d != 0])
    for key, (rows, d, e) in list(out.items()):
        m = scored[rows]
        out[key] = (rows[m], d[m], e[m])
    return out


def window_return(m15: pd.DataFrame, rows: np.ndarray, d: np.ndarray, end_t: np.ndarray) -> dict:
    """The raw signed log return from the decision close to the window's last close (Blose / Gao measure)."""
    t = ta.epoch_s(m15.index).astype(np.int64) + 900
    c = m15["close"].to_numpy(float)
    last = np.searchsorted(t, end_t, side="right") - 1
    r = d * np.log(c[last] / c[rows])
    sd = float(np.std(r, ddof=1))
    return {"n": len(r), "mean_bp": float(1e4 * np.mean(r)), "t": float(np.mean(r) / (sd / math.sqrt(len(r)))) if sd > 0 else math.nan}


# ---------------- B13-4: features and the model ----------------
def features(m15: pd.DataFrame, h1: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    idx = m15.index
    o, h, lo_, c = (m15[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    t_close = ta.epoch_s(idx).astype(np.int64) + 900
    cols: dict[str, np.ndarray] = {}
    lc = np.log(c)
    for n in (1, 4, 16, 96):
        cols[f"lr{n}"] = lc - ta.shift(lc, n)
    a15 = ta.atr(h, lo_, c, 14)
    cols["atr15"] = a15 / c
    cols["atr_ratio"] = a15 / pd.Series(a15).rolling(480, min_periods=480).median().to_numpy()
    # 1h and 4h: last completed bar
    h1h, h1l, h1c = (h1[x].to_numpy(float) for x in ("high", "low", "close"))
    h1t = ta.epoch_s(h1.index).astype(np.int64) + 3600
    p1 = np.searchsorted(h1t, t_close, side="right") - 1
    a1 = ta.atr(h1h, h1l, h1c, 14)
    e20_1, e50_1 = ta.ema(h1c, 20), ta.ema(h1c, 50)
    g1 = p1 >= 0
    take = lambda arr, p, g: np.where(g, arr[np.maximum(p, 0)], np.nan)
    cols["atr1h"] = take(a1, p1, g1) / c
    h4 = sources.resample_ny_session(h1, 4)
    h4t = ta.epoch_s(h4.index).astype(np.int64) + 4 * 3600
    p4 = np.searchsorted(h4t, t_close, side="right") - 1
    h4c = h4["close"].to_numpy(float)
    e20_4, e50_4 = ta.ema(h4c, 20), ta.ema(h4c, 50)
    g4 = p4 >= 0
    # trading-day, week and month levels from the 15m bars themselves
    td = tday(idx)
    df = pd.DataFrame({"h": h, "l": lo_, "c": c, "td": td})
    cols_td_h = df.groupby("td")["h"].cummax().to_numpy()
    cols_td_l = df.groupby("td")["l"].cummin().to_numpy()
    day = df.groupby("td").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    dh, dl, dc = (day[x].to_numpy(float) for x in ("h", "l", "c"))
    datr = ta.atr(dh, dl, dc, 14)
    dsma = ta.sma(dc, 20)
    dpos = np.searchsorted(day.index.values, td.values) - 1            # the previous completed trading day
    gd = dpos >= 0
    pdh, pdl = take(dh, dpos, gd), take(dl, dpos, gd)
    datr_p = take(datr, dpos, gd)
    vote_d = np.sign(take(dc, dpos, gd) - take(dsma, dpos, gd))
    wk = td - pd.to_timedelta(td.day_of_week, unit="D")
    df["wk"], df["mo"] = wk, td.to_period("M").to_timestamp()
    levels = {}
    for key in ("wk", "mo"):
        g = df.groupby(key).agg(h=("h", "max"), l=("l", "min"))
        pos = np.searchsorted(g.index.values, df[key].values) - 1
        gg = pos >= 0
        levels[key] = (take(g["h"].to_numpy(float), pos, gg), take(g["l"].to_numpy(float), pos, gg))
    a = np.where(a15 > 0, a15, np.nan)
    for nm, lv in (("tdh", cols_td_h), ("tdl", cols_td_l), ("pdh", pdh), ("pdl", pdl), ("pwh", levels["wk"][0]),
                   ("pwl", levels["wk"][1]), ("pmh", levels["mo"][0]), ("pml", levels["mo"][1])):
        cols[f"d_{nm}"] = np.clip((c - lv) / a, -20, 20)
    rng_today = cols_td_h - cols_td_l
    cols["range_today"] = rng_today / datr_p
    cols["pos_today"] = np.where(rng_today > 0, (c - cols_td_l) / np.where(rng_today > 0, rng_today, 1), 0.5)
    vote_4 = np.where(g4, np.sign(e20_4[np.maximum(p4, 0)] - e50_4[np.maximum(p4, 0)]), np.nan)
    vote_1 = np.where(g1, np.sign(e20_1[np.maximum(p1, 0)] - e50_1[np.maximum(p1, 0)]), np.nan)
    cols["vote_d"], cols["vote_4h"], cols["vote_1h"] = vote_d, vote_4, vote_1
    cols["vote_sum"] = vote_d + vote_4 + vote_1
    e20 = ta.ema(c, 20)
    cols["ema20_slope"] = (e20 - ta.shift(e20, 4)) / a
    cols["rsi14"] = ta.rsi(c, 14)
    br = h - lo_
    safe = np.where(br > 0, br, 1.0)
    cols["close_loc"] = np.where(br > 0, (c - lo_) / safe, 0.5)
    cols["upper_wick"] = np.where(br > 0, (h - np.maximum(o, c)) / safe, 0.0)
    cols["lower_wick"] = np.where(br > 0, (np.minimum(o, c) - lo_) / safe, 0.0)
    nyc = (idx + pd.Timedelta(minutes=15)).tz_convert(NY)
    hr = nyc.hour.to_numpy() + nyc.minute.to_numpy() / 60.0
    cols["hour_sin"], cols["hour_cos"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
    cols["weekday"] = td.day_of_week.to_numpy().astype(float)
    cal = sessions.calendar(idx)
    cols["london"], cols["newyork"] = cal["in_london"].to_numpy(float), cal["in_ny"].to_numpy(float)
    names = list(cols)
    X = np.column_stack([np.asarray(cols[k], float) for k in names])
    return X, names


def _model(kind: str):
    if kind == "gbm":
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
                                              min_samples_leaf=200, random_state=13)
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))


def _fit_predict(kind, X, y, tr, te):
    Xtr, Xte = X[tr], X[te]
    if kind != "gbm":                                   # impute with training medians
        med = np.nanmedian(Xtr, axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        Xtr = np.where(np.isfinite(Xtr), Xtr, med)
        Xte = np.where(np.isfinite(Xte), Xte, med)
    mdl = _model(kind).fit(Xtr, y[tr])
    return mdl.predict_proba(Xtr)[:, 1], mdl.predict_proba(Xte)[:, 1]


def ml_run(X, labels, rows, kind="gbm") -> dict:
    """labels: {side: race dict} for the T15 / S13 outcome on every bar. Purged walk-forward over BLOCKS blocks."""
    from sklearn.metrics import roc_auc_score
    n = X.shape[0]
    edges = np.linspace(0, len(rows), BLOCKS + 1).astype(int)
    P = {s: np.full(n, np.nan) for s in (1, -1)}
    THR = {s: np.full(n, np.nan) for s in (1, -1)}
    BASE = {s: np.full(n, np.nan) for s in (1, -1)}
    folds = []
    for f in range(1, BLOCKS):
        te = rows[edges[f]:edges[f + 1]]
        tr_all = rows[rows < te[0] - PURGE]
        rec = {"fold": f, "test_from": int(te[0]), "test_to": int(te[-1]), "train_rows": len(tr_all)}
        for s in (1, -1):
            r = labels[s]
            dec = r["win"] | r["loss"]
            tr = tr_all[dec[tr_all]]
            y = r["win"].astype(int)
            p_tr, p_te = _fit_predict(kind, X, y, tr, te)
            P[s][te], THR[s][te] = p_te, float(np.quantile(p_tr, Q_THR))
            BASE[s][te] = float(y[tr].mean())
            m = te[dec[te]]
            pm = P[s][m]
            rec[f"auc_{'long' if s > 0 else 'short'}"] = float(roc_auc_score(y[m], pm)) if len(np.unique(y[m])) == 2 else math.nan
        folds.append(rec)
    oof = rows[edges[1]:]
    out = {"folds": folds, "auc": {}, "brier": {}, "calibration": {}}
    for s in (1, -1):
        nm = "long" if s > 0 else "short"
        r = labels[s]
        dec = r["win"] | r["loss"]
        m = oof[dec[oof]]
        y = r["win"][m].astype(int)
        p = P[s][m]
        out["auc"][nm] = float(roc_auc_score(y, p))
        out["brier"][nm] = {"model": float(np.mean((p - y) ** 2)), "base_rate": float(np.mean((BASE[s][m] - y) ** 2))}
        q = np.quantile(p, np.linspace(0, 1, 11))
        b = np.clip(np.searchsorted(q, p, side="right") - 1, 0, 9)
        out["calibration"][nm] = [{"decile": int(i + 1), "pred": float(p[b == i].mean()), "actual": float(y[b == i].mean()),
                                   "n": int((b == i).sum())} for i in range(10) if (b == i).any()]
    # the trading rule: one position at a time
    entries, sides = [], []
    nxt = -1
    for i in oof:
        if i < nxt:
            continue
        eL, eS = P[1][i] - THR[1][i], P[-1][i] - THR[-1][i]
        if not (np.isfinite(eL) and np.isfinite(eS)) or max(eL, eS) < 0:
            continue
        s = 1 if eL >= eS else -1
        r = labels[s]
        entries.append(i)
        sides.append(s)
        nxt = int(r["j"][i] + min(int(r["k"][i]), PATH_BARS))
    out["entries"] = np.asarray(entries, int)
    out["sides"] = np.asarray(sides, int)
    return out


# ---------------- stages ----------------
def development(rd: str, log=print) -> dict:
    m15, h1 = load(rd, "development")
    idx = m15.index
    c = m15["close"].to_numpy(float)
    t_close = ta.epoch_s(idx).astype(np.int64) + 900
    cost = H.cost_pts(idx)
    scored = idx >= SCORE_FROM
    srows = np.flatnonzero(scored)
    every3 = srows[::3]
    res = {"stage": "development", "bars": len(idx), "window": [str(idx[0]), str(idx[-1])], "trials": {}}
    log(f"[dev] {len(idx)} bars; B13-0 geometry")
    res["B13-0_development"] = geometry(m15, c, every3, 900, PATH_BARS, True)
    rnd = {T: random_rates(m15, idx, c, every3, T, S_STOP) for T in T_ALL}
    res["random"] = {f"T{T:g}": {"long": v["long"], "short": v["short"]} for T, v in rnd.items()}
    # clock rules
    for key, (rows, d, end_t) in clock_rules(m15, scored).items():
        for T in T_ALL:
            r = race(m15, t_close[rows], c[rows], d, T, S_STOP, PATH_BARS, end_t=end_t)
            rl = race(m15, t_close[rows], c[rows], np.ones(len(rows), int), T, S_STOP, PATH_BARS, end_t=end_t)
            rs = race(m15, t_close[rows], c[rows], -np.ones(len(rows), int), T, S_STOP, PATH_BARS, end_t=end_t)
            dl, ds = rl["win"] | rl["loss"], rs["win"] | rs["loss"]
            base_rate = (rl["win"][dl].mean() + rs["win"][ds].mean()) / 2
            st = stats(r, d, cost[rows], T, S_STOP, np.full(len(rows), base_rate))
            if T == T_MAIN:
                st["window_return"] = window_return(m15, rows, d, end_t)
            res["trials"][f"{key} T{T:g}"] = st
        log(f"[dev] {key}: n {res['trials'][f'{key} T15']['n']} rate {res['trials'][f'{key} T15']['rate']:.3f}")
    # the model
    log("[dev] B13-4 features")
    X, names = features(m15, h1)
    labels = {T: {s: race(m15, t_close, c, np.full(len(c), s), T, S_STOP) for s in (1, -1)} for T in (T_MAIN,)}
    lab = labels[T_MAIN]
    rows = srows[(lab[1]["ok"])[srows]]
    res["B13-4_features"] = names
    for kind in ("gbm", "logit"):
        log(f"[dev] B13-4 {kind}")
        mr = ml_run(X, lab, rows, kind)
        e, s = mr.pop("entries"), mr.pop("sides")
        res[f"B13-4_{kind}"] = mr
        for T in T_ALL:
            r = race(m15, t_close[e], c[e], s, T, S_STOP)
            base = np.where(s > 0, rnd[T]["long"], rnd[T]["short"])
            nm = "B13-4" if kind == "gbm" else "B13-4 logit (secondary)"
            res["trials"][f"{nm} T{T:g}"] = stats(r, s, cost[e], T, S_STOP, base)
        log(f"[dev] {kind}: AUC {mr['auc']}; trades {len(e)}")
    prim = {k: res["trials"][f"{k} T15"] for k in ("B13-2a", "B13-2b", "B13-3", "B13-4")}
    p1 = holm({k: v["p_one_sided"] for k, v in prim.items()})
    verdict = {}
    for k, v in prim.items():
        if v["n"] < MIN_N:
            verdict[k] = "INSUFFICIENT"
        else:
            verdict[k] = "PASS" if (p1[k] and math.isfinite(v["t"]) and v["t"] >= 1.645) else "FAIL"
    res["primary"] = {"holm_p1": p1, "verdict": verdict}
    return res


def validation(rd: str, dev_passes: list[str], log=print) -> dict:
    m_dev, h_dev = load(rd, "development")
    m_val, h_val = load(rd, "validation")
    base = pd.concat([m_dev, m_val]).sort_index()
    base = base[~base.index.duplicated(keep="last")]
    h1 = pd.concat([h_dev, h_val]).sort_index()
    h1 = h1[~h1.index.duplicated(keep="last")]
    cfg = config.DEFAULT
    m = b10.make_market(base, h1, "15m", 900)
    F = compute_features(m, cfg)
    idx = pd.DatetimeIndex(F["index"])
    c = np.asarray(F["c"], float)
    t_close = ta.epoch_s(idx).astype(np.int64) + 900
    cost = H.cost_pts(idx)
    log(f"[val] engine run on {len(idx)} bars {idx[0]} -> {idx[-1]}")
    sig = sorted(b10.signals(engine.run(m, cfg, "treatment", F)))
    in_val = idx >= H.VAL[0]
    ii = np.asarray([x[0] for x in sig if in_val[x[0]]], int)
    dd = np.asarray([x[1] for x in sig if in_val[x[0]]], int)
    vrows = np.flatnonzero(in_val)
    vc = m_val["close"].to_numpy(float)
    vrnd = {T: random_rates(m_val, m_val.index, vc, np.arange(0, len(m_val), 3), T, S_STOP) for T in T_ALL}
    res = {"stage": "validation", "bars_validation": int(in_val.sum()), "window": [str(idx[vrows[0]]), str(idx[-1])],
           "signals_in_validation": len(ii), "random": {f"T{T:g}": {"long": v["long"], "short": v["short"]} for T, v in vrnd.items()},
           "trials": {}}
    for T in T_ALL:
        r = race(m_val, t_close[ii], c[ii], dd, T, S_STOP)
        res["trials"][f"B13-1 T{T:g}"] = stats(r, dd, cost[ii], T, S_STOP, np.where(dd > 0, vrnd[T]["long"], vrnd[T]["short"]))
    if dev_passes:
        res["dev_passes_note"] = f"development passes tested here: {dev_passes}"
        vidx = m_val.index
        vt = ta.epoch_s(vidx).astype(np.int64) + 900
        vcost = H.cost_pts(vidx)
        allrows = np.ones(len(m_val), bool)
        for key, (rows, d, end_t) in clock_rules(m_val, allrows).items():
            if key not in dev_passes:
                continue
            r = race(m_val, vt[rows], vc[rows], d, T_MAIN, S_STOP, PATH_BARS, end_t=end_t)
            rl = race(m_val, vt[rows], vc[rows], np.ones(len(rows), int), T_MAIN, S_STOP, PATH_BARS, end_t=end_t)
            rs = race(m_val, vt[rows], vc[rows], -np.ones(len(rows), int), T_MAIN, S_STOP, PATH_BARS, end_t=end_t)
            dl, ds = rl["win"] | rl["loss"], rs["win"] | rs["loss"]
            br = (rl["win"][dl].mean() + rs["win"][ds].mean()) / 2
            res["trials"][f"{key} T15"] = stats(r, d, vcost[rows], T_MAIN, S_STOP, np.full(len(rows), br))
        if "B13-4" in dev_passes:
            raise NotImplementedError("B13-4 validation is written only if it passes development (registration)")
    prim = {"B13-1 T13": res["trials"]["B13-1 T13"], "B13-1 T15": res["trials"]["B13-1 T15"]}
    prim.update({f"{k} T15": res["trials"][f"{k} T15"] for k in dev_passes if f"{k} T15" in res["trials"]})
    p1 = holm({k: v["p_one_sided"] for k, v in prim.items()})
    res["primary"] = {"holm_p1": p1, "verdict": {k: ("INSUFFICIENT" if v["n"] < MIN_N else
                                                     "PASS" if (p1[k] and math.isfinite(v["t"]) and v["t"] >= 1.645) else "FAIL")
                                                 for k, v in prim.items()}}
    return res


def live_geometry(store_dir: str) -> dict:
    from ..data import store as ST
    x5 = sources.trading_week_only(sources.drop_offgrid(ST.load(store_dir, "XAU/USD_5m")))
    c = x5["close"].to_numpy(float)
    rows = np.arange(0, len(x5), 3)
    return {"window": [str(x5.index[0]), str(x5.index[-1])], "bars_5m": len(x5),
            "grid": geometry(x5, c, rows, 300, 288, False)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--stage", choices=("development", "validation", "live"), required=True)
    ap.add_argument("--store", help="the site's store (live stage)")
    ap.add_argument("--dev-results", help="the committed development results (validation stage)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    stamp = datetime.now(timezone.utc).isoformat()
    if a.stage == "development":
        res = development(a.rd)
    elif a.stage == "validation":
        with open(a.dev_results) as fh:
            dev = json.load(fh)
        passes = [k for k, v in dev["primary"]["verdict"].items() if v == "PASS"]
        res = validation(a.rd, passes)
    else:
        res = live_geometry(a.store)
    res = {"registration": REG, "utc": stamp, **res}
    with open(a.out, "w") as f:
        json.dump(_clean(res), f, indent=1, allow_nan=False)
    if a.trials and "trials" in res:
        verdict = res.get("primary", {}).get("verdict", {})
        for nm, s in res["trials"].items():
            rec = {"phase": "B13", "partition": res["stage"], "id": nm, **_clean(s)}
            key = nm if nm in verdict else (nm[:-4] if nm.endswith(" T15") and nm[:-4] in verdict else None)
            if key:
                rec["primary"], rec["verdict"] = key, verdict[key]
            H.log_trial(a.trials, rec)
    print(json.dumps(_clean(res.get("primary", {})), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
