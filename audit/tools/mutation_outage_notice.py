"""Mutation test of the outage notice (read-only on the repo).

Usage: python audit/tools/mutation_outage_notice.py <empty scratch dir>
Each mutant is applied to a COPY (quantum/outage_notice.py or the workflow) in the scratch dir; tests/test_outage_notice.py
must fail on it. The workflow mutants are the condition variants GitHub itself evaluated in probe run 43172558297, plus
edits that break the step's wiring. Exit status 1 if any mutant survives."""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
W = sys.argv[1]
MOD = "quantum/outage_notice.py"
WF = ".github/workflows/quantum-site.yml"
COND_A = "(failure() || cancelled()) && format('x{0}', vars.OUTAGE_NOTICE) != 'x0'"
COND_B = "&& (steps.pipeline.outcome != 'success' || steps.savestore.outcome != 'success')"

M = {
    # --- quantum/outage_notice.py ---
    "N01 kind: only a FAILED pipeline counts (skipped / timed out missed)": (MOD, 'if (pipeline or "").strip() != "success":', 'if (pipeline or "").strip() == "failure":'),
    "N02 kind: store-save failure ignored": (MOD, '        return "state"\n', '        return None\n'),
    "N03 kind: down and state swapped": (MOD, '        return "down"\n', '        return "state"\n'),
    "N04 dedupe: any message counts, not only outage notices": (MOD, "if OUTAGE_TAG in (m.get(\"tags\") or []) and now", "if now"),
    "N05 dedupe: window inclusive (<=)": (MOD, "< window_min * 60:", "<= window_min * 60:"),
    "N06 dedupe: fail closed when ntfy's record is unreadable": (MOD, "        recent = False\n        out[\"dedupe\"] = f\"unavailable", "        recent = True\n        out[\"dedupe\"] = f\"unavailable"),
    "N07 any HTTP answer counted as sent": (MOD, 'out["sent"] = 200 <= out["http"] < 300', 'out["sent"] = True'),
    "N08 reminder every 60 min, not 180": (MOD, "REPEAT_MIN = 180", "REPEAT_MIN = 60"),
    "N09 notice sent without the outage tag (dedupe can never see it)": (MOD, '"Tags": f"warning,{OUTAGE_TAG}"', '"Tags": "warning"'),
    "N10 the topic leaks into the log": (MOD, 'out = {"kind": kind(env.get("PIPELINE", ""), env.get("SAVESTORE", "")), "sent": False}',
                                         'out = {"kind": kind(env.get("PIPELINE", ""), env.get("SAVESTORE", "")), "sent": False, "t": env.get("NTFY_TOPIC")}'),
    "N11 down message replaced by the state message": (MOD, '    "down": ("XAUUSD SITE DOWN: the site run of {hhmm} UTC failed, so alerts are paused until a run succeeds. "',
                                                       '    "down": ("XAUUSD ALERT STATE NOT SAVED: the site run of {hhmm} UTC failed, so alerts are paused until a run succeeds. "'),
    "N12 poll window not sent to ntfy": (MOD, "/json?poll=1&since={int(window_min)}m", "/json?poll=1"),
    "N13 a non-stdlib import (breaks when pip install failed)": (MOD, "import urllib.request\n", "import urllib.request\nimport requests  # noqa\n"),
    "N14 a refused send raises": (MOD, '        out["http"] = getattr(e, "code", None)\n', '        raise\n'),
    # --- the workflow condition and wiring ---
    "W01 deployed condition (null bug)": (WF, f"{COND_A}\n          {COND_B}", "failure() && vars.OUTAGE_NOTICE != '0'"),
    "W02 first PR-A version (no cancelled(): a timed-out run is silent)": (WF, "(failure() || cancelled())", "failure()"),
    "W03 store-save clause removed": (WF, COND_B, "&& steps.pipeline.outcome != 'success'"),
    "W04 || turned into &&": (WF, COND_B, "&& (steps.pipeline.outcome != 'success' && steps.savestore.outcome != 'success')"),
    "W05 outcome clause removed (Pages-only failures page the phone)": (WF, f"\n          {COND_B}", ""),
    "W06 null bug back in the off switch": (WF, "format('x{0}', vars.OUTAGE_NOTICE) != 'x0'", "vars.OUTAGE_NOTICE != '0'"),
    "W07 == 'failure' instead of != 'success'": (WF, COND_B, "&& (steps.pipeline.outcome == 'failure' || steps.savestore.outcome == 'failure')"),
    "W08 savestore id removed": (WF, "        id: savestore\n", ""),
    "W09 step outcome not passed to the script": (WF, "          SAVESTORE: ${{ steps.savestore.outcome }}\n", ""),
    "W10 continue-on-error removed (a notice failure fails the run)": (WF, "        continue-on-error: true\n        timeout-minutes: 2\n", "        timeout-minutes: 2\n"),
}


def main() -> int:
    res, survived = {}, []
    for name, (rel, a, b) in M.items():
        d = os.path.join(W, "r")
        shutil.rmtree(d, ignore_errors=True)
        for sub in ("quantum/__init__.py", MOD, "tests/conftest.py", "tests/test_outage_notice.py",
                    "tests/fixtures/outage_condition_probe.json", WF):
            os.makedirs(os.path.dirname(os.path.join(d, sub)), exist_ok=True)
            shutil.copy(os.path.join(REPO, sub), os.path.join(d, sub))
        p = os.path.join(d, rel)
        s = open(p).read()
        assert s.count(a) == 1, (name, s.count(a))
        open(p, "w").write(s.replace(a, b))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-p", "no:cacheprovider",
                            "tests/test_outage_notice.py"], cwd=d, capture_output=True, text=True)
        failed = [ln.split("::")[1].split(" ")[0] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        if r.returncode == 0:
            survived.append(name)
        res[name] = {"killed": r.returncode != 0, "failing_tests": failed, "rc": r.returncode}
        print(("KILLED  " if r.returncode else "SURVIVED"), name, "->", len(failed), "failing test(s)", flush=True)
    json.dump(res, open(os.path.join(W, "mutation_outage_notice.json"), "w"), indent=1)
    print(f"{len(M) - len(survived)} of {len(M)} mutants killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
