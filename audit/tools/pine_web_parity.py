#!/usr/bin/env python3
"""Pine engine vs website engine, block by block, EXECUTED (2026-10-31, after PR #49).

The website (system of record) runs a Python port of the Treatment engine; the Pine Master runs the original. F-A78
(the engine's score has no skill) was measured on the PORT. This tool executes the Pine blocks as written (pine_exec) and
the website's own Python functions (imported from the default branch, read-only) on the same random inputs:

  1 L / S / R score normalisation: Pine normalizeScores  vs  engine.normalize_scores (Pine math.round = half away
    from zero; the port's pround)
  2 race-probability grid interpolation: Pine f_gridInterp  vs  engine.f_grid_interp
  3 the outcome EVENT the score is fitted to: the Pine race loop (entry OUTCOME_N bars back, unit R = aatr x
    regSLMult (nz 1.5) at the entry bar, scan forward up to 60 bars, stop first)  vs  engine.label_outcome's race,
    bar by bar on random paths, so the event F-A78 scored is the event the Pine engine fits

Known, documented differences between the two engines (docs/PLATFORM.md D-01 ... D-12, e.g. the analog scan cadence)
are NOT covered: they make the Pine score's VALUES differ from the port's, which is why F-A78 holds for the Pine engine
only by inference (same event, same fit family) and by Diagnostics' on-chart reliability table, not by measurement.
Usage: python3 audit/tools/pine_web_parity.py"""
import importlib
import math
import os
import random
import subprocess
import sys
import tarfile
import io
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

REF = "origin/claude/audit-prompt-real-artefacts-nekqv6"
M = open("artefacts/XAUUSD_Quantum_5_0_Master.pine", encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    fails += not ok


# the website's engine module, from the default branch, without its package side effects
tmp = tempfile.mkdtemp()
tar = subprocess.run(["git", "archive", REF, "quantum"], capture_output=True, check=True).stdout
tarfile.open(fileobj=io.BytesIO(tar)).extractall(tmp)
sys.path.insert(0, tmp)
try:
    W = importlib.import_module("quantum.engine")
except ModuleNotFoundError as e:
    print(f"NOT RUN  website engine not importable here ({e}); install numpy / pandas")
    sys.exit(2)
rev = subprocess.run(["git", "log", "-1", "--format=%h", REF], capture_output=True, text=True).stdout.strip()


def fn(head):
    a = next(i for i, l in enumerate(M) if l.startswith(head))
    out = [M[a]]
    for l in M[a + 1:]:
        if l.startswith("    ") or not l.strip():
            out.append(l)
        else:
            break
    return [l for l in out if l.strip()]


env = P.Env()
P.define(fn("normalizeScores(float b, float be, float r, float minFloor) =>"), env)
P.define(fn("f_gridInterp(_rr, _p0, _p1, _p2, _p3, _decay) =>"), env)
rng = random.Random(49)

# ---- 1
bad = n = 0
vals = [0.0, 5.0, 10.0, 33.3, 47.5, 50.0, 62.5, 80.0, 95.0, 99.0, 120.0]
for _ in range(20000):
    b, be, r = (rng.choice(vals + [rng.uniform(-10, 130)]) for _ in range(3))
    fl = rng.choice([0.0, 5.0, 10.0, 15.0])
    got = P.evaluate(f"normalizeScores({b!r}, {be!r}, {r!r}, {fl!r})", P.Env(funcs=env.funcs))
    want = W.normalize_scores(b, be, r, fl)
    n += 1
    if any(abs(x - y) > 1e-9 for x, y in zip(got, want)):
        bad += 1
        if bad <= 3:
            print("   mismatch", (b, be, r, fl), got, want)
ctl1 = sum(1 for x in (0.5, 1.5, 2.5, 47.5, 62.5) if round(x) != P._round(x))
report(ctl1 > 0, f"1c control: Python's half-to-even round differs from Pine math.round on {ctl1} / 5 halves (the case the port's pround exists for)")
report(bad == 0, f"1 L / S / R normalisation: Pine normalizeScores == website normalize_scores, {n} cases incl. boundaries, "
       f"mismatches {bad}")

# ---- 2
bad = n = 0
for _ in range(20000):
    rr = rng.choice([-1.0, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 6.0, rng.uniform(-1, 8)])
    ps = [rng.uniform(0, 100) for _ in range(4)]
    dec = rng.random() < 0.5
    got = P.evaluate(f"f_gridInterp({rr!r}, {ps[0]!r}, {ps[1]!r}, {ps[2]!r}, {ps[3]!r}, {str(dec).lower()})", P.Env(funcs=env.funcs))
    want = W.f_grid_interp(rr, *ps, dec)
    n += 1
    bad += abs(got - want) > 1e-9
report(bad == 0, f"2 race grid interpolation: Pine f_gridInterp == website f_grid_interp, {n} cases, mismatches {bad}")

# ---- 3 the outcome race, executed from the Pine loop as written, vs the website's label_outcome
i0 = next(i for i, l in enumerate(M) if l.strip().startswith("float _oR = nz(adaptiveATR[OUTCOME_N]) * nz(regSLMult[OUTCOME_N], 1.5)"))
i1 = next(i for i in range(i0, len(M)) if M[i].strip().startswith("array.set(hOut, oP, _oRes)"))
ind = len(M[i0]) - len(M[i0].lstrip())
LOOP = [l[ind:] for l in M[i0:i1] if l.strip() and not l.strip().startswith("//")]
MUT = [x.replace("low[_k] <= _oEnt - _oR ? -1 : high[_k] >= _oEnt + _oR ? 1 : 0",
                  "high[_k] >= _oEnt + _oR ? 1 : low[_k] <= _oEnt - _oR ? -1 : 0") for x in LOOP]
assert MUT != LOOP, "race line not found for the control"
bad = n = ctl = 0
for _ in range(400):
    N = rng.choice([3, 4, 12, 70])
    bars = 200
    c, h, l, a, m = [], [], [], [], []
    px = 2000.0
    for k in range(bars):
        o = px
        px = o + rng.gauss(0, 2)
        c.append(px)
        h.append(max(o, px) + abs(rng.gauss(0, 1.2)))
        l.append(min(o, px) - abs(rng.gauss(0, 1.2)))
        a.append(math.nan if rng.random() < 0.02 else abs(rng.gauss(2.5, 0.7)))
        m.append(math.nan if rng.random() < 0.05 else rng.choice([1.0, 1.2, 1.5, 2.0]))
    for i in range(N, bars):
        r = i - N
        e = P.Env(OUTCOME_N=float(N), _oEnt=c[r], adaptiveATR=P.Series(a[:i + 1]), regSLMult=P.Series(m[:i + 1]),
                  low=P.Series(l[:i + 1]), high=P.Series(h[:i + 1]))
        P.run(LOOP, e)
        H = {"out": [0] * bars, "race": [0] * bars, "term": [0.0] * bars, "ret": [0.0] * bars, "runit": [0.0] * bars,
             "bev": [0] * bars, "bcont": [0.0] * bars, "first": [0] * bars}
        W.label_outcome(r, i, N, H, c, h, l, a, m, h, l, [math.nan] * bars, [math.nan] * bars)
        n += 1
        bad += int(e["_oRes"]) != int(H["out"][r])
        if n % 7 == 0:                         # positive control: target checked first on a tie must be detected
            e2 = P.Env(OUTCOME_N=float(N), _oEnt=c[r], adaptiveATR=P.Series(a[:i + 1]), regSLMult=P.Series(m[:i + 1]),
                       low=P.Series(l[:i + 1]), high=P.Series(h[:i + 1]))
            P.run(MUT, e2)
            ctl += int(e2["_oRes"]) != int(H["out"][r])
report(bad == 0 and n > 10000, f"3 outcome event: the Pine race loop (as written) == website label_outcome, {n} races on random paths "
       f"(N 3 / 4 / 12 / 70, na ATR and multipliers included), mismatches {bad}")
report(ctl > 0, f"3c positive control: a target-first (tie order flipped) copy of the loop IS detected ({ctl} mismatches)")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine blocks executed in Python vs the website's engine @ {rev}; "
      "TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
