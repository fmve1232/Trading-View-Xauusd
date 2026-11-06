"""Phase B19 (research/registrations/B19.json, approved 2026-11-07; written after the registration was committed).

Two stages, then a plan:
  A  a trigger: the frozen engine's SIGNAL (ENG) or its own structure event with bias / VWAP / session agreeing (STR),
     on 15m, 30m, 1h and 4h, pooled with the live REPEAT rule;
  B  confirmation on the 15m bars after it: a CLOSE beyond P0 + d x 15s (or 20s) in the trigger's own direction, with
     filter set F0 (the close only) or F1 (+ momentum, structure continuation, cost, volatility), invalidated by a
     -13s move or an opposite structure event first, expired after 96 bars;
  plan: entry E1 (market at the confirmation close) or E2 (limit at the threshold, 8 bars), stop S10 / S13 / SATR /
     SSTR, target 15-30s, EXECUTE only with target / stop >= 1, the stop in [5s, 40s] and cost <= 15% of it; exit on
     the 15m bars, a two-level bar AMBIGUOUS (a loss), gaps filled at the open, a time stop at 192 bars.
Every condition is read at a bar's close from data up to that close. Distances are $ at $4,000 scaled by P0 / 4000;
costs are $ per oz, unscaled. Research code: never imported by production.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .. import config, engine, ta
from ..data import sources
from ..features import compute as compute_features
from . import b8_news, b10, b13, history
from . import harness as H

REG = "B19"
WIN, HOLD, LIMIT_BARS = 96, 192, 8                 # confirmation window, holding window, E2 validity (15m bars)
INV = 13.0                                         # price invalidation before confirmation ($ at $4,000)
X_LEVELS = {"X15": 15.0, "X20": 20.0}
CONFS = ("none", "X15F0", "X20F0", "X15F1", "X20F1")
ENTRIES = ("E1", "E2")
STOPS = ("S10", "S13", "SATR", "SSTR")
TARGETS = (15.0, 20.0, 25.0, 30.0)
RR_MIN, D_MIN, D_MAX, COST_FRAC = 1.0, 5.0, 40.0, 0.15
F1_RSI_BUY, F1_RSI_SELL, F1_COST, F1_RANGE_ATR, F1_GAP_ATR = 55.0, 45.0, 0.80, 2.5, 0.5
SATR_MULT, SSTR_BUF, SSTR_LOOKBACK = 3.0, 0.2, 16
REPEAT_SEC, REPEAT_USD = 4 * 3600, 15.0
STRUCT_TYPES = ("BOS", "MSS", "CHoCH")
TFS = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
OP_COST = b13.OP_COST
EPS = 1e-9
PRIMARY = {  # name: (trigger set, confirmation, entry, stop, target); strategy 1 is handled apart (entry at P0, 13 / 13)
    "2 trigger only": ("none", "E1", "S13", 20.0),
    "3 $15 confirmation": ("X15F0", "E1", "S13", 20.0),
    "4 $20 confirmation": ("X20F0", "E1", "S13", 20.0),
    "5a $15 + momentum and structure": ("X15F1", "E1", "S13", 20.0),
    "5b $20 + momentum and structure": ("X20F1", "E1", "S13", 20.0),
}
HYPOTHESES = {f"H{k + 1}": (fam, name) for k, (fam, name) in enumerate(
    [(f, n) for f in ("ENG", "STR") for n in ("3 $15 confirmation", "4 $20 confirmation", "5a $15 + momentum and structure",
                                              "5b $20 + momentum and structure")])}


# ---------------- the 15m path ----------------
@dataclass
class Path15:
    t: np.ndarray        # bar open, epoch s
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    c_prev: np.ndarray
    atr: np.ndarray      # ATR14 (Wilder) at the bar's close
    rsi: np.ndarray      # RSI14
    ema20: np.ndarray
    cost: np.ndarray     # model cost $ per oz at the bar
    up_evt: np.ndarray   # a bullish BOS / MSS / CHoCH is published at this bar's close
    dn_evt: np.ndarray


def make_path(df: pd.DataFrame, up_evt: np.ndarray | None = None, dn_evt: np.ndarray | None = None) -> Path15:
    o, h, lo_, c = (np.array(df[k].to_numpy(float), dtype=float) for k in ("open", "high", "low", "close"))   # own copies
    n = len(c)
    cp = np.concatenate([[np.nan], c[:-1]])
    return Path15(t=ta.epoch_s(df.index).astype(np.int64), o=o, h=h, l=lo_, c=c, c_prev=cp, atr=np.array(ta.atr(h, lo_, c, 14), float),
                  rsi=np.array(ta.rsi(c, 14), float), ema20=np.array(ta.ema(c, 20), float), cost=np.array(H.cost_pts(df.index), float),
                  up_evt=np.zeros(n, bool) if up_evt is None else np.asarray(up_evt, bool),
                  dn_evt=np.zeros(n, bool) if dn_evt is None else np.asarray(dn_evt, bool))


def struct_arrays(res, n: int) -> tuple[np.ndarray, np.ndarray]:
    up, dn = np.zeros(n, bool), np.zeros(n, bool)
    for e in res.events:
        if e["type"] in STRUCT_TYPES and e.get("dir") in (1, -1) and 0 <= e["i"] < n:
            (up if e["dir"] == 1 else dn)[e["i"]] = True
    return up, dn


# ---------------- stage A ----------------
def triggers_from_run(res, F, tf: str, kind: str) -> list[dict]:
    """ENG: the engine's SIGNAL events. STR: BOS / MSS / CHoCH with the engine's bias agreeing, the close beyond VWAP in
    that direction and session_quality >= 30 at that bar."""
    idx = pd.DatetimeIndex(F["index"])
    c = np.asarray(F["c"], float)
    sec = TFS[tf]
    R = res.rows
    bull, bear = np.asarray(R["bull"], float), np.asarray(R["bear"], float)
    vwap, sq = np.asarray(F["vwap"], float), np.asarray(F["session_quality"], float)
    reg = list(R["regime_label"])
    out = []
    for e in res.events:
        i, d = e["i"], e.get("dir")
        if d not in (1, -1) or not (0 <= i < len(c)):
            continue
        if kind == "ENG":
            if e["type"] != "SIGNAL":
                continue
        else:
            if e["type"] not in STRUCT_TYPES:
                continue
            ok_bias = (bull[i] > bear[i]) if d == 1 else (bear[i] > bull[i])
            ok_vwap = np.isfinite(vwap[i]) and (c[i] - vwap[i]) * d > 0
            if not (ok_bias and ok_vwap and sq[i] >= 30):
                continue
        out.append({"tf": tf, "kind": kind, "i": int(i), "t_close": int(idx[i].timestamp()) + sec, "dir": int(d), "p0": float(c[i]),
                    "bull": float(bull[i]), "bear": float(bear[i]), "regime": str(reg[i]), "sl_eng": e.get("sl"), "tp1_eng": e.get("tp1")})
    return out


def dedupe(trigs: list[dict]) -> list[dict]:
    """The live REPEAT rule (A1): pooled across timeframes in time order, a trigger in the same direction within 4 hours
    and $15 (scaled) of an earlier KEPT trigger's P0 is dropped."""
    kept: list[dict] = []
    for x in sorted(trigs, key=lambda z: (z["t_close"], -TFS[z["tf"]])):
        s = x["p0"] / 4000.0
        if any(k["dir"] == x["dir"] and x["t_close"] - k["t_close"] <= REPEAT_SEC and abs(x["p0"] - k["p0"]) <= REPEAT_USD * s
               for k in kept[-50:]):
            continue
        kept.append(x)
    return kept


def attach(trigs: list[dict], P: Path15) -> dict:
    """Arrays for the triggers that have a full confirmation window on the path: j0 = first 15m bar opening at or after
    the trigger's close."""
    t0 = np.asarray([x["t_close"] for x in trigs], np.int64)
    j0 = np.searchsorted(P.t, t0)
    ok = (j0 >= SSTR_LOOKBACK) & (j0 + WIN + HOLD + LIMIT_BARS < len(P.t))
    keep = np.flatnonzero(ok)
    return {"trig": [trigs[k] for k in keep], "j0": j0[keep], "p0": np.asarray([trigs[k]["p0"] for k in keep], float),
            "d": np.asarray([trigs[k]["dir"] for k in keep], int), "t_close": t0[keep]}


# ---------------- stage B ----------------
def _win(a: np.ndarray, j: np.ndarray, w: int) -> np.ndarray:
    return sliding_window_view(a, w)[j]


def confirm(P: Path15, A: dict, conf: str) -> dict:
    """Status per trigger: CONFIRMED (k = absolute 15m bar of confirmation), INVALIDATED (price or structure) or EXPIRED;
    plus the touch milestones. conf 'none' = no confirmation (the trade starts at the trigger)."""
    j0, p0, d = A["j0"], A["p0"], A["d"]
    n = len(j0)
    s = p0 / 4000.0
    dd, pp, ss = d[:, None], p0[:, None], s[:, None]
    hh, ll, cc, oo = _win(P.h, j0, WIN), _win(P.l, j0, WIN), _win(P.c, j0, WIN), _win(P.o, j0, WIN)
    fav = np.where(dd > 0, hh - pp, pp - ll)
    adv = np.where(dd > 0, pp - ll, hh - pp)
    out = {"reached15": (fav >= 15.0 * ss - EPS).any(1), "reached20": (fav >= 20.0 * ss - EPS).any(1),
           "reached30": (fav >= 30.0 * ss - EPS).any(1)}
    if conf == "none":
        out.update(status=np.array(["TRIGGER"] * n, object), k=j0 - 1, inv_kind=np.array([""] * n, object))
        return out
    X = X_LEVELS[conf[:3]]
    inv_p = adv >= INV * ss - EPS
    inv_s = np.where(dd > 0, _win(P.dn_evt, j0, WIN), _win(P.up_evt, j0, WIN))
    inv = inv_p | inv_s
    first_inv = np.where(inv.any(1), inv.argmax(1), WIN)
    cand = (cc - pp) * dd >= X * ss - EPS
    if conf.endswith("F1"):
        rsi, ema, atr = _win(P.rsi, j0, WIN), _win(P.ema20, j0, WIN), _win(P.atr, j0, WIN)
        cost, cprev = _win(P.cost, j0, WIN), _win(P.c_prev, j0, WIN)
        same = np.where(dd > 0, _win(P.up_evt, j0, WIN), _win(P.dn_evt, j0, WIN))
        mom = np.where(dd > 0, rsi >= F1_RSI_BUY, rsi <= F1_RSI_SELL) & ((cc - ema) * dd > 0)
        struct = np.cumsum(same, axis=1) >= 1
        calm = ((hh - ll) <= F1_RANGE_ATR * atr) & (np.abs(oo - cprev) <= F1_GAP_ATR * atr)
        cand = cand & mom & struct & (cost <= F1_COST + EPS) & calm
    first_conf = np.where(cand.any(1), cand.argmax(1), WIN)
    confirmed = (first_conf < first_inv) & (first_conf < WIN)        # the same bar invalidating and closing beyond: invalid
    invalid = ~confirmed & (first_inv < WIN)
    status = np.where(confirmed, "CONFIRMED", np.where(invalid, "INVALIDATED", "EXPIRED")).astype(object)
    row = np.arange(n)
    fi = np.minimum(first_inv, WIN - 1)
    kind = np.where(invalid, np.where(inv_p[row, fi], "price", "structure"), "").astype(object)
    out.update(status=status, k=np.where(confirmed, j0 + first_conf, -1), inv_kind=kind)
    return out


# ---------------- the plan and the exit ----------------
def _sstr_level(P: Path15, j0: np.ndarray, k: np.ndarray, d: np.ndarray, conf: str) -> np.ndarray:
    lv = np.full(len(j0), np.nan)
    for x in range(len(j0)):
        a, b = (j0[x] - SSTR_LOOKBACK, j0[x]) if conf == "none" else (j0[x], k[x] + 1)
        if b <= a or k[x] < 0:
            continue
        lv[x] = (P.l[a:b].min() - SSTR_BUF * P.atr[k[x]]) if d[x] > 0 else (P.h[a:b].max() + SSTR_BUF * P.atr[k[x]])
    return lv


def plan_and_exit(P: Path15, A: dict, C: dict, conf: str, entry: str, stop: str, T: float, sstr: np.ndarray | None = None,
                  own: tuple[np.ndarray, np.ndarray] | None = None, rules: bool = True) -> dict:
    """Trades for one configuration. own = (stop distance, target distance) in price units overriding stop / T (the
    engine's own levels); rules=False skips the EXECUTE check (strategy 1 as alerted)."""
    d, p0 = A["d"], A["p0"]
    s = p0 / 4000.0
    act = (C["status"] == "CONFIRMED") if conf != "none" else np.ones(len(d), bool)
    k = C["k"]
    n = len(d)
    ent, start, mask_tp = np.full(n, np.nan), np.full(n, -1), np.zeros(n, bool)
    missed = np.zeros(n, bool)
    for x in np.flatnonzero(act):
        if conf == "none" or entry == "E1":
            ent[x], start[x] = (p0[x], A["j0"][x]) if conf == "none" else (P.c[k[x]], k[x] + 1)
            continue
        L = p0[x] + d[x] * X_LEVELS[conf[:3]] * s[x]                  # E2: a limit at the threshold, 8 bars
        for b in range(k[x] + 1, k[x] + 1 + LIMIT_BARS):
            if d[x] > 0 and P.l[b] <= L:
                ent[x], start[x], mask_tp[x] = min(P.o[b], L), b, True
                break
            if d[x] < 0 and P.h[b] >= L:
                ent[x], start[x], mask_tp[x] = max(P.o[b], L), b, True
                break
        else:
            missed[x] = True
    kk = np.where(k >= 0, k, A["j0"] - 1)
    atr_k = P.atr[kk]
    if own is not None:
        D, Tpx = own
    else:
        Tpx = T * s
        if stop == "S10":
            D = 10.0 * s
        elif stop == "S13":
            D = 13.0 * s
        elif stop == "SATR":
            D = SATR_MULT * atr_k
        else:
            lv = sstr if sstr is not None else _sstr_level(P, A["j0"], kk, d, conf)
            D = (ent - lv) * d
    D = np.asarray(D, float)
    filled = np.isfinite(ent) & (start >= 0)
    cost = P.cost[kk]
    if rules:
        ex = filled & np.isfinite(D) & (D > 0) & (Tpx / np.where(D > 0, D, np.nan) >= RR_MIN - EPS) & (D >= D_MIN * s - EPS) \
            & (D <= D_MAX * s + EPS) & (cost <= COST_FRAC * D / s + EPS)
    else:
        ex = filled & np.isfinite(D) & (D > 0)
    rejected = filled & ~ex
    res = {"execute": ex, "rejected": rejected, "missed": missed, "outcome": np.array([""] * n, object), "net": np.full(n, np.nan),
           "r": np.full(n, np.nan), "hold_min": np.full(n, np.nan), "cost": cost, "entry": ent, "D": D, "t_entry": np.zeros(n, np.int64)}
    ii = np.flatnonzero(ex)
    if not len(ii):
        return res
    b0 = start[ii]
    oo, hh, ll, cc = (_win(a, b0, HOLD) for a in (P.o, P.h, P.l, P.c))
    dd = d[ii][:, None]
    e_ = ent[ii][:, None]
    tp = e_ + dd * np.broadcast_to(np.asarray(Tpx, float), (n,))[ii][:, None]
    sl = e_ - dd * D[ii][:, None]
    m0 = np.zeros(oo.shape, bool)
    m0[:, 0] = mask_tp[ii]
    open_sl = (oo - sl) * dd <= 0
    open_tp = ((oo - tp) * dd >= 0) & ~m0
    hit_sl = np.where(dd > 0, ll <= sl, hh >= sl)
    hit_tp = np.where(dd > 0, hh >= tp, ll <= tp) & ~m0
    evt = open_sl | open_tp | hit_sl | hit_tp
    first = np.where(evt.any(1), evt.argmax(1), HOLD)
    r = np.arange(len(ii))
    f = np.minimum(first, HOLD - 1)
    o_sl, o_tp, h_sl, h_tp = open_sl[r, f], open_tp[r, f], hit_sl[r, f], hit_tp[r, f]
    none = first >= HOLD
    out = np.where(none, "TIMEOUT", np.where(o_sl, "SL", np.where(o_tp, "TP", np.where(h_sl & h_tp, "AMBIGUOUS",
                   np.where(h_tp, "TP", "SL"))))).astype(object)
    px = np.where(none, cc[r, HOLD - 1], np.where(o_sl | o_tp, oo[r, f], np.where(out == "TP", tp[:, 0], sl[:, 0])))
    net = (px - ent[ii]) * d[ii] / s[ii] - cost[ii]
    res["outcome"][ii] = out
    res["net"][ii] = net
    res["r"][ii] = net / (D[ii] / s[ii])
    res["hold_min"][ii] = (np.where(none, HOLD - 1, first) + 1) * 15.0         # from the entry bar to the exit bar
    res["t_entry"][ii] = P.t[b0]
    return res


# ---------------- statistics ----------------
def max_drawdown(x: np.ndarray) -> float:
    if not len(x):
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(x)])
    return float((np.maximum.accumulate(eq) - eq).max())


def summarize(A: dict, C: dict, T_: dict) -> dict:
    ex = T_["execute"]
    order = np.argsort(T_["t_entry"][ex], kind="stable")
    net, r, out = T_["net"][ex][order], T_["r"][ex][order], T_["outcome"][ex][order]
    n = int(ex.sum())
    wins, losses = net[net > 0].sum(), -net[net < 0].sum()

    def t_of(x):
        sd = float(np.std(x, ddof=1)) if len(x) > 2 else 0.0
        return float(np.mean(x) / (sd / math.sqrt(len(x)))) if sd > 0 else math.nan

    amb = out == "AMBIGUOUS"
    st = C["status"]
    return {"triggers": len(A["d"]), "reached15": int(C["reached15"].sum()), "reached20": int(C["reached20"].sum()),
            "confirmed": int((st == "CONFIRMED").sum()), "invalidated": int((st == "INVALIDATED").sum()),
            "invalidated_price": int(((st == "INVALIDATED") & (C["inv_kind"] == "price")).sum()),
            "invalidated_structure": int(((st == "INVALIDATED") & (C["inv_kind"] == "structure")).sum()),
            "expired": int((st == "EXPIRED").sum()), "rejected": int(T_["rejected"].sum()), "missed_limit": int(T_["missed"].sum()),
            "missed_opportunities_30": int((C["reached30"] & ~ex).sum()),
            "trades": n, "tp_first": float(np.mean(out == "TP")) if n else math.nan, "sl_first": float(np.mean(out == "SL")) if n else math.nan,
            "ambiguous": float(np.mean(amb)) if n else math.nan, "timeout": float(np.mean(out == "TIMEOUT")) if n else math.nan,
            "profit_factor": float(wins / losses) if losses > 0 else (math.inf if wins > 0 else math.nan),
            "mean_net_usd_per_oz": float(np.mean(net)) if n else math.nan, "sd_net": float(np.std(net, ddof=1)) if n > 2 else math.nan,
            "t": t_of(net) if n else math.nan, "mean_r": float(np.mean(r)) if n else math.nan,
            "max_drawdown_r": max_drawdown(r), "avg_hold_min": float(np.mean(T_["hold_min"][ex])) if n else math.nan,
            "avg_cost_usd_per_oz": float(np.mean(T_["cost"][ex])) if n else math.nan,
            "mean_net_ambiguous_excluded": float(np.mean(net[~amb])) if (n and (~amb).any()) else math.nan,
            "mean_net_operator_cost": float(np.mean(net + T_["cost"][ex][order] - OP_COST)) if n else math.nan,
            "usd_per_trade_0p2lot": float(np.mean(net)) * 20 if n else math.nan}


def holm_adjusted(ps: dict) -> dict:
    """Holm step-down adjusted p-values."""
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, run_max, out = len(items), 0.0, {}
    for r, (k, p) in enumerate(items):
        run_max = max(run_max, min(1.0, (m - r) * p))
        out[k] = run_max
    return out


def welch_p(a: np.ndarray, b: np.ndarray) -> float:
    """One-sided p of mean(a) > mean(b)."""
    if len(a) < 3 or len(b) < 3:
        return math.nan
    se = math.sqrt(np.var(a, ddof=1) / len(a) + np.var(b, ddof=1) / len(b))
    return 1 - H._norm_cdf((np.mean(a) - np.mean(b)) / se) if se > 0 else math.nan


def monthly(T_: dict, months: pd.PeriodIndex) -> np.ndarray:
    ex = T_["execute"]
    s = pd.Series(T_["r"][ex], index=pd.to_datetime(T_["t_entry"][ex], unit="s", utc=True).tz_localize(None).to_period("M"))
    g = s.groupby(level=0).mean()
    return g.reindex(months).fillna(0.0).to_numpy(float)


# ---------------- data and runs ----------------
def load_part(rd: str, part: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Development / validation / holdout through the harness seals; 'recent' = 2026-01-01 onwards (not sealed), scored
    after a two-month warm-up inside it so no holdout bar is read."""
    if part == "recent":
        m15, h1 = history.load(rd, "XAU/USD", "15min"), history.load(rd, "XAU/USD", "1h")
        lo = H.HOLD[1]
        m15, h1 = m15[m15.index >= lo], h1[h1.index >= lo]
        return m15, h1, lo + pd.Timedelta(days=59)
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), part, REG if part != "development" else None)
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), part, REG if part != "development" else None)
    start = b13.SCORE_FROM if part == "development" else m15.index[0] + pd.Timedelta(days=67)
    return m15, h1, start


def engine_runs(m15: pd.DataFrame, h1: pd.DataFrame, log=print) -> dict:
    bases = {"15m": m15, "30m": sources.resample_ohlc(m15, "30min"), "1h": h1, "4h": sources.resample_ny_session(h1, 4)}
    out = {}
    for tf, base in bases.items():
        m = b10.make_market(base, h1, tf, TFS[tf])
        F = compute_features(m, config.DEFAULT)
        out[tf] = (engine.run(m, config.DEFAULT, "treatment", F), F)
        log(f"[B19] engine on {len(base)} {tf} bars")
    return out


def news_windows() -> list[tuple[int, int]]:
    w = []
    for kind, days in b8_news.DATES.items():
        for day in days:
            t = int(b8_news.release_utc(kind, day).timestamp())
            w.append((t, t + 7200))
    return w


def regimes(A: dict, P: Path15, nw: list[tuple[int, int]]) -> dict:
    trig = A["trig"]
    vol = P.atr / P.c
    q80 = float(np.nanquantile(vol, 0.8))
    lab = {}
    for x, tr in enumerate(trig):
        g = []
        g.append("trending" if tr["regime"] in ("STRONG TR", "EXPANSION") else "ranging" if tr["regime"] in b10.RANGE_REGIMES else "other")
        if vol[A["j0"][x] - 1] >= q80:
            g.append("volatile")
        if any(a <= tr["t_close"] <= b for a, b in nw):
            g.append("news")
        lab[x] = g
    return lab


def run(rd: str, part: str = "development", configs: list[str] | None = None, log=print) -> dict:
    m15, h1, score_from = load_part(rd, part)
    runs = engine_runs(m15, h1, log)
    res15, _ = runs["15m"]
    up, dn = struct_arrays(res15, len(m15))
    P = make_path(m15, up, dn)
    t_from = int(score_from.timestamp())
    fams = {}
    for kind in ("ENG", "STR"):
        trig = [x for tf, (res, F) in runs.items() for x in triggers_from_run(res, F, tf, kind)]
        trig = dedupe([x for x in trig if x["t_close"] >= t_from])
        fams[kind] = attach(trig, P)
        log(f"[B19] {kind}: {len(fams[kind]['d'])} triggers (after REPEAT)")
    rows = np.flatnonzero(P.t >= t_from)[::8]
    rows = rows[(rows >= SSTR_LOOKBACK) & (rows + 1 + WIN + HOLD + LIMIT_BARS < len(P.t))]
    rt = [{"tf": "15m", "kind": "N2", "i": int(i), "t_close": int(P.t[i]) + 900, "dir": dsg, "p0": float(P.c[i]), "regime": "",
           "bull": math.nan, "bear": math.nan, "sl_eng": None, "tp1_eng": None} for i in rows for dsg in (1, -1)]
    fams["N2"] = attach(rt, P)
    months = pd.period_range(score_from.tz_localize(None), m15.index[-1].tz_localize(None), freq="M")
    nw = news_windows() if part == "development" else []
    out = {"registration": REG, "part": part, "window": [str(m15.index[0]), str(m15.index[-1])], "scored_from": str(score_from),
           "triggers": {k: len(v["d"]) for k, v in fams.items()}, "per_tf": {}, "configs": {}, "primary": {}, "strategy1": {},
           "regimes": {}, "monthly": {}, "per_trade": {}}
    for kind in ("ENG", "STR"):
        out["per_tf"][kind] = {tf: int(sum(1 for x in fams[kind]["trig"] if x["tf"] == tf)) for tf in TFS}
    want = None if configs is None else set(configs)
    for fam_name in ("ENG", "STR", "N2"):
        A = fams[fam_name]
        if not len(A["d"]):
            continue
        reg_lab = regimes(A, P, nw) if fam_name != "N2" else {}
        for conf in CONFS:
            C = confirm(P, A, conf)
            kk = np.where(C["k"] >= 0, C["k"], A["j0"] - 1)
            sstr = _sstr_level(P, A["j0"], kk, A["d"], conf)
            for entry in (("E1",) if conf == "none" else ENTRIES):
                for stop in STOPS:
                    for T in TARGETS:
                        key = f"{fam_name} {conf} {entry} {stop} T{T:g}"
                        base_key = key.replace("N2 ", "")
                        if want is not None and fam_name != "N2" and key not in want:
                            continue
                        if want is not None and fam_name == "N2" and not any(w.endswith(base_key) for w in want):
                            continue
                        T_ = plan_and_exit(P, A, C, conf, entry, stop, T, sstr=sstr if stop == "SSTR" else None)
                        sm = summarize(A, C, T_)
                        out["configs"][key] = sm
                        ex = T_["execute"]
                        o = np.argsort(T_["t_entry"][ex], kind="stable")
                        if fam_name != "N2" or (conf, entry, stop, T) in PRIMARY.values():
                            out["per_trade"][key] = {"net": T_["net"][ex][o], "r": T_["r"][ex][o], "t": T_["t_entry"][ex][o]}
                        if fam_name != "N2":
                            out["monthly"][key] = monthly(T_, months).tolist()
                            for name, (pc, pe, ps, pt) in PRIMARY.items():
                                if (conf, entry, stop, T) == (pc, pe, ps, pt):
                                    by = {}
                                    for g in ("trending", "ranging", "other", "volatile", "news"):
                                        sel = np.array([g in reg_lab.get(x, []) for x in range(len(A["d"]))], bool) & ex
                                        nn = int(sel.sum())
                                        by[g] = {"trades": nn, "tp_first": float(np.mean(T_["outcome"][sel] == "TP")) if nn else None,
                                                 "mean_net": float(np.mean(T_["net"][sel])) if nn else None}
                                    out["regimes"][f"{fam_name} {name}"] = by
                                    tfs_ = {}
                                    for tf in TFS:
                                        sel = np.array([A["trig"][x]["tf"] == tf for x in range(len(A["d"]))], bool) & ex
                                        nn = int(sel.sum())
                                        tfs_[tf] = {"trades": nn, "tp_first": float(np.mean(T_["outcome"][sel] == "TP")) if nn else None,
                                                    "mean_net": float(np.mean(T_["net"][sel])) if nn else None}
                                    out["regimes"][f"{fam_name} {name} by timeframe"] = tfs_
        if fam_name in ("ENG", "STR"):                    # strategy 1: entry at P0, as alerted (-13 / +13) and the engine's own levels
            C = confirm(P, A, "none")
            s = A["p0"] / 4000.0
            T_ = plan_and_exit(P, A, C, "none", "E1", "S13", 13.0, own=(13.0 * s, 13.0 * s), rules=False)
            out["strategy1"][f"{fam_name} as alerted 13/13"] = summarize(A, C, T_)
            ex = T_["execute"]
            o = np.argsort(T_["t_entry"][ex], kind="stable")
            out["per_trade"][f"{fam_name} 1 as alerted"] = {"net": T_["net"][ex][o], "r": T_["r"][ex][o], "t": T_["t_entry"][ex][o]}
            if fam_name == "ENG":
                sl = np.array([x["sl_eng"] if x["sl_eng"] is not None else np.nan for x in A["trig"]], float)
                tp = np.array([x["tp1_eng"] if x["tp1_eng"] is not None else np.nan for x in A["trig"]], float)
                T_ = plan_and_exit(P, A, C, "none", "E1", "S13", 13.0, own=(np.abs(A["p0"] - sl), np.abs(tp - A["p0"])), rules=False)
                out["strategy1"]["ENG engine's own SL / TP1"] = summarize(A, C, T_)
    # primary tests
    ps = {}
    for h, (fam, name) in HYPOTHESES.items():
        pc, pe, pst, pt = PRIMARY[name]
        key = f"{fam} {pc} {pe} {pst} T{pt:g}"
        sm = out["configs"].get(key)
        n2 = out["per_trade"].get(f"N2 {pc} {pe} {pst} T{pt:g}", {}).get("net", [])
        me = np.asarray(out["per_trade"].get(key, {}).get("net", []), float)
        p_t = H.t_pvalue(sm["t"], sm["trades"]) if sm and sm["trades"] > 2 else math.nan
        p_w = welch_p(me, np.asarray(n2, float))
        ps[h] = p_t if math.isfinite(p_t) else 1.0
        out["primary"][h] = {"family": fam, "strategy": name, "config": key, "trades": sm["trades"] if sm else 0,
                             "mean_net": sm["mean_net_usd_per_oz"] if sm else None, "t": sm["t"] if sm else None,
                             "p_t": p_t, "n2_mean_net": float(np.mean(n2)) if len(n2) else None, "p_vs_n2": p_w,
                             "profit_factor": sm["profit_factor"] if sm else None}
    hol = holm_adjusted(ps)
    for h, v in out["primary"].items():
        hp = hol.get(h)
        v["p_holm"] = hp
        enough = v["trades"] >= 50
        v["verdict"] = ("INSUFFICIENT" if not enough else
                        "PASS" if (hp is not None and hp <= 0.05 and v["p_vs_n2"] is not None and math.isfinite(v["p_vs_n2"])
                                   and v["p_vs_n2"] <= 0.05 and (v["profit_factor"] or 0) >= 1.1) else "FAIL")
    return out


def grid_stats(out: dict) -> dict:
    """Walk-forward, PBO, DSR and Reality Check over the 288 ENG / STR configurations (development)."""
    keys = [k for k in out["configs"] if not k.startswith("N2")]
    perf = np.array([out["monthly"][k] for k in keys]).T          # months x configs
    res = {"configurations": len(keys)}
    res["pbo"] = H.pbo_cscv(perf, 8) if perf.shape[0] >= 8 else {"pbo": None}
    res["reality_check"] = H.reality_check(perf, B=1000)
    res["reality_check"]["best_config"] = keys[res["reality_check"]["best"]]
    srs, best = [], None
    for k in keys:
        r = np.asarray(out["per_trade"][k]["r"], float)
        if len(r) >= 30 and np.std(r, ddof=1) > 0:
            sr = float(np.mean(r) / np.std(r, ddof=1))
            srs.append(sr)
            if best is None or sr > best[1]:
                best = (k, sr, r)
    if best:
        r = best[2]
        sk = float(pd.Series(r).skew())
        ku = float(pd.Series(r).kurt()) + 3.0
        res["dsr"] = {"best_config": best[0], "sr_per_trade": best[1], "trades": len(r),
                      **H.deflated_sharpe(best[1], len(r), sk, ku, srs)}
    # walk-forward: train 12 months, test 6, step 6
    t0 = pd.Timestamp(out["scored_from"])
    end = pd.Timestamp(out["window"][1])
    wf, cur = [], t0
    while cur + pd.DateOffset(months=12) < end:
        tr_a, tr_b = cur, cur + pd.DateOffset(months=12)
        te_b = min(tr_b + pd.DateOffset(months=6), end)
        best_k, best_m = None, -math.inf
        for k in keys:
            t = np.asarray(out["per_trade"][k]["t"], np.int64)
            r = np.asarray(out["per_trade"][k]["r"], float)
            sel = (t >= tr_a.timestamp()) & (t < tr_b.timestamp())
            if sel.sum() >= 20 and r[sel].mean() > best_m:
                best_k, best_m = k, float(r[sel].mean())
        if best_k:
            t = np.asarray(out["per_trade"][best_k]["t"], np.int64)
            r = np.asarray(out["per_trade"][best_k]["r"], float)
            n_ = np.asarray(out["per_trade"][best_k]["net"], float)
            sel = (t >= tr_b.timestamp()) & (t < te_b.timestamp())
            wf.append({"train": [str(tr_a.date()), str(tr_b.date())], "test_to": str(te_b.date()), "selected": best_k,
                       "train_mean_r": best_m, "test_trades": int(sel.sum()), "test_mean_r": float(r[sel].mean()) if sel.any() else None,
                       "test_mean_net": float(n_[sel].mean()) if sel.any() else None, "test_r": r[sel].tolist()})
        cur = cur + pd.DateOffset(months=6)
    allr = np.concatenate([np.asarray(w["test_r"]) for w in wf]) if wf else np.zeros(0)
    res["walk_forward"] = {"windows": [{k: v for k, v in w.items() if k != "test_r"} for w in wf], "test_trades": len(allr),
                           "test_mean_r": float(allr.mean()) if len(allr) else None,
                           "test_t": float(allr.mean() / (allr.std(ddof=1) / math.sqrt(len(allr)))) if len(allr) > 2 and allr.std(ddof=1) > 0 else None}
    return res


def candidates(out: dict, gs: dict) -> list[str]:
    wf_ok = (gs["walk_forward"]["test_mean_r"] or -1) > 0
    c = []
    for k, sm in out["configs"].items():
        if k.startswith("N2") or sm["trades"] < 50:
            continue
        if (sm["t"] or 0) >= 2.0 and (sm["profit_factor"] or 0) >= 1.2 and wf_ok:
            c.append((sm["t"], k))
    return [k for _, k in sorted(c, reverse=True)[:2]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--part", default="development", choices=("development", "validation", "holdout", "recent"))
    ap.add_argument("--configs", help="comma-separated configuration keys (validation / holdout / recent)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    ap.add_argument("--val-results", help="holdout only: the committed validation results; every config must have passed")
    a = ap.parse_args(argv)
    cfgs = [x.strip() for x in a.configs.split(",")] if a.configs else None
    if a.part in ("validation", "holdout", "recent") and not cfgs:
        raise SystemExit("validation / holdout / recent run only the declared configurations (--configs)")
    if a.part == "holdout":                                 # the registration's gate: development AND validation passed
        val = {}
        if a.val_results:
            with open(a.val_results) as f:
                val = json.load(f)
        passed = {k for k, v in (val.get("validation_pass") or {}).items() if v}
        if not cfgs or not set(cfgs) <= passed:
            raise SystemExit(f"the holdout opens only for candidates that passed validation: {sorted(set(cfgs or []) - passed)}")
    out = run(a.rd, a.part, cfgs)
    out["utc"] = datetime.now(timezone.utc).isoformat()
    if a.part == "development":
        out["grid"] = grid_stats(out)
        out["candidates"] = candidates(out, out["grid"])
    keep = {k for k in out["per_trade"] if " 1 as alerted" in k or any(k.endswith(f"{c} {e} {st} T{t:g}") for c, e, st, t in PRIMARY.values())}
    out["per_trade"] = {k: {a_: v[a_].tolist() for a_ in v} for k, v in out["per_trade"].items() if k in keep}
    with open(a.out, "w") as f:
        json.dump(b13._clean(out), f, indent=1, allow_nan=False)
    if a.trials:
        for k, sm in out["configs"].items():
            if k.startswith("N2"):
                continue
            H.log_trial(a.trials, {"phase": REG, "partition": a.part, "id": f"B19 {k}", **b13._clean(sm)})
        for h, v in out["primary"].items():
            H.log_trial(a.trials, {"phase": REG, "partition": a.part, "id": f"B19 {h} {v['family']} {v['strategy']}",
                                   "primary": h, **b13._clean(v)})
    print(json.dumps({h: (v["trades"], v["verdict"]) for h, v in out["primary"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
