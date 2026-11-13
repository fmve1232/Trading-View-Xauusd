"""Cross-asset relationships of XAU/USD: exploratory, read-only (operator directive 2026-11-13, section 4).

  python3 -I audit/tools/xasset_corr.py <research-data dir> <market-data store dir> <out.json>

Inputs (never committed; vendor data stays on its own branches):
  * <research-data>/TD_XAU_USD_15min   Twelve Data XAU/USD 15-minute bars (branch `research-data`)
  * <store>/XAU_USD_15m                the production store's XAU/USD 15-minute bars (branch `market-data`), used only
                                       after the research series ends
  * <store>/{DX-Y.NYB,_TNX,_GSPC,EURUSD_X,SI_F,GC_F}_60m   Yahoo hourly bars of the engine's cross-asset feeds
  * <store>/_VIX_1d                    Yahoo daily VIX

Sealed data. Amendment 13 seals VALIDATION (2023-01-24 .. 2024-07-01) and the HOLDOUT (2024-07-01 .. 2026-01-01).
Nothing from 2023-01-24 to 2026-01-01 is read into any statistic: every series is cut before use and the cut is asserted.
  * Hourly study: 2026-01-01 onwards (after the holdout), the six hourly feeds.
  * Daily study: the DEVELOPMENT partition (2020-01-24 .. 2023-01-24), VIX (the only daily cross-asset series the store
    holds for that period; B7 covers DXY, yields, real yields, oil, breakevens and COT on the same partition).

Alignment (synchronised observations). XAU's price at time T = the close of the 15-minute bar that ENDS at T. A cross-asset
hourly bar k opening at t_k is used only when the bars before and after it are exactly one hour away (so it is a full
hour, not a session's short last bar); its return ln(C_k / C_{k-1}) spans [t_k, t_k + 1h], and gold's return is taken
over the same span. US10Y (^TNX) bars open at :20; gold has no :20 price, so its span uses the :15 closes (5 minutes
early, stated in the output). Forward windows (predictive tests) start at the first 15-minute mark at least 15 minutes
after the cross-asset bar closed, so a value published with Yahoo's delay (about 10 minutes for CME futures) is known.

Statistics. Pearson and Spearman; moving-block bootstrap 95% intervals (blocks of 24 observations); Newey-West slope
t-tests for predictive regressions; walk-forward out-of-sample R-squared (monthly refits, expanding window) against the
zero forecast and against gold's own last return; directional accuracy (binomial); Holm over every predictive test.
Correlation is description, not causation, and not an edge: an edge needs out-of-sample predictive value after costs.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

VAL0, HOLD1 = pd.Timestamp("2023-01-24 02:00", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")
DEV0, DEV1 = pd.Timestamp("2020-01-24 02:00", tz="UTC"), VAL0
W0 = HOLD1                                   # hourly study: after the holdout
SERIES = {"DXY": "DX-Y.NYB_60m", "US10Y": "_TNX_60m", "SPX": "_GSPC_60m", "EURUSD": "EURUSD_X_60m",
          "SILVER(SI=F)": "SI_F_60m", "GC=F": "GC_F_60m"}
TEXTBOOK = {"DXY": -1, "US10Y": -1, "SPX": 0, "EURUSD": +1, "SILVER(SI=F)": +1, "GC=F": +1}
COST_OZ = 0.26                               # PLAN_COST_PER_LOT 26 per 100 oz: the plan's round-trip cost per ounce
RNG = np.random.default_rng(20261113)
H, M15 = pd.Timedelta(hours=1), pd.Timedelta(minutes=15)


def load(dirpath: str) -> pd.DataFrame:
    fs = sorted(f for f in os.listdir(dirpath) if f.endswith(".csv"))
    df = pd.concat([pd.read_csv(os.path.join(dirpath, f), index_col=0) for f in fs])
    df.index = pd.to_datetime(df.index, utc=True)
    return df[~df.index.duplicated(keep="last")].sort_index()


def sealed_free(idx: pd.DatetimeIndex) -> bool:
    return not ((idx >= VAL0) & (idx < HOLD1)).any()


def block_ci(x, y, fn, L=24, reps=2000):
    n = len(x)
    if n < 3 * L:
        return [math.nan, math.nan]
    starts = np.arange(n - L + 1)
    k = int(math.ceil(n / L))
    out = np.empty(reps)
    for r in range(reps):
        s = RNG.choice(starts, k)
        ii = (s[:, None] + np.arange(L)[None, :]).ravel()[:n]
        out[r] = fn(x[ii], y[ii])
    return [float(np.nanpercentile(out, 2.5)), float(np.nanpercentile(out, 97.5))]


def pear(x, y):
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 else math.nan


def spear(x, y):
    return float(stats.spearmanr(x, y).statistic) if len(x) > 2 else math.nan


def nw_slope(x, y, lags):
    X = np.column_stack([np.ones_like(x), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    XtXi = np.linalg.inv(X.T @ X)
    u = X * e[:, None]
    S = u.T @ u
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        g = u[l:].T @ u[:-l]
        S += w * (g + g.T)
    V = XtXi @ S @ XtXi
    t = b[1] / math.sqrt(V[1, 1]) if V[1, 1] > 0 else math.nan
    return float(b[1]), float(t), float(2 * (1 - stats.norm.cdf(abs(t))))


def holm(ps):
    ps = np.asarray(ps, float)
    order = np.argsort(ps)
    adj = np.empty_like(ps)
    m, run = len(ps), 0.0
    for r, i in enumerate(order):
        run = max(run, (m - r) * ps[i])
        adj[i] = min(run, 1.0)
    return adj


def xau_price(x15: pd.DataFrame) -> pd.Series:
    """Close of each 15-minute bar, indexed by the time the bar ENDS."""
    return pd.Series(x15["close"].to_numpy(float), index=x15.index + M15)


def p_at(px: pd.Series, t: pd.DatetimeIndex) -> np.ndarray:
    """Gold's price at each time t: the last bar ending at or before t, if it ended within 15 minutes of t."""
    k = px.index.searchsorted(t, side="right") - 1
    ok = k >= 0
    kk = np.where(ok, k, 0)
    when = px.index[kk]
    v = px.to_numpy()[kk]
    good = ok & ((t - when) < M15) & ((t - when) >= pd.Timedelta(0))
    return np.where(good, v, np.nan)


def ceil15(t: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return t.ceil("15min")


def spans(df: pd.DataFrame) -> pd.DataFrame:
    """Full-hour bars on the series' own minute grid: start, end, log return."""
    grid = df.index.minute.value_counts().idxmax()
    d = df[df.index.minute == grid]
    t = d.index
    c = d["close"].to_numpy(float)
    prev_ok = np.r_[False, (t[1:] - t[:-1]) == H]
    next_ok = np.r_[(t[1:] - t[:-1]) == H, False]
    keep = prev_ok & next_ok & (c > 0) & np.r_[False, c[:-1] > 0]
    r = np.r_[np.nan, np.log(c[1:] / c[:-1])]
    out = pd.DataFrame({"start": t, "end": t + H, "r": r})[keep]
    out.attrs["grid"] = int(grid)
    return out


def ewma_sd(r: np.ndarray, lam=0.94, warm=24) -> np.ndarray:
    """Trailing EWMA standard deviation using only earlier observations."""
    out = np.full(len(r), np.nan)
    v = np.nanvar(r[:warm]) if len(r) > warm else np.nan
    for i in range(len(r)):
        if i >= warm:
            out[i] = math.sqrt(v)
        if not math.isnan(r[i]):
            v = lam * v + (1 - lam) * r[i] ** 2 if not math.isnan(v) else r[i] ** 2
    return out


def session(h: int) -> str:
    return "Asia 22-07" if (h >= 22 or h < 7) else "London 07-12" if h < 12 else "London/NY 12-16" if h < 16 else "NY 16-22"


def walk_forward(dfp: pd.DataFrame, ycol: str, xcols: list[str], min_months=3) -> dict:
    """Monthly refits on all earlier months; OOS forecasts of the next month."""
    m = dfp["start"].dt.tz_convert(None).dt.to_period("M")
    months = sorted(m.unique())
    preds = np.full(len(dfp), np.nan)
    for j in range(min_months, len(months)):
        tr, te = (m < months[j]).to_numpy(), (m == months[j]).to_numpy()
        X = np.column_stack([np.ones(tr.sum())] + [dfp.loc[tr, c].to_numpy() for c in xcols])
        b, *_ = np.linalg.lstsq(X, dfp.loc[tr, ycol].to_numpy(), rcond=None)
        Xt = np.column_stack([np.ones(te.sum())] + [dfp.loc[te, c].to_numpy() for c in xcols])
        preds[te] = Xt @ b
    ok = ~np.isnan(preds)
    return {"pred": preds, "ok": ok}


def oos_block(dfp: pd.DataFrame, x: str, lag_own: str, y: str, lags: int) -> dict:
    """Three walk-forward models on the same OOS rows: drift (intercept only), own (gold's own last hour) and full
    (own + the cross-asset move). The cross-asset variable is useful only if FULL beats OWN; beating 50% is not enough
    (a fitted drift alone beats 50% whenever gold moved one way more often)."""
    mods = {"drift": walk_forward(dfp, y, []), "own": walk_forward(dfp, y, [lag_own]), "full": walk_forward(dfp, y, [lag_own, x])}
    ok = mods["drift"]["ok"] & mods["own"]["ok"] & mods["full"]["ok"]
    yy = dfp[y].to_numpy()[ok]
    px = dfp["p_fwd0"].to_numpy()[ok]
    nz = yy != 0
    out = {"n_oos": int(ok.sum()), "up_share": float(np.mean(yy[nz] > 0)), "cost_usd_per_oz": COST_OZ}
    err = {}
    for k, m_ in mods.items():
        pf = m_["pred"][ok]
        err[k] = (yy - pf) ** 2
        out[f"hit_{k}"] = float(np.mean(np.sign(pf[nz]) == np.sign(yy[nz])))
        out[f"usd_per_oz_{k}"] = float(np.mean(np.sign(pf) * (np.exp(yy) - 1) * px))
    sse0 = float(np.sum(yy ** 2))
    out["oos_r2_full_vs_zero"] = 1 - float(err["full"].sum()) / sse0
    out["oos_r2_full_vs_own"] = 1 - float(err["full"].sum()) / float(err["own"].sum())
    d = err["own"] - err["full"]                         # > 0 when the cross-asset variable helps
    dm = d - d.mean()
    lr = float(np.sum(dm ** 2)) + 2 * sum((1 - l / (lags + 1)) * float(np.sum(dm[l:] * dm[:-l])) for l in range(1, lags + 1))
    se = math.sqrt(lr) / len(d) if lr > 0 else math.nan
    out["dm_t_full_better"] = float(d.mean() / se) if se and se > 0 else math.nan
    out["dm_p_one_sided"] = float(1 - stats.norm.cdf(out["dm_t_full_better"])) if not math.isnan(out["dm_t_full_better"]) else math.nan
    out["hit_gain_full_minus_own"] = out["hit_full"] - out["hit_own"]
    return out


def hourly_study(px: pd.Series, store: str) -> dict:
    out = {}
    tests = []                          # (series, horizon, p) for Holm
    vix = load(os.path.join(store, "_VIX_1d"))["close"]
    for name, folder in SERIES.items():
        df = load(os.path.join(store, folder))
        df = df[df.index >= W0 - pd.Timedelta(days=3)]
        sp = spans(df)
        sp = sp[sp["start"] >= W0].reset_index(drop=True)
        assert sealed_free(pd.DatetimeIndex(sp["start"])), name
        grid = df.index.minute.value_counts().idxmax()
        g0, g1 = p_at(px, pd.DatetimeIndex(sp["start"])), p_at(px, pd.DatetimeIndex(sp["end"]))
        sp["g"] = np.log(g1 / g0)
        f0 = ceil15(pd.DatetimeIndex(sp["end"]) + M15)
        sp["p_fwd0"] = p_at(px, f0)
        sp["g_f1"] = np.log(p_at(px, f0 + H) / sp["p_fwd0"])
        sp["g_f4"] = np.log(p_at(px, f0 + 4 * H) / sp["p_fwd0"])
        sp["g_lag"] = np.log(sp["p_fwd0"] / p_at(px, f0 - H))      # gold's own last hour, known at the forecast time
        sp = sp.dropna(subset=["r", "g"]).reset_index(drop=True)
        x, y = sp["r"].to_numpy(), sp["g"].to_numpy()
        res = {"store_series": folder, "minute_grid": f":{grid:02d}", "gold_span_note":
               "gold uses :15 closes for :20 bars (5 min early)" if grid % 15 else "exact",
               "first": str(sp["start"].iloc[0])[:16], "last": str(sp["start"].iloc[-1])[:16], "n_1h": len(sp),
               "textbook_sign": TEXTBOOK[name]}
        res["pearson_1h"], res["spearman_1h"] = pear(x, y), spear(x, y)
        res["pearson_1h_ci95"] = block_ci(x, y, pear)
        sx, sy = ewma_sd(x), ewma_sd(y)
        ok = ~np.isnan(sx) & ~np.isnan(sy) & (sx > 0) & (sy > 0)
        res["pearson_1h_vol_adjusted"] = pear(x[ok] / sx[ok], y[ok] / sy[ok])
        # observation windows: 4h blocks of 4 contiguous matched hours, and UTC days (sums of matched hours)
        sp["blk4"] = ((sp["start"] - sp["start"].iloc[0]) // (4 * H)).astype(int)
        b4 = sp.groupby("blk4").agg(r=("r", "sum"), g=("g", "sum"), k=("r", "size"))
        b4 = b4[b4["k"] == 4]
        dd = sp.groupby(sp["start"].dt.floor("D")).agg(r=("r", "sum"), g=("g", "sum"), k=("r", "size"))
        dd = dd[dd["k"] >= 4]
        res["pearson_4h"], res["n_4h"] = pear(b4["r"].to_numpy(), b4["g"].to_numpy()), len(b4)
        res["pearson_4h_ci95"] = block_ci(b4["r"].to_numpy(), b4["g"].to_numpy(), pear, L=6)
        res["pearson_daily"], res["n_daily"] = pear(dd["r"].to_numpy(), dd["g"].to_numpy()), len(dd)
        res["pearson_daily_ci95"] = block_ci(dd["r"].to_numpy(), dd["g"].to_numpy(), pear, L=5)
        # rolling windows
        for W in (120, 500):
            if len(sp) > W + 10:
                rr = pd.Series(x).rolling(W).corr(pd.Series(y)).dropna().to_numpy()
                full_sign = np.sign(res["pearson_1h"])
                res[f"rolling_{W}"] = {"q05": float(np.quantile(rr, .05)), "median": float(np.median(rr)), "q95": float(np.quantile(rr, .95)),
                                        "share_opposite_sign": float(np.mean(np.sign(rr) == -full_sign)),
                                        "share_abs_below_0.1": float(np.mean(np.abs(rr) < 0.1))}
        # monthly stability: Cochran's Q on Fisher z (descriptive; ignores serial dependence)
        mon = []
        for per, g_ in sp.groupby(sp["start"].dt.tz_convert(None).dt.to_period("M")):
            if len(g_) >= 30:
                mon.append((str(per), len(g_), pear(g_["r"].to_numpy(), g_["g"].to_numpy())))
        z = np.array([np.arctanh(np.clip(r_, -0.999, 0.999)) for _, _, r_ in mon])
        w = np.array([n_ - 3 for _, n_, _ in mon], float)
        zbar = np.sum(w * z) / np.sum(w)
        Q = float(np.sum(w * (z - zbar) ** 2))
        res["monthly"] = [{"month": m_, "n": n_, "r": r_} for m_, n_, r_ in mon]
        res["monthly_heterogeneity"] = {"Q": Q, "df": len(mon) - 1, "p": float(1 - stats.chi2.cdf(Q, len(mon) - 1))}
        # regimes: gold's trailing realised volatility (past only), session, VIX level (expanding median of past closes)
        gl = pd.Series(sp["g_lag"].to_numpy())
        rv = gl.abs().rolling(24, min_periods=12).mean().shift(1).to_numpy()
        qs = np.nanquantile(rv, [1 / 3, 2 / 3])
        reg = {}
        for lab, mask in (("vol low", rv <= qs[0]), ("vol mid", (rv > qs[0]) & (rv <= qs[1])), ("vol high", rv > qs[1])):
            mask = mask & ~np.isnan(rv)
            reg[lab] = {"n": int(mask.sum()), "r": pear(x[mask], y[mask])}
        ses = sp["start"].dt.hour.map(session)
        for lab in ("Asia 22-07", "London 07-12", "London/NY 12-16", "NY 16-22"):
            mask = (ses == lab).to_numpy()
            if mask.sum() >= 30:
                reg[lab] = {"n": int(mask.sum()), "r": pear(x[mask], y[mask])}
        vday = vix.index.normalize()
        vser = pd.Series(vix.to_numpy(float), index=vday)
        prev_vix = vser.reindex(sp["start"].dt.normalize() - pd.Timedelta(days=1), method="ffill").to_numpy()
        med = vser.expanding().median().reindex(sp["start"].dt.normalize() - pd.Timedelta(days=1), method="ffill").to_numpy()
        for lab, mask in (("VIX above its past median", prev_vix > med), ("VIX at or below", prev_vix <= med)):
            mask = mask & ~np.isnan(prev_vix) & ~np.isnan(med)
            reg[lab] = {"n": int(mask.sum()), "r": pear(x[mask], y[mask])}
        res["regimes"] = reg
        # predictive: this hour's cross-asset move -> gold's next 1h / 4h, starting >= 15 min after the bar closed
        pred = {}
        for hz, col, lags in (("1h", "g_f1", 1), ("4h", "g_f4", 5)):
            dfp = sp.dropna(subset=[col, "g_lag", "p_fwd0"]).reset_index(drop=True)
            slope, t, p = nw_slope(dfp["r"].to_numpy(), dfp[col].to_numpy(), lags)
            pred[hz] = {"n": len(dfp), "pearson_lead": pear(dfp["r"].to_numpy(), dfp[col].to_numpy()), "nw_slope": slope, "nw_t": t, "p": p,
                        **oos_block(dfp, "r", "g_lag", col, lags)}
            tests.append((name, hz, p))
            tests.append((name, hz + "_dm", pred[hz]["dm_p_one_sided"]))
        res["predictive"] = pred
        out[name] = res
    adj = holm([p for _, _, p in tests])
    for (name, hz, _), a in zip(tests, adj):
        if hz.endswith("_dm"):
            out[name]["predictive"][hz[:-3]]["dm_p_holm"] = float(a)
        else:
            out[name]["predictive"][hz]["p_holm"] = float(a)
    out["_holm_family_size"] = len(tests)
    return out


def daily_dev(px: pd.Series, store: str) -> dict:
    """DEVELOPMENT partition only: gold at 16:15 New York (the VIX close) vs VIX, same day and next day."""
    vix = load(os.path.join(store, "_VIX_1d"))["close"]
    days = pd.DatetimeIndex(sorted(set(vix.index.normalize())))
    days = days[(days >= DEV0.normalize()) & (days < DEV1.normalize())]
    t = pd.DatetimeIndex([pd.Timestamp(d.date()).tz_localize("America/New_York") + pd.Timedelta(hours=16, minutes=15) for d in days]).tz_convert("UTC")
    assert (t < VAL0).all()
    g = p_at(px, t)
    v = vix.reindex(days).to_numpy(float)
    df = pd.DataFrame({"t": t, "g": g, "v": v}).dropna()
    df = df[df["t"] >= DEV0].reset_index(drop=True)
    df["rg"], df["rv"] = np.log(df["g"]).diff(), np.log(df["v"]).diff()
    df["rg_next"] = df["rg"].shift(-1)
    a = df.dropna(subset=["rg", "rv"])
    b = df.dropna(subset=["rv", "rg_next"])
    slope, tt, p = nw_slope(b["rv"].to_numpy(), b["rg_next"].to_numpy(), 1)
    yearly = [{"year": int(y_), "n": len(q), "r": pear(q["rv"].to_numpy(), q["rg"].to_numpy())} for y_, q in a.groupby(a["t"].dt.year)]
    rr = pd.Series(a["rv"].to_numpy()).rolling(60).corr(pd.Series(a["rg"].to_numpy())).dropna().to_numpy()
    return {"partition": "development 2020-01-24..2023-01-24", "n_days": len(a), "first": str(a["t"].iloc[0])[:10], "last": str(a["t"].iloc[-1])[:10],
            "pearson_same_day": pear(a["rv"].to_numpy(), a["rg"].to_numpy()), "spearman_same_day": spear(a["rv"].to_numpy(), a["rg"].to_numpy()),
            "pearson_same_day_ci95": block_ci(a["rv"].to_numpy(), a["rg"].to_numpy(), pear, L=5),
            "rolling_60d": {"q05": float(np.quantile(rr, .05)), "median": float(np.median(rr)), "q95": float(np.quantile(rr, .95)),
                            "share_negative": float(np.mean(rr < 0))},
            "yearly": yearly,
            "next_day": {"n": len(b), "pearson": pear(b["rv"].to_numpy(), b["rg_next"].to_numpy()), "nw_slope": slope, "nw_t": tt, "p": p}}


def main():
    rd, store, out = sys.argv[1:4]
    x15 = load(os.path.join(rd, "TD_XAU_USD_15min"))
    s15 = load(os.path.join(store, "XAU_USD_15m"))
    ov = x15.index.intersection(s15.index)
    diff = (x15.loc[ov, "close"] - s15.loc[ov, "close"]).abs()
    x = pd.concat([x15, s15[s15.index > x15.index[-1]]]).sort_index()
    x = x[(x.index < VAL0) | (x.index >= HOLD1 - pd.Timedelta(days=3))]
    px = xau_price(x)
    res = {"generated_from": {"research_xau_15m": [str(x15.index[0])[:16], str(x15.index[-1])[:16], len(x15)],
                              "store_xau_15m_after": [str(s15.index[0])[:16], str(s15.index[-1])[:16], len(s15)]},
           "overlap_check": {"bars": len(ov), "max_abs_close_diff": float(diff.max()) if len(ov) else None,
                             "share_differing_over_1c": float((diff > 0.01).mean()) if len(ov) else None},
           "sealed_ranges_excluded": [str(VAL0), str(HOLD1)]}
    res["hourly_2026"] = hourly_study(px, store)
    res["daily_dev_vix"] = daily_dev(px, store)
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(json.dumps({k: res[k] for k in ("generated_from", "overlap_check")}, indent=1))


if __name__ == "__main__":
    main()
