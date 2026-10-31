#!/usr/bin/env python3
"""Forward-ledger statistics, computed independently (institutional audit, 2026-10-31).

Reads the website's forward ledger (branch `forward-ledger`, holdout/<tf>_<arm>.json: the system of record's
out-of-sample trades, written by its pipeline after each freeze) and reports, per arm and timeframe:

  A performance   N, win rate (R > 0) with a Wilson 95% interval, average net win / loss, expectancy (mean R) with a
                  Student-t AND a bootstrap 95% interval, profit factor, maximum drawdown in R (closed trades in exit
                  order), expectancy BEFORE costs (R scaled by gross / net points), cost as a share of |gross move|
  B probability   the engine's calibrated probability `p` (cal_p_long / cal_p_short at entry) against the event the
                  website scores it on (`tp1_hit`): Brier score, the base-rate Brier (always predict the observed
                  rate), Brier skill score, log loss, reliability by quintile of p, calibration error (count-weighted
                  |mean p - observed|), ROC-AUC (Mann-Whitney) with a bootstrap interval. AUC measures ranking
                  (discrimination), Brier / reliability measure calibration: they answer different questions.
  C expectancy    `ev` (the plan's expected value at entry, in R) against the realised R: mean ev vs mean R, and their
    model         Spearman rank correlation
  D breakdowns    by session, regime and exit reason: DESCRIPTIVE ONLY. Choosing a filter from these splits would be
                  tuning on the holdout (AUDIT_PROMPT §9); they are printed to diagnose, never to select.

Nothing here is a decision: the website's pre-registered rules decide (A7). Every number is recomputed from the raw
records; no figure is copied from a report. Usage: python3 audit/tools/ledger_stats.py [--arms h4,h3] [--json out]"""
import json
import math
import random
import subprocess
import sys

BR = "origin/forward-ledger"
Z = 1.959964


def load(name):
    try:
        out = subprocess.run(["git", "show", f"{BR}:holdout/{name}.json"], capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    d = json.loads(out)
    return [t for t in d if isinstance(t, dict) and not t.get("open")] if isinstance(d, list) else []


def wilson(k, n):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z / d * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    return max(0.0, c - h), min(1.0, c + h)


def t975(df):
    """exact Student-t 97.5% quantile by bisection on the CDF (regularised incomplete beta, continued fraction)"""
    def betacf(a, b, x):
        c, d = 1.0, 1 - (a + b) * x / (a + 1)
        d = 1 / d
        h = d
        for m in range(1, 300):
            m2 = 2 * m
            aa = m * (b - m) * x / ((a - 1 + m2) * (a + m2))
            d, c = 1 / (1 + aa * d), 1 + aa / c
            h *= d * c
            aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + 1 + m2))
            d, c = 1 / (1 + aa * d), 1 + aa / c
            h *= d * c
        return h

    def cdf(t):
        x = df / (df + t * t)
        lb = math.lgamma(df / 2 + 0.5) - math.lgamma(df / 2) - math.lgamma(0.5)
        return 1 - 0.5 * math.exp(lb + df / 2 * math.log(x) + 0.5 * math.log(1 - x)) * betacf(df / 2, 0.5, x) / (df / 2)
    lo, hi = 1.9, 20.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < 0.975 else (lo, mid)
    return (lo + hi) / 2


def mean(x):
    return sum(x) / len(x)


def sd(x):
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def boot_ci(x, stat, rng, n=4000):
    vals = sorted(stat([x[rng.randrange(len(x))] for _ in x]) for _ in range(n))
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def auc(p, y):
    """Mann-Whitney: P(p of a positive > p of a negative), ties count 1/2"""
    pos = [a for a, b in zip(p, y) if b]
    neg = [a for a, b in zip(p, y) if not b]
    if not pos or not neg:
        return float("nan")
    s = sum((1.0 if a > b else 0.5 if a == b else 0.0) for a in pos for b in neg)
    return s / (len(pos) * len(neg))


def spearman(a, b):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else float("nan")


def maxdd(r):
    peak = cum = dd = 0.0
    for v in r:
        cum += v
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def analyse(name, T, rng):
    T = sorted(T, key=lambda t: (t["exit_time"], t["entry_time"]))
    r = [t["r"] for t in T]
    n = len(r)
    out = {"name": name, "n": n}
    if n < 2:
        return out
    w = [v for v in r if v > 0]
    l_ = [-v for v in r if v < 0]
    m, s = mean(r), sd(r)
    tq = t975(n - 1)
    gross = [t["r"] * t["gross_pts"] / t["pts"] if t["pts"] else 0.0 for t in T]
    out.update(wins=len(w), wr=len(w) / n, wr_ci=wilson(len(w), n), avg_win=mean(w) if w else float("nan"),
               avg_loss=mean(l_) if l_ else float("nan"), mean_r=m, t_ci=(m - tq * s / math.sqrt(n), m + tq * s / math.sqrt(n)),
               boot_ci=boot_ci(r, mean, rng), pf=sum(w) / sum(l_) if l_ else float("inf"), max_dd=maxdd(r), sum_r=sum(r),
               mean_gross_r=mean(gross), cost_share=sum(t["cost_pts"] for t in T) / max(1e-9, sum(abs(t["gross_pts"]) for t in T)),
               first=T[0]["entry_time"], last=T[-1]["exit_time"], keys=sorted({t.get("freeze_key", "") for t in T}))
    P = [(t["p"], 1 if t["tp1_hit"] else 0) for t in T if t.get("p") is not None]
    if len(P) >= 10:
        p = [a for a, _ in P]
        y = [b for _, b in P]
        base = mean(y)
        brier = mean([(a - b) ** 2 for a, b in P])
        bbase = mean([(base - b) ** 2 for b in y])
        eps = 1e-6
        ll = -mean([b * math.log(min(max(a, eps), 1 - eps)) + (1 - b) * math.log(1 - min(max(a, eps), 1 - eps)) for a, b in P])
        o = sorted(range(len(p)), key=lambda i: p[i])
        bins = [o[k * len(o) // 5:(k + 1) * len(o) // 5] for k in range(5)]
        rel = [(len(bk), mean([p[i] for i in bk]), mean([y[i] for i in bk])) for bk in bins if bk]
        ce = sum(c * abs(a - b) for c, a, b in rel) / len(p)
        a_ = auc(p, y)
        boots = []
        for _ in range(1000):
            idx = [rng.randrange(len(p)) for _ in p]
            boots.append(auc([p[i] for i in idx], [y[i] for i in idx]))
        boots = sorted(v for v in boots if not math.isnan(v))
        out.update(prob=dict(n=len(P), event="tp1_hit", base=base, mean_p=mean(p), brier=brier, brier_base=bbase,
                             bss=1 - brier / bbase if bbase else float("nan"), logloss=ll, rel=rel, ce=ce, auc=a_,
                             auc_ci=(boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]) if boots else (float("nan"),) * 2))
    E = [(t["ev"], t["r"]) for t in T if t.get("ev") is not None]
    if len(E) >= 10:
        out.update(ev=dict(n=len(E), mean_ev=mean([a for a, _ in E]), mean_r=mean([b for _, b in E]),
                           rho=spearman([a for a, _ in E], [b for _, b in E])))
    for key in ("session", "regime", "exit_reason"):
        g = {}
        for t in T:
            g.setdefault(str(t.get(key)), []).append(t["r"])
        out[key] = {k: (len(v), mean(v)) for k, v in sorted(g.items())}
    return out


def fmt(o):
    if o["n"] < 2:
        return f"{o['name']}: N {o['n']} (too few to analyse)"
    L = [f"{o['name']}: N {o['n']} ({o['first'][:10]} .. {o['last'][:10]}), freeze key(s) {', '.join(k[:22] for k in o['keys'])}",
         f"  A  win {o['wr']:.1%} (Wilson {o['wr_ci'][0]:.1%}-{o['wr_ci'][1]:.1%}); avg win {o['avg_win']:.3f}R, avg loss {o['avg_loss']:.3f}R; "
         f"expectancy {o['mean_r']:+.4f}R (t {o['t_ci'][0]:+.3f}..{o['t_ci'][1]:+.3f}; bootstrap {o['boot_ci'][0]:+.3f}..{o['boot_ci'][1]:+.3f}); "
         f"PF {o['pf']:.3f}; max drawdown {o['max_dd']:.2f}R; sum {o['sum_r']:+.2f}R",
         f"     before costs {o['mean_gross_r']:+.4f}R per trade; costs = {o['cost_share']:.0%} of |gross move|"]
    if "prob" in o:
        q = o["prob"]
        L.append(f"  B  p vs {q['event']} (n {q['n']}): base rate {q['base']:.3f}, mean p {q['mean_p']:.3f}; Brier {q['brier']:.4f} vs "
                 f"base-rate {q['brier_base']:.4f} -> skill {q['bss']:+.3f}; log loss {q['logloss']:.4f}; calibration error {q['ce']:.3f}; "
                 f"AUC {q['auc']:.3f} ({q['auc_ci'][0]:.3f}-{q['auc_ci'][1]:.3f})")
        L.append("     reliability (quintiles of p): " + " | ".join(f"n{c} p{a:.2f} obs{b:.2f}" for c, a, b in q["rel"]))
    if "ev" in o:
        e = o["ev"]
        L.append(f"  C  ev at entry: mean {e['mean_ev']:+.3f}R vs realised {e['mean_r']:+.3f}R; Spearman(ev, R) {e['rho']:+.3f} (n {e['n']})")
    for key in ("session", "regime", "exit_reason"):
        L.append(f"  D  {key} (descriptive only): " + ", ".join(f"{k} {n_}/{v:+.2f}" for k, (n_, v) in o[key].items()))
    return "\n".join(L)


if __name__ == "__main__":
    arms = ["h4", "h3", "h5", "h6", "h2", "treatment", "control", "challenger"]
    if "--arms" in sys.argv:
        arms = sys.argv[sys.argv.index("--arms") + 1].split(",")
    rng = random.Random(20261031)
    res = []
    for arm in arms:
        for tf in ("5m", "15m", "1h", "4h"):
            T = load(f"{tf}_{arm}")
            if T is None:
                print(f"{tf}_{arm}: NOT RUN (ledger file not reachable)")
                continue
            o = analyse(f"{arm.upper()} {tf}", T, rng)
            res.append(o)
            print(fmt(o))
    if "--json" in sys.argv:
        json.dump(res, open(sys.argv[sys.argv.index("--json") + 1], "w"), default=str, indent=1)
    ref = subprocess.run(["git", "log", "-1", "--format=%H %ci", BR], capture_output=True, text=True).stdout.strip()
    print(f"RESULT: computed from {BR} @ {ref}; descriptive statistics of out-of-sample records, not a decision (A7)")
