"""Vectorised (stateless) part of the Master engine: every series that depends only on bars.

Each block cites the Pine Master section it ports. Stateful logic (structure, zones, the
analog engine, scoring, gates) lives in engine.py, which consumes these arrays.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import ta
from .config import Config
from .data.market import Market, align, htf_expr
from .sessions import calendar

MACRO_STALE_DAYS = 5.0   # a macro value older than this (weekends + a holiday) is invalid


def _valid_age(open_epoch: np.ndarray, close_epoch: np.ndarray) -> np.ndarray:
    return (~np.isnan(open_epoch)) & ((close_epoch - open_epoch) <= MACRO_STALE_DAYS * 86400)


def _t_inv(p: float, df: int) -> float:
    q = 1.0 - p if p > 0.5 else p
    t = math.sqrt(-2.0 * math.log(q))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    z = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    z = z if p > 0.5 else -z
    if df > 2:
        z2 = z * z
        z3 = z2 * z
        z5 = z3 * z2
        z = z + (z3 + z) / (4.0 * df) + (5.0 * z5 + 16.0 * z3 + 3.0 * z) / (96.0 * df * df)
    return z


def compute(m: Market, cfg: Config) -> dict:
    b = m.base
    n = len(b)
    F: dict = {"n": n, "index": b.index}
    o = b["open"].to_numpy(float)
    h = b["high"].to_numpy(float)
    l = b["low"].to_numpy(float)
    c = b["close"].to_numpy(float)
    v = b["volume"].to_numpy(float)
    vol_missing = np.isnan(v)
    v = np.where(vol_missing, 0.0, v)   # documented: missing futures volume counts as 0
    F.update(o=o, h=h, l=l, c=c, v=v, vol_imputed=int(vol_missing.sum()))
    tf_sec = m.tf_sec
    close_t = m.close_times
    close_epoch = ta.epoch_s(close_t).astype(float)
    open_epoch = ta.epoch_s(b.index).astype(float)
    F["open_epoch"] = open_epoch
    F["close_epoch"] = close_epoch

    cal = calendar(b.index)
    F["cal"] = cal

    # ---- core indicators ----
    F["ema20"] = ta.ema(c, cfg.ema20_len)
    F["ema100"] = ta.ema(c, cfg.ema100_len)
    F["ema200"] = ta.ema(c, cfg.ema200_len)
    atr = ta.atr(h, l, c, cfg.atr_len)
    F["atr"] = atr
    dip, dim, adx = ta.dmi(h, l, c, cfg.adx_len, cfg.adx_len)
    F["diplus"], F["diminus"], F["adx"] = dip, dim, adx

    adx_gate = np.zeros(n, dtype=bool)
    g = False
    for i in range(n):
        a = adx[i]
        g = (a > cfg.adx_threshold - 2) if g else (a > cfg.adx_threshold)
        adx_gate[i] = g
    F["adx_gate"] = adx_gate

    hlc3 = (h + l + c) / 3.0
    new_day = cal["crossed_day"].to_numpy()
    new_week = cal["crossed_week"].to_numpy()
    new_month = cal["crossed_month"].to_numpy()
    vwap = ta.anchored_vwap(hlc3, v, new_day)
    F["vwap"] = vwap
    F["wvwap"] = ta.anchored_vwap(hlc3, v, new_week)
    F["mvwap"] = ta.anchored_vwap(hlc3, v, new_month)
    vsd = ta.stdev(c - vwap, 20)
    F["vwap_up2"] = vwap + vsd * 2.0
    F["vwap_lo2"] = vwap - vsd * 2.0
    F["vwap_reject_bull"] = (l <= F["vwap_lo2"]) & (c > vwap)
    bb_basis = ta.sma(c, 20)
    bb_dev = ta.stdev(c, 20) * 2.0
    F["bb_basis"], F["bb_dev"] = bb_basis, bb_dev
    F["rsi"] = ta.rsi(c, cfg.rsi_len)
    vol_sma20 = ta.sma(v, 20)
    F["vol_sma20"] = vol_sma20
    F["high_volume"] = v > vol_sma20
    c1 = ta.shift(c, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_ret = np.where(np.abs(np.nan_to_num(c1, nan=c)) > 1e-10, c / np.where(np.isnan(c1), c, c1), 0.0) - 1.0
    clamp_w = np.clip(np.nan_to_num(ta.shift(ta.stdev(raw_ret, 100), 1), nan=0.0) * 6.0, 0.002, 0.05)
    gold_ret = np.clip(raw_ret, -clamp_w, clamp_w)
    F["gold_ret"] = gold_ret

    # ---- HTF trend scores ----
    htf_scores = {}
    for key, avail in (("5", tf_sec < 300), ("15", tf_sec < 900), ("60", tf_sec < 3600),
                       ("240", tf_sec < 14400), ("D", tf_sec < 86400)):
        if not avail or m.htf.get(key) is None or len(m.htf[key]) == 0:
            htf_scores[key] = np.full(n, 50.0)
            continue
        ex = htf_expr(m.htf[key])
        al = align(close_t, ex, ["c1", "e20", "e100", "e200"])
        hc, e20, e100, e200 = al["c1"], al["e20"], al["e100"], al["e200"]
        sc = ((~np.isnan(e200)) & (hc > e200)) * 40 + ((~np.isnan(e20)) & (~np.isnan(e100)) & (e20 > e100)) * 40 + ((~np.isnan(e20)) & (hc > e20)) * 20
        htf_scores[key] = np.where(np.isnan(hc), 50.0, sc.astype(float))
    F["htf_scores"] = htf_scores
    hb = {k: s >= 60 for k, s in htf_scores.items()}
    hs = {k: s <= 40 for k, s in htf_scores.items()}
    F["htf_bull"], F["htf_bear"] = hb, hs
    F["htf_align_long"] = hb["15"].astype(int) + hb["60"] + hb["240"] + hb["D"]
    F["htf_align_short"] = hs["15"].astype(int) + hs["60"] + hs["240"] + hs["D"]
    F["htf_bull_gate"] = F["htf_align_long"] >= 2
    F["htf_bear_gate"] = F["htf_align_short"] >= 2
    F["htf_full_long"] = hb["5"].astype(int) + hb["15"] + hb["60"] + hb["240"] + hb["D"]
    F["htf_full_short"] = hs["5"].astype(int) + hs["15"] + hs["60"] + hs["240"] + hs["D"]

    # ---- adaptive ATR, regime engine ----
    atr_tr = ta.atr(h, l, c, 7)
    atr_rg = ta.atr(h, l, c, 21)
    regime_strength = np.clip((adx - (cfg.adx_threshold - 5)) / 10.0, 0.0, 1.0)
    F["regime_strength"] = np.nan_to_num(regime_strength, nan=0.0)
    raw_aatr = (atr_rg * (1.0 - regime_strength) + atr_tr * regime_strength) if cfg.show_adaptive_atr else atr
    tr_na = ta.tr(h, l, c, handle_na=False)
    aatr = np.fmax(np.where(np.isnan(raw_aatr), tr_na, raw_aatr), c * 0.0001)
    F["aatr"] = aatr
    atr_pct = ta.percentrank(aatr, 50)
    F["atr_pct"] = atr_pct
    F["var_short"] = ta.variance(gold_ret, 10)
    F["var_long"] = ta.variance(gold_ret, 50)
    gr1 = ta.shift(gold_ret, 1)
    ret_mean100 = ta.sma(gr1, 100)
    ret_std100 = ta.stdev(gr1, 100)
    with np.errstate(divide="ignore", invalid="ignore"):
        rz_raw = np.where(ret_std100 > 0.0, (gold_ret - ret_mean100) / ret_std100, 0.0)
    F["ret_z_raw"] = rz_raw

    bb_width_rel = np.where(bb_basis > 0, bb_dev / bb_basis, 0.0)
    bb_width_pct = ta.percentrank(bb_width_rel, 100)
    adx_pct = ta.percentrank(adx, 200)
    atr_sma100 = ta.sma(aatr, 100)
    news = cal["news_window"].to_numpy()
    reg_abn = news | (np.abs(rz_raw) > 3.0) | ((atr_sma100 > 0) & (aatr > atr_sma100 * 2.5))
    reg_cmp = ~reg_abn & (bb_width_pct <= 20) & (adx < 20)
    bbw3 = np.nan_to_num(ta.shift(bb_width_pct, 3), nan=50.0)
    adx5 = ta.shift(adx, 5)
    adx5 = np.where(np.isnan(adx5), adx, adx5)
    reg_exp = ~reg_abn & ~reg_cmp & (((bb_width_pct > 25) & (bbw3 <= 20)) | ((atr_pct >= 80) & (adx > adx5)))
    reg_str = ~reg_abn & ~reg_cmp & ~reg_exp & (adx > cfg.adx_threshold) & (adx_pct >= 70)
    reg_weak = ~reg_abn & ~reg_cmp & ~reg_exp & ~reg_str & (adx > cfg.adx_threshold)
    F.update(reg_abnormal=reg_abn, reg_compression=reg_cmp, reg_expansion=reg_exp,
             reg_strong=reg_str, reg_weak=reg_weak)
    F["mkt_regime"] = np.where(reg_abn, "ABNORMAL", np.where(reg_cmp, "COMPRESS", np.where(reg_exp, "EXPANSION",
                                np.where(reg_str, "STRONG TR", np.where(reg_weak, "WEAK TR", "RANGE")))))
    F["vol_tag"] = np.where(atr_pct >= 80, "HV", np.where(atr_pct <= 20, "LV", "NV"))
    ap = np.nan_to_num(atr_pct, nan=0.0)   # Pine: a na percentile makes the product na; clamp takes over
    sl_mult = np.where(reg_abn, 2.0, np.where(reg_exp, 1.8, np.where(reg_str, 1.5, np.where(reg_weak, 1.4, np.where(reg_cmp, 1.1, 1.2))))) * (0.9 + ap / 500.0)
    F["reg_sl_mult"] = np.clip(sl_mult, 1.0, 2.2)
    F["reg_bos_mult"] = np.where(atr_pct >= 80, 1.20, np.where(atr_pct <= 20, 0.85, 1.0))
    F["reg_liq_mult"] = np.where(atr_pct >= 80, 1.30, np.where(atr_pct <= 20, 0.80, 1.0))
    F["reg_horizon_mult"] = np.where(reg_cmp | reg_abn, 0.7, np.where(reg_exp | reg_str, 1.2, 1.0))
    F["reg_size_mult"] = np.where(reg_abn, 0.5, np.where(atr_pct >= 80, 0.75, 1.0))
    F["reg_conf_cap"] = np.where(reg_abn, 60, 100)

    # ---- Cornish-Fisher z (moments over 100 bars of goldRet[1]) ----
    r = gr1
    m2 = ta.sma(r * r, 100) * 100.0
    m3 = ta.sma(r * r * r, 100) * 100.0
    m4 = ta.sma(r ** 4, 100) * 100.0
    nn = 100.0
    mu = ret_mean100
    var_ = np.maximum(m2 / nn - mu * mu, 0.000001)
    sd = np.sqrt(var_)
    cf_valid = np.arange(n) > 100
    skew = np.where(cf_valid, (m3 / nn - 3.0 * mu * m2 / nn + 2.0 * mu ** 3) / sd ** 3, 0.0)
    kurt = np.where(cf_valid, (m4 / nn - 4.0 * mu * m3 / nn + 6.0 * mu * mu * m2 / nn - 3.0 * mu ** 4) / (var_ * var_) - 3.0, 0.0)
    F["ret_skew"], F["ret_kurt"] = skew, kurt
    skc = np.clip(skew, -1.0, 1.0)
    cfk = np.clip(kurt, -1.0, 3.0)
    rz = rz_raw.copy()
    ok = cf_valid & (np.abs(skew) < 1.5) & (np.abs(kurt) < 7.0) & ~np.isnan(rz_raw)
    w = np.where(ok, rz_raw, 0.0)   # iterate only where the expansion is used
    with np.errstate(over="ignore", invalid="ignore"):
        w = _cf_iterate(w, np.where(ok, rz_raw, 0.0), skc, cfk)
    # A Newton step can diverge on a pathological moment set; fall back to the raw z there.
    F["ret_z"] = np.where(ok & np.isfinite(w), w, rz)
    return _rest(F, m, cfg, c, h, l, o, v, c1, aatr, atr, adx, dip, dim, vwap, bb_basis, bb_dev,
                 gold_ret, cal, close_t, close_epoch, open_epoch, tf_sec, atr_pct)


def _cf_iterate(w, target, skc, cfk):
    for _ in range(6):
        w2 = w * w
        w3 = w2 * w
        q = w + (w2 - 1.0) * skc / 6.0 + (w3 - 3.0 * w) * cfk / 24.0 - (2.0 * w3 - 5.0 * w) * skc * skc / 36.0
        dq = 1.0 + w * skc / 3.0 + (3.0 * w2 - 3.0) * cfk / 24.0 - (6.0 * w2 - 5.0) * skc * skc / 36.0
        w = w - (q - target) / np.maximum(dq, 0.1)
    return w


def _rest(F, m, cfg, c, h, l, o, v, c1, aatr, atr, adx, dip, dim, vwap, bb_basis, bb_dev,
          gold_ret, cal, close_t, close_epoch, open_epoch, tf_sec, atr_pct):
    n = F["n"]

    with np.errstate(divide="ignore", invalid="ignore"):
        dv = np.where(aatr > 0, (c - vwap) / aatr, 0.0)
        d20 = np.where(aatr > 0, (c - F["ema20"]) / aatr, 0.0)
        d100 = np.where(aatr > 0, (c - F["ema100"]) / aatr, 0.0)
        d200 = np.where(aatr > 0, (c - F["ema200"]) / aatr, 0.0)
    F["dist_vwap_atr"] = dv
    F["mr_composite"] = np.clip(dv * 30.0 + d20 * 25.0 + d100 * 25.0 + d200 * 20.0 + F["ret_z"] * 15.0, -100, 100)
    F["regime_trending"] = adx > cfg.adx_threshold
    F["regime_ranging"] = (adx <= cfg.adx_threshold) & (adx > 15)
    F["regime_dead"] = adx <= 15

    # ---- sessions ----
    rs = F["regime_strength"]
    kz = cal["in_killzone"].to_numpy()
    lon = cal["in_london"].to_numpy()
    nyf = cal["in_ny"].to_numpy()
    asia = cal["in_asian"].to_numpy()
    lkz = cal["in_london_kz"].to_numpy()
    lfix = cal["in_london_fix_kz"].to_numpy()
    nykz = cal["in_ny_kz"].to_numpy()
    lcl = cal["in_london_close_kz"].to_numpy()
    sq = np.where(kz, np.trunc(30.0 + rs * 20.0), np.where(lon | nyf, 25, np.where(asia, 10, 0)))
    sq = sq + np.where(lfix, np.trunc(25.0 - rs * 10.0), 0)
    sq = sq + np.where(nykz, np.trunc(10.0 + rs * 10.0), 0)
    sq = sq + np.where(~asia | lkz, 10, 0)
    sq = sq + np.where(lon & ~lkz, np.trunc(10.0 - rs * 5.0), 0)
    F["session_quality"] = np.minimum(np.floor(sq / 80.0 * 100.0 + 0.5), 100).astype(int)
    F["session_label"] = np.where(kz, np.where(lfix, "LON-FIX", np.where(lkz, "LON-KZ", np.where(lcl, "LON-CL", np.where(nykz, "NY-KZ", "KZ")))),
                                  np.where(lon, "LONDON", np.where(nyf, "NY", np.where(asia, "ASIAN", "OFF"))))
    F["session_conf_mult"] = np.where(kz, np.where(nykz, 1.15, np.where(lkz, 1.10, 1.05)),
                                      np.where(lon, 1.05, np.where(nyf, 1.08, np.where(asia, 0.92, 1.0))))
    F["sess_spread"] = np.where(kz, max(0.18, cfg.spread_cost), np.where(nyf, max(0.22, cfg.spread_cost),
                                np.where(lon, max(0.30, cfg.spread_cost), max(0.50, cfg.spread_cost))))

    # ---- macro feeds ----
    def ext(df, kind):
        cols = {}
        if df is None or len(df) == 0:
            return None
        cc = df["close"].to_numpy(float)
        x1 = ta.shift(cc, 1)
        cols["c1"] = x1
        cols["e10"] = ta.ema(x1, 10)
        cols["e20"] = ta.ema(x1, 20)
        if kind in ("dxy", "eur"):
            cols["roc"] = ta.roc(x1, cfg.dxy_roc_len)
        if kind == "yld":
            cols["roc"] = ta.roc(x1, cfg.zn_roc_len)
        if kind in ("dxy", "slv"):
            cols["rsi"] = ta.rsi(x1, cfg.rsi_len)
        if kind == "gc":
            vv = df["volume"].to_numpy(float)
            v1 = ta.shift(vv, 1)
            cols["v1"] = v1
            cols["vavg"] = ta.sma(v1, 20)
            cols["t1"] = ta.shift(ta.epoch_s(df.index).astype(float), 1)
        return pd.DataFrame(cols, index=df.index)

    def feed(name, df, kind):
        e = ext(df, kind)
        if e is None:
            F[f"{name}_ok"] = np.zeros(n, dtype=bool)
            for k in ("c1", "e10", "e20", "roc", "rsi"):
                F[f"{name}_{k}"] = np.full(n, np.nan)
            return
        al = align(close_t, e, list(e.columns))
        for k in e.columns:
            F[f"{name}_{k}"] = al[k]
        F[f"{name}_ok"] = _valid_age(al["_open"], close_epoch) & ~np.isnan(al["c1"])
        F[f"{name}_open"] = al["_open"]

    feed("dxy", m.ext_macro.get("dxy"), "dxy")
    feed("yld", m.ext_macro.get("us10y"), "yld")
    feed("slv", m.ext_chart.get("silver"), "slv")
    feed("eur", m.ext_chart.get("eurusd"), "eur")
    feed("spx", m.ext_chart.get("spx"), "spx")
    tips_df = m.ext_macro.get("us10y")
    if cfg.tips_source == "fred_dfii10" and m.ext_daily.get("DFII10") is not None:
        tips_df = m.ext_daily["DFII10"]
    feed("tips", tips_df, "tips")
    feed("gc", m.ext_chart.get("gc"), "gc")

    dxy_valid = F["dxy_ok"] & ~np.isnan(F["dxy_e10"]) & ~np.isnan(F["dxy_e20"])
    yld_valid = F["yld_ok"] & ~np.isnan(F["yld_e10"]) & ~np.isnan(F["yld_e20"])
    slv_valid = F["slv_ok"] & ~np.isnan(F["slv_e20"])
    eur_valid = F["eur_ok"] & ~np.isnan(F["eur_e10"]) & ~np.isnan(F["eur_e20"])
    spx_valid = F["spx_ok"] & ~np.isnan(F["spx_e10"]) & ~np.isnan(F["spx_e20"])
    tips_valid = F["tips_ok"] & ~np.isnan(F["tips_e10"]) & ~np.isnan(F["tips_e20"])
    F.update(dxy_valid=dxy_valid, yld_valid=yld_valid, slv_valid=slv_valid, eur_valid=eur_valid,
             spx_valid=spx_valid, tips_valid=tips_valid)
    dxc, yc, sc_, ec, pc, tc = F["dxy_c1"], F["yld_c1"], F["slv_c1"], F["eur_c1"], F["spx_c1"], F["tips_c1"]
    dxy_bull = dxy_valid & (dxc > F["dxy_e10"]) & (F["dxy_e10"] > F["dxy_e20"])
    dxy_bear = dxy_valid & (dxc < F["dxy_e10"]) & (F["dxy_e10"] < F["dxy_e20"])
    y_up = yld_valid & (yc > F["yld_e10"]) & (F["yld_e10"] > F["yld_e20"])
    y_dn = yld_valid & (yc < F["yld_e10"]) & (F["yld_e10"] < F["yld_e20"])
    yld_rising = y_dn if cfg.invert_yield else y_up
    yld_falling = y_up if cfg.invert_yield else y_dn
    eur_bull = eur_valid & (ec > F["eur_e10"]) & (F["eur_e10"] > F["eur_e20"])
    eur_bear = eur_valid & (ec < F["eur_e10"]) & (F["eur_e10"] < F["eur_e20"])
    spx_bull = spx_valid & (pc > F["spx_e10"]) & (F["spx_e10"] > F["spx_e20"])
    spx_bear = spx_valid & (pc < F["spx_e10"]) & (F["spx_e10"] < F["spx_e20"])
    tips_rising = tips_valid & (tc > F["tips_e10"]) & (F["tips_e10"] > F["tips_e20"])
    tips_falling = tips_valid & (tc < F["tips_e10"]) & (F["tips_e10"] < F["tips_e20"])
    slv_bull = slv_valid & (sc_ > F["slv_e20"])
    slv_bear = slv_valid & (sc_ < F["slv_e20"])
    F.update(dxy_bull=dxy_bull, dxy_bear=dxy_bear, yld_rising=yld_rising, yld_falling=yld_falling,
             eur_bull=eur_bull, eur_bear=eur_bear, spx_bull=spx_bull, spx_bear=spx_bear,
             tips_rising=tips_rising, tips_falling=tips_falling, slv_bull=slv_bull, slv_bear=slv_bear)

    # US2Y (daily FRED) and the 2s10s curve
    y2 = m.ext_daily.get("DGS2")
    y2a = align(close_t, y2, ["close"]) if y2 is not None else {"close": np.full(n, np.nan), "_open": np.full(n, np.nan)}
    y2v = y2a["close"]
    y2_valid = ~np.isnan(y2v) & ~np.isnan(yc) & _valid_age(y2a["_open"], close_epoch)
    curve = np.where(y2_valid, yc - y2v, np.nan)
    F["y2_valid"] = y2_valid
    F["curve_2s10s"] = curve
    F["curve_steep"] = y2_valid & (curve > ta.shift(curve, 1))

    # VIX (daily close[1])
    vix = m.ext_daily.get("vix")
    if vix is not None and len(vix):
        vx = pd.DataFrame({"c1": ta.shift(vix["close"].to_numpy(float), 1)}, index=vix.index)
        F["vix"] = align(close_t, vx, ["c1"])["c1"]
    else:
        F["vix"] = np.full(n, np.nan)

    # Daily closes of the chart symbol (_dC1/_dC2) and previous-month high/low.
    d = m.htf.get("D")
    if d is not None and len(d):
        dd = pd.DataFrame({"c1": ta.shift(d["close"].to_numpy(float), 1),
                           "c2": ta.shift(d["close"].to_numpy(float), 2)}, index=d.index)
        ad = align(close_t, dd, ["c1", "c2"])
        F["d_c1"], F["d_c2"] = ad["c1"], ad["c2"]
        # previous trading-month high / low
        ny_open = d.index.tz_convert("America/New_York") + pd.Timedelta(hours=7)
        mk = (ny_open.year * 100 + ny_open.month).to_numpy()
        dfm = pd.DataFrame({"h": d["high"].to_numpy(float), "l": d["low"].to_numpy(float), "m": mk})
        mh = dfm.groupby("m")["h"].max()
        ml = dfm.groupby("m")["l"].min()
        months = np.array(sorted(mh.index))
        prev_h = {months[j]: mh[months[j - 1]] for j in range(1, len(months))}
        prev_l = {months[j]: ml[months[j - 1]] for j in range(1, len(months))}
        mkc = cal["month_key"]
        F["pm_high"] = np.array([prev_h.get(k, np.nan) for k in mkc], dtype=float)
        F["pm_low"] = np.array([prev_l.get(k, np.nan) for k in mkc], dtype=float)
    else:
        F["d_c1"] = F["d_c2"] = F["pm_high"] = F["pm_low"] = np.full(n, np.nan)

    # ---- COT (weekly, aligned on RELEASE time) and weekly OI conviction ----
    cot = m.cot
    F["cot_valid"] = np.zeros(n, dtype=bool)
    F["cot_pct"] = np.full(n, np.nan)
    F["oi_valid"] = np.zeros(n, dtype=bool)
    F["oi_chg_pct"] = np.full(n, np.nan)
    F["oi_price_up"] = np.zeros(n, dtype=bool)
    if cot is not None and len(cot) > 2:
        net = (cot["nc_long"] - cot["nc_short"]).to_numpy(float)
        # D-05: percentile over cotLen WEEKS. Pine ranks the weekly value over the last
        # cotLen CHART bars, which mostly repeat one week's number.
        pct = ta.percentrank(net, cfg.cot_len)
        oi = cot["open_interest"].to_numpy(float)
        oi_prev = ta.shift(oi, 1)
        oi_chg = np.where(oi_prev > 0, (oi - oi_prev) / oi_prev * 100.0, np.nan)
        cf = pd.DataFrame({"pct": pct, "oichg": oi_chg}, index=cot.index)
        if d is not None and "asof" in cot:
            # price change between consecutive report as-of dates, from the daily series
            dclose = pd.Series(d["close"].to_numpy(float), index=(d.index.tz_convert("America/New_York") + pd.Timedelta(hours=7)).normalize().tz_localize(None))
            dclose = dclose[~dclose.index.duplicated(keep="last")]
            pa = dclose.reindex(pd.DatetimeIndex(cot["asof"]), method="ffill").to_numpy(float)
            cf["pup"] = np.concatenate([[np.nan], (pa[1:] > pa[:-1]).astype(float)])
        else:
            cf["pup"] = np.nan
        ac = align(close_t, cf, ["pct", "oichg", "pup"])
        age_ok = (~np.isnan(ac["_open"])) & ((close_epoch - ac["_open"]) <= 10 * 86400)
        F["cot_valid"] = age_ok & ~np.isnan(ac["pct"])
        F["cot_pct"] = np.where(F["cot_valid"], ac["pct"], np.nan)
        F["oi_valid"] = age_ok & ~np.isnan(ac["oichg"]) & ~np.isnan(ac["pup"])
        F["oi_chg_pct"] = ac["oichg"]
        F["oi_price_up"] = ac["pup"] == 1.0
    cot_on = cfg.cot_enable
    cot_long = F["cot_valid"] & (F["cot_pct"] >= cfg.cot_extreme)
    cot_short = F["cot_valid"] & (F["cot_pct"] <= 100 - cfg.cot_extreme)
    F["cot_crowd_long"], F["cot_crowd_short"] = cot_long, cot_short
    F["cot_regime"] = np.where(~(F["cot_valid"] & cot_on), 0, np.where(cot_long, -1, np.where(cot_short, 1, 0)))
    oi_rising = F["oi_valid"] & (F["oi_chg_pct"] > 0.0)
    pup = F["oi_price_up"]
    F["oi_conviction"] = np.where(~F["oi_valid"], 0, np.where(pup & oi_rising, 1, np.where(~pup & oi_rising, -1, 0)))
    F["oi_state"] = np.where(~F["oi_valid"], "OI —", np.where(pup & oi_rising, "OI NEW-LONG", np.where(~pup & oi_rising, "OI NEW-SHORT",
                             np.where(pup & ~oi_rising, "OI COVER", "OI LIQ"))))

    # ---- GC futures confirmation ----
    gc_enabled = (m.ext_chart.get("gc") is not None) and tf_sec >= cfg.gc_min_tf_sec
    gcc, gce, gcv, gcva, gct = F["gc_c1"], F["gc_e20"], F.get("gc_v1", np.full(n, np.nan)), F.get("gc_vavg", np.full(n, np.nan)), F.get("gc_t1", np.full(n, np.nan))
    gc_res = ~np.isnan(gcc) & ~np.isnan(gce) & ~np.isnan(gcv)
    gc_fin = gc_res & (gcc > 0) & (gcv >= 0)
    gc_fresh = gc_res & ~np.isnan(gct) & ((open_epoch - gct) <= tf_sec * 3)
    gc_plaus = gc_fin & (c > 0) & (np.abs(gcc - c) / c <= 0.05)
    gc_valid = gc_enabled & gc_res & gc_fin & gc_fresh & gc_plaus
    F["gc_enabled"] = gc_enabled
    F["gc_valid"] = gc_valid
    F["gc_fail"] = np.where(not gc_enabled, "", np.where(~gc_res, "!UNRESOLVED", np.where(~gc_fin, "!BADPRICE", np.where(~gc_fresh, "!STALE", np.where(~gc_plaus, "!SYMBOL?", "")))))
    gc_bull = gc_valid & (gcc > gce)
    gc_bear = gc_valid & (gcc < gce)
    gc_volexp = gc_valid & ~np.isnan(gcva) & (gcva > 0) & (gcv > gcva * cfg.gc_vol_mult)
    spot_bull = c1 > ta.ema(c1, 20)
    F["gc_confirms_bull"] = gc_valid & gc_bull & spot_bull
    F["gc_confirms_bear"] = gc_valid & gc_bear & ~spot_bull
    F["gc_diverges"] = gc_valid & (gc_bull != spot_bull)
    F["gc_strong_bull"] = F["gc_confirms_bull"] & gc_volexp
    F["gc_strong_bear"] = F["gc_confirms_bear"] & gc_volexp
    F["GC_STATUS"] = np.where(gc_valid, 0, np.where(~gc_res | (not gc_enabled), 1, np.where(~gc_fin, 3, np.where(~gc_fresh, 2, 3))))
    F["OI_STATUS"] = np.where(F["oi_valid"], 0, 1)
    F["US2Y_STATUS"] = np.where(y2_valid, 0, 1)
    F["COT_STATUS"] = np.where(F["cot_valid"] & cot_on, 0, 1)

    mbv = (F["gc_confirms_bull"].astype(int) + dxy_bear + yld_falling + spx_bull + eur_bull + slv_bull + tips_falling)
    mbr = (F["gc_confirms_bear"].astype(int) + dxy_bull + yld_rising + spx_bear + eur_bear + slv_bear + tips_rising)
    pool = 6 + gc_valid.astype(int)
    need = np.ceil(pool / 2.0)
    F["macro_bull_votes"], F["macro_bear_votes"] = mbv, mbr
    F["macro_bull"] = mbv >= need
    F["macro_bear"] = mbr >= need
    dxy_roc = np.where(dxy_valid, np.nan_to_num(F["dxy_roc"], nan=0.0), 0.0)
    zn_roc = np.where(yld_valid, np.nan_to_num(F["yld_roc"], nan=0.0), 0.0)
    eur_roc = np.where(eur_valid, np.nan_to_num(F["eur_roc"], nan=0.0), 0.0)

    # ---- correlations (chart-bar returns of the aligned macro closes) ----
    def rets(x, valid):
        x1 = ta.shift(x, 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            rr = np.where(np.abs(x1) > 1e-10, x / x1, 0.0) - 1.0
        return np.where(valid & ~np.isnan(x1), rr, np.nan)

    series = {"DXY": (dxc, dxy_valid, -1.0), "Yld": (yc, yld_valid, 1.0 if cfg.invert_yield else -1.0),
              "Slv": (sc_, slv_valid, 1.0), "SPX": (pc, spx_valid, 1.0), "EUR": (ec, eur_valid, 1.0),
              "TIPS": (tc, tips_valid, -1.0)}
    p_upper = 1.0 - (0.05 / 18.0) / 2.0
    sig = {}
    for L in (cfg.corr_short_len, cfg.corr_med_len, cfg.corr_long_len):
        dfree = max(L - 2, 1)
        t = _t_inv(p_upper, dfree)
        sig[L] = t / math.sqrt(dfree + t * t)
    F["corr_sig"] = sig
    corr = {}
    health = {}
    avg_corr = {}
    stab = {}
    for key, (x, valid, sign) in series.items():
        rr = rets(x, valid)
        cs = [np.where(valid, ta.correlation(gold_ret, rr, L), np.nan) for L in (cfg.corr_short_len, cfg.corr_med_len, cfg.corr_long_len)]
        corr[key] = cs
        z = [np.nan_to_num(q, nan=0.0) for q in cs]
        avg_corr[key] = (z[0] + z[1] + z[2]) / 3.0
        stab[key] = np.abs(z[0] - z[2])

        def win(rv, s):
            rsv = rv * sign
            norm = rsv / s if s > 0 else rsv * 10.0
            return 50.0 + 45.0 * np.clip(norm, -1.0, 1.0)
        hm = (win(z[0], sig[cfg.corr_short_len]) + win(z[1], sig[cfg.corr_med_len]) + win(z[2], sig[cfg.corr_long_len])) / 3.0
        health[key] = np.where(valid, hm, 0.0)
    F["corr"], F["avg_corr"], F["corr_health"] = corr, avg_corr, health
    valids = [dxy_valid, yld_valid, slv_valid, spx_valid, eur_valid, tips_valid]
    num_valid = sum(vv.astype(float) for vv in valids)
    F["num_valid"] = num_valid
    tot_h = health["DXY"] + health["Yld"] + health["Slv"] + health["SPX"] + health["EUR"] + health["TIPS"]
    F["avg_corr_health"] = np.where(num_valid > 0, tot_h / np.maximum(num_valid, 1), 0.0)
    tot_s = stab["DXY"] + stab["Yld"] + stab["Slv"] + stab["SPX"] + stab["EUR"] + stab["TIPS"]
    F["avg_stability"] = np.where(num_valid > 0, tot_s / np.maximum(num_valid, 1), 0.0)

    wd = np.minimum(np.abs(avg_corr["DXY"]) * 100, 30)
    wy = np.minimum(np.abs(avg_corr["Yld"]) * 100, 30)
    ws = np.minimum(np.abs(avg_corr["Slv"]) * 100, 25)
    wp = np.where(spx_valid, np.minimum(np.abs(avg_corr["SPX"]) * 100, 15), 0.0)
    we = np.where(eur_valid, 20.0, 0.0)
    wt = np.minimum(np.abs(avg_corr["TIPS"]) * 100, 25)
    wtot = wd + wy + ws + wp + we + wt
    with np.errstate(divide="ignore", invalid="ignore"):
        wD = np.where(wtot > 0, wd / wtot * 100, 30.0)
        wY = np.where(wtot > 0, wy / wtot * 100, 25.0)
        wS = np.where(wtot > 0, ws / wtot * 100, 20.0)
        wP = np.where(wtot > 0, wp / wtot * 100, 15.0)
        wE = np.where(wtot > 0, we / wtot * 100, 20.0)
        wT = np.where(wtot > 0, wt / wtot * 100, 10.0)
    ms = (np.where(dxy_valid, np.where(dxy_bear, wD, np.where(dxy_bull, -wD, 0.0)), 0.0)
          + np.where(yld_valid, np.where(yld_falling, wY, np.where(yld_rising, -wY, 0.0)), 0.0)
          + np.where(spx_valid, np.where(spx_bull, wP, np.where(spx_bear, -wP, 0.0)), 0.0)
          + np.where(eur_valid, np.where(eur_bull, wE, np.where(eur_bear, -wE, 0.0)), 0.0)
          + np.where(slv_valid, np.where(sc_ > F["slv_e20"], wS, np.where(sc_ < F["slv_e20"], -wS, 0.0)), 0.0)
          + np.where(tips_valid, np.where(tips_falling, wT, np.where(tips_rising, -wT, 0.0)), 0.0)
          + np.where(dxy_valid, np.where(dxy_roc < -0.15, 10.0, np.where(dxy_roc > 0.15, -10.0, 0.0)), 0.0)
          + np.where(yld_valid, np.where(zn_roc < -0.1, 5.0, np.where(zn_roc > 0.1, -5.0, 0.0)), 0.0)
          + np.where(eur_valid, np.where(eur_roc > 0.15, 5.0, np.where(eur_roc < -0.15, -5.0, 0.0)), 0.0))
    mss = np.trunc(np.clip(ms, -100, 100))
    F["macro_strength"] = mss
    msd = np.nan_to_num(ta.stdev(mss, 20), nan=50.0)
    nvalid6 = (dxy_valid.astype(int) + yld_valid + slv_valid + spx_valid + eur_valid + tips_valid) / 6.0
    F["macro_strength_conf"] = np.floor(nvalid6 * 30.0 + F["avg_corr_health"] * 0.50 + (1.0 - np.minimum(msd / 100.0, 1.0)) * 20.0 + 0.5)
    F["dxy_rsi"] = F["dxy_rsi"]

    # ---- trend scores ----
    e20, e100, e200 = F["ema20"], F["ema100"], F["ema200"]
    e20_3 = ta.shift(e20, 3)
    bts = ((c > e200) * 20 + (e20 > e100) * 20 + (e20 > e20_3) * 20 + ((dip > dim) & (adx > cfg.adx_threshold)) * 20
           + (c > e100) * 10 + (F["high_volume"] & (c > e20)) * 10)
    brs = ((c < e200) * 20 + (e20 < e100) * 20 + (e20 < e20_3) * 20 + ((dim > dip) & (adx > cfg.adx_threshold)) * 20
           + (c < e100) * 10 + (F["high_volume"] & (c < e20)) * 10)
    F["bull_trend_score"], F["bear_trend_score"] = bts.astype(int), brs.astype(int)
    F["bull_trend"] = bts >= cfg.trend_threshold
    F["bear_trend"] = brs >= cfg.trend_threshold

    # ---- pivots ----
    F["piv_hi"] = ta.pivothigh(h, cfg.internal_pivot_len, cfg.internal_pivot_len)
    F["piv_lo"] = ta.pivotlow(l, cfg.internal_pivot_len, cfg.internal_pivot_len)
    F["swing_piv_hi"] = ta.pivothigh(h, cfg.swing_pivot_len, cfg.swing_pivot_len)
    F["swing_piv_lo"] = ta.pivotlow(l, cfg.swing_pivot_len, cfg.swing_pivot_len)
    body = np.abs(c - o)
    rng_ = h - l
    F["body"] = body
    F["range"] = rng_
    F["body_pct"] = np.where(rng_ > 0, body / np.where(rng_ > 0, rng_, 1.0) * 100.0, 0.0)
    F["pr_raw_vol"] = ta.percentrank(v, cfg.vol_lookback)
    F["vol_delta50"] = ta.rolling_sum(np.where(c > o, v, np.where(c < o, -v, 0.0)), 50)
    bar_dir = np.where(c > o, 1.0, np.where(c < o, -1.0, np.where(c > c1, 0.5, np.where(c < c1, -0.5, 0.0))))
    cvd = np.cumsum(bar_dir * v)
    F["cvd_bull"] = ta.ema(cvd, 20) > ta.ema(cvd, 100)
    F["cvd_bear"] = ta.ema(cvd, 20) < ta.ema(cvd, 100)
    F["vwap_slope"] = vwap - np.where(np.isnan(ta.shift(vwap, 10)), vwap, ta.shift(vwap, 10))
    vs = F["vwap_slope"]
    F["vwap_accel"] = vs - np.where(np.isnan(ta.shift(vs, 5)), vs, ta.shift(vs, 5))
    F["atr_sma20"] = ta.sma(aatr, 20)
    F["highest_n"] = None  # filled by the engine once OUTCOME_N is known
    return F
