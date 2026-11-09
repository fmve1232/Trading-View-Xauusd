"""Phase D: the race on one-minute BID / ASK paths (research/registrations/PHASE_D.json, Workstreams B and C). Research only.

B26's execution model, unchanged, at one-minute resolution:
  * decision at a 15-minute close T; fill at the first quote of the first minute at or after T inside that 15-minute
    bar (no fill otherwise, counted): a BUY at the ASK, a SELL at the BID, plus entry slippage;
  * TP / SL at +-distance from the fill; a BUY's levels trigger on the BID, a SELL's on the ASK;
  * a minute opening beyond the stop exits at its open less the exit slippage (gap); beyond the target, at the target;
  * a minute reaching both levels is AMBIGUOUS = the stop (worst case); the best case (TP) is reported as the bound;
  * the trade times out at T_end (B26's 192nd 15-minute bar close, supplied by the caller), or exits at the close of
    the last minute before a closure of more than 2 hours (CLOSURE), at the exit side less the exit slippage; a trade
    still open at the end of the data is OPEN (excluded).
Sources: Dukascopy (real best bid and best ask per minute) or MT5 (BID bars; ask = bid + the bar's spread x point, a
per-minute constant: an approximation, labelled as such). The first-hit search uses block extrema (exact, not sampled).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import b26

BLK = 64
CLOSURE_S = b26.CLOSURE_S
TP, SL, AMB, TIMEOUT, CLOSURE, OPEN, NOFILL = range(7)
NAMES = ("TP", "SL", "AMBIGUOUS", "TIMEOUT", "CLOSURE", "OPEN", "NO_FILL")


@dataclass
class M1Path:
    t: np.ndarray            # epoch seconds of each minute's open
    bo: np.ndarray
    bh: np.ndarray
    bl: np.ndarray
    bc: np.ndarray
    ao: np.ndarray
    ah: np.ndarray
    al: np.ndarray
    ac: np.ndarray
    closure_end: np.ndarray  # True at the last minute before a gap > CLOSURE_S (and at the final minute)
    source: str

    @property
    def n(self) -> int:
        return len(self.t)

    def __post_init__(self):
        nb = (self.n + BLK - 1) // BLK
        pad = nb * BLK - self.n

        def blocks(x, fn, fill):
            return fn(np.r_[x, np.full(pad, fill)].reshape(nb, BLK), axis=1)
        self.bh_max, self.bl_min = blocks(self.bh, np.max, -np.inf), blocks(self.bl, np.min, np.inf)
        self.ah_max, self.al_min = blocks(self.ah, np.max, -np.inf), blocks(self.al, np.min, np.inf)
        self.ce_idx = np.flatnonzero(self.closure_end)


def _epoch(idx: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(idx.tz_convert("UTC").as_unit("s").asi8, dtype=np.int64)


def _closure(t: np.ndarray) -> np.ndarray:
    return np.r_[np.diff(t) > CLOSURE_S, True] if len(t) else np.zeros(0, bool)


def from_dukascopy(m1: pd.DataFrame, scale: float) -> M1Path:
    m = m1.sort_index()
    m = m[~m.index.duplicated()]
    t = _epoch(pd.DatetimeIndex(m.index))
    v = {c: m[c].to_numpy(float) / scale for c in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c")}
    return M1Path(t, v["bid_o"], v["bid_h"], v["bid_l"], v["bid_c"], v["ask_o"], v["ask_h"], v["ask_l"], v["ask_c"], _closure(t), "dukascopy")


def from_mt5(m1: pd.DataFrame, point: float) -> M1Path:
    """MT5 bars are BID; the ask is bid + spread_points x point for the whole minute (approximation)."""
    if not point or point <= 0:
        raise ValueError("the broker's point size is required to build the ask side; it is never assumed")
    m = m1.sort_index()
    m = m[~m.index.duplicated()]
    t = _epoch(pd.DatetimeIndex(m.index))
    s = m["spread_points"].to_numpy(float) * point
    o, h, lo, c = (m[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    return M1Path(t, o, h, lo, c, o + s, h + s, lo + s, c + s, _closure(t), "mt5 (ask = bid + spread)")


def first_hit(x: np.ndarray, blk: np.ndarray, start: int, stop: int, thr: float, ge: bool) -> int:
    """First j in [start, stop) with x[j] >= thr (ge) or <= thr; -1 if none. blk = per-block max (ge) or min."""
    if start >= stop:
        return -1
    head = min((start // BLK + 1) * BLK, stop)
    seg = x[start:head]
    m = seg >= thr if ge else seg <= thr
    if m.any():
        return start + int(np.argmax(m))
    if head >= stop:
        return -1
    b1, b2 = head // BLK, (stop - 1) // BLK
    mm = blk[b1:b2 + 1] >= thr if ge else blk[b1:b2 + 1] <= thr
    if not mm.any():
        return -1
    lo = (b1 + int(np.argmax(mm))) * BLK
    hi = min(lo + BLK, stop)
    seg = x[lo:hi]
    m = seg >= thr if ge else seg <= thr
    return lo + int(np.argmax(m)) if m.any() else -1


def fill_index(P: M1Path, t_dec: np.ndarray, bar_s: int = 900) -> np.ndarray:
    """The first minute at or after each decision time inside the same 15-minute bar; -1 when none."""
    j = np.searchsorted(P.t, t_dec, "left")
    jj = np.clip(j, 0, max(P.n - 1, 0))
    ok = (j < P.n) & (P.t[jj] < t_dec + bar_s) if P.n else np.zeros(len(t_dec), bool)
    return np.where(ok, j, -1)


def race(P: M1Path, f: int, d: int, tp_d: float, sl_d: float, si: float, so: float, t_end: int,
         fill_px: float | None = None, skip_fill_bar: bool = False) -> tuple:
    """One trade from minute f. Returns (worst outcome, best outcome, exit index, exit price (worst), fill, gap).
    fill_px overrides the open fill (a stop entry); skip_fill_bar starts the level search after f (see stop_entry)."""
    if fill_px is None:
        fill = (P.ao[f] + si) if d > 0 else (P.bo[f] - si)
    else:
        fill = fill_px
    tp, sl = fill + d * tp_d, fill - d * sl_d
    end = int(np.searchsorted(P.t, t_end, "left"))                       # minutes opening before T_end
    ci = P.ce_idx[np.searchsorted(P.ce_idx, f, "left")] if len(P.ce_idx) else P.n - 1
    stop = min(end, ci + 1, P.n)
    s0 = f + 1 if skip_fill_bar else f
    if d > 0:
        jt = first_hit(P.bh, P.bh_max, s0, stop, tp, True)
        js = first_hit(P.bl, P.bl_min, s0, stop, sl, False)
        op = P.bo
    else:
        jt = first_hit(P.al, P.al_min, s0, stop, tp, False)
        js = first_hit(P.ah, P.ah_max, s0, stop, sl, True)
        op = P.ao
    beyond_sl = (lambda j: op[j] <= sl) if d > 0 else (lambda j: op[j] >= sl)
    beyond_tp = (lambda j: op[j] >= tp) if d > 0 else (lambda j: op[j] <= tp)
    if js >= 0 and (jt < 0 or js < jt):
        g = bool(beyond_sl(js))
        px = (op[js] - d * so) if g else (sl - d * so)
        return SL, SL, js, px, fill, g
    if jt >= 0 and (js < 0 or jt < js):
        return TP, TP, jt, tp, fill, bool(beyond_tp(jt))
    if jt >= 0 and jt == js:
        if beyond_sl(js):
            return SL, SL, js, op[js] - d * so, fill, True
        if beyond_tp(jt):
            return TP, TP, jt, tp, fill, True
        return AMB, TP, js, sl - d * so, fill, False
    last_data = P.n - 1
    if ci < last_data and ci < end:                                       # a real closure comes first
        j, code = ci, CLOSURE
    elif end <= last_data:                                                # every minute opening before T_end was scanned
        j, code = max(end - 1, f), TIMEOUT
    else:                                                                 # the data end before T_end
        return OPEN, OPEN, last_data, np.nan, fill, False
    cl = P.bc[j] - so if d > 0 else P.ac[j] + so
    return code, code, j, cl, fill, False


def bracket(P: M1Path, t_dec: np.ndarray, t_end: np.ndarray, d: int, tp_usd: float, sl_usd: float, k: np.ndarray,
            si: float = 0.0, so: float = 0.0, cm: float = 0.0) -> pd.DataFrame:
    """Every decision's trade with TP / SL of tp_usd / sl_usd x k (k = price / 4000 in development, 1 in 2026);
    slippage and commission in 4000-equivalent USD (x k). net_* in USD per oz, 4000-equivalent."""
    f_all = fill_index(P, t_dec)
    rows = []
    for x, f in enumerate(f_all):
        kk = float(k[x])
        if f < 0:
            rows.append((NOFILL, NOFILL, -1, np.nan, np.nan, False, np.nan, np.nan))
            continue
        o_w, o_b, j, px, fill, gap = race(P, int(f), d, tp_usd * kk, sl_usd * kk, si * kk, so * kk, int(t_end[x]))
        net_w = (d * (px - fill) - cm * kk) / kk if o_w != OPEN else np.nan
        net_b = (tp_usd * kk - cm * kk) / kk if (o_w == AMB and o_b == TP) else net_w
        rows.append((o_w, o_b, j, px, fill, gap, net_w, net_b))
    df = pd.DataFrame(rows, columns=["worst", "best", "exit_j", "exit_px", "fill", "gap", "net_worst", "net_best"])
    df["outcome"] = [NAMES[int(o)] for o in df["worst"]]
    df["outcome_best"] = [NAMES[int(o)] for o in df["best"]]
    return df


def stop_entry(P: M1Path, t_dec: np.ndarray, t_end: np.ndarray, d: int, x_usd: float, window_s: int, tp_usd: float,
               sl_usd: float, ref_px: np.ndarray, k: np.ndarray, si: float = 0.0, so: float = 0.0, cm: float = 0.0) -> pd.DataFrame:
    """Stop entry x_usd beyond the decision reference price (the 15-minute close) within window_s; then the bracket from
    the fill. A BUY stop triggers on the ASK, a SELL stop on the BID; a minute opening beyond the stop fills at its open.
    In the fill minute the order of the rest of its range is unknown: WORST counts a stop touched there as SL and a target
    touched there as not yet hit; BEST the reverse. Both are returned."""
    f_all = fill_index(P, t_dec)
    out = []
    for x, f in enumerate(f_all):
        kk = float(k[x])
        if f < 0:
            out.append((NOFILL, NOFILL, np.nan, np.nan))
            continue
        lvl = ref_px[x] + d * x_usd * kk
        stop_t = min(int(t_dec[x]) + window_s, int(t_end[x]))
        stop_i = int(np.searchsorted(P.t, stop_t, "left"))
        if d > 0:
            j = first_hit(P.ah, P.ah_max, int(f), stop_i, lvl, True)
        else:
            j = first_hit(P.bl, P.bl_min, int(f), stop_i, lvl, False)
        if j < 0:
            out.append((NOFILL, NOFILL, np.nan, np.nan))
            continue
        op = P.ao[j] if d > 0 else P.bo[j]
        fill = (max(lvl, op) + si * kk) if d > 0 else (min(lvl, op) - si * kk)
        tp, sl = fill + d * tp_usd * kk, fill - d * sl_usd * kk
        hit_sl_here = (P.bl[j] <= sl) if d > 0 else (P.ah[j] >= sl)
        hit_tp_here = (P.bh[j] >= tp) if d > 0 else (P.al[j] <= tp)
        res = race(P, j, d, tp_usd * kk, sl_usd * kk, 0.0, so * kk, int(t_end[x]), fill_px=fill, skip_fill_bar=True)
        o_w, o_b, px_w = res[0], res[1], res[3]
        if hit_sl_here:                                   # worst: the stop touched in the fill minute came first
            o_w, px_w = SL, sl - d * so * kk
        if hit_tp_here:                                   # best: the target touched in the fill minute came first
            o_b = TP
        net_w = (d * (px_w - fill) - cm * kk) / kk if o_w != OPEN else np.nan
        net_b = (tp_usd * kk - cm * kk) / kk if o_b == TP else net_w
        out.append((o_w, o_b, net_w, net_b))
    df = pd.DataFrame(out, columns=["worst", "best", "net_worst", "net_best"])
    df["outcome"] = [NAMES[int(o)] for o in df["worst"]]
    df["outcome_best"] = [NAMES[int(o)] for o in df["best"]]
    return df
