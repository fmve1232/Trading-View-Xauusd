"""Phase B31 (research/registrations/B31.json, approved 2026-11-15; written after the registration was committed).

Liquidity-aware opportunity selection on 15m bars: five independent modules built from the frozen engine's detectors,
each with a structural stop, a +$10 first target (+$15 / +$20 raced as well), a net R:R >= 1 check on TP1, a room-to-
opposing-liquidity check and one position at a time; compared with the production engine's signals, the F1-F4 engine's
and a matched random control. Every value used at bar j is known at bar j's open or close as stated; nothing reads a later
bar. Distances are $ at $4,000 scaled by s = price / 4000; costs are $ per oz. Research code: never imported by production.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import sessions, ta
from ..data import sources
from . import b10, b13, b19, history
from . import harness as H

REG = "B31"
TP = (10.0, 15.0, 20.0)
REJECT_BARS, SHIFT_BARS = 3, 8
LIMIT_BARS = b19.LIMIT_BARS            # 8: a limit order's validity
SL_BUF = b19.SSTR_BUF                  # 0.2 x ATR beyond the structure
D_MIN, RR_MIN, COST_FRAC = b19.D_MIN, b19.RR_MIN, b19.COST_FRAC
HOLD = 96                              # 24 h time stop
FVG_ATR = 0.3                          # the engine's FVG gap rule
DISP_BODY = 2.5                        # the engine's disp_mult: "no fading a strong displacement" (D)
REPEAT_SEC, REPEAT_USD = 4 * 3600, 15.0
RND_K, SEED, BOOT = 20, 31, 2000
OP_COST = b13.OP_COST
EPS = 1e-9
SELL_SIDE = ("PDL", "PWL", "ASL", "LOL", "NYL", "EQL")      # swept -> BUY
BUY_SIDE = ("PDH", "PWH", "ASH", "LOH", "NYH", "EQH")       # swept -> SELL
RANK = {"PW": 1.0, "PD": 0.8, "AS": 0.6, "LO": 0.6, "NY": 0.6, "EQ": 0.6}
MODULES = ("A", "B", "C", "D", "E")
SEALED = ("validation", "holdout")
WEIGHTS = {"liq": 20, "struct": 20, "entry": 20, "volvol": 15, "sess": 10, "cross": 5, "space": 10}


# ---------------- context: every array a module reads ----------------
@dataclass
class Ctx:
    t: np.ndarray; o: np.ndarray; h: np.ndarray; l: np.ndarray; c: np.ndarray  # noqa: E702
    atr: np.ndarray; aatr: np.ndarray; cost: np.ndarray; date: np.ndarray; sess: np.ndarray
    pools: dict                      # name -> level known before the bar (NaN = none)
    asia_date: np.ndarray            # trading date of the Asian session behind ASH / ASL
    up_any: np.ndarray; dn_any: np.ndarray; up_shift: np.ndarray; dn_shift: np.ndarray
    ob_bull_hi: np.ndarray; ob_bear_lo: np.ndarray
    ranging: np.ndarray; vwap: np.ndarray; lo2: np.ndarray; up2: np.ndarray
    htf_up: np.ndarray; htf_dn: np.ndarray; e15_up: np.ndarray; e1_up: np.ndarray; e4_up: np.ndarray
    atr_ok: np.ndarray


def session_label(cal: pd.DataFrame) -> np.ndarray:
    a, lo, ny = (cal[k].to_numpy(bool) for k in ("in_asian", "in_london", "in_ny"))
    return np.where(lo & ny, "LONDON+NY", np.where(lo, "LONDON", np.where(ny, "NEW YORK", np.where(a, "ASIAN", "OFF")))).astype(object)


def prev_group(key: np.ndarray, x: np.ndarray, fn) -> np.ndarray:
    """For each bar: fn (max / min) of x over ALL bars of the previous group (consecutive key runs, in order)."""
    out = np.full(len(x), np.nan)
    order = list(dict.fromkeys(key.tolist()))
    s = pd.Series(x).groupby(key, sort=False).agg(fn)
    prev = {order[i]: order[i - 1] for i in range(1, len(order))}
    for i, k in enumerate(key):
        if k in prev:
            out[i] = s[prev[k]]
    return out


def last_completed_session(flag: np.ndarray, h: np.ndarray, l: np.ndarray, date: np.ndarray):
    """High / low of the most recently COMPLETED run of `flag` before each bar (a run's levels exist from the bar after
    its last bar), and the trading date that run belonged to."""
    n = len(flag)
    hi, lo, dt = np.full(n, np.nan), np.full(n, np.nan), np.array([None] * n, object)
    runs, i = [], 0
    while i < n:
        if flag[i]:
            j = i
            while j + 1 < n and flag[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    for r, (a, b) in enumerate(runs):
        end = runs[r + 1][1] + 1 if r + 1 < len(runs) else n
        hi[b + 1:end], lo[b + 1:end] = h[a:b + 1].max(), l[a:b + 1].min()
        dt[b + 1:end] = date[a]
    return hi, lo, dt


def build_pools(df: pd.DataFrame, cal: pd.DataFrame, eqh: np.ndarray, eql: np.ndarray):
    h, l = df["high"].to_numpy(float), df["low"].to_numpy(float)
    date = np.asarray(cal["trading_date"].to_numpy())
    iso = pd.DatetimeIndex(cal["trading_date"]).isocalendar()
    wk = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    pools = {"PDH": prev_group(date, h, "max"), "PDL": prev_group(date, l, "min"),
             "PWH": prev_group(wk, h, "max"), "PWL": prev_group(wk, l, "min")}
    asia_date = None
    for nm, col in (("AS", "in_asian"), ("LO", "in_london"), ("NY", "in_ny")):
        hi, lo, dt = last_completed_session(cal[col].to_numpy(bool), h, l, date)
        pools[nm + "H"], pools[nm + "L"] = hi, lo
        if nm == "AS":
            asia_date = dt
    prev_e = lambda a: np.concatenate([[np.nan], np.asarray(a, float)[:-1]])       # the engine's level at the bar before
    pools["EQH"], pools["EQL"] = prev_e(eqh), prev_e(eql)
    s = pd.Series(h)
    g = pd.Series(date)
    pools["CDH"] = s.groupby(g).cummax().groupby(g).shift(1).to_numpy(float)
    pools["CDL"] = pd.Series(l).groupby(g).cummin().groupby(g).shift(1).to_numpy(float)
    return pools, asia_date


def htf_up_at(t_close15: np.ndarray, bars: pd.DataFrame, sec: int) -> tuple[np.ndarray, np.ndarray]:
    """EMA20 > EMA100 (and <) on the last bar of `bars` COMPLETED by each 15m close."""
    c = bars["close"].to_numpy(float)
    e20, e100 = np.asarray(ta.ema(c, 20), float), np.asarray(ta.ema(c, 100), float)
    done = ta.epoch_s(bars.index).astype(np.int64) + sec
    k = np.searchsorted(done, t_close15, side="right") - 1
    ok = k >= 100
    kk = np.maximum(k, 0)
    return ok & (e20[kk] > e100[kk]), ok & (e20[kk] < e100[kk])


def make_ctx(m15: pd.DataFrame, h1: pd.DataFrame, res15, F15) -> Ctx:
    P = b19.make_path(m15)
    cal = sessions.calendar(m15.index)
    R = res15.rows
    n = len(m15)
    up_any, dn_any, up_shift, dn_shift = (np.zeros(n, bool) for _ in range(4))
    for e in res15.events:
        if e["type"] in b19.STRUCT_TYPES and 0 <= e["i"] < n:
            if e["dir"] == 1:
                up_any[e["i"]] = True
                up_shift[e["i"]] |= e["type"] in ("MSS", "CHoCH")
            elif e["dir"] == -1:
                dn_any[e["i"]] = True
                dn_shift[e["i"]] |= e["type"] in ("MSS", "CHoCH")
    pools, asia_date = build_pools(m15, cal, np.asarray(R["eqh"], float), np.asarray(R["eql"], float))
    t_close = P.t + 900
    e1u, e1d = htf_up_at(t_close, h1, 3600)
    h4 = sources.resample_ny_session(h1, 4)
    e4u, e4d = htf_up_at(t_close, h4, 14400)
    e15u = np.asarray(F15["ema20"], float) > np.asarray(F15["ema100"], float)
    atr = pd.Series(P.atr)
    q20 = atr.shift(1).rolling(2760, min_periods=500).quantile(0.2).to_numpy()
    q80 = atr.shift(1).rolling(2760, min_periods=500).quantile(0.8).to_numpy()
    reg = np.array([str(x) for x in R["regime_label"]], object)
    return Ctx(t=P.t, o=P.o, h=P.h, l=P.l, c=P.c, atr=P.atr, aatr=np.asarray(F15["aatr"], float), cost=P.cost,
               date=np.asarray(cal["trading_date"].to_numpy()), sess=session_label(cal), pools=pools, asia_date=asia_date,
               up_any=up_any, dn_any=dn_any, up_shift=up_shift, dn_shift=dn_shift,
               ob_bull_hi=np.asarray(R["ob_bull_hi"], float), ob_bear_lo=np.asarray(R["ob_bear_lo"], float),
               ranging=np.isin(reg, b10.RANGE_REGIMES), vwap=np.asarray(F15["vwap"], float),
               lo2=np.asarray(F15["vwap_lo2"], float), up2=np.asarray(F15["vwap_up2"], float),
               htf_up=e1u & e4u, htf_dn=e1d & e4d, e15_up=e15u, e1_up=e1u, e4_up=e4u,
               atr_ok=(P.atr >= q20) & (P.atr <= q80))


# ---------------- detectors ----------------
def fvg_at(X: Ctx, i: int, d: int):
    """The engine's FVG rule at bar i in direction d: (zone low, zone high) or None."""
    if i < 2 or not np.isfinite(X.aatr[i]):
        return None
    if d == 1 and X.l[i] > X.h[i - 2] and X.l[i] - X.h[i - 2] > FVG_ATR * X.aatr[i]:
        return (X.h[i - 2], X.l[i])
    if d == -1 and X.h[i] < X.l[i - 2] and X.l[i - 2] - X.h[i] > FVG_ATR * X.aatr[i]:
        return (X.h[i], X.l[i - 2])
    return None


def crossings(X: Ctx, kinds: tuple) -> list[dict]:
    """Every first crossing of a pool level per trading day, classified REJECTED (a close back inside within 3 bars) or
    ACCEPTED (the 3 closes from the crossing all beyond)."""
    n, out, seen = len(X.c), [], set()
    for kind in kinds:
        P = X.pools[kind]
        side = -1 if kind in SELL_SIDE else 1                    # -1: a level below price (sell-side)
        for j in range(1, n):
            lv = P[j]
            if not np.isfinite(lv):
                continue
            beyond = X.l[j] < lv - EPS if side == -1 else X.h[j] > lv + EPS
            if not beyond:
                continue
            key = (kind, round(float(lv), 2), X.date[j])
            if key in seen:
                continue
            seen.add(key)
            back = [k for k in range(j, min(j + REJECT_BARS, n)) if (X.c[k] > lv if side == -1 else X.c[k] < lv)]
            if not back and j + REJECT_BARS > n:
                seen.discard(key)                                   # undecided at the end of the data: decided later
                continue
            if back:
                k = back[0]
                ext = X.l[j:k + 1].min() if side == -1 else X.h[j:k + 1].max()
                out.append({"kind": kind, "j": j, "k": k, "lv": float(lv), "ext": float(ext), "status": "REJECTED",
                            "pen": float(abs(ext - lv)), "bars": k - j + 1, "dir": -side})       # trade away from the side
            else:
                a = j + REJECT_BARS - 1
                ext = X.l[j:a + 1].min() if side == 1 else X.h[j:a + 1].max()               # the breakout leg's far end
                out.append({"kind": kind, "j": j, "k": a, "lv": float(lv), "ext": float(ext), "status": "ACCEPTED",
                            "pen": 0.0, "bars": REJECT_BARS, "dir": side})                  # trade with the break
    return sorted(out, key=lambda e: (e["j"], e["kind"]))


def aligned(X: Ctx, i: int, d: int) -> bool:
    return bool(X.htf_up[i]) if d == 1 else bool(X.htf_dn[i])


def opposing_room(X: Ctx, i: int, d: int, e: float) -> float:
    """$ (unscaled) from e to the nearest opposing pool known at bar i (inf if none)."""
    names = ("PDH", "PWH", "ASH", "LOH", "NYH", "EQH", "CDH") if d == 1 else ("PDL", "PWL", "ASL", "LOL", "NYL", "EQL", "CDL")
    best = math.inf
    for nm in names:
        lv = X.pools[nm][i]
        if np.isfinite(lv) and (lv - e) * d > EPS:
            best = min(best, abs(lv - e))
    return best


# ---------------- setups (orders) per module ----------------
def seq_sweep(X: Ctx, ev: dict, need: str) -> dict | None:
    """A (need='A') / B (need='B') after a REJECTED sweep: the shift, the zone and the limit order; None if absent."""
    d, j = ev["dir"], ev["j"]
    end = min(j + SHIFT_BARS, len(X.c) - 1)
    for m in range(ev["k"], end + 1):
        hit = (X.up_shift[m] if need == "A" else X.up_any[m]) if d == 1 else (X.dn_shift[m] if need == "A" else X.dn_any[m])
        if not hit:
            continue
        if aligned(X, m, d) != (need == "B"):
            return None
        zone, f_bar, etype = None, m, "OB"
        for f in range(j, min(m + 2, len(X.c) - 1) + 1):
            z = fvg_at(X, f, d)
            if z is not None:
                zone, f_bar, etype = z, f, "FVG"
                break
        if zone is not None:
            lim = zone[1] if d == 1 else zone[0]
        else:                                   # no FVG by 2 bars after the shift: known only then, so the order waits
            if m + 2 > len(X.c) - 1:
                return None                         # not decided yet at the end of the data
            lim = X.ob_bull_hi[m] if d == 1 else X.ob_bear_lo[m]
            if not np.isfinite(lim):
                return None
            f_bar = m + 2
        stop = ev["ext"] - d * SL_BUF * X.atr[m]
        return {"order_bar": max(m, f_bar), "limit": float(lim), "stop": float(stop), "inval": ev["ext"], "entry_type": etype,
                "dir": d, "ev": ev, "shift_bar": m}
    return None


def seq_break(X: Ctx, ev: dict) -> dict | None:
    d, j, a = ev["dir"], ev["j"], ev["k"]
    if not any(fvg_at(X, f, d) is not None for f in range(j, a + 1)):
        return None
    leg = min(ev["ext"], ev["lv"]) if d == 1 else max(ev["ext"], ev["lv"])
    stop = leg - d * SL_BUF * X.atr[a]
    return {"order_bar": a, "limit": ev["lv"], "stop": float(stop), "inval": None, "entry_type": "RETEST", "dir": d, "ev": ev,
            "false_break_level": ev["lv"]}


def setups(X: Ctx, mod: str, evs: list[dict] | None = None) -> list[dict]:
    out = []
    if mod in ("A", "B"):
        for ev in evs:
            if ev["status"] == "REJECTED":
                s = seq_sweep(X, ev, mod)
                if s:
                    out.append(s)
    elif mod == "C":
        for ev in evs:
            if ev["status"] == "ACCEPTED":
                s = seq_break(X, ev)
                if s:
                    out.append(s)
    elif mod == "E":
        first = {}
        for ev in evs:
            if ev["kind"] in ("ASH", "ASL") and X.sess[ev["j"]] in ("LONDON", "NEW YORK", "LONDON+NY") \
                    and X.asia_date[ev["j"]] == X.date[ev["j"]] and X.date[ev["j"]] not in first:
                first[X.date[ev["j"]]] = ev
        for ev in first.values():
            s = ((seq_sweep(X, ev, "A") or seq_sweep(X, ev, "B")) if ev["status"] == "REJECTED" else seq_break(X, ev))
            if s:
                out.append(s)
    elif mod == "D":
        n = len(X.c)
        for j in range(1, n):
            if not X.ranging[j]:
                continue
            for d in (1, -1):
                dev = X.l[j] <= X.lo2[j] if d == 1 else X.h[j] >= X.up2[j]
                if not dev or (j > 0 and (X.l[j - 1] <= X.lo2[j - 1] if d == 1 else X.h[j - 1] >= X.up2[j - 1])):
                    continue                                        # the first bar of a deviation only
                ks = [k for k in range(j, min(j + REJECT_BARS, n)) if (X.c[k] > X.lo2[k] if d == 1 else X.c[k] < X.up2[k])]
                if not ks:
                    continue
                k = ks[0]
                body_against = (X.o[j:k + 1] - X.c[j:k + 1]) * d
                if (body_against >= DISP_BODY * X.atr[j:k + 1]).any():
                    continue
                ext = X.l[j:k + 1].min() if d == 1 else X.h[j:k + 1].max()
                out.append({"order_bar": k, "limit": None, "market": float(X.c[k]), "stop": float(ext - d * SL_BUF * X.atr[k]),
                            "inval": None, "entry_type": "MARKET", "dir": d, "ev": {"kind": "VWAP", "j": j, "k": k, "bars": k - j + 1},
                            "vwap": float(X.vwap[k])})
    return sorted(out, key=lambda s: s["order_bar"])


# ---------------- the order's life: checks, fill, outcome ----------------
def check(X: Ctx, s: dict, e: float, i: int, cost: float) -> str | None:
    d, sc = s["dir"], e / 4000.0
    D = (e - s["stop"]) * d / sc
    if not np.isfinite(D) or D <= 0:
        return "stop on the wrong side"
    if D < D_MIN - EPS:
        return "stop"
    if (TP[0] - cost) / (D + cost) < RR_MIN - EPS:
        return "reward"
    if cost > COST_FRAC * D + EPS:
        return "cost"
    if opposing_room(X, i, d, e) / sc < TP[0] - EPS:
        return "room"
    if s.get("vwap") is not None and (s["vwap"] - e) * d / sc < TP[0] - EPS:
        return "room"
    return None


def race(X: Ctx, b0: int, d: int, e: float, stop: float, tgt: float) -> tuple[str, int, float]:
    """From bar b0 (the bar after the fill): target vs stop; a gap through a level fills at the open; a bar touching
    both = AMBIGUOUS (the stop); time stop after HOLD bars at that close."""
    n = len(X.c)
    for b in range(b0, min(b0 + HOLD, n)):
        o, h, l = X.o[b], X.h[b], X.l[b]
        if (o - stop) * d <= 0:
            return "SL", b, o
        if (o - tgt) * d >= 0:
            return "TP", b, o
        hs = (l <= stop) if d == 1 else (h >= stop)
        ht = (h >= tgt) if d == 1 else (l <= tgt)
        if hs and ht:
            return "AMBIGUOUS", b, stop
        if hs:
            return "SL", b, stop
        if ht:
            return "TP", b, tgt
    last = min(b0 + HOLD, n) - 1
    return "TIMEOUT", last, X.c[last]


def thirds(X: Ctx, b0: int, d: int, e: float, stop: float, sc: float) -> float:
    """Secondary plan: thirds at +10 / +15 / +20, the stop moved to the entry after TP1; $ per oz (scaled) before cost."""
    legs, st, got = [e + d * x * sc for x in TP], stop, []
    b = b0
    for t in legs:
        r, b, px = race(X, b, d, e, st, t)
        if r == "TP":
            got.append((t - e) * d / sc)
            st = e
            b = b + 1
        else:
            rest = (px - e) * d / sc
            got += [rest] * (3 - len(got))
            break
    return float(np.mean(got))


def run_module(X: Ctx, sets: list[dict], t_from: int, cost_kind: str = "model") -> dict:
    """Every setup through repeat -> checks -> fill or invalidation -> outcome, one position at a time."""
    n = len(X.c)
    stat = {"setups": 0, "repeat": 0, "rejected": {}, "invalidated": 0, "false_breakout": 0, "missed": 0, "overlap": 0}
    trades, kept, busy = [], [], -1
    for s in sets:
        i0 = s["order_bar"]
        if X.t[i0] + 900 < t_from or i0 + 1 >= n:
            continue
        stat["setups"] += 1
        p_ref = s["limit"] if s.get("limit") is not None else s["market"]
        if any(k["dir"] == s["dir"] and X.t[i0] - X.t[k["order_bar"]] <= REPEAT_SEC and abs(p_ref - k["p"]) <= REPEAT_USD * p_ref / 4000
               for k in kept[-50:]):
            stat["repeat"] += 1
            continue
        kept.append({"dir": s["dir"], "order_bar": i0, "p": p_ref})
        cost = X.cost[i0] if cost_kind == "model" else OP_COST
        why = check(X, s, p_ref, i0, cost)
        if why:
            stat["rejected"][why] = stat["rejected"].get(why, 0) + 1
            continue
        d = s["dir"]
        if s.get("limit") is None:                                 # market at the order bar's close
            fill_bar, e = i0, s["market"]
            first = i0 + 1
        else:
            fill_bar, e = None, None
            for b in range(i0 + 1, min(i0 + 1 + LIMIT_BARS, n)):
                o = X.o[b]
                if s["inval"] is not None and (o - s["inval"]) * d < 0:
                    stat["invalidated"] += 1
                    break
                if s.get("false_break_level") is not None and (o - s["limit"]) * d < 0:
                    stat["false_breakout"] += 1
                    break
                touch = (X.l[b] <= s["limit"]) if d == 1 else (X.h[b] >= s["limit"])
                if touch:
                    fill_bar, e = b, (min(o, s["limit"]) if d == 1 else max(o, s["limit"]))
                    break
                if s["inval"] is not None and ((X.l[b] < s["inval"]) if d == 1 else (X.h[b] > s["inval"])):
                    stat["invalidated"] += 1
                    break
                if s["inval"] is not None and (X.dn_any[b] if d == 1 else X.up_any[b]):   # sweep setups only
                    stat["invalidated"] += 1
                    break
            else:
                stat["missed"] += 1
                continue
            if fill_bar is None:
                continue
            first = fill_bar + 1
        if fill_bar <= busy:
            stat["overlap"] += 1
            continue
        sc = e / 4000.0
        stop = s["stop"]
        D = (e - stop) * d / sc
        res = {}
        fill_stop = s.get("limit") is not None and ((X.l[fill_bar] <= stop) if d == 1 else (X.h[fill_bar] >= stop))
        for x in TP:
            res[x] = ("SL", fill_bar, stop) if fill_stop else race(X, first, d, e, stop, e + d * x * sc)
        out1, b_exit, px = res[TP[0]]
        net = (px - e) * d / sc - cost
        busy = b_exit
        if fill_stop or b_exit < first:
            mfe, mae = 0.0, float(D)
        else:
            seg = slice(first, b_exit + 1)
            mfe = max(float(((X.h[seg] - e) if d == 1 else (e - X.l[seg])).max() / sc), 0.0)
            mae = max(float(((e - X.l[seg]) if d == 1 else (X.h[seg] - e)).max() / sc), 0.0)
        th = (-D if fill_stop else thirds(X, first, d, e, stop, sc)) - cost
        trades.append({"t": int(X.t[fill_bar]) + (900 if s.get("limit") is None else 0), "bar": int(fill_bar), "dir": d, "entry": float(e),
                       "stop": float(stop), "D": float(D), "cost": float(cost), "out": out1,
                       "tp2": res[TP[1]][0], "tp3": res[TP[2]][0], "net": float(net), "r": float(net / (D + cost)),
                       "r_thirds": float(th / (D + cost)), "mfe": mfe, "mae": mae,
                       "min_to_tp1": float((b_exit - fill_bar) * 15) if out1 == "TP" else None, "exit_bar": int(b_exit),
                       "sess": str(X.sess[fill_bar]), "ranging": bool(X.ranging[fill_bar]), "entry_type": s["entry_type"],
                       "kind": s["ev"]["kind"], "score": score(X, s, e, fill_bar, D, cost)})
    stat["executed"] = len(trades)
    return {"stat": stat, "trades": trades}


# ---------------- the operator's 100-point score (declared components; not a probability) ----------------
def score(X: Ctx, s: dict, e: float, i: int, D: float, cost: float) -> float:
    d, ev = s["dir"], s["ev"]
    kind = ev.get("kind", "")
    if kind == "VWAP":
        liq = 0.5
    elif kind in ("ENG", "RND"):
        liq = 0.0
    elif s["entry_type"] == "RETEST":
        liq = RANK.get(kind[:2], 0.6)
    else:
        liq = RANK.get(kind[:2], 0.6) * {1: 1.0, 2: 0.75, 3: 0.5}.get(ev.get("bars", 3), 0.5)
    ups = [bool(X.e15_up[i]), bool(X.e1_up[i]), bool(X.e4_up[i])]
    struct = sum(u if d == 1 else (not u) for u in ups) / 3.0
    entry = {"FVG": 1.0, "OB": 0.7, "RETEST": 0.8, "MARKET": 0.4}.get(s["entry_type"], 0.4)
    volvol = (0.5 + (1.0 if X.atr_ok[i] else 0.5)) / 2.0
    sess = ((1.0 if X.sess[i] in ("LONDON", "NEW YORK", "LONDON+NY") else 0.4) + 0.5) / 2.0
    room = opposing_room(X, i, d, e) / (e / 4000.0)
    space = 0.5 * min(room / 20.0, 1.0) + 0.5 * min(((TP[0] - cost) / (D + cost)) / 1.5, 1.0)
    comp = {"liq": liq, "struct": struct, "entry": entry, "volvol": volvol, "sess": sess, "cross": 0.5, "space": space}
    return float(sum(WEIGHTS[k] * v for k, v in comp.items()))


# ---------------- arms: the engines and the matched random control ----------------
def eng_setups(X: Ctx, trigs: list[dict]) -> list[dict]:
    out = []
    t15 = X.t
    for tr in trigs:
        if tr.get("sl_eng") is None:
            continue
        i = int(np.searchsorted(t15, tr["t_close"], side="left")) - 1     # the 15m bar whose close is the signal close
        if i < 1 or i + 1 >= len(t15):
            continue
        out.append({"order_bar": i, "limit": None, "market": float(tr["p0"]), "stop": float(tr["sl_eng"]), "inval": None,
                    "entry_type": "MARKET", "dir": int(tr["dir"]), "ev": {"kind": "ENG", "bars": 3}})
    return sorted(out, key=lambda s: s["order_bar"])


def matched_random(X: Ctx, trades: list[dict], lo_bar: int, cost_kind: str = "model", k: int = RND_K, seed: int = SEED) -> dict:
    """For each trade: k random 15m closes with the same session label and direction, the same scaled stop distance and
    targets, outcomes by the same race."""
    rng = H.seeded_rng(seed)
    n = len(X.c)
    by_sess = {}
    for s_ in set(X.sess[lo_bar:n - HOLD - 1].tolist()):
        by_sess[s_] = np.flatnonzero(X.sess[lo_bar:n - HOLD - 1] == s_) + lo_bar
    hits, rs = [], []
    for tr in trades:
        pool = by_sess.get(tr["sess"])
        if pool is None or not len(pool):
            continue
        for b in rng.choice(pool, size=k, replace=True):
            e, d = X.c[b], tr["dir"]
            sc = e / 4000.0
            stop = e - d * tr["D"] * sc
            cost = X.cost[b] if cost_kind == "model" else OP_COST
            out, _, px = race(X, b + 1, d, e, stop, e + d * TP[0] * sc)
            hits.append(out == "TP")
            rs.append(((px - e) * d / sc - cost) / (tr["D"] + cost))
    return {"n": len(hits), "tp1_rate": float(np.mean(hits)) if hits else math.nan, "mean_r": float(np.mean(rs)) if rs else math.nan}


# ---------------- statistics ----------------
def boot_ci(r: np.ndarray, day: np.ndarray, seed: int = SEED) -> list[float]:
    if len(r) < 3:
        return [math.nan, math.nan]
    days = np.unique(day)
    g = {dd: r[day == dd] for dd in days}
    rng = H.seeded_rng(seed)
    m = [np.concatenate([g[p] for p in rng.choice(days, size=len(days), replace=True)]).mean() for _ in range(BOOT)]
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def summarize(tr: list[dict], stat: dict, rnd: dict | None = None) -> dict:
    o = {"stat": stat, "n": len(tr)}
    if not tr:
        return o
    out = np.array([x["out"] for x in tr], object)
    r = np.array([x["r"] for x in tr])
    net = np.array([x["net"] for x in tr])
    for name, msk in (("tp1_first", out == "TP"), ("sl_first", out == "SL"), ("ambiguous", out == "AMBIGUOUS"),
                      ("timeout", out == "TIMEOUT"), ("tp2_first", np.array([x["tp2"] == "TP" for x in tr])),
                      ("tp3_first", np.array([x["tp3"] == "TP" for x in tr]))):
        k = int(msk.sum())
        o[name] = {"k": k, "rate": k / len(tr), "wilson95": list(H.wilson(k, len(tr)))}
    day = np.array([x["t"] // 86400 for x in tr])
    sd = float(np.std(r, ddof=1)) if len(r) > 2 else math.nan
    o.update(mean_r=float(r.mean()), mean_r_t95=[float(r.mean() - 1.96 * sd / math.sqrt(len(r))), float(r.mean() + 1.96 * sd / math.sqrt(len(r)))]
             if len(r) > 2 else [math.nan, math.nan], mean_r_boot95=boot_ci(r, day), usd_per_trade=float(r.mean() * 650.0),
             mean_r_thirds=float(np.mean([x["r_thirds"] for x in tr])),
             profit_factor=float(net[net > 0].sum() / -net[net < 0].sum()) if (net < 0).any() else math.nan,
             max_drawdown_usd=b19.max_drawdown(r[np.argsort([x["t"] for x in tr], kind="stable")] * 650.0),
             mfe_mean=float(np.mean([x["mfe"] for x in tr])), mae_mean=float(np.mean([x["mae"] for x in tr])),
             min_to_tp1_median=float(np.median([x["min_to_tp1"] for x in tr if x["min_to_tp1"] is not None])) if (out == "TP").any() else math.nan,
             stop_D_median=float(np.median([x["D"] for x in tr])), cost_mean=float(np.mean([x["cost"] for x in tr])),
             break_even_tp1=float(np.mean([(x["D"] + x["cost"]) / (TP[0] + x["D"]) for x in tr])))
    if rnd is not None:
        o["rnd"] = rnd
        p1, p0, n1, n0 = o["tp1_first"]["rate"], rnd["tp1_rate"], len(tr), rnd["n"]
        if n0 and 0 < (p1 * n1 + p0 * n0) / (n1 + n0) < 1:
            pp = (p1 * n1 + p0 * n0) / (n1 + n0)
            z = (p1 - p0) / math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
            o["z_vs_rnd"], o["p_vs_rnd"] = float(z), float(1 - H._norm_cdf(z))
    return o


def auc(score_: np.ndarray, y: np.ndarray) -> float:
    pos, neg = score_[y == 1], score_[y == 0]
    if not len(pos) or not len(neg):
        return math.nan
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def isotonic_fit(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pool-adjacent-violators: non-decreasing step function of y on x (returns the knots and the fitted values)."""
    o = np.argsort(x, kind="stable")
    xs, ys = x[o].astype(float), y[o].astype(float)
    blocks = [[v, 1.0, xx] for v, xx in zip(ys, xs)]
    out = []
    for b in blocks:
        out.append(b)
        while len(out) > 1 and out[-2][0] > out[-1][0]:
            v2, w2, x2 = out.pop()
            v1, w1, x1 = out.pop()
            out.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, x2])
    knots = np.array([b[2] for b in out])
    vals = np.array([b[0] for b in out])
    return knots, vals


def isotonic_predict(knots: np.ndarray, vals: np.ndarray, x: np.ndarray) -> np.ndarray:
    k = np.searchsorted(knots, x, side="left")
    return vals[np.minimum(k, len(vals) - 1)]


# ---------------- data and runs ----------------
def load_part(rd: str, part: str):
    if part == "recent":
        m15, h1 = history.load(rd, "XAU/USD", "15min"), history.load(rd, "XAU/USD", "1h")
        lo = H.HOLD[1]
        m15, h1 = m15[m15.index >= lo], h1[h1.index >= lo]
        return m15, h1, lo + pd.Timedelta(days=59)
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), part, REG if part in SEALED else None)
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), part, REG if part in SEALED else None)
    start = b13.SCORE_FROM if part == "development" else m15.index[0] + pd.Timedelta(days=67)
    return m15, h1, start


def run(rd: str, part: str, f_eng: dict | None = None, trials: str | None = None, log=print) -> dict:
    m15, h1, score_from = load_part(rd, part)
    runs = b19.engine_runs(m15, h1, log)
    res15, F15 = runs["15m"]
    X = make_ctx(m15, h1, res15, F15)
    t_from = int(score_from.timestamp())
    lo_bar = int(np.searchsorted(X.t, t_from))
    evs = crossings(X, SELL_SIDE + BUY_SIDE)
    eng = b19.dedupe([x for tf, (res, F) in runs.items() for x in b19.triggers_from_run(res, F, tf, "ENG") if x["t_close"] >= t_from])
    arms = {m: setups(X, m, evs) for m in MODULES}
    arms["PROD-ENG"] = eng_setups(X, eng)
    if f_eng is not None and part in f_eng:
        arms["F-ENG"] = eng_setups(X, [x for x in f_eng[part] if x["t_close"] >= t_from])
    out = {"meta": {"part": part, "bars_15m": len(m15), "first": str(m15.index[0]), "last": str(m15.index[-1]),
                    "scored_from": str(score_from), "data_hash_15m": H.data_hash(m15), "data_hash_1h": H.data_hash(h1),
                    "crossings": len(evs), "rejected_sweeps": sum(e["status"] == "REJECTED" for e in evs),
                    "accepted_breaks": sum(e["status"] == "ACCEPTED" for e in evs)},
           "results": {}, "trades": {}}
    for cost_kind in ("model", "operator"):
        allt = []
        for name, sets in arms.items():
            R = run_module(X, sets, t_from, cost_kind)
            rnd = matched_random(X, R["trades"], lo_bar, cost_kind) if cost_kind == "model" else None
            out["results"][f"{name}|{cost_kind}"] = summarize(R["trades"], R["stat"], rnd)
            if cost_kind == "model":
                out["trades"][name] = R["trades"]
            if name in MODULES:
                allt += [dict(x, mod=name) for x in R["trades"]]
            if trials:
                H.log_trial(trials, {"reg": REG, "part": part, "key": f"{name}|{cost_kind}", "n": len(R["trades"]),
                                     "mean_r": out["results"][f"{name}|{cost_kind}"].get("mean_r", math.nan)})
        for label, keep in (("COMBINED", lambda x: True), ("COMBINED-Q75", lambda x: x["score"] >= 75)):
            comb, busy, seen = [], -1, set()
            for x in sorted((y for y in allt if keep(y)), key=lambda y: (y["bar"], y["mod"])):
                if (x["bar"], x["dir"]) in seen or x["bar"] <= busy:
                    continue
                seen.add((x["bar"], x["dir"]))
                comb.append(x)
                busy = x["exit_bar"]
            rnd = matched_random(X, comb, lo_bar, cost_kind) if cost_kind == "model" else None
            out["results"][f"{label}|{cost_kind}"] = summarize(comb, {"setups": len(comb)}, rnd)
            if cost_kind == "model":
                out["trades"][label] = comb
    log(f"[B31] {part}: " + ", ".join(f"{k.split('|')[0]} {v['n']}" for k, v in out["results"].items() if k.endswith("|model")))
    return out


def decide(parts: dict) -> dict:
    rows, ps = {}, {}
    for u in MODULES + ("COMBINED", "COMBINED-Q75"):
        tr = [x for p in SEALED for x in parts[p]["trades"].get(u, [])]
        n = len(tr)
        rnd = [parts[p]["results"][f"{u}|model"].get("rnd") or {} for p in SEALED]
        n0 = sum(x.get("n", 0) for x in rnd)
        p0 = sum(x.get("tp1_rate", 0) * x.get("n", 0) for x in rnd if x.get("n")) / n0 if n0 else math.nan
        dev = parts["development"]["results"].get(f"{u}|model", {})
        row = {"n_oos": n, "dev_mean_r": dev.get("mean_r", math.nan), "rnd_tp1_rate_oos": p0}
        if n:
            r = np.array([x["r"] for x in tr])
            hit = np.array([x["out"] == "TP" for x in tr])
            row.update(mean_r_oos=float(r.mean()), boot95_oos=boot_ci(r, np.array([x["t"] // 86400 for x in tr])),
                       tp1_rate_oos=float(hit.mean()), wilson95_oos=list(H.wilson(int(hit.sum()), n)))
            pp = (hit.sum() + p0 * n0) / (n + n0) if n0 else math.nan
            if n0 and 0 < pp < 1:
                z = (hit.mean() - p0) / math.sqrt(pp * (1 - pp) * (1 / n + 1 / n0))
                ps[u] = float(1 - H._norm_cdf(z))
        rows[u] = row
    adj = b19.holm_adjusted({k: v for k, v in ps.items()}) if ps else {}
    for u, row in rows.items():
        row["holm_p"] = adj.get(u, math.nan)
        if row["n_oos"] < 30:
            row["verdict"] = "INSUFFICIENT"
        else:
            ok = (row.get("boot95_oos", [math.nan])[0] > 0 and row["holm_p"] < 0.05 and row["dev_mean_r"] > 0)
            row["verdict"] = "SUPPORTED" if ok else "NOT SUPPORTED"
    return rows


def calibration(parts: dict) -> dict:
    """The score on development -> isotonic P(TPk before SL); applied out of sample (all modules pooled)."""
    dev = [x for m in MODULES for x in parts["development"]["trades"].get(m, [])]
    oos = [x for p in SEALED for m in MODULES for x in parts[p]["trades"].get(m, [])]
    out = {"n_dev": len(dev), "n_oos": len(oos)}
    if len(dev) < 30 or len(oos) < 30:
        return out
    sd, so = np.array([x["score"] for x in dev]), np.array([x["score"] for x in oos])
    for key, lab in (("tp1", lambda x: x["out"] == "TP"), ("tp2", lambda x: x["tp2"] == "TP"), ("tp3", lambda x: x["tp3"] == "TP")):
        yd, yo = np.array([lab(x) for x in dev], float), np.array([lab(x) for x in oos], float)
        kn, va = isotonic_fit(sd, yd)
        pr = isotonic_predict(kn, va, so)
        base = yd.mean()
        q = pd.qcut(pr + 1e-9 * np.arange(len(pr)), 5, labels=False, duplicates="drop")
        rel = [{"pred": float(pr[q == b].mean()), "obs": float(yo[q == b].mean()), "n": int((q == b).sum())} for b in sorted(set(q))]
        rng = H.seeded_rng(SEED)
        bs = [auc(so[ii], yo[ii]) for ii in (rng.integers(0, len(so), len(so)) for _ in range(1000))]
        out[key] = {"auc_dev": auc(sd, yd), "auc_oos": auc(so, yo), "auc_oos_95": [float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))],
                    "brier_oos": float(np.mean((pr - yo) ** 2)), "brier_base_oos": float(np.mean((base - yo) ** 2)),
                    "reliability_oos": rel, "base_dev": float(base), "base_oos": float(yo.mean())}
    cls = lambda s: "high" if s >= 85 else "qualified" if s >= 75 else "watchlist" if s >= 65 else "reject"
    out["by_class_oos"] = {c: {"n": int(sum(cls(x["score"]) == c for x in oos)),
                               "tp1_rate": float(np.mean([x["out"] == "TP" for x in oos if cls(x["score"]) == c]))
                               if any(cls(x["score"]) == c for x in oos) else math.nan} for c in ("high", "qualified", "watchlist", "reject")}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--parts", default="development,validation,holdout,recent")
    ap.add_argument("--f-eng", help="JSON of the F1-F4 engine's ENG triggers per partition (from that tree)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    f_eng = json.load(open(a.f_eng)) if a.f_eng else None
    parts = {p: run(a.rd, p, f_eng, a.trials) for p in a.parts.split(",")}
    rep = {"registration": REG, "parts": {p: {"meta": v["meta"], "results": v["results"]} for p, v in parts.items()}}
    if all(p in parts for p in ("development",) + SEALED):
        rep["decision"] = decide(parts)
        rep["calibration"] = calibration(parts)
    with open(a.out, "w") as f:
        json.dump(rep, f, indent=1, default=lambda v: None if (isinstance(v, float) and v != v) else (float(v) if isinstance(v, (np.floating, float)) else str(v)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
