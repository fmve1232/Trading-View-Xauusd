"""B29 (research/registrations/B29.json, committed ffc0b6857 before this code): Track B, dynamic TP / SL.

  G  the TP x SL grid (101 pairs) at every eligible bar, against the no-information arithmetic
  V  ATR-scaled brackets (25 pairs)
  M  20 / 60-day time-series momentum for large brackets (direction-neutral baseline)
  C  a calibrated LightGBM per bracket (7 brackets, B27's purged quarterly walk-forward)
  E  21 trigger families x 7 brackets, immediate entry

The engine is B26's trade with TP != SL, vectorised: for every entry at once it finds the first bar at which each
level is reached on the exit side (a BUY's bid, a SELL's ask), so one pass serves every bracket. A bar reaching both
levels is AMBIGUOUS: worst case (the stop, primary) and best case (the target) are both kept.

RESEARCH ONLY: never imported by production (tests/test_integrity.py).
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import ta
from . import b26, b27, b28
from . import harness as H

REG = "B29"
TPS = (3, 5, 7, 10, 12, 15, 18, 20, 25, 30)
SLS = (3, 5, 7, 10, 12, 15, 18, 20, 25, 30)
GRID = tuple([(t, s) for t in TPS for s in SLS] + [(8, 10)])
ATR_M = (0.5, 1.0, 1.5, 2.0, 3.0)
ATR_GRID = tuple((a, b) for a in ATR_M for b in ATR_M)
TSM_BRACKETS = ((20, 20), (25, 15), (25, 25), (30, 20), (30, 30), (20, 10), (30, 15))
TSM_LOOKBACK = (20, 60)
MODEL_BRACKETS = ((5, 10), (10, 10), (10, 15), (15, 10), (20, 10), (20, 20), (30, 20))
QS_C = (0.50, 0.20, 0.10, 0.05, 0.02, 0.01)
SCEN = ("GROSS", "OP", "ENG", "ADV")
TP_, SL_, AMB_, TIMEOUT_, CLOSURE_, OPEN_ = range(6)
OUT_NAMES = ("TP", "SL", "AMBIGUOUS", "TIMEOUT", "CLOSURE", "OPEN")
CHUNK = 12000
INCONCLUSIVE_GAP = 0.02


# ---------------- the vectorised engine ----------------
def scen_costs(spread: np.ndarray, sc: str) -> tuple[np.ndarray, float, float, float]:
    """(spread per entry, entry slippage, exit slippage, commission) in 4000-equivalent dollars per oz."""
    if sc == "GROSS":
        return np.zeros_like(spread), 0.0, 0.0, 0.0
    if sc == "OP":
        return np.full_like(spread, 0.26), 0.0, 0.0, 0.0
    if sc == "ENG":
        return spread, 0.20, 0.20, 0.07
    if sc == "ADV":
        return 2.0 * spread, 0.40, 0.40, 0.07
    raise ValueError(sc)


class Paths:
    """Exit-side excursions from the fill for a block of entries (one direction, one cost scenario).

    fav[r, j] / adv[r, j]: the running maximum favourable / adverse excursion up to bar f_r + j on the exit side;
    ofav / oadv: the same at bar j's open only (for gaps). valid[r, j]: bar f_r + j is inside the trade's window
    (before a closure, the 2-day limit and the data end); last[r] the last valid column and why it ends."""

    def __init__(self, P: b26.Path, f: np.ndarray, d: int, s: np.ndarray, si: np.ndarray, horizon: int):
        o, h, l, c = (np.asarray(x) for x in (P.o, P.h, P.l, P.c))
        n = P.n
        self.d, self.horizon, self.f = d, horizon, f
        cols = np.arange(horizon)
        J = np.minimum(f[:, None] + cols[None, :], n - 1)
        ce = np.flatnonzero(np.asarray(P.closure_end))
        jc = ce[np.searchsorted(ce, f, "left")]                        # the first closure-end bar at or after f
        lim = np.minimum.reduce([jc - f, np.full(len(f), horizon - 1), n - 1 - f])
        self.valid = cols[None, :] <= lim[:, None]
        self.last = lim
        # B26's order at a bar: the data end (OPEN), then a closure (CLOSURE), then the 2-day limit (TIMEOUT)
        self.reason = np.where(f + lim >= n - 1, OPEN_, np.where(lim == jc - f, CLOSURE_, TIMEOUT_))
        off = -d * s / 2.0
        self.fill = o[f] + d * (s / 2.0 + si)
        to, th, tl, tc = o[J] + off[:, None], h[J] + off[:, None], l[J] + off[:, None], c[J] + off[:, None]
        if d > 0:
            fav, adv = th - self.fill[:, None], self.fill[:, None] - tl
            self.ofav = to - self.fill[:, None]
        else:
            fav, adv = self.fill[:, None] - tl, th - self.fill[:, None]
            self.ofav = self.fill[:, None] - to
        fav = np.where(self.valid, fav, -np.inf)
        adv = np.where(self.valid, adv, -np.inf)
        self.fav = np.maximum.accumulate(fav, axis=1)
        self.adv = np.maximum.accumulate(adv, axis=1)
        self.close_last = tc[np.arange(len(f)), lim]
        self.J = J

    def first(self, cum: np.ndarray, level) -> np.ndarray:
        lvl = np.asarray(level, float)
        hit = cum >= (lvl[:, None] if lvl.ndim else lvl)
        return np.where(hit.any(axis=1), hit.argmax(axis=1), self.horizon)


def resolve(pp: Paths, i_tp: np.ndarray, i_sl: np.ndarray, tp: np.ndarray, sl: np.ndarray, so: float, cm: np.ndarray) -> dict:
    """Outcome (worst and best case), net per oz in price units, exit column, for given first-passage columns."""
    N = len(i_tp)
    r = np.arange(N)
    j = np.minimum(i_tp, i_sl)
    jj = np.minimum(j, pp.horizon - 1)
    oadv = -pp.ofav[r, jj]
    ofav = pp.ofav[r, jj]
    neither = j >= pp.horizon
    sl_first = i_sl < i_tp
    same = (i_tp == i_sl) & ~neither
    gap_sl = (sl_first | same) & (oadv >= sl)
    gap_tp = same & ~gap_sl & (ofav >= tp)
    amb = same & ~gap_sl & ~gap_tp
    worst = np.full(N, TP_)
    worst[sl_first | gap_sl | amb] = SL_
    worst[amb] = AMB_
    worst[neither] = pp.reason[neither]
    best = worst.copy()
    best[amb] = TP_
    net_sl = np.where(gap_sl, -oadv, -sl) - so
    net_tp = tp
    net_neither = pp.d * (pp.close_last - pp.d * so - pp.fill)
    net_w = np.where(neither, net_neither, np.where(worst == TP_, net_tp, net_sl)) - cm
    net_b = np.where(amb, net_tp - cm, net_w)
    col = np.where(neither, pp.last, j)
    return {"worst": worst, "best": best, "net_w": net_w, "net_b": net_b, "col": col, "gap": gap_sl | gap_tp}


def label_block(P: b26.Path, dec: np.ndarray, d: int, spread: np.ndarray, k: np.ndarray, sc: str, horizon: int,
                fixed: tuple = GRID, atr: np.ndarray | None = None, atr_grid: tuple = ()) -> dict:
    """Labels of every bracket for the entries decided at bars `dec` (fill at dec + 1), in chunks."""
    sp, si, so, cm = scen_costs(spread, sc)
    res = {g: {key: [] for key in ("worst", "best", "net_w", "net_b", "exit_bar", "minutes", "gap")} for g in (*fixed, *(("ATR",) + g for g in atr_grid))}
    t = np.asarray(P.t, dtype=np.int64)
    tps = sorted({g[0] for g in fixed})
    sls = sorted({g[1] for g in fixed})
    for a0 in range(0, len(dec), CHUNK):
        sl_ = slice(a0, a0 + CHUNK)
        f = dec[sl_] + 1
        kk = k[sl_]
        pp = Paths(P, f, d, sp[sl_] * kk, si * kk, horizon)
        ftp = {v: pp.first(pp.fav, v * kk) for v in tps}
        fsl = {v: pp.first(pp.adv, v * kk) for v in sls}
        jobs = [(g, ftp[g[0]], fsl[g[1]], g[0] * kk, g[1] * kk) for g in fixed]
        if atr is not None:
            aa = atr[dec[sl_]]
            atp = {m: pp.first(pp.fav, m * aa) for m in sorted({g[0] for g in atr_grid})}
            asl = {m: pp.first(pp.adv, m * aa) for m in sorted({g[1] for g in atr_grid})}
            jobs += [(("ATR",) + g, atp[g[0]], asl[g[1]], g[0] * aa, g[1] * aa) for g in atr_grid]
        for g, itp, isl, tpl, sll in jobs:
            rr = resolve(pp, itp, isl, tpl, sll, so * kk, cm * kk)
            xb = pp.J[np.arange(len(f)), np.minimum(rr["col"], horizon - 1)]
            xt = t[xb] + P.bar
            xt = np.where(rr["gap"], t[xb], xt)
            res[g]["worst"].append(rr["worst"].astype(np.int8))
            res[g]["best"].append(rr["best"].astype(np.int8))
            res[g]["net_w"].append((rr["net_w"] / kk).astype(np.float32))
            res[g]["net_b"].append((rr["net_b"] / kk).astype(np.float32))
            res[g]["exit_bar"].append(xb.astype(np.int32))
            res[g]["minutes"].append(((xt - t[f]) / 60.0).astype(np.float32))
            res[g]["gap"].append(rr["gap"])
        del pp
    return {g: {key: np.concatenate(v) if v else np.zeros(0) for key, v in d_.items()} for g, d_ in res.items()}


def theory(tp: float, sl: float, spread: float, sc: str) -> tuple[float, float]:
    """(p0, break-even) for a bracket in 4000-equivalent dollars under a cost scenario (PHASE_C_PLAN.md section 2)."""
    _, si, so, cm = scen_costs(np.array([spread]), sc)
    s = scen_costs(np.array([spread]), sc)[0][0]
    delta = s + si
    return (sl - delta) / (tp + sl), (sl + so + cm) / (tp + sl + so)


# ---------------- populations and tables ----------------
def decisions(P_: dict) -> pd.DataFrame:
    """One row per eligible decision bar (from the B26 / B27 label table) with its calendar fields."""
    L = P_["Lp"]
    D = L.drop_duplicates("dec_i")[["dec_i", "fill_utc", "session", "ym", "nyday", "vol_tercile", "trend_state"]].sort_values("dec_i")
    return D.reset_index(drop=True)


def tables(P_: dict, sc: str, horizon: int = 192, fixed: tuple = GRID, atr_grid: tuple = (), path=None, dec_frame=None) -> dict:
    """Every-bar labels of each bracket, BUY and SELL, as a dict (bracket -> DataFrame)."""
    path = path or P_["path"]
    Dc = dec_frame if dec_frame is not None else decisions(P_)
    dec = Dc["dec_i"].to_numpy()
    spread = np.asarray([P_["costs"][i + 1][0] for i in dec]) if dec_frame is None else Dc["spread"].to_numpy()
    k = P_["k"][dec] if dec_frame is None else Dc["k"].to_numpy()
    atr = None
    if atr_grid:
        m = P_["m15"]
        atr = ta.atr(*(m[x].to_numpy(float) for x in ("high", "low", "close")), 14)
    out = {}
    for d in (1, -1):
        lab = label_block(path, dec if dec_frame is None else Dc["f_i"].to_numpy() - 1, d, spread, k, sc, horizon, fixed, atr, atr_grid)
        for g, v in lab.items():
            df = pd.DataFrame({"dec_i": dec, "d": d, "fill_utc": Dc["fill_utc"].to_numpy(), "session": Dc["session"].to_numpy(),
                               "ym": Dc["ym"].to_numpy(), "nyday": Dc["nyday"].to_numpy(), "vol_tercile": Dc["vol_tercile"].to_numpy(),
                               "trend_state": Dc["trend_state"].to_numpy(),
                               "outcome": np.asarray(OUT_NAMES)[v["worst"]], "outcome_best": np.asarray(OUT_NAMES)[v["best"]],
                               "net_usd_oz": v["net_w"].astype(float), "net_best": v["net_b"].astype(float), "exit_bar": v["exit_bar"],
                               "minutes": v["minutes"].astype(float), "gap": v["gap"]})
            df["exit_utc"] = df["fill_utc"] + df["minutes"] * 60.0
            out.setdefault(g, []).append(df)
    res = {}
    sp, si, so, cm = scen_costs(spread, sc)
    spr = np.tile(sp, 2)
    for g, parts in out.items():
        df = pd.concat(parts, ignore_index=True)
        df["cost_usd_oz"] = (spr + si + np.where(df["outcome"] == "TP", 0.0, so) + cm).astype(np.float32)
        for col in ("session", "ym", "nyday", "vol_tercile", "trend_state", "outcome", "outcome_best"):
            df[col] = df[col].astype("category")
        res[g] = df                                   # OPEN rows kept (same row order in every scenario); statistics skip them
    return res


def seq_stats(L: pd.DataFrame, rows: np.ndarray, rates: dict, weeks: float, risk: float | None, mc: bool = False) -> dict:
    """B27's independent-series statistics plus the best-case rate, expectancy per unit risk and SL-first share."""
    st = b27.series_stats(L, rows, rates, weeks, mc)
    seq = st.get("_seq")
    if seq is not None and len(seq["fill_t"]):
        sub = L.iloc[rows]
        s = b27.seq_rows(sub["dec_i"].to_numpy(), sub["exit_bar"].to_numpy(), sub["outcome"].to_numpy())
        ob = sub["outcome_best"].to_numpy()[s]
        kb, nb = b27.decided(ob)
        st["r_best"] = kb / nb if nb else math.nan
        o = sub["outcome"].to_numpy()[s]
        st["sl_first"] = float(np.isin(o, ["SL", "AMBIGUOUS"]).mean())
        st["inconclusive"] = bool(st["r_best"] - st["r"] > INCONCLUSIVE_GAP)
        mins = sub["minutes"].to_numpy()[s]
        st["minutes_tp"] = float(np.median(mins[o == "TP"])) if (o == "TP").any() else math.nan
        st["minutes_sl"] = float(np.median(mins[np.isin(o, ["SL", "AMBIGUOUS"])])) if np.isin(o, ["SL", "AMBIGUOUS"]).any() else math.nan
        st["longest_losing_run"] = _run(sub["net_usd_oz"].to_numpy()[s])
    e = st.get("exp_oz")
    st["exp_per_risk"] = e / risk if risk and e is not None and not math.isnan(e) else math.nan
    return st


def _run(net: np.ndarray) -> int:
    best = cur = 0
    for v in net:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return best


KEYS = (*b27.SUMMARY_KEYS, "r_best", "sl_first", "inconclusive", "minutes_tp", "minutes_sl", "longest_losing_run", "exp_per_risk")


def row(st: dict) -> dict:
    return {k: st.get(k) for k in KEYS}


# ---------------- TSMOM ----------------
def tsmom(m15: pd.DataFrame, lookback: int) -> np.ndarray:
    """Per 15m bar: the sign of the change of the New York session daily close over the last `lookback` completed days."""
    tday = (m15.index.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)).normalize()
    close = pd.Series(m15["close"].to_numpy(float), index=m15.index).groupby(tday).last()
    ch = np.sign(close - close.shift(lookback))
    prev = ch.shift(1)                                           # the change known when today's session starts
    return pd.Series(tday, index=m15.index).map(prev).to_numpy(float)


# ---------------- the run ----------------
def freeze(cands: list[dict], n_inf: int = 20, n_big: int = 5, n_small: int = 5) -> list[dict]:
    def lb(c_):
        return c_["stats"]["ci95"][0] if c_["stats"].get("n_decided") else -1.0

    groups = (("informative", sorted([c for c in cands if c["informative"]], key=lb, reverse=True)[:n_inf]),
              ("top_n300", sorted([c for c in cands if c["stats"].get("n_decided", 0) >= b27.MIN_N], key=lb, reverse=True)[:n_big]),
              ("low_frequency", sorted([c for c in cands if b27.LOW_N <= c["stats"].get("n_decided", 0) < b27.MIN_N], key=lb, reverse=True)[:n_small]))
    seen, out = set(), []
    for board, g in groups:
        for c in g:
            if c["id"] not in seen:
                seen.add(c["id"])
                c["board"] = board
                out.append(c)
    return out


def gname(g) -> str:
    return f"ATR {g[1]:g}x/{g[2]:g}x" if g[0] == "ATR" else f"TP{g[0]}/SL{g[1]}"


def risk_of(g, L: pd.DataFrame, P_: dict) -> float:
    """The stop in 4000-equivalent dollars (median for ATR brackets)."""
    if g[0] != "ATR":
        return float(g[1])
    m = P_["m15"]
    atr = ta.atr(*(m[x].to_numpy(float) for x in ("high", "low", "close")), 14)
    return float(np.nanmedian(g[2] * atr[L["dec_i"].to_numpy()] / P_["k"][L["dec_i"].to_numpy()]))


def closest_fixed(med_tp: float, med_sl: float) -> tuple:
    return min(GRID, key=lambda g: abs(g[0] - med_tp) + abs(g[1] - med_sl))


def welch_greater(x: np.ndarray, y: np.ndarray) -> float:
    """One-sided Welch t-test p-value for mean(x) > mean(y)."""
    from scipy.stats import ttest_ind
    if len(x) < 2 or len(y) < 2:
        return 1.0
    return float(ttest_ind(x, y, equal_var=False, alternative="greater").pvalue)


def gross_positive_p(net: np.ndarray) -> float:
    """One-sided one-sample t-test p-value for mean(net) > 0 (B29 amendments 1-3)."""
    from scipy.stats import ttest_1samp
    return float(ttest_1samp(net, 0.0, alternative="greater").pvalue) if len(net) > 2 else 1.0


def flag_v(V: list[dict]) -> None:
    """V's test (registration B29, amendments 1-3, before any real result): the POOLED BUY + SELL ENG expectancy of the
    ATR bracket's independent series is above zero (drift cancels; ENG charges stop slippage, so the GROSS stop-overshoot
    optimism does not enter); the closest-fixed comparison is description only (biased by size mismatch)."""
    brackets = sorted({tuple(c["bracket"]) for c in V})
    pool = {g: np.concatenate([c["_eng_net"] for c in V if tuple(c["bracket"]) == g]) for g in brackets}
    p_of = {g: gross_positive_p(pool[g]) for g in brackets}
    ok_of = dict(zip(brackets, b27.bh([p_of[g] for g in brackets]), strict=True))
    for c in V:
        c["p_pooled_eng"] = p_of[tuple(c["bracket"])]
        c["eng_pooled_exp_oz"] = float(pool[tuple(c["bracket"])].mean()) if len(pool[tuple(c["bracket"])]) else None
    passed = [ok_of[tuple(c["bracket"])] for c in V]
    for c, ok in zip(V, passed, strict=True):
        st = c["stats"]
        c["bh"] = bool(ok)
        c["informative"] = bool(ok and st.get("n_decided", 0) >= b27.MIN_N)          # V: profitable without any entry signal
        c["tradeable"] = bool(c["informative"] and st["ci95"][0] > st["break_even"])


def trigger_rows(L: pd.DataFrame, P_: dict, fam: str, d: int) -> np.ndarray:
    tr = b27.triggers(P_["F"], P_["Lp"], fam, P_["k"]) if fam in b27.FAMILIES else b28.triggers(P_["F"], P_["Lp"], fam, P_["k"])
    want = {i for i, dd, _, _ in tr if dd == d}
    return np.flatnonzero((L["d"].to_numpy() == d) & np.isin(L["dec_i"].to_numpy(), list(want)))


def tsm_rows(L: pd.DataFrame, P_: dict, lookback: int) -> np.ndarray:
    sig = tsmom(P_["m15"], lookback)
    dec = L["dec_i"].to_numpy()
    return np.flatnonzero(np.isin(dec, np.unique(dec)[::16]) & (L["d"].to_numpy() == sig[dec]))


def neutralise(st: dict, rates_g: dict, P_: dict) -> None:
    """M's registered baseline: replace the same-direction matched rate by the direction-neutral one."""
    neu = b28.extra(st.get("_seq"), b28.neutral_rates(rates_g), P_["Lp"], P_["path"])
    if neu:
        st["matched_same_direction"] = st["matched_random"]
        st["matched_random"] = neu["direction_neutral_random"]
        st["p_vs_random"] = neu["p_vs_neutral"]


def run(a, log=print) -> dict:
    pops = b27.load_pops(a.rd, a.store5, a.store60)
    D, Y = pops["DEV"], pops["Y2026"]
    for P_ in (D, Y):
        b27.prepare(P_, log)
        P_["F"] = pd.concat([P_["F"], b28.new_events(P_["m15"], P_["F"])], axis=1)
    out = {"registration": REG, "utc": datetime.now(timezone.utc).isoformat()}
    keep_alt = set(MODEL_BRACKETS) | set(TSM_BRACKETS)

    # ---- G and V: every-bar tables (ENG and GROSS with the ATR brackets; OP / ADV kept only where needed) ----
    T = {("DEV", "ENG"): tables(D, "ENG", atr_grid=ATR_GRID), ("DEV", "GROSS"): tables(D, "GROSS", atr_grid=ATR_GRID)}
    log("[B29] DEV tables ENG / GROSS")
    rates = {g: b27.base_rates(L) for g, L in T[("DEV", "ENG")].items()}
    wD = b27.weeks_of(T[("DEV", "ENG")][GRID[0]])
    G = {g: {d: {"id": f"G {gname(g)} {dn}", "bracket": list(g), "dir": dn} for d, dn in b27.DIRS.items()} for g in GRID}

    def g_stats(sc: str, tabs: dict) -> None:
        for g in GRID:
            L = tabs[g]
            rg = rates[g] if sc == "ENG" else b27.base_rates(L)
            for d in (1, -1):
                rows = np.flatnonzero((L["d"] == d).to_numpy())
                st = seq_stats(L, rows, rg, wD, g[1])
                kb, nb = b27.decided(L["outcome"].to_numpy()[rows])
                ka, na = b27.decided(L["outcome_best"].to_numpy()[rows])
                p0, be = theory(g[0], g[1], 0.30, sc)
                G[g][d][sc] = {**row(st), "allbar_r_worst": kb / nb if nb else None, "allbar_r_best": ka / na if na else None,
                               "theory_p0_in_session": p0, "theory_break_even": be}

    g_stats("ENG", T[("DEV", "ENG")])
    g_stats("GROSS", T[("DEV", "GROSS")])
    top_g = sorted(GRID, key=lambda g: -max(G[g][d]["ENG"]["exp_per_risk"] for d in (1, -1)))[:10]
    keep_alt |= set(top_g)
    for sc in ("OP", "ADV"):
        tabs = tables(D, sc)
        g_stats(sc, tabs)
        T[("DEV", sc)] = {g: tabs[g] for g in keep_alt}
        del tabs
        log(f"[B29] DEV tables {sc}")
    out["G"] = [G[g][d] for g in GRID for d in (1, -1)]
    T[("Y2026", "ENG")] = tables(Y, "ENG", atr_grid=ATR_GRID)
    rates_y = {g: b27.base_rates(L) for g, L in T[("Y2026", "ENG")].items()}
    wY = b27.weeks_of(T[("Y2026", "ENG")][GRID[0]])

    V = []
    for g in ATR_GRID:
        key = ("ATR",) + g
        L = T[("DEV", "ENG")][key]
        m = D["m15"]
        atr = ta.atr(*(m[x].to_numpy(float) for x in ("high", "low", "close")), 14)
        dec = L["dec_i"].to_numpy()
        med_tp, med_sl = (float(np.nanmedian(x * atr[dec] / D["k"][dec])) for x in g)
        fx = closest_fixed(med_tp, med_sl)
        for d, dn in b27.DIRS.items():
            rows = np.flatnonzero((L["d"] == d).to_numpy())
            st = seq_stats(L, rows, rates[key], wD, med_sl)
            Lf = T[("DEV", "ENG")][fx]
            sf = seq_stats(Lf, np.flatnonzero((Lf["d"] == d).to_numpy()), rates[fx], wD, fx[1])
            xa = (st["_seq"]["net"] / med_sl) if st.get("_seq") else np.zeros(0)
            xf = (sf["_seq"]["net"] / fx[1]) if sf.get("_seq") else np.zeros(0)
            Lg = T[("DEV", "GROSS")][key]
            sg = seq_stats(Lg, np.flatnonzero((Lg["d"] == d).to_numpy()), b27.base_rates(Lg), wD, med_sl)
            gnet = sg["_seq"]["net"] if sg.get("_seq") else np.zeros(0)
            V.append({"study": "V", "id": f"V {gname(key)} {dn}", "bracket": list(key), "dir": dn, "stats": st,
                      "_eng_net": st["_seq"]["net"] if st.get("_seq") else np.zeros(0),
                      "gross_exp_oz_upper_reference": float(gnet.mean()) if len(gnet) else None,
                      "vs_fixed": {"fixed": gname(fx), "median_tp": med_tp, "median_sl": med_sl, "exp_per_risk": st["exp_per_risk"],
                                   "fixed_exp_per_risk": sf["exp_per_risk"], "p_description_only": welch_greater(xa, xf)}})
    flag_v(V)
    log("[B29] V done")

    M = []
    for lb_ in TSM_LOOKBACK:
        for g in TSM_BRACKETS:
            L = T[("DEV", "ENG")][g]
            rows = tsm_rows(L, D, lb_)
            st = seq_stats(L, rows, rates[g], wD, g[1])
            neutralise(st, rates[g], D)
            for dn, dd in (("BUY", 1), ("SELL", -1)):
                rr = rows[L["d"].to_numpy()[rows] == dd]
                st[f"r_{dn}"] = seq_stats(L, rr, rates[g], wD, g[1]).get("r") if len(rr) else None
            M.append({"study": "M", "id": f"M TSMOM{lb_} {gname(g)}", "bracket": list(g), "lookback": lb_, "dir": "TREND", "stats": st})
    b27.flag(M)
    log("[B29] M done")

    C, Cinfo, WF = [], {}, {}
    for g in MODEL_BRACKETS:
        L = T[("DEV", "ENG")][g]
        WF[g] = b27.walk_forward(D["F"], L, D["h1"], ("LGBM",), log=lambda *_: None)
        y = (L["outcome"] == "TP").to_numpy(int)
        p = WF[g]["res"]["LGBM"]["p"]
        tm = ~np.isnan(p)
        Cinfo[gname(g)] = {"auc": b27.auc(y, p), "brier": float(np.mean((p[tm] - y[tm]) ** 2)),
                           "brier_constant": float(y[tm].mean() * (1 - y[tm].mean())), "reliability": b27.reliability(y, p)}
        for (dd, q), rows in b27.wf_selections(L, WF[g], "LGBM").items():
            if q in QS_C:
                C.append({"study": "C", "id": f"C LGBM {gname(g)} top{q * 100:g}% {b27.DIRS[dd]}", "bracket": list(g), "q": q,
                          "dir": b27.DIRS[dd], "rows": rows, "stats": seq_stats(L, rows, rates[g], wD, g[1])})
        log(f"[B29] C {gname(g)}: AUC {Cinfo[gname(g)]['auc']:.4f}")
    b27.flag(C)

    E = []
    for g in MODEL_BRACKETS:
        L = T[("DEV", "ENG")][g]
        for fam in (*b27.FAMILIES, *b28.FAMILIES):
            for d, dn in b27.DIRS.items():
                rr = trigger_rows(L, D, fam, d)
                if len(rr):
                    E.append({"study": "E", "id": f"E {fam} {gname(g)} {dn}", "family": fam, "bracket": list(g), "dir": dn,
                              "stats": seq_stats(L, rr, rates[g], wD, g[1])})
    b27.flag(E)
    log(f"[B29] E: {len(E)} configurations")

    # ---- freeze on development, check on 2026 ----
    frozen = [*freeze(V), *freeze(M), *freeze(C), *freeze(E)]
    def epr(e):
        v = e["ENG"]["exp_per_risk"]
        return -9.0 if v is None or math.isnan(v) else v

    picks = sorted(out["G"], key=epr, reverse=True)[:5]
    for e in picks:
        frozen.append({"study": "G", "id": e["id"], "bracket": e["bracket"], "dir": e["dir"], "board": "best_exp_per_risk",
                       "informative": False, "tradeable": False, "bh": False})
    FM = {}
    for c in frozen:
        g = tuple(c["bracket"])
        L, Ly = T[("DEV", "ENG")][g], T[("Y2026", "ENG")][g]
        d = 1 if c["dir"] == "BUY" else -1
        risk = c["vs_fixed"]["median_sl"] if c["study"] == "V" else g[1]
        if c["study"] in ("G", "V"):
            rows_d = np.flatnonzero((L["d"] == d).to_numpy())
            rows_y = np.flatnonzero((Ly["d"] == d).to_numpy())
        elif c["study"] == "M":
            rows_d, rows_y = tsm_rows(L, D, c["lookback"]), tsm_rows(Ly, Y, c["lookback"])
        elif c["study"] == "C":
            if g not in FM:
                FM[g] = b27.final_models(D["F"], L, D["h1"], ("LGBM",))
                FM[g]["py"] = b27.apply_final(FM[g], Y["F"], Ly, Y["h1"])["LGBM"]
            rows_d = c["rows"]
            rows_y = np.flatnonzero((Ly["d"] == d).to_numpy() & (FM[g]["py"] >= FM[g]["thr"]["LGBM"][(d, c["q"])]))
        else:
            rows_d, rows_y = trigger_rows(L, D, c["family"], d), trigger_rows(Ly, Y, c["family"], d)
        c["stats"] = seq_stats(L, rows_d, rates[g], wD, risk, mc=True)
        c["y2026"] = seq_stats(Ly, rows_y, rates_y[g], wY, risk)
        if c["study"] == "M":
            neutralise(c["stats"], rates[g], D)
            neutralise(c["y2026"], rates_y[g], Y)
        c["dev_extra"] = b28.extra(c["stats"].get("_seq"), b28.neutral_rates(rates[g]), D["Lp"], D["path"])
        c["cost"] = {sc: row(seq_stats(T[("DEV", sc)][g], rows_d, b27.base_rates(T[("DEV", sc)][g]), wD, risk))
                     for sc in ("GROSS", "OP", "ADV") if g in T[("DEV", sc)]}
    for c, ph in zip(frozen, b27.holm([c["y2026"].get("p_vs_random", 1.0) for c in frozen]), strict=True):
        y_ = c["y2026"]
        c["y2026_holm_p"] = ph
        c["holds_2026"] = bool(ph < 0.05 and y_.get("n_decided", 0) and y_["ci95"][0] > y_["matched_random"])
        c["above_break_even_2026"] = bool(y_.get("n_decided", 0) and y_["ci95"][0] > y_["break_even"])

    out["resolution_5m"] = resolution_5m(Y, T[("Y2026", "ENG")])
    out["counts"] = {s_: {"tested": len(v), "bh": sum(c["bh"] for c in v), "informative": sum(c["informative"] for c in v),
                          "tradeable": sum(c["tradeable"] for c in v)} for s_, v in (("V", V), ("M", M), ("C", C), ("E", E))}
    out["C_models"] = Cinfo

    def pack(c):
        p = {k: c.get(k) for k in ("id", "study", "bracket", "dir", "family", "q", "lookback", "board", "bh", "informative", "tradeable",
                                   "y2026_holm_p", "holds_2026", "above_break_even_2026", "vs_fixed", "p_pooled_eng",
                                   "eng_pooled_exp_oz", "gross_exp_oz_upper_reference")}
        p["dev"] = row(c["stats"])
        for k in ("matched_same_direction", "r_BUY", "r_SELL"):
            if k in c["stats"]:
                p["dev"][k] = c["stats"][k]
        if "y2026" in c:
            p["y2026"] = row(c["y2026"])
        for k in ("dev_extra", "cost"):
            if k in c:
                p[k] = c[k]
        return p

    for key, lst in (("V", V), ("M", M), ("C", C), ("E", E)):
        out[key] = [pack(c) for c in lst]
    out["frozen"] = [pack(c) for c in frozen]
    out["_frozen"] = frozen
    return out


def resolution_5m(Y: dict, T15: dict) -> dict:
    """The grid on the same 15m decisions, resolved on the live store's 5m bars (fill at the 5m bar opening at the 15m
    fill time): the 15m worst / best bounds against the 5m bounds, per bracket and direction."""
    df5 = Y["df5"]
    P5 = b26.make_path(df5, 300)
    t5 = np.asarray(P5.t, dtype=np.int64)
    Dc = decisions(Y)
    Dc = Dc[(Dc["fill_utc"] >= t5[0]) & (Dc["fill_utc"] <= t5[-1])].copy()
    f5 = np.searchsorted(t5, Dc["fill_utc"].to_numpy())
    ok = (f5 < len(t5)) & (t5[np.clip(f5, 0, len(t5) - 1)] == Dc["fill_utc"].to_numpy())
    Dc, f5 = Dc[ok].copy(), f5[ok]
    Dc["f_i"] = f5
    Dc["spread"] = [Y["costs"][i + 1][0] for i in Dc["dec_i"]]
    Dc["k"] = 1.0
    T5 = tables(Y, "ENG", horizon=576, path=P5, dec_frame=Dc)
    out = {}
    for g in GRID:
        for d, dn in b27.DIRS.items():
            a5 = T5[g][T5[g]["d"] == d]
            a15 = T15[g][(T15[g]["d"] == d) & T15[g]["dec_i"].isin(Dc["dec_i"])]
            k5w, n5w = b27.decided(a5["outcome"].to_numpy())
            k5b, n5b = b27.decided(a5["outcome_best"].to_numpy())
            k1w, n1w = b27.decided(a15["outcome"].to_numpy())
            k1b, n1b = b27.decided(a15["outcome_best"].to_numpy())
            out[f"{gname(g)} {dn}"] = {"n": int(n5w), "r5_worst": k5w / n5w if n5w else None, "r5_best": k5b / n5b if n5b else None,
                                       "r15_worst": k1w / n1w if n1w else None, "r15_best": k1b / n1b if n1b else None,
                                       "exp5_oz": float(a5["net_usd_oz"].mean()) if len(a5) else None}
    return out


def write(out: dict, dir_: str, trials: str | None) -> None:
    os.makedirs(dir_, exist_ok=True)
    frozen = out.pop("_frozen")
    with open(os.path.join(dir_, "b29_summary.json"), "w") as fh:
        json.dump(b27._clean(out), fh, indent=1, allow_nan=False)
    g_rows = []
    for e in out["G"]:
        for sc in SCEN:
            v = e[sc]
            g_rows.append({"bracket": gname(tuple(e["bracket"])), "tp": e["bracket"][0], "sl": e["bracket"][1], "dir": e["dir"], "scenario": sc,
                           **{k: v.get(k) for k in (*KEYS, "allbar_r_worst", "allbar_r_best", "theory_p0_in_session", "theory_break_even") if k != "ci95"},
                           "lo": v["ci95"][0] if v.get("ci95") else None, "hi": v["ci95"][1] if v.get("ci95") else None})
    pd.DataFrame(g_rows).to_csv(os.path.join(dir_, "b29_grid.csv"), index=False, float_format="%.4f")
    for key in ("V", "M", "C", "E"):
        rows = [{"id": c["id"], "dir": c["dir"], **{k: c["dev"].get(k) for k in KEYS if k != "ci95"},
                 "lo": c["dev"]["ci95"][0] if c["dev"].get("ci95") else None, "hi": c["dev"]["ci95"][1] if c["dev"].get("ci95") else None,
                 "bh": c["bh"], "informative": c["informative"], "tradeable": c["tradeable"]} for c in out[key]]
        pd.DataFrame(rows).to_csv(os.path.join(dir_, f"b29_{key}.csv.gz"), index=False, float_format="%.4f", compression="gzip")
    frames = [f for c in frozen for f in (b27._seq_frame(c["id"], "DEV", c["stats"].get("_seq")),
                                           b27._seq_frame(c["id"], "Y2026", c["y2026"].get("_seq"))) if f is not None]
    if frames:
        pd.concat(frames).to_csv(os.path.join(dir_, "b29_frozen_trades.csv.gz"), index=False, float_format="%.4f", compression="gzip")
    if trials:
        log_trials(out, trials)


def log_trials(out: dict, trials: str) -> None:
    for e in out["G"]:
        v = e["ENG"]
        H.log_trial(trials, {"phase": REG, "partition": "development", "id": f"B29 {e['id']}", "n": v["n_decided"], "success": v["r"],
                             "ci95": v["ci95"], "net_usd_per_oz": v["exp_oz"], "verdict": "DESCRIPTIVE (no-information grid)"})
    for key in ("V", "M", "C", "E"):
        for c in out[key]:
            dv = c["dev"]
            H.log_trial(trials, {"phase": REG, "partition": "development", "id": f"B29 {c['id']}", "n": dv["n_decided"], "success": dv["r"],
                                 "ci95": dv["ci95"], "net_usd_per_oz": dv["exp_oz"],
                                 "verdict": "TRADEABLE" if c["tradeable"] else ("INFORMATIVE" if c["informative"] else "NO")})
    for c in out["frozen"]:
        y_ = c.get("y2026") or {}
        H.log_trial(trials, {"phase": REG, "partition": "unsealed 2026 (frozen check)", "id": f"B29 {c['id']}", "n": y_.get("n_decided"),
                             "success": y_.get("r"), "ci95": y_.get("ci95"), "net_usd_per_oz": y_.get("exp_oz"),
                             "holm_p": c.get("y2026_holm_p"), "verdict": "HOLDS" if c.get("holds_2026") else "DOES NOT HOLD"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True)
    ap.add_argument("--store60", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    out = run(a)
    write(out, a.out, a.trials)
    print(json.dumps(b27._clean({"counts": out["counts"], "C_models": {k: v["auc"] for k, v in out["C_models"].items()}}), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
