"""Mutation test of the SIGNAL alert's first line (operator approval 2026-11-13): the plan stop named, the engine's
levels labelled reference. Every way of breaking it must make the tests fail.

Usage: python audit/tools/mutation_engine_reference.py <empty scratch dir>
Copies quantum/ and tests/ into the scratch dir, applies one mutant at a time to quantum/notify.py there, runs the
headline, plan, sixty-mode and stale-signal tests, and reports KILLED / SURVIVED. The repository itself is never
modified."""
import os
import shutil
import subprocess
import sys

W = sys.argv[1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
NOTIFY = "quantum/notify.py"
TESTS = ["tests/test_engine_reference_levels.py", "tests/test_notify_plan.py", "tests/test_alert_sixty.py",
         "tests/test_stale_signals.py", "tests/test_stale_gate_paths.py"]
OLD = ('''    return (f"XAUUSD {tf} {d} (confirmed close) | entry {_fmt(m['px'], off)} SL {_fmt(m['sl'], off)} "
            f"TP1 {_fmt(m['tp1'], off)} TP2 {_fmt(m['tp2'], off)} TP3 {_fmt(m['tp3'], off)} | TQ {m['tq']}")
''')

MUTANTS = {
    "E01 the old first line": ('    head = f"XAUUSD {tf} {d} (confirmed close) | entry {_fmt(m[\'px\'], off)}"\n', OLD),
    "E02 the plan's TP named as the stop": ('        sl, _ = plan_levels(m["px"], m["dir"], pl)', '        _, sl = plan_levels(m["px"], m["dir"], pl)'),
    "E03 the stop without the MT5 offset": ("plan stop SL {_fmt(sl, off)}", "plan stop SL {_fmt(sl)}"),
    "E04 a stop named on a REPEAT": ("signal_head(m, tf, d, pl if rp is None else None, off)", "signal_head(m, tf, d, pl, off)"),
    "E05 the reference label dropped": ('ENGINE_REF = "engine reference only"', 'ENGINE_REF = "engine"'),
    "E06 'not the plan' dropped": ('        ref += ", not the plan"', '        ref += ""'),
    "E07 an engine level dropped": ("TP3 {_fmt(m['tp3'], off)} | TQ {m['tq']}\")", "| TQ {m['tq']}\")"),
    "E08 the target's amount named as the stop's": ("(-${pl['sl_usd']:,.0f})\"\n        ref", "(-${pl['tp_usd']:,.0f})\"\n        ref"),
    "E09 the plan stop never named": ('    if pl and m.get("px") is not None:\n        sl, _', '    if pl and False:\n        sl, _'),
    "E10 the prefix the filters key on changed": ('(confirmed close) | entry {_fmt(m[\'px\'], off)}"\n    ref', '(confirmed close): entry {_fmt(m[\'px\'], off)}"\n    ref'),
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
        mut = orig.replace(a, b)
        if name.startswith("E01"):                         # replace the whole body with the old line
            i = orig.index(a)
            j = orig.index("\n\n\ndef messages(", i)
            mut = orig[:i] + b + orig[j:]
        open(os.path.join(W, NOTIFY), "w", encoding="utf-8").write(mut)
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
