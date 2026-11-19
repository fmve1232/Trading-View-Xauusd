"""B31b-W4 (research only; production never imports this module): pullback continuation (Module A), reversal against
the M30 trend (Module B), breakout and retest (Module C) and the entry-timing study, on M15 decisions with M30
context. research/registrations/B31b-W4.json fixes every rule before this code ran; this file implements it.

Every order goes through w3liq.execute (fills, $650 sizing, eligibility, the +$10 / +$15 / +$20 races, M5 ambiguity,
gap losses) and every method is compared with w3liq.matched_random, so W4 measures exactly as W3 did. Development
only: validation and holdout are sealed (harness.partition refuses them without an approved registration, and run()
refuses them here regardless).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os

import numpy as np
import pandas as pd

from .. import ta
from ..data import sources, store
from . import harness as H
from . import w3liq as W

REG = "B31b-W4"
PB_BARS = 24                  # a Module A episode: the 24 M15 bars after the BREAK
APPROACH = 0.25               # x ATR: within this distance of the zone = the approach (keyzones WATCH_NEAR_ATR)
EMA_TOL = 0.10                # x ATR: A2's reach of the EMA band
ZW_MIN, ZW_MAX = 0.15, 0.75   # zone width, x ATR (keyzones MIN_W / MAX_W)
A2_WIN, A3_WIN, A6_WIN = 4, 8, 4
B2_WIN, B3_WIN, B4_WIN = 4, 8, 16
C_WIN, C_TOL = 12, 0.10
TAX_BARS = 96
CTX_LR = 3
METHODS = ("A1", "A2", "A3", "A4", "A5", "A6", "T1", "T4", "T6", "B1", "B2", "B3", "B4", "C1", "C2")
NAMES = {"A1": "zone rejection close", "A2": "EMA band + displacement", "A3": "M5 MSS after the approach",
         "A4": "retest limit at the broken level", "A5": "sweep of the pullback high + displacement",
         "A6": "failed reclaim of the broken level", "T1": "early limit at the approach", "T4": "next M15 close after A1",
         "T6": "limit at A2's displacement midpoint", "B1": "sweep + reclaim close", "B2": "reclaim + displacement",
         "B3": "reclaim + M15 MSS", "B4": "higher low after the MSS", "C1": "break, acceptance, retest rejection",
         "C2": "C1 with the M30 context"}


# ---------------- context: M30 structure, point in time ----------------
def last_two(piv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """At each bar q: the last and the previous confirmed pivot values (pivot q - CTX_LR, known at q's close)."""
    last, prev = np.full(len(piv), np.nan), np.full(len(piv), np.nan)
    a = b = math.nan
    for q, v in enumerate(piv):
        if np.isfinite(v):
            a, b = float(v), a
        last[q], prev[q] = a, b
    return last, prev


def m30_context(t30: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """-1 / +1 / 0 at each M30 bar's close: lower highs and lower lows with EMA20 < EMA50 < EMA100 (keyzones.structure's
    'bearish'), the mirror, or neither."""
    hl, hp = last_two(ta.pivothigh(h, CTX_LR, CTX_LR))
    ll, lp = last_two(ta.pivotlow(l, CTX_LR, CTX_LR))
    e20, e50, e100 = (np.asarray(ta.ema(c, n), float) for n in (20, 50, 100))
    bear = (hl < hp) & (ll < lp) & (e20 < e50) & (e50 < e100)
    bull = (hl > hp) & (ll > lp) & (e20 > e50) & (e50 > e100)
    return np.where(bear, -1, np.where(bull, 1, 0)).astype(np.int64)


def ctx_at(F15: W.Frame, F30: W.Frame) -> np.ndarray:
    """The M30 context known at each M15 bar's close (the last M30 bar closed by then)."""
    cx = m30_context(F30.t, F30.h, F30.l, F30.c)
    k = np.searchsorted(F30.t + F30.sec, F15.t + F15.sec, side="right") - 1
    return np.where(k >= 0, cx[np.clip(k, 0, len(cx) - 1)], 0)


def last_swing(piv: np.ndarray, lr: int) -> tuple[np.ndarray, np.ndarray]:
    """At each bar q: the value and the pivot bar of the most recent pivot confirmed at or before q."""
    val, at = np.full(len(piv), np.nan), np.full(len(piv), -1, np.int64)
    v, p = math.nan, -1
    for q, x in enumerate(piv):
        if np.isfinite(x):
            v, p = float(x), q - lr
        val[q], at[q] = v, p
    return val, at


def htf_swings(df: pd.DataFrame, sec: int, t_close15: np.ndarray) -> dict:
    """The most recent confirmed swing high / low (pivot 3 / 3) of a higher timeframe known at each M15 close."""
    t = ta.epoch_s(df.index).astype(np.int64)
    h, l = df["high"].to_numpy(float), df["low"].to_numpy(float)
    hv, _ = last_swing(ta.pivothigh(h, CTX_LR, CTX_LR), CTX_LR)
    lv, _ = last_swing(ta.pivotlow(l, CTX_LR, CTX_LR), CTX_LR)
    k = np.searchsorted(t + sec, t_close15, side="right") - 1
    ok = k >= 0
    kk = np.clip(k, 0, len(t) - 1)
    return {1: np.where(ok, hv[kk], np.nan), -1: np.where(ok, lv[kk], np.nan)}


# ---------------- helpers ----------------
def against(F: W.Frame, d: int, a: int, b: int) -> float:
    """The extreme against direction d over bars a..b (the highest high for a short)."""
    return float(F.h[a:b + 1].max()) if d == -1 else float(F.l[a:b + 1].min())


def wick_zone(F: W.Frame, p: int, d: int, atr: float, L: float) -> tuple[float, float]:
    """(near, far) edges of the broken swing's wick zone (keyzones rule): near = the level L facing price after a break
    in direction d, far = L - d x width, width = the wick beyond the body clipped to [0.15, 0.75] x ATR."""
    body = min(F.o[p], F.c[p]) if d == -1 else max(F.o[p], F.c[p])
    w = min(max(abs(body - L), ZW_MIN * atr), ZW_MAX * atr)
    return L, L - d * w


def tc(F: W.Frame, j: int) -> int:
    return int(F.t[j]) + F.sec


def mkt(m: str, d: int, F: W.Frame, j: int, stop: float, **kw) -> dict:
    return {"m": m, "d": d, "kind": "MKT", "t": tc(F, j), "px": float(F.c[j]), "stop": float(stop), "j": j, **kw}


def lim(m: str, d: int, F: W.Frame, j: int, px: float, stop: float, valid: int, **kw) -> dict:
    return {"m": m, "d": d, "kind": "LIM", "t": tc(F, j), "px": float(px), "stop": float(stop), "j": j, "valid": valid, **kw}


# ---------------- Module A: episodes and their orders ----------------
def a_episodes(F: W.Frame, ctx: np.ndarray, score_from: int) -> list[dict]:
    n = len(F.c)
    sl_v, sl_p = last_swing(F.pl, W.SW_LR)
    sh_v, sh_p = last_swing(F.ph, W.SW_LR)
    busy = {1: -1, -1: -1}
    out = []
    for i in range(1, n):
        if F.t[i] + F.sec < score_from:
            continue
        d = int(ctx[i])
        if d == 0 or i <= busy[d]:
            continue
        L, p = (sl_v[i - 1], sl_p[i - 1]) if d == -1 else (sh_v[i - 1], sh_p[i - 1])
        atr = F.atr[i]
        if not np.isfinite(L) or p < 0 or not np.isfinite(atr) or atr <= 0:
            continue
        if not (d * (F.c[i] - L) > 0 and d * (F.c[i - 1] - L) <= 0):
            continue
        zn, zf = wick_zone(F, p, d, atr, L)
        out.append({"i": i, "d": d, "L": float(L), "zn": zn, "zf": zf, "atr": float(atr), "end": min(i + PB_BARS, n - 1)})
        busy[d] = i + PB_BARS
    return out


def a_orders(P: W.Path, F: W.Frame, ep: dict, e50: np.ndarray, pl5: np.ndarray | None, ph5: np.ndarray | None) -> list[dict]:
    i, d, L, zn, zf, atr, end = ep["i"], ep["d"], ep["L"], ep["zn"], ep["zf"], ep["atr"], ep["end"]
    buf = W.SL_BUF * atr
    eid = f"A{d:+d}@{tc(F, i)}"
    out = []
    reach = lambda j: -d * ((F.h[j] if d == -1 else F.l[j]) - zn)      # noqa: E731  >= 0: traded to / into the zone
    # T1 and A4: limits placed at the BREAK close
    out.append(lim("T1", d, F, i, zn + d * APPROACH * atr, zf - d * buf, end, ep=eid))
    out.append(lim("A4", d, F, i, L, zf - d * buf, i + W.LIMIT_BARS, ep=eid))
    j0 = next((j for j in range(i + 1, end + 1) if reach(j) >= -APPROACH * atr), None)
    if j0 is not None:
        # A1, then T4
        m1 = next((m for m in range(j0, end + 1) if reach(m) >= 0 and d * (F.c[m] - zn) > 0), None)
        if m1 is not None:
            out.append(mkt("A1", d, F, m1, against(F, d, j0, m1) - d * buf, ep=eid))
            if m1 + 1 < len(F.c) and d * (F.c[m1 + 1] - F.c[m1]) > 0:
                out.append(mkt("T4", d, F, m1 + 1, against(F, d, j0, m1 + 1) - d * buf, ep=eid))
        # A3: M5 MSS after the approach
        if P.t5 is not None and pl5 is not None:
            o3 = a3_m5(P, F, ep, j0, buf, pl5, ph5, eid)
            if o3 is not None:
                out.append(o3)
    # A2 (and T6): the first EMA-band reach that a displacement completes within A2_WIN bars
    for j in range(i + 1, end + 1):
        es = (F.e20[j], e50[j], F.e100[j])
        if not all(np.isfinite(es)):
            continue
        if d == -1:
            ok = all(x > F.c[j] for x in es) and F.h[j] >= min(es) - EMA_TOL * atr
        else:
            ok = all(x < F.c[j] for x in es) and F.l[j] <= max(es) + EMA_TOL * atr
        if not ok:
            continue
        m = next((m for m in range(j + 1, min(j + A2_WIN, len(F.c) - 1) + 1) if d * (F.c[m] - F.o[m]) >= W.DISP_BODY * atr), None)
        if m is None:
            continue
        stop = against(F, d, j, m) - d * buf
        out.append(mkt("A2", d, F, m, stop, ep=eid))
        out.append(lim("T6", d, F, m, (F.o[m] + F.c[m]) / 2.0, stop, m + W.DISP_BARS, ep=eid))
        break
    # A5: a pullback minor swing inside the episode, swept and closed back, then a displacement within 2 bars
    piv2 = F.ph2 if d == -1 else F.pl2
    ref = math.nan
    for k in range(i + 1, end + 1):
        q = k - 1
        if q > i and np.isfinite(piv2[q]) and q - W.MSS_LR > i:
            ref = float(piv2[q])
        if not np.isfinite(ref):
            continue
        swept = (F.h[k] > ref and F.c[k] < ref) if d == -1 else (F.l[k] < ref and F.c[k] > ref)
        if not swept:
            continue
        m = next((m for m in range(k, min(k + 2, len(F.c) - 1) + 1) if d * (F.c[m] - F.o[m]) >= W.DISP_BODY * atr), None)
        if m is not None:
            out.append(mkt("A5", d, F, m, against(F, d, k, m) - d * buf, ep=eid))
            break
    # A6: a close back across L against d, then within A6_WIN bars a close across it again with d
    for r in range(i + 1, end + 1):
        if d * (F.c[r] - L) >= 0:
            continue
        m = next((m for m in range(r + 1, min(r + A6_WIN, len(F.c) - 1) + 1) if d * (F.c[m] - L) > 0), None)
        if m is not None:
            out.append(mkt("A6", d, F, m, against(F, d, r, m) - d * buf, ep=eid))
            break
    return out


def a3_m5(P: W.Path, F: W.Frame, ep: dict, j0: int, buf: float, pl5: np.ndarray, ph5: np.ndarray, eid: str) -> dict | None:
    """A3: from the first M5 bar of the approach, the first M5 close beyond the most recent M5 minor swing in direction
    d whose pivot formed at or after that bar, within A3_WIN M15 bars; cancelled by an M15 close beyond the zone's far
    side first. Stop = the extreme since the approach (M5 bars) + buffer."""
    d, zn, zf, atr = ep["d"], ep["zn"], ep["zf"], ep["atr"]
    a, b = W.m5_span(P, int(F.t[j0]), int(F.t[j0]) + 900 * (A3_WIN + 1))
    if b <= a:
        return None
    near = zn + d * APPROACH * atr
    s = next((j for j in range(a, b) if ((P.h5[j] >= near) if d == -1 else (P.l5[j] <= near))), None)
    if s is None:
        return None
    piv = pl5 if d == -1 else ph5
    ref, run = math.nan, -math.inf if d == -1 else math.inf
    for j in range(s, b):
        run = max(run, P.h5[j]) if d == -1 else min(run, P.l5[j])
        q = j - 1
        if q >= s + W.M5_LR and np.isfinite(piv[q]):
            ref = float(piv[q])
        t_close = int(P.t5[j]) + 300
        k15 = int(np.searchsorted(F.t + F.sec, t_close, side="right")) - 1      # the last M15 bar closed by then
        if k15 >= j0 and any(d * (F.c[x] - zf) < 0 for x in range(j0, k15 + 1)):
            return None
        if np.isfinite(ref) and d * (P.c5[j] - ref) > 0:
            return {"m": "A3", "d": d, "kind": "MKT", "t": t_close, "px": float(P.c5[j]), "stop": float(run - d * buf),
                    "j": None, "ep": eid}
    return None


# ---------------- Module B: sweeps against the context ----------------
def b_events(F: W.Frame, ctx: np.ndarray, score_from: int) -> list[dict]:
    n = len(F.c)
    sl_v, _ = last_swing(F.pl, W.SW_LR)
    sh_v, _ = last_swing(F.ph, W.SW_LR)
    out = []
    for i in range(1, n):
        if F.t[i] + F.sec < score_from:
            continue
        c = int(ctx[i])
        atr = F.atr[i]
        if c == 0 or not np.isfinite(atr) or atr <= 0:
            continue
        lv = [(sl_v[i - 1], "SW"), (F.pools["PDL"][i], "PD")] if c == -1 else [(sh_v[i - 1], "SW"), (F.pools["PDH"][i], "PD")]
        for L, kind in lv:
            if not np.isfinite(L):
                continue
            if c == -1 and F.l[i] < L and F.c[i] > L and F.c[i - 1] > L:
                out.append({"i": i, "c": c, "d": 1, "L": float(L), "kind": kind, "atr": float(atr)})
                break
            if c == 1 and F.h[i] > L and F.c[i] < L and F.c[i - 1] < L:
                out.append({"i": i, "c": c, "d": -1, "L": float(L), "kind": kind, "atr": float(atr)})
                break
    return out


def b_orders(F: W.Frame, ev: dict) -> list[dict]:
    i, d, L, atr = ev["i"], ev["d"], ev["L"], ev["atr"]
    n = len(F.c)
    buf = W.SL_BUF * atr
    eid = f"B{d:+d}@{tc(F, i)}"
    out = [mkt("B1", d, F, i, against(F, d, i, i) - d * buf, ep=eid)]
    for m in range(i + 1, min(i + B2_WIN, n - 1) + 1):
        if not all(d * (F.c[k] - L) > 0 for k in range(i, m + 1)):
            break
        if d * (F.c[m] - F.o[m]) >= W.DISP_BODY * atr:
            out.append(mkt("B2", d, F, m, against(F, d, i, m) - d * buf, ep=eid))
            break
    piv2 = F.ph2 if d == 1 else F.pl2
    ref, m3 = math.nan, None
    for q in range(max(i - B3_WIN + 1, 0), i + 1):                              # minor swings confirmed after i - 8
        if np.isfinite(piv2[q]):
            ref = float(piv2[q])
    for m in range(i + 1, min(i + B3_WIN, n - 1) + 1):
        if np.isfinite(ref) and d * (F.c[m] - ref) > 0:
            m3 = m
            out.append(mkt("B3", d, F, m, against(F, d, i, m) - d * buf, ep=eid))
            break
        if np.isfinite(piv2[m]):
            ref = float(piv2[m])
    if m3 is not None:
        pa = F.pl2 if d == 1 else F.ph2
        x = against(F, d, i, i)
        for q in range(m3 + 1, min(m3 + B4_WIN, n - 1) + 1):
            v = pa[q]
            if np.isfinite(v) and q - W.MSS_LR > i and d * (v - x) > 0:
                out.append(mkt("B4", d, F, q, v - d * buf, ep=eid))
                break
    return out


def m30_swings(F30: W.Frame) -> dict:
    return {1: last_swing(F30.ph, CTX_LR)[0], -1: last_swing(F30.pl, CTX_LR)[0], "tc": F30.t + F30.sec}


def b_taxonomy(F: W.Frame, F30: W.Frame, ev: dict, sw: dict) -> str:
    """Descriptive only (uses the future; never a feature): what followed the sweep within TAX_BARS bars."""
    i, d, atr = ev["i"], ev["d"], ev["atr"]
    n = len(F.c)
    x, c0 = against(F, d, i, i), F.c[i]
    reached = broke = None
    for k in range(i + 1, min(i + TAX_BARS, n - 1) + 1):
        if broke is None and d * (F.c[k] - x) < 0:
            broke = k
        if reached is None and d * ((F.h[k] if d == 1 else F.l[k]) - c0) >= atr:
            reached = k
    if reached is None:
        return "CONTINUATION" if broke is not None else "UNRESOLVED"
    if broke is not None and broke <= reached:
        return "CONTINUATION"
    if broke is not None:
        return "SHORT-COVERING BOUNCE"
    t0, t1 = tc(F, i), tc(F, min(i + TAX_BARS, n - 1))
    v = sw[d]
    for q in range(max(int(np.searchsorted(sw["tc"], t0, side="right")), 1), int(np.searchsorted(sw["tc"], t1, side="right"))):
        if np.isfinite(v[q - 1]) and d * (F30.c[q] - v[q - 1]) > 0:
            return "GENUINE REVERSAL"
    return "FAILED BREAKDOWN"


# ---------------- Module C: break, acceptance, retest ----------------
def c_orders(F: W.Frame, ctx: np.ndarray, hts: list[dict], score_from: int) -> list[dict]:
    n = len(F.c)
    out = []
    for i in range(1, n - 1):
        if F.t[i] + F.sec < score_from:
            continue
        atr = F.atr[i]
        if not np.isfinite(atr) or atr <= 0:
            continue
        for d in (1, -1):
            cands = [F.pools["PDH" if d == 1 else "PDL"][i]] + [ht[d][i - 1] for ht in hts]
            L = next((x for x in cands if np.isfinite(x) and d * (F.c[i] - x) > 0 and d * (F.c[i - 1] - x) <= 0
                      and d * (F.c[i + 1] - x) > 0), None)
            if L is None:
                continue
            a = i + 1
            buf = W.SL_BUF * atr
            for k in range(a + 1, min(a + C_WIN, n - 1) + 1):
                if d * (F.c[k] - L) < 0:
                    break                                       # closed back across the level first: cancelled
                touch = (F.h[k] >= L - C_TOL * atr) if d == -1 else (F.l[k] <= L + C_TOL * atr)
                if touch and d * (F.c[k] - L) > 0:
                    o = mkt("C1", d, F, k, against(F, d, a, k) - d * buf, ep=f"C{d:+d}@{tc(F, i)}")
                    out.append(o)
                    if int(ctx[k]) == d:
                        out.append({**o, "m": "C2"})
                    break
    return out


# ---------------- a run ----------------
def code_sha() -> str:
    return hashlib.sha256(open(__file__, "rb").read()).hexdigest()


def store_frames(st_dir: str, t_from: str, t_to: str):
    """The market-data store's bars (the 17-18 Nov case study: the research-data 15min series ends 2 Nov)."""
    ld = lambda nm: sources.trading_week_only(sources.drop_offgrid(store.load(st_dir, nm)))      # noqa: E731
    lo, hi = pd.Timestamp(t_from, tz="UTC"), pd.Timestamp(t_to, tz="UTC")
    cut = lambda x: x[(x.index >= lo - pd.Timedelta(days=W.WARM_DAYS)) & (x.index < hi)]        # noqa: E731
    m15, h1, m5 = (cut(ld(nm)) for nm in ("XAU_USD_15m", "XAU_USD_60m", "XAU_USD_5m"))
    return m15, h1, m5, int(lo.timestamp())


def orders_of(P: W.Path, F15: W.Frame, F30: W.Frame, h1: pd.DataFrame, score_from: int) -> tuple[list, list, list]:
    """Every registered order (before execution), the Module A episodes and the Module B events."""
    ctx = ctx_at(F15, F30)
    e50 = np.asarray(ta.ema(F15.c, 50), float)
    pl5 = ph5 = None
    if P.t5 is not None:
        pl5, ph5 = ta.pivotlow(P.l5, W.M5_LR, W.M5_LR), ta.pivothigh(P.h5, W.M5_LR, W.M5_LR)
    tclose = F15.t + F15.sec
    m30df = pd.DataFrame({"high": F30.h, "low": F30.l}, index=pd.to_datetime(F30.t, unit="s", utc=True))
    hts = [htf_swings(h1, 3600, tclose), htf_swings(m30df, 1800, tclose)]            # H1, then M30 (after PD)
    eps = a_episodes(F15, ctx, score_from)
    bev = b_events(F15, ctx, score_from)
    orders = []
    for ep in eps:
        orders += a_orders(P, F15, ep, e50, pl5, ph5)
    sw30 = m30_swings(F30)
    for ev in bev:
        ev["tax"] = b_taxonomy(F15, F30, ev, sw30)
        orders += b_orders(F15, ev)
    orders += c_orders(F15, ctx, hts, score_from)
    return orders, eps, bev


def run(m15: pd.DataFrame, h1: pd.DataFrame, m5: pd.DataFrame | None, score_from: int) -> dict:
    P, F15, F30, incomplete = W.frames(m15, h1, m5)
    ctx = ctx_at(F15, F30)
    orders, eps, bev = orders_of(P, F15, F30, h1, score_from)
    rows = []
    for od in orders:
        r = W.execute(P, F15, od)
        r.update(tf="M15", ep=od.get("ep"), ev_id=f"{od['m']}-{od['t']}-{od['d']}")
        rows.append(r)
    m5cov = W.m5_coverage(P, score_from)
    meta = {"score_from": score_from, "end": int(P.t[-1]) + 900, "bars15": int((P.t >= score_from).sum()),
            "m30_incomplete_pairs": incomplete, "m5_coverage": m5cov, "data_hash": H.data_hash(m15),
            "context_share": {str(v): float(np.mean(ctx[(F15.t + F15.sec) >= score_from] == v)) for v in (-1, 0, 1)}}
    return {"meta": meta, "episodes": eps, "b_events": bev, "rows": rows, "P": P,
            "lo_k": int(np.searchsorted(P.t, score_from)), "hi_k": len(P.c)}


def holm(ps: dict) -> dict:
    items = sorted(((p, k) for k, p in ps.items() if p is not None and np.isfinite(p)))
    m, out, run_max = len(items), {}, 0.0
    for r, (p, k) in enumerate(items):
        run_max = max(run_max, min(1.0, (m - r) * p))
        out[k] = run_max
    return out


def usable(rows: list[dict]) -> list[dict]:
    return W.one_position([r for r in rows if r["status"] == "FILLED" and r.get("eligible")])


def analyse(res: dict) -> dict:
    P, rows = res["P"], res["rows"]
    out = {"methods": {}, "funnel": {}}
    for m in METHODS:
        mr = [r for r in rows if r["m"] == m]
        st = {}
        for r in mr:
            k = r["status"] if r["status"] != "FILLED" else ("ELIGIBLE" if r.get("eligible") else f"REJECTED:{r.get('why')}")
            st[k] = st.get(k, 0) + 1
        out["funnel"][m] = {"orders": len(mr), **st}
        u = usable(mr)
        rnd = W.matched_random(P, u, res["lo_k"], res["hi_k"]) if u else None
        s = W.summarize(u, rnd)
        s["per_direction"] = {str(d): W.summarize([r for r in u if r["d"] == d]) for d in (1, -1)}
        bs = {}
        for r in u:
            if W.decided(r):
                kd = min(max(W.k_at(P, r["t_dec"]) - 1, 0), len(P.c) - 1)
                bs.setdefault(str(P.sess[kd]), []).append(r)
        s["by_session"] = {k: {"n": len(v), "tp10_first": sum(x["tp10"] == "TP" for x in v)} for k, v in sorted(bs.items())}
        out["methods"][m] = {"name": NAMES[m], **s}
    fam = {}
    for T in W.TP:
        key = f"tp{int(T)}"
        ps = {m: out["methods"][m].get(key, {}).get("random", {}).get("p_one_sided") for m in METHODS}
        fam[key] = holm(ps)
    out["holm"] = fam
    verdict = {}
    for m in METHODS:
        s = out["methods"][m]
        x = s.get("tp10", {})
        n = s.get("n", 0)
        lb = (x.get("mean_net_r_boot95") or [math.nan])[0]
        ph = fam["tp10"].get(m)
        ok = n >= 30 and np.isfinite(lb) and lb > 0 and ph is not None and ph < 0.05
        verdict[m] = {"n": n, "mean_net_r_lb95": lb, "holm_p_tp10": ph, "candidate": bool(ok)}
    out["verdict"] = verdict
    out["overall"] = "CANDIDATE(S): " + ", ".join(m for m in METHODS if verdict[m]["candidate"]) if any(
        v["candidate"] for v in verdict.values()) else "NO CANDIDATE"
    out["timing_paired_vs_A1"] = timing(rows)
    out["b_taxonomy"] = taxonomy_table(res)
    return out


def timing(rows: list[dict]) -> dict:
    """Paired comparison on Module A episodes where A1 and the other method both filled, eligible and decided."""
    by = {}
    for r in rows:
        if r.get("ep") and r["status"] == "FILLED" and r.get("eligible") and W.decided(r):
            by.setdefault(r["ep"], {})[r["m"]] = r
    out = {}
    for m in ("T1", "A3", "T4", "A4", "A2", "T6", "A5", "A6"):
        pairs = [(e["A1"], e[m]) for e in by.values() if "A1" in e and m in e]
        if not pairs:
            out[m] = {"n": 0}
            continue
        dr = np.array([b["tp10_r"] - a["tp10_r"] for a, b in pairs], float)
        de = np.array([b["d"] * (b["e"] - a["e"]) / a["s"] for a, b in pairs], float)       # + = a better price for m
        day = np.array([a["t_fill"] // 86400 for a, _ in pairs])
        out[m] = {"n": len(pairs), "mean_diff_net_r": float(np.nanmean(dr)), "boot95": W.boot_mean(np.nan_to_num(dr), day),
                  "median_entry_better_usd": float(np.median(de)),
                  "tp10_first": {"A1": int(sum(a["tp10"] == "TP" for a, _ in pairs)), m: int(sum(b["tp10"] == "TP" for _, b in pairs))}}
    return out


def taxonomy_table(res: dict) -> dict:
    t = {}
    for ev in res["b_events"]:
        t.setdefault(ev["tax"], 0)
        t[ev["tax"]] += 1
    return {"events": len(res["b_events"]), "classes": t}


CASE_COLS = ("m", "d", "ep", "t_dec", "t_fill", "kind", "status", "why", "eligible", "e", "stop", "D", "cost", "lots",
             "tp10", "tp15", "tp20", "tp10_r", "tp15_r", "tp20_r", "tp10_min", "mfe", "mae", "loss_usd")
TRADE_COLS = ("m", "d", "ep", "t_dec", "t_fill", "kind", "status", "why", "eligible", "D", "cost", "lots",
              "tp10", "tp15", "tp20", "tp10_r", "tp15_r", "tp20_r", "tp10_min", "tp15_min", "tp20_min", "mfe", "mae", "loss_usd")


def trades_csv(rows: list[dict], path: str) -> None:
    u = {id(r) for r in usable(rows)}
    with open(path, "w") as f:
        f.write(",".join(("utc_decision",) + TRADE_COLS + ("counted",)) + "\n")
        for r in sorted(rows, key=lambda x: (x["t_dec"], x["m"])):
            vals = [pd.Timestamp(r["t_dec"], unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M")]
            for c in TRADE_COLS:
                v = r.get(c)
                vals.append("" if v is None or (isinstance(v, float) and not np.isfinite(v)) else
                            (f"{v:.4f}" if isinstance(v, float) else str(v)))
            vals.append("1" if id(r) in u else "0")
            f.write(",".join(x.replace(",", ";") for x in vals) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="B31b-W4 pullback / reversal / retest study (research only)")
    ap.add_argument("--part", default="development", choices=("development", "case"))
    ap.add_argument("--rd", help="research-data clone (development)")
    ap.add_argument("--store", help="market-data store (case study)")
    ap.add_argument("--case", default="2026-11-17,2026-11-19")
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--trials", default=None)
    a = ap.parse_args(argv)
    if a.part == "development":                    # validation / holdout are not choices: sealed for W4
        m15, h1, m5, score_from = W.load(a.rd, "development", None)
    else:
        lo, hi = a.case.split(",")
        m15, h1, m5, score_from = store_frames(a.store, lo, hi)
    res = run(m15, h1, m5, score_from)
    out = analyse(res) if a.part == "development" else {"rows": [{k: r.get(k) for k in CASE_COLS} for r in res["rows"]],
                                                          "b_events": res["b_events"], "episodes": res["episodes"]}
    out["meta"] = {**res["meta"], "registration": REG, "part": a.part, "code_sha256": code_sha()}
    with open(a.out, "w") as f:
        json.dump(W.jsonable(out), f, indent=1, allow_nan=False)
    if a.csv:
        trades_csv(res["rows"], a.csv)
    if a.trials and a.part == "development":
        H.log_trial(a.trials, {"id": f"{REG}-development", "registration": REG, "part": a.part, "code_sha256": code_sha(),
                               "orders": len(res["rows"]), "episodes": len(res["episodes"]), "b_events": len(res["b_events"]),
                               "overall": out["overall"], "data_hash": res["meta"]["data_hash"]})
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
