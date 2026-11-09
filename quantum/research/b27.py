"""B27 (research/registrations/B27.json, committed 0065cadb1 before this code): the maximum achievable TP-first rate for
+$15 / -$15, by a registered discovery framework selected on development data only and checked, frozen, on 2026.

RESEARCH ONLY: never imported by the engine, the arms or the site (tests/test_integrity.py). Trades are B26's trade
(quantum.research.b26): decision at a 15m close, fill at the next open (BUY at the ask, SELL at the bid), +-$15 from the
actual fill, triggers on the exit side, worst-case same-bar and gap rules.

  S1 single conditions      S2 trigger families x entry mechanisms x confirmation distances
  S3 probability models     S4 feature ranking and ablation      S5 regimes      S6 2026 intermarket (descriptive)

  python -m quantum.research.b27 --rd <research-data> --store5 <XAU_USD_5m> --store60 <XAU_USD_60m> --md <market-data>
      --out <dir> [--trials research/trials.jsonl]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config, engine, ta
from ..data import sources
from ..features import compute as compute_features
from . import b8_news, b10, b19, b22, b26, history
from . import harness as H

REG = "B27"
CONF_X = (3, 5, 7, 10, 12, 15, 20)
CONF_WIN = 96
FILL_WIN = 8
QS = (0.50, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005)
# What the "top q" thresholds and selections are computed on. "raw" (Phase C audit fix, 2026-11-09): the uncalibrated
# model score, whose training-window quantile really selects about q (isotonic calibration is monotone, so the order is
# the same). "calibrated" reproduces the B27 (acca0426f) and B29 (9a86c684c) runs: there the threshold was a quantile of
# isotonic-calibrated probabilities, a step function with ~20 levels per window, so ">= threshold" admitted the whole
# top step (e.g. 42% of test rows for a nominal top 1%; research/results/phasec/phasec_c_diag.json).
SELECT_ON = "raw"
MIN_N = 300
LOW_N = 30
DIRS = {1: "BUY", -1: "SELL"}
FAMILIES = ("EVERY_HOUR", "ENG_SIGNAL", "SWEEP", "GRAB", "BREAK", "BOS", "FVG", "DISPLACEMENT", "EMA_PULLBACK",
            "VOL_EXPANSION", "ASIA_BREAKOUT", "FAILED_BREAKOUT", "PD_SWEEP")
EVENT_COL = {"ENG_SIGNAL": "sg_signal", "SWEEP": "sg_sweep", "GRAB": "sg_grab", "BREAK": "sg_break", "BOS": "ev_bos",
             "FVG": "ev_fvg", "DISPLACEMENT": "ev_disp", "EMA_PULLBACK": "ev_pullback", "VOL_EXPANSION": "ev_volx",
             "ASIA_BREAKOUT": "ev_asia", "FAILED_BREAKOUT": "ev_failbo", "PD_SWEEP": "ev_pdsweep"}
LEVEL_COL = {"FVG": "lv_fvg", "DISPLACEMENT": "lv_disp", "ASIA_BREAKOUT": "lv_asia", "FAILED_BREAKOUT": "lv_failbo",
             "PD_SWEEP": "lv_pdsweep"}
NOT_TESTED = ("true VWAP / volume profile / POC / relative volume (no traded volume in the feed)",
              "intraday DXY / 10Y / EURUSD / silver / S&P on 2020-22 (no bars held; 2026 descriptive only, S6)",
              "PCE (no dated list)")
SEED = 27
MOVE = b26.MOVE


# ---------------- features (S1, S3) ----------------
def engine_struct(m15: pd.DataFrame, h1: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """The production engine's BOS / MSS / CHoCH events (up, down) on these bars, read-only."""
    m = b10.make_market(m15, h1, "15m", 900)
    F = compute_features(m, config.DEFAULT)
    res = engine.run(m, config.DEFAULT, "treatment", F)
    return b19.struct_arrays(res, len(m15))


def _release_times() -> np.ndarray:
    rel = [int(b8_news.release_utc(kind, day).timestamp()) for kind, days in b8_news.DATES.items() for day in days]
    from .. import news_calendar
    rel += [e["t"] for e in news_calendar.events()]
    return np.unique(np.asarray(rel, dtype=np.int64))


def extra_features(m15: pd.DataFrame, up: np.ndarray, dn: np.ndarray, trend_1h: np.ndarray) -> pd.DataFrame:
    """B27's added features, every one from bars closed at or before the row's bar. nd_ = direction-free, sg_ = signed
    (+ favours a BUY), ev_ = signed events, lv_ = the event's limit level."""
    o, h, l, c = (m15[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    idx = m15.index
    atr = ta.atr(h, l, c, 14)
    atr100 = ta.atr(h, l, c, 100)
    dip, dim, adx = ta.dmi(h, l, c, 14, 14)
    sd = ta.stdev(c, 20)
    bbw_rank = ta.percentrank(4 * sd, 500)
    rng, body = h - l, np.abs(c - o)
    sgn = np.sign(c - o)
    e20 = ta.ema(c, 20)

    consec = np.zeros(n)
    for i in range(1, n):
        s = np.sign(c[i] - c[i - 1])
        consec[i] = (consec[i - 1] + s if np.sign(consec[i - 1]) == s and s != 0 else s)
    consec = np.clip(consec, -8, 8)

    disp = np.where((rng >= 2 * atr) & (body >= 0.7 * rng), sgn, 0.0)
    lv_disp = np.where(disp != 0, o + 0.5 * (c - o), np.nan)

    fvg = np.zeros(n)
    lv_fvg = np.full(n, np.nan)
    in_fvg = np.zeros(n)
    bull_zone = bear_zone = None                                   # (bottom, top, created)
    for i in range(2, n):
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= 0.3 * atr[i]:
            fvg[i], lv_fvg[i] = 1.0, 0.5 * (l[i] + h[i - 2])
            bull_zone = (h[i - 2], l[i], i)
        elif h[i] < l[i - 2] and l[i - 2] - h[i] >= 0.3 * atr[i]:
            fvg[i], lv_fvg[i] = -1.0, 0.5 * (h[i] + l[i - 2])
            bear_zone = (h[i], l[i - 2], i)
        v = 0.0
        if bull_zone and i > bull_zone[2]:
            if l[i] < bull_zone[0] or i - bull_zone[2] > 48:
                bull_zone = None
            elif l[i] <= bull_zone[1]:
                v += 1.0
        if bear_zone and i > bear_zone[2]:
            if h[i] > bear_zone[1] or i - bear_zone[2] > 48:
                bear_zone = None
            elif h[i] >= bear_zone[0]:
                v -= 1.0
        in_fvg[i] = v

    ob = np.zeros(n)
    zones = []                                                     # (lo, hi, dir, created)
    for i in range(n):
        if disp[i] != 0:
            for k in range(i - 1, max(i - 6, -1), -1):
                if np.sign(c[k] - o[k]) == -disp[i]:
                    zones.append((l[k], h[k], disp[i], i))
                    break
        zones = [z for z in zones if i - z[3] <= 48 and not (z[2] > 0 and c[i] < z[0]) and not (z[2] < 0 and c[i] > z[1])]
        for z in zones:
            if i > z[3] and l[i] <= z[1] and h[i] >= z[0]:
                ob[i] += z[2]
    ob = np.clip(ob, -1, 1)

    ph, pl = ta.pivothigh(h, 5, 5), ta.pivotlow(l, 5, 5)
    eq = np.zeros(n)
    highs, lows = [], []
    for i in range(n):
        if not np.isnan(ph[i]):
            highs = ([*highs, (ph[i], i)])[-3:]
        if not np.isnan(pl[i]):
            lows = ([*lows, (pl[i], i)])[-3:]
        a = atr[i]
        if np.isnan(a):
            continue
        hs = [v for v, j in highs if i - j <= 96 and 0 < v - c[i] <= 1.5 * a]
        ls = [v for v, j in lows if i - j <= 96 and 0 < c[i] - v <= 1.5 * a]
        eqh = any(abs(x - y) <= 0.15 * a for x_i, x in enumerate(hs) for y in hs[x_i + 1:])
        eql = any(abs(x - y) <= 0.15 * a for x_i, x in enumerate(ls) for y in ls[x_i + 1:])
        eq[i] = float(eqh) - float(eql)

    utc_day = idx.normalize()
    hour = idx.hour.to_numpy()
    df = pd.DataFrame({"h": h, "l": l}, index=idx)
    asia = df[hour < 7].groupby(utc_day[hour < 7]).agg(hi=("h", "max"), lo=("l", "min"))
    a_hi = pd.Series(utc_day, index=idx).map(asia["hi"]).to_numpy(float)
    a_lo = pd.Series(utc_day, index=idx).map(asia["lo"]).to_numpy(float)
    after = (hour >= 7) & (hour < 21)
    asia_pos = np.where(after & (a_hi > a_lo), (c - 0.5 * (a_hi + a_lo)) / np.where(a_hi > a_lo, a_hi - a_lo, np.nan), np.nan)
    ev_asia = np.zeros(n)
    lv_asia = np.full(n, np.nan)
    london = (hour >= 7) & (hour < 12)
    prev_c = np.r_[np.nan, c[:-1]]
    same_day = np.r_[False, utc_day[1:] == utc_day[:-1]]
    done = set()
    for i in np.flatnonzero(london & same_day & ~np.isnan(a_hi)):
        key = utc_day[i]
        if key in done:
            continue
        if c[i] > a_hi[i] >= prev_c[i]:
            ev_asia[i], lv_asia[i] = 1.0, a_hi[i]
            done.add(key)
        elif c[i] < a_lo[i] <= prev_c[i]:
            ev_asia[i], lv_asia[i] = -1.0, a_lo[i]
            done.add(key)

    tday = (idx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)).normalize()
    dd = df.groupby(tday).agg(hi=("h", "max"), lo=("l", "min"))
    prev = dd.shift(1)
    pdh = pd.Series(tday, index=idx).map(prev["hi"]).to_numpy(float)
    pdl = pd.Series(tday, index=idx).map(prev["lo"]).to_numpy(float)
    ev_pd = np.where((h > pdh) & (c < pdh), -1.0, np.where((l < pdl) & (c > pdl), 1.0, 0.0))
    lv_pd = np.where(ev_pd < 0, pdh, np.where(ev_pd > 0, pdl, np.nan))

    hh20 = pd.Series(h).shift(1).rolling(20).max().to_numpy()
    ll20 = pd.Series(l).shift(1).rolling(20).min().to_numpy()
    ev_fb = np.where((h > hh20) & (c < hh20), -1.0, np.where((l < ll20) & (c > ll20), 1.0, 0.0))
    lv_fb = np.where(ev_fb < 0, hh20, np.where(ev_fb > 0, ll20, np.nan))
    hi96 = pd.Series(h).rolling(96).max().to_numpy()
    lo96 = pd.Series(l).rolling(96).min().to_numpy()
    prem = (c - lo96) / np.where(hi96 > lo96, hi96 - lo96, np.nan) - 0.5

    flip = np.zeros(n)
    last_d, prev_d, last_i = 0, 0, -10 ** 9
    for i in range(n):
        ev = 1 if up[i] else (-1 if dn[i] else 0)
        if ev:
            prev_d, last_d, last_i = last_d, ev, i
        if last_d and prev_d and last_d != prev_d and i - last_i <= 8:
            flip[i] = last_d
    ev_bos = np.where(up, 1.0, np.where(dn, -1.0, 0.0))
    pull = np.where((trend_1h > 0) & (l <= e20) & (c > e20), 1.0, np.where((trend_1h < 0) & (h >= e20) & (c < e20), -1.0, 0.0))
    volx = np.where((np.r_[np.nan, bbw_rank[:-1]] <= 20) & (rng >= 1.5 * atr), sgn, 0.0)

    t_close = ta.epoch_s(idx).astype(np.int64) + 900
    rel = _release_times()
    j = np.searchsorted(rel, t_close, "left")
    to_next = np.where(j < len(rel), (rel[np.clip(j, 0, len(rel) - 1)] - t_close) / 60.0, np.nan)
    since = np.where(j > 0, (t_close - rel[np.clip(j - 1, 0, len(rel) - 1)]) / 60.0, np.nan)
    dated = np.zeros(n, bool)
    for lo_, hi_ in b26.DATED:
        dated |= (t_close >= int(lo_.timestamp())) & (t_close < int(hi_.timestamp()))
    to_next = np.where(dated, np.minimum(to_next, 600), np.nan)
    since = np.where(dated, np.minimum(since, 600), np.nan)

    return pd.DataFrame({
        "nd_adx": adx, "nd_atr_ratio": atr / atr100, "nd_bbw_rank": bbw_rank, "nd_news_to_next": to_next, "nd_news_since": since,
        "sg_di_diff": dip - dim, "sg_consec": consec, "sg_in_fvg": in_fvg, "sg_ob_retest": ob, "sg_eq_liquidity": eq,
        "sg_asia_pos": asia_pos, "sg_prem_disc": prem, "sg_flip": flip, "sg_disp": disp, "sg_fvg_new": fvg,
        "ev_bos": ev_bos, "ev_fvg": fvg, "ev_disp": disp, "ev_pullback": pull, "ev_volx": volx, "ev_asia": ev_asia,
        "ev_failbo": ev_fb, "ev_pdsweep": ev_pd,
        "lv_fvg": lv_fvg, "lv_disp": lv_disp, "lv_asia": lv_asia, "lv_failbo": lv_fb, "lv_pdsweep": lv_pd}, index=idx)


def build_features(m15: pd.DataFrame, h1: pd.DataFrame, log=print) -> pd.DataFrame:
    base, _ = b22.base_features(m15, h1, log)
    up, dn = engine_struct(m15, h1)
    ext = extra_features(m15, up, dn, base["sg_trend_1h"].to_numpy(float))
    log(f"[B27] features on {len(m15)} bars")
    return pd.concat([base, ext], axis=1)


def feature_columns(F: pd.DataFrame) -> tuple[list[str], list[str]]:
    nd = [c for c in F.columns if c.startswith("nd_")]
    sg = [c for c in F.columns if c.startswith("sg_")]
    return nd, sg


FAMILY_OF = {"ENGINE": ("nd_tq", "nd_sess_q", "nd_reg_", "sg_signal", "sg_sweep", "sg_grab", "sg_break", "sg_bull_minus_bear"),
             "TREND": ("sg_d_e", "sg_slope", "sg_trend_", "sg_di_diff", "nd_adx", "sg_d_vwap"),
             "OSCILLATOR": ("sg_rsi", "nd_rsi_abs", "sg_macd", "sg_pct_b"),
             "VOLATILITY": ("nd_atr", "nd_range_atr", "nd_body_atr", "nd_bb_width", "nd_bbw_rank"),
             "LIQUIDITY": ("sg_d_pd", "sg_d_pw", "nd_day_pos", "sg_day_pos", "sg_asia", "sg_eq_", "sg_prem"),
             "STRUCTURE_SMC": ("nd_fvg", "sg_in_fvg", "sg_ob_", "sg_disp", "sg_flip", "sg_since_", "sg_fvg_new"),
             "MOMENTUM": ("sg_ret", "sg_wick", "nd_run", "sg_run", "sg_consec"),
             "TIME_NEWS": ("nd_hour", "nd_weekday", "nd_london", "nd_ny", "nd_news"),
             "MARKOV": ("hmm_",)}


def family(col: str) -> str:
    for fam, pre in FAMILY_OF.items():
        if any(col.startswith(p) for p in pre):
            return fam
    return "OTHER"


# ---------------- labels (B26) ----------------
def labels(name: str, m15: pd.DataFrame, h1: pd.DataFrame, score_from: pd.Timestamp, scale: bool) -> pd.DataFrame:
    df = b26.run_population(name, {"bars": m15, "h1": h1, "score_from": score_from, "scale": scale, "tf": "15m"},
                            log=lambda *_: None)
    df["d"] = np.where(df["dir"] == "BUY", 1, -1)
    df["ym"] = pd.to_datetime(df["fill_utc"], unit="s", utc=True).dt.strftime("%Y-%m")
    return df


def labels_5m(L15: pd.DataFrame, m15: pd.DataFrame, df5: pd.DataFrame) -> pd.DataFrame:
    """The same 15m decisions, filled at the 5m bar opening at the 15m fill time and resolved on 5m bars (ENG)."""
    P5 = b26.make_path(df5, 300)
    t5 = np.asarray(P5.t, dtype=np.int64)
    t15 = ta.epoch_s(m15.index).astype(np.int64)
    L = L15[(L15["fill_utc"] >= t5[0]) & (L15["fill_utc"] <= t5[-1])].copy()
    f5 = np.searchsorted(t5, L["fill_utc"].to_numpy())
    ok = (f5 < len(t5)) & (t5[np.clip(f5, 0, len(t5) - 1)] == L["fill_utc"].to_numpy())
    L, f5 = L[ok].copy(), f5[ok]
    out, xt, net, cost = [], [], [], []
    for (_, r), f in zip(L.iterrows(), f5, strict=True):
        k = r["k"]
        res = b26.race(P5, int(f), int(r["d"]), r["spread"] * k, r["slip_in"] * k, 0.20 * k, k, b26.HORIZON["5m"])
        oc = b26.OUTCOMES[res[0]]
        out.append(oc)
        xt.append(res[3])
        net.append((r["d"] * (res[2] - res[5]) - r["commission"] * k) / k if oc != "OPEN" else np.nan)
        cost.append(r["spread"] + r["slip_in"] + (0.0 if oc == "TP" else 0.20) + r["commission"])
    L["outcome"], L["exit_utc"], L["net_usd_oz"], L["cost_usd_oz"] = out, xt, net, cost
    L["exit_bar"] = np.searchsorted(t15, np.asarray(xt) - 1, "right") - 1
    L["minutes"] = (L["exit_utc"] - L["fill_utc"]) / 60.0
    return L


# ---------------- statistics ----------------
def decided(out: np.ndarray) -> tuple[int, int]:
    tp = int((out == "TP").sum())
    return tp, tp + int(((out == "SL") | (out == "AMBIGUOUS")).sum())


def seq_rows(dec: np.ndarray, ex: np.ndarray, out: np.ndarray) -> np.ndarray:
    """Positions forming the non-overlapping series (rows sorted by dec): the next entry only once the last has exited."""
    keep, cur = [], -1
    for q in np.argsort(dec, kind="stable"):
        if out[q] == "OPEN":
            continue
        if dec[q] >= cur:
            keep.append(q)
            cur = ex[q]
    return np.asarray(keep, dtype=int)


def base_rates(L: pd.DataFrame) -> dict:
    """B26-style all-bar decided rate per (direction, session, month): the matched random reference."""
    g = L[L["outcome"].isin(["TP", "SL", "AMBIGUOUS"])]
    return (g.assign(tp=(g["outcome"] == "TP").astype(float)).groupby(["d", "session", "ym"])["tp"].mean()).to_dict()


def matched(rates: dict, d: np.ndarray, sess: np.ndarray, ym: np.ndarray) -> float:
    vals = [rates.get((int(a), b, c)) for a, b, c in zip(d, sess, ym, strict=True)]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else math.nan


def binom_p(k: int, n: int, p: float) -> float:
    from scipy.stats import binomtest
    if n == 0 or not (0 < p < 1):
        return 1.0
    return float(binomtest(k, n, p, alternative="greater").pvalue)


def bh(ps: list[float], q: float = 0.05) -> list[bool]:
    m = len(ps)
    if m == 0:
        return []
    order = np.argsort(ps)
    passed = np.zeros(m, bool)
    kmax = -1
    for rank, j in enumerate(order, 1):
        if ps[j] <= q * rank / m:
            kmax = rank
    if kmax > 0:
        passed[order[:kmax]] = True
    return passed.tolist()


def holm(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)
    adj = np.zeros(m)
    run = 0.0
    for i, j in enumerate(order):
        run = max(run, min(1.0, (m - i) * ps[j]))
        adj[j] = run
    return adj.tolist()


def max_dd(net: np.ndarray) -> float:
    cum = np.cumsum(net)
    return float(np.max(np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum)) if len(cum) else 0.0


def mc_dd(net: np.ndarray, n: int = 2000) -> float:
    if len(net) < 2:
        return math.nan
    rng = H.seeded_rng(SEED)
    return float(np.quantile([max_dd(rng.permutation(net)) for _ in range(n)], 0.95))


def break_even_decided(out: np.ndarray, net: np.ndarray) -> float:
    """The decided TP-first rate at which the series' expectancy is zero, holding its timeouts / closures as measured:
    r* = (-L - (n_neither / n_decided) * N) / (W - L), W / L / N = mean net of TP / stop / neither trades."""
    tp, st = out == "TP", np.isin(out, ["SL", "AMBIGUOUS"])
    ne = np.isin(out, ["TIMEOUT", "CLOSURE"])
    if not tp.any() or not st.any():
        return math.nan
    W, L = float(net[tp].mean()), float(net[st].mean())
    if W == L:
        return math.nan
    N = float(net[ne].mean()) if ne.any() else 0.0
    return (-L - (ne.sum() / (tp.sum() + st.sum())) * N) / (W - L)


def stats_of(out: np.ndarray, net: np.ndarray, minutes: np.ndarray, cost: np.ndarray | None, d: np.ndarray, sess: np.ndarray,
             ym: np.ndarray, days: np.ndarray, rates: dict, weeks: float, mc: bool = False, seq: dict | None = None) -> dict:
    """Statistics of an independent-trade series (already non-overlapping); the series itself is kept under _seq."""
    k, n = decided(out)
    lo, hi = H.wilson(k, n) if n else (math.nan, math.nan)
    b = matched(rates, d, sess, ym)
    w, z = net[out == "TP"], net[out != "TP"]
    # break_even: the TP share of ALL trades (stops, timeouts and closures together) at which the expectancy is zero.
    # It is NOT the comparator of the decided rate r = TP / (TP + SL) when timeouts / closures are common (it is too low
    # there). break_even_decided is: the decided rate at which the expectancy is zero, with the timeouts and closures
    # held at their measured share and mean, so r > break_even_decided exactly when exp_oz > 0. Phase C audit, 2026-11-09.
    be = float(-z.mean() / (w.mean() - z.mean())) if len(w) and len(z) and w.mean() != z.mean() else math.nan
    be_d = break_even_decided(out, net)
    wins, losses = net[net > 0].sum(), net[net < 0].sum()
    res = {"n_trades": len(out), "n_decided": n, "tp": k, "r": k / n if n else math.nan, "ci95": [lo, hi],
           "tp_all": float((out == "TP").mean()) if len(out) else math.nan, "neither": float(np.isin(out, ["TIMEOUT", "CLOSURE"]).mean()) if len(out) else math.nan,
           "matched_random": b, "p_vs_random": binom_p(k, n, b) if n and not math.isnan(b) else 1.0, "break_even": be,
           "break_even_decided": be_d,
           "exp_oz": float(net.mean()) if len(net) else math.nan, "exp_050lot_ASSUMED": float(net.mean() * b26.LOT_OZ) if len(net) else math.nan,
           "pf": float(wins / -losses) if losses < 0 else math.nan, "max_dd_050lot_ASSUMED": max_dd(net * b26.LOT_OZ),
           "minutes_median": float(np.median(minutes)) if len(minutes) else math.nan,
           "cost_oz": float(np.mean(cost)) if cost is not None and len(cost) else math.nan,
           "days": len(np.unique(days)), "per_week": len(out) / weeks if weeks else math.nan}
    if mc:
        res["mc_dd95_050lot_ASSUMED"] = mc_dd(net * b26.LOT_OZ)
    if seq is not None:
        res["_seq"] = seq
    return res


def series_stats(L: pd.DataFrame, rows: np.ndarray, rates: dict, weeks: float, mc: bool = False) -> dict:
    sub = L.iloc[rows]
    s = seq_rows(sub["dec_i"].to_numpy(), sub["exit_bar"].to_numpy(), sub["outcome"].to_numpy())
    t = sub.iloc[s]
    seq = {"fill_t": t["fill_utc"].to_numpy(), "exit_t": t["exit_utc"].to_numpy(), "d": t["d"].to_numpy(),
           "outcome": t["outcome"].to_numpy(), "net": t["net_usd_oz"].to_numpy(float), "cost": t["cost_usd_oz"].to_numpy(float),
           "minutes": t["minutes"].to_numpy(float), "session": t["session"].to_numpy()}
    res = stats_of(t["outcome"].to_numpy(), t["net_usd_oz"].to_numpy(float), t["minutes"].to_numpy(float),
                   t["cost_usd_oz"].to_numpy(float), t["d"].to_numpy(), t["session"].to_numpy(),
                   t["ym"].to_numpy(), t["nyday"].to_numpy(), rates, weeks, mc, seq)
    res["n_raw"] = len(sub)
    return res


def weeks_of(L: pd.DataFrame) -> float:
    return (L["fill_utc"].max() - L["fill_utc"].min()) / (7 * 86400.0)


# ---------------- S1: single conditions ----------------
def conditions(F: pd.DataFrame, L: pd.DataFrame, edges: dict | None = None) -> tuple[list[dict], dict]:
    """Quintiles of every feature in the trade's favour (sg_ x direction) and event flags, BUY and SELL separately."""
    nd, sg = feature_columns(F)
    out, new_edges = [], {}
    for d, dn in DIRS.items():
        Ld = L[L["d"] == d]
        rows_all = np.flatnonzero((L["d"] == d).to_numpy())
        fi = Ld["dec_i"].to_numpy()
        for col in nd + sg:
            x = F[col].to_numpy(float)[fi] * (d if col.startswith("sg_") else 1)
            key = f"{col}|{dn}"
            if edges is None:
                ok = ~np.isnan(x)
                uniq = np.unique(x[ok])
                if len(uniq) <= 3:
                    e = ("flag", [float(v) for v in uniq])
                else:
                    e = ("q", [float(v) for v in np.nanquantile(x, [0.2, 0.4, 0.6, 0.8])])
                new_edges[key] = e
            else:
                e = edges.get(key)
                if e is None:
                    continue
            kind, cuts = e
            if kind == "flag":
                bins = [(f"={v:g}", x == v) for v in cuts]
            else:
                b = np.digitize(x, cuts)
                bins = [(f"Q{q + 1}", (b == q) & ~np.isnan(x)) for q in range(5)]
            for lab, m in bins:
                if m.sum() == 0:
                    continue
                out.append({"study": "S1", "id": f"S1 {col} {lab} {dn}", "feature": col, "bin": lab, "dir": dn,
                            "family": family(col), "rows": rows_all[m]})
    return out, new_edges


# ---------------- S2: entries ----------------
def race_fill(P: b26.Path, j0: int, fill: float, d: int, s: float, so: float, k: float, horizon: int,
              fill_bar: int | None = None) -> tuple:
    """A trade already filled at `fill`. If filled inside bar `fill_bar` (limit / stop), that bar counts only against
    the trade (its stop, never its target); the path then starts at fill_bar + 1. Otherwise it starts at j0 (gap rules
    apply). Returns (outcome, exit_t, exit_px, mfe, mae)."""
    dist = MOVE * k
    tp, sl = fill + d * dist, fill - d * dist
    off = -d * s / 2.0
    if fill_bar is not None:
        adverse = (P.l[fill_bar] + off <= sl) if d > 0 else (P.h[fill_bar] + off >= sl)
        if adverse:
            return "SL", P.t[fill_bar] + P.bar, sl - d * so, 0.0, dist
        j0 = fill_bar + 1
    mfe = mae = 0.0
    end = min(j0 + horizon, P.n)
    for j in range(j0, end):
        oj, hj, lj = P.o[j] + off, P.h[j] + off, P.l[j] + off
        if d > 0:
            if oj <= sl:
                return "SL", P.t[j], oj - so, mfe, fill - oj
            if oj >= tp:
                return "TP", P.t[j], tp, dist, mae
            fav, adv, hit_t, hit_s = hj - fill, fill - lj, hj >= tp, lj <= sl
        else:
            if oj >= sl:
                return "SL", P.t[j], oj + so, mfe, oj - fill
            if oj <= tp:
                return "TP", P.t[j], tp, dist, mae
            fav, adv, hit_t, hit_s = fill - lj, hj - fill, lj <= tp, hj >= sl
        mfe, mae = max(mfe, min(fav, dist)), max(mae, min(adv, dist))
        if hit_s:
            return ("AMBIGUOUS" if hit_t else "SL"), P.t[j] + P.bar, sl - d * so, mfe, dist
        if hit_t:
            return "TP", P.t[j] + P.bar, tp, dist, mae
        if j == P.n - 1:
            return "OPEN", P.t[j] + P.bar, math.nan, mfe, mae
        if P.closure_end[j]:
            return "CLOSURE", P.t[j] + P.bar, P.c[j] + off - d * so, mfe, mae
        if j == j0 + horizon - 1:
            return "TIMEOUT", P.t[j] + P.bar, P.c[j] + off - d * so, mfe, mae
    return "OPEN", P.t[end - 1] + P.bar, math.nan, mfe, mae


def confirm_scan(P: b26.Path, i: int, d: int, k: float, xs=CONF_X, win: int = CONF_WIN) -> dict:
    """From trigger bar i (close p0): for each X, the first bar whose CLOSE is >= X*k beyond p0 in direction d, before the
    original stop (p0 -+ 15k) is touched (a bar touching it is invalidating even if it also closes beyond)."""
    p0 = P.c[i]
    stop = p0 - d * MOVE * k
    out = {}
    pending = list(xs)
    for j in range(i + 1, min(i + 1 + win, P.n)):
        if (P.l[j] <= stop) if d > 0 else (P.h[j] >= stop):
            for x in pending:
                out[x] = ("INVALIDATED", j)
            return out
        mv = d * (P.c[j] - p0)
        for x in list(pending):
            if mv >= x * k:
                out[x] = ("CONFIRMED", j)
                pending.remove(x)
        if not pending:
            return out
    for x in pending:
        out[x] = ("EXPIRED", None)
    return out


def limit_fill(P: b26.Path, j_from: int, level: float, d: int, s: float, bars: int = FILL_WIN) -> tuple[int | None, float]:
    """A limit at `level` (BUY below the market, SELL above) working on bars j_from .. j_from+bars-1: a BUY fills when the
    ask reaches it (at the open if the bar opens through it), a SELL when the bid does."""
    for j in range(j_from, min(j_from + bars, P.n)):
        if d > 0:
            ask_o, ask_l = P.o[j] + s / 2, P.l[j] + s / 2
            if ask_o <= level:
                return j, ask_o
            if ask_l <= level:
                return j, level
        else:
            bid_o, bid_h = P.o[j] - s / 2, P.h[j] - s / 2
            if bid_o >= level:
                return j, bid_o
            if bid_h >= level:
                return j, level
        if P.closure_end[j]:
            return None, math.nan
    return None, math.nan


def stop_fill(P: b26.Path, i: int, level: float, d: int, s: float, si: float, k: float, win: int = CONF_WIN) -> tuple:
    """A buy stop (sell stop) at `level` from trigger bar i, cancelled once the original stop p0 -+ 15k trades. Returns
    (bar, fill) or (None, nan). A bar that touches both the order and the original stop fills (the conservative case)."""
    p0 = P.c[i]
    cancel = p0 - d * MOVE * k
    for j in range(i + 1, min(i + 1 + win, P.n)):
        if d > 0:
            ask_o, ask_h = P.o[j] + s / 2, P.h[j] + s / 2
            if ask_o >= level:
                return j, ask_o + si
            if ask_h >= level:
                return j, level + si
            if P.l[j] <= cancel:
                return None, math.nan
        else:
            bid_o, bid_l = P.o[j] - s / 2, P.l[j] - s / 2
            if bid_o <= level:
                return j, bid_o - si
            if bid_l <= level:
                return j, level - si
            if P.h[j] >= cancel:
                return None, math.nan
        if P.closure_end[j]:
            return None, math.nan
    return None, math.nan


def entry_trades(P: b26.Path, trig: list[tuple], costs: dict, horizon: int = 192, xs=CONF_X) -> dict:
    """trig: (i, d, k, level or nan). For every mode, the list of trades (one per filled trigger) as dicts."""
    out = {m: [] for m in entry_modes(xs)}
    out["_funnel"] = []                                           # (d, {X: status}) per trigger, aligned with trig

    def cost_at(j, k):
        return tuple(v * k for v in costs[j])

    def run_and_book(mode, i, d, k, j_fill, fill, s, so, cm, paid_in, fill_bar=None):
        oc, xt, xpx, mfe, mae = race_fill(P, j_fill, fill, d, s, so, k, horizon, fill_bar=fill_bar)
        if oc == "OPEN":
            return
        net = (d * (xpx - fill) - cm) / k
        cost = (s + paid_in + (0.0 if oc == "TP" else so) + cm) / k
        out[mode].append({"i": i, "d": d, "fill_t": P.t[j_fill], "exit_t": xt, "outcome": oc, "net": net, "cost": cost,
                          "minutes": (xt - P.t[j_fill]) / 60.0, "mfe": mfe / k, "mae": mae / k})

    for i, d, k, lv in trig:
        if i + 1 >= P.n or P.t[i + 1] - P.t[i] != P.bar:
            out["_funnel"].append((d, None))
            continue
        f = i + 1
        s, si, so, cm = cost_at(f, k)
        run_and_book("IMM", i, d, k, f, P.o[f] + d * (s / 2 + si), s, so, cm, si)
        conf = confirm_scan(P, i, d, k, xs)
        out["_funnel"].append((d, {x: conf[x][0] for x in xs}))
        for x in xs:
            st, j = conf[x]
            if st != "CONFIRMED" or j + 1 >= P.n or P.t[j + 1] - P.t[j] != P.bar:
                continue
            s, si, so, cm = cost_at(j + 1, k)
            run_and_book(f"CONF_{x}", i, d, k, j + 1, P.o[j + 1] + d * (s / 2 + si), s, so, cm, si)
            jb, fl = limit_fill(P, j + 1, P.c[i] + d * x * k, d, s)
            if jb is not None:
                s, si, so, cm = cost_at(jb, k)
                run_and_book(f"RETEST_{x}", i, d, k, jb, fl, s, so, cm, 0.0, fill_bar=jb)
        for x in xs:
            s, si, so, cm = cost_at(f, k)
            jb, fl = stop_fill(P, i, P.c[i] + d * x * k, d, s, si, k)
            if jb is not None:
                run_and_book(f"STOP_{x}", i, d, k, jb, fl, s, so, cm, si, fill_bar=jb)
        if not math.isnan(lv) and 0.5 * k <= d * (P.c[i] - lv) <= 14 * k:
            s, si, so, cm = cost_at(f, k)
            jb, fl = limit_fill(P, f, lv, d, s)
            if jb is not None:
                run_and_book("LIMIT", i, d, k, jb, fl, s, so, cm, 0.0, fill_bar=jb)
    return out


def entry_modes(xs=CONF_X) -> list[str]:
    return ["IMM", *[f"CONF_{x}" for x in xs], *[f"RETEST_{x}" for x in xs], *[f"STOP_{x}" for x in xs], "LIMIT"]


def triggers(F: pd.DataFrame, L: pd.DataFrame, fam: str, k_of: np.ndarray) -> list[tuple]:
    """Trigger bars of a family inside the scored, eligible set (the bars that have a B26 label)."""
    elig = np.unique(L["dec_i"].to_numpy())
    if fam == "EVERY_HOUR":
        sel = elig[::4]
        return [(int(i), d, float(k_of[i]), math.nan) for i in sel for d in (1, -1)]
    ev = F[EVENT_COL[fam]].to_numpy(float)
    lv = F[LEVEL_COL[fam]].to_numpy(float) if fam in LEVEL_COL else np.full(len(F), np.nan)
    sel = elig[ev[elig] != 0]
    return [(int(i), int(np.sign(ev[i])), float(k_of[i]), float(lv[i])) for i in sel]


def trade_stats(tr: list[dict], n_trig: int, P: b26.Path, rates: dict, sess_of: dict, weeks: float, mc: bool = False) -> dict:
    if not tr:
        return {"n_triggers": n_trig, "n_filled": 0}
    tr = sorted(tr, key=lambda x: x["fill_t"])
    keep, cur = [], -1
    for x in tr:
        if x["fill_t"] >= cur:
            keep.append(x)
            cur = x["exit_t"]
    def a(key):
        return np.asarray([x[key] for x in keep])

    ft = a("fill_t")
    fidx = pd.to_datetime(ft, unit="s", utc=True)
    sess = np.asarray([sess_of.get(int(t), "OFF") for t in ft])
    ym = fidx.strftime("%Y-%m").to_numpy()
    days = (fidx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)).normalize().strftime("%Y-%m-%d").to_numpy()
    seq = {"fill_t": ft, "exit_t": a("exit_t"), "d": a("d"), "outcome": a("outcome"), "net": a("net"), "cost": a("cost"),
           "minutes": a("minutes"), "session": sess}
    res = stats_of(a("outcome"), a("net"), a("minutes"), a("cost"), a("d"), sess, ym, days, rates, weeks, mc, seq)
    res.update({"n_triggers": n_trig, "n_filled": len(tr), "fill_rate": len(tr) / n_trig if n_trig else math.nan,
                "exp_per_trigger_oz": float(sum(x["net"] for x in tr) / n_trig) if n_trig else math.nan,
                "mfe_mean": float(a("mfe").mean()), "mae_mean": float(a("mae").mean()),
                "minutes_tp_median": float(np.median(a("minutes")[a("outcome") == "TP"])) if (a("outcome") == "TP").any() else math.nan,
                "false_entries": float((a("outcome") != "TP").mean())})
    return res


# ---------------- S3: probability models ----------------
BASE_MODELS = ("LR", "HGB", "LGBM")
MODELS = ("LR", "HGB", "LGBM", "LGBM_SEP", "ENS")


def design(F: pd.DataFrame, L: pd.DataFrame, hmm: np.ndarray | None) -> tuple[np.ndarray, list[str]]:
    """One row per (decision bar, direction): direction-free features, signed features x direction, the HMM state
    probabilities, the signed CUSUM, and the direction."""
    nd, sg = feature_columns(F)
    i = L["dec_i"].to_numpy()
    d = L["d"].to_numpy(float)[:, None]
    X = [F[nd].to_numpy(float)[i], F[sg].to_numpy(float)[i] * d]
    names = nd + sg
    if hmm is not None:
        X += [hmm[i, :3], hmm[i, 3:4] * d]
        names += ["hmm_calm", "hmm_mid", "hmm_wild", "hmm_cusum_signed"]
    X.append(d)
    return np.column_stack(X), [*names, "direction"]


class Fitted:
    """The base models fitted on one training set; predict() gives the raw probability of each registered model
    (ENS = the mean of LR, HGB and LGBM; LGBM_SEP = separate BUY and SELL LGBMs)."""

    def __init__(self, X: np.ndarray, y: np.ndarray, d: np.ndarray, models=MODELS):
        self.m = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for name in BASE_MODELS:
                if name in models or "ENS" in models:
                    Xf = np.nan_to_num(X) if name == "LR" else X
                    self.m[name] = b22.make(name).fit(Xf, y)
            if "LGBM_SEP" in models:
                self.m["LGBM_SEP"] = {dd: b22.make("LGBM").fit(X[d == dd], y[d == dd]) for dd in (1, -1)}
        self.models = models

    def predict(self, X: np.ndarray, d: np.ndarray) -> dict:
        out = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for name in BASE_MODELS:
                if name in self.m:
                    out[name] = self.m[name].predict_proba(np.nan_to_num(X) if name == "LR" else X)[:, 1]
            if "LGBM_SEP" in self.m:
                p = np.full(len(X), np.nan)
                for dd in (1, -1):
                    if (d == dd).any():
                        p[d == dd] = self.m["LGBM_SEP"][dd].predict_proba(X[d == dd])[:, 1]
                out["LGBM_SEP"] = p
        if "ENS" in self.models:
            out["ENS"] = np.mean([out[n] for n in BASE_MODELS], axis=0)
        return {k: v for k, v in out.items() if k in self.models}


def isotonic(p_cal, y_cal, p):
    from sklearn.isotonic import IsotonicRegression
    return IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p_cal, y_cal).predict(p)


def hmm_block(h1_fit: pd.DataFrame, h1_apply: pd.DataFrame, t_close: np.ndarray, seed: int = 7) -> np.ndarray:
    """B22's 3-state HMM fitted on h1_fit only, forward-filtered over h1_apply, read at each decision's close."""
    from hmmlearn.hmm import GaussianHMM

    def feats(h1):
        c1 = h1["close"].to_numpy(float)
        r = np.diff(np.log(c1), prepend=np.nan) * 100
        return np.column_stack([np.nan_to_num(r), np.abs(np.nan_to_num(r))]), r

    Xf, _ = feats(h1_fit)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mdl = GaussianHMM(n_components=3, covariance_type="diag", n_iter=50, random_state=seed).fit(Xf[1:])
    Xa, ra = feats(h1_apply)
    probs = b22.hmm_filter(mdl, Xa)[:, np.argsort(mdl.means_[:, 1])]
    ct = ta.epoch_s(h1_apply.index).astype(np.int64) + 3600
    cus = b22.cusum(np.nan_to_num(ra))
    return np.column_stack([b22.asof(ct, probs[:, j], t_close) for j in range(3)] + [b22.asof(ct, cus, t_close)])


def split_fit_cal(t_fill: np.ndarray, t_exit: np.ndarray, usable: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Time split of a training set: calibration = the last 20% of its time span (by fill time); the fitting rows must
    have exited one day before the calibration starts (rows are NOT time-ordered: BUY rows come before SELL rows)."""
    t_cut = np.quantile(t_fill[usable], 0.8)
    fit_m = usable & (t_exit < t_cut - 86400)
    cal_m = usable & (t_fill >= t_cut)
    return fit_m, cal_m


def walk_forward(F: pd.DataFrame, L: pd.DataFrame, h1: pd.DataFrame, models=MODELS, start: str = "2021-01-01",
                 drop_family: str | None = None, log=print) -> dict:
    """Quarterly purged walk-forward: every test row's calibrated out-of-sample probability, per model, and the
    threshold of each (direction, q) from the training window's own calibration rows."""
    t_fill, t_exit = L["fill_utc"].to_numpy(), L["exit_utc"].to_numpy()
    y = (L["outcome"] == "TP").to_numpy(int)
    d = L["d"].to_numpy()
    tc = ta.epoch_s(F.index).astype(np.int64) + 900
    end = pd.Timestamp(int(t_fill.max()), unit="s", tz="UTC") + pd.Timedelta(seconds=1)
    res = {m: {"p": np.full(len(L), np.nan), "raw": np.full(len(L), np.nan), "thr": {}} for m in models}
    names = None
    for qs, qe in b22.quarters(start, end):
        s0, s1 = int(qs.timestamp()), int(qe.timestamp())
        te = (t_fill >= s0) & (t_fill < s1)
        usable = (t_exit < s0 - 86400) & (L["outcome"] != "OPEN").to_numpy()
        if te.sum() == 0 or usable.sum() < 5000:
            continue
        hm = hmm_block(h1[h1.index < qs - pd.Timedelta(days=1)], h1, tc)
        X, names = design(F, L, hm)
        if drop_family:
            keep = [j for j, nm in enumerate(names) if family(nm) != drop_family or nm == "direction"]
            X = X[:, keep]
        fit_m, cal_m = split_fit_cal(t_fill, t_exit, usable)
        fm = Fitted(X[fit_m], y[fit_m], d[fit_m], models)
        p_cal, p_te = fm.predict(X[cal_m], d[cal_m]), fm.predict(X[te], d[te])
        for m in models:
            res[m]["p"][te] = isotonic(p_cal[m], y[cal_m], p_te[m])
            res[m]["raw"][te] = p_te[m]
            for (dd, q), v in thresholds(p_cal[m], y[cal_m], d[cal_m]).items():
                res[m]["thr"].setdefault((dd, q), []).append((s0, v))
        log(f"[B27] walk-forward {qs.date()}: test {int(te.sum())}, fit {int(fit_m.sum())}, calibrate {int(cal_m.sum())}")
    return {"res": res, "names": names}


def thresholds(p_cal: np.ndarray, y_cal: np.ndarray, d_cal: np.ndarray, qs=QS) -> dict:
    """The (direction, q) thresholds from a window's calibration rows, on the score SELECT_ON names."""
    sc = p_cal if SELECT_ON == "raw" else isotonic(p_cal, y_cal, p_cal)
    return {(dd, q): float(np.quantile(sc[d_cal == dd], 1 - q)) for dd in (1, -1) for q in qs}


def wf_selections(L: pd.DataFrame, wf: dict, model: str) -> dict:
    """Rows selected for each (direction, q): the test score (SELECT_ON) >= its own training window's threshold."""
    p = wf["res"][model]["raw" if SELECT_ON == "raw" else "p"]
    t_fill = L["fill_utc"].to_numpy()
    d = L["d"].to_numpy()
    sel = {}
    for (dd, q), lst in wf["res"][model]["thr"].items():
        thr = np.full(len(L), np.nan)
        for j, (s0, v) in enumerate(lst):
            s1 = lst[j + 1][0] if j + 1 < len(lst) else 10 ** 12
            thr[(t_fill >= s0) & (t_fill < s1)] = v
        sel[(dd, q)] = np.flatnonzero((d == dd) & ~np.isnan(p) & ~np.isnan(thr) & (p >= thr))
    return sel


def auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    m = ~np.isnan(p)
    return float(roc_auc_score(y[m], p[m])) if m.sum() and len(np.unique(y[m])) == 2 else math.nan


def reliability(y: np.ndarray, p: np.ndarray) -> list[dict]:
    m = ~np.isnan(p)
    y, p = y[m], p[m]
    if len(p) == 0:
        return []
    edges = np.unique(np.quantile(p, np.linspace(0, 1, 11)))
    b = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
    return [{"bin": int(k), "p_mean": float(p[b == k].mean()), "observed": float(y[b == k].mean()), "n": int((b == k).sum())}
            for k in range(len(edges) - 1) if (b == k).any()]


def final_models(F: pd.DataFrame, L: pd.DataFrame, h1: pd.DataFrame, models=MODELS) -> dict:
    """Refitted on all development (calibrated on its last 20%), with thresholds from the calibration rows."""
    y = (L["outcome"] == "TP").to_numpy(int)
    d = L["d"].to_numpy()
    tc = ta.epoch_s(F.index).astype(np.int64) + 900
    X, _ = design(F, L, hmm_block(h1, h1, tc))
    fit_m, cal_m = split_fit_cal(L["fill_utc"].to_numpy(), L["exit_utc"].to_numpy(), (L["outcome"] != "OPEN").to_numpy())
    fm = Fitted(X[fit_m], y[fit_m], d[fit_m], models)
    p_cal = fm.predict(X[cal_m], d[cal_m])
    thr = {m: thresholds(p_cal[m], y[cal_m], d[cal_m]) for m in models}
    return {"fitted": fm, "p_cal": p_cal, "y_cal": y[cal_m], "thr": thr, "h1": h1}


def apply_final(FM: dict, F: pd.DataFrame, L: pd.DataFrame, h1_apply: pd.DataFrame, scores: bool = False) -> dict:
    """Calibrated probabilities of the final models on new rows; with scores=True, the score that is compared with
    FM["thr"] (raw or calibrated, per SELECT_ON)."""
    tc = ta.epoch_s(F.index).astype(np.int64) + 900
    X, _ = design(F, L, hmm_block(FM["h1"], h1_apply, tc))
    raw = FM["fitted"].predict(X, L["d"].to_numpy())
    if scores and SELECT_ON == "raw":
        return raw
    return {m: isotonic(FM["p_cal"][m], FM["y_cal"], p) for m, p in raw.items()}


# ---------------- S4: feature ranking ----------------
def ranking(F: pd.DataFrame, L: pd.DataFrame, h1: pd.DataFrame, wf: dict, base_auc: float, log=print) -> dict:
    y = (L["outcome"] == "TP").to_numpy(int)
    d = L["d"].to_numpy()
    t_fill, t_exit = L["fill_utc"].to_numpy(), L["exit_utc"].to_numpy()
    test = ~np.isnan(wf["res"]["LGBM"]["p"])
    t_split = int(t_fill[test].min())
    tc = ta.epoch_s(F.index).astype(np.int64) + 900
    X, names = design(F, L, hmm_block(h1[h1.index < pd.Timestamp(t_split - 86400, unit="s", tz="UTC")], h1, tc))
    out = {"univariate_auc": {nm: auc(y, X[:, j]) for j, nm in enumerate(names)}, "ablation": {}, "permutation_auc_drop": {}}
    for fam in FAMILY_OF:
        w = walk_forward(F, L, h1, ("LGBM",), drop_family=fam, log=lambda *_: None)
        a_ = auc(y, w["res"]["LGBM"]["p"])
        out["ablation"][fam] = {"auc_without": a_, "change": a_ - base_auc}
        log(f"[B27] ablation without {fam}: AUC {a_:.4f} ({a_ - base_auc:+.4f})")
    trm = (t_exit < t_split - 86400) & (L["outcome"] != "OPEN").to_numpy()
    mdl = Fitted(X[trm], y[trm], d[trm], ("LGBM",)).m["LGBM"]
    base = auc(y[test], mdl.predict_proba(X[test])[:, 1])
    rng = H.seeded_rng(SEED)
    for j, nm in enumerate(names):
        drops = []
        for _ in range(3):
            Xp = X[test].copy()
            Xp[:, j] = rng.permutation(Xp[:, j])
            drops.append(base - auc(y[test], mdl.predict_proba(Xp)[:, 1]))
        out["permutation_auc_drop"][nm] = float(np.mean(drops))
    out["permutation_base_auc"] = base
    return out


# ---------------- S5: regimes ----------------
def regimes(F: pd.DataFrame, rel: np.ndarray) -> dict:
    adx = F["nd_adx"].to_numpy(float)
    di = F["sg_di_diff"].to_numpy(float)
    t1 = F["sg_trend_1h"].to_numpy(float)
    ar = F["nd_atr_ratio"].to_numpy(float)
    tc = F["t_close"].to_numpy()
    liq = (pd.Series(((F["sg_sweep"] != 0) | (F["sg_grab"] != 0)).to_numpy(float)).rolling(4, min_periods=1).max() > 0).to_numpy()
    j = np.searchsorted(rel, tc, "right") - 1
    since = np.where(j >= 0, tc - rel[np.clip(j, 0, None)], 10 ** 9)
    jn = np.searchsorted(rel, tc, "left")
    to_next = np.where(jn < len(rel), rel[np.clip(jn, 0, len(rel) - 1)] - tc, 10 ** 9)
    return {"STRONG_BULL": (adx >= 25) & (di > 0) & (t1 > 0), "STRONG_BEAR": (adx >= 25) & (di < 0) & (t1 < 0),
            "WEAK_BULL": (adx >= 18) & (adx < 25) & (di > 0), "WEAK_BEAR": (adx >= 18) & (adx < 25) & (di < 0),
            "SIDEWAYS": adx < 18, "EXPANSION": ar >= 1.3, "CONTRACTION": ar <= 0.75,
            "REVERSAL": F["sg_flip"].to_numpy(float) != 0, "NEWS": (since <= 7200) | (to_next <= 1800),
            "POST_NEWS": (since > 7200) & (since <= 21600), "LIQUIDITY": liq}


# ---------------- S6: intermarket (2026, descriptive) ----------------
INTER = {"DXY": "DX-Y.NYB_60m", "US10Y": "_TNX_60m", "EURUSD": "EURUSD_X_60m", "SILVER": "SI_F_60m", "SPX": "_GSPC_60m"}


def load_any(d: str) -> pd.DataFrame | None:
    import glob
    parts = [pd.read_csv(f, index_col=0, parse_dates=True) for f in sorted(glob.glob(os.path.join(d, "*.csv")))]
    if not parts:
        return None
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    idx = pd.DatetimeIndex(df.index)
    df.index = idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")
    return sources.drop_offgrid(df).dropna(subset=["close"])


def intermarket(md: str, F: pd.DataFrame) -> dict:
    """The signed 4-hour change of each series, read from its last 1h bar CLOSED by each decision."""
    out = {}
    tc = F["t_close"].to_numpy()
    for name, folder in INTER.items():
        df = load_any(os.path.join(md, folder)) if os.path.isdir(os.path.join(md, folder)) else None
        if df is None or len(df) < 10:
            continue
        ct = ta.epoch_s(df.index).astype(np.int64) + 3600
        c = df["close"].to_numpy(float)
        out[name] = b22.asof(ct, np.r_[np.full(4, np.nan), c[4:] / c[:-4] - 1], tc)
    return out


# ---------------- selection ----------------
def flag(cands: list[dict]) -> None:
    passed = bh([c_["stats"].get("p_vs_random", 1.0) for c_ in cands])
    for c_, ok in zip(cands, passed, strict=True):
        s = c_["stats"]
        n = s.get("n_decided", 0)
        c_["bh"] = bool(ok)
        c_["informative"] = bool(ok and n >= MIN_N and s["ci95"][0] > s["matched_random"])
        c_["tradeable"] = bool(c_["informative"] and s["ci95"][0] > s["break_even_decided"] and s["exp_oz"] > 0)


def frozen_set(cands: list[dict]) -> list[dict]:
    def lb(c_):
        return c_["stats"]["ci95"][0] if c_["stats"].get("n_decided") else -1.0

    inf = sorted([c_ for c_ in cands if c_["informative"]], key=lb, reverse=True)[:40]
    big = sorted([c_ for c_ in cands if c_["stats"].get("n_decided", 0) >= MIN_N], key=lb, reverse=True)[:10]
    small = sorted([c_ for c_ in cands if LOW_N <= c_["stats"].get("n_decided", 0) < MIN_N], key=lb, reverse=True)[:10]
    seen, out = set(), []
    for board, group in (("informative", inf), ("top_n300", big), ("low_frequency", small)):
        for c_ in group:
            if c_["id"] not in seen:
                seen.add(c_["id"])
                c_["board"] = board
                out.append(c_)
    return out


SUMMARY_KEYS = ("n_raw", "n_trades", "n_decided", "r", "ci95", "matched_random", "p_vs_random", "break_even", "break_even_decided", "exp_oz",
                "exp_050lot_ASSUMED", "pf", "max_dd_050lot_ASSUMED", "mc_dd95_050lot_ASSUMED", "minutes_median", "cost_oz",
                "per_week", "days", "tp_all", "neither", "n_triggers", "n_filled", "fill_rate", "exp_per_trigger_oz", "mfe_mean",
                "mae_mean", "minutes_tp_median", "false_entries")


def summary_row(stats: dict) -> dict:
    return {k: stats.get(k) for k in SUMMARY_KEYS}


def pareto(points: list[dict]) -> list[str]:
    """Ids not dominated on (r up, per_week up, exp_oz up, max_dd down)."""
    keep = []
    for a in points:
        dom = any(b is not a and b["r"] >= a["r"] and b["per_week"] >= a["per_week"] and b["exp_oz"] >= a["exp_oz"]
                  and b["dd"] <= a["dd"] and (b["r"] > a["r"] or b["per_week"] > a["per_week"] or b["exp_oz"] > a["exp_oz"]
                                              or b["dd"] < a["dd"]) for b in points)
        if not dom:
            keep.append(a["id"])
    return keep


# ---------------- the run ----------------
def load_pops(rd: str, store5: str, store60: str) -> dict:
    """Development 2020-22 (15m, scaled) and 2026 (15m, literal; the research history extended by the live store to
    2026-11-06), with the live store's 5m bars for 5m exits. No validation or holdout bar is read."""
    m15d = sources.repair_reopen(H.partition(history.load(rd, "XAU/USD", "15min"), "development"), 900)
    h1d = sources.repair_reopen(H.partition(history.load(rd, "XAU/USD", "1h"), "development"), 3600)
    lo = H.HOLD[1]
    m15r = history.load(rd, "XAU/USD", "15min")
    m15r = sources.repair_reopen(m15r[m15r.index >= lo], 900)
    df5 = b26.load_store(store5, 300)
    ext = sources.resample_ohlc(df5, "15min")
    m15r = pd.concat([m15r, ext[ext.index > m15r.index[-1]]]).sort_index()
    h1r = history.load(rd, "XAU/USD", "1h")
    h1r = sources.repair_reopen(h1r[h1r.index >= lo], 3600)
    s60 = b26.load_store(store60, 3600)
    h1r = pd.concat([h1r, s60[s60.index > h1r.index[-1]]]).sort_index()
    return {"DEV": {"m15": m15d, "h1": h1d, "score_from": pd.Timestamp("2020-04-01", tz="UTC"), "scale": True},
            "Y2026": {"m15": m15r, "h1": h1r, "score_from": pd.Timestamp("2026-03-01", tz="UTC"), "scale": False, "df5": df5}}


def prepare(P_: dict, log=print) -> None:
    from .. import sessions

    P_["F"] = build_features(P_["m15"], P_["h1"], log)
    P_["F"]["t_close"] = ta.epoch_s(P_["m15"].index).astype(np.int64) + 900
    L = labels("B27", P_["m15"], P_["h1"], P_["score_from"], P_["scale"])
    P_["Lp"] = L[L["outcome"] != "OPEN"].reset_index(drop=True)
    P_["rates"] = base_rates(P_["Lp"])
    P_["weeks"] = weeks_of(P_["Lp"])
    P_["path"] = b26.make_path(P_["m15"], 900)
    c = P_["m15"]["close"].to_numpy(float)
    P_["k"] = c / b26.REF if P_["scale"] else np.ones(len(c))
    idx = P_["m15"].index
    eng = H.cost_pts(idx, slippage=0.0, commission_lot=0.0)
    P_["costs"] = [(float(v), 0.20, 0.20, 0.07) for v in eng]
    cal = sessions.calendar(idx)
    a_, lo_, ny_ = (cal[x].to_numpy(bool) for x in ("in_asian", "in_london", "in_ny"))
    sess = np.where(a_, "ASIA", np.where(lo_ & ny_, "OVERLAP", np.where(lo_, "LONDON", np.where(ny_, "NY", "OFF"))))
    P_["sess_of"] = dict(zip(ta.epoch_s(idx).astype(np.int64).tolist(), sess.tolist(), strict=True))


def s2_family(P_: dict, fam: str) -> tuple[list[tuple], dict]:
    trig = triggers(P_["F"], P_["Lp"], fam, P_["k"])
    return trig, entry_trades(P_["path"], trig, P_["costs"])


def s2_stats(P_: dict, trig: list[tuple], trades: dict, d: int, mode: str, mc: bool = False) -> dict:
    tr = [x for x in trades[mode] if x["d"] == d]
    return trade_stats(tr, sum(1 for x in trig if x[1] == d), P_["path"], P_["rates"], P_["sess_of"], P_["weeks"], mc)


def run(a, log=print) -> dict:
    pops = load_pops(a.rd, a.store5, a.store60)
    rel = _release_times()
    D, Y = pops["DEV"], pops["Y2026"]
    prepare(D, log)
    prepare(Y, log)
    Y["L5p"] = labels_5m(Y["Lp"], Y["m15"], Y["df5"])
    Y["L5p"] = Y["L5p"][Y["L5p"]["outcome"] != "OPEN"].reset_index(drop=True)
    Y["rates5"], Y["weeks5"] = base_rates(Y["L5p"]), weeks_of(Y["L5p"])
    out = {"registration": REG, "utc": datetime.now(timezone.utc).isoformat(), "not_tested": NOT_TESTED, "baseline": {},
           "data": {"DEV": {"bars": len(D["m15"]), "hash": H.data_hash(D["m15"]), "rows": len(D["Lp"])},
                    "Y2026": {"bars": len(Y["m15"]), "hash": H.data_hash(Y["m15"]), "rows": len(Y["Lp"]), "rows_5m": len(Y["L5p"])}}}
    for nm, L_, rates, weeks in (("DEV", D["Lp"], D["rates"], D["weeks"]), ("Y2026", Y["Lp"], Y["rates"], Y["weeks"]),
                                 ("Y2026_5m", Y["L5p"], Y["rates5"], Y["weeks5"])):
        for d, dn in DIRS.items():
            out["baseline"][f"{nm} {dn}"] = summary_row(series_stats(L_, np.flatnonzero((L_["d"] == d).to_numpy()), rates, weeks, mc=True))

    s1, edges = conditions(D["F"], D["Lp"])
    for c_ in s1:
        c_["stats"] = series_stats(D["Lp"], c_["rows"], D["rates"], D["weeks"])
    flag(s1)
    log(f"[B27] S1: {len(s1)} conditions, {sum(c_['bh'] for c_ in s1)} BH, {sum(c_['informative'] for c_ in s1)} informative")

    s2, funnel = [], {}
    for fam in FAMILIES:
        trig, trades = s2_family(D, fam)
        for d, dn in DIRS.items():
            for mode in entry_modes():
                st = s2_stats(D, trig, trades, d, mode)
                if st.get("n_filled"):
                    s2.append({"study": "S2", "id": f"S2 {fam} {mode} {dn}", "family": fam, "mode": mode, "dir": dn, "stats": st})
            fl = [f_ for dd, f_ in trades["_funnel"] if dd == d and f_ is not None]
            for x in CONF_X:
                funnel[f"{fam} {dn} X{x}"] = {st_: sum(1 for f_ in fl if f_[x] == st_) for st_ in ("CONFIRMED", "INVALIDATED", "EXPIRED")}
        log(f"[B27] S2 {fam}: {len(trig)} triggers")
    flag(s2)

    wf = walk_forward(D["F"], D["Lp"], D["h1"], MODELS, log=log)
    yD = (D["Lp"]["outcome"] == "TP").to_numpy(int)
    dD = D["Lp"]["d"].to_numpy()
    s3, s3_info = [], {}
    for m in MODELS:
        p = wf["res"][m]["p"]
        tm = ~np.isnan(p)
        s3_info[m] = {"auc": auc(yD, p), "auc_buy": auc(yD[dD == 1], p[dD == 1]), "auc_sell": auc(yD[dD == -1], p[dD == -1]),
                      "brier": float(np.mean((p[tm] - yD[tm]) ** 2)), "brier_constant": float(yD[tm].mean() * (1 - yD[tm].mean())),
                      "reliability": reliability(yD, p), "n_test_rows": int(tm.sum())}
        for (dd, q), rows in wf_selections(D["Lp"], wf, m).items():
            s3.append({"study": "S3", "id": f"S3 {m} top{q * 100:g}% {DIRS[dd]}", "model": m, "q": q, "dir": DIRS[dd], "rows": rows})
    for c_ in s3:
        c_["stats"] = series_stats(D["Lp"], c_["rows"], D["rates"], D["weeks"])
    flag(s3)
    log("[B27] S3 AUC " + json.dumps({m: round(v["auc"], 4) for m, v in s3_info.items()}))

    rank = ranking(D["F"], D["Lp"], D["h1"], wf, s3_info["LGBM"]["auc"], log)

    s5 = []
    regD = regimes(D["F"], rel)
    for name_, mask in regD.items():
        for d, dn in DIRS.items():
            rows = np.flatnonzero((D["Lp"]["d"] == d).to_numpy() & mask[D["Lp"]["dec_i"].to_numpy()])
            if len(rows):
                s5.append({"study": "S5", "id": f"S5 {name_} {dn}", "regime": name_, "dir": dn, "rows": rows})
    for c_ in s5:
        c_["stats"] = series_stats(D["Lp"], c_["rows"], D["rates"], D["weeks"])
    flag(s5)

    # ---- freeze on development, check on 2026 ----
    frozen = frozen_set(s1 + s2 + s3 + s5)
    FM = final_models(D["F"], D["Lp"], D["h1"])
    pY = apply_final(FM, Y["F"], Y["Lp"], Y["h1"], scores=True)
    pos15 = {k_: j for j, k_ in enumerate(zip(Y["Lp"]["dec_i"].astype(int), Y["Lp"]["d"].astype(int), strict=True))}
    key5 = list(zip(Y["L5p"]["dec_i"].astype(int), Y["L5p"]["d"].astype(int), strict=True))
    map5 = np.asarray([pos15.get(k_, -1) for k_ in key5])
    s1y = {c_["id"]: c_["rows"] for c_ in conditions(Y["F"], Y["Lp"], edges)[0]}
    regY = regimes(Y["F"], rel)
    fam_cache = {}
    for c_ in frozen:
        d = 1 if c_["dir"] == "BUY" else -1
        y_rows = None
        if c_["study"] == "S1":
            y_rows = s1y.get(c_["id"], np.zeros(0, int))
        elif c_["study"] == "S5":
            y_rows = np.flatnonzero((Y["Lp"]["d"] == d).to_numpy() & regY[c_["regime"]][Y["Lp"]["dec_i"].to_numpy()])
        elif c_["study"] == "S3":
            y_rows = np.flatnonzero((Y["Lp"]["d"] == d).to_numpy() & (pY[c_["model"]] >= FM["thr"][c_["model"]][(d, c_["q"])]))
        if c_["study"] == "S2":
            if c_["family"] not in fam_cache:
                fam_cache[c_["family"]] = (s2_family(D, c_["family"]), s2_family(Y, c_["family"]))
            (tD, trD), (tY, trY) = fam_cache[c_["family"]]
            c_["stats"] = s2_stats(D, tD, trD, d, c_["mode"], mc=True)
            c_["y2026"] = s2_stats(Y, tY, trY, d, c_["mode"])
        else:
            c_["stats"] = series_stats(D["Lp"], c_["rows"], D["rates"], D["weeks"], mc=True)
            c_["y2026"] = series_stats(Y["Lp"], y_rows, Y["rates"], Y["weeks"])
            sel = set(zip(Y["Lp"]["dec_i"].to_numpy()[y_rows].tolist(), Y["Lp"]["d"].to_numpy()[y_rows].tolist(), strict=True))
            y5 = np.flatnonzero(np.asarray([k_ in sel for k_ in key5], bool)) if len(key5) else np.zeros(0, int)
            if len(y5):
                c_["y2026_5m"] = series_stats(Y["L5p"], y5, Y["rates5"], Y["weeks5"])
    for c_, ph in zip(frozen, holm([c_["y2026"].get("p_vs_random", 1.0) for c_ in frozen]), strict=True):
        y_ = c_["y2026"]
        c_["y2026_holm_p"] = ph
        c_["holds_2026"] = bool(ph < 0.05 and y_.get("n_decided", 0) and y_["ci95"][0] > y_["matched_random"])
        c_["above_break_even_2026"] = bool(y_.get("n_decided", 0) and y_["ci95"][0] > y_["break_even_decided"])
    _ = map5

    def pack(c_):
        keep = {k_: c_.get(k_) for k_ in ("id", "study", "family", "feature", "bin", "mode", "model", "q", "regime", "dir", "board",
                                          "bh", "informative", "tradeable", "y2026_holm_p", "holds_2026", "above_break_even_2026")}
        keep["dev"] = summary_row(c_["stats"])
        for k_ in ("y2026", "y2026_5m"):
            if k_ in c_:
                keep[k_] = summary_row(c_[k_])
        return keep

    out["counts"] = {s: {"tested": len(v), "bh": sum(c_["bh"] for c_ in v), "informative": sum(c_["informative"] for c_ in v),
                         "tradeable": sum(c_["tradeable"] for c_ in v)} for s, v in (("S1", s1), ("S2", s2), ("S3", s3), ("S5", s5))}
    out["frozen"] = [pack(c_) for c_ in frozen]
    for key, lst in (("S1", s1), ("S2", s2), ("S3", s3), ("S5", s5)):
        out[key] = [pack(c_) for c_ in lst]
    out["S2_confirmation_funnel"] = funnel
    out["S3_models"] = s3_info
    out["S4"] = rank

    def pts(lst, filt, min_n):
        return [{"id": c_["id"], "r": c_["stats"]["r"], "per_week": c_["stats"]["per_week"], "exp_oz": c_["stats"]["exp_oz"],
                 "dd": c_["stats"]["max_dd_050lot_ASSUMED"]} for c_ in lst if filt(c_) and c_["stats"].get("n_decided", 0) >= min_n]

    out["S2_pareto"] = {f"{fam} {dn}": pareto(pts(s2, lambda c_, fam=fam, dn=dn: c_["family"] == fam and c_["dir"] == dn, 100))
                        for fam in FAMILIES for dn in DIRS.values()}
    out["S3_pareto"] = {f"{m} {dn}": pareto(pts(s3, lambda c_, m=m, dn=dn: c_["model"] == m and c_["dir"] == dn, 30))
                        for m in MODELS for dn in DIRS.values()}

    s6 = {}
    for name_, x in (intermarket(a.md, Y["F"]) if a.md else {}).items():
        for d, dn in DIRS.items():
            xi = x[Y["Lp"]["dec_i"].to_numpy()] * d
            m_ = (Y["Lp"]["d"] == d).to_numpy() & ~np.isnan(xi)
            if m_.sum() < 100:
                continue
            b = np.digitize(xi, np.nanquantile(xi[m_], [0.2, 0.4, 0.6, 0.8]))
            for q in range(5):
                s6[f"S6 {name_} Q{q + 1} {dn}"] = summary_row(series_stats(Y["Lp"], np.flatnonzero(m_ & (b == q)), Y["rates"], Y["weeks"]))
    for v, ok in zip(s6.values(), bh([v["p_vs_random"] for v in s6.values()]), strict=True):
        v["bh"] = bool(ok)
    out["S6_intermarket_2026_descriptive"] = s6
    out["_frozen"] = frozen
    return out


def _seq_frame(c_id: str, period: str, seq: dict | None) -> pd.DataFrame | None:
    if not seq or len(seq.get("fill_t", [])) == 0:
        return None
    df = pd.DataFrame({k: seq[k] for k in ("fill_t", "exit_t", "d", "outcome", "net", "cost", "minutes", "session")})
    df.insert(0, "period", period)
    df.insert(0, "candidate", c_id)
    for col in ("fill_t", "exit_t"):
        df[col] = pd.to_datetime(df[col], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    df["dir"] = np.where(df.pop("d") > 0, "BUY", "SELL")
    df["net_usd_050lot_ASSUMED"] = df["net"] * b26.LOT_OZ
    return df


def write(out: dict, dir_: str, trials: str | None) -> None:
    os.makedirs(dir_, exist_ok=True)
    frozen = out.pop("_frozen")
    with open(os.path.join(dir_, "b27_summary.json"), "w") as fh:
        json.dump(_clean(out), fh, indent=1, allow_nan=False)
    board = []
    for c_ in out["frozen"]:
        dv, y_, y5 = c_["dev"], c_.get("y2026") or {}, c_.get("y2026_5m") or {}
        board.append({"id": c_["id"], "board": c_["board"], "dir": c_["dir"], "informative": c_["informative"], "tradeable": c_["tradeable"],
                      **{f"dev_{k}": dv.get(k) for k in ("r", "n_decided", "matched_random", "exp_oz", "pf", "per_week", "max_dd_050lot_ASSUMED",
                                                          "mc_dd95_050lot_ASSUMED", "minutes_median", "cost_oz", "fill_rate")},
                      "dev_lo": dv["ci95"][0] if dv.get("ci95") else None, "dev_hi": dv["ci95"][1] if dv.get("ci95") else None,
                      **{f"y26_{k}": y_.get(k) for k in ("r", "n_decided", "matched_random", "exp_oz", "pf", "per_week")},
                      "y26_lo": y_["ci95"][0] if y_.get("ci95") else None, "y26_holm_p": c_.get("y2026_holm_p"),
                      "holds_2026": c_.get("holds_2026"), "y26_5m_r": y5.get("r"), "y26_5m_n": y5.get("n_decided")})
    pd.DataFrame(board).to_csv(os.path.join(dir_, "b27_leaderboard.csv"), index=False, float_format="%.4f")
    for key in ("S1", "S2", "S3", "S5"):
        flat = []
        for c_ in out[key]:
            dv = c_["dev"]
            flat.append({"id": c_["id"], "dir": c_["dir"], **{k: c_.get(k) for k in ("family", "feature", "bin", "mode", "model", "q", "regime")},
                         **{k: dv.get(k) for k in SUMMARY_KEYS if k != "ci95"}, "lo": dv["ci95"][0] if dv.get("ci95") else None,
                         "hi": dv["ci95"][1] if dv.get("ci95") else None, "bh": c_["bh"], "informative": c_["informative"],
                         "tradeable": c_["tradeable"]})
        pd.DataFrame(flat).to_csv(os.path.join(dir_, f"b27_{key}.csv.gz"), index=False, float_format="%.4f", compression="gzip")
    frames = [f for c_ in frozen for f in (_seq_frame(c_["id"], "DEV", c_["stats"].get("_seq")),
                                            _seq_frame(c_["id"], "Y2026", c_.get("y2026", {}).get("_seq")),
                                            _seq_frame(c_["id"], "Y2026_5m", c_.get("y2026_5m", {}).get("_seq"))) if f is not None]
    if frames:
        pd.concat(frames).to_csv(os.path.join(dir_, "b27_frozen_trades.csv.gz"), index=False, float_format="%.4f", compression="gzip")
    if trials:
        log_trials(out, trials)


def log_trials(out: dict, trials: str) -> None:
    """One trial line per tested configuration (development) and per frozen candidate (2026 check). Works on the
    in-memory result or on b27_summary.json read back."""
    for key in ("S1", "S2", "S3", "S5"):
        for c_ in out[key]:
            dv = c_["dev"]
            H.log_trial(trials, {"phase": REG, "partition": "development", "id": f"B27 {c_['id']}", "n": dv["n_decided"],
                                 "success": dv["r"], "ci95": dv["ci95"], "net_usd_per_oz": dv["exp_oz"],
                                 "verdict": "TRADEABLE" if c_["tradeable"] else ("INFORMATIVE" if c_["informative"] else "NO")})
    for c_ in out["frozen"]:
        y_ = c_.get("y2026") or {}
        H.log_trial(trials, {"phase": REG, "partition": "unsealed 2026 (frozen check)", "id": f"B27 {c_['id']}",
                             "n": y_.get("n_decided"), "success": y_.get("r"), "ci95": y_.get("ci95"), "net_usd_per_oz": y_.get("exp_oz"),
                             "holm_p": c_.get("y2026_holm_p"), "verdict": "HOLDS" if c_.get("holds_2026") else "DOES NOT HOLD"})


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items() if not str(k).startswith("_")}
    return b26._clean(x) if not isinstance(x, (list, tuple)) else [_clean(v) for v in x]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True)
    ap.add_argument("--store60", required=True)
    ap.add_argument("--md", help="a folder with the live store's intermarket 60m series (S6, descriptive)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    out = run(a)
    write(out, a.out, a.trials)
    print(json.dumps(_clean({"counts": out["counts"], "auc": {m: v["auc"] for m, v in out["S3_models"].items()}}), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
