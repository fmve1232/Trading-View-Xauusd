"""Mutation test of the daily / weekly report split (operator approval 2026-11-13): every way of breaking it must make the
tests fail.

Usage: python audit/tools/mutation_daily_report_split.py <empty scratch dir>
Copies quantum/ and tests/ into the scratch dir, applies one mutant at a time to quantum/notify.py there, runs the split,
plan and sixty-mode tests, and reports KILLED / SURVIVED. The repository itself is never modified."""
import os
import shutil
import subprocess
import sys

W = sys.argv[1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
NOTIFY = "quantum/notify.py"
TESTS = ["tests/test_daily_report_split.py", "tests/test_notify_plan.py", "tests/test_alert_sixty.py"]

MUTANTS = {
    "D01 no split in sixty mode": ("    if not sixty():\n        return report_lines(kind, label,", "    if True:\n        return report_lines(kind, label,"),
    "D02 split in the other modes too": ("    if not sixty():\n        return report_lines(kind, label,", "    if False:\n        return report_lines(kind, label,"),
    "D03 website records in the phone headline": ("    phone = [r for r in recs if r.get(\"tf\") in PHONE_TFS_SIXTY]", "    phone = list(recs)"),
    "D04 website line dropped": ("        out.insert(1, line)", "        pass"),
    "D05 phone open count includes website plans": ("summarize(phone, cost_per_lot),\n                       p_open)",
                                                     "summarize(phone, cost_per_lot),\n                       len(open_plans))"),
    "D06 website open count dropped": ('                + (f" | still open {w_open}" if w_open else ""))', '                + "")'),
    "D07 label claims every 15m alert was sent": ("(your phone's timeframe)", "(sent to your phone)"),
    "D08 website timeframes unsorted": ("key=lambda x: TF_SEC.get(x, 0))", "key=str)"),
    "D09 the caller's records modified": ("    w_open = len(open_plans) - p_open\n", "    w_open = len(open_plans) - p_open\n    recs[:] = phone\n"),
    "D10 daily report not split": ('lines += period_report_lines("DAILY", date.fromisoformat(prev).strftime("%a %d %b"), recs, open_d, cpl)',
                                   'lines += report_lines("DAILY", date.fromisoformat(prev).strftime("%a %d %b"), summarize(recs, cpl), len(open_d))'),
    "D11 weekly report not split": ('lines += period_report_lines("WEEKLY", prev, recs, open_w, cpl)',
                                    'lines += report_lines("WEEKLY", prev, summarize(recs, cpl), len(open_w))'),
    "D12 website block narrowed to the phone": ('report["plans"]["validation"] = validation_block(vlog, plans, now_t, cpl)',
                                                'report["plans"]["validation"] = validation_block([r for r in vlog if r["tf"] in PHONE_TFS_SIXTY], plans, now_t, cpl)'),
    "D13 expired counted as closed": ('(f"{sw[\'n\']} closed, TP first {sw[\'tp\']}/{sw[\'n\']} = {sw[\'rate\']:.0%}" if sw["n"] else "none closed")',
                                      '(f"{len(web)} closed, TP first {sw[\'tp\']}/{sw[\'n\']}" if web else "none closed")'),
}


def main():
    for d in ("quantum", "tests"):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(W, d), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    orig = open(os.path.join(W, NOTIFY), encoding="utf-8").read()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("FWD_B24", None)
    env.pop("ALERT_MODE", None)

    def run():
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TESTS], cwd=W,
                              capture_output=True, text=True, env=env).returncode

    killed = 0
    for name, (a, b) in MUTANTS.items():
        assert orig.count(a) == 1, name
        open(os.path.join(W, NOTIFY), "w", encoding="utf-8").write(orig.replace(a, b))
        k = run() != 0
        killed += k
        print(("KILLED   " if k else "SURVIVED ") + name)
    open(os.path.join(W, NOTIFY), "w", encoding="utf-8").write(orig)
    ok = run() == 0
    print(f"unmutated: {'PASS' if ok else 'FAIL'}")
    print(f"{killed} of {len(MUTANTS)} mutants killed")
    sys.exit(0 if killed == len(MUTANTS) and ok else 1)


if __name__ == "__main__":
    main()
