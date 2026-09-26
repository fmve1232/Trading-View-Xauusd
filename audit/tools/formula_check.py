#!/usr/bin/env python3
"""Numerical checks of the v16 formula corrections, against their definitions.

Each check compares the formula AS IMPLEMENTED IN THE PINE (re-typed here) with a direct
computation from first principles. Like race_model_check.py, this tests the MATHEMATICS,
not the .pine file: a transcription error in the script would not show up here.

  1. Cornish-Fisher direction: an observed standardised return must be mapped to its
     normal-equivalent by INVERTING q(w); the forward map double-counts the tails.
  2. Murphy decomposition: UNC + REL - RES equals the Brier score of bin-mean forecasts
     exactly, with raw frequencies over the same bins; smoothed/filtered variants do not.
  3. Kelly with timeouts: f* = (p b - q) / (b (p + q)) is the argmax of expected log growth.
  4. t-quantile Fisher expansion: both correction terms at the ORIGINAL z (textbook form;
     numerically a ~1e-5 change, stated as such).

Usage: python3 audit/tools/formula_check.py
"""
import math
import random
import statistics as st
from statistics import NormalDist

N = NormalDist()
fails = 0


def check(name, ok, detail):
    global fails
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


# 1. Cornish-Fisher -----------------------------------------------------------------
rng = random.Random(3)
xs = [rng.gauss(0, 1) if rng.random() < 0.85 else rng.gauss(0.8, 2.5) for _ in range(200000)]
mu, sd = st.fmean(xs), st.pstdev(xs)
z = sorted((x - mu) / sd for x in xs)
S = max(-1, min(1, st.fmean([v ** 3 for v in z])))
K = max(-1, min(3, st.fmean([v ** 4 for v in z]) - 3))
q = lambda w: w + (w * w - 1) * S / 6 + (w ** 3 - 3 * w) * K / 24 - (2 * w ** 3 - 5 * w) * S * S / 36
dq = lambda w: 1 + w * S / 3 + (3 * w * w - 3) * K / 24 - (6 * w * w - 5) * S * S / 36


def inv(x):
    w = x
    for _ in range(6):
        w -= (q(w) - x) / max(dq(w), 0.1)
    return w


err_inv = err_fwd = 0.0
for pct in (0.01, 0.05, 0.25, 0.75, 0.95, 0.99):
    x = z[int(pct * len(z))]
    t = N.inv_cdf(pct)
    err_inv = max(err_inv, abs(inv(x) - t))
    err_fwd = max(err_fwd, abs(q(x) - t))
check("Cornish-Fisher inverted (Newton)", err_inv < 0.15 and err_fwd > 1.0,
      f"max |error| vs true normal quantile: inverse {err_inv:.2f}, old forward {err_fwd:.2f}")

# 2. Murphy decomposition -----------------------------------------------------------
rng = random.Random(5)
bins = []
for _ in range(5):
    n = rng.randint(1, 200)
    pm = rng.random()
    b = sum(rng.random() < min(1, max(0, pm + rng.uniform(-.2, .2))) for _ in range(n))
    bins.append((n, pm, b))
Nt = sum(n for n, _, _ in bins)
base = sum(b for _, _, b in bins) / Nt
direct = sum(b * (pm - 1) ** 2 + (n - b) * pm ** 2 for n, pm, b in bins) / Nt
rel = sum(n * (pm - b / n) ** 2 for n, pm, b in bins) / Nt
res = sum(n * (b / n - base) ** 2 for n, pm, b in bins) / Nt
check("Murphy decomposition exact", abs(direct - (base * (1 - base) + rel - res)) < 1e-12,
      f"direct {direct:.10f} vs UNC+REL-RES {base * (1 - base) + rel - res:.10f}")

# 3. Kelly with timeouts ------------------------------------------------------------
worst = 0.0
for p, qq, b in ((0.35, 0.30, 1.0), (0.5, 0.2, 1.5), (0.2, 0.1, 2.0), (0.45, 0.45, 0.9)):
    f = (p * b - qq) / (b * (p + qq))
    grid = max((p * math.log(1 + g * b) + qq * math.log(1 - g), g) for g in [i / 20000 for i in range(0, 19999)])[1]
    worst = max(worst, abs(max(f, 0.0) - grid))
check("Kelly f* = (pb - q)/(b(p+q))", worst < 1e-3, f"max |formula - numeric argmax| = {worst:.5f}")

# 4. Fisher t-quantile expansion ----------------------------------------------------
# Reference: t quantile by bisection on the t CDF (Simpson integration of the density).
def t_cdf(x, df):
    c = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) / math.sqrt(df * math.pi)
    f = lambda u: c * (1 + u * u / df) ** (-(df + 1) / 2)
    n = 4000
    h = x / n
    s = f(0) + f(x) + sum((4 if i % 2 else 2) * f(i * h) for i in range(1, n))
    return 0.5 + s * h / 3


def t_inv(p, df):
    lo, hi = 0.0, 50.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if t_cdf(mid, df) < p else (lo, mid)
    return (lo + hi) / 2


p = 1 - (0.05 / 18) / 2
for df in (28, 58, 118):
    z0 = N.inv_cdf(p)
    new = z0 + (z0 ** 3 + z0) / (4 * df) + (5 * z0 ** 5 + 16 * z0 ** 3 + 3 * z0) / (96 * df * df)
    z1 = z0 + (z0 ** 3 + z0) / (4 * df)
    old = z1 + (5 * z0 ** 5 + 16 * z0 ** 3 + 3 * z1) / (96 * df * df)
    ref = t_inv(p, df)
    # The v16 change makes the code match the textbook expansion; numerically it moves
    # the result by ~1e-5, far below the expansion's own ~1e-3 truncation error. So the
    # test is accuracy against the reference, and the old-vs-new gap is reported, not judged.
    check(f"Fisher t-quantile df={df}", abs(new - ref) < 0.01,
          f"reference {ref:.4f}  expansion {new:.4f}  (old ordering differed by {abs(new - old):.1e})")

print("RESULT:", "PASS" if fails == 0 else f"FAIL ({fails})",
      "-- checks the mathematics only; the Pine is NOT exercised")
raise SystemExit(fails)
