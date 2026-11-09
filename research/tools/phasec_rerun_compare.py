"""Phase C: compare the corrected re-runs (b27.SELECT_ON = "raw", break_even_decided) with the registered runs as run.

Checks that every study the fix does not touch reproduces exactly (B27 S1 / S2 / S5, B29 G / V / M / E: n, rate, interval,
expectancy, p-value), then lists what changed: the model studies (B27 S3, B29 C), the frozen sets, and the 2026 checks.
With --trials, appends the changed configurations and every frozen 2026 check of the re-runs to the trial log
(append-only; phases "B27-fix" / "B29-fix").

  python research/tools/phasec_rerun_compare.py research/results/b27 research/results/b27_fix research/results/b29 \
      research/results/b29_fix [--trials research/trials.jsonl]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, ".")
from quantum.research import harness as H

KEYS = ("n_decided", "r", "ci95", "exp_oz", "p_vs_random", "matched_random")


def load(d, name):
    with open(os.path.join(d, name)) as fh:
        return json.load(fh)


def same(a, b) -> bool:
    for k in KEYS:
        x, y = a.get(k), b.get(k)
        if isinstance(x, list) or isinstance(y, list):
            if (x is None) != (y is None) or (x and any(not _eq(u, v) for u, v in zip(x, y, strict=True))):
                return False
        elif not _eq(x, y):
            return False
    return True


def _eq(x, y) -> bool:
    if x is None or y is None:
        return x is y
    if isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y):
        return True
    return abs(float(x) - float(y)) <= 1e-9 * max(1.0, abs(float(x)))


def check(old: list, new: list, label: str) -> int:
    o = {c["id"]: c["dev"] for c in old}
    n = {c["id"]: c["dev"] for c in new}
    assert set(o) == set(n), f"{label}: configuration sets differ"
    bad = [k for k in o if not same(o[k], n[k])]
    print(f"- {label}: {len(o)} configurations, {len(o) - len(bad)} identical" + (f", DIFFERENT: {bad[:5]}" if bad else ""))
    return len(bad)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("b27_old")
    ap.add_argument("b27_new")
    ap.add_argument("b29_old")
    ap.add_argument("b29_new")
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    o27, n27 = load(a.b27_old, "b27_summary.json"), load(a.b27_new, "b27_summary.json")
    o29, n29 = load(a.b29_old, "b29_summary.json"), load(a.b29_new, "b29_summary.json")
    print("## Reproduction of the studies the fix does not touch\n")
    bad = sum(check(o27[k], n27[k], f"B27 {k}") for k in ("S1", "S2", "S5"))
    g_old = [{"id": e["id"], "dev": e["ENG"]} for e in o29["G"]]
    g_new = [{"id": e["id"], "dev": e["ENG"]} for e in n29["G"]]
    bad += check(g_old, g_new, "B29 G (ENG)")
    bad += sum(check(o29[k], n29[k], f"B29 {k}") for k in ("V", "M", "E"))
    s4o, s4n = o27["S4"], n27["S4"]
    s4_bad = [k for k in ("univariate_auc", "permutation_auc_drop") for f in s4o[k] if not _eq(s4o[k][f], s4n[k].get(f))]
    s4_bad += [f for f in s4o["ablation"] if not _eq(s4o["ablation"][f]["change"], s4n["ablation"][f]["change"])]
    print(f"- B27 S4 (feature ranking, FEATURE_AUDIT.md): {'identical' if not s4_bad else f'DIFFERENT: {s4_bad[:5]}'}")
    bad += len(s4_bad)
    print(f"\nNon-model differences: {bad}.\n")
    print("## Model studies: as run (calibrated threshold) against corrected (raw score)\n")
    for lab, old, new in (("B27 S3", o27["S3"], n27["S3"]), ("B29 C", o29["C"], n29["C"])):
        o = {c["id"]: c for c in old}
        print(f"\n### {lab}\n")
        print("| Configuration | n as run | r as run | n corrected | r corrected | Random | Exp / oz corrected | p corrected | BH |")
        print("|---|---|---|---|---|---|---|---|---|")
        for c in new:
            d, od = c["dev"], o[c["id"]]["dev"]
            print(f"| {c['id']} | {od.get('n_decided')} | {_p(od.get('r'))} | {d.get('n_decided')} | {_p(d.get('r'))} | {_p(d.get('matched_random'))} | "
                  f"{_n(d.get('exp_oz'))} | {_n(d.get('p_vs_random'), 4)} | {'yes' if c['bh'] else 'no'} |")
        print(f"\nBH-significant: {sum(c['bh'] for c in new)}; INFORMATIVE: {sum(c['informative'] for c in new)}; "
              f"TRADEABLE: {sum(c['tradeable'] for c in new)} (of {len(new)}).")
    print("\n## Frozen sets and 2026\n")
    for lab, old, new in (("B27", o27["frozen"], n27["frozen"]), ("B29", o29["frozen"], n29["frozen"])):
        oi, ni = [c["id"] for c in old], [c["id"] for c in new]
        print(f"- {lab}: {len(ni)} frozen; new: {[x for x in ni if x not in oi]}; dropped: {[x for x in oi if x not in ni]}; "
              f"hold on 2026: {sum(bool(c.get('holds_2026')) for c in new)}; smallest Holm p: "
              f"{min((c.get('y2026_holm_p') or 1.0) for c in new):.3f}")
    if a.trials:
        for phase, s, keys in (("B27-fix", n27, ("S3",)), ("B29-fix", n29, ("C",))):
            for k in keys:
                for c in s[k]:
                    dv = c["dev"]
                    H.log_trial(a.trials, {"phase": phase, "partition": "development", "id": f"{phase} {c['id']}", "n": dv.get("n_decided"),
                                           "success": dv.get("r"), "ci95": dv.get("ci95"), "net_usd_per_oz": dv.get("exp_oz"),
                                           "verdict": "TRADEABLE" if c["tradeable"] else ("INFORMATIVE" if c["informative"] else "NO"),
                                           "note": "re-run with top-q on the raw score (SELECT_ON = raw), Phase C audit"})
            for c in s["frozen"]:
                y_ = c.get("y2026") or {}
                H.log_trial(a.trials, {"phase": phase, "partition": "unsealed 2026 (frozen check)", "id": f"{phase} {c['id']}",
                                       "n": y_.get("n_decided"), "success": y_.get("r"), "ci95": y_.get("ci95"),
                                       "net_usd_per_oz": y_.get("exp_oz"), "holm_p": c.get("y2026_holm_p"),
                                       "verdict": "HOLDS" if c.get("holds_2026") else "DOES NOT HOLD"})
        print(f"\nTrials appended to {a.trials}.")
    return 1 if bad else 0


def _p(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def _n(x, d=2):
    return "—" if x is None else f"{x:+.{d}f}" if d == 2 else f"{x:.{d}f}"


if __name__ == "__main__":
    raise SystemExit(main())
