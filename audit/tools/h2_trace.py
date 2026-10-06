#!/usr/bin/env python3
"""Execute the H2 block AS WRITTEN in Strategy_H2.pine (pine_exec.py) against its specification.

  1. volume profile vs an independent implementation of the spec (100 bars, 40 bins, typical
     price, first-maximum POC, 70% value area grown toward the larger neighbour)
  2. volume profile vs the ENGINE's own VP block (Treatment), on the same bars -- H2 claims to use
     the engine's definition, this proves it
  3. signal + plan (sweep, trend, discount/premium vs POC, 0.5-5 ATR risk, SL/TP1/TP2) vs the spec
  4. swing/sweep state machine run bar by bar (a swing is consumed once traded through)
Not covered: ta.pivothigh/pivotlow and request.security themselves (TradingView built-ins), and
the TradingView runtime. Usage: python3 audit/tools/h2_trace.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

H2 = 'artefacts/XAUUSD_Quantum_5_0_Strategy_H2.pine'
T = 'artefacts/XAUUSD_Quantum_5_0_Strategy.pine'
rng = random.Random(9)
fails = 0


def report(name, bad, detail):
    global fails
    fails += bad > 0
    print(f"  {'PASS' if bad == 0 else 'FAIL'}  {name}: {detail}, mismatches {bad}")


def ref_vp(h, l, c, v):
    hi, lo = max(h[-100:]), min(l[-100:])
    bs = (hi - lo) / 40
    vv = [0.0] * 40
    for i in range(100):
        k = max(0, min(int(((h[-1 - i] + l[-1 - i] + c[-1 - i]) / 3 - lo) / bs), 39))
        vv[k] += v[-1 - i]
    pk = max(range(40), key=lambda j: (vv[j], -j))
    cum, tgt, a, b = vv[pk], sum(vv) * 0.7, pk, pk
    while cum < tgt and (a > 0 or b < 39):
        vb = vv[a - 1] if a > 0 else -1
        va = vv[b + 1] if b < 39 else -1
        if va >= vb and b < 39:
            b += 1
            cum += va
        elif a > 0:
            a -= 1
            cum += vb
        else:
            break
    return lo + bs * (pk + .5), lo + bs * (b + .5), lo + bs * (a + .5)


def test_vp():
    vp, ln = P.extract(H2, r'^if barstate.isconfirmed and bar_index >= 100 and h2VHi > h2VLo', r'^    h2Val := ')
    eng, ln2 = P.extract(T, r'^if barstate.isconfirmed and not perfMode$', r'^    vpRefresh \+= 1')
    bad_ref = bad_eng = 0
    for _ in range(300):
        px = 4000.0
        h, l, c, v = [], [], [], []
        for _ in range(150):
            o = px
            px += rng.gauss(0, 3)
            h.append(max(o, px) + abs(rng.gauss(0, 1.5)))
            l.append(min(o, px) - abs(rng.gauss(0, 1.5)))
            c.append(px)
            v.append(float(rng.randint(50, 5000)))
        hi, lo = max(h[-100:]), min(l[-100:])
        S = P.Series
        env = P.Env(**{'barstate.isconfirmed': True, 'bar_index': 150, 'h2VHi': hi, 'h2VLo': lo, 'high': S(h), 'low': S(l),
                       'close': S(c), 'volume': S(v), 'h2Poc': P.NA, 'h2Vah': P.NA, 'h2Val': P.NA})
        P.run(vp, env)
        got = (env['h2Poc'], env['h2Vah'], env['h2Val'])
        bad_ref += max(abs(a - b) for a, b in zip(got, ref_vp(h, l, c, v))) > 1e-9
        ee = P.Env(**{'barstate.islast': True, 'barstate.isconfirmed': True, 'perfMode': False, 'vpRefresh': 0, 'vpHigh': hi,
                      'vpLow': lo, 'vpBuckets': 40, 'vpLookback': 100, 'vpVolumes': [0.0] * 40, 'vpPrices': [0.0] * 40,
                      'high': S(h), 'low': S(l), 'close': S(c), 'volume': S(v), 'vpocPrice': P.NA, 'vahPrice': P.NA,
                      'valPrice': P.NA, 'vaRatio': 0.0, 'vaPos': ''})
        P.run(eng, ee)
        bad_eng += max(abs(a - b) for a, b in zip(got, (ee['vpocPrice'], ee['vahPrice'], ee['valPrice']))) > 1e-9
    report("volume profile vs independent spec", bad_ref, f"L{ln}, 300 random 150-bar series")
    report("volume profile vs the engine's own VP code", bad_eng, f"Treatment L{ln2}, same bars")


def test_plan():
    pl, ln = P.extract(H2, r'^float h2RL = ', r'^float h2Tp2 = ')
    bad = 0
    for _ in range(3000):
        sl, sh, up, dn = (rng.random() < .5 for _ in range(4))
        atr = rng.uniform(2, 20)
        cl = 4000 + rng.uniform(-30, 30)
        hi_, lo_ = cl + rng.uniform(0, 25), cl - rng.uniform(0, 25)
        poc = cl + rng.uniform(-30, 30)
        vah, val = poc + rng.uniform(0, 20), poc - rng.uniform(0, 20)
        env = P.Env(h2SweepL=sl, h2SweepH=sh, close=cl, low=lo_, high=hi_, h2Atr=atr, h2TrendUp=up, h2TrendDn=dn,
                    h2Poc=poc, h2Vah=vah, h2Val=val)
        P.run(pl, env)
        rL = cl - (lo_ - .15 * atr) if sl else None
        rS = (hi_ + .15 * atr) - cl if sh else None
        L_ = bool(sl and up and cl <= poc and .5 * atr <= rL <= 5 * atr)
        S_ = bool(sh and dn and cl >= poc and .5 * atr <= rS <= 5 * atr)
        ok = env['h2Long'] == L_ and env['h2Short'] == S_
        if L_:
            ok &= abs(env['h2Sl'] - (cl - rL)) < 1e-9 and abs(env['h2Tp1'] - max(poc, cl + rL)) < 1e-9 and abs(env['h2Tp2'] - max(vah, cl + 2 * rL)) < 1e-9
        elif S_:
            ok &= abs(env['h2Sl'] - (cl + rS)) < 1e-9 and abs(env['h2Tp1'] - min(poc, cl - rS)) < 1e-9 and abs(env['h2Tp2'] - min(val, cl - 2 * rS)) < 1e-9
        else:
            ok &= P.isna(env['h2Sl']) and P.isna(env['h2Tp1'])
        bad += not ok
    report("signal + plan vs the spec", bad, f"L{ln}, 3000 random cases")


def test_state():
    blk, ln = P.extract(H2, r'^bool h2SweepL = ', r'^    h2SwH := h2PH')
    bad = sweeps = 0
    for _ in range(200):
        px = 4000.0
        env = P.Env(h2SwH=P.NA, h2SwL=P.NA)
        swH = swL = None
        for _ in range(300):
            o = px
            px += rng.gauss(0, 3)
            hi, lo = max(o, px) + abs(rng.gauss(0, 1.5)), min(o, px) - abs(rng.gauss(0, 1.5))
            ph = hi + rng.uniform(1, 6) if rng.random() < .06 else P.NA
            pv = lo - rng.uniform(1, 6) if rng.random() < .06 else P.NA
            env.update({'barstate.isconfirmed': True, 'low': lo, 'high': hi, 'close': px, 'h2PH': ph, 'h2PL': pv})
            P.run(blk, env)
            sL = swL is not None and lo < swL and px > swL
            sH = swH is not None and hi > swH and px < swH
            if swL is not None and lo < swL:
                swL = None
            if swH is not None and hi > swH:
                swH = None
            if not P.isna(pv):
                swL = pv
            if not P.isna(ph):
                swH = ph
            sweeps += sL + sH
            bad += not (env['h2SweepL'] == sL and env['h2SweepH'] == sH
                        and (P.isna(env['h2SwL']) if swL is None else env['h2SwL'] == swL)
                        and (P.isna(env['h2SwH']) if swH is None else env['h2SwH'] == swH))
    report("swing / sweep state machine, bar by bar", bad, f"L{ln}, 200 paths x 300 bars, {sweeps} sweeps")


if __name__ == '__main__':
    print(os.path.basename(H2))
    test_vp()
    test_plan()
    test_state()
    print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails})", "-- Pine text executed in Python; TradingView runtime NOT exercised")
    sys.exit(1 if fails else 0)
