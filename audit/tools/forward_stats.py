"""Statistics of RECORDED forward trades for one engine key (read-only).

Usage: python audit/tools/forward_stats.py <forward-ledger checkout> <main freeze key> [--archive] [--seed 7]

Per ledger: n, win % with Wilson 95% interval, mean net R with a bootstrap 95% interval (10,000 resamples), t,
profit factor with a bootstrap interval, sum R, max drawdown in R. Also the trades split by regime and session, and
the calibration of the recorded P (cal_p at entry, against "TP1 reached"), where at least 10 trades carry one.
The bootstrap treats trades as independent; serial dependence makes the true intervals wider.
"""
import argparse
import glob
import json
import math
import os
from collections import defaultdict

import numpy as np


def wilson(k, n, z=1.96):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def pf(pts):
    gl = -pts[pts < 0].sum()
    return pts[pts > 0].sum() / gl if gl > 0 else math.inf


def summary(T, rng, B=10000):
    r = np.array([t["r"] for t in T], float)
    pts = np.array([t["pts"] for t in T], float)
    n = len(r)
    k = int((r > 0).sum())
    out = {"n": n, "win": k / n * 100 if n else math.nan, "wilson": wilson(k, n)}
    if n == 0:
        return out
    sd = r.std(ddof=1) if n > 1 else math.nan
    cum = np.cumsum(r)
    out.update(mean=r.mean(), t=r.mean() / (sd / math.sqrt(n)) if n > 1 and sd > 0 else math.nan, pf=pf(pts), sum=r.sum(),
               dd=float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max()), sd=sd)
    if n >= 5:
        idx = rng.integers(0, n, size=(B, n))
        means = r[idx].mean(axis=1)
        out["mean_ci"] = (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
        g = np.where(pts[idx] > 0, pts[idx], 0).sum(axis=1)
        lo = -np.where(pts[idx] < 0, pts[idx], 0).sum(axis=1)
        pfs = np.where(lo > 0, g / np.where(lo > 0, lo, 1), np.inf)
        out["pf_ci"] = (float(np.percentile(pfs, 2.5)), float(np.percentile(pfs, 97.5)))
    return out


def f(x, d=3):
    return "—" if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else f"{x:+.{d}f}" if d else f"{x:.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("key")
    ap.add_argument("--archive", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    pat = os.path.join(a.base, "holdout", "archive" if a.archive else "", "*.json")
    led = {}
    for p in sorted(glob.glob(pat)):
        name = os.path.basename(p)[:-5]
        if name.startswith("manifest"):
            continue
        T = [t for t in json.load(open(p)) if isinstance(t, dict) and not t.get("open") and str(t.get("freeze_key", "")).startswith(a.key)]
        if T:
            led[name] = T
    print("| Ledger | n | Win % [Wilson 95%] | Mean R [bootstrap 95%] | t | PF [bootstrap 95%] | Sum R | Max DD (R) |")
    print("|---|---|---|---|---|---|---|---|")
    for name, T in led.items():
        s = summary(T, rng)
        mci = s.get("mean_ci")
        pci = s.get("pf_ci")
        print(f"| {name} | {s['n']} | {s['win']:.1f} [{s['wilson'][0] * 100:.1f}, {s['wilson'][1] * 100:.1f}] | {f(s['mean'])}"
              f"{f' [{mci[0]:+.3f}, {mci[1]:+.3f}]' if mci else ''} | {f(s['t'], 2)} | {f(s['pf'], 2).lstrip('+')}"
              f"{f' [{pci[0]:.2f}, {pci[1]:.2f}]' if pci and math.isfinite(pci[1]) else (' [—]' if pci else '')} | {f(s['sum'], 2)} | {s['dd']:.2f} |")
    big = {n: T for n, T in led.items() if len(T) >= 30}
    for field in ("regime", "session"):
        print(f"\n**By {field}** (ledgers with n ≥ 30; groups with n < 10 shown for completeness only)\n")
        print(f"| Ledger | {field} | n | Win % | Mean R [bootstrap 95%] | Sum R |")
        print("|---|---|---|---|---|---|")
        for name, T in big.items():
            g = defaultdict(list)
            for t in T:
                g[t.get(field) or "—"].append(t)
            for kk, TT in sorted(g.items(), key=lambda x: -len(x[1])):
                s = summary(TT, rng)
                mci = s.get("mean_ci")
                print(f"| {name} | {kk} | {s['n']} | {s['win']:.0f} | {f(s['mean'])}{f' [{mci[0]:+.2f}, {mci[1]:+.2f}]' if mci and s['n'] >= 10 else ''} | {f(s['sum'], 2)} |")
    print("\n**Calibration of the recorded P (TP1 reached), ledgers with ≥ 10 trades carrying P**\n")
    rows = 0
    for name, T in led.items():
        P = [(t["p"], 1.0 if t["tp1_hit"] else 0.0) for t in T if t.get("p") is not None]
        if len(P) < 10:
            continue
        p = np.array([x for x, _ in P])
        y = np.array([x for _, x in P])
        base = y.mean()
        br = float(np.mean((p - y) ** 2))
        print(f"- {name}: n {len(P)}, mean P {p.mean():.2f}, observed {base:.2f}, Brier {br:.3f}, "
              f"skill {1 - br / (base * (1 - base)):+.2f}" if 0 < base < 1 else f"- {name}: n {len(P)} (one outcome only)")
        rows += 1
    if not rows:
        print("- No ledger has 10 or more trades with a recorded P: **calibration NOT ASSESSABLE** on this record.")


if __name__ == "__main__":
    main()
