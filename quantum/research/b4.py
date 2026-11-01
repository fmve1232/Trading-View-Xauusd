"""Phase B4: entry-price hypotheses from the literature, on the operator's -$10 stop with +$10 / +$15 / +$20 targets.
DEVELOPMENT data only. Declared 2026-11-01, committed before the first run, not changed after seeing results.

    python -m quantum.research.b4 <research-data checkout> <out.json> [--registry research/trials.jsonl]

The operator asked (2026-11-01) for "the exact market entry price in which the next $10 movement is confirmed or has a
higher probability to hit +$10". Under a price with no predictable drift, P(+a before -b) = b / (a + b) from ANY entry
price (optional stopping), so an entry price can only help where it coincides with predictable drift. The literature
names three candidates that this repository can test with its data (research/ENTRY_PRICE_RESEARCH.md):

H1 ROUND NUMBERS (Osler 2003, J. Finance 58: take-profit orders cluster AT round numbers -> reversals there;
   stop-loss orders cluster just BEYOND them -> moves accelerate after a crossing). Levels: multiples of $10, $50, $100.
     RN_CROSS(R)    a close crosses a multiple of R (previous close below, this close at or above -> LONG; mirror SHORT);
                    the level must not have been crossed by a close in the previous 20 bars
     RN_REJECT(R)   a bar opens below the next multiple of R above it, trades up to it, and closes back below -> SHORT
                    (mirror LONG): the first touch of a take-profit cluster
H2 SESSION-OPEN MOMENTUM (Gao, Han, Li & Zhou 2018, J. Financial Economics 129; intraday momentum in commodity futures
   and FX): the first 30 minutes of a session predict its direction.
     LONDON_OPEN    the return from the last close before 08:00 London to the 08:30 London close; trade its sign then
     NY_OPEN        the same for 08:30 -> 09:00 New York (the US data-release minute)
H3 LIMIT ENTRY AT A BETTER PRICE (adverse selection of limit orders: fills come disproportionately before adverse moves)
     LIMIT(x)       from every 4th 15-minute close, long and short separately: a limit order x below (long) / above
                    (short) the decision price, valid 4 bars (1 hour); filled at the limit or at a better opening price;
                    the stop and targets are measured from the fill. Compared with the MARKET entry from the same
                    decisions. x = $2 and $5 (scaled to $4,000). The order of prices inside the fill bar is unknown, so
                    the trial uses the CONSERVATIVE bound (on the fill bar only the move against the trade counts) and
                    the OPTIMISTIC bound (the path starts at the next bar) is reported beside it.
Decision bars: 15-minute (H1 also on 1-hour). Everything else is B2's declaration (quantum/research/b2.py): 15-minute
paths over 3 trading days, distances and costs scaled to $4,000, frozen costs, fills at the level or a gapping open, ties
= LOSS unless the bar opened beyond the target, one position at a time (H1, H2; H3 is a geometry comparison and uses
every decision), direction-matched random baseline, B2's five-part pass rule; the 90% target reported beside it.
Trials: H1 3 levels x 2 rules x 2 TF x 3 targets = 36; H2 2 x 3 = 6; H3 2 offsets x 3 targets = 6 (market entry
reported as the comparison, not a trial). 48 trials. B4 does not log B2's unscaled sensitivity.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys

import numpy as np
import pandas as pd

from .. import ta
from . import b2, history
from . import harness as H

TARGETS = {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
ROUND_LEVELS = (10.0, 50.0, 100.0)
CROSS_LOOKBACK = 20
SESSIONS = {"LONDON_OPEN": ("Europe/London", 8, 0), "NY_OPEN": ("America/New_York", 8, 30)}
LIMIT_OFFSETS = (2.0, 5.0)
LIMIT_BARS = 4
LIMIT_STEP = 4


# ---------------- H1 ----------------
def round_cross(c: np.ndarray, R: float) -> np.ndarray:
    n = len(c)
    s = np.zeros(n)
    last = {}                                         # level -> bar of its last close-cross
    for i in range(1, n):
        a, b = c[i - 1], c[i]
        if not (math.isfinite(a) and math.isfinite(b)):
            continue
        if b > a:
            lv = [k * R for k in range(math.floor(a / R) + 1, math.floor(b / R) + 1)]
            d = 1
        elif b < a:
            lv = [k * R for k in range(math.ceil(b / R), math.ceil(a / R))]
            d = -1
        else:
            continue
        if not lv:
            continue
        if all(i - last.get(x, -10**9) > CROSS_LOOKBACK for x in lv):
            s[i] = d
        for x in lv:
            last[x] = i
    return s


def round_reject(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, R: float) -> np.ndarray:
    up = np.ceil(c / R) * R                           # the next multiple of R at or above the close
    up = np.where(np.isclose(up, c), up + R, up)
    dn = np.floor(c / R) * R
    dn = np.where(np.isclose(dn, c), dn - R, dn)
    short = (o < up) & (h >= up) & (c < up)
    long_ = (o > dn) & (l <= dn) & (c > dn)
    s = np.where(short & ~long_, -1.0, np.where(long_ & ~short, 1.0, 0.0))
    return s


# ---------------- H2 ----------------
def session_open(df: pd.DataFrame, tz: str, hh: int, mm: int) -> np.ndarray:
    """Signal at the close of the bar ending 30 minutes after the open (local time): the sign of the close there minus
    the last close before the open. 15-minute bars."""
    loc = df.index.tz_convert(tz)
    c = df["close"].to_numpy(float)
    n = len(c)
    s = np.zeros(n)
    mins = loc.hour * 60 + loc.minute
    open_m = hh * 60 + mm
    pos = {k: i for i, k in enumerate(zip(loc.date, mins))}
    for i in range(n):
        if mins[i] != open_m + 15:                    # the bar opening 15 min after the open closes 30 min after it
            continue
        j_open = pos.get((loc.date[i], open_m))
        if j_open is None or j_open < 1 or j_open + 1 != i:
            continue
        r = c[i] - c[j_open - 1]
        if r != 0 and math.isfinite(r):
            s[i] = 1.0 if r > 0 else -1.0
    return s


# ---------------- H3 ----------------
def limit_fills(P: b2.Paths, t_dec: np.ndarray, p: np.ndarray, d: np.ndarray, x: np.ndarray):
    """A limit order x better than p (below for a long), valid LIMIT_BARS 15-minute bars from the first bar after the
    decision. Returns (filled mask, fill bar index, fill price). A bar that opens through the limit fills at its open."""
    j, ok = P.locate(t_dec)
    last = len(P.t) - 1
    idx = np.minimum(j[:, None] + np.arange(LIMIT_BARS)[None, :], last)
    lim = p - d * x
    touch = np.where(d[:, None] > 0, P.l[idx] <= lim[:, None] + 1e-9, P.h[idx] >= lim[:, None] - 1e-9)
    k = np.where(touch.any(1), touch.argmax(1), LIMIT_BARS)
    filled = ok & (k < LIMIT_BARS)
    kk = np.minimum(k, LIMIT_BARS - 1)
    jj = np.minimum(j + kk, last)
    o = P.o[jj]
    through = np.where(d > 0, o <= lim, o >= lim)
    fill = np.where(through, o, lim)
    return filled, jj, fill


def evaluate_fills(P: b2.Paths, jj: np.ndarray, fill: np.ndarray, d: np.ndarray, targets: dict, scale: np.ndarray, mode: str):
    """Outcomes for entries filled INSIDE bar jj at `fill` (one direction per call).
    conservative: walk from bar jj with its open set to the fill and its favourable extreme capped at the fill, so only
                  the adverse part of the fill bar can count (a TP inside the fill bar might have printed before the fill)
    optimistic:   walk from the next bar (the rest of the fill bar is ignored)."""
    if mode == "optimistic":
        jj = jj + 1
        ok = jj + b2.HORIZON <= len(P.t)
        ab = [(a * scale[ok], b * scale[ok]) for a, b in targets.values()]
        return ok, P.evaluate(jj[ok], fill[ok], d[ok], ab)
    ok = jj + b2.HORIZON <= len(P.t)
    Q = copy.copy(P)                                   # never touch the shared (read-only) price arrays
    Q.o, Q.h, Q.l = P.o.copy(), P.h.copy(), P.l.copy()
    Q.o[jj] = fill
    up = d > 0
    Q.h[jj[up]] = fill[up]                             # a long cannot reach its TP inside the fill bar
    Q.l[jj[~up]] = fill[~up]                           # nor a short
    ab = [(a * scale[ok], b * scale[ok]) for a, b in targets.values()]
    ev = Q.evaluate(jj[ok], fill[ok], d[ok], ab)
    return ok, ev


# ---------------- run ----------------
def _trial(res, registry, names, daily, tid, meta, t_e, out, pnl, cost, a, b, d, exit_t, p_rand, one_pos=True):
    keep = b2.one_position(t_e, exit_t) if (one_pos and len(t_e)) else np.arange(len(t_e))
    st = b2._stats(out[keep], pnl[keep], cost[keep], a[keep], b[keep], d[keep])
    if st["n"]:
        pr = p_rand(st)
        z = (st["win_rate"] - pr) / math.sqrt(max(pr * (1 - pr), 1e-12) / st["n"])
    else:
        pr = z = math.nan
    b_ref = meta["b_usd_at_4000"]
    rec = {"id": tid, **meta, **{k: st.get(k) for k in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "gross_r", "t")},
           "random_same_mix": pr, "z_vs_random": z, "usd_per_trade_0p5lot": st["net_r"] * b_ref * 50 if st["n"] else None,
           "operator_target_90": {"point": bool(st["n"] and st["win_rate"] >= 0.9), "lower_95": bool(st["n"] and st["wilson"][0] >= 0.9)}}
    rec["pass"] = {"1_wilson_lb_above_break_even": bool(st["n"] and st["wilson"][0] > st["break_even"]),
                   "2_t_above_3": bool(st["n"] and (st["t"] or 0) > 3 and st["net_r"] > 0),
                   "3_beats_random_by_2se": bool(st["n"] and z > 2)}
    res["trials"].append(rec)
    H.log_trial(registry, {"phase": "B4", "partition": "development", **rec})
    names.append(tid)
    net_r = (pnl[keep] - cost[keep]) / b[keep] if len(keep) else np.zeros(0)
    days = pd.to_datetime(t_e[keep], unit="s", utc=True).normalize()
    daily[tid] = pd.Series(net_r, index=days).groupby(level=0).sum() if len(keep) else pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    print(f"{tid:34s} n {st.get('n', 0):5d} win {st.get('win_rate', math.nan):.3f} [{(st.get('wilson') or [math.nan])[0]:.3f}] be {st.get('break_even', math.nan):.3f} "
          f"rand {pr:.3f} z {z:+.2f} net {st.get('net_r', math.nan):+.3f}R", flush=True)


def run(rd: str, outp: str, registry: str) -> dict:
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
    P = b2.Paths(m15)
    cost15 = H.cost_pts(m15.index)
    res = {"partition": "development", "set": "B4", "from": str(H.DEV[0]), "to": str(H.DEV[1]),
           "targets": {k: list(v) for k, v in TARGETS.items()}, "baseline": {}, "trials": [], "comparisons": {}, "family": {}}
    # direction-matched random baseline (B2's): every 15-minute close
    j_all, ok_all = P.locate(P.t + b2.PATH_SEC)
    jr, pr_ = j_all[ok_all], P.c[ok_all]
    sc = pr_ / b2.REF_PRICE
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        dd = np.full(len(jr), dv)
        ev = P.evaluate(jr, pr_, dd, [(a * sc, b * sc) for a, b in TARGETS.values()])
        for (tn, (a, b)), e in zip(TARGETS.items(), ev):
            res["baseline"][f"{tn} {dname}"] = float(np.mean(e["out"] == 1))

    def p_rand_for(tn):
        return lambda st: (st["long"] * res["baseline"][f"{tn} long"] + st["short"] * res["baseline"][f"{tn} short"]) / st["n"]

    daily, names = {}, []
    # H1 and H2 on decision bars
    sets = []
    for tf, df, tf_sec in (("15min", m15, 900), ("1h", h1, 3600)):
        o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
        for R in ROUND_LEVELS:
            sets.append((tf, df, tf_sec, f"RN_CROSS_{int(R)}", round_cross(c, R)))
            sets.append((tf, df, tf_sec, f"RN_REJECT_{int(R)}", round_reject(o, h, l, c, R)))
    for name, (tz, hh, mm) in SESSIONS.items():
        sets.append(("15min", m15, 900, name, session_open(m15, tz, hh, mm)))
    for tf, df, tf_sec, sname, sig in sets:
        cost_bar = H.cost_pts(df.index)
        t_close = ta.epoch_s(df.index) + tf_sec
        c = df["close"].to_numpy(float)
        i = np.flatnonzero(sig != 0)
        j, ok = P.locate(t_close[i])
        i, j = i[ok], j[ok]
        p, d = c[i], sig[i]
        scale = p / b2.REF_PRICE
        ev = P.evaluate(j, p, d, [(a * scale, b * scale) for a, b in TARGETS.values()])
        for q, (tn, (a, b)) in enumerate(TARGETS.items()):
            e = ev[q]
            exit_t = P.t[np.minimum(e["exit"], len(P.t) - 1)] + b2.PATH_SEC
            meta = {"tf": tf, "setup": sname, "target": tn, "a_usd_at_4000": a, "b_usd_at_4000": b, "data_hash": H.data_hash(df), "decisions": len(i)}
            _trial(res, registry, names, daily, f"{tf} {sname} {tn}", meta, t_close[i], e["out"], e["pnl"], cost_bar[i] * scale,
                   a * scale, b * scale, d, exit_t, p_rand_for(tn))
    # H3: limit versus market entry from the same systematic decisions (every LIMIT_STEP-th 15-minute close)
    k = np.arange(0, len(P.t), LIMIT_STEP)
    t_dec, p_dec = P.t[k] + b2.PATH_SEC, P.c[k]
    sc_dec = p_dec / b2.REF_PRICE
    fills = {}
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        d_all = np.full(len(k), dv)
        j, okm = P.locate(t_dec)
        evm = P.evaluate(j[okm], p_dec[okm], d_all[okm], [(a * sc_dec[okm], b * sc_dec[okm]) for a, b in TARGETS.values()])
        for q, tn in enumerate(TARGETS):
            res["comparisons"][f"MARKET {tn} {dname}"] = {"n": int(okm.sum()), "win_rate": float(np.mean(evm[q]["out"] == 1))}
        for x in LIMIT_OFFSETS:
            filled, jj, fill = limit_fills(P, t_dec, p_dec, d_all, x * sc_dec)
            jj, fill, df_ = jj[filled], fill[filled], d_all[filled]
            sc_f = fill / b2.REF_PRICE
            for mode in ("conservative", "optimistic"):
                ok3, ev3 = evaluate_fills(P, jj, fill, df_, TARGETS, sc_f, mode)
                fills[(x, dname, mode)] = (jj, fill, df_, sc_f, ok3, ev3)
                for q, tn in enumerate(TARGETS):
                    res["comparisons"][f"LIMIT_{int(x)} {mode} {tn} {dname}"] = {
                        "decisions": len(k), "filled": len(jj), "fill_rate": float(len(jj) / len(k)), "n": int(ok3.sum()),
                        "win_rate": float(np.mean(ev3[q]["out"] == 1)) if ok3.any() else None}
    cat = np.concatenate
    for x in LIMIT_OFFSETS:
        for q, (tn, (a, b)) in enumerate(TARGETS.items()):
            parts = [fills[(x, dname, "conservative")] for dname in ("long", "short")]
            t_e = cat([P.t[jj[ok3]] + b2.PATH_SEC for jj, _, _, _, ok3, _ in parts])
            out = cat([ev3[q]["out"] for *_, ev3 in parts])
            pnl = cat([ev3[q]["pnl"] for *_, ev3 in parts])
            sc_ok = cat([sc_f[ok3] for _, _, _, sc_f, ok3, _ in parts])
            cost = cat([cost15[jj[ok3]] for jj, _, _, _, ok3, _ in parts]) * sc_ok
            dd = cat([df_[ok3] for _, _, df_, _, ok3, _ in parts])
            meta = {"tf": "15min", "setup": f"LIMIT_{int(x)}", "target": tn, "a_usd_at_4000": a, "b_usd_at_4000": b,
                    "data_hash": H.data_hash(m15), "decisions": int(2 * len(k)), "bound": "conservative"}
            _trial(res, registry, names, daily, f"15min LIMIT_{int(x)} {tn}", meta, t_e, out, pnl, cost, a * sc_ok, b * sc_ok, dd, None,
                   lambda st, tn=tn, cmp_=res["comparisons"]: (st["long"] * cmp_[f"MARKET {tn} long"]["win_rate"] + st["short"] * cmp_[f"MARKET {tn} short"]["win_rate"]) / st["n"],
                   one_pos=False)
    D = pd.DataFrame(daily).fillna(0.0).sort_index()
    D.index = pd.DatetimeIndex(D.index)
    W = D.groupby(pd.Grouper(freq="W")).sum()
    rc = H.reality_check(D[names].to_numpy(), B=1000, mean_block=10.0)
    tr_map = {t["id"]: t for t in res["trials"]}
    pv = [H.t_pvalue(tr_map[x]["t"], tr_map[x]["n"]) if tr_map[x]["n"] and tr_map[x]["t"] is not None else 1.0 for x in names]
    pv = [1.0 if not math.isfinite(v) else v for v in pv]
    bh = H.benjamini_hochberg(pv, q=0.10)
    for t_, okb in zip(names, bh):
        tr_map[t_]["pass"]["4_bh_fdr10"] = bool(okb)
        tr_map[t_]["pass"]["5_reality_check_p_below_0p05"] = bool(rc["p_value"] < 0.05)
        tr_map[t_]["passes_all"] = all(tr_map[t_]["pass"].values())
    res["family"] = {"trials": len(names), "reality_check": {**rc, "best_id": names[rc["best"]]}, "pbo": H.pbo_cscv(W[names].to_numpy(), groups=8),
                     "bh_fdr10_passed": [n_ for n_, okb in zip(names, bh) if okb], "passes_all": [t["id"] for t in res["trials"] if t.get("passes_all")],
                     "operator_target_90_lower_95": [t["id"] for t in res["trials"] if t["operator_target_90"]["lower_95"]]}
    with open(outp, "w") as f:
        json.dump(res, f, indent=1, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rd")
    ap.add_argument("out")
    ap.add_argument("--registry", default="research/trials.jsonl")
    a = ap.parse_args(argv)
    r = run(a.rd, a.out, a.registry)
    print(json.dumps(r["family"], indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
