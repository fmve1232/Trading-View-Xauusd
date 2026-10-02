#!/usr/bin/env python3
"""Run the probability / statistics formulas AS WRITTEN in a .pine file against references.

Each block is read out of the artefact by anchor text (not re-typed) and executed with
pine_exec.py on random inputs, then compared with an independent first-principles
computation. A transcription error in the Pine therefore shows up here, which is what
formula_check.py (re-typed maths) cannot catch. It still is not the TradingView runtime:
the compiler and the chart remain the final test (CLAUDE.md).

Blocks: Wilson lower bound + Kelly (dashboard sizing) | race-grid interpolation |
plan-probability CI half-width | Platt/WLS calibration fit | Murphy Brier decomposition |
tanh squash in trade quality | inverse Cornish-Fisher (Newton) | race expectancy.

Usage: python3 audit/tools/formula_trace.py [artefacts/XAUUSD_Quantum_5_0_Master.pine ...]
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

rng = random.Random(11)
fails = 0
notes = []


def ok(name, cond, detail):
    global fails
    fails += not cond
    print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")


def close(a, b, tol=1e-9):
    return (P.isna(a) and P.isna(b)) or abs(a - b) <= tol * max(1.0, abs(b))


def wilson_low(p, n, z=1.96):
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h


def test_kelly(path):
    blk, ln = P.extract(path, r'float _brK = nz\(array.get\(gOosBearWr', r'float _rawKelly =')
    worst = 0.0
    for _ in range(3000):
        wr, br = rng.uniform(5, 45), rng.uniform(5, 45)
        N, OUT = rng.randint(30, 3000), rng.choice([1, 3, 12])
        aw, al = rng.uniform(0.3, 3), rng.uniform(0.3, 2)
        env = P.Env(oOosWr=wr, gOosBearWr=[br], tpIsLong=rng.random() < .5, oOosN=N, OUTCOME_N=OUT,
                    oAvgW=aw, oAvgL=al, oAvgWOos=rng.choice([0.0, aw]), oAvgLOos=rng.choice([0.0, al]))
        P.run(blk, env)
        pw, pl = (wr, br) if env['tpIsLong'] else (br, wr)
        res = (wr + br) / 100.0
        neff = max(N * res / OUT, 1.0)
        p = max(wilson_low((pw / 100.0) / res, neff), 0.01)
        W = env['oAvgWOos'] if env['oAvgWOos'] > 0 else aw
        Lz = env['oAvgLOos'] if env['oAvgLOos'] > 0 else al
        b = W / max(abs(Lz), 0.01)
        ref = (p * b - (1 - p)) / b * 100.0
        worst = max(worst, abs(env['_rawKelly'] - ref))
    ok("Wilson-low p' and Kelly f* (dashboard sizing)", worst < 1e-9, f"L{ln}, 3000 random cases, max |diff| {worst:.1e}")
    # optimality of the form (p'b - q')/b for the bet on resolved outcomes
    p_, b_ = 0.42, 1.8
    grid = max((p_ * math.log(1 + f * b_) + (1 - p_) * math.log(1 - f), f) for f in [i / 10000 for i in range(9999)])[1]
    ok("Kelly form is the log-growth optimum", abs(grid - (p_ * b_ - (1 - p_)) / b_) < 2e-4, f"argmax {grid:.4f} vs formula {(p_ * b_ - (1 - p_)) / b_:.4f}")


def test_grid(path):
    blk, ln = P.extract(path, r'^f_gridInterp\(', r'^f_gridInterp\(')
    body = blk[0].split('=>', 1)[1] if '=>' in blk[0] else None
    if body is None or not body.strip():
        L = open(path, encoding='utf-8').read().split('\n')
        body = L[ln]
    worst = 0.0
    for _ in range(5000):
        rr = rng.uniform(-0.5, 5)
        p = [rng.uniform(0, 100) for _ in range(4)]
        dec = rng.random() < .5
        env = P.Env(_rr=rr, _p0=p[0], _p1=p[1], _p2=p[2], _p3=p[3], _decay=dec)
        got = P.evaluate(body, env)
        if rr <= 0:
            ref = p[0]
        elif rr <= 3:
            k = min(int(math.ceil(rr)) - 1, 2) if rr > 0 else 0
            k = 0 if rr <= 1 else 1 if rr <= 2 else 2
            ref = p[k] + (p[k + 1] - p[k]) * (rr - k)
        else:
            ref = p[3] * 0.7 ** (rr - 3) if dec else p[3]
        worst = max(worst, abs(got - ref))
    ok("race-grid interpolation (0..3 linear, decay beyond)", worst < 1e-9, f"L{ln}, 5000 cases, max |diff| {worst:.1e}")


def test_ci(path):
    blk, ln = P.extract(path, r'^f_ciHalf\(', r'_ciN >= 3 \?')
    worst, maxw = 0.0, 0.0
    for _ in range(2000):
        pp, n = rng.uniform(0, 100), rng.uniform(3, 500)
        env = P.Env(_pPct=pp, _ciN=n)
        P.run(blk[1:-1], env)
        got = P.evaluate(blk[-1].strip(), env)
        p = pp / 100
        ref = 164.5 * math.sqrt(p * (1 - p) / (n + 3.0))
        worst = max(worst, abs(got - ref))
        # Wilson 90% half-width in percent, for comparison
        z = 1.645
        wil = 100 * z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        maxw = max(maxw, abs(got - wil))
    ok("plan-probability +/- half-width", worst < 1e-9, f"L{ln}: 1.645*sqrt(p(1-p)/(n+3)) = a 90% interval, max |diff| {worst:.1e}")
    notes.append(f"f_ciHalf (L{ln}) is a 90% interval (z = 1.645) on the effective sample; the dashboard prints it as a bare '±'. "
                 f"It differs from a Wilson 90% half-width by up to {maxw:.1f} points over n 3-500 (largest at small n, extreme p).")


def test_platt(path):
    """Reference: Berkson-weighted WLS of logit(bin rate) on (bin mean score - 50), with the slope
    constrained to the monotone direction (>= 0) by PROJECTION and the intercept re-solved for the
    slope used (the constrained least-squares optimum). Every refresh updates the fit."""
    blk, ln = P.extract(path, r'float _pfSw = 0\.0', r'array.set\(gCalFit, 1,')
    worst, n, stale, floor, offc = 0.0, 0, 0, 0, 0
    for _ in range(2000):
        t = [rng.randint(0, 400) for _ in range(5)]
        s_ = [t[k] * rng.uniform(10 + 15 * k, 25 + 15 * k) for k in range(5)]
        b = [rng.randint(0, x) if x else 0 for x in t]
        env = P.Env(funcs={'bayesRate': lambda w, m: (w + 1) / (m + 2) if m > 0 else 0.5},
                    gCalFit=[0.123, 0.456], c0t=t[0], c1t=t[1], c2t=t[2], c3t=t[3], c4t=t[4],
                    c0s=s_[0], c1s=s_[1], c2s=s_[2], c3s=s_[3], c4s=s_[4], c0b=b[0], c1b=b[1], c2b=b[2], c3b=b[3], c4b=b[4])
        P.run(blk, env)
        pts = []
        for k in range(5):
            if t[k] >= 30:
                ar = min(max((b[k] + 1) / (t[k] + 2), 0.05), 0.95)
                pts.append((s_[k] / t[k] - 50, math.log(ar / (1 - ar)), t[k] * ar * (1 - ar)))
        if len(pts) < 3:
            continue
        n += 1
        Sw = sum(w for _, _, w in pts)
        mx = sum(w * x for x, _, w in pts) / Sw
        my = sum(w * y for _, y, w in pts) / Sw
        vr = sum(w * (x - mx) ** 2 for x, _, w in pts) / Sw
        K = sum(w * (x - mx) * (y - my) for x, y, w in pts) / Sw / vr if vr > 1e-6 else 0.0
        refK = min(max(K, 0.0), 0.25)
        refA = min(max(my - refK * mx, -5.0), 5.0)
        g = env['gCalFit']
        if g == [0.123, 0.456]:
            stale += 1
            continue
        d = max(abs(g[0] - refK), abs(g[1] - refA))
        floor += abs(g[0] - refK) > 1e-9
        offc += abs(g[0] - refK) <= 1e-9 and abs(g[1] - refA) > 1e-9
        worst = max(worst, d)
    ok("Platt/WLS calibration = constrained least squares", worst < 1e-9 and stale == 0,
       f"L{ln}, {n} fits: stale (not updated) {stale}, slope != projection {floor}, "
       f"intercept off the weighted centroid {offc}, max |diff| {worst:.2g}")


def test_brier(path):
    blk, ln = P.extract(path, r'float _totalCal = c0t \+ c1t', r'_cCalBrier := _totalCal > 0')
    worst = 0.0
    for _ in range(2000):
        t = [rng.randint(0, 300) for _ in range(5)]
        if sum(t) == 0:
            continue
        s = [t[k] * rng.uniform(5, 95) for k in range(5)]
        b = [rng.randint(0, x) if x else 0 for x in t]
        env = P.Env(c0t=t[0], c1t=t[1], c2t=t[2], c3t=t[3], c4t=t[4], c0s=s[0], c1s=s[1], c2s=s[2], c3s=s[3], c4s=s[4],
                    c0b=b[0], c1b=b[1], c2b=b[2], c3b=b[3], c4b=b[4], _cCalBrier=P.NA, gCalRel=[P.NA] * 16)
        P.run(blk, env)
        N = sum(t)
        bs = sum(b[k] * (1 - s[k] / t[k] / 100) ** 2 + (t[k] - b[k]) * (s[k] / t[k] / 100) ** 2 for k in range(5) if t[k]) / N
        worst = max(worst, abs(env['_cCalBrier'] - bs))
    ok("Murphy decomposition = Brier score of bin-mean forecasts", worst <= 0.0005 + 1e-12,
       f"L{ln}, 2000 cases, max |diff| {worst:.4f} (display rounds to 3 dp)")


def test_tanh(path):
    blk, ln = P.extract(path, r'float _tqTx = ', r'float _tqFc = ')
    worst = 0.0
    for _ in range(2000):
        x = rng.uniform(-12, 12)
        env = P.Env(planExpectancy=x)
        P.run(blk, env)
        ref = 50 + 50 * math.tanh(max(min(x / 0.75, 10), -10))
        worst = max(worst, abs(env['_tqFc'] - ref))
    ok("trade-quality expectancy squash = 50 + 50 tanh(EV/0.75)", worst < 1e-9, f"L{ln}, max |diff| {worst:.1e}")


def test_cf(path):
    blk, ln = P.extract(path, r'^float _cfK = ', r'^    retZScore := _w')
    worst = 0.0
    nonmono = bad = 0
    for _ in range(2000):
        S, K, x = rng.uniform(-1.4, 1.4), rng.uniform(-0.9, 6.5), rng.uniform(-4, 4)
        Sc = max(min(S, 1.0), -1.0)
        env = P.Env(retKurt=K, retSkew=S, retSkewC=Sc, _cfValid=True, retZScoreRaw=x)
        P.run(blk, env)
        Kc = max(min(K, 3.0), -1.0)
        q = lambda w: w + (w * w - 1) * Sc / 6 + (w ** 3 - 3 * w) * Kc / 24 - (2 * w ** 3 - 5 * w) * Sc * Sc / 36
        lo, hi = -12.0, 12.0
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if q(mid) < x else (lo, mid)
        ref = (lo + hi) / 2
        a2 = Kc / 8 - Sc * Sc / 6          # q'(w) = a2 w^2 + a1 w + a0
        mono = a2 > 0 and (Sc / 3) ** 2 - 4 * a2 * (1 - Kc / 8 + 5 * Sc * Sc / 36) < 0
        nonmono += not mono
        d = abs(env['retZScore'] - ref) if math.isfinite(env['retZScore']) else math.inf
        if mono:
            worst = max(worst, d)
        else:
            # no inverse exists; the defined behaviour is to leave the observed z unchanged
            bad += abs(env['retZScore'] - x) > 1e-12 if math.isfinite(env['retZScore']) else True
    ok("inverse Cornish-Fisher by Newton (6 steps), where q is monotone", worst < 1e-3,  # 1e-3 sigma moves mrComposite by < 0.02 pt
       f"L{ln}: max |diff| to bisection {worst:.1e}")
    ok("inverse Cornish-Fisher outside the monotone (Maillard) domain", bad == 0,
       f"{nonmono} of 2000 random (S, K) draws in the gated range make q non-monotone "
       f"(needs K > 4S^2/3 and a negative discriminant); no inverse exists there, so the observed z must be "
       f"kept: violated in {bad} of them (Newton output instead, up to overflow)")


def test_race(path):
    blk, ln = P.extract(path, r'    float planExpectancy = na$', r'planExpectancy := _pW \* tpRR1')
    blk = [l for l in blk]
    grid_body = None
    L = open(path, encoding='utf-8').read().split('\n')
    for l in L:
        if l.startswith('f_gridInterp('):
            i = L.index(l)
            grid_body = L[i + 1].strip() if not l.split('=>', 1)[1].strip() else l.split('=>', 1)[1]
    gi = lambda *a: P.evaluate(grid_body, P.Env(_rr=a[0], _p0=a[1], _p1=a[2], _p2=a[3], _p3=a[4], _decay=a[5]))
    worst = 0.0
    for _ in range(1000):
        g = [rng.uniform(0, 100) for _ in range(12)] + [rng.uniform(-0.5, 0.5) for _ in range(6)]
        env = P.Env(funcs={'f_gridInterp': gi}, gRaceProb=g, tpDist=rng.uniform(1, 30), tpIsLong=rng.random() < .5,
                    tpRR1=rng.uniform(0.5, 3.5), _sessSpread=rng.uniform(0, 1), slippagePts=rng.uniform(0, .5),
                    commissionL=rng.uniform(0, 7), pointValue=rng.choice([1.0, 100.0]))
        P.run(blk, env)
        o = 0 if env['tpIsLong'] else 6
        to = 12 if env['tpIsLong'] else 15
        r = env['tpRR1']
        pw = gi(r, 100.0, g[o], g[o + 1], g[o + 2], True) / 100
        pl = gi(r, 0.0, g[o + 3], g[o + 4], g[o + 5], False) / 100
        pt = gi(r, 0.0, g[to], g[to + 1], g[to + 2], False)
        c = ((env['_sessSpread'] + 2 * env['slippagePts']) + env['commissionL'] / max(env['pointValue'], 1.0)) / env['tpDist']
        worst = max(worst, abs(env['planExpectancy'] - (pw * r - pl + pt - c)))
    ok("race expectancy E[R] = Pw*RR - Pl + E[timeout MTM] - cost", worst < 1e-9, f"L{ln}, max |diff| {worst:.1e}")


def test_mtf(path):
    blk, ln = P.extract(path, r'^int mtfAvail = ', r'^mtfConfluenceScore = ')
    worst = 0.0
    for tf in (60, 300, 900, 3600, 14400):
        av = {k: tf < v for k, v in (('htf5mAvailable', 300), ('htf15mAvailable', 900), ('htf1hAvailable', 3600), ('htf4hAvailable', 14400))}
        n_av = sum(av.values())
        for _ in range(300):
            mb = rng.randint(0, n_av) + rng.randint(0, 6)
            ms = rng.randint(0, n_av) + rng.randint(0, 6)
            env = P.Env(mtfConfluenceBull=mb, mtfConfluenceBear=ms, **av)
            P.run([l for l in blk if not l.startswith('//')], env)
            ref = P._round((mb - ms) / (n_av + 6.0) * 100.0)
            worst = max(worst, abs(env['mtfConfluenceScore'] - ref))
    ok("MTF confluence normalised by the votes available on the chart TF (F-A40)", worst == 0,
       f"L{ln}: 1M/5M/15M/1H/4H x 300 cases, max |diff| {worst}")


TESTS = [test_mtf, test_kelly, test_grid, test_ci, test_platt, test_brier, test_tanh, test_cf, test_race]

if __name__ == '__main__':
    files = sys.argv[1:] or ['artefacts/XAUUSD_Quantum_5_0_Master.pine']
    for f in files:
        print(os.path.basename(f))
        for t in TESTS:
            try:
                t(f)
            except StopIteration:
                print(f"  SKIP  {t.__name__}: block not present in this file")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"  FAIL  {t.__name__}: could not execute the block ({type(e).__name__}: {e})")
    for n in notes[:1]:
        print("NOTE:", n)
    print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails})",
          "-- the Pine text is executed in Python; the TradingView runtime is NOT exercised")
    sys.exit(1 if fails else 0)
