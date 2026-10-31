#!/usr/bin/env python3
"""Is the engine's probability a probability? (Amendment 12 evidence, 2026-10-31)

Scores the website engine's calibrated probability `cal_p_long` (quantum/engine.py: P(the long race wins | it resolves),
computed causally at each bar from past analog outcomes) against the event it is defined on, labelled HERE,
independently of the engine's own labels:

  race at bar r: entry close[r], unit R = aatr[r] x reg_sl_mult[r] (nz 1.5); over the next N bars (N = outcome_n =
  max(3, 3600 / tf seconds)) the first bar with low <= entry - R is a LOSS (checked first: a bar touching both is a loss,
  as the engine's label_outcome), else the first with high >= entry + R is a WIN; neither within N bars = timeout.

The input is a pickle written by running the engine READ-ONLY on a copy of the market-data store (audit/tools/engine_dump.py),
so no number here depends on the engine's own outcome bookkeeping. Reported, per period (before / from the forward-test
start 2026-09-28) and in total: n resolved, base rate, mean p, Brier, Brier of two baselines (the period's own base rate:
an oracle, and the causal running base rate up to each bar: a fair one), skill vs each, log loss, reliability by
quintile of p, calibration error, ROC-AUC with a bootstrap interval. AUC measures ranking, Brier / reliability measure
calibration. Overlapping races (consecutive bars share future bars) are autocorrelated: intervals here are optimistic,
so a block bootstrap (blocks of N bars) is used for AUC.

Diagnosis only: nothing is tuned (AUDIT_PROMPT §9); Amendment 12 records the result and registers arm H6.
Usage: python3 audit/tools/engine_calibration.py <dump.pkl> [<dump.pkl> ...]"""
import math
import pickle
import random
import sys

FWD = "2026-09-28"


def label(o, h, l, c, aatr, regsl, N):
    n = len(c)
    out = [None] * n
    for r in range(n):
        if r + N >= n:
            break
        a = aatr[r]
        m = regsl[r] if regsl[r] == regsl[r] else 1.5
        if a != a or a <= 0:
            continue
        R = a * m
        ent = c[r]
        res = 0
        for k in range(r + 1, r + N + 1):
            if l[k] <= ent - R:
                res = -1
                break
            if h[k] >= ent + R:
                res = 1
                break
        out[r] = res
    return out


def auc(p, y):
    pairs = sorted(zip(p, y))
    # rank-sum with average ranks for ties
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    npos = sum(1 for _, b in pairs if b)
    nneg = len(pairs) - npos
    if not npos or not nneg:
        return float("nan")
    rs = sum(r for r, (_, b) in zip(ranks, pairs) if b)
    return (rs - npos * (npos + 1) / 2) / (npos * nneg)


def score(rows, N, rng):
    p = [a for a, _, _ in rows]
    y = [b for _, b, _ in rows]
    run = [z for _, _, z in rows]
    n = len(p)
    if n < 30:
        return None
    base = sum(y) / n
    brier = sum((a - b) ** 2 for a, b in zip(p, y)) / n
    b_or = sum((base - b) ** 2 for b in y) / n
    b_run = sum((z - b) ** 2 for z, b in zip(run, y)) / n
    eps = 1e-6
    ll = -sum(b * math.log(min(max(a, eps), 1 - eps)) + (1 - b) * math.log(1 - min(max(a, eps), 1 - eps)) for a, b in zip(p, y)) / n
    o = sorted(range(n), key=lambda i: p[i])
    rel = []
    for k in range(5):
        bk = o[k * n // 5:(k + 1) * n // 5]
        rel.append((len(bk), sum(p[i] for i in bk) / len(bk), sum(y[i] for i in bk) / len(bk)))
    ce = sum(cnt * abs(a - b) for cnt, a, b in rel) / n
    a_ = auc(p, y)
    blocks = [list(range(s, min(s + N, n))) for s in range(0, n, N)]
    bs = []
    for _ in range(400):
        idx = [i for _ in blocks for i in blocks[rng.randrange(len(blocks))]]
        bs.append(auc([p[i] for i in idx], [y[i] for i in idx]))
    bs = sorted(v for v in bs if v == v)
    return dict(n=n, base=base, mean_p=sum(p) / n, brier=brier, b_oracle=b_or, b_running=b_run, skill_oracle=1 - brier / b_or,
                skill_running=1 - brier / b_run, logloss=ll, rel=rel, ce=ce, auc=a_, auc_ci=(bs[int(.025 * len(bs))], bs[int(.975 * len(bs)) - 1]))


def main(path):
    d = pickle.load(open(path, "rb"))
    N = d["N"]
    lab = label(d["o"], d["h"], d["l"], d["c"], list(d["aatr"]), list(d["regsl"]), N)
    pl = list(d["rows"]["cal_p_long"])
    idx = d["index"]
    rows_all, rows_pre, rows_fwd = [], [], []
    wins = tot = 0
    n_bars = len(lab)
    n_p = sum(1 for v in pl if v == v)
    n_to = sum(1 for v in lab if v == 0)
    for r, res in enumerate(lab):
        # the running base rate at bar r uses only races already decided: race q is known at bar q + N
        q = r - N
        if q >= 0 and lab[q] in (1, -1):
            tot += 1
            wins += lab[q] == 1
        if res is None or res == 0:
            continue
        run = wins / tot if tot >= 30 else 0.5
        a = pl[r]
        if a == a:
            row = (a, 1 if res == 1 else 0, run)
            rows_all.append(row)
            (rows_fwd if str(idx[r])[:10] >= FWD else rows_pre).append(row)
    rng = random.Random(7)
    print(f"{path}: {n_bars} bars {str(idx[0])[:16]} .. {str(idx[-1])[:16]} UTC, N = {N} bars; p defined on {n_p} bars; "
          f"races resolved {sum(1 for v in lab if v)} / timeouts {n_to}")
    for nm, rows in (("before the forward start", rows_pre), ("from 2026-09-28 (forward period)", rows_fwd), ("all", rows_all)):
        s = score(rows, N, rng)
        if s is None:
            print(f"  {nm}: n {len(rows)} (too few)")
            continue
        print(f"  {nm}: n {s['n']}, base rate {s['base']:.3f}, mean p {s['mean_p']:.3f}; Brier {s['brier']:.4f} vs oracle base {s['b_oracle']:.4f} "
              f"(skill {s['skill_oracle']:+.3f}) / running base {s['b_running']:.4f} (skill {s['skill_running']:+.3f}); log loss {s['logloss']:.4f}; "
              f"calibration error {s['ce']:.3f}; AUC {s['auc']:.3f} (block bootstrap {s['auc_ci'][0]:.3f}-{s['auc_ci'][1]:.3f})")
        print("     reliability (quintiles of p): " + " | ".join(f"n{c} p{a:.2f} obs{b:.2f}" for c, a, b in s["rel"]))


if __name__ == "__main__":
    for pth in sys.argv[1:]:
        main(pth)
    print("RESULT: website engine run read-only on the market-data store; events labelled independently; diagnosis only (A7)")
