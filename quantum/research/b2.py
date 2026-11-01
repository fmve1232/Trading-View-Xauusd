"""Phase B2 (research/14; research/04 rows 13-20 and 25): SMC setups against the OPERATOR'S TRADE, DEVELOPMENT data only.

Declared 2026-11-01, committed before the first run, and not changed after seeing results.

    python -m quantum.research.b2 <research-data checkout> <out.json> [--registry research/trials.jsonl] [--set b2|b2b|b2c]

THE EVENT (operator, 2026-11-01): SL $500 / TP $1,000 at 0.5 lot = -$10 / +$20 of price from the decision price,
"the market should move $10 to $20 my way without hitting my SL".
    T20   +$20 before -$10   primary: the operator's trade
    T10   +$10 before -$10   secondary: the lower end of "$10 to $20"
    T2    +$2  before -$10   the earlier statement (SL $500 / TP $100); its break-even is ~90%
SCALING. The development window (2020-01-24 -> 2023-01-24) traded at ~$1,450-2,070; the trade is defined at today's
~$4,000. Distances AND costs are scaled by P / 4,000 (P = the decision price), so each test asks about the same relative
move (T20: +0.50% before -0.25%) at the same relative cost. The unscaled reading (the same dollars in 2020-22, a
relatively larger move) is logged in the same record as a sensitivity and never used for selection.
HORIZON. 3 trading days (288 fifteen-minute bars): the operator's trade has no time exit and nearly every path resolves
within it; a path still open is closed at the horizon bar's close.
PATHS. 15-minute bars from the first bar opening at or after the decision bar's close. A bar reaching both levels is a
LOSS unless it opened beyond the target. Fills: the level, or the bar's open when the bar opened beyond it (a gap
through the stop loses more than the stop; a gap beyond the target wins more). One position at a time: a new decision
is taken only after the previous one resolved, so outcomes do not overlap and the t-statistic is valid.
COSTS. The frozen engine model at the decision bar (harness.cost_pts: session spread + 2 x 0.20 slippage + $7 / lot),
scaled as above, charged once per trade.

SETUPS (decision at the close of bar i from bars <= i only; decision bars 15min and 1h):
    SWEEP_PD    wick beyond the prior trading day's high (low), close back inside -> SHORT (LONG); first per level per day
    SWEEP_PW    the same at the prior trading week's high / low; first per level per week
    SWEEP_EQ    the same at equal highs / lows: two confirmed swing pivots (3 / 3) within 0.10 ATR(14) in the last 100
                bars; each level fires once
    BREAK_PD    first close of the day beyond the prior day's high (low) -> LONG (SHORT): continuation
    BOS         close beyond the last confirmed swing high (low), the previous break in the SAME direction -> with it
    CHOCH       close beyond the last confirmed swing high (low), the previous break in the OTHER direction -> with it
    FVG_RETEST  a 3-bar fair value gap of at least 0.10 ATR; the first bar within 20 bars that trades into it and does not
                close through it -> in the gap's direction
    OB_RETEST   at each structure break, the last opposite-colour candle in the 10 bars before it; the first bar within
                50 bars that trades into its range and does not close through it -> in the break's direction
    FAILED_BO   close beyond the prior 20-bar high (low), then a close back inside within 3 bars -> SHORT (LONG)
    Row 29 (market-profile acceptance) is NOT TESTED: the research series has no volume.

BASELINE every setup must beat: random entries in the same direction mix, i.e. the event rate over every 15-minute
close of the partition (long and short separately), weighted by the setup's longs / shorts.

PASS RULE (all five, declared now):
    (1) Wilson 95% lower bound of the win rate > the break-even win rate (b + c) / (a + b)
    (2) mean net result > 0 with one-sided t > 3
    (3) win rate above the direction-matched random rate by more than 2 standard errors
    (4) the one-sided Benjamini-Hochberg screen at q = 0.10 over the whole family
    (5) White's Reality Check p < 0.05 over the family
A setup passing all five may be PROPOSED for registration. Nothing here opens validation or the holdout.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
import pandas as pd

from .. import sessions, ta
from . import harness as H
from . import history

TARGETS = {"T20": (20.0, 10.0), "T10": (10.0, 10.0), "T2": (2.0, 10.0)}     # +a before -b, in $ at REF_PRICE
# B2b (declared 2026-11-01 before its first run, at the operator's request after B2's results): SL $1,000 /
# TP $1,000 at 0.5 lot = +$20 before -$20 of price. One target only, to keep the family small. Everything else is
# B2's declaration unchanged: the nine setups, 15min / 1h decision bars, 15-minute paths over 3 trading days, price
# scaling to $4,000 (unscaled logged as a sensitivity), frozen costs, fills, one position at a time, the
# direction-matched random baseline and the five-part pass rule (break-even here = (20 + c) / 40, about 52%).
B2B_TARGETS = {"T20S20": (20.0, 20.0)}
# B2c (declared 2026-11-01 before its first run, at the operator's request after B2b): "-$10 stop with +$10, +$15 and
# +$20 profit". +$10 and +$20 before -$10 were already run in B2 (T10, T20) on the same data and code; re-running them
# would reproduce the same numbers and double-count the trials, so only the new target is run here and the three are
# reported together. SL $500 / TP $750 at 0.5 lot = +$15 before -$10; break-even (10 + c) / 25, about 43%; random
# about 40%. Everything else is B2's declaration unchanged.
B2C_TARGETS = {"T15": (15.0, 10.0)}
REF_PRICE = 4000.0
HORIZON = 288                         # 15-minute bars = 3 trading days
PATH_SEC = 900
MAX_WAIT_SEC = 3 * 86400
TFS = {"15min": 900, "1h": 3600}
SETUPS = ("SWEEP_PD", "SWEEP_PW", "SWEEP_EQ", "BREAK_PD", "BOS", "CHOCH", "FVG_RETEST", "OB_RETEST", "FAILED_BO")
PIVOT = 3
EQ_TOL_ATR, EQ_LOOKBACK = 0.10, 100
FVG_MIN_ATR, FVG_WINDOW = 0.10, 20
OB_LOOKBACK, OB_WINDOW = 10, 50
FBO_N, FBO_WITHIN = 20, 3
CHUNK = 2000


# ---------------- setups ----------------
def _prior_period_hl(h, l, key) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    codes, _ = pd.factorize(key)          # chronological: the index is sorted
    ph = pd.Series(h).groupby(codes).max().to_numpy()
    pl = pd.Series(l).groupby(codes).min().to_numpy()
    prev_h = np.where(codes > 0, ph[np.maximum(codes - 1, 0)], np.nan)
    prev_l = np.where(codes > 0, pl[np.maximum(codes - 1, 0)], np.nan)
    return prev_h, prev_l, codes


def _sweep(h, l, c, lvl_h, lvl_l, codes) -> np.ndarray:
    s = np.zeros(len(c))
    done_h, done_l = set(), set()
    for i in range(len(c)):
        up = math.isfinite(lvl_h[i]) and h[i] > lvl_h[i] and c[i] < lvl_h[i] and codes[i] not in done_h
        dn = math.isfinite(lvl_l[i]) and l[i] < lvl_l[i] and c[i] > lvl_l[i] and codes[i] not in done_l
        if up:
            done_h.add(codes[i])
        if dn:
            done_l.add(codes[i])
        if up != dn:
            s[i] = -1.0 if up else 1.0
    return s


def _structure(h, l, c):
    """Swing pivots (3 / 3, known 3 bars after the pivot) and every close beyond the last unbroken one.
    Returns (breaks, prev): breaks[i] = +1 / -1 on a break bar, prev[i] = the direction of the previous break (0 = none)."""
    phv, plv = ta.pivothigh(h, PIVOT, PIVOT), ta.pivotlow(l, PIVOT, PIVOT)
    n = len(c)
    brk, prev = np.zeros(n), np.zeros(n)
    sh = slo = math.nan
    last = 0
    for i in range(n):
        if math.isfinite(phv[i]):
            sh = phv[i]
        if math.isfinite(plv[i]):
            slo = plv[i]
        if math.isfinite(sh) and c[i] > sh:
            brk[i], prev[i], last, sh = 1.0, last, 1, math.nan
        elif math.isfinite(slo) and c[i] < slo:
            brk[i], prev[i], last, slo = -1.0, last, -1, math.nan
    return brk, prev


def signals(df: pd.DataFrame) -> dict:
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    n = len(c)
    atr = ta.atr(h, l, c, 14)
    cal = sessions.calendar(df.index)
    td = pd.to_datetime(pd.Series(cal["trading_date"].to_numpy()))
    pdh, pdl, dcode = _prior_period_hl(h, l, td.to_numpy())
    pwh, pwl, wcode = _prior_period_hl(h, l, td.dt.to_period("W-SUN").astype(str).to_numpy())
    out = {"SWEEP_PD": _sweep(h, l, c, pdh, pdl, dcode), "SWEEP_PW": _sweep(h, l, c, pwh, pwl, wcode)}

    # equal highs / lows
    phv, plv = ta.pivothigh(h, PIVOT, PIVOT), ta.pivotlow(l, PIVOT, PIVOT)
    s = np.zeros(n)
    piv_h, piv_l, lv_h, lv_l = [], [], [], []         # (value, bar confirmed); live levels (value, bar formed)
    for i in range(n):
        a = atr[i]
        for piv, lv, v in ((piv_h, lv_h, phv[i]), (piv_l, lv_l, plv[i])):
            if math.isfinite(v) and a > 0:
                piv[:] = [p for p in piv if i - p[1] <= EQ_LOOKBACK]
                m = [p for p in piv if abs(p[0] - v) <= EQ_TOL_ATR * a]
                if m:
                    lv.append((max([v] + [p[0] for p in m]) if lv is lv_h else min([v] + [p[0] for p in m]), i))
                piv.append((v, i))
        lv_h[:] = [x for x in lv_h if i - x[1] <= EQ_LOOKBACK]
        lv_l[:] = [x for x in lv_l if i - x[1] <= EQ_LOOKBACK]
        up = [x for x in lv_h if x[1] < i and h[i] > x[0] and c[i] < x[0]]
        dn = [x for x in lv_l if x[1] < i and l[i] < x[0] and c[i] > x[0]]
        for x in up:
            lv_h.remove(x)
        for x in dn:
            lv_l.remove(x)
        if bool(up) != bool(dn):
            s[i] = -1.0 if up else 1.0
    out["SWEEP_EQ"] = s

    # first close of the day beyond the prior day's high / low
    s = np.zeros(n)
    fired = set()
    for i in range(n):
        if math.isfinite(pdh[i]) and c[i] > pdh[i] and (dcode[i], 1) not in fired:
            s[i] = 1.0
            fired.add((dcode[i], 1))
        elif math.isfinite(pdl[i]) and c[i] < pdl[i] and (dcode[i], -1) not in fired:
            s[i] = -1.0
            fired.add((dcode[i], -1))
    out["BREAK_PD"] = s

    brk, prev = _structure(h, l, c)
    out["BOS"] = np.where((brk != 0) & (prev == brk), brk, 0.0)
    out["CHOCH"] = np.where((brk != 0) & (prev == -brk), brk, 0.0)

    # fair value gap retest
    s = np.zeros(n)
    gaps = []                                          # (dir, lo, hi, bar formed)
    for i in range(n):
        gaps = [g for g in gaps if i - g[3] <= FVG_WINDOW]
        hit = None
        for g in gaps:
            d, lo, hi, k = g
            if k >= i:
                continue
            if d > 0 and l[i] <= hi:
                hit = (g, 1.0 if c[i] >= lo else 0.0)
            elif d < 0 and h[i] >= lo:
                hit = (g, -1.0 if c[i] <= hi else 0.0)
            if hit:
                break
        if hit:
            gaps.remove(hit[0])
            s[i] = hit[1]
        if i >= 2 and atr[i] > 0:
            if l[i] - h[i - 2] >= FVG_MIN_ATR * atr[i]:
                gaps.append((1, h[i - 2], l[i], i))
            elif l[i - 2] - h[i] >= FVG_MIN_ATR * atr[i]:
                gaps.append((-1, h[i], l[i - 2], i))
    out["FVG_RETEST"] = s

    # order block retest
    s = np.zeros(n)
    obs = []                                           # (dir, lo, hi, bar of the break)
    for i in range(n):
        obs = [z for z in obs if i - z[3] <= OB_WINDOW]
        hit = None
        for z in obs:
            d, lo, hi, k = z
            if k >= i:
                continue
            if d > 0 and l[i] <= hi:
                hit = (z, 1.0 if c[i] >= lo else 0.0)
            elif d < 0 and h[i] >= lo:
                hit = (z, -1.0 if c[i] <= hi else 0.0)
            if hit:
                break
        if hit:
            obs.remove(hit[0])
            s[i] = hit[1]
        if brk[i] != 0:
            d = int(brk[i])
            for k in range(i - 1, max(i - 1 - OB_LOOKBACK, -1), -1):
                if (d > 0 and c[k] < o[k]) or (d < 0 and c[k] > o[k]):
                    obs.append((d, l[k], h[k], i))
                    break
    out["OB_RETEST"] = s

    # failed breakout
    s = np.zeros(n)
    hh, ll = ta.highest(h, FBO_N), ta.lowest(l, FBO_N)
    pend = []                                          # (dir of the breakout, level, bar)
    for i in range(n):
        pend = [p for p in pend if i - p[2] <= FBO_WITHIN]
        fail = [p for p in pend if p[2] < i and ((p[0] > 0 and c[i] < p[1]) or (p[0] < 0 and c[i] > p[1]))]
        for p in fail:
            pend.remove(p)
        dirs = {-p[0] for p in fail}
        if len(dirs) == 1:
            s[i] = float(dirs.pop())
        if i >= 1 and math.isfinite(hh[i - 1]) and c[i] > hh[i - 1]:
            pend.append((1, hh[i - 1], i))
        elif i >= 1 and math.isfinite(ll[i - 1]) and c[i] < ll[i - 1]:
            pend.append((-1, ll[i - 1], i))
    out["FAILED_BO"] = s
    return out


# ---------------- outcomes ----------------
class Paths:
    def __init__(self, df: pd.DataFrame):
        self.t = ta.epoch_s(df.index)
        self.o, self.h, self.l, self.c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))

    def locate(self, t_close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        t = self.t
        j = np.searchsorted(t, t_close)
        nxt = t[np.minimum(j, len(t) - 1)]
        ok = (t_close >= t[0]) & (j + HORIZON <= len(t)) & (nxt - t_close <= MAX_WAIT_SEC)
        return j, ok

    def evaluate(self, j: np.ndarray, p: np.ndarray, d: np.ndarray, ab: list[tuple[np.ndarray, np.ndarray]]) -> list[dict]:
        """For each (a, b) pair of per-trigger arrays: outcome (1 win, 0 loss, -1 open), result in $ per oz (fills at
        the level or at a gapping open; open paths at the horizon close) and the exit bar's index in the path."""
        res = [{"out": np.zeros(len(j), np.int8), "pnl": np.zeros(len(j)), "exit": np.zeros(len(j), np.int64)} for _ in ab]
        steps = np.arange(HORIZON)
        for s0 in range(0, len(j), CHUNK):
            sl = slice(s0, s0 + CHUNK)
            jj, pp, dd = j[sl], p[sl, None], d[sl, None]
            rows = jj[:, None] + steps[None, :]
            hh, ll = self.h[rows], self.l[rows]
            up = dd > 0
            cf = np.maximum.accumulate(np.where(up, hh - pp, pp - ll), axis=1)
            ca = np.maximum.accumulate(np.where(up, pp - ll, hh - pp), axis=1)
            od = (self.o[rows] - pp) * dd
            mk = (self.c[jj + HORIZON - 1] - pp[:, 0]) * dd[:, 0]
            r = np.arange(len(jj))
            for q, (a_all, b_all) in enumerate(ab):
                a, b = a_all[sl][:, None], b_all[sl][:, None]
                hit_a, hit_b = cf >= a - 1e-9, ca >= b - 1e-9
                ia = np.where(hit_a.any(1), hit_a.argmax(1), HORIZON)
                ib = np.where(hit_b.any(1), hit_b.argmax(1), HORIZON)
                oa, ob = od[r, np.minimum(ia, HORIZON - 1)], od[r, np.minimum(ib, HORIZON - 1)]
                win = (ia < ib) | ((ia == ib) & (ia < HORIZON) & (oa >= a[:, 0] - 1e-9))
                loss = ~win & (ib < HORIZON) & (ib <= ia)
                out = np.where(win, 1, np.where(loss, 0, -1)).astype(np.int8)
                pnl = np.where(win, np.maximum(a[:, 0], oa), np.where(loss, np.minimum(-b[:, 0], ob), mk))
                ex = jj + np.where(win, ia, np.where(loss, ib, HORIZON - 1))
                res[q]["out"][sl], res[q]["pnl"][sl], res[q]["exit"][sl] = out, pnl, ex
        return res


def one_position(t_dec: np.ndarray, exit_t: np.ndarray) -> np.ndarray:
    """Indices (into time-sorted decisions) taken when only one trade may be open: the next decision is taken only
    after the previous one's exit bar has closed."""
    keep, free = [], -np.inf
    for k in np.argsort(t_dec, kind="stable"):
        if t_dec[k] >= free:
            keep.append(k)
            free = exit_t[k]
    return np.asarray(keep, np.int64)


def _stats(out, pnl, cost, a, b, d) -> dict:
    n = len(out)
    if n == 0:
        return {"n": 0}
    net_r = (pnl - cost) / b                    # in units of the stop distance
    w, lo_ = int((out == 1).sum()), int((out == 0).sum())
    sd = net_r.std(ddof=1) if n > 1 else math.nan
    be = float(np.mean((b + cost) / (a + b)))
    lo, hi = H.wilson(w, n)
    t = float(net_r.mean() / (sd / math.sqrt(n))) if n > 1 and sd > 0 else math.nan
    return {"n": n, "long": int((d > 0).sum()), "short": int((d < 0).sum()), "wins": w, "losses": lo_, "open": n - w - lo_,
            "win_rate": w / n, "wilson": [lo, hi], "break_even": be, "net_r": float(net_r.mean()),
            "gross_r": float((pnl / b).mean()), "t": t}


def run(rd: str, outp: str, registry: str, targets: dict = TARGETS, phase: str = "B2") -> dict:
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    P = Paths(m15)
    res = {"partition": "development", "set": phase, "from": str(H.DEV[0]), "to": str(H.DEV[1]), "targets": {k: list(v) for k, v in targets.items()},
           "ref_price": REF_PRICE, "horizon_15m_bars": HORIZON, "baseline": {}, "trials": [], "family": {}}

    # direction-matched random baseline: every 15-minute close of the partition, long and short, every target
    t_all = P.t + PATH_SEC
    j_all, ok_all = P.locate(t_all)
    jr, pr = j_all[ok_all], P.c[ok_all]
    cr = H.cost_pts(m15.index)[ok_all]
    sc = pr / REF_PRICE
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        dd = np.full(len(jr), dv)
        ab = [(a * sc, b * sc) for a, b in targets.values()]
        ev = P.evaluate(jr, pr, dd, ab)
        for (tn, (a, b)), e in zip(targets.items(), ev):
            st = _stats(e["out"], e["pnl"], cr * sc, a * sc, b * sc, dd)
            res["baseline"][f"{tn} {dname}"] = {k: st[k] for k in ("n", "win_rate", "wilson", "net_r", "break_even")}
            print(f"baseline {tn} {dname:5s} n {st['n']:6d} win {st['win_rate']:.3f} net {st['net_r']:+.3f}R", flush=True)

    daily, weekly, names = {}, {}, []
    for tf, tf_sec in TFS.items():
        df = m15 if tf == "15min" else H.partition(history.load(rd, "XAU/USD", tf), "development")
        dh = H.data_hash(df)
        cost_bar = H.cost_pts(df.index)
        t_close = ta.epoch_s(df.index) + tf_sec
        c = df["close"].to_numpy(float)
        for sname, sig in signals(df).items():
            i = np.flatnonzero(sig != 0)
            j, ok = P.locate(t_close[i])
            i, j = i[ok], j[ok]
            p, d = c[i], sig[i]
            scale = p / REF_PRICE
            cs, cu = cost_bar[i] * scale, cost_bar[i]
            ab = [(a * scale, b * scale) for a, b in targets.values()] + [(np.full(len(i), a), np.full(len(i), b)) for a, b in targets.values()]
            ev = P.evaluate(j, p, d, ab)
            for q, (tn, (a, b)) in enumerate(targets.items()):
                e, eu = ev[q], ev[q + len(targets)]
                keep = one_position(t_close[i], P.t[np.minimum(e["exit"], len(P.t) - 1)] + PATH_SEC)
                st = _stats(e["out"][keep], e["pnl"][keep], cs[keep], a * scale[keep], b * scale[keep], d[keep])
                st_all = _stats(e["out"], e["pnl"], cs, a * scale, b * scale, d)
                keep_u = one_position(t_close[i], P.t[np.minimum(eu["exit"], len(P.t) - 1)] + PATH_SEC)
                st_u = _stats(eu["out"][keep_u], eu["pnl"][keep_u], cu[keep_u], np.full(len(keep_u), a), np.full(len(keep_u), b), d[keep_u])
                rl, rs = res["baseline"][f"{tn} long"], res["baseline"][f"{tn} short"]
                if st["n"]:
                    p_rand = (st["long"] * rl["win_rate"] + st["short"] * rs["win_rate"]) / st["n"]
                    z = (st["win_rate"] - p_rand) / math.sqrt(max(p_rand * (1 - p_rand), 1e-12) / st["n"])
                else:
                    p_rand = z = math.nan
                tid = f"{tf} {sname} {tn}"
                rec = {"id": tid, "tf": tf, "setup": sname, "target": tn, "a_usd_at_4000": a, "b_usd_at_4000": b, "data_hash": dh,
                       "triggers": len(i), **{k: st.get(k) for k in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "gross_r", "t")},
                       "random_same_mix": p_rand, "z_vs_random": z,
                       # in today's dollars at 0.5 lot (50 oz): net R x the stop ($10 at $4,000) x 50
                       "usd_per_trade_0p5lot": st["net_r"] * b * 50 if st["n"] else None,
                       "all_triggers": {k: st_all.get(k) for k in ("n", "win_rate", "net_r")},
                       "unscaled_sensitivity": {k: st_u.get(k) for k in ("n", "win_rate", "break_even", "net_r", "t")}}
                rec["pass"] = {"1_wilson_lb_above_break_even": bool(st["n"] and st["wilson"][0] > st["break_even"]),
                               "2_t_above_3": bool(st["n"] and (st["t"] or 0) > 3 and st["net_r"] > 0),
                               "3_beats_random_by_2se": bool(st["n"] and z > 2)}
                res["trials"].append(rec)
                H.log_trial(registry, {"phase": phase, "partition": "development", **rec})
                names.append(tid)
                dts = pd.to_datetime(t_close[i][keep], unit="s", utc=True).normalize()
                net_r = (e["pnl"][keep] - cs[keep]) / (b * scale[keep])
                dser = pd.Series(net_r, index=dts).groupby(level=0).sum() if len(keep) else pd.Series(dtype=float)
                daily[tid] = dser
                weekly[tid] = dser.groupby(pd.Grouper(freq="W")).sum() if len(dser) else dser
                print(f"{tid:28s} n {st.get('n', 0):5d} win {st.get('win_rate', math.nan):.3f} [{(st.get('wilson') or [math.nan])[0]:.3f}] "
                      f"be {st.get('break_even', math.nan):.3f} rand {p_rand:.3f} z {z:+.2f} net {st.get('net_r', math.nan):+.3f}R t {st.get('t', math.nan):+.2f}", flush=True)

    D = pd.DataFrame(daily).fillna(0.0).sort_index()
    W = pd.DataFrame(weekly).fillna(0.0).sort_index()
    rc = H.reality_check(D[names].to_numpy(), B=1000, mean_block=10.0)
    tr_map = {t["id"]: t for t in res["trials"]}
    pv = [H.t_pvalue(tr_map[x]["t"], tr_map[x]["n"]) if tr_map[x]["n"] and tr_map[x]["t"] is not None else 1.0 for x in names]
    pv = [1.0 if not math.isfinite(v) else v for v in pv]
    bh = H.benjamini_hochberg(pv, q=0.10)
    sr = (D[names].mean() / D[names].std(ddof=1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    best = sr.idxmax()
    x = D[best].to_numpy()
    dsr = H.deflated_sharpe(float(sr[best]), len(x), float(pd.Series(x).skew()), float(pd.Series(x).kurt() + 3), list(sr.values))
    for t_, ok in zip(names, bh):
        tr_map[t_]["pass"]["4_bh_fdr10"] = bool(ok)
        tr_map[t_]["pass"]["5_reality_check_p_below_0p05"] = bool(rc["p_value"] < 0.05)
        tr_map[t_]["passes_all"] = all(tr_map[t_]["pass"].values())
    res["family"] = {"trials": len(names), "days": len(D), "weeks": len(W), "reality_check": {**rc, "best_id": names[rc["best"]]},
                     "pbo": H.pbo_cscv(W[names].to_numpy(), groups=8), "best_daily_sharpe": {"id": best, "sharpe_daily": float(sr[best]), **dsr},
                     "bh_fdr10_passed": [n_ for n_, ok in zip(names, bh) if ok],
                     "passes_all": [t_["id"] for t_ in res["trials"] if t_.get("passes_all")],
                     "note": "Screens are one-sided (H1: mean net > 0). The pass flags 1-3 are per trial; 4-5 are family-wide."}
    with open(outp, "w") as f:
        json.dump(res, f, indent=1, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rd")
    ap.add_argument("out")
    ap.add_argument("--registry", default="research/trials.jsonl")
    ap.add_argument("--set", default="b2", choices=("b2", "b2b", "b2c"))
    a = ap.parse_args(argv)
    sets = {"b2": (TARGETS, "B2"), "b2b": (B2B_TARGETS, "B2b"), "b2c": (B2C_TARGETS, "B2c")}
    r = run(a.rd, a.out, a.registry, *sets[a.set])
    print(json.dumps(r["family"], indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
