"""B31b-W3 (research/registrations/B31b-W3.json, approved 2026-11-18; written after the registration was committed).

M15 / M30 liquidity sweep, liquidation and breakout events on spot XAU/USD: every crossing of a live liquidity level,
what was true before it, what the crossing bar did, and what price did afterwards; the classes A-G; two independent
engines (A reversal, B continuation) with ten entry methods; costs, $650 sizing and a matched random control.

Causality. A level is used at bar i only if it was known before bar i opened. Every feature is computed from bars that
closed at or before the decision. Outcomes (paths, races, classes) read only bars that open after the decision and are
never features. Distances are $ at $4,000 (divided by s = price / 4000, as B31); costs are today's $ per oz.

Implementation notes fixed before any run (amendment A1 in the registration):
  * a level the crossing bar OPENS beyond (a gap) is consumed without an event and counted as gapped;
  * type 11 = a BREAK with a close back inside at bar i+1 or i+2; type 12 = closes beyond at i, i+1 and i+2 (exclusive);
  * class F = before either +$10 barrier, BOTH the event's own side is pushed again (the sweep extreme exceeded, or for
    a BREAK a close back inside) AND the nearest live level on the other side is crossed.

Research code: never imported by production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import sessions, ta
from ..data import sources
from . import b31, history
from . import harness as H

REG = "B31b-W3"
FREEZE_ID = "B31b-W3-FREEZE"
TP = (10.0, 15.0, 20.0)
MOVES = (5.0, 10.0, 15.0, 20.0)
HORIZONS = (5, 15, 30, 60, 120, 240)              # minutes
SL_BUF = 0.2                                      # x ATR beyond the structure (B31 SL_BUF)
HOLD_SEC = 96 * 900                               # 24 h time stop and class window (B31 HOLD)
LIMIT_BARS = 8
DISP_BARS = 4
DISP_BODY = 1.0
MSS_BARS = 8
MSS_LR = 2
MSS_LOOK = 20
SW_LR = 3
SW_DAYS = 5
EQ_GAP = 4
EQ_USD = 0.5
EQ_ATR = 0.10
M5_WIN = 3600
M5_LR = 2
ORIGIN_BARS = 8
COST_FRAC = 0.15
RISK_USD = 650.0
OZ = 100.0
MARGIN = 0.05
SEED = 3103
RND_K = 20
BOOT = 2000
WARM_DAYS = 45
EPS = 1e-9
TFS = {"M15": 900, "M30": 1800}
RANK = {"PW": 7, "PD": 6, "PS": 5, "AS": 4, "LO": 4, "NY": 4, "EQ": 3, "SW": 2}
STATIC = ("PDH", "PDL", "PWH", "PWL", "ASH", "ASL", "LOH", "LOL", "NYH", "NYL", "PSH", "PSL")
SESS = ("ASIA", "LDN_OPEN", "LDN_CONT", "NY_OPEN", "OVERLAP", "NY_CONT", "OFF")
A_METHODS = ("A-IMM", "A-CONF", "A-MSS", "A-M5MSS", "A-RETEST", "A-DISP")
B_METHODS = ("B-CLOSE", "B-ACC", "B-RETEST", "B-DISP")
SEALED = ("validation", "holdout")


# ---------------- frames ----------------
@dataclass
class Path:
    """The 15m grid every race and path measurement runs on, and the optional M5 series that refines it."""
    t: np.ndarray; o: np.ndarray; h: np.ndarray; l: np.ndarray; c: np.ndarray  # noqa: E702
    cost: np.ndarray; atr: np.ndarray; sess: np.ndarray
    t5: np.ndarray | None = None; o5: np.ndarray | None = None; h5: np.ndarray | None = None  # noqa: E702
    l5: np.ndarray | None = None; c5: np.ndarray | None = None  # noqa: E702


@dataclass
class Frame:
    tf: str; sec: int
    t: np.ndarray; o: np.ndarray; h: np.ndarray; l: np.ndarray; c: np.ndarray  # noqa: E702
    atr: np.ndarray; atr100: np.ndarray; e20: np.ndarray; e100: np.ndarray; e200: np.ndarray  # noqa: E702
    er20: np.ndarray; twap: np.ndarray; sess: np.ndarray; date: np.ndarray; dord: np.ndarray  # noqa: E702
    in_lon: np.ndarray; in_ny: np.ndarray  # noqa: E702
    pools: dict; end15: np.ndarray; rstart: dict  # noqa: E702
    m30_up: np.ndarray; m30_dn: np.ndarray; h1_up: np.ndarray; h1_dn: np.ndarray; h4_up: np.ndarray; h4_dn: np.ndarray  # noqa: E702
    ph: np.ndarray; pl: np.ndarray; ph2: np.ndarray; pl2: np.ndarray  # noqa: E702


def arrays(df: pd.DataFrame):
    return (ta.epoch_s(df.index).astype(np.int64),) + tuple(df[x].to_numpy(float) for x in ("open", "high", "low", "close"))


def make_m30(m15: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """M30 from pairs of 15m bars opening at :00 + :15 or :30 + :45; a 30m bar needs both (incomplete pairs counted)."""
    key = m15.index.floor("30min")
    g = m15.groupby(key)
    agg = g.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    cnt = g.size()
    full = cnt.to_numpy() == 2
    out = agg[full]
    out.index = pd.DatetimeIndex(out.index)
    return out, int((~full).sum())


def sess_bucket(cal: pd.DataFrame) -> np.ndarray:
    hour = cal["hour"].to_numpy()
    a, lo, ny = (cal[k].to_numpy(bool) for k in ("in_asian", "in_london", "in_ny"))
    ny_open = np.where(cal["us_dst"].to_numpy(bool), 14, 15)
    ldo = lo & (hour < 9)
    nyo = ny & (hour < ny_open + 2)
    out = np.full(len(hour), "OFF", object)
    out[a] = "ASIA"
    out[lo & ~ldo & ~ny] = "LDN_CONT"
    out[ldo] = "LDN_OPEN"
    out[ny & ~lo & ~nyo] = "NY_CONT"
    out[lo & ny & ~nyo] = "OVERLAP"
    out[nyo] = "NY_OPEN"
    return out


def efficiency_ratio(c: np.ndarray, n: int = 20) -> np.ndarray:
    d = np.abs(np.diff(c, prepend=np.nan))
    s = pd.Series(d).rolling(n).sum().to_numpy()
    net = np.abs(c - np.concatenate([np.full(n, np.nan), c[:-n]]))
    return np.where(s > 0, net / s, np.nan)


def twap(h, l, c, date) -> np.ndarray:
    tp = pd.Series((h + l + c) / 3.0)
    g = pd.Series(date)
    return (tp.groupby(g).cumsum() / tp.groupby(g).cumcount().add(1)).to_numpy(float)


def htf_trend(t_close: np.ndarray, bars: pd.DataFrame, sec: int) -> tuple[np.ndarray, np.ndarray]:
    return b31.htf_up_at(t_close, bars, sec)


def prev_session_levels(cal: pd.DataFrame, h: np.ndarray, l: np.ndarray):
    """High / low of the most recently COMPLETED of the three sessions (Asia, London, New York) before each bar: a
    session's levels exist from the bar after its last bar until another session completes."""
    n = len(h)
    runs = []
    for col in ("in_asian", "in_london", "in_ny"):
        f = cal[col].to_numpy(bool)
        i = 0
        while i < n:
            if not f[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and f[j + 1]:
                j += 1
            runs.append((j, float(h[i:j + 1].max()), float(l[i:j + 1].min())))
            i = j + 1
    hi, lo = np.full(n, np.nan), np.full(n, np.nan)
    if not runs:
        return hi, lo
    runs.sort()
    ends = np.array([r[0] for r in runs])
    k = np.searchsorted(ends, np.arange(n) - 1, side="right") - 1
    ok = k >= 0
    hi[ok] = np.array([r[1] for r in runs])[k[ok]]
    lo[ok] = np.array([r[2] for r in runs])[k[ok]]
    return hi, lo


def run_start(x: np.ndarray) -> np.ndarray:
    """Index where the current run of equal values began (NaN runs included)."""
    n = len(x)
    out = np.zeros(n, np.int64)
    for i in range(1, n):
        same = (x[i] == x[i - 1]) or (np.isnan(x[i]) and np.isnan(x[i - 1]))
        out[i] = out[i - 1] if same else i
    return out


def make_frame(df: pd.DataFrame, tf: str, h1: pd.DataFrame, m30: pd.DataFrame | None, end15: np.ndarray) -> Frame:
    sec = TFS[tf]
    t, o, h, l, c = arrays(df)
    cal = sessions.calendar(df.index)
    date = np.asarray(cal["trading_date"].to_numpy())
    uniq = {d: k for k, d in enumerate(dict.fromkeys(date.tolist()))}
    dord = np.array([uniq[d] for d in date.tolist()], np.int64)
    pools, _ = b31.build_pools(df, cal, np.full(len(df), np.nan), np.full(len(df), np.nan))
    pools.pop("EQH"), pools.pop("EQL")
    psh, psl = prev_session_levels(cal, h, l)
    pools["PSH"], pools["PSL"] = psh, psl
    atr = ta.atr(h, l, c, 14)
    tc = t + sec
    if m30 is not None:
        mu, md = htf_trend(tc, m30, 1800)
    else:
        e20, e100 = np.asarray(ta.ema(c, 20), float), np.asarray(ta.ema(c, 100), float)
        mu, md = e20 > e100, e20 < e100
    hu, hd = htf_trend(tc, h1, 3600)
    h4 = sources.resample_ny_session(h1, 4)
    fu, fd = htf_trend(tc, h4, 14400)
    return Frame(tf=tf, sec=sec, t=t, o=o, h=h, l=l, c=c, atr=atr, atr100=ta.atr(h, l, c, 100),
                 e20=np.asarray(ta.ema(c, 20), float), e100=np.asarray(ta.ema(c, 100), float), e200=np.asarray(ta.ema(c, 200), float),
                 er20=efficiency_ratio(c), twap=twap(h, l, c, date), sess=sess_bucket(cal), date=date, dord=dord,
                 in_lon=cal["in_london"].to_numpy(bool), in_ny=cal["in_ny"].to_numpy(bool), pools=pools, end15=end15,
                 rstart={k: run_start(pools[k]) for k in STATIC},
                 m30_up=mu, m30_dn=md, h1_up=hu, h1_dn=hd, h4_up=fu, h4_dn=fd,
                 ph=ta.pivothigh(h, SW_LR, SW_LR), pl=ta.pivotlow(l, SW_LR, SW_LR),
                 ph2=ta.pivothigh(h, MSS_LR, MSS_LR), pl2=ta.pivotlow(l, MSS_LR, MSS_LR))


def make_path(m15: pd.DataFrame, m5: pd.DataFrame | None) -> Path:
    t, o, h, l, c = arrays(m15)
    cal = sessions.calendar(m15.index)
    P = Path(t=t, o=o, h=h, l=l, c=c, cost=H.cost_pts(m15.index), atr=ta.atr(h, l, c, 14), sess=sess_bucket(cal))
    if m5 is not None and len(m5):
        P.t5, P.o5, P.h5, P.l5, P.c5 = arrays(m5)
    return P


# ---------------- levels and events ----------------
def level_kind(name: str) -> str:
    return name[:2]


def live_swings(F: Frame):
    """Swing and equal-high / low levels: (side, value, live_from_bar, expire_ord, kind, origin_bar)."""
    out = []
    n = len(F.c)
    for side, piv, ext in ((1, F.ph, F.h), (-1, F.pl, F.l)):
        conf = []                                           # confirmed swings of this side: (pivot bar, value, conf bar)
        for q in range(n):
            v = piv[q]
            if not np.isfinite(v):
                continue
            p = q - SW_LR                                   # the pivot bar; known from the close of bar q
            exp = F.dord[q] + SW_DAYS
            out.append((side, float(v), q + 1, exp, "SW" + ("H" if side == 1 else "L"), p))
            tol = max(EQ_USD * F.c[q] / 4000.0, EQ_ATR * F.atr[q]) if np.isfinite(F.atr[q]) else EQ_USD * F.c[q] / 4000.0
            for (p0, v0, q0) in reversed(conf):
                if F.dord[q] >= F.dord[q0] + SW_DAYS:
                    break
                if p - p0 < EQ_GAP:
                    continue
                # the earlier swing must still be untaken at q: no bar between its confirmation and q traded through it
                seg = F.h[q0 + 1:q + 1] if side == 1 else F.l[q0 + 1:q + 1]
                untaken = not (np.any(seg > v0 + EPS) if side == 1 else np.any(seg < v0 - EPS))
                if untaken and abs(v - v0) <= tol + EPS:
                    lv = max(v, v0) if side == 1 else min(v, v0)
                    out.append((side, float(lv), q + 1, exp, "EQ" + ("H" if side == 1 else "L"), p))
                    break
            conf.append((p, float(v), q))
    return out


def find_events(F: Frame, score_from: int) -> tuple[list[dict], dict]:
    """Every first crossing of a live level, one event per bar and side. score_from: epoch s of the first bar scored
    (earlier bars still consume levels)."""
    n = len(F.c)
    stats = {"gapped": 0, "bars": 0}
    dyn = sorted(live_swings(F), key=lambda x: x[2])
    di = 0
    live_dyn = []                                           # [side, value, expire_ord, kind, origin, alive]
    taken = set()                                           # static (kind, value) consumed
    events = []
    for i in range(1, n):
        while di < len(dyn) and dyn[di][2] <= i:
            s_, v, _, exp, kind, p = dyn[di]
            live_dyn.append([s_, v, exp, kind, p, True])
            di += 1
        live_dyn = [x for x in live_dyn if x[5] and F.dord[i] < x[2]]
        scored = F.t[i] >= score_from
        if scored:
            stats["bars"] += 1
        per_side = {1: [], -1: []}
        for name in STATIC:
            v = F.pools[name][i]
            if not np.isfinite(v):
                continue
            side = 1 if name.endswith("H") else -1
            key = (name, int(F.rstart[name][i]))
            if key in taken:
                continue
            per_side[side].append(("S", name, float(v), key))
        for x in live_dyn:
            per_side[x[0]].append(("D", x[3], x[1], x))
        cd = {1: F.pools["CDH"][i], -1: F.pools["CDL"][i]}
        for side in (1, -1):
            ext = F.h[i] if side == 1 else F.l[i]
            crossed, cand = [], per_side[side]
            for item in cand:
                v = item[2]
                if side * (ext - v) <= EPS:
                    continue
                if side * (F.o[i] - v) >= 0:            # opened at / beyond the level: a gap, consumed without an event
                    if scored:
                        stats["gapped"] += 1
                    consume(item, taken)
                    continue
                crossed.append(item)
            if not crossed:
                continue
            for item in crossed:
                consume(item, taken)
            if not scored:
                continue
            vals = [x[2] for x in crossed]
            ref = min(vals) if side == 1 else max(vals)
            outer = max(vals) if side == 1 else min(vals)
            kinds = sorted({level_kind(x[1]) for x in crossed}, key=lambda k: -RANK[k])
            names = sorted({x[1] for x in crossed})
            # live levels on the OTHER side at this bar (for room and class F); the current-day extreme counts
            other = [x[2] for x in per_side[-side] if (F.c[i] - x[2]) * side > EPS]
            if np.isfinite(cd[-side]) and (F.c[i] - cd[-side]) * side > EPS:
                other.append(float(cd[-side]))
            opp = (max(other) if side == 1 else min(other)) if other else math.nan
            beyond = [x[2] for x in per_side[side] if x not in crossed and side * (x[2] - ext) > EPS]
            nxt = (min(beyond) if side == 1 else max(beyond)) if beyond else math.nan
            ages = [i - (x[3][4] + SW_LR) if x[0] == "D" else i - int(F.rstart[x[1]][i]) for x in crossed]
            events.append({"tf": F.tf, "i": i, "side": side, "L": float(ref), "L_out": float(outer), "n_lv": len(crossed),
                           "kinds": kinds, "names": names, "primary": kinds[0], "ext": float(ext),
                           "disp": "SWEEP" if side * (F.c[i] - ref) < 0 else "BREAK", "opp": opp, "next_same": nxt,
                           "age": float(min(ages)), "sess": F.sess[i]})
    return events, stats


def consume(item, taken: set) -> None:
    if item[0] == "S":
        taken.add(item[3])
    else:
        item[3][5] = False


# ---------------- paths on the 15m grid (M5 refines) ----------------
def k_at(P: Path, t: int) -> int:
    """First 15m bar opening at or after t."""
    return int(np.searchsorted(P.t, t, side="left"))


def m5_span(P: Path, t0: int, t1: int) -> tuple[int, int]:
    if P.t5 is None:
        return 0, 0
    return int(np.searchsorted(P.t5, t0, side="left")), int(np.searchsorted(P.t5, t1, side="left"))


def first_touch(P: Path, k0: int, k1: int, level: float, d: int, pre: tuple[int, int] | None = None) -> float:
    """Earliest time (s, the open of the bar that traded at / through `level` in direction d) over the M5 bars of the
    `pre` interval [t0, t1) and then the 15m bars k0..k1-1; a 15m touch is refined to its M5 sub-bar when M5 exists.
    inf if never."""
    if pre is not None and P.t5 is not None:
        a, b = m5_span(P, *pre)
        if b > a:
            x = P.h5[a:b] >= level if d == 1 else P.l5[a:b] <= level
            if x.any():
                return float(P.t5[a + int(np.argmax(x))])
    k1 = min(k1, len(P.t))
    if k1 <= k0:
        return math.inf
    x = P.h[k0:k1] >= level if d == 1 else P.l[k0:k1] <= level
    if not x.any():
        return math.inf
    k = k0 + int(np.argmax(x))
    if P.t5 is not None:
        a, b = m5_span(P, int(P.t[k]), int(P.t[k]) + 900)
        if b > a:
            y = P.h5[a:b] >= level if d == 1 else P.l5[a:b] <= level
            if y.any():
                return float(P.t5[a + int(np.argmax(y))])
    return float(P.t[k])


def touch_close(P: Path, tau: float) -> float:
    """Close time of the bar a touch belongs to: the M5 bar (5-minute resolution) when one opens at tau, else the 15m."""
    if not math.isfinite(tau):
        return math.inf
    if P.t5 is not None:
        a, b = m5_span(P, int(tau), int(tau) + 1)
        if b > a:
            return tau + 300
    return tau + 900


def resolve_m5(P: Path, k: int, d: int, stop: float, tgt: float) -> str | None:
    """Order stop and target inside 15m bar k with its M5 bars; None if no M5 or one M5 bar touches both."""
    if P.t5 is None:
        return None
    a, b = m5_span(P, int(P.t[k]), int(P.t[k]) + 900)
    for j in range(a, b):
        o, h, l = P.o5[j], P.h5[j], P.l5[j]
        if (o - stop) * d <= 0:
            return "SL"
        if (o - tgt) * d >= 0:
            return "TP"
        hs = (l <= stop) if d == 1 else (h >= stop)
        ht = (h >= tgt) if d == 1 else (l <= tgt)
        if hs and ht:
            return None
        if hs:
            return "SL"
        if ht:
            return "TP"
    return None


def race(P: Path, k0: int, d: int, e: float, stop: float, tgt: float, pre: tuple[int, int] | None = None,
         hold: int = HOLD_SEC // 900) -> tuple[str, float, float, bool]:
    """From the M5 bars of `pre` (an entry inside a 15m bar) then 15m bar k0 for `hold` bars: target vs stop. A gap
    through a level fills at the open; a 15m bar touching both is ordered by M5, else AMBIGUOUS (the stop). Time stop at
    the last bar's close. Returns (outcome, exit time, exit price, resolved_by_m5)."""
    if pre is not None and P.t5 is not None:
        a, b = m5_span(P, *pre)
        for j in range(a, b):
            o, h, l = P.o5[j], P.h5[j], P.l5[j]
            if (o - stop) * d <= 0:
                return "SL", float(P.t5[j]), o, False
            if (o - tgt) * d >= 0:
                return "TP", float(P.t5[j]), o, False
            hs = (l <= stop) if d == 1 else (h >= stop)
            ht = (h >= tgt) if d == 1 else (l <= tgt)
            if hs and ht:
                return "AMBIGUOUS", float(P.t5[j]), stop, False
            if hs:
                return "SL", float(P.t5[j]), stop, False
            if ht:
                return "TP", float(P.t5[j]), tgt, False
    n = len(P.c)
    last = min(k0 + hold, n) - 1
    for k in range(k0, min(k0 + hold, n)):
        o, h, l = P.o[k], P.h[k], P.l[k]
        if (o - stop) * d <= 0:
            return "SL", float(P.t[k]), o, False
        if (o - tgt) * d >= 0:
            return "TP", float(P.t[k]), o, False
        hs = (l <= stop) if d == 1 else (h >= stop)
        ht = (h >= tgt) if d == 1 else (l <= tgt)
        if hs and ht:
            r = resolve_m5(P, k, d, stop, tgt)
            if r is None:
                return "AMBIGUOUS", float(P.t[k]), stop, False
            return r, float(P.t[k]), stop if r == "SL" else tgt, True
        if hs:
            return "SL", float(P.t[k]), stop, False
        if ht:
            return "TP", float(P.t[k]), tgt, False
    if last < k0:
        return "NODATA", math.nan, math.nan, False
    if k0 + hold > n:
        return "OPEN", float(P.t[last]), P.c[last], False          # the data ends before the time stop
    return "TIMEOUT", float(P.t[last]), P.c[last], False


def excursions(P: Path, k0: int, nbar: int, d: int, e: float, s: float, pre: tuple[int, int] | None = None) -> tuple[float, float]:
    """MFE / MAE ($ at $4,000) in direction d from e over the `pre` M5 bars and 15m bars k0..k0+nbar-1."""
    hi, lo = -math.inf, math.inf
    if pre is not None and P.t5 is not None:
        a, b = m5_span(P, *pre)
        if b > a:
            hi, lo = max(hi, P.h5[a:b].max()), min(lo, P.l5[a:b].min())
    k1 = min(k0 + nbar, len(P.c))
    if k1 > k0:
        hi, lo = max(hi, P.h[k0:k1].max()), min(lo, P.l[k0:k1].min())
    if not math.isfinite(hi):
        return math.nan, math.nan
    fav = (hi - e) if d == 1 else (e - lo)
    adv = (e - lo) if d == 1 else (hi - e)
    return max(fav, 0.0) / s, max(adv, 0.0) / s


def de(mfe: float, mae: float) -> float:
    t = mfe + mae
    return mfe / t if t > 0 else math.nan


# ---------------- sequences after the crossing (all causal: each is known at the close it names) ----------------
def followups(F: Frame, ev: dict) -> dict:
    i, side, L, n = ev["i"], ev["side"], ev["L"], len(F.c)
    out = {"k11": None, "a12": None, "r13": None, "k_in": None, "m14": None, "undecided": False}
    if ev["disp"] == "SWEEP":
        out["k_in"] = i
    else:
        if i + 2 >= n:
            out["undecided"] = True
            return out
        back = [k for k in (i + 1, i + 2) if side * (F.c[k] - L) < 0]
        if back:
            out["k11"] = out["k_in"] = back[0]
        else:
            out["a12"] = a = i + 2
            for j in range(a + 1, min(a + LIMIT_BARS, n - 1) + 1):
                if (F.l[j] <= L) if side == 1 else (F.h[j] >= L):
                    out["r13"] = j
                    break
                if side * (F.c[j] - L) < 0:
                    break
    k_in = out["k_in"]
    if k_in is not None:
        piv = F.pl2 if side == 1 else F.ph2                   # the opposite swing the shift must close beyond
        for m in range(k_in, min(i + MSS_BARS, n - 1) + 1):
            ref = math.nan
            for q in range(m - 1, max(i - MSS_LOOK + MSS_LR, 0) - 1, -1):
                if np.isfinite(piv[q]):
                    ref = piv[q]
                    break
            if not np.isfinite(ref):
                lo_, hi_ = max(i - 5, 0), i
                ref = (F.l[lo_:hi_].min() if side == 1 else F.h[lo_:hi_].max()) if hi_ > lo_ else math.nan
            if np.isfinite(ref) and ((F.c[m] < ref) if side == 1 else (F.c[m] > ref)):
                out["m14"] = m
                break
    return out


def ext_since(F: Frame, side: int, a: int, b: int) -> float:
    return float(F.h[a:b + 1].max() if side == 1 else F.l[a:b + 1].min())


def orders(P: Path, F: Frame, ev: dict, fu: dict, m5piv: dict | None) -> list[dict]:
    """Every entry the registered methods place for one event (market or limit), before eligibility."""
    i, side, L, n = ev["i"], ev["side"], ev["L"], len(F.c)
    atr = F.atr[i]
    if not np.isfinite(atr) or atr <= 0:
        return []
    buf = SL_BUF * atr
    tc = lambda j: int(F.t[j]) + F.sec                         # noqa: E731
    out = []
    dA, dB = -side, side
    if ev["disp"] == "SWEEP":
        X = ev["ext"]
        out.append({"m": "A-IMM", "d": dA, "kind": "MKT", "t": tc(i), "px": F.c[i], "stop": X + side * buf, "j": i})
        if i + 1 < n and dA * (F.c[i + 1] - F.c[i]) > 0 and side * (F.c[i + 1] - L) < 0:
            out.append({"m": "A-CONF", "d": dA, "kind": "MKT", "t": tc(i + 1), "px": F.c[i + 1],
                        "stop": ext_since(F, side, i, i + 1) + side * buf, "j": i + 1})
        out.append({"m": "A-RETEST", "d": dA, "kind": "LIM", "t": tc(i), "px": L, "stop": X + side * buf, "j": i,
                    "valid": i + LIMIT_BARS})
        for j in range(i + 1, min(i + DISP_BARS, n - 1) + 1):
            if dA * (F.c[j] - F.o[j]) >= DISP_BODY * atr:
                out.append({"m": "A-DISP", "d": dA, "kind": "LIM", "t": tc(j), "px": (F.o[j] + F.c[j]) / 2.0,
                            "stop": ext_since(F, side, i, j) + side * buf, "j": j, "valid": j + DISP_BARS})
                break
        if m5piv is not None:
            o5 = m5_mss(P, ev, tc(i), buf, m5piv)
            if o5 is not None:
                out.append(o5)
    if fu["m14"] is not None:
        m = fu["m14"]
        out.append({"m": "A-MSS", "d": dA, "kind": "MKT", "t": tc(m), "px": F.c[m], "stop": ext_since(F, side, i, m) + side * buf,
                    "j": m})
    if ev["disp"] == "BREAK":
        opp = (lambda a, b: float(F.l[a:b + 1].min())) if side == 1 else (lambda a, b: float(F.h[a:b + 1].max()))
        out.append({"m": "B-CLOSE", "d": dB, "kind": "MKT", "t": tc(i), "px": F.c[i], "stop": opp(i, i) - side * buf, "j": i})
        for j in range(i, min(i + 2, n - 1) + 1):
            if not all(side * (F.c[k] - L) > 0 for k in range(i, j + 1)):
                break
            if dB * (F.c[j] - F.o[j]) >= DISP_BODY * atr:
                out.append({"m": "B-DISP", "d": dB, "kind": "LIM", "t": tc(j), "px": (F.o[j] + F.c[j]) / 2.0,
                            "stop": opp(j, j) - side * buf, "j": j, "valid": j + DISP_BARS})
                break
        a = fu["a12"]
        if a is not None:
            out.append({"m": "B-ACC", "d": dB, "kind": "MKT", "t": tc(a), "px": F.c[a], "stop": opp(i, a) - side * buf, "j": a})
            out.append({"m": "B-RETEST", "d": dB, "kind": "LIM", "t": tc(a), "px": L, "stop": opp(i, a) - side * buf, "j": a,
                        "valid": a + LIMIT_BARS, "cancel_back": True, "L": L})
    return out


def m5_pivots(P: Path) -> dict | None:
    """The most recent confirmed M5 swing high / low at or before each M5 bar (pivots 2 bars each side)."""
    if P.t5 is None or not len(P.t5):
        return None
    ph = pd.Series(ta.pivothigh(P.h5, M5_LR, M5_LR)).ffill().to_numpy(float)
    pl = pd.Series(ta.pivotlow(P.l5, M5_LR, M5_LR)).ffill().to_numpy(float)
    return {"ph": ph, "pl": pl}


def m5_mss(P: Path, ev: dict, t0: int, buf: float, piv: dict) -> dict | None:
    """A-M5MSS: within 60 minutes of the sweep close, the first M5 close beyond the most recent M5 swing in the trade
    direction (confirmed before that close); cancelled by an M5 close back beyond the level first."""
    side, L = ev["side"], ev["L"]
    a, b = m5_span(P, t0, t0 + M5_WIN)
    if b <= a:
        return None
    run = ev["ext"]
    ref = piv["pl"] if side == 1 else piv["ph"]
    for j in range(a, b):
        run = max(run, P.h5[j]) if side == 1 else min(run, P.l5[j])
        if side * (P.c5[j] - L) > 0:
            return None
        r = ref[j - 1] if j >= 1 else math.nan
        if np.isfinite(r) and ((P.c5[j] < r) if side == 1 else (P.c5[j] > r)):
            return {"m": "A-M5MSS", "d": -side, "kind": "MKT", "t": int(P.t5[j]) + 300, "px": P.c5[j], "stop": run + side * buf,
                    "j": None}
    return None


# ---------------- execution of one order: fill, eligibility, sizing, the three races ----------------
def lots_for(D: float, cost: float) -> float:
    return math.floor(RISK_USD / ((D + cost) * OZ) * 100.0 + 1e-9) / 100.0 if D + cost > 0 else 0.0


def execute(P: Path, F: Frame, od: dict) -> dict:
    """Fill (market at the decision close; limit when a later bar trades through, a gap at the open), then the stop vs
    +$10 / +$15 / +$20 races from the fill. Costs from the 15m bar that closes at the decision."""
    d, t_dec = od["d"], od["t"]
    kd = k_at(P, t_dec) - 1 if t_dec % 900 == 0 else k_at(P, t_dec - (t_dec % 900))
    kd = min(max(kd, 0), len(P.c) - 1)
    cost = float(P.cost[kd])
    row = {"m": od["m"], "d": d, "t_dec": int(t_dec), "kind": od["kind"], "status": None, "why": None}
    pre, fill_k, e = None, None, None
    if od["kind"] == "MKT":
        e = float(od["px"])
        if t_dec % 900:
            nxt = t_dec - (t_dec % 900) + 900
            pre, k0 = (t_dec, nxt), k_at(P, nxt)
        else:
            k0 = k_at(P, t_dec)
        t_fill = t_dec
    else:
        jv = min(od["valid"], len(F.c) - 1)
        k_end = k_at(P, int(F.t[jv]) + F.sec)
        k = k_at(P, t_dec)
        lim = float(od["px"])
        last_of = {int(F.end15[j]): j for j in range(od["j"] + 1, jv + 1)} if od.get("cancel_back") else {}
        while k < min(k_end, len(P.c)):
            if d == 1 and P.o[k] <= lim:
                e, fill_k = float(P.o[k]), k
            elif d == 1 and P.l[k] <= lim:
                e, fill_k = lim, k
            elif d == -1 and P.o[k] >= lim:
                e, fill_k = float(P.o[k]), k
            elif d == -1 and P.h[k] >= lim:
                e, fill_k = lim, k
            if fill_k is not None:
                break
            j = last_of.get(k)
            if j is not None and d * (F.c[j] - od["L"]) < 0:
                row.update(status="CANCELLED", why="close back inside before the fill")
                return row
            k += 1
        if fill_k is None:
            row.update(status="MISSED", why="limit not filled in time")
            return row
        t_fill = int(P.t[fill_k])
        k0 = fill_k + 1
    s = e / 4000.0
    stop = float(od["stop"])
    D = d * (e - stop) / s
    row.update(e=e, stop=stop, s=s, D=D, cost=cost, t_fill=int(t_fill))
    if not np.isfinite(D) or D <= 0:
        row.update(status="REJECTED", why="stop on the wrong side")
        return row
    lots = lots_for(D, cost)
    row["lots"] = lots
    reasons = []
    if lots < 0.01:
        reasons.append("size")
    if cost > COST_FRAC * D + EPS:
        reasons.append("cost")
    row["eligible"] = not reasons
    row["why"] = ",".join(reasons) or None
    # a limit filled inside a bar that also reaches the stop: the stop (conservative; the order inside the bar is unknown)
    fb_stop = fill_k is not None and ((P.l[fill_k] <= stop) if d == 1 else (P.h[fill_k] >= stop))
    for T in TP:
        tgt = e + d * T * s
        if fb_stop:
            out, tx, px, r5 = "SL", float(P.t[fill_k]), stop, False
        else:
            out, tx, px, r5 = race(P, k0, d, e, stop, tgt, pre)
        g = d * (px - e) / s if np.isfinite(px) else math.nan
        key = f"tp{int(T)}"
        row[key] = out
        row[key + "_m5"] = r5
        row[key + "_min"] = (touch_close(P, tx) - t_fill) / 60.0 if out == "TP" else math.nan
        row[key + "_r"] = (g - cost) / (D + cost) if np.isfinite(g) else math.nan
        row[key + "_exit"] = tx
        if key == "tp10":
            row["loss_usd"] = lots * (-g + cost) * OZ if out in ("SL", "AMBIGUOUS") and np.isfinite(g) else math.nan
    row["fill_bar_stop"] = bool(fb_stop)
    row["mfe"], row["mae"] = excursions(P, k0, HOLD_SEC // 900, d, e, s, pre)
    row["status"] = "FILLED"
    return row


# ---------------- per-event measurement ----------------
def fvg_against(i: int, d: int, e: float, reach: float, zones: tuple) -> int:
    """1 if an unfilled FVG of the opposing kind (formed in the last 500 bars, known at bar i) lies between e and
    e + d * reach."""
    ks, Z = zones
    a, b = int(np.searchsorted(ks, i - 500, side="left")), int(np.searchsorted(ks, i, side="right"))
    for (k, lo, hi, pol, filled) in Z[a:b]:
        if filled <= i or pol != -d:
            continue
        if (d == 1 and e < lo < e + reach) or (d == -1 and e - reach < hi < e):
            return 1
    return 0


def fvg_zones(F: Frame) -> tuple:
    """(bar formed, low, high, polarity, bar filled) for every 3-bar gap > 0.3 x ATR (the engine's rule)."""
    n, out = len(F.c), []
    for i in range(2, n):
        a = F.atr[i]
        if not np.isfinite(a):
            continue
        for pol, lo, hi in ((1, F.h[i - 2], F.l[i]), (-1, F.h[i], F.l[i - 2])):
            if hi - lo > 0.3 * a:
                fill = n
                for j in range(i + 1, min(i + 600, n)):
                    if (pol == 1 and F.l[j] <= lo) or (pol == -1 and F.h[j] >= hi):
                        fill = j
                        break
                out.append((i, float(lo), float(hi), pol, fill))
    return np.array([z[0] for z in out], np.int64), out


def tr_sign(up, dn, i) -> int:
    return 1 if up[i] else (-1 if dn[i] else 0)


def measure(P: Path, F: Frame, ev: dict, fu: dict, zones: tuple, ev_by_side_bar: dict) -> dict:
    """Before / during / after for one event, and its class."""
    i, side, L = ev["i"], ev["side"], ev["L"]
    p = i - 1
    a0 = F.atr[p] if np.isfinite(F.atr[p]) and F.atr[p] > 0 else F.atr[i]
    s = F.c[i] / 4000.0
    rng = max(F.h[i] - F.l[i], EPS)
    top = max(F.o[i], F.c[i]) if side == 1 else min(F.o[i], F.c[i])
    st = 1 if (F.e20[p] > F.e100[p] > F.e200[p]) else (-1 if F.e20[p] < F.e100[p] < F.e200[p] else 0)
    m = {
        "atr_usd": a0 / s, "b_dist": side * (L - F.c[p]) / a0, "b_atrr": F.atr[p] / F.atr100[p] if F.atr100[p] > 0 else math.nan,
        "b_comp": (F.h[max(0, i - 16):i].max() - F.l[max(0, i - 16):i].min()) / a0,
        "b_e20": (F.c[p] - F.e20[p]) / a0, "b_e100": (F.c[p] - F.e100[p]) / a0, "b_e200": (F.c[p] - F.e200[p]) / a0, "b_stack": st,
        "b_m30": tr_sign(F.m30_up, F.m30_dn, i), "b_h1": tr_sign(F.h1_up, F.h1_dn, i), "b_h4": tr_sign(F.h4_up, F.h4_dn, i),
        "b_twap": (F.c[p] - F.twap[p]) / a0, "b_body": abs(F.c[p] - F.o[p]) / max(F.h[p] - F.l[p], EPS),
        "b_mom": side * (F.c[p] - F.c[max(0, p - 4)]) / a0, "b_er": F.er20[p],
        "room_rev": abs(F.c[i] - ev["opp"]) / s if np.isfinite(ev["opp"]) else math.inf,
        "room_cont": abs(ev["next_same"] - F.c[i]) / s if np.isfinite(ev["next_same"]) else math.inf,
        "fvg_rev": fvg_against(i, -side, F.c[i], TP[0] * s, zones), "fvg_cont": fvg_against(i, side, F.c[i], TP[0] * s, zones),
        "two_sided": int(any(ev_by_side_bar.get((-side, j)) for j in range(i - 8, i))),
        "d_pen": side * (ev["ext"] - L) / a0, "pen_usd": side * (ev["ext"] - L) / s, "d_wick": max(side * (ev["ext"] - top), 0.0) / rng,
        "d_close": side * (F.c[i] - L) / a0, "d_body": abs(F.c[i] - F.o[i]) / a0, "d_range": (F.h[i] - F.l[i]) / a0,
        "d_disp": int(abs(F.c[i] - F.o[i]) >= DISP_BODY * a0),
        "regime": "TREND" if F.er20[p] >= 0.30 else ("RANGE" if F.er20[p] < 0.15 else "MIXED"),
        "vol": "HIGH" if m_ratio(F, p) >= 1.25 else ("LOW" if m_ratio(F, p) <= 0.80 else "NORMAL"),
    }
    # ---- after: from the event close, in the reversal direction (continuation = mirror) ----
    T0 = int(F.t[i]) + F.sec
    k0 = k_at(P, T0)
    e, dR = float(F.c[i]), -side
    for hz in HORIZONS:
        if hz == 5:
            f_, a_ = excursions(P, k0, 0, dR, e, s, (T0, T0 + 300)) if P.t5 is not None else (math.nan, math.nan)
        else:
            f_, a_ = excursions(P, k0, hz // 15, dR, e, s)
        m[f"mfe{hz}"], m[f"mae{hz}"], m[f"de{hz}"] = f_, a_, de(f_, a_)
    k1 = k0 + HOLD_SEC // 900
    m["truncated"] = int(k1 > len(P.c))
    t = {}
    for X in MOVES:
        for nm, dd in (("rev", dR), ("cont", side)):
            tau = first_touch(P, k0, k1, e + dd * X * s, dd)
            t[(nm, X)] = tau
            m[f"min_{nm}{int(X)}"] = (touch_close(P, tau) - T0) / 60.0 if math.isfinite(tau) else math.nan
    rdir = side if ev["disp"] == "SWEEP" else -side
    m["retest240"] = int(math.isfinite(first_touch(P, k0, k0 + 16, L, rdir)))
    lo_, hi_ = max(i - ORIGIN_BARS, 0), i
    origin = (F.l[lo_:hi_].min() if side == 1 else F.h[lo_:hi_].max()) if hi_ > lo_ else math.nan
    m["origin240"] = int(np.isfinite(origin) and math.isfinite(first_touch(P, k0, k0 + 16, origin, -side)))
    m["mss8"] = int(fu["m14"] is not None)
    m["fail3"] = int(fu["k11"] is not None)
    tr10, tc10 = t[("rev", 10.0)], t[("cont", 10.0)]
    m["first10"] = "NONE" if not (math.isfinite(tr10) or math.isfinite(tc10)) else (
        "TIE" if tr10 == tc10 else ("REV" if tr10 < tc10 else "CONT"))
    m["cls"], m["cls_sub"] = classify(P, F, ev, fu, k0, k1, tr10, tc10)
    return m


def m_ratio(F: Frame, p: int) -> float:
    return F.atr[p] / F.atr100[p] if F.atr100[p] > 0 else math.nan


def classify(P: Path, F: Frame, ev: dict, fu: dict, k0: int, k1: int, tr: float, tc: float) -> tuple[str, str]:
    """Classes A-G (registration 'classes' and amendment A1). Times are touch times (M5-refined where possible); a TF
    close counts at the end of its bar."""
    i, side, L = ev["i"], ev["side"], ev["L"]
    trunc = k1 > len(P.c)
    first10 = min(tr, tc)
    if math.isfinite(tr) and tr == tc:
        return "G", "tie at +$10"
    to = first_touch(P, k0, k1, ev["opp"], -side) if np.isfinite(ev["opp"]) else math.inf
    if ev["disp"] == "SWEEP":
        tx = first_touch(P, k0, k1, ev["ext"] + side * 0.01, side)
        if math.isfinite(to) and math.isfinite(tx) and max(to, tx) < first10:
            return "F", "both sides taken"
        if any(math.isfinite(a) and a == b for a, b in ((tr, tx), (to, first10), (tx, first10))):
            return "G", "tie"
        if tr < tx:
            return "A", "A1"
        if tx < tr:
            if tc < tr:
                return "D", "D"
            if math.isfinite(tr):
                return "A", "A2"
        return ("G", "data end") if trunc else ("E", "E")
    # BREAK
    n = len(F.c)
    tb, jb = math.inf, None
    t_lim = float(P.t[min(k1, len(P.t)) - 1]) + 900.0
    for j in range(i + 1, n):
        if int(F.t[j]) + F.sec > t_lim:
            break
        if side * (F.c[j] - L) < 0:
            tb, jb = float(int(F.t[j]) + F.sec - 1), j
            break
    if math.isfinite(to) and math.isfinite(tb) and max(to, tb) < first10:
        return "F", "both sides taken"
    if tc < tb:
        return "B", "B"
    if tb < tc:
        xb = ext_since(F, side, i, jb)
        kb = k_at(P, int(F.t[jb]) + F.sec)
        txb = first_touch(P, kb, k1, xb + side * 0.01, side)
        if tr < min(txb, tc):
            return "C", "C"
        return ("G", "data end") if trunc and not math.isfinite(tc) else ("E", "E")
    return ("G", "data end") if trunc else ("E", "E")


# ---------------- event types, model features, one build per timeframe ----------------
def types_of(ev: dict, fu: dict, F: Frame) -> list[int]:
    i, k = ev["i"], set(ev["names"])
    sw = ev["disp"] == "SWEEP"
    out = []
    if sw:
        out.append(1 if ev["side"] == 1 else 2)
    if "PDH" in k:
        out.append(3)
    if "PDL" in k:
        out.append(4)
    if k & {"PSH", "PSL"}:
        out.append(5)
    if k & {"ASH", "ASL"}:
        out.append(6)
    if sw and F.in_lon[i]:
        out.append(7)
    if sw and F.in_ny[i]:
        out.append(8)
    if k & {"EQH", "EQL"}:
        out.append(9)
    if sw and k & {"SWH", "SWL"}:
        out.append(10)
    if fu["k11"] is not None:
        out.append(11)
    if fu["a12"] is not None:
        out.append(12)
    if fu["r13"] is not None:
        out.append(13)
    if fu["m14"] is not None:
        out.append(14)
    return out


FEATURES = ("g_logD", "g_costD", "g_geo", "lv_pw", "lv_pd", "lv_ps", "lv_sess", "lv_eq", "lv_n", "lv_age",
            "b_dist", "b_comp", "b_atrr", "b_e20", "b_e100", "b_e200", "b_stack", "b_m30", "b_h1", "b_h4", "b_twap", "b_body",
            "b_mom", "b_room", "b_fvg", "b_two", "d_pen", "d_wick", "d_close", "d_body", "d_range", "w_bars", "w_de",
            "s_asia", "s_ldo", "s_ldc", "s_nyo", "s_ovl", "s_nyc")
GROUPS = {"geometry": ("g_logD", "g_costD", "g_geo"), "level": ("lv_pw", "lv_pd", "lv_ps", "lv_sess", "lv_eq", "lv_n", "lv_age"),
          "trend": ("b_e20", "b_e100", "b_e200", "b_stack", "b_m30", "b_h1", "b_h4"), "volatility": ("b_comp", "b_atrr"),
          "location": ("b_dist", "b_twap", "b_room", "b_fvg", "b_two"), "momentum": ("b_body", "b_mom"),
          "during": ("d_pen", "d_wick", "d_close", "d_body", "d_range"), "waiting": ("w_bars", "w_de"),
          "session": ("s_asia", "s_ldo", "s_ldc", "s_nyo", "s_ovl", "s_nyc")}
GEOMETRY = GROUPS["geometry"]


def features(P: Path, F: Frame, ev: dict, row: dict) -> dict:
    d, D, cost = row["d"], row["D"], row["cost"]
    pg = D / (D + TP[0])
    A = row["m"].startswith("A")
    prim = ev["primary"]
    T0 = int(F.t[ev["i"]]) + F.sec
    k0, kd = k_at(P, T0), k_at(P, row["t_dec"])
    if kd > k0:
        f_, a_ = excursions(P, k0, kd - k0, d, ev["c"], ev["c"] / 4000.0)
        wde = de(f_, a_)
    else:
        wde = math.nan
    room = ev["room_rev"] if A else ev["room_cont"]
    return {"g_logD": math.log(D), "g_costD": cost / D, "g_geo": math.log(pg / (1 - pg)),
            "lv_pw": int(prim == "PW"), "lv_pd": int(prim == "PD"), "lv_ps": int(prim == "PS"), "lv_sess": int(prim in ("AS", "LO", "NY")),
            "lv_eq": int(prim == "EQ"), "lv_n": ev["n_lv"], "lv_age": math.log1p(max(ev["age"], 0.0)),
            "b_dist": ev["b_dist"], "b_comp": ev["b_comp"], "b_atrr": ev["b_atrr"], "b_e20": d * ev["b_e20"], "b_e100": d * ev["b_e100"],
            "b_e200": d * ev["b_e200"], "b_stack": d * ev["b_stack"], "b_m30": d * ev["b_m30"], "b_h1": d * ev["b_h1"], "b_h4": d * ev["b_h4"],
            "b_twap": d * ev["b_twap"], "b_body": ev["b_body"], "b_mom": ev["b_mom"], "b_room": min(room, 50.0) / 10.0,
            "b_fvg": ev["fvg_rev"] if A else ev["fvg_cont"], "b_two": ev["two_sided"], "d_pen": ev["d_pen"], "d_wick": ev["d_wick"],
            "d_close": ev["d_close"], "d_body": ev["d_body"], "d_range": ev["d_range"], "w_bars": (row["t_dec"] - T0) / F.sec,
            "w_de": 0.5 if not np.isfinite(wde) else wde,
            "s_asia": int(ev["sess"] == "ASIA"), "s_ldo": int(ev["sess"] == "LDN_OPEN"), "s_ldc": int(ev["sess"] == "LDN_CONT"),
            "s_nyo": int(ev["sess"] == "NY_OPEN"), "s_ovl": int(ev["sess"] == "OVERLAP"), "s_nyc": int(ev["sess"] == "NY_CONT")}


def build(P: Path, F: Frame, score_from: int, m5piv: dict | None, log=print) -> tuple[list[dict], list[dict], dict]:
    """Events (with measurements and class) and every order (with fill, eligibility and the three races)."""
    events, st = find_events(F, score_from)
    zones = fvg_zones(F)
    by = {(e["side"], e["i"]): True for e in events}
    trades = []
    for ev in events:
        i, side = ev["i"], ev["side"]
        fu = followups(F, ev)
        ev["t"] = int(F.t[i]) + F.sec
        ev["c"] = float(F.c[i])
        ev["id"] = f"W3-{F.tf}-{ev['t']}-{'BS' if side == 1 else 'SS'}"
        ev["types"] = types_of(ev, fu, F)
        ev["undecided"] = fu["undecided"]
        ev.update(measure(P, F, ev, fu, zones, by))
        for od in orders(P, F, ev, fu, m5piv):
            row = execute(P, F, od)
            row.update(ev_id=ev["id"], tf=F.tf, sess=ev["sess"], regime=ev["regime"], vol=ev["vol"], primary=ev["primary"],
                       types=ev["types"], t_ev=ev["t"])
            if row["status"] == "FILLED":
                row.update(features(P, F, ev, row))
            trades.append(row)
    log(f"{F.tf}: {len(events)} events, {len(trades)} orders, gapped {st['gapped']}")
    return events, trades, st


def one_position(rows: list[dict]) -> list[dict]:
    """One position at a time per variant (method x timeframe): busy until the +$10 race's exit."""
    out, busy = [], {}
    for r in sorted(rows, key=lambda x: (x["t_fill"], x["ev_id"])):
        key = (r["m"], r["tf"])
        if r["t_fill"] < busy.get(key, -1):
            continue
        out.append(r)
        ex = r.get("tp10_exit")
        busy[key] = ex if ex is not None and np.isfinite(ex) else r["t_fill"]
    return out


# ---------------- fast race (equivalent to race() when there is no M5 pre-segment; tested) ----------------
def race_fast(P: Path, k0: int, d: int, e: float, stop: float, tgt: float, hold: int = HOLD_SEC // 900) -> tuple[str, float, float, bool]:
    n = len(P.c)
    k1 = min(k0 + hold, n)
    if k1 <= k0:
        return "NODATA", math.nan, math.nan, False
    o, h, l = P.o[k0:k1], P.h[k0:k1], P.l[k0:k1]
    gs, gt = (o - stop) * d <= 0, (o - tgt) * d >= 0
    hs = (l <= stop) if d == 1 else (h >= stop)
    ht = (h >= tgt) if d == 1 else (l <= tgt)
    S, T = gs | hs, gt | ht
    js = int(np.argmax(S)) if S.any() else 10 ** 9
    jt = int(np.argmax(T)) if T.any() else 10 ** 9
    if js == jt == 10 ** 9:
        last = k1 - 1
        return ("OPEN" if k0 + hold > n else "TIMEOUT"), float(P.t[last]), float(P.c[last]), False
    j = min(js, jt)
    k = k0 + j
    if gs[j]:
        return "SL", float(P.t[k]), float(o[j]), False
    if gt[j]:
        return "TP", float(P.t[k]), float(o[j]), False
    if js == jt:
        r = resolve_m5(P, k, d, stop, tgt)
        if r is None:
            return "AMBIGUOUS", float(P.t[k]), stop, False
        return r, float(P.t[k]), stop if r == "SL" else tgt, True
    return ("SL", float(P.t[k]), stop, False) if js < jt else ("TP", float(P.t[k]), tgt, False)


# ---------------- statistics ----------------
def rate(k: int, n: int) -> dict:
    return {"k": int(k), "n": int(n), "rate": (k / n) if n else math.nan, "wilson95": list(H.wilson(int(k), int(n)))}


def boot_mean(r: np.ndarray, day: np.ndarray, seed: int = SEED, B: int = BOOT) -> list[float]:
    """Day-clustered bootstrap 95% interval of the mean."""
    if len(r) < 3:
        return [math.nan, math.nan]
    u, inv = np.unique(day, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=r), np.bincount(inv)
    rng = H.seeded_rng(seed)
    pick = rng.integers(0, len(u), size=(B, len(u)))
    m = sums[pick].sum(axis=1) / cnts[pick].sum(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def max_dd(x: np.ndarray) -> float:
    if not len(x):
        return 0.0
    c = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], c]))[1:] - c).max())


def two_prop_p(k1: int, n1: int, k0: int, n0: int) -> tuple[float, float]:
    if not n1 or not n0:
        return math.nan, math.nan
    p1, p0 = k1 / n1, k0 / n0
    pp = (k1 + k0) / (n1 + n0)
    if not 0 < pp < 1:
        return math.nan, math.nan
    z = (p1 - p0) / math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
    return float(z), float(1 - H._norm_cdf(z))


def decided(r: dict, key: str = "tp10") -> bool:
    return r.get(key) in ("TP", "SL", "AMBIGUOUS", "TIMEOUT")


def summarize(rows: list[dict], rnd: dict | None = None) -> dict:
    rows = [r for r in rows if decided(r)]
    o = {"n": len(rows)}
    if not rows:
        return o
    day = np.array([r["t_fill"] // 86400 for r in rows])
    order = np.argsort([r["t_fill"] for r in rows], kind="stable")
    for T in TP:
        key = f"tp{int(T)}"
        out = np.array([r[key] for r in rows], object)
        rr = np.array([r[key + "_r"] for r in rows], float)
        D = np.array([r["D"] for r in rows])
        c = np.array([r["cost"] for r in rows])
        tmin = [r[key + "_min"] for r in rows if r[key] == "TP"]
        x = {"tp_first": rate((out == "TP").sum(), len(rows)), "sl_first": rate((out == "SL").sum(), len(rows)),
             "ambiguous": int((out == "AMBIGUOUS").sum()), "timeout": int((out == "TIMEOUT").sum()),
             "m5_resolved": int(sum(bool(r[key + "_m5"]) for r in rows)),
             "mean_net_r": float(np.nanmean(rr)), "mean_net_r_boot95": boot_mean(np.nan_to_num(rr), day),
             "usd_per_trade": float(np.nanmean(rr) * RISK_USD),
             "profit_factor": float(rr[rr > 0].sum() / -rr[rr < 0].sum()) if (rr < 0).any() else math.nan,
             "max_drawdown_usd": max_dd(np.nan_to_num(rr[order]) * RISK_USD),
             "geometric_baseline": float(np.mean(D / (D + T))), "break_even": float(np.mean((D + c) / (T + D))),
             "median_min_to_tp": float(np.median(tmin)) if tmin else math.nan}
        if rnd is not None and key in rnd:
            k0, n0 = rnd[key]["k"], rnd[key]["n"]
            z, p = two_prop_p(int((out == "TP").sum()), len(rows), k0, n0)
            x["random"] = {"tp_first": rate(k0, n0), "mean_net_r": rnd[key]["mean_r"], "z": z, "p_one_sided": p}
        o[key] = x
    o["median_D"] = float(np.median([r["D"] for r in rows]))
    o["mean_cost"] = float(np.mean([r["cost"] for r in rows]))
    o["median_lots"] = float(np.median([r["lots"] for r in rows]))
    o["mfe_median"] = float(np.nanmedian([r["mfe"] for r in rows]))
    o["mae_median"] = float(np.nanmedian([r["mae"] for r in rows]))
    loss = np.array([r["loss_usd"] for r in rows if np.isfinite(r.get("loss_usd", math.nan))])
    o["realised_loss_usd"] = {"n": int(len(loss)), "max": float(loss.max()) if len(loss) else math.nan,
                              "over_650": int((loss > RISK_USD + 1e-6).sum()), "mean": float(loss.mean()) if len(loss) else math.nan}
    o["weeks"] = float((max(r["t_fill"] for r in rows) - min(r["t_fill"] for r in rows)) / 604800.0) if len(rows) > 1 else math.nan
    return o


def matched_random(P: Path, rows: list[dict], lo_k: int, hi_k: int, seed: int = SEED, k: int = RND_K) -> dict:
    """For each trade: k random 15m closes in [lo_k, hi_k) with the same direction, session bucket and ATR14 tercile, the
    same scaled stop distance and targets, the same race and costs."""
    rng = H.seeded_rng(seed)
    hi_k = min(hi_k, len(P.c) - 2)
    idx = np.arange(lo_k, hi_k)
    a = P.atr[idx]
    q1, q2 = np.nanpercentile(a, [100 / 3, 200 / 3])
    terc = np.where(P.atr < q1, 0, np.where(P.atr < q2, 1, 2))
    pools = {}
    for b in idx:
        pools.setdefault((P.sess[b], int(terc[b])), []).append(b)
    pools = {kk: np.array(v) for kk, v in pools.items()}
    res = {f"tp{int(T)}": {"k": 0, "n": 0, "r": []} for T in TP}
    for r in rows:
        if not decided(r):
            continue
        kd = min(max(k_at(P, r["t_dec"]) - 1, 0), len(P.c) - 1)
        pool = pools.get((P.sess[kd], int(terc[kd])))
        if pool is None or not len(pool):
            continue
        for b in rng.choice(pool, size=k, replace=True):
            e = float(P.c[b])
            s = e / 4000.0
            d = r["d"]
            stop = e - d * r["D"] * s
            cost = float(P.cost[b])
            for T in TP:
                out, _, px, _ = race_fast(P, int(b) + 1, d, e, stop, e + d * T * s)
                if out not in ("TP", "SL", "AMBIGUOUS", "TIMEOUT"):
                    continue
                key = f"tp{int(T)}"
                res[key]["n"] += 1
                res[key]["k"] += int(out == "TP")
                res[key]["r"].append((d * (px - e) / s - cost) / (r["D"] + cost))
    return {kk: {"k": v["k"], "n": v["n"], "mean_r": float(np.mean(v["r"])) if v["r"] else math.nan} for kk, v in res.items()}


# ---------------- logistic model (L2, C = 1, IRLS; no other hyper-parameter) ----------------
def logit_fit(X: np.ndarray, y: np.ndarray, C: float = 1.0, iters: int = 50) -> np.ndarray:
    n, p = X.shape
    Z = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(p + 1)
    lam = np.full(p + 1, 1.0 / C)
    lam[0] = 0.0
    for _ in range(iters):
        z = np.clip(Z @ w, -30, 30)
        mu = 1 / (1 + np.exp(-z))
        g = Z.T @ (mu - y) + lam * w
        Hm = (Z * (mu * (1 - mu))[:, None]).T @ Z + np.diag(lam)
        step = np.linalg.solve(Hm + 1e-9 * np.eye(p + 1), g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def logit_pred(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(w[0] + X @ w[1:], -30, 30)))


def standardize(Xtr: np.ndarray, Xte: np.ndarray):
    mu, sd = np.nanmean(Xtr, axis=0), np.nanstd(Xtr, axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    f = lambda X: np.nan_to_num((X - mu) / sd)                 # noqa: E731
    return f(Xtr), f(Xte), mu, sd


def auc(p: np.ndarray, y: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return math.nan
    rk = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((rk[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def matrix(rows: list[dict], cols) -> np.ndarray:
    return np.array([[float(r[c]) for c in cols] for r in rows], float)


def label(rows: list[dict], key: str = "tp10") -> np.ndarray:
    return np.array([1.0 if r[key] == "TP" else 0.0 for r in rows])


def walk_forward(rows: list[dict], cols, t_lo: int, t_hi: int, folds: int = 6) -> np.ndarray:
    """Out-of-fold p for folds 2..k (NaN in fold 1): each fold predicted by a model trained on earlier trades whose
    24 h outcome window ends before the fold starts (purge)."""
    t = np.array([r["t_fill"] for r in rows])
    edges = np.linspace(t_lo, t_hi, folds + 1)
    X, y = matrix(rows, cols), label(rows)
    p = np.full(len(rows), np.nan)
    for f in range(1, folds):
        te = (t >= edges[f]) & (t < edges[f + 1])
        tr = t + HOLD_SEC < edges[f]
        if te.sum() == 0 or tr.sum() < 30 or len(np.unique(y[tr])) < 2:
            continue
        Xtr, Xte, _, _ = standardize(X[tr], X[te])
        p[te] = logit_pred(logit_fit(Xtr, y[tr]), Xte)
    return p


def lr_test(rows: list[dict], feat: str) -> float:
    """p-value of adding one feature to the geometry-only logistic model (likelihood ratio, chi-square 1 df)."""
    y = label(rows)
    if len(rows) < 50 or len(np.unique(y)) < 2:
        return math.nan
    ll = []
    for cols in (GEOMETRY, GEOMETRY + (feat,)):
        X, _, _, _ = standardize(matrix(rows, cols), matrix(rows[:1], cols))
        w = logit_fit(X, y, C=1e6)
        pr = np.clip(logit_pred(w, X), 1e-12, 1 - 1e-12)
        ll.append(float((y * np.log(pr) + (1 - y) * np.log(1 - pr)).sum()))
    stat = max(2 * (ll[1] - ll[0]), 0.0)
    return float(math.erfc(math.sqrt(stat / 2)))            # chi-square(1) survival = erfc(sqrt(x / 2))


# ---------------- data, partition gate, one run ----------------
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RES_DIR = os.path.join(ROOT, "research", "results")
FREEZE_PATH = os.path.join(H.REG_DIR, f"{FREEZE_ID}.json")


def code_sha() -> str:
    return hashlib.sha256(open(__file__, "rb").read()).hexdigest()


def gate(part: str, res_dir: str = RES_DIR, freeze_path: str = FREEZE_PATH) -> None:
    """The registration's order: validation only after the freeze (same code) and only once; holdout only after a
    validation PASS and only once."""
    done = lambda p: [f for f in os.listdir(res_dir) if f.startswith(f"b31b_w3_{p}_")] if os.path.isdir(res_dir) else []  # noqa: E731
    if part == "validation":
        if not os.path.exists(freeze_path):
            raise H.SealedPartition("validation is sealed: the freeze amendment is not committed")
        fz = json.load(open(freeze_path))
        if fz.get("code_sha256") != code_sha():
            raise H.SealedPartition("validation is sealed: the code differs from the frozen code")
        if done("validation"):
            raise H.SealedPartition("validation was already opened once")
    if part == "holdout":
        v = done("validation")
        if not v:
            raise H.SealedPartition("holdout is sealed: no validation result")
        res = json.load(open(os.path.join(res_dir, sorted(v)[-1])))
        if not any(c.get("verdict") == "PASS" for c in res.get("candidates", [])):
            raise H.SealedPartition("holdout is sealed: no candidate passed validation")
        if done("holdout"):
            raise H.SealedPartition("holdout was already opened once")


def load(rd: str, part: str, m5_rd: str | None = None):
    m15, h1 = history.load(rd, "XAU/USD", "15min"), history.load(rd, "XAU/USD", "1h")
    m5 = history.load(m5_rd or rd, "XAU/USD", "5min")
    if part == "recent":
        lo = H.HOLD[1]
        cut = lambda x: None if x is None else x[x.index >= lo]          # noqa: E731
        m15, h1, m5 = cut(m15), cut(h1), cut(m5)
    else:
        reg = REG if part in SEALED else None
        m15, h1 = H.partition(m15, part, reg), H.partition(h1, part, reg)
        m5 = H.partition(m5, part, reg) if m5 is not None else None
    if m5 is not None and not len(m5):
        m5 = None
    return m15, h1, m5, int((m15.index[0] + pd.Timedelta(days=WARM_DAYS)).timestamp())


def frames(m15: pd.DataFrame, h1: pd.DataFrame, m5: pd.DataFrame | None):
    m30, incomplete = make_m30(m15)
    P = make_path(m15, m5)
    F15 = make_frame(m15, "M15", h1, m30, np.arange(len(m15)))
    end30 = np.searchsorted(P.t, ta.epoch_s(m30.index).astype(np.int64) + 900, side="left")
    F30 = make_frame(m30, "M30", h1, None, end30)
    return P, F15, F30, incomplete


def m5_coverage(P: Path, lo: int) -> float:
    if P.t5 is None:
        return 0.0
    k = np.arange(np.searchsorted(P.t, lo), len(P.t))
    if not len(k):
        return math.nan
    a = np.searchsorted(P.t5, P.t[k])
    b = np.searchsorted(P.t5, P.t[k] + 900)
    return float(((b - a) >= 3).mean())


def run_part(rd: str, part: str, m5_rd: str | None = None, log=print) -> dict:
    if part in SEALED:
        gate(part)
    m15, h1, m5, score_from = load(rd, part, m5_rd)
    P, F15, F30, incomplete = frames(m15, h1, m5)
    piv = m5_pivots(P)
    out = {"part": part, "score_from": score_from, "end": int(P.t[-1]) + 900, "m30_incomplete_pairs": incomplete,
           "m5_coverage": m5_coverage(P, score_from), "bars15": int((P.t >= score_from).sum()), "data_hash": H.data_hash(m15)}
    ev_all, tr_all, gapped = [], [], {}
    for F in (F15, F30):
        ev, tr, st = build(P, F, score_from, piv, log)
        ev_all += ev
        tr_all += tr
        gapped[F.tf] = st["gapped"]
    out["gapped"] = gapped
    return {"meta": out, "events": ev_all, "trades": tr_all, "P": P}


# ---------------- descriptive analysis (Deliverables A, B, E) ----------------
def q(x, p):
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    return float(np.percentile(x, p)) if len(x) else math.nan


def ev_after(evs: list[dict]) -> dict:
    """The path after the event (reversal direction; continuation = mirror)."""
    o = {"n": len(evs)}
    if not evs:
        return o
    for hz in HORIZONS:
        o[f"h{hz}"] = {"mfe_med": q([e[f"mfe{hz}"] for e in evs], 50), "mae_med": q([e[f"mae{hz}"] for e in evs], 50),
                       "de_med": q([e[f"de{hz}"] for e in evs], 50)}
    for X in MOVES:
        for nm in ("rev", "cont"):
            v = [e[f"min_{nm}{int(X)}"] for e in evs]
            k = sum(1 for x in v if np.isfinite(x))
            o[f"{nm}{int(X)}"] = {**rate(k, len(evs)), "median_min": q(v, 50)}
    fc = pd.Series([e["first10"] for e in evs]).value_counts().to_dict()
    o["first10"] = {k: int(v) for k, v in fc.items()}
    for nm in ("retest240", "origin240", "mss8", "fail3"):
        o[nm] = rate(sum(e[nm] for e in evs), len(evs))
    return o


def mw_p(a: list, b: list) -> float:
    """Two-sided Mann-Whitney U p-value (normal approximation, ties averaged)."""
    a = np.asarray([x for x in a if np.isfinite(x)], float)
    b = np.asarray([x for x in b if np.isfinite(x)], float)
    if len(a) < 10 or len(b) < 10:
        return math.nan
    rk = pd.Series(np.concatenate([a, b])).rank().to_numpy()
    u = rk[:len(a)].sum() - len(a) * (len(a) + 1) / 2
    mu, sd = len(a) * len(b) / 2, math.sqrt(len(a) * len(b) * (len(a) + len(b) + 1) / 12)
    z = (u - mu) / sd if sd > 0 else 0.0
    return float(2 * (1 - H._norm_cdf(abs(z))))


EV_FEATS = ("b_dist", "b_atrr", "b_comp", "b_e20", "b_e200", "b_stack", "b_m30", "b_h1", "b_h4", "b_twap", "b_body", "b_mom",
            "room_rev", "room_cont", "fvg_rev", "fvg_cont", "two_sided", "d_pen", "pen_usd", "d_wick", "d_close", "d_body",
            "d_range", "d_disp", "n_lv", "age", "atr_usd")


def class_contrast(evs: list[dict], good: str, bad: tuple) -> dict:
    """Median of each before / during measure for the successful class vs the others, with Mann-Whitney p and BH."""
    g = [e for e in evs if e["cls"] == good]
    b = [e for e in evs if e["cls"] in bad]
    rows, ps = {}, []
    for f in EV_FEATS:
        va = [min(e[f], 100.0) if f.startswith("room") else e[f] for e in g]
        vb = [min(e[f], 100.0) if f.startswith("room") else e[f] for e in b]
        p = mw_p(va, vb)
        rows[f] = {"median_" + good: q(va, 50), "median_other": q(vb, 50), "p": p}
        ps.append(p if np.isfinite(p) else 1.0)
    keep = H.benjamini_hochberg(ps, 0.10)
    for f, k in zip(EV_FEATS, keep):
        rows[f]["bh10"] = bool(k)
    return {"n_" + good: len(g), "n_other": len(b), "features": rows}


def news_flags(evs: list[dict]) -> None:
    """Development only: within 60 minutes after a CPI / NFP / FOMC release (b8_news.DATES)."""
    from . import b8_news as B8
    rel = sorted(int(B8.release_utc(k, d).timestamp()) for k in B8.DATES for d in B8.DATES[k])
    rel = np.array(rel)
    for e in evs:
        t_open = e["t"] - TFS[e["tf"]]
        j = np.searchsorted(rel, t_open, side="right") - 1
        e["news"] = int(j >= 0 and t_open - rel[j] < 3600)


def describe(res: dict) -> dict:
    meta, evs = res["meta"], res["events"]
    weeks = (meta["end"] - meta["score_from"]) / 604800.0
    out = {"meta": {**meta, "weeks": weeks}}
    if meta["part"] == "development":
        news_flags(evs)
    for tf in TFS:
        E = [e for e in evs if e["tf"] == tf]
        T = {}
        for ty in range(1, 15):
            sub = [e for e in E if ty in e["types"]]
            cls = pd.Series([e["cls"] for e in sub]).value_counts().to_dict()
            T[ty] = {"n": len(sub), "per_week": len(sub) / weeks, "classes": {k: int(v) for k, v in cls.items()},
                     "after": ev_after(sub)}
        by_disp = {}
        for disp in ("SWEEP", "BREAK"):
            sub = [e for e in E if e["disp"] == disp]
            by_disp[disp] = {"n": len(sub), "classes": {k: int(v) for k, v in pd.Series([e["cls"] for e in sub]).value_counts().items()},
                             "by_class": {c: ev_after([e for e in sub if e["cls"] == c]) for c in "ABCDEFG"},
                             "by_session": {ss: ev_after([e for e in sub if e["sess"] == ss]) for ss in SESS},
                             "overlap_union": ev_after([e for e in sub if e["sess"] in ("NY_OPEN", "OVERLAP")]),
                             "by_regime": {rg: ev_after([e for e in sub if e["regime"] == rg]) for rg in ("TREND", "MIXED", "RANGE")},
                             "by_vol": {v: ev_after([e for e in sub if e["vol"] == v]) for v in ("LOW", "NORMAL", "HIGH")},
                             "by_primary": {k: ev_after([e for e in sub if e["primary"] == k]) for k in RANK}}
            if meta["part"] == "development":
                by_disp[disp]["by_news"] = {str(v): ev_after([e for e in sub if e.get("news") == v]) for v in (0, 1)}
        out[tf] = {"events": len(E), "per_week": len(E) / weeks, "types": T, "disp": by_disp,
                   "sweep_A_vs_DE": class_contrast([e for e in E if e["disp"] == "SWEEP"], "A", ("D", "E")),
                   "break_B_vs_CE": class_contrast([e for e in E if e["disp"] == "BREAK"], "B", ("C", "E")),
                   "break_C_vs_BE": class_contrast([e for e in E if e["disp"] == "BREAK"], "C", ("B", "E"))}
    return out


def variants(res: dict) -> dict:
    """Per method x timeframe: the order funnel and every eligible, one-position trade (decided)."""
    out = {}
    for tf in TFS:
        for m in A_METHODS + B_METHODS:
            rows = [r for r in res["trades"] if r["tf"] == tf and r["m"] == m]
            fun = pd.Series([r["status"] if r["status"] != "FILLED" else ("ELIGIBLE" if r["eligible"] else "REJECTED:" + r["why"])
                             for r in rows]).value_counts().to_dict()
            rej = pd.Series([r["why"] for r in rows if r["status"] == "REJECTED"]).value_counts().to_dict()
            elig = [r for r in rows if r["status"] == "FILLED" and r["eligible"] and decided(r)]
            out[(m, tf)] = {"orders": len(rows), "funnel": {k: int(v) for k, v in fun.items()},
                            "rejected_before_fill": {k: int(v) for k, v in rej.items()}, "eligible": elig, "kept": one_position(elig)}
    return out


FILTERS = {"cost<=15%D": None, "room>=10": lambda r: r["b_room"] * 10 >= TP[0] - EPS, "h1_agrees": lambda r: r["b_h1"] > 0,
           "h4_agrees": lambda r: r["b_h4"] > 0, "london_or_ny": lambda r: r["sess"] not in ("ASIA", "OFF"),
           "no_fvg_against": lambda r: r["b_fvg"] == 0, "displacement_bar": lambda r: r["d_body"] >= DISP_BODY}


def filter_table(P: Path, rows: list[dict], lo_k: int, hi_k: int) -> dict:
    """Q8: each filter alone on a variant's trades: kept share, +$10-first rate vs the trades it removes, mean R."""
    out = {}
    base = summarize(rows)
    for nm, f in FILTERS.items():
        if f is None:
            continue
        a = [r for r in rows if f(r)]
        b = [r for r in rows if not f(r)]
        sa, sb = summarize(a), summarize(b)
        ka = sa.get("tp10", {}).get("tp_first", {})
        kb = sb.get("tp10", {}).get("tp_first", {})
        z, p = two_prop_p(ka.get("k", 0), ka.get("n", 0), kb.get("k", 0), kb.get("n", 0)) if a and b else (math.nan, math.nan)
        out[nm] = {"kept_share": len(a) / len(rows) if rows else math.nan, "tp10_kept": ka.get("rate"), "tp10_removed": kb.get("rate"),
                   "mean_r_kept": sa.get("tp10", {}).get("mean_net_r"), "mean_r_removed": sb.get("tp10", {}).get("mean_net_r"),
                   "geo_kept": sa.get("tp10", {}).get("geometric_baseline"), "geo_removed": sb.get("tp10", {}).get("geometric_baseline"),
                   "z": z, "p": p}
    out["_base"] = {"n": base["n"], "tp10": base.get("tp10", {}).get("tp_first", {}).get("rate")}
    return out


def confirmation_cost(res: dict) -> dict:
    """For SWEEP events whose +$10 reversal happened: the share of that move gone at each delayed method's entry, and
    how many such reversals no delayed method entered."""
    out = {}
    trades = {}
    for r in res["trades"]:
        if r["status"] == "FILLED":
            trades.setdefault(r["ev_id"], []).append(r)
    for tf in TFS:
        A = [e for e in res["events"] if e["tf"] == tf and e["disp"] == "SWEEP" and np.isfinite(e["min_rev10"])]
        x = {}
        for m in ("A-CONF", "A-MSS", "A-M5MSS", "A-RETEST", "A-DISP"):
            gone = []
            for e in A:
                for r in trades.get(e["id"], []):
                    if r["m"] == m:
                        gone.append(r["d"] * (r["e"] - e["c"]) / (e["c"] / 4000.0) / TP[0])
            x[m] = {"entered": len(gone), "share_gone_median": q(gone, 50), "share_gone_p75": q(gone, 75)}
        none = sum(1 for e in A if not any(r["m"] in ("A-CONF", "A-MSS", "A-M5MSS", "A-RETEST", "A-DISP") for r in trades.get(e["id"], [])))
        out[tf] = {"sweeps_with_rev10": len(A), "no_delayed_entry": none, "methods": x}
    return out


# ---------------- model analysis, univariate tests, selection (development only) ----------------
def be(r: dict) -> float:
    return (r["D"] + r["cost"]) / (TP[0] + r["D"])


def model_report(rows: list[dict], t_lo: int, t_hi: int) -> dict:
    """Walk-forward out-of-fold: full model vs geometry-only, Brier skill, reliability, group ablation."""
    if len(rows) < 100:
        return {"n": len(rows), "note": "fewer than 100 trades: not fitted"}
    y = label(rows)
    pf = walk_forward(rows, FEATURES, t_lo, t_hi)
    pg = walk_forward(rows, GEOMETRY, t_lo, t_hi)
    ok = np.isfinite(pf) & np.isfinite(pg)
    if ok.sum() < 50:
        return {"n": len(rows), "note": "too few out-of-fold predictions"}
    yy, a, g = y[ok], pf[ok], pg[ok]
    base = yy.mean()
    br = lambda p: float(np.mean((p - yy) ** 2))                 # noqa: E731
    o = {"n": len(rows), "n_oof": int(ok.sum()), "base_rate": float(base), "auc_full": auc(a, yy), "auc_geometry": auc(g, yy),
         "brier_full": br(a), "brier_geometry": br(g), "brier_base": br(np.full(len(yy), base))}
    o["bss_vs_base"] = 1 - o["brier_full"] / o["brier_base"] if o["brier_base"] > 0 else math.nan
    o["bss_vs_geometry"] = 1 - o["brier_full"] / o["brier_geometry"] if o["brier_geometry"] > 0 else math.nan
    dec = pd.qcut(pd.Series(a), 10, labels=False, duplicates="drop").to_numpy()
    o["reliability"] = [{"p_mean": float(a[dec == k].mean()), "hit": float(yy[dec == k].mean()), "n": int((dec == k).sum())}
                        for k in np.unique(dec)]
    rng = H.seeded_rng(SEED)
    bs = []
    for _ in range(300):
        ix = rng.integers(0, len(yy), len(yy))
        bs.append(auc(a[ix], yy[ix]) - auc(g[ix], yy[ix]))
    o["auc_gain_boot95"] = [float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))]
    abl = {}
    for gname, cols in GROUPS.items():
        if gname == "geometry":
            continue
        keep = tuple(c for c in FEATURES if c not in cols)
        pa = walk_forward(rows, keep, t_lo, t_hi)[ok]
        abl[gname] = {"auc_drop": o["auc_full"] - auc(pa, yy), "brier_rise": br(pa) - o["brier_full"]}
    o["ablation"] = abl
    return o


def univariate(V: dict) -> list[dict]:
    """Likelihood-ratio p of each feature added to geometry, per variant with >= 100 trades; BH at q = 0.10 overall."""
    out = []
    for (m, tf), v in V.items():
        rows = v["kept"]
        if len(rows) < 100:
            continue
        for f in FEATURES:
            if f in GEOMETRY:
                continue
            x = np.array([r[f] for r in rows], float)
            if np.nanstd(x) == 0:
                continue
            p = lr_test(rows, f)
            y = label(rows)
            hi = x >= np.nanpercentile(x, 67)
            lo = x <= np.nanpercentile(x, 33)
            out.append({"m": m, "tf": tf, "f": f, "p": p, "tp10_top_third": float(y[hi].mean()) if hi.any() else math.nan,
                        "tp10_bottom_third": float(y[lo].mean()) if lo.any() else math.nan})
    keep = H.benjamini_hochberg([r["p"] if np.isfinite(r["p"]) else 1.0 for r in out], 0.10)
    for r, k in zip(out, keep):
        r["bh10"] = bool(k)
    return out


def qualifies(sm: dict) -> bool:
    x = sm.get("tp10")
    if not x or sm["n"] < 30:
        return False
    rnd = x.get("random", {})
    return (x["mean_net_r"] > 0 and x["mean_net_r_boot95"][0] > 0 and np.isfinite(rnd.get("p_one_sided", math.nan))
            and rnd["p_one_sided"] < 0.05)


def select(P: Path, V: dict, t_lo: int, t_hi: int, lo_k: int, hi_k: int, log=print) -> dict:
    """The registered selection: per engine, the qualifying variant x rule (folds 2-6) with the highest mean net R."""
    edges = np.linspace(t_lo, t_hi, 7)
    rows_out, srs = [], []
    monthly = {}
    for (m, tf), v in V.items():
        rows = v["eligible"]
        if not rows:
            continue
        pf = walk_forward(rows, FEATURES, t_lo, t_hi) if len(rows) >= 100 else np.full(len(rows), np.nan)
        for rule in ("UNCONDITIONAL", "MODEL"):
            take = [r for r, p in zip(rows, pf) if r["t_fill"] >= edges[1]
                    and (rule == "UNCONDITIONAL" or (np.isfinite(p) and p >= be(r) + MARGIN))]
            take = one_position(take)
            rnd = matched_random(P, take, lo_k, hi_k) if take else None
            sm = summarize(take, rnd)
            rr = np.array([r["tp10_r"] for r in take if decided(r)], float)
            sr = float(rr.mean() / rr.std(ddof=1)) if len(rr) > 2 and rr.std(ddof=1) > 0 else math.nan
            if np.isfinite(sr):
                srs.append(sr)
            mo = pd.Series(rr, index=pd.to_datetime([r["t_fill"] for r in take if decided(r)], unit="s")).resample("MS").mean() if len(rr) else pd.Series(dtype=float)
            monthly[(m, tf, rule)] = mo
            rows_out.append({"engine": m[0], "m": m, "tf": tf, "rule": rule, "summary": sm, "sharpe": sr, "qualifies": qualifies(sm)})
            log(f"  {m} {tf} {rule}: n {sm['n']} mean R {sm.get('tp10', {}).get('mean_net_r')}")
    cand = {}
    for eng in ("A", "B"):
        q_ = [r for r in rows_out if r["engine"] == eng and r["qualifies"]]
        cand[eng] = max(q_, key=lambda r: r["summary"]["tp10"]["mean_net_r"]) if q_ else None
    # DSR of each candidate against every Sharpe tried; PBO over the monthly matrix
    if monthly:
        M = pd.DataFrame(monthly).fillna(0.0)
        pbo = H.pbo_cscv(M.to_numpy(float), 8) if M.shape[0] >= 8 else {"pbo": math.nan}
    else:
        pbo = {"pbo": math.nan}
    for eng, c in cand.items():
        if c is None:
            continue
        take_r = c["summary"]
        c["dsr"] = H.deflated_sharpe(c["sharpe"], take_r["n"], 0.0, 3.0, srs)
    return {"all": rows_out, "candidates": cand, "pbo": pbo, "trials": len(rows_out)}


def freeze_model(rows: list[dict]) -> dict:
    X, y = matrix(rows, FEATURES), label(rows)
    Xs, _, mu, sd = standardize(X, X[:1])
    w = logit_fit(Xs, y)
    return {"features": list(FEATURES), "mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist(), "margin": MARGIN, "n_fit": len(rows)}


def apply_frozen(rows: list[dict], fz: dict) -> list[dict]:
    if fz["rule"] == "UNCONDITIONAL":
        return one_position(rows)
    md = fz["model"]
    X = (matrix(rows, md["features"]) - np.array(md["mu"])) / np.array(md["sd"])
    p = logit_pred(np.array(md["w"]), np.nan_to_num(X))
    keep = []
    for r, pp in zip(rows, p):
        r["p_model"] = float(pp)
        if pp >= be(r) + md["margin"]:
            keep.append(r)
    return one_position(keep)


# ---------------- outputs and command line ----------------
def jsonable(x):
    if isinstance(x, dict):
        return {(k if isinstance(k, str) else "|".join(map(str, k)) if isinstance(k, tuple) else str(k)): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else round(float(x), 6)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def breakdown(rows: list[dict]) -> dict:
    o = {}
    for key, vals in (("sess", SESS), ("regime", ("TREND", "MIXED", "RANGE")), ("vol", ("LOW", "NORMAL", "HIGH"))):
        o[key] = {}
        for v in vals:
            sub = [r for r in rows if r[key] == v]
            sm = summarize(sub)
            o[key][v] = {"n": sm["n"], **({f"tp{int(T)}": sm[f"tp{int(T)}"]["tp_first"]["rate"] for T in TP} if sm["n"] else {}),
                         "mean_r10": sm.get("tp10", {}).get("mean_net_r")}
    return o


def variant_report(res: dict, V: dict, lo_k: int, hi_k: int) -> dict:
    P = res["P"]
    out = {}
    for key, v in V.items():
        kept = v["kept"]
        rnd = matched_random(P, kept, lo_k, hi_k) if kept else None
        out[key] = {"orders": v["orders"], "funnel": v["funnel"], "rejected_before_fill": v["rejected_before_fill"],
                    "eligible": len(v["eligible"]), "kept": len(kept), "summary": summarize(kept, rnd),
                    "breakdown": breakdown(kept), "filters": filter_table(P, kept, lo_k, hi_k)}
    return out


EV_CSV = ("id", "tf", "side", "disp", "primary", "n_lv", "sess", "regime", "vol", "cls", "cls_sub", "pen_usd", "atr_usd", "d_pen",
          "d_wick", "d_close", "d_body", "d_range", "b_dist", "b_mom", "b_comp", "b_atrr", "room_rev", "room_cont", "two_sided",
          "mfe15", "mae15", "mfe60", "mae60", "mfe240", "mae240", "de15", "de60", "de240", "min_rev10", "min_cont10", "min_rev15",
          "min_cont15", "min_rev20", "min_cont20", "first10", "retest240", "origin240", "mss8", "fail3")


def events_csv(evs: list[dict], path: str) -> None:
    """One row per event: distances, times and labels only (no price level, no bar), like B31b-W2's CSV."""
    rows = []
    for e in evs:
        r = {k: e.get(k) for k in EV_CSV}
        r["types"] = " ".join(map(str, e["types"]))
        rows.append(r)
    pd.DataFrame(rows).round(3).to_csv(path, index=False)


def analyse(res: dict, part: str, log=print, do_select: bool = False) -> dict:
    P, meta = res["P"], res["meta"]
    lo_k = int(np.searchsorted(P.t, meta["score_from"]))
    hi_k = len(P.t) - HOLD_SEC // 900 - 1
    V = variants(res)
    out = {"registration": REG, "code_sha256": code_sha(), "describe": describe(res), "confirmation_cost": confirmation_cost(res)}
    log("variants ...")
    out["variants"] = variant_report(res, V, lo_k, hi_k)
    if part == "development":
        log("univariate ...")
        out["univariate"] = univariate(V)
        log("models ...")
        out["models"] = {key: model_report(v["eligible"], meta["score_from"], meta["end"]) for key, v in V.items()}
    if do_select:
        log("selection ...")
        sel = select(P, V, meta["score_from"], meta["end"], lo_k, hi_k, log)
        drafts = {}
        for eng, c in sel["candidates"].items():
            if c is None:
                continue
            rows = V[(c["m"], c["tf"])]["eligible"]
            drafts[eng] = {"m": c["m"], "tf": c["tf"], "rule": c["rule"],
                           "model": freeze_model(rows) if c["rule"] == "MODEL" else None}
        out["selection"] = {"all": [{k: v for k, v in r.items()} for r in sel["all"]],
                            "candidates": {k: (None if v is None else {"m": v["m"], "tf": v["tf"], "rule": v["rule"], "dsr": v.get("dsr"),
                                                                    "summary": v["summary"]}) for k, v in sel["candidates"].items()},
                            "pbo": sel["pbo"], "trials": sel["trials"], "freeze_drafts": drafts}
    return out


def evaluate(res: dict, fz: dict, log=print) -> dict:
    """Validation / holdout: the frozen candidates only; Holm across candidates x targets."""
    P, meta = res["P"], res["meta"]
    lo_k = int(np.searchsorted(P.t, meta["score_from"]))
    hi_k = len(P.t) - HOLD_SEC // 900 - 1
    V = variants(res)
    cands, tests = [], []
    for eng, c in fz["candidates"].items():
        rows = V[(c["m"], c["tf"])]["eligible"]
        take = apply_frozen(rows, c)
        rnd = matched_random(P, take, lo_k, hi_k) if take else None
        sm = summarize(take, rnd)
        cands.append({"engine": eng, "m": c["m"], "tf": c["tf"], "rule": c["rule"], "summary": sm})
        for T in TP:
            p = sm.get(f"tp{int(T)}", {}).get("random", {}).get("p_one_sided", math.nan)
            tests.append((len(cands) - 1, int(T), p if np.isfinite(p) else 1.0))
    order = sorted(range(len(tests)), key=lambda k: tests[k][2])
    m_ = len(tests)
    adj, run = [0.0] * m_, 0.0
    for rank, k in enumerate(order):
        run = max(run, min(1.0, (m_ - rank) * tests[k][2]))
        adj[k] = run
    for (ci, T, p), a in zip(tests, adj):
        cands[ci].setdefault("holm", {})[f"tp{T}"] = {"p": p, "p_holm": a}
    for c in cands:
        sm = c["summary"]
        x = sm.get("tp10", {})
        ok = (sm["n"] >= 30 and x.get("mean_net_r", -1) > 0 and x.get("mean_net_r_boot95", [-1])[0] > 0
              and c["holm"]["tp10"]["p_holm"] < 0.05)
        c["verdict"] = "PASS" if ok else ("INSUFFICIENT" if sm["n"] < 30 else "FAIL")
    out = {"registration": REG, "code_sha256": code_sha(), "freeze": fz.get("frozen_utc"), "describe": describe(res),
           "candidates": cands, "variants": variant_report(res, V, lo_k, hi_k)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="B31b-W3 liquidity event study (research only)")
    ap.add_argument("cmd", choices=("discover", "describe", "evaluate"))
    ap.add_argument("--rd", required=True)
    ap.add_argument("--m5-rd", default=None)
    ap.add_argument("--part", default="development")
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--trials", default=None)
    a = ap.parse_args(argv)
    res = run_part(a.rd, a.part, a.m5_rd)
    if a.cmd == "evaluate":
        fz = json.load(open(FREEZE_PATH))
        out = evaluate(res, fz)
    else:
        out = analyse(res, a.part, do_select=(a.cmd == "discover" and a.part == "development"))
    out["meta"] = res["meta"]
    with open(a.out, "w") as f:
        json.dump(jsonable(out), f, indent=1, allow_nan=False)
    if a.csv:
        events_csv(res["events"], a.csv)
    if a.trials:
        H.log_trial(a.trials, {"id": f"{REG}-{a.cmd}-{a.part}", "registration": REG, "part": a.part, "cmd": a.cmd,
                               "code_sha256": code_sha(), "events": len(res["events"]), "orders": len(res["trades"]),
                               "data_hash": res["meta"]["data_hash"]})
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
