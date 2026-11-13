"""Forward calibration of the engine's displayed probability `p` (P(TP1 before SL)) on the frozen forward ledgers.

  python3 -I audit/tools/calib_audit.py <forward-ledger dir> <out.json>

Read-only. Every closed trade with a recorded `p` is scored against `tp1_hit` (what backtest.py scores it against).
The ledgers record `p` at entry, before the outcome, under the freeze key in force, so this is an out-of-sample test of
the probability as shown. Arms share entries (treatment, challenger and the research arms often take the same bar), so
pooled rows are NOT independent: the UNIQUE group keeps one row per (timeframe, entry time, side) and is the one to read. Archived ledgers (earlier freeze keys) are reported separately and never pooled with the
current one. Metrics: Brier score and its skill against the base rate, log loss, reliability by p-bin with Wilson
intervals, calibration intercept and slope (logistic regression of the outcome on logit(p)), and AUC.
Verdict per group: NOT CALIBRATED when (n >= 10) the observed wins differ from the sum of the shown probabilities at the 5%
level (calibration-in-the-large); otherwise INSUFFICIENT DATA below 100 trades; at 100 or more, CALIBRATED only if the
calibration slope's 95% interval contains 1, the intercept's contains 0 and the Brier skill score is > 0."""
from __future__ import annotations

import glob
import json
import math
import os
import sys

import numpy as np
from scipy import optimize, stats

LED, OUT = sys.argv[1], sys.argv[2]


def wilson(k, n, z=1.96):
    if n == 0:
        return [math.nan, math.nan]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def logit_fit(x, y):
    """Outcome ~ a + b * logit(p): maximum likelihood with a Hessian-based standard error."""
    X = np.column_stack([np.ones_like(x), x])

    def nll(w):
        z = X @ w
        return float(np.sum(np.logaddexp(0, z) - y * z))
    r = optimize.minimize(nll, np.array([0.0, 1.0]), method="BFGS")
    w = r.x
    pz = 1 / (1 + np.exp(-(X @ w)))
    Hm = (X * (pz * (1 - pz))[:, None]).T @ X
    se = np.sqrt(np.diag(np.linalg.inv(Hm))) if np.linalg.cond(Hm) < 1e12 else np.array([math.nan, math.nan])
    return w, se


def auc(p, y):
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return math.nan
    return float(stats.mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg)))


def score(rows):
    p = np.clip(np.array([r["p"] for r in rows], float), 1e-4, 1 - 1e-4)
    y = np.array([1.0 if r["tp1_hit"] else 0.0 for r in rows])
    n = len(p)
    out = {"n": n, "mean_p": float(p.mean()), "observed": float(y.mean()), "observed_ci95": wilson(int(y.sum()), n)}
    if n < 2:
        return out
    base = y.mean()
    brier = float(np.mean((p - y) ** 2))
    brier_ref = float(np.mean((base - y) ** 2))
    out.update({"brier": brier, "brier_base_rate": brier_ref, "brier_skill": 1 - brier / brier_ref if brier_ref > 0 else math.nan,
                "brier_coin": float(np.mean((0.5 - y) ** 2)),
                "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), "auc": auc(p, y),
                "p_range": [float(p.min()), float(p.max())], "p_sd": float(p.std())})
    bins = [0, .4, .45, .5, .55, .6, .65, 1.0]
    rel = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rel.append({"bin": f"{lo:.2f}-{hi:.2f}", "n": int(m.sum()), "mean_p": float(p[m].mean()), "observed": float(y[m].mean()),
                        "observed_ci95": wilson(int(y[m].sum()), int(m.sum()))})
    out["reliability"] = rel
    if n >= 20 and p.std() > 1e-6:
        w, se = logit_fit(np.log(p / (1 - p)), y)
        out["calibration_intercept"], out["calibration_slope"] = float(w[0]), float(w[1])
        out["intercept_ci95"] = [float(w[0] - 1.96 * se[0]), float(w[0] + 1.96 * se[0])]
        out["slope_ci95"] = [float(w[1] - 1.96 * se[1]), float(w[1] + 1.96 * se[1])]
    # calibration-in-the-large: observed wins vs the sum of the shown probabilities (Poisson-binomial normal approximation)
    exp_, var_ = float(p.sum()), float(np.sum(p * (1 - p)))
    z = (float(y.sum()) - exp_) / math.sqrt(var_) if var_ > 0 else math.nan
    out["citl"] = {"expected_wins": exp_, "observed_wins": int(y.sum()), "z": z, "p_two_sided": float(2 * (1 - stats.norm.cdf(abs(z))))}
    if n >= 10 and out["citl"]["p_two_sided"] < 0.05:
        out["verdict"] = "NOT CALIBRATED (" + ("over" if z < 0 else "under") + "confident in the large)"
    elif n < 100:
        out["verdict"] = "INSUFFICIENT DATA"
    else:
        ok = ("slope_ci95" in out and out["slope_ci95"][0] <= 1 <= out["slope_ci95"][1]
              and out["intercept_ci95"][0] <= 0 <= out["intercept_ci95"][1] and out["brier_skill"] > 0)
        out["verdict"] = "CALIBRATED" if ok else "NOT CALIBRATED"
    return out


def load(path):
    try:
        d = json.load(open(path))
    except Exception:  # noqa: BLE001 - a malformed ledger is reported, not skipped silently
        return None
    return d if isinstance(d, list) else None


def main():
    res = {"current": {}, "archive": {}}
    for scope, pat in (("current", os.path.join(LED, "holdout", "*.json")), ("archive", os.path.join(LED, "holdout", "archive", "**", "*.json"))):
        groups, keys, bad, uniq = {}, {}, [], {}
        for f in sorted(glob.glob(pat, recursive=True)):
            if os.path.basename(f).startswith("manifest"):
                continue
            d = load(f)
            if d is None:
                bad.append(os.path.relpath(f, LED))
                continue
            rows = [t for t in d if isinstance(t, dict) and not t.get("open") and t.get("p") is not None and "tp1_hit" in t]
            name = os.path.relpath(f, os.path.join(LED, "holdout"))[:-5]
            fam = name.split("_", 1)[1] if "_" in os.path.basename(name) else name
            for t in rows:
                keys.setdefault(t.get("freeze_key"), 0)
                keys[t.get("freeze_key")] += 1
            groups.setdefault(name, []).extend(rows)
            groups.setdefault("ALL rows " + scope, []).extend(rows)
            tf = os.path.basename(name).split("_")[0]
            for t in rows:                                   # arms share entries: one row per (timeframe, entry, side)
                uniq.setdefault((tf, t.get("entry_time"), t.get("dir")), t)
            groups.setdefault("family " + fam.split("/")[-1], []).extend(rows)
        groups["UNIQUE trades " + scope] = list(uniq.values())
        res[scope] = {"unreadable": bad, "freeze_keys": keys, "groups": {k: score(v) for k, v in sorted(groups.items()) if v}}
    json.dump(res, open(OUT, "w"), indent=1)
    for scope in ("current", "archive"):
        print("==", scope, "freeze keys", res[scope]["freeze_keys"], "unreadable", len(res[scope]["unreadable"]))
        for k, v in res[scope]["groups"].items():
            if k.startswith(("ALL", "family", "UNIQUE")) or v["n"] >= 50:
                print(f"  {k:28s} n {v['n']:4d} mean p {v['mean_p']:.3f} obs {v['observed']:.3f} "
                      f"[{v['observed_ci95'][0]:.2f},{v['observed_ci95'][1]:.2f}] Brier {v.get('brier', float('nan')):.4f} "
                      f"base {v.get('brier_base_rate', float('nan')):.4f} skill {v.get('brier_skill', float('nan')):+.3f} "
                      f"logloss {v.get('log_loss', float('nan')):.3f} AUC {v.get('auc', float('nan')):.3f} "
                      f"slope {v.get('calibration_slope', float('nan')):+.2f} {[round(x, 2) for x in v.get('slope_ci95', [])]} "
                      f"CITL exp {v.get('citl', {}).get('expected_wins', float('nan')):.1f} obs {v.get('citl', {}).get('observed_wins', '-')} "
                      f"p {v.get('citl', {}).get('p_two_sided', float('nan')):.4f} -> {v.get('verdict')}")


if __name__ == "__main__":
    main()
