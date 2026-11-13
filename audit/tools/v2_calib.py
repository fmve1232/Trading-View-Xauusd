"""Stage-2 verification of the forward calibration of the engine's `p` (read-only).

  python3 -I audit/tools/v2_calib.py <forward-ledger dir> <out dir>

What `p` is here. quantum/holdout.update_ledger writes a trade once, the first time a run sees it CLOSED; the row's `p`
is the value that run's engine computed for the ENTRY bar (backtest.py: pos["p"] at entry). The engine has no
look-ahead (tests/test_no_lookahead.py), so the outcome cannot enter `p`; but the run is later than the entry, so `p`
reflects any revision of earlier bars and that run's data window. The value shown on the site at entry time was never
stored and cannot be recovered.

Unit of analysis. One row per (timeframe, entry time, side): arms (treatment, challenger, control, H5, H6) share
entries, and those rows have the same outcome. Trades on different timeframes at nearby times are kept but reported.

Test (calibration-in-the-large). H0: each trade i reaches TP1 first independently with probability p_i (the p the
ledger recorded). Under H0 the number of TP1 trades S follows a Poisson-binomial distribution; the exact two-sided
p-value sums the probabilities of every count at most as likely as the observed one. Also: the normal approximation,
a Wilson interval for the observed rate, and bootstrap intervals for (observed rate - mean p) resampling trades and
resampling trading days (clusters), which relaxes independence within a day.
Outputs: v2_calib.json, v2_calib_trades.csv (every unique trade: the independent check)."""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
from scipy import stats

LED, OUT = sys.argv[1], sys.argv[2]
RNG = np.random.default_rng(20261113)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def poisson_binomial(p):
    """Exact distribution of the number of successes, by dynamic programming."""
    f = np.zeros(len(p) + 1)
    f[0] = 1.0
    for q in p:
        f[1:] = f[1:] * (1 - q) + f[:-1] * q
        f[0] *= (1 - q)
    return f


def exact_two_sided(p, s):
    f = poisson_binomial(p)
    return float(f[f <= f[s] * (1 + 1e-9)].sum()), float(f[: s + 1].sum()), float(f[s:].sum())


def wilson(k, n, z=1.959963984540054):
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def boot(diff_fn, units, reps=20000):
    out = np.empty(reps)
    m = len(units)
    for r in range(reps):
        out[r] = diff_fn([units[i] for i in RNG.integers(0, m, m)])
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def analyse(rows):
    p = np.array([r["p"] for r in rows], float)
    y = np.array([r["tp1"] for r in rows], int)
    n, s = len(p), int(y.sum())
    two, lower, upper = exact_two_sided(p, s)
    var = float(np.sum(p * (1 - p)))
    z = (s - p.sum()) / math.sqrt(var)
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["entry_time"][:10]].append(r)
    days = list(by_day.values())

    def diff(rs):
        return float(np.mean([x["tp1"] for x in rs]) - np.mean([x["p"] for x in rs]))
    return {"n": n, "tp1": s, "observed": s / n, "observed_wilson95": wilson(s, n), "mean_p": float(p.mean()),
            "expected_tp1": float(p.sum()), "exact_p_two_sided": two, "exact_p_le_observed": lower, "exact_p_ge_observed": upper,
            "normal_z": float(z), "normal_p_two_sided": float(2 * stats.norm.sf(abs(z))),
            "diff_obs_minus_p": diff(rows), "diff_boot95_trades": boot(diff, rows),
            "diff_boot95_day_clusters": boot(lambda ds: diff([x for d in ds for x in d]), days),
            "trading_days": len(days), "max_trades_one_day": max(len(d) for d in days),
            "brier": float(np.mean((p - y) ** 2)), "brier_base_rate": float(np.mean((y.mean() - y) ** 2)),
            "auc": float(stats.mannwhitneyu(p[y == 1], p[y == 0]).statistic / (s * (n - s))) if 0 < s < n else None}


def main():
    os.makedirs(OUT, exist_ok=True)
    res, inputs = {}, {}
    all_rows = []
    for scope, pat in (("current", os.path.join(LED, "holdout", "*.json")),
                       ("archive", os.path.join(LED, "holdout", "archive", "*.json"))):
        uniq = {}
        n_rows = 0
        for f in sorted(glob.glob(pat)):
            if os.path.basename(f).startswith("manifest"):
                continue
            inputs[os.path.relpath(f, LED)] = sha(f)
            tf, arm = os.path.basename(f)[:-5].split("_", 1)
            for t in json.load(open(f)):
                if not isinstance(t, dict) or t.get("open") or t.get("p") is None or "tp1_hit" not in t:
                    continue
                n_rows += 1
                k = (tf, t["entry_time"], t["dir"])
                u = uniq.setdefault(k, {"scope": scope, "tf": tf, "entry_time": t["entry_time"], "dir": t["dir"], "arms": [],
                                        "p_values": [], "tp1_values": [], "freeze_keys": set(), "recorded_utc": [],
                                        "exit_time": t.get("exit_time"), "exit_reason": t.get("exit_reason"), "entry": t.get("entry")})
                u["arms"].append(arm)
                u["p_values"].append(float(t["p"]))
                u["tp1_values"].append(bool(t["tp1_hit"]))
                u["freeze_keys"].add(t.get("freeze_key"))
                u["recorded_utc"].append(t.get("recorded_utc"))
        rows = []
        conflicts = 0
        for u in uniq.values():
            if len(set(u["tp1_values"])) > 1 or max(u["p_values"]) - min(u["p_values"]) > 1e-9:
                conflicts += 1
            rows.append({**u, "p": float(np.mean(u["p_values"])), "tp1": int(u["tp1_values"][0]),
                         "freeze_keys": sorted(k for k in u["freeze_keys"] if k)})
        rows.sort(key=lambda r: r["entry_time"])
        all_rows += rows
        res[scope] = {"ledger_rows_with_p": n_rows, "unique_trades": len(rows),
                      "rows_whose_arms_disagree_on_p_or_outcome": conflicts, "pooled": analyse(rows) if rows else None,
                      "by_freeze_key": {}, "by_timeframe": {}}
        fk = defaultdict(list)
        for r in rows:
            fk[" + ".join(r["freeze_keys"])].append(r)
        for k, rs in sorted(fk.items()):
            res[scope]["by_freeze_key"][k] = analyse(rs) if len(rs) >= 5 else {"n": len(rs)}
        for tf in sorted({r["tf"] for r in rows}):
            rs = [r for r in rows if r["tf"] == tf]
            res[scope]["by_timeframe"][tf] = analyse(rs) if len(rs) >= 5 else {"n": len(rs)}
        # nearby trades on other timeframes, same side, entries within 4 hours: a dependence diagnostic
        near = 0
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if b["dir"] == a["dir"] and b["tf"] != a["tf"] and abs(np.datetime64(b["entry_time"][:19]) - np.datetime64(a["entry_time"][:19])) <= np.timedelta64(4, "h"):
                    near += 1
        res[scope]["same_side_pairs_on_other_timeframes_within_4h"] = near
    res["inputs_sha256"] = inputs
    json.dump(res, open(os.path.join(OUT, "v2_calib.json"), "w"), indent=1, default=list)
    with open(os.path.join(OUT, "v2_calib_trades.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "timeframe", "entry_time", "side", "entry", "p", "tp1_hit", "exit_time", "exit_reason", "arms", "freeze_keys", "first_recorded_utc"])
        for r in all_rows:
            w.writerow([r["scope"], r["tf"], r["entry_time"], "BUY" if r["dir"] == 1 else "SELL", r["entry"], f"{r['p']:.4f}", r["tp1"],
                        r["exit_time"], r["exit_reason"], "|".join(sorted(r["arms"])), "|".join(r["freeze_keys"]), min(x for x in r["recorded_utc"] if x)])
    for scope in ("current", "archive"):
        s = res[scope]
        a = s["pooled"]
        print(f"== {scope}: {s['ledger_rows_with_p']} ledger rows -> {s['unique_trades']} unique trades; arms disagreeing {s['rows_whose_arms_disagree_on_p_or_outcome']}; "
              f"same-side pairs on other timeframes within 4 h: {s['same_side_pairs_on_other_timeframes_within_4h']}")
        print(f"   TP1 {a['tp1']}/{a['n']} = {a['observed']:.3f} Wilson {[round(x, 3) for x in a['observed_wilson95']]} | mean p {a['mean_p']:.3f} expected {a['expected_tp1']:.1f}"
              f" | exact two-sided p {a['exact_p_two_sided']:.5f} (P[S<=obs] {a['exact_p_le_observed']:.5f}) | normal z {a['normal_z']:.2f} p {a['normal_p_two_sided']:.5f}")
        print(f"   obs - p {a['diff_obs_minus_p']:+.3f}; bootstrap 95% trades {[round(x, 3) for x in a['diff_boot95_trades']]}, day clusters {[round(x, 3) for x in a['diff_boot95_day_clusters']]}"
              f" ({a['trading_days']} days, max {a['max_trades_one_day']} a day) | Brier {a['brier']:.4f} vs base {a['brier_base_rate']:.4f} | AUC {a['auc']}")
        for k, v in s["by_freeze_key"].items():
            print(f"   key {k[:60]:60s} n {v['n']:3d}" + (f" obs {v['observed']:.2f} mean p {v['mean_p']:.2f} exact p {v['exact_p_two_sided']:.4f}" if "observed" in v else ""))
        for k, v in s["by_timeframe"].items():
            print(f"   tf {k:4s} n {v['n']:3d}" + (f" obs {v['observed']:.2f} mean p {v['mean_p']:.2f} exact p {v['exact_p_two_sided']:.4f}" if "observed" in v else ""))


if __name__ == "__main__":
    main()
