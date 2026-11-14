"""Mutation test of the alert disclaimer (operator approval 2026-11-13): every way of breaking the policy must make the
tests fail.

Usage: python audit/tools/mutation_alert_disclaimer.py <empty scratch dir>
Copies quantum/ and tests/ into the scratch dir, applies one mutant at a time to quantum/notify.py there, runs the
disclaimer, stale-signal and plan tests, and reports KILLED / SURVIVED. The repository itself is never modified."""
import os
import shutil
import subprocess
import sys

W = sys.argv[1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
NOTIFY = "quantum/notify.py"
TESTS = ["tests/test_alert_disclaimer.py", "tests/test_stale_signals.py", "tests/test_notify_plan.py",
         "tests/test_alert_sixty.py", "tests/test_notify_delivery.py"]
D0 = 'TRADE_DISCLAIMER = ("RECORD \\u2014 NOT A VALIDATED SIGNAL \\u2014 NO TRADE",'

MUTANTS = {   # integrated with P-0 (#104): sends go through _say / _say_tf; the tf message is wrapped inside _say_tf
    "A01 wording changed": (D0, 'TRADE_DISCLAIMER = ("RECORD - NOT A VALIDATED SIGNAL - NO TRADE",'),
    "A02 explanation dropped": ('"a validated live trading edge.")', '"")'),
    "A03 lone disclaimer when nothing to send": ("return [*TRADE_DISCLAIMER, *lines] if lines else []",
                                                 "return [*TRADE_DISCLAIMER, *lines]"),
    "A04 engine alerts without it": ("_say(tf, trade_msg(out), sorted(events)", "_say(tf, out, sorted(events)"),
    "A05 setup alerts without it": ('"setup", trade_msg(sl_), [', '"setup", sl_, ['),
    "A06 4h alerts without it": ('"h4", trade_msg(hl), [', '"h4", hl, ['),
    "A07 grab trades without it": ('_say("grab_test", trade_msg(phone_only(glines)),', '_say("grab_test", phone_only(glines),'),
    "A08 setup results without it": ('_say("setup_updates", trade_msg(s_upd),', '_say("setup_updates", s_upd,'),
    "A09 on the daily report too": ('_say("report", lines, [rkey], "daily / weekly report")',
                                    '_say("report", trade_msg(lines), [rkey], "daily / weekly report")'),
    "A10 on the website lines too": ('report[tf] = {"lines": lines, "sent"', 'report[tf] = {"lines": trade_msg(lines), "sent"'),
    "A11 after the phone filter is skipped": ("allowed, j, pairs = phone_only(phone_lines), 0, []", "allowed, j, pairs = list(phone_lines), 0, []"),
    "A12 delivery log names the disclaimer": ('"first": (without_disclaimer(lines) or lines)[0][:80],', '"first": lines[0][:80],'),
    "A13 the DELIVERY WARNING above the disclaimer": ("    body = lines[:top] + warn + lines[top:]", "    body = warn + lines"),
    "A14 a RESENT line above the disclaimer": ("    return lines[:top] + [f\"RESENT ({'; '.join(notes)})\"[:RESENT_MAX]] + lines[top:] + ",
                                               "    return [f\"RESENT ({'; '.join(notes)})\"[:RESENT_MAX]] + lines + "),
}

def main():
    for d in ("quantum", "tests"):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(W, d), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    orig = open(os.path.join(W, NOTIFY), encoding="utf-8").read()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("FWD_B24", None)

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
