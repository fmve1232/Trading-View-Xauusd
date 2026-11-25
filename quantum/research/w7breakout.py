"""B31b-W7 (research only; production never imports this module): the development study of the live M15 / M30 breakout
monitor (quantum/breakouts.py), registered in research/registrations/B31b-W7.json (+ amendment A1) before any code.

  (a) detection accuracy: an independent reference implementation of the registered rules (ref_detect / ref_follow,
      written again from the registration, sharing only the registered primitives: sessions.calendar,
      shadow.build_pools, shadow.session_label, ta.atr, ta.pivothigh / pivotlow) must reproduce the production
      detector's events and stages exactly on the development bars;
  (b) breakout quality: the stage rates (displacement, acceptance, retest held, failed before / after confirmation)
      by timeframe, direction, session and level kind;
  entries E0-E4 (the registered shadow entries) through B31b-W3's execution (fills, $650 sizing at the stop including
      the modelled cost, cost <= 15% of the stop, the +$10 / +$15 / +$20 races refined on M5, a 24 h time stop) plus
      the registered extension and room checks, one position at a time per variant and timeframe; against R1 (20
      random market entries in the same watch window, same direction, stop distance and targets) and R2 (the same
      moment, stop distance and targets, the opposite direction); 10 paired tests (variant x timeframe) of the
      +$10-first rate vs R1, day-clustered bootstrap, Holm-adjusted;
  features: section 4 of the directive, walk-forward (6 folds, purged) logistic models, baseline vs each group.

Distances are $ at $4,000 (scaled by price / 4,000) as in B31b-W3 .. W5. Development partition only: validation and
holdout are sealed (harness.partition refuses them without an approved registration; main() refuses them here
regardless). Nothing here is a probability shown to anyone; it is a measurement on development data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd

from .. import breakouts as B
from .. import sessions, shadow, ta
from . import harness as H
from . import w3liq as W
from .w4pull import holm

REG = "B31b-W7"
EPS = 1e-9
VARIANTS = ("E0", "E1", "E2", "E3", "E4")
NAMES = {"E0": "market at the breakout close", "E1": "market at the confirmation close",
         "E2": "limit at the level, placed at the confirmation close, valid 8 bars",
         "E3": "M5 resume after the confirmation close (within 4 bars of the timeframe)",
         "E4": "limit at the middle of a displacement breakout bar's body, valid 4 bars"}
E3_BARS, E4_BARS = 4, 4
K_RAND = 20
SEED = W.SEED
LEVEL_ORDER = {"PW": 0, "PD": 1, "AS": 2, "LO": 3, "NY": 4, "EQ": 5, "RG": 6, "SW": 7}


# ---------------- (a) the independent reference detector ----------------
def _rank(kind: str) -> int:
    return {"PW": 7, "PD": 6, "AS": 5, "LO": 5, "NY": 5, "EQ": 4, "RG": 3, "SW": 2}[kind[:2]]


def ref_detect(t, o, h, l, c, sec: int) -> list[dict]:
    """The registered breakout rules, written again. Every level is an instance with its own lifetime:
      static (PD / PW / session): a maximal run of bars over which the pool value is unchanged and finite;
      swing: reported by the 3/3 pivot at bar q, usable from q + 1 while its trading day is less than 5 after q's;
      equal highs / lows: an older and a newer live swing of a side, pivots >= 4 bars apart, within
        max($0.50, 0.10 x ATR at the newer one's report bar); the outer price; usable from the newer one's q + 1
        while both swings are live;
      range (A1): at bar i the box of bars i-12 .. i-1 when its height <= 1.5 x ATR[i-1] and no range broke after i-13.
    A level is consumed by the close that crosses it. One event per bar and side."""
    t = np.asarray(t, np.int64)
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    n = len(c)
    if n < 12 + 2 * 3 + 2:
        return []
    cal = sessions.calendar(pd.DatetimeIndex(pd.to_datetime(t, unit="s", utc=True)))
    pools, _ = shadow.build_pools(h, l, cal, np.full(n, np.nan), np.full(n, np.nan))
    atr = np.asarray(ta.atr(h, l, c, 14), float)
    day = pd.factorize(cal["trading_date"])[0]
    sess = shadow.session_label(cal)
    piv = {1: ta.pivothigh(h, 3, 3), -1: ta.pivotlow(l, 3, 3)}
    # swings and the equal pairs they form
    swings = {s: [{"id": ("SW", s, q), "v": float(piv[s][q]), "p": q - 3, "q": q, "day": int(day[q])}
                  for q in range(n) if np.isfinite(piv[s][q])] for s in (1, -1)}
    pairs = {1: {}, -1: {}}                        # by the newer swing's position in swings[s]
    for s in (1, -1):
        lo = 0
        for b_ in range(len(swings[s])):
            y = swings[s][b_]
            while lo < b_ and day[y["q"]] - swings[s][lo]["day"] >= 5:     # an older swing already dead by then
                lo += 1
            tol = max(0.5, 0.10 * atr[y["q"]]) if np.isfinite(atr[y["q"]]) else 0.5
            for x in swings[s][lo:b_]:
                if y["p"] - x["p"] >= 4 and abs(y["v"] - x["v"]) <= tol:
                    v = max(x["v"], y["v"]) if s == 1 else min(x["v"], y["v"])
                    pairs[s].setdefault(b_, []).append({"id": ("EQ", s, x["q"], y["q"]), "v": v, "x": x, "y": y})
    # static runs
    runs = {}
    for side, kinds in ((1, ("PWH", "PDH", "ASH", "LOH", "NYH")), (-1, ("PWL", "PDL", "ASL", "LOL", "NYL"))):
        for k in kinds:
            v = np.asarray(pools[k], float)
            start = np.zeros(n, int)
            for j in range(1, n):
                start[j] = start[j - 1] if v[j] == v[j - 1] else j
            runs[k] = (side, v, start)
    consumed: set = set()
    last_range = -10 ** 9
    out = []
    win = {1: [0, 0], -1: [0, 0]}                  # swings[s][lo:hi] = reported before i and not expired at i

    def sw_live(x, i):
        return x["q"] < i and day[i] - x["day"] < 5 and x["id"] not in consumed

    for i in range(1, n):
        for s in (1, -1):
            w_, S_ = win[s], swings[s]
            while w_[1] < len(S_) and S_[w_[1]]["q"] < i:
                w_[1] += 1
            while w_[0] < w_[1] and day[i] - S_[w_[0]]["day"] >= 5:
                w_[0] += 1
        box = None
        if i >= 12 and last_range < i - 12 and np.isfinite(atr[i - 1]):
            hi, lo = float(h[i - 12:i].max()), float(l[i - 12:i].min())
            if hi - lo <= 1.5 * atr[i - 1]:
                box = {1: hi, -1: lo}
        if not (np.isfinite(c[i]) and np.isfinite(c[i - 1])):
            continue
        for s in (1, -1):
            live = []
            for k, (side, v, start) in runs.items():
                if side == s and np.isfinite(v[i]) and (k, int(start[i])) not in consumed:
                    live.append((k, float(v[i]), (k, int(start[i]))))
            lo_, hi_ = win[s]
            live += [("SWH" if s == 1 else "SWL", x["v"], x["id"]) for x in swings[s][lo_:hi_] if sw_live(x, i)]
            live += [("EQH" if s == 1 else "EQL", p["v"], p["id"]) for b_ in range(lo_, hi_) for p in pairs[s].get(b_, ())
                     if p["id"] not in consumed and sw_live(p["x"], i) and sw_live(p["y"], i)]
            if box is not None:
                live.append(("RGH" if s == 1 else "RGL", box[s], ("RG", s, i)))
            hit = [x for x in live if s * (c[i] - x[1]) > EPS and s * (x[1] - c[i - 1]) >= -EPS]
            if not hit:
                continue
            for x in hit:
                consumed.add(x[2])
            if any(x[0][:2] == "RG" for x in hit):
                last_range = i
            near = sorted(hit, key=lambda x: (s * (x[1] - c[i - 1]), -_rank(x[0]), LEVEL_ORDER[x[0][:2]]))[0]
            top = sorted(hit, key=lambda x: (-_rank(x[0]), s * x[1], LEVEL_ORDER[x[0][:2]]))[0]
            a = float(atr[i - 1]) if np.isfinite(atr[i - 1]) else math.nan
            body = s * (c[i] - o[i])
            ahead = sorted({round(x[1], 2) for x in live if x[2] not in consumed and s * (x[1] - c[i]) > EPS},
                           key=lambda v: s * v)
            out.append({"i": i, "dir": s, "ref": round(near[1], 2), "ref_kind": near[0], "primary": top[0],
                        "levels": sorted((x[0], round(x[1], 2)) for x in hit), "disp": bool(a > 0 and body >= a - EPS),
                        "gap": bool(s * (o[i] - near[1]) > EPS), "sess": str(sess[i]), "atr": a,
                        "beyond": ahead[:B.BEYOND_KEEP]})
    return out


def ref_follow(ev: dict, h, l, c) -> dict:
    """The registered stages, written again: FAILED = the first close back inside within 16 bars; CONFIRMED = the
    breakout bar itself when it is a displacement bar, else bar i+2 when closes i+1 and i+2 are beyond; RETEST HELD =
    the first bar after the confirmation bar and before any failure that reaches the level (and so closes beyond it);
    CLOSED = bar i+16 when nothing failed and that bar exists."""
    i, s, L, n = ev["i"], ev["dir"], ev["ref"], len(c)
    end = min(i + 16, n - 1)
    js = np.arange(i + 1, end + 1)
    inside = js[s * (np.asarray(c)[js] - L) <= EPS]
    failed = int(inside[0]) if len(inside) else None
    if ev["disp"]:
        conf, how = i, "DISPLACEMENT"
    elif i + 2 <= end and (failed is None or failed > i + 2):
        conf, how = i + 2, "ACCEPTED"
    else:
        conf, how = None, None
    retest = None
    if conf is not None:
        stop_at = failed if failed is not None else end + 1
        for j in range(conf + 1, stop_at):
            if (l[j] <= L + EPS) if s == 1 else (h[j] >= L - EPS):
                retest = j
                break
    closed = i + 16 if failed is None and i + 16 <= n - 1 else None
    return {"confirmed": conf, "how": how, "retest": retest, "failed": failed, "closed": closed}


def detection_check(F) -> dict:
    """Production (breakouts.detect / follow) vs the reference on one timeframe's development bars, event by event."""
    prod, _ = B.detect(F.t, F.o, F.h, F.l, F.c, F.sec)
    ref = ref_detect(F.t, F.o, F.h, F.l, F.c, F.sec)
    P = {(e["i"], e["dir"]): e for e in prod}
    R = {(e["i"], e["dir"]): e for e in ref}
    only_p, only_r = sorted(set(P) - set(R)), sorted(set(R) - set(P))
    diff = []
    for k in sorted(set(P) & set(R)):
        p, r = P[k], R[k]
        pv = {"ref": p["ref"], "ref_kind": p["ref_kind"], "primary": p["primary"], "disp": p["disp"], "gap": p["gap"],
              "sess": p["sess"], "beyond": p["beyond"], "levels": sorted((x["kind"], x["price"]) for x in p["levels"])}
        rv = {k2: r[k2] for k2 in pv}
        sp = B.follow(p, F.o, F.h, F.l, F.c)
        sr = ref_follow(r, F.h, F.l, F.c)
        if pv != rv or sp != sr or not (p["atr"] == r["atr"] or (math.isnan(p["atr"]) and math.isnan(r["atr"]))):
            diff.append({"i": k[0], "dir": k[1], "t": int(F.t[k[0]]), "prod": {**pv, **sp}, "ref": {**rv, **sr}})
    return {"tf": F.tf, "bars": len(F.c), "events_production": len(prod), "events_reference": len(ref),
            "only_production": [list(x) for x in only_p[:20]], "n_only_production": len(only_p),
            "only_reference": [list(x) for x in only_r[:20]], "n_only_reference": len(only_r),
            "field_or_stage_differences": len(diff), "examples": diff[:10],
            "identical": not only_p and not only_r and not diff}


# ---------------- events, stages and the registered shadow entries ----------------
def events(F, score_from: int) -> list[dict]:
    """Production events of one timeframe with their stages; scored from score_from (the warm-up is skipped)."""
    evs, _ = B.detect(F.t, F.o, F.h, F.l, F.c, F.sec)
    out = []
    for ev in evs:
        if ev["t_close"] < score_from:
            continue
        st = B.follow(ev, F.o, F.h, F.l, F.c)
        out.append({**ev, "tf": F.tf, "st": st, "id": f"{F.tf}:{ev['t']}:{ev['dir']}"})
    return out


def _tc(F, j: int) -> int:
    return int(F.t[j]) + F.sec


def _opp(F, s: int, a: int, b: int) -> float:
    return float(F.l[a:b + 1].min()) if s == 1 else float(F.h[a:b + 1].max())


def e3_order(P, F, ev: dict, k: int, buf: float) -> dict | None:
    """E3: within E3_BARS bars of the timeframe after the confirmation close, the first M5 bar whose previous M5 bar made
    a pullback (a lower high for up, a higher low for down) and which closes beyond that previous bar's high (low); a
    market order at its close. Stop: the opposite extreme of bars i .. k and of the M5 bars up to it, less 0.2 ATR."""
    if P.t5 is None or not len(P.t5):
        return None
    s, t0 = ev["dir"], _tc(F, k)
    a, b = W.m5_span(P, t0, t0 + E3_BARS * F.sec)
    for j in range(max(a + 1, 2), b):
        prev, prev2 = j - 1, j - 2
        if s == 1 and P.h5[prev] < P.h5[prev2] and P.c5[j] > P.h5[prev]:
            pass
        elif s == -1 and P.l5[prev] > P.l5[prev2] and P.c5[j] < P.l5[prev]:
            pass
        else:
            continue
        ext = float(P.l5[a:j + 1].min()) if s == 1 else float(P.h5[a:j + 1].max())
        opp = min(_opp(F, s, ev["i"], k), ext) if s == 1 else max(_opp(F, s, ev["i"], k), ext)
        return {"m": "E3", "d": s, "kind": "MKT", "t": int(P.t5[j]) + 300, "px": float(P.c5[j]), "stop": opp - s * buf,
                "j": None}
    return None


def orders_for(P, F, ev: dict) -> list[dict]:
    """The registered shadow entries E0-E4 of one event (before eligibility)."""
    i, s, L = ev["i"], ev["dir"], ev["ref"]
    a = ev["atr"]
    if not (np.isfinite(a) and a > 0):
        return []
    buf = B.SL_BUF * a
    out = [{"m": "E0", "d": s, "kind": "MKT", "t": _tc(F, i), "px": float(F.c[i]), "stop": _opp(F, s, i, i) - s * buf, "j": i}]
    k = ev["st"]["confirmed"]
    if k is not None:
        stop = _opp(F, s, i, k) - s * buf
        out.append({"m": "E1", "d": s, "kind": "MKT", "t": _tc(F, k), "px": float(F.c[k]), "stop": stop, "j": k})
        out.append({"m": "E2", "d": s, "kind": "LIM", "t": _tc(F, k), "px": float(L), "stop": stop, "j": k,
                    "valid": k + B.RETEST_VALID})
        o3 = e3_order(P, F, ev, k, buf)
        if o3 is not None:
            out.append(o3)
    if ev["disp"]:
        out.append({"m": "E4", "d": s, "kind": "LIM", "t": _tc(F, i), "px": (float(F.o[i]) + float(F.c[i])) / 2.0,
                    "stop": _opp(F, s, i, i) - s * buf, "j": i, "valid": i + E4_BARS})
    for od in out:
        od.update(ev_id=ev["id"], L=float(L))
    return out


def checks(row: dict, ev: dict) -> list[str]:
    """The registered ENTRY READY checks beyond W3's size and cost: extension (entry at most 1 ATR beyond the level) and
    room (no unbroken same-side level within $10, scaled, ahead of the entry). Distances at the fill price."""
    why = []
    s, e, sc = ev["dir"], row["e"], row["s"]
    if s * (e - ev["ref"]) > B.EXT_ATR * ev["atr"] + EPS:
        why.append("extension")
    room = [s * (v - e) for v in ev["beyond"] if s * (v - e) > EPS]
    if room and min(room) < B.ROOM_USD * sc - EPS:
        why.append("room")
    return why


def run_entries(P, F, evs: list[dict]) -> list[dict]:
    rows = []
    by = {ev["id"]: ev for ev in evs}
    for ev in evs:
        for od in orders_for(P, F, ev):
            r = W.execute(P, F, od)
            r.update(tf=F.tf, ev_id=od["ev_id"], sess=ev["sess"], ref_kind=ev["ref_kind"])
            if r["status"] == "FILLED":
                extra = checks(r, by[od["ev_id"]])
                r["checks"] = extra
                r["ready"] = bool(r.get("eligible")) and not extra
            rows.append(r)
    return rows


# ---------------- controls ----------------
def _start(P, r: dict) -> tuple[int, tuple[int, int] | None]:
    """Where a trade's race starts (the bar after a limit's fill bar; a market fill's own bar, or its M5 remainder)."""
    t = int(r["t_fill"])
    if r["kind"] != "MKT":
        return W.k_at(P, t) + 1, None
    if t % 900:
        nxt = t - (t % 900) + 900
        return W.k_at(P, nxt), (t, nxt)
    return W.k_at(P, t), None


def controls(P, F_by_tf: dict, rows: list[dict], evs_by_id: dict, k: int = K_RAND) -> dict:
    """R1 per trade: k random 15m closes from the breakout close to the end of its watch, same direction, stop distance
    (scaled) and targets; R2 per trade: the same start, stop distance and targets, the opposite direction. Returns
    {id(row): {"r1_tp10_rate", "r1_mean_r", "r1": {tp: [k, n]}, "r2": {tp: out}, "r2_r": float}}."""
    out = {}
    for r in rows:
        ev = evs_by_id[r["ev_id"]]
        F = F_by_tf[ev["tf"]]
        i = ev["i"]
        kb = W.k_at(P, _tc(F, i)) - 1
        ke = W.k_at(P, _tc(F, min(i + B.WATCH, len(F.c) - 1))) - 1
        ke = min(ke, len(P.c) - 2)
        g = H.seeded_rng(SEED + (int(r["t_fill"]) % 1000003) * 7 + VARIANTS.index(r["m"]) * 2 + (1 if r["d"] == 1 else 0))
        r1 = {f"tp{int(T)}": [0, 0] for T in W.TP}
        rr10 = []
        if ke >= kb >= 0:
            for b in g.integers(kb, ke + 1, size=k):
                e = float(P.c[b])
                sc = e / 4000.0
                stop = e - r["d"] * r["D"] * sc
                cost = float(P.cost[b])
                for T in W.TP:
                    res, _, px, _ = W.race_fast(P, int(b) + 1, r["d"], e, stop, e + r["d"] * T * sc)
                    if res not in ("TP", "SL", "AMBIGUOUS", "TIMEOUT"):
                        continue
                    key = f"tp{int(T)}"
                    r1[key][1] += 1
                    r1[key][0] += int(res == "TP")
                    if key == "tp10":
                        rr10.append((r["d"] * (px - e) / sc - cost) / (r["D"] + cost))
        k0, pre = _start(P, r)
        e, sc, d2 = r["e"], r["s"], -r["d"]
        stop2 = e - d2 * r["D"] * sc
        r2, r2r = {}, math.nan
        for T in W.TP:
            res, _, px, _ = W.race(P, k0, d2, e, stop2, e + d2 * T * sc, pre)
            r2[f"tp{int(T)}"] = res
            if T == 10.0 and res in ("TP", "SL", "AMBIGUOUS", "TIMEOUT") and np.isfinite(px):
                r2r = (d2 * (px - e) / sc - r["cost"]) / (r["D"] + r["cost"])
        out[id(r)] = {"r1": r1, "r1_tp10_rate": r1["tp10"][0] / r1["tp10"][1] if r1["tp10"][1] else math.nan,
                      "r1_mean_r": float(np.mean(rr10)) if rr10 else math.nan, "r2": r2, "r2_r": r2r}
    return out


# ---------------- statistics ----------------
def boot_p(x: np.ndarray, day: np.ndarray, B_: int = W.BOOT) -> tuple[list[float], float]:
    """Day-clustered bootstrap 95% interval of the mean and the one-sided p of mean <= 0."""
    if len(x) < 3:
        return [math.nan, math.nan], math.nan
    u, inv = np.unique(day, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=x), np.bincount(inv)
    pick = H.seeded_rng(SEED).integers(0, len(u), size=(B_, len(u)))
    m = sums[pick].sum(axis=1) / cnts[pick].sum(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))], float((m <= 0).mean())


def counted(rows: list[dict], m: str, tf: str) -> list[dict]:
    """ENTRY READY trades of one variant and timeframe, one position at a time."""
    return W.one_position([r for r in rows if r["m"] == m and r["tf"] == tf and r["status"] == "FILLED" and r.get("ready")])


def stage_rates(evs: list[dict]) -> dict:
    """Registered rates over events whose watch ended (failed or closed), and the raw counts."""
    def block(xs):
        done = [e for e in xs if e["st"]["failed"] is not None or e["st"]["closed"] is not None]
        n = len(done)
        conf = [e for e in done if e["st"]["confirmed"] is not None]
        fb = sum(1 for e in done if e["st"]["failed"] is not None and e["st"]["confirmed"] is None)
        fa = sum(1 for e in done if e["st"]["failed"] is not None and e["st"]["confirmed"] is not None)
        return {"events": len(xs), "watch_ended": n,
                "displacement": W.rate(sum(e["disp"] for e in done), n),
                "accepted": W.rate(sum(1 for e in done if e["st"]["how"] == "ACCEPTED"), n),
                "confirmed": W.rate(len(conf), n),
                "retest_held": W.rate(sum(1 for e in done if e["st"]["retest"] is not None), n),
                "failed_before_confirmation": W.rate(fb, n), "failed_after_confirmation": W.rate(fa, n),
                "not_failed_in_watch": W.rate(n - fb - fa, n)}
    out = {"all": block(evs)}
    for name, f in (("tf", lambda e: e["tf"]), ("dir", lambda e: "BUY" if e["dir"] == 1 else "SELL"),
                     ("session", lambda e: e["sess"]), ("ref_kind", lambda e: e["ref_kind"][:2]),
                     ("primary", lambda e: e["primary"][:2])):
        out[name] = {k: block([e for e in evs if f(e) == k]) for k in sorted({f(e) for e in evs})}
    out["tf_x_dir"] = {f"{tf}:{d}": block([e for e in evs if e["tf"] == tf and e["dir"] == d])
                       for tf in sorted({e["tf"] for e in evs}) for d in (1, -1)}
    return out


def variant_summary(u: list[dict], ctl: dict) -> dict:
    s = W.summarize(u)
    dec = [r for r in u if W.decided(r)]
    if not dec:
        return s
    day = np.array([r["t_fill"] // 86400 for r in dec])
    tp = np.array([float(r["tp10"] == "TP") for r in dec])
    c1 = np.array([ctl[id(r)]["r1_tp10_rate"] for r in dec], float)
    ok = np.isfinite(c1)
    ci, p = boot_p(tp[ok] - c1[ok], day[ok])
    s["vs_R1_tp10_rate"] = {"n": int(ok.sum()), "trade_rate": float(tp[ok].mean()) if ok.any() else math.nan,
                            "r1_rate": float(c1[ok].mean()) if ok.any() else math.nan,
                            "mean_diff": float((tp[ok] - c1[ok]).mean()) if ok.any() else math.nan, "boot95": ci,
                            "p_one_sided": p}
    rr = np.array([r["tp10_r"] for r in dec], float)
    m1 = np.array([ctl[id(r)]["r1_mean_r"] for r in dec], float)
    okr = np.isfinite(rr) & np.isfinite(m1)
    ci2, p2 = boot_p(rr[okr] - m1[okr], day[okr])
    s["vs_R1_net_r"] = {"n": int(okr.sum()), "mean_diff_r": float((rr[okr] - m1[okr]).mean()) if okr.any() else math.nan,
                        "boot95": ci2, "p_one_sided": p2}
    r2r = np.array([ctl[id(r)]["r2_r"] for r in dec], float)
    r2tp = sum(1 for r in dec if ctl[id(r)]["r2"]["tp10"] == "TP")
    ok2 = np.isfinite(r2r) & np.isfinite(rr)
    ci3, p3 = boot_p(rr[ok2] - r2r[ok2], day[ok2])
    s["vs_R2_opposite"] = {"r2_tp10_first": W.rate(r2tp, len(dec)), "mean_diff_r": float((rr[ok2] - r2r[ok2]).mean())
                           if ok2.any() else math.nan, "boot95": ci3, "p_one_sided": p3}
    ci4, _ = boot_p(np.nan_to_num(rr), day)
    s["tp10_mean_net_r_boot95_day"] = ci4
    s["by_dir"] = {("BUY" if d == 1 else "SELL"): W.summarize([r for r in u if r["d"] == d]) for d in (1, -1)}
    s["by_session"] = {k: {"n": len(v), "tp10_first": sum(r["tp10"] == "TP" for r in v),
                           "mean_net_r": float(np.nanmean([r["tp10_r"] for r in v]))}
                       for k, v in sorted(_group(dec, lambda r: r["sess"]).items())}
    return s


def _group(xs, f) -> dict:
    g = {}
    for x in xs:
        g.setdefault(f(x), []).append(x)
    return g


def funnel(rows: list[dict], m: str, tf: str) -> dict:
    mr = [r for r in rows if r["m"] == m and r["tf"] == tf]
    st = {}
    for r in mr:
        if r["status"] != "FILLED":
            k = f"{r['status']}:{r.get('why')}"
        elif r.get("ready"):
            k = "READY"
        else:
            k = "NOT_READY:" + ",".join(([r["why"]] if r.get("why") else []) + r.get("checks", []))
        st[k] = st.get(k, 0) + 1
    return {"orders": len(mr), **dict(sorted(st.items()))}


# ---------------- features (section 4) and the walk-forward models ----------------
SESS5 = ("ASIAN", "LONDON", "LONDON+NY", "NEW YORK", "OFF")
KINDS = ("PW", "PD", "AS", "LO", "NY", "EQ", "RG", "SW")
BASE = ("D0", "cost", "atr_s") + tuple(f"s_{x}" for x in SESS5)
GROUPS = {"candle": ("pen_atr", "body_range", "wick_with", "wick_against", "body_atr"),
          "mtf_alignment": ("align",), "room": ("opp_atr", "room_usd"), "cost_stop": ("cost_stop",),
          "regime": ("atr_pct100", "er20"), "level": tuple(f"k_{x}" for x in KINDS) + ("n_levels",)}


def features(P, F, ev: dict, other: list[dict]) -> dict:
    i, s = ev["i"], ev["dir"]
    o_, h_, l_, c_ = (float(x[i]) for x in (F.o, F.h, F.l, F.c))
    a, sc = ev["atr"], c_ / 4000.0
    rng = max(h_ - l_, 1e-9)
    stop0 = _opp(F, s, i, i) - s * B.SL_BUF * a
    D0 = s * (c_ - stop0) / sc
    kd = min(max(W.k_at(P, _tc(F, i)) - 1, 0), len(P.c) - 1)
    cost = float(P.cost[kd])
    ahead = [s * (v - c_) for v in ev["beyond"] if s * (v - c_) > EPS]
    opp = min(ahead) if ahead else math.nan
    lo = max(0, i - 100)
    hist = F.atr[lo:i]
    hist = hist[np.isfinite(hist)]
    tcl = ev["t_close"]
    f = {"D0": D0, "cost": cost, "atr_s": a / sc, "pen_atr": s * (c_ - ev["ref"]) / a,
         "body_range": abs(c_ - o_) / rng,
         "wick_with": ((h_ - max(o_, c_)) if s == 1 else (min(o_, c_) - l_)) / rng,
         "wick_against": ((min(o_, c_) - l_) if s == 1 else (h_ - max(o_, c_))) / rng,
         "body_atr": ev["body_atr"] if np.isfinite(ev["body_atr"]) else 0.0,
         "align": float(any(x["dir"] == s and tcl - 3600 <= x["t_close"] <= tcl for x in other)),
         "opp_atr": min(opp / a, 10.0) if np.isfinite(opp) else 10.0,
         "room_usd": min(opp / sc, 50.0) if np.isfinite(opp) else 50.0,
         "cost_stop": cost / D0 if D0 > 0 else 1.0,
         "atr_pct100": float((hist < a).mean()) if len(hist) else 0.5,
         "er20": float(F.er20[i]) if np.isfinite(F.er20[i]) else 0.0,
         "n_levels": float(len(ev["levels"]))}
    for x in SESS5:
        f[f"s_{x}"] = float(ev["sess"] == x)
    for x in KINDS:
        f[f"k_{x}"] = float(ev["primary"][:2] == x)
    return f


def wf(X: np.ndarray, y: np.ndarray, t: np.ndarray, t_end: np.ndarray, t_lo: int, t_hi: int, folds: int = 6) -> np.ndarray:
    """Out-of-fold p for folds 2..k: each fold predicted by a model trained on earlier rows whose outcome window ends
    before the fold starts (purge)."""
    edges = np.linspace(t_lo, t_hi, folds + 1)
    p = np.full(len(y), np.nan)
    for f in range(1, folds):
        te = (t >= edges[f]) & (t < edges[f + 1])
        tr = t_end < edges[f]
        if te.sum() == 0 or tr.sum() < 30 or len(np.unique(y[tr])) < 2:
            continue
        Xtr, Xte, _, _ = W.standardize(X[tr], X[te])
        p[te] = W.logit_pred(W.logit_fit(Xtr, y[tr]), Xte)
    return p


def predictive(rows: list[dict], y: np.ndarray, t: np.ndarray, t_end: np.ndarray, t_lo: int, t_hi: int) -> dict:
    if len(rows) < 200 or len(np.unique(y)) < 2:
        return {"n": len(rows), "note": "too few rows"}
    day = t // 86400
    sets = {"baseline": BASE, **{f"+{g}": BASE + cols for g, cols in GROUPS.items()},
            "+all": BASE + tuple(c for cols in GROUPS.values() for c in cols)}
    ll = lambda p: -(y * np.log(np.clip(p, 1e-9, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-9, 1)))   # noqa: E731
    pr = {k: wf(W.matrix(rows, cols), y, t, t_end, t_lo, t_hi) for k, cols in sets.items()}
    ok = np.isfinite(pr["baseline"])
    base_ll = ll(pr["baseline"])
    out = {"n": len(rows), "n_oof": int(ok.sum()), "base_rate_oof": float(y[ok].mean()) if ok.any() else math.nan, "sets": {}}
    for k, p in pr.items():
        m = ok & np.isfinite(p)
        dll = base_ll[m] - ll(p)[m]
        out["sets"][k] = {"n": int(m.sum()), "logloss_oof": float(np.mean(ll(p)[m])),
                          "gain_vs_baseline_per_row": float(np.mean(dll)), "gain_boot95": W.boot_mean(dll, day[m]),
                          "brier_oof": float(np.mean((p[m] - y[m]) ** 2)), "auc_oof": W.auc(p[m], y[m])}
    return out


# ---------------- a run ----------------
def code_sha() -> str:
    return hashlib.sha256(open(__file__, "rb").read()).hexdigest()


def build(m15: pd.DataFrame, h1: pd.DataFrame, m5: pd.DataFrame | None, score_from: int) -> dict:
    P, F15, F30, incomplete = W.frames(m15, h1, m5)
    Fs = {"M15": F15, "M30": F30}
    det = {tf: detection_check(F) for tf, F in Fs.items()}
    evs = {tf: events(F, score_from) for tf, F in Fs.items()}
    rows = []
    for tf, F in Fs.items():
        rows += run_entries(P, F, evs[tf])
    return {"P": P, "F": Fs, "events": evs, "rows": rows, "detection": det, "incomplete_m30": incomplete,
            "score_from": score_from, "t_end": int(P.t[-1]) + 900}


def analyse(res: dict) -> dict:
    P, Fs, evs, rows = res["P"], res["F"], res["events"], res["rows"]
    allev = evs["M15"] + evs["M30"]
    by_id = {e["id"]: e for e in allev}
    out = {"detection_accuracy": res["detection"], "stage_rates": stage_rates(allev), "variants": {}, "funnel": {}}
    us = {(m, tf): counted(rows, m, tf) for m in VARIANTS for tf in Fs}
    ctl = controls(P, Fs, [r for u in us.values() for r in u if W.decided(r)], by_id)
    ps = {}
    for (m, tf), u in us.items():
        key = f"{m}:{tf}"
        out["funnel"][key] = funnel(rows, m, tf)
        s = variant_summary(u, ctl)
        out["variants"][key] = {"name": NAMES[m], **s}
        ps[key] = (s.get("vs_R1_tp10_rate") or {}).get("p_one_sided")
    hp = holm(ps)
    verdict = {}
    for key, s in out["variants"].items():
        lb = (s.get("tp10_mean_net_r_boot95_day") or [math.nan])[0]
        mr = (s.get("tp10") or {}).get("mean_net_r", math.nan)
        verdict[key] = {"n": s.get("n", 0), "holm_p": hp.get(key), "mean_net_r": mr, "mean_net_r_lb95": lb,
                        "candidate": bool(hp.get(key) is not None and hp[key] < 0.05 and np.isfinite(mr) and mr > 0
                                          and np.isfinite(lb) and lb > 0)}
    out["verdict"] = verdict
    out["overall"] = ("CANDIDATE(S): " + ", ".join(k for k, v in verdict.items() if v["candidate"])
                      if any(v["candidate"] for v in verdict.values()) else "NO CANDIDATE")
    # features: (A) no FAILED within the watch, every event whose watch ended; (B) +$10-first of E1 (every fill)
    feat = {}
    for tf, F in Fs.items():
        other = evs["M30" if tf == "M15" else "M15"]
        for e in evs[tf]:
            feat[e["id"]] = features(P, F, e, other)
    A = [e for e in allev if e["st"]["failed"] is not None or e["st"]["closed"] is not None]
    ya = np.array([float(e["st"]["failed"] is None) for e in A])
    ta_ = np.array([e["t_close"] for e in A], np.int64)
    tea = np.array([e["t_close"] + B.WATCH * Fs[e["tf"]].sec for e in A], np.int64)
    rowsA = [dict(feat[e["id"]], tf30=float(e["tf"] == "M30")) for e in A]
    out["features_no_failure"] = predictive(rowsA, ya, ta_, tea, res["score_from"], res["t_end"])
    E1 = [r for r in rows if r["m"] == "E1" and r["status"] == "FILLED" and W.decided(r)]
    rowsB = [dict(feat[r["ev_id"]], D0=r["D"], cost=r["cost"]) for r in E1]
    yb = np.array([float(r["tp10"] == "TP") for r in E1])
    tb = np.array([r["t_fill"] for r in E1], np.int64)
    out["features_e1_tp10_first"] = predictive(rowsB, yb, tb, tb + W.HOLD_SEC, res["score_from"], res["t_end"])
    out["events_total"] = {"M15": len(evs["M15"]), "M30": len(evs["M30"])}
    out["incomplete_m30_bars"] = res["incomplete_m30"]
    out["m5_coverage"] = W.m5_coverage(P, int(np.searchsorted(P.t, res["score_from"]))) if P.t5 is not None else 0.0
    return out


TRADE_COLS = ("m", "tf", "d", "ev_id", "t_dec", "t_fill", "kind", "status", "why", "eligible", "ready", "checks", "sess",
              "ref_kind", "e", "stop", "D", "cost", "lots", "tp10", "tp15", "tp20", "tp10_r", "tp15_r", "tp20_r", "mfe",
              "mae", "loss_usd")


def trades_csv(rows: list[dict], path: str) -> None:
    pd.DataFrame([{k: (",".join(r[k]) if isinstance(r.get(k), list) else r.get(k)) for k in TRADE_COLS} for r in rows]).to_csv(
        path, index=False)


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", default="development")
    ap.add_argument("--rd", required=True, help="research-data clone (development)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv")
    a = ap.parse_args(argv)
    if a.part != "development":
        raise H.SealedPartition(f"{REG}: only the development partition is registered for this study")
    m15, h1, m5, score_from = W.load(a.rd, "development", None)
    res = build(m15, h1, m5, score_from)
    out = analyse(res)
    out.update(registration=REG, part=a.part, code_sha256=code_sha(),
               breakouts_sha256=hashlib.sha256(open(B.__file__, "rb").read()).hexdigest(),
               data={"m15_bars": len(m15), "first": str(m15.index[0]), "last": str(m15.index[-1]),
                     "score_from": pd.Timestamp(score_from, unit="s", tz="UTC").isoformat()})
    with open(a.out, "w") as fh:
        json.dump(_clean(out), fh, indent=1)
    if a.csv:
        trades_csv(res["rows"], a.csv)
    print(json.dumps({"overall": out["overall"], "events": out["events_total"],
                      "detection_identical": {k: v["identical"] for k, v in out["detection_accuracy"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
