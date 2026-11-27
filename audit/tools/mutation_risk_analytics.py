"""Mutation test of the G5 risk analytics (read-only on the repo).

Usage: python audit/tools/mutation_risk_analytics.py <empty scratch dir> [--json out.json]
Each mutant is applied to a COPY of audit/tools/risk_analytics.py in the scratch dir; tests/test_risk_analytics.py must
fail on it. M11 is an equivalent mutant for the property tested (a seed that depends only on the group's own key keeps
every other group's numbers unchanged when a group is added); it is listed so the run shows it, and does not fail.
"""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EQUIVALENT = {"M11 group seed from the key's length, not its hash"}
M = {
    "M01 CVaR k rounded down": ("k = max(1, math.ceil(alpha * n))", "k = max(1, math.floor(alpha * n))"),
    "M02 the start is not a peak": ("eq = np.concatenate([[0.0], np.cumsum(r)])", "eq = np.cumsum(r)"),
    "M03 calendar day, not the 17:00 New York session day": ("return (t + timedelta(hours=7)).date().isoformat()", "return t.date().isoformat()"),
    "M04 blocks do not wrap": ("cur = (cur + 1) % n_days", "cur = min(cur + 1, n_days - 1)"),
    "M05 never a new block": ("if i == 0 or rng.random() < p_new:", "if i == 0:"),
    "M06 trades shuffled inside a day": ("out[s] = max_drawdown(np.concatenate([days[i] for i in idx]))",
                                          "out[s] = max_drawdown(np.random.default_rng(s).permutation(np.concatenate([days[i] for i in idx])))"),
    "M07 before-cost expectancy equals after-cost": ('gross = (np.array([t["gross_pts"] for t in trades], float)[ok] / d_sl[ok])',
                                                      'gross = np.array([t["r"] for t in trades], float)[ok]'),
    "M08 ledger order, not exit order": ('        v.sort(key=lambda t: (t["exit_time"], t["entry_time"]))', "        pass"),
    "M09 open trades counted": ('            if t.get("open"):\n                continue', "            pass"),
    "M10 freeze keys merged": ('key = (m.group(2), m.group(1), t.get("freeze_key") or t.get("config_hash") or "")', 'key = (m.group(2), m.group(1), "")'),
    "M11 group seed from the key's length, not its hash": ("return seed + int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)", "return seed + len(key)"),
    "M12 the 95th percentile is the median": ("q = {p: round(float(np.quantile(dd, p / 100)), 4) for p in (50, 95, 99)}",
                                              "q = {p: round(float(np.quantile(dd, 0.5)), 4) for p in (50, 95, 99)}"),
    "M13 measured cost reported as the modelled one": ('"after_measured_cost": None,', '"after_measured_cost": round(float(net.mean()), 4) if n else None,'),
}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    w = argv[0]
    out = argv[argv.index("--json") + 1] if "--json" in argv else os.path.join(w, "mutation.json")
    res = {}
    for name, (a, b) in M.items():
        d = os.path.join(w, "r")
        shutil.rmtree(d, ignore_errors=True)
        for sub in ("quantum", "tests", "audit/tools", "docs/final_audit"):
            shutil.copytree(os.path.join(REPO, sub), os.path.join(d, sub), ignore=shutil.ignore_patterns("__pycache__"))
        p = os.path.join(d, "audit", "tools", "risk_analytics.py")
        with open(p) as f:
            s = f.read()
        assert s.count(a) == 1, name
        with open(p, "w") as f:
            f.write(s.replace(a, b))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-p", "no:cacheprovider",
                            "tests/test_risk_analytics.py"], cwd=d, capture_output=True, text=True, check=False)
        failed = [x.split("::")[1].split(" ")[0] for x in r.stdout.splitlines() if x.startswith("FAILED")]
        res[name] = failed
        tag = "KILLED  " if failed else ("EQUIVAL." if name in EQUIVALENT else "SURVIVED")
        print(tag, name, "->", len(failed), "test(s) failed", flush=True)
    shutil.rmtree(os.path.join(w, "r"), ignore_errors=True)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    survived = [k for k, v in res.items() if not v and k not in EQUIVALENT]
    print(f"{sum(1 for v in res.values() if v)} of {len(res)} killed; equivalent: {len(EQUIVALENT)}; survived: {len(survived)}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
