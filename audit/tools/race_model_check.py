#!/usr/bin/env python3
"""Model check for the v14 race expectancy (F-A19) and the old marginal estimator.

WHAT THIS TESTS: the MATHEMATICS the Pine implements -- the first-touch race label
(stop first on a same-bar tie), the timeout mark-to-market term, and the expectancy
    E[R] = P(TP first) * RR - P(SL first) + E[timeout MTM]
-- re-implemented here and run on synthetic price paths whose true answer is known.

WHAT THIS DOES NOT TEST: the Pine source itself. It is a re-implementation, so a
transcription error in the .pine would not show up here. The compiler and the chart
are still the only test of the script. Nothing here uses XAUUSD history.

Known answers (booked fills are AT the level; the simulated path overshoots it between
substeps, which biases booked E[R] by about +delta*(P(loss)-P(win)), ~+0.03R here -- an
artefact of the simulation's discretisation, reported rather than hidden):
  * driftless (martingale) price, any RR: true bracket expectancy = 0 before cost,
    minus a small negative bias from the conservative same-bar tie rule.
  * positive drift: long expectancy > 0, short < 0.
  * driftless, RR 1: P(win | resolved) ~ 0.50 at EVERY horizon, while the unconditional
    P(win) falls with the horizon -- why the gate compares the conditional with 0.50.
The old estimator (pTP - pSL, a difference of marginal touch rates, F-038) has no
such property: under a fair game it reads strongly negative at RR 2-3.

Usage: python3 audit/tools/race_model_check.py [--seed N]
"""
import argparse
import random


def simulate(n_bars, drift, sub=24, seed=1):
    """Brownian bars: per-bar sigma = 1, built from `sub` substeps -> OHLC."""
    rng = random.Random(seed)
    s = 1.0 / sub ** 0.5
    mu = drift / sub
    px = 0.0
    O, H, L, C = [], [], [], []
    for _ in range(n_bars):
        o = px
        hi = lo = px
        for _ in range(sub):
            px += mu + rng.gauss(0.0, s)
            hi = max(hi, px)
            lo = min(lo, px)
        O.append(o)
        H.append(hi)
        L.append(lo)
        C.append(px)
    return H, L, C


def race_label(H, L, C, t, n, r):
    """Mirror of the Pine hRace/hTerm labelling for the entry at bar t."""
    ent = C[t]
    tu = [9999] * 4
    td = [9999] * 4
    for i, j in enumerate(range(t + 1, t + n + 1)):
        for k in (1, 2, 3):
            if tu[k] == 9999 and H[j] >= ent + k * r:
                tu[k] = i
            if td[k] == 9999 and L[j] <= ent - k * r:
                td[k] = i
    out = {}
    for k in (1, 2, 3):
        out[("L", k)] = 2 if td[1] < 9999 and td[1] <= tu[k] else 1 if tu[k] < 9999 else 0
        out[("S", k)] = 2 if tu[1] < 9999 and tu[1] <= td[k] else 1 if td[k] < 9999 else 0
    mtm = (C[t + n] - ent) / r
    # marginal touches, as the old _gHit histogram counted them
    mfe = (max(H[t + 1:t + n + 1]) - ent) / r
    mae = (ent - min(L[t + 1:t + n + 1])) / r
    return out, mtm, mfe, mae


def estimate(H, L, C, n, r):
    N = 0
    win = {}
    loss = {}
    tmo = {}
    touch_tp = {1: 0, 2: 0, 3: 0}
    touch_sl = 0
    for t in range(0, len(C) - n - 1):
        lab, mtm, mfe, mae = race_label(H, L, C, t, n, r)
        N += 1
        for key, o in lab.items():
            if o == 1:
                win[key] = win.get(key, 0) + 1
            elif o == 2:
                loss[key] = loss.get(key, 0) + 1
            else:
                tmo[key] = tmo.get(key, 0.0) + (mtm if key[0] == "L" else -mtm)
        for k in (1, 2, 3):
            touch_tp[k] += mfe >= k
        touch_sl += mae >= 1.0
    res = {}
    for side in ("L", "S"):
        for k in (1, 2, 3):
            key = (side, k)
            pw = win.get(key, 0) / N
            pl = loss.get(key, 0) / N
            pt = tmo.get(key, 0.0) / N
            res[key] = (pw, pl, pt, pw * k - pl + pt)
    old = {k: touch_tp[k] / N - touch_sl / N for k in (1, 2, 3)}
    return N, res, old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--bars", type=int, default=60000)
    a = ap.parse_args()
    r = 1.5  # R = 1.5 x per-bar sigma, the nominal stop
    fails = 0
    for drift in (0.0, 0.05):
        H, L, C = simulate(a.bars, drift, seed=a.seed)
        for n in (3, 12):
            N, res, old = estimate(H, L, C, n, r)
            se = 2.0 * (3.0 / N) ** 0.5 * n ** 0.5  # rough, overlap-inflated
            print(f"drift={drift:+.2f}/bar  horizon={n:2d} bars  N={N}")
            for k in (1, 2, 3):
                pw, pl, pt, evl = res[("L", k)]
                evs = res[("S", k)][3]
                cond = pw / (pw + pl) if pw + pl > 0 else float("nan")
                print(f"  RR {k}:  P(win) {pw:5.3f}  P(loss) {pl:5.3f}  P(win|res) {cond:5.3f}"
                      f"  tmoMTM {pt:+.3f}   E[R] long {evl:+.3f}  short {evs:+.3f}"
                      f"   old pTP-pSL {old[k]:+.3f}")
                if drift == 0.0:
                    ok = abs(evl) < 0.05 + se and abs(evs) < 0.05 + se
                else:
                    ok = evl > 0 and evs < 0
                fails += not ok
            print()
    print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails})",
          "-- model check of the estimator only; the Pine is NOT exercised")
    return fails


if __name__ == "__main__":
    raise SystemExit(main())
