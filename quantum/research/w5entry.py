"""B31b-W5 (research only; production never imports this module): the executable entry-price study.

After a directional impulse known at the decision time, which entry price (and so which stop distance to the SAME
structural invalidation) reaches +$10 before the stop more often than a fair random entry, after costs?
research/registrations/B31b-W5.json fixes every rule before this code ran; this file implements it.

Every order goes through w3liq.execute (fills, $650 sizing, eligibility, the +$10 / +$15 / +$20 races, M5 ordering of a
bar that touches both, gap losses). Controls: R1 random timing in the same window with the same stop distance (primary),
R2 the immediate entry, R3 a random price in the same eligible zone with the same structural stop, R4 W3's matched random.
Random draws are seeded per opportunity / trade, so a result never depends on the order in which things were processed.
Development only: validation and holdout are not CLI choices.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd

from .. import ta
from . import harness as H
from . import w3liq as W
from .w4pull import holm, store_frames

REG = "B31b-W5"
IMP_ATR, LOOK, WIN = 2.0, 16, 16
BUF = W.SL_BUF
FIB = (0.236, 0.382, 0.5, 0.618, 0.786)
NONFIB = (0.30, 0.45, 0.55, 0.70)
LEVELS = FIB + NONFIB
RAND_LO, RAND_HI, ZONE_MAX = 0.2, 0.8, 0.8
I_ATR, K_ATR, K_COST, J_WIN = 1.0, 1.0, 8.0, 4
K_RAND = 20
SEED = W.SEED
E_LOOKBACK = 4 * 96                                   # swings considered for E: confirmed within the last 4 days
BNAME = {r: f"B{r:g}" for r in LEVELS}
CANDIDATES = ("A0", "A1") + tuple(BNAME[r] for r in LEVELS) + ("C", "E", "F", "G20", "G50", "H", "I", "J", "K")
CONTROLS = ("B_rand",)
NAMES = {"A0": "market at the impulse close (earliest plausible)", "A1": "market at the first pullback close",
         **{BNAME[r]: f"limit at a {r:g} retracement" + (" (Fibonacci)" if r in FIB else "") for r in LEVELS},
         "B_rand": "CONTROL: limit at a random 0.2-0.8 retracement", "C": "limit at the displacement candle's open",
         "E": "limit at the broken structure level", "F": "limit at the anchored TWAP (volume-free VWAP proxy)",
         "G20": "limit following EMA20", "G50": "limit following EMA50", "H": "M5 pullback, then resume",
         "I": "limit 1 ATR below the impulse extreme", "J": "failed reclaim of the broken level",
         "K": "adaptive: the deepest price keeping the stop >= 1 ATR and >= 8 x cost"}


def rng_for(*key):
    """A generator seeded by the registration seed and the opportunity / trade identity: draws never depend on order.
    Through harness.seeded_rng, the one place research code may draw random numbers (tests/test_integrity.py)."""
    return H.seeded_rng([SEED] + [int(k) & 0x7FFFFFFF for k in key])


def tc(F: W.Frame, j: int) -> int:
    return int(F.t[j]) + F.sec


# ---------------- opportunities: impulses known at the decision time ----------------
def opportunities(F: W.Frame, score_from: int) -> list[dict]:
    n = len(F.c)
    busy, used = {1: -1, -1: -1}, {1: set(), -1: set()}
    out = []
    for t0 in range(LOOK + 1, n):
        if F.t[t0] + F.sec < score_from:
            continue
        a0, a1 = F.atr[t0], F.atr[t0 - 1]
        if not (np.isfinite(a0) and np.isfinite(a1) and a0 > 0):
            continue
        for d in (1, -1):
            if t0 <= busy[d]:
                continue
            seg = F.l[t0 - LOOK:t0] if d == 1 else F.h[t0 - LOOK:t0]
            k = int(np.argmin(seg)) if d == 1 else int(np.argmax(seg))
            p0, X0 = t0 - LOOK + k, float(seg[k])
            if p0 in used[d]:
                continue
            if not (d * (F.c[t0] - X0) >= IMP_ATR * a0 and d * (F.c[t0 - 1] - X0) < IMP_ATR * a1):
                continue
            S = X0 - d * BUF * a0
            run = float(F.h[p0:t0 + 1].max()) if d == 1 else float(F.l[p0:t0 + 1].min())
            t1 = None
            for j in range(t0 + 1, min(t0 + LOOK, n - 1) + 1):
                if d * (F.c[j] - S) < 0:
                    break
                ext = F.h[j] if d == 1 else F.l[j]
                if d * (ext - run) <= 0:
                    t1 = j
                    break
                run = float(ext)
            end = min((t1 if t1 is not None else t0) + WIN, n - 1)
            op = {"id": f"{d:+d}@{tc(F, t0)}", "d": d, "t0": t0, "p0": p0, "X0": X0, "S": float(S), "atr0": float(a0),
                  "p_0": float(F.c[t0]), "t1": t1, "end": end}
            if t1 is not None:
                op["Hx"] = run
                op["R"] = d * (run - X0)
            out.append(op)
            used[d].add(p0)
            busy[d] = end
    return out


def broken_level(F: W.Frame, op: dict) -> float | None:
    """E's level: the most recent swing (pivot 3 / 3) against which the impulse broke out, known before it was crossed:
    confirmed at q <= t0, inside (X0, Hx), price on the far side at p0, and a close beyond it in p0 .. t1 at or after q."""
    d, p0, t0, t1, X0, Hx = op["d"], op["p0"], op["t0"], op["t1"], op["X0"], op["Hx"]
    piv = F.ph if d == 1 else F.pl
    for q in range(t0, max(t0 - E_LOOKBACK, W.SW_LR) - 1, -1):
        v = piv[q]
        if not np.isfinite(v) or not (d * (v - X0) > 0 and d * (Hx - v) > 0) or d * (F.c[p0] - v) >= 0:
            continue
        a = max(p0, q)
        if a <= t1 and np.any(d * (F.c[a:t1 + 1] - v) > 0):
            return float(v)
    return None


# ---------------- orders of one opportunity ----------------
def mkt(m, op, F, j, **kw):
    return {"m": m, "d": op["d"], "kind": "MKT", "t": tc(F, j), "px": float(F.c[j]), "stop": op["S"], "j": j, "op": op["id"], **kw}


def lim(m, op, F, px, **kw):
    return {"m": m, "d": op["d"], "kind": "LIM", "t": tc(F, op["t1"]), "px": float(px), "stop": op["S"], "j": op["t1"],
            "valid": op["end"], "cancel_back": True, "L": op["S"], "op": op["id"], **kw}


def missed(m, op, why):
    return {"m": m, "op": op["id"], "d": op["d"], "status": "MISSED", "why": why, "virtual": True}


def orders_for(P: W.Path, F: W.Frame, op: dict, ema: dict) -> list[dict]:
    d, S = op["d"], op["S"]
    out = [mkt("A0", op, F, op["t0"])]
    t1 = op["t1"]
    if t1 is None:
        return out
    Hx, R = op["Hx"], op["R"]
    out.append(mkt("A1", op, F, t1))
    for r in LEVELS:
        out.append(lim(BNAME[r], op, F, Hx - d * r * R))
    u = float(rng_for(op["t0"], d + 2, 1).uniform(RAND_LO, RAND_HI))
    out.append(lim("B_rand", op, F, Hx - d * u * R, u=u))
    body = d * (F.c[op["p0"]:t1 + 1] - F.o[op["p0"]:t1 + 1])
    if np.any(body > 0):
        kb = op["p0"] + int(np.argmax(body))
        if d * (F.o[kb] - S) > 0:
            out.append(lim("C", op, F, F.o[kb]))
    lv = broken_level(F, op)
    if lv is not None:
        out.append(lim("E", op, F, lv, level=lv))
    tw = float(np.mean((F.h[op["p0"]:t1 + 1] + F.l[op["p0"]:t1 + 1] + F.c[op["p0"]:t1 + 1]) / 3.0))
    out.append(lim("F", op, F, tw))
    for nm in ("G20", "G50"):
        out.append(dynamic_limit(nm, op, F, ema[nm]))
    out.append(m5_resume(P, F, op))
    out.append(lim("I", op, F, Hx - d * I_ATR * F.atr[t1]))
    if lv is not None:
        out.append(failed_reclaim(op, F, lv))
    else:
        out.append(missed("J", op, "no broken structure level"))
    s1 = F.c[t1] / 4000.0
    pk = S + d * max(K_ATR * F.atr[t1], K_COST * P.cost[t1] * s1)
    out.append(mkt("K", op, F, t1) if d * (F.c[t1] - pk) <= 0 else lim("K", op, F, pk))
    return out


def dynamic_limit(m: str, op: dict, F: W.Frame, e: np.ndarray) -> dict:
    """A limit re-priced at the close of each bar to that bar's EMA; the order returned is the one that fills (a one-bar
    limit at the EMA of the bar before the fill bar), or a MISSED record."""
    d, S, t1, end = op["d"], op["S"], op["t1"], op["end"]
    for j in range(t1 + 1, end + 1):
        if d * (F.c[j - 1] - S) < 0 and j - 1 > t1:
            return missed(m, op, "cancelled: a close beyond the structural stop")
        g = e[j - 1]
        if not np.isfinite(g):
            continue
        hit = (F.l[j] <= g) if d == 1 else (F.h[j] >= g)
        if hit:
            return {"m": m, "d": d, "kind": "LIM", "t": tc(F, j - 1), "px": float(g), "stop": S, "j": j - 1, "valid": j,
                    "op": op["id"]}
    return missed(m, op, "limit not filled in time")


def m5_resume(P: W.Path, F: W.Frame, op: dict) -> dict:
    """H: after t1, the first M5 bar k whose previous bar k-1 made a lower high than k-2 (a pullback) and whose close is
    above that previous high (UP; the mirror DOWN); both k-1 and k-2 open after t1's close."""
    d, S, t1 = op["d"], op["S"], op["t1"]
    if P.t5 is None:
        return missed("H", op, "NOT RUN: no 5min bars")
    t_hi = tc(F, t1 + WIN) if t1 + WIN < len(F.c) else 2 ** 62     # the window by bar count; the data's end otherwise
    a, b = W.m5_span(P, tc(F, t1), t_hi)
    if b - a < 3:
        return missed("H", op, "NOT RUN: no 5min bars in the window")
    for k in range(a + 2, b):
        t_close = int(P.t5[k]) + 300
        k15 = int(np.searchsorted(F.t + F.sec, t_close, side="right")) - 1
        if k15 > t1 and np.any(d * (F.c[t1 + 1:k15 + 1] - S) < 0):
            return missed("H", op, "cancelled: a close beyond the structural stop")
        if d == 1:
            ok = P.h5[k - 1] < P.h5[k - 2] and P.c5[k] > P.h5[k - 1]
        else:
            ok = P.l5[k - 1] > P.l5[k - 2] and P.c5[k] < P.l5[k - 1]
        if ok:
            return {"m": "H", "d": d, "kind": "MKT", "t": t_close, "px": float(P.c5[k]), "stop": S, "j": None, "op": op["id"]}
    return missed("H", op, "no M5 resume in the window")


def failed_reclaim(op: dict, F: W.Frame, lv: float) -> dict:
    """J: the first bar m with a close back across E's level in direction d while one of the J_WIN closes before it (from
    t1 + 1 on, inside the window) was on the other side; cancelled by a close beyond the structural stop first."""
    d, S, t1, end = op["d"], op["S"], op["t1"], op["end"]
    for m in range(t1 + 1, min(end + J_WIN, len(F.c) - 1) + 1):
        if d * (F.c[m] - S) < 0:
            return missed("J", op, "cancelled: a close beyond the structural stop")
        prev = [r for r in range(max(t1 + 1, m - J_WIN), m) if r <= end]
        if d * (F.c[m] - lv) > 0 and any(d * (F.c[r] - lv) < 0 for r in prev):
            return mkt("J", op, F, m, level=lv)
        if m > end and not any(d * (F.c[r] - lv) < 0 for r in prev):
            break
    return missed("J", op, "no retrace through the level and close back in the window")


# ---------------- controls ----------------
def r1_control(P: W.Path, rows: list[dict], ops: dict, k: int = K_RAND) -> tuple[dict, dict]:
    """R1: per counted trade, k random M15 closes in the same opportunity window, same direction and stop distance D,
    same targets, race and cost model. Returns the pooled {tp: {k, n, mean_r}} and each trade's own control mean R."""
    res = {f"tp{int(T)}": {"k": 0, "n": 0, "r": []} for T in W.TP}
    own = {}
    for r in rows:
        if not W.decided(r):
            continue
        op = ops[r["op"]]
        lo = op["t0"] if (r["m"] == "A0" or op["t1"] is None) else op["t1"]
        hi = min(lo + WIN, len(P.c) - 2)
        g = rng_for(r["t_dec"], r["d"] + 2, sum(map(ord, r["m"])))
        mine = []
        for b in g.integers(lo, hi + 1, size=k):
            e = float(P.c[b])
            s = e / 4000.0
            stop = e - r["d"] * r["D"] * s
            cost = float(P.cost[b])
            for T in W.TP:
                out, _, px, _ = W.race_fast(P, int(b) + 1, r["d"], e, stop, e + r["d"] * T * s)
                if out not in ("TP", "SL", "AMBIGUOUS", "TIMEOUT"):
                    continue
                key = f"tp{int(T)}"
                rr = (r["d"] * (px - e) / s - cost) / (r["D"] + cost)
                res[key]["n"] += 1
                res[key]["k"] += int(out == "TP")
                res[key]["r"].append(rr)
                if key == "tp10":
                    mine.append(rr)
        own[id(r)] = float(np.mean(mine)) if mine else math.nan
    return {kk: {"k": v["k"], "n": v["n"], "mean_r": float(np.mean(v["r"])) if v["r"] else math.nan} for kk, v in res.items()}, own


def r3_control(P: W.Path, F: W.Frame, ops: list[dict], k: int = K_RAND) -> dict:
    """R3: per opportunity, k limits at prices drawn uniformly between the impulse extreme and its 0.8 retracement, the
    same structural stop, window and cancellation. Returns {op id: {n, tp10_first, mean_r}} over eligible decided fills."""
    out = {}
    for op in ops:
        if op["t1"] is None:
            continue
        g = rng_for(op["t0"], op["d"] + 2, 3)
        rs, hits = [], 0
        for u in g.uniform(0.0, ZONE_MAX, size=k):
            r = W.execute(P, F, lim("R3", op, F, op["Hx"] - op["d"] * u * op["R"]))
            if r["status"] == "FILLED" and r.get("eligible") and W.decided(r):
                rs.append(r["tp10_r"])
                hits += int(r["tp10"] == "TP")
        out[op["id"]] = {"n": len(rs), "tp10_first": hits, "mean_r": float(np.mean(rs)) if rs else math.nan}
    return out


# ---------------- per-opportunity description (uses the future: descriptive only) ----------------
def describe(P: W.Path, F: W.Frame, op: dict) -> dict:
    d, t0, p0, X0, S, a0 = op["d"], op["t0"], op["p0"], op["X0"], op["S"], op["atr0"]
    s0 = op["p_0"] / 4000.0
    mfe0, _ = W.excursions(P, t0 + 1, 96, d, op["p_0"], s0)
    x = {"id": op["id"], "d": d, "t1": op["t1"] is not None, "bars_to_t0": t0 - p0, "mfe_from_p0": mfe0}
    if op["t1"] is None:
        return x
    t1, Hx, R, end = op["t1"], op["Hx"], op["R"], op["end"]
    body = np.abs(F.c[p0:t1 + 1] - F.o[p0:t1 + 1])
    x.update(R_usd=R / s0, R_atr=R / a0, bars_to_t1=t1 - p0, disp_ratio=float(body.max() / R) if R > 0 else math.nan)
    deepest, k_ext = Hx, None
    for j in range(t1, end + 1):
        if d * ((F.h[j] if d == 1 else F.l[j]) - Hx) > 0 and j > t1:
            k_ext = j
            break
        deepest = min(deepest, F.l[j]) if d == 1 else max(deepest, F.h[j])
    x["max_retrace_share"] = d * (Hx - deepest) / R if R > 0 else math.nan
    x["retrace_bars"] = (k_ext if k_ext is not None else end) - t1
    x["new_extreme_in_window"] = k_ext is not None
    jj = k_ext if k_ext is not None else end
    x["atr_change"] = float(F.atr[jj] / F.atr[t1]) if F.atr[t1] > 0 else math.nan
    piv = F.pl2 if d == 1 else F.ph2
    x["higher_low"] = bool(any(np.isfinite(piv[q]) and d * (piv[q] - X0) > 0 for q in range(t1 + 1, end + 1)))
    x["structure_held"] = not bool(np.any(d * (F.c[t1 + 1:end + 1] - S) < 0))
    lv = [F.pools[kk][t1] for kk in (("PDH", "PWH", "ASH", "LOH", "NYH", "PSH") if d == 1 else ("PDL", "PWL", "ASL", "LOL", "NYL", "PSL"))
          if kk in F.pools]
    dist = [d * (v - Hx) for v in lv if np.isfinite(v) and d * (v - Hx) > 0]
    x["opposing_level_atr"] = float(min(dist) / F.atr[t1]) if dist else math.nan
    return x


# ---------------- features for the predictive question (known at placement / fill) ----------------
SESS_D = ("ASIA", "LDN_OPEN", "LDN_CONT", "NY_OPEN", "OVERLAP", "NY_CONT")
GROUPS = {
    "returns": ("ret1", "ret4", "ret16", "accel"),
    "candle": ("body", "wick_with", "wick_against"),
    "volatility": ("atr5_20", "rv16"),
    "impulse": ("imp_atr", "imp_bars", "disp"),
    "retracement": ("depth_u", "fill_bars", "atr_fill_t0"),
    "levels": ("opp_lv_atr", "swing_atr"),
    "mtf": ("m30", "h1", "h4"),
    "regime": ("er20", "atr_pct"),
}
BASE = ("geo", "cost_D", "log_atr") + tuple(f"s_{s}" for s in SESS_D)


def features(P: W.Path, F: W.Frame, op: dict, r: dict, aux: dict) -> dict:
    d, t1, a = op["d"], op["t1"], F.atr[op["t1"]]
    s = F.c[t1] / 4000.0
    sess = str(P.sess[t1])
    f = {"geo": math.log(r["D"] / 10.0), "cost_D": r["cost"] / r["D"], "log_atr": math.log(a / s)}
    f.update({f"s_{x}": float(sess == x) for x in SESS_D})
    ret = lambda k: d * (F.c[t1] - F.c[t1 - k]) / a                                               # noqa: E731
    f.update(ret1=ret(1), ret4=ret(4), ret16=ret(16), accel=ret(1) - ret(4) / 4.0)
    rng = F.h[t1] - F.l[t1]
    if rng > 0:
        f["body"] = d * (F.c[t1] - F.o[t1]) / rng
        top, bot = F.h[t1] - max(F.o[t1], F.c[t1]), min(F.o[t1], F.c[t1]) - F.l[t1]
        f["wick_with"], f["wick_against"] = ((top, bot) if d == 1 else (bot, top))
        f["wick_with"], f["wick_against"] = f["wick_with"] / rng, f["wick_against"] / rng
    else:
        f["body"] = f["wick_with"] = f["wick_against"] = 0.0
    f["atr5_20"] = aux["atr5"][t1] / aux["atr20"][t1] if aux["atr20"][t1] > 0 else 1.0
    lr = np.diff(np.log(F.c[t1 - 16:t1 + 1]))
    f["rv16"] = float(np.std(lr) * F.c[t1] / a)
    f["imp_atr"], f["imp_bars"] = op["R"] / op["atr0"], float(t1 - op["p0"])
    body = np.abs(F.c[op["p0"]:t1 + 1] - F.o[op["p0"]:t1 + 1])
    f["disp"] = float(body.max() / op["R"]) if op["R"] > 0 else 0.0
    kf = W.k_at(P, r["t_fill"])
    f["depth_u"] = d * (op["Hx"] - r["e"]) / op["R"] if op["R"] > 0 else 0.0
    f["fill_bars"] = float(kf - t1)
    f["atr_fill_t0"] = float(P.atr[max(min(kf, len(P.atr)) - 1, 0)] / op["atr0"])     # the bar before the fill bar
    lv = [F.pools[kk][t1] for kk in (("PDH", "PWH", "ASH", "LOH", "NYH", "PSH") if d == 1 else ("PDL", "PWL", "ASL", "LOL", "NYL", "PSL"))
          if kk in F.pools]
    dist = [d * (v - r["e"]) for v in lv if np.isfinite(v) and d * (v - r["e"]) > 0]
    f["opp_lv_atr"] = min(min(dist) / a, 10.0) if dist else 10.0
    sw = aux["sw_hi"][t1] if d == 1 else aux["sw_lo"][t1]
    f["swing_atr"] = min(max(d * (sw - r["e"]) / a, -10.0), 10.0) if np.isfinite(sw) else 0.0
    up, dn = (F.m30_up, F.m30_dn), (F.h1_up, F.h1_dn)
    f["m30"] = float(d * (int(up[0][t1]) - int(up[1][t1])))
    f["h1"] = float(d * (int(dn[0][t1]) - int(dn[1][t1])))
    f["h4"] = float(d * (int(F.h4_up[t1]) - int(F.h4_dn[t1])))
    f["er20"] = float(F.er20[t1]) if np.isfinite(F.er20[t1]) else 0.0
    f["atr_pct"] = float(aux["atr_pct"][t1])
    return f


def aux_arrays(F: W.Frame) -> dict:
    sw_hi = pd.Series(F.ph).ffill().to_numpy(float)
    sw_lo = pd.Series(F.pl).ffill().to_numpy(float)
    atr = pd.Series(F.atr)
    return {"atr5": ta.atr(F.h, F.l, F.c, 5), "atr20": ta.atr(F.h, F.l, F.c, 20), "sw_hi": sw_hi, "sw_lo": sw_lo,
            "atr_pct": atr.rolling(500, min_periods=50).rank(pct=True).fillna(0.5).to_numpy(float)}


def predictive(rows: list[dict], t_lo: int, t_hi: int) -> dict:
    """Walk-forward out-of-fold log-loss / Brier / AUC of the baseline vs baseline + each group (and all together)."""
    if len(rows) < 200:
        return {"n": len(rows), "note": "too few rows"}
    y = W.label(rows)
    day = np.array([r["t_fill"] // 86400 for r in rows])
    sets = {"baseline": BASE, **{f"+{g}": BASE + cols for g, cols in GROUPS.items()},
            "+all": BASE + tuple(c for cols in GROUPS.values() for c in cols)}
    pr = {k: W.walk_forward(rows, cols, t_lo, t_hi) for k, cols in sets.items()}
    ok = np.isfinite(pr["baseline"])
    ll = lambda p: -(y * np.log(np.clip(p, 1e-9, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-9, 1)))   # noqa: E731
    base_ll = ll(pr["baseline"])
    out = {"n": len(rows), "n_oof": int(ok.sum()), "base_rate_oof": float(y[ok].mean()), "sets": {}}
    for k, p in pr.items():
        m = ok & np.isfinite(p)
        dll = base_ll[m] - ll(p)[m]                          # + = better than the baseline
        X = W.matrix(rows, sets[k])
        Xs, _, _, _ = W.standardize(X, X[:1])
        w = W.logit_fit(Xs, y)
        ins = float(np.mean(ll(W.logit_pred(w, Xs))))
        out["sets"][k] = {"n": int(m.sum()), "logloss_oof": float(np.mean(ll(p)[m])), "logloss_in_sample": ins,
                          "gain_vs_baseline_per_trade": float(np.mean(dll)), "gain_boot95": W.boot_mean(dll, day[m]),
                          "brier_oof": float(np.mean((p[m] - y[m]) ** 2)), "auc_oof": W.auc(p[m], y[m])}
    return out


# ---------------- a run ----------------
def code_sha() -> str:
    return hashlib.sha256(open(__file__, "rb").read()).hexdigest()


def build(m15: pd.DataFrame, h1: pd.DataFrame, m5: pd.DataFrame | None, score_from: int) -> dict:
    P, F, F30, incomplete = W.frames(m15, h1, m5)
    ema = {"G20": F.e20, "G50": np.asarray(ta.ema(F.c, 50), float)}
    ops = opportunities(F, score_from)
    rows = []
    for op in ops:
        for od in orders_for(P, F, op, ema):
            if od.get("virtual"):
                rows.append({**od, "tf": "M15", "t_dec": None})
                continue
            r = W.execute(P, F, od)
            r.update(tf="M15", op=od["op"], ev_id=f"{od['m']}-{od['t']}-{od['d']}", u=od.get("u"))
            rows.append(r)
    return {"P": P, "F": F, "F30": F30, "ops": ops, "rows": rows, "incomplete": incomplete,
            "lo_k": int(np.searchsorted(P.t, score_from)), "hi_k": len(P.c), "score_from": score_from}


def counted(rows: list[dict], m: str) -> list[dict]:
    return W.one_position([r for r in rows if r["m"] == m and r["status"] == "FILLED" and r.get("eligible")])


def boot_p_gt0(x: np.ndarray, day: np.ndarray, B: int = W.BOOT) -> tuple[list[float], float]:
    """Day-clustered bootstrap 95% interval of the mean and the one-sided p of mean <= 0."""
    if len(x) < 3:
        return [math.nan, math.nan], math.nan
    u, inv = np.unique(day, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=x), np.bincount(inv)
    pick = H.seeded_rng(SEED).integers(0, len(u), size=(B, len(u)))
    m = sums[pick].sum(axis=1) / cnts[pick].sum(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))], float((m <= 0).mean())


def analyse(res: dict) -> dict:
    P, F, rows = res["P"], res["F"], res["rows"]
    ops = {op["id"]: op for op in res["ops"]}
    r3 = r3_control(P, F, res["ops"])
    out = {"opportunities": {"n": len(ops), "with_t1": sum(op["t1"] is not None for op in ops.values()),
                             "up": sum(op["d"] == 1 for op in ops.values())},
           "methods": {}, "funnel": {}}
    a1 = {r["op"]: r for r in counted(rows, "A1") if W.decided(r)}
    for m in CANDIDATES + CONTROLS:
        mr = [r for r in rows if r["m"] == m]
        st = {}
        for r in mr:
            k = r["status"] if r["status"] != "FILLED" else ("ELIGIBLE" if r.get("eligible") else f"REJECTED:{r.get('why')}")
            if r["status"] == "MISSED":
                k = f"MISSED:{r.get('why')}"
            st[k] = st.get(k, 0) + 1
        out["funnel"][m] = {"orders": len(mr), **st}
        u = counted(rows, m)
        dec = [r for r in u if W.decided(r)]
        r1, own = r1_control(P, u, ops) if u else (None, {})
        s = W.summarize(u, r1)
        s["r4_w3_matched"] = W.matched_random(P, u, res["lo_k"], res["hi_k"]) if u else None
        if dec:
            day = np.array([r["t_fill"] // 86400 for r in dec])
            for T in W.TP:
                key = f"tp{int(T)}"
                ex = np.array([float(r[key] == "TP") - r["D"] / (r["D"] + T) for r in dec])
                ci, _ = boot_p_gt0(ex, day)
                s[key]["excess_over_geometry"] = float(ex.mean())
                s[key]["excess_boot95"] = ci
                tm = [r[key + "_min"] for r in dec if r[key] == "TP"]
                s[key]["min_to_tp_quartiles"] = [float(np.percentile(tm, q)) for q in (25, 50, 75)] if tm else None
            s["tp10_first_net_negative"] = sum(1 for r in dec if r["tp10"] == "TP" and r["tp10_r"] <= 0)
            s["tp10_then_stop_before_tp20"] = sum(1 for r in dec if r["tp10"] == "TP" and r["tp20"] in ("SL", "AMBIGUOUS"))
            # entry price relative to the earliest plausible price and to the immediate entry (+ = better)
            imp0 = [op_d(ops[r["op"]]) * (ops[r["op"]]["p_0"] - r["e"]) / ops[r["op"]]["atr0"] for r in dec]
            s["entry_vs_p0_atr_quartiles"] = [float(np.percentile(imp0, q)) for q in (25, 50, 75)]
            imp1 = [op_d(ops[r["op"]]) * (F.c[ops[r["op"]]["t1"]] - r["e"]) / ops[r["op"]]["atr0"] for r in dec
                    if ops[r["op"]]["t1"] is not None]
            s["entry_vs_A1_atr_quartiles"] = [float(np.percentile(imp1, q)) for q in (25, 50, 75)] if imp1 else None
            dl = [(r["t_fill"] - tc(F, ops[r["op"]]["t0"])) / 60.0 for r in dec]
            s["delay_min_quartiles"] = [float(np.percentile(dl, q)) for q in (25, 50, 75)]
            cons = []
            for r in dec:
                op = ops[r["op"]]
                s0 = op["p_0"] / 4000.0
                mfe0, _ = W.excursions(P, op["t0"] + 1, 96, op["d"], op["p_0"], s0)
                if mfe0 and mfe0 > 0:
                    cons.append(max(0.0, op["d"] * (r["e"] - op["p_0"]) / s0) / mfe0)
            s["consumed_share_of_mfe_quartiles"] = [float(np.percentile(cons, q)) for q in (25, 50, 75)] if cons else None
            sens = {}
            for kmul in (1.5, 2.0):
                g = [r["tp10_r"] * (r["D"] + r["cost"]) + r["cost"] for r in dec]
                rr = [(gi - kmul * r["cost"]) / (r["D"] + kmul * r["cost"]) for gi, r in zip(g, dec)]
                sens[f"cost_x{kmul:g}"] = float(np.mean(rr))
            s["cost_sensitivity_mean_r_tp10"] = sens
            # paired against R1 (own control), R2 (A1 on the same opportunity) and R3 (random price in the zone)
            for nm, ctl in (("vs_R1", lambda r: own.get(id(r), math.nan)),
                            ("vs_R2_immediate", lambda r: a1[r["op"]]["tp10_r"] if r["op"] in a1 else math.nan),
                            ("vs_R3_zone", lambda r: r3.get(r["op"], {}).get("mean_r", math.nan))):
                diff = np.array([r["tp10_r"] - ctl(r) for r in dec], float)
                okm = np.isfinite(diff)
                ci, p = boot_p_gt0(diff[okm], day[okm])
                s[f"paired_{nm}"] = {"n": int(okm.sum()), "mean_diff_r": float(diff[okm].mean()) if okm.any() else math.nan,
                                     "boot95": ci, "p_one_sided": p}
            bs, bt = {}, {}
            for r in dec:
                kd = min(max(W.k_at(P, r["t_dec"]) - 1, 0), len(P.c) - 1)
                bs.setdefault(str(P.sess[kd]), []).append(r)
            for kk, v in sorted(bs.items()):
                bt[kk] = {"n": len(v), "tp10_first": sum(x["tp10"] == "TP" for x in v), "mean_r": float(np.mean([x["tp10_r"] for x in v]))}
            s["by_session"] = bt
            s["per_direction"] = {str(dd): W.summarize([r for r in u if r["d"] == dd]) for dd in (1, -1)}
        out["methods"][m] = {"name": NAMES[m], **s}
    fam = {}
    for T in W.TP:
        key = f"tp{int(T)}"
        fam[key] = holm({m: out["methods"][m].get(key, {}).get("random", {}).get("p_one_sided") for m in CANDIDATES})
    out["holm_vs_R1"] = fam
    verdict = {}
    for m in CANDIDATES:
        s = out["methods"][m]
        x = s.get("tp10", {})
        lb = (x.get("mean_net_r_boot95") or [math.nan])[0]
        ph = fam["tp10"].get(m)
        verdict[m] = {"n": s.get("n", 0), "mean_net_r_lb95": lb, "holm_p_tp10_vs_R1": ph,
                      "candidate": bool(s.get("n", 0) >= 30 and np.isfinite(lb) and lb > 0 and ph is not None and ph < 0.05)}
    out["verdict"] = verdict
    out["overall"] = ("CANDIDATE(S): " + ", ".join(m for m in CANDIDATES if verdict[m]["candidate"])
                      if any(v["candidate"] for v in verdict.values()) else "NO CANDIDATE")
    out["fibonacci_vs_random_level"] = fib_test(rows)
    desc = [describe(P, F, op) for op in res["ops"]]
    out["impulses"] = describe_summary(desc)
    out["depth_bins_B_rand"] = depth_bins(rows, ops)
    aux = aux_arrays(F)
    pr = [dict(r, **features(P, F, ops[r["op"]], r, aux)) for r in counted(rows, "B_rand") if W.decided(r)]
    out["predictive"] = predictive(pr, res["score_from"], int(P.t[-1]) + 900)
    out["r3_zone_control"] = {"opportunities": len(r3), "with_fills": sum(v["n"] > 0 for v in r3.values()),
                              "tp10_first_rate": (sum(v["tp10_first"] for v in r3.values()) / max(sum(v["n"] for v in r3.values()), 1)),
                              "mean_r": float(np.nanmean([v["mean_r"] for v in r3.values() if v["n"]])) if r3 else math.nan}
    return out


def op_d(op: dict) -> int:
    return op["d"]


def fib_test(rows: list[dict]) -> dict:
    """Every B level against the random-level control on the same opportunities (paired net R at +$10)."""
    rand = {r["op"]: r for r in counted(rows, "B_rand") if W.decided(r)}
    out, ps = {}, {}
    for lv in LEVELS:
        m = BNAME[lv]
        pairs = [(r, rand[r["op"]]) for r in counted(rows, m) if W.decided(r) and r["op"] in rand]
        if len(pairs) < 3:
            out[m] = {"n": len(pairs)}
            continue
        diff = np.array([a["tp10_r"] - b["tp10_r"] for a, b in pairs])
        day = np.array([a["t_fill"] // 86400 for a, _ in pairs])
        ci, p = boot_p_gt0(diff, day)
        out[m] = {"n": len(pairs), "fibonacci": lv in FIB, "mean_diff_r": float(diff.mean()), "boot95": ci, "p_one_sided": p}
        ps[m] = p
    hp = holm(ps)
    for m in hp:
        out[m]["holm_p"] = hp[m]
    out["fibonacci_supported"] = any(out[BNAME[lv]].get("holm_p", 1) < 0.05 and out[BNAME[lv]].get("boot95", [0])[0] > 0 for lv in FIB)
    return out


def describe_summary(desc: list[dict]) -> dict:
    q = lambda k: [float(np.nanpercentile([x[k] for x in desc if k in x], p)) for p in (10, 25, 50, 75, 90)] if any(k in x for x in desc) else None  # noqa: E731
    with_t1 = [x for x in desc if x["t1"]]
    return {"n": len(desc), "with_pullback": len(with_t1),
            "quantiles_10_25_50_75_90": {k: q(k) for k in ("R_usd", "R_atr", "bars_to_t0", "bars_to_t1", "disp_ratio",
                                                            "max_retrace_share", "retrace_bars", "atr_change",
                                                            "opposing_level_atr", "mfe_from_p0")},
            "share_new_extreme_in_window": float(np.mean([x["new_extreme_in_window"] for x in with_t1])) if with_t1 else None,
            "share_higher_low": float(np.mean([x["higher_low"] for x in with_t1])) if with_t1 else None,
            "share_structure_held": float(np.mean([x["structure_held"] for x in with_t1])) if with_t1 else None}


def depth_bins(rows: list[dict], ops: dict) -> list[dict]:
    rr = [r for r in counted(rows, "B_rand") if W.decided(r)]
    out = []
    for lo, hi in ((0.2, 0.35), (0.35, 0.5), (0.5, 0.65), (0.65, 0.8001)):
        b = [r for r in rr if lo <= r["u"] < hi]
        if not b:
            out.append({"depth": [lo, round(hi, 2)], "n": 0})
            continue
        day = np.array([r["t_fill"] // 86400 for r in b])
        ex = np.array([float(r["tp10"] == "TP") - r["D"] / (r["D"] + 10.0) for r in b])
        nr = np.array([r["tp10_r"] for r in b])
        out.append({"depth": [lo, round(hi, 2)], "n": len(b), "tp10_first": float(np.mean([r["tp10"] == "TP" for r in b])),
                    "median_D": float(np.median([r["D"] for r in b])), "excess_over_geometry": float(ex.mean()),
                    "excess_boot95": boot_p_gt0(ex, day)[0], "mean_r": float(nr.mean()), "mean_r_boot95": boot_p_gt0(nr, day)[0]})
    return out


TRADE_COLS = ("m", "d", "op", "t_dec", "t_fill", "kind", "status", "why", "eligible", "u", "D", "cost", "lots",
              "tp10", "tp15", "tp20", "tp10_r", "tp15_r", "tp20_r", "tp10_min", "mfe", "mae", "loss_usd")


def trades_csv(rows: list[dict], path: str) -> None:
    keep = {id(r) for m in CANDIDATES + CONTROLS for r in counted(rows, m)}
    with open(path, "w") as f:
        f.write(",".join(("utc_decision",) + TRADE_COLS + ("counted",)) + "\n")
        for r in sorted((r for r in rows if r.get("t_dec") is not None), key=lambda x: (x["t_dec"], x["m"])):
            vals = [pd.Timestamp(r["t_dec"], unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M")]
            for c in TRADE_COLS:
                v = r.get(c)
                vals.append("" if v is None or (isinstance(v, float) and not np.isfinite(v)) else
                            (f"{v:.4f}" if isinstance(v, float) else str(v)))
            vals.append("1" if id(r) in keep else "0")
            f.write(",".join(x.replace(",", ";") for x in vals) + "\n")


CASE_COLS = ("m", "d", "op", "t_dec", "t_fill", "kind", "status", "why", "eligible", "e", "stop", "D", "cost", "lots",
             "tp10", "tp15", "tp20", "tp10_r", "tp10_min", "mfe", "mae")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="B31b-W5 executable entry-price study (research only)")
    ap.add_argument("--part", default="development", choices=("development", "case"))
    ap.add_argument("--rd", help="research-data clone (development)")
    ap.add_argument("--store", help="market-data store (case)")
    ap.add_argument("--case", default="2026-11-18,2026-11-19T06:00")
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--trials", default=None)
    a = ap.parse_args(argv)
    if a.part == "development":                    # validation / holdout are not choices: sealed for W5
        m15, h1, m5, score_from = W.load(a.rd, "development", None)
    else:
        lo, hi = a.case.split(",")
        m15, h1, m5, score_from = store_frames(a.store, lo, hi)
    res = build(m15, h1, m5, score_from)
    if a.part == "development":
        out = analyse(res)
    else:
        out = {"ops": res["ops"], "rows": [{k: r.get(k) for k in CASE_COLS} for r in res["rows"]]}
    out["meta"] = {"registration": REG, "part": a.part, "code_sha256": code_sha(), "score_from": score_from,
                   "end": int(res["P"].t[-1]) + 900, "bars15": int((res["P"].t >= score_from).sum()),
                   "m5_coverage": W.m5_coverage(res["P"], score_from), "data_hash": H.data_hash(m15),
                   "contract_oz_per_lot": "100 ASSUMED (no validated broker specification)"}
    with open(a.out, "w") as f:
        json.dump(W.jsonable(out), f, indent=1, allow_nan=False)
    if a.csv:
        trades_csv(res["rows"], a.csv)
    if a.trials and a.part == "development":
        H.log_trial(a.trials, {"id": f"{REG}-development", "registration": REG, "part": a.part, "code_sha256": code_sha(),
                               "opportunities": len(res["ops"]), "orders": len(res["rows"]), "overall": out["overall"],
                               "data_hash": out["meta"]["data_hash"]})
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
