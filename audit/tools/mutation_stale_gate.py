"""Mutation test of the stale-signal gate (read-only on the repo).

Usage: python audit/tools/mutation_stale_gate.py <empty scratch dir>
Each mutant is applied to a COPY of quantum/notify.py in the scratch dir; tests/test_stale_signals.py plus
tests/test_stale_gate_paths.py must fail on it. G01-G12 move a rule boundary or remove a check of the deployed gate (the
15 / 15-60 / 60-minute rules must stay exactly as they are); G13-G17 undo one of the three 2026-11-12 fixes; G18-G24
open another way for a stale or repeated signal to become actionable. Exit status 1 if any mutant survives."""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
W = sys.argv[1]
TESTS = ["tests/test_stale_signals.py", "tests/test_stale_gate_paths.py"]

M = {
    # --- the three rules and the price check (must be unchanged) ---
    "G01 FRESH boundary exclusive (15 min exactly -> DELAYED)": ("    if age <= FRESH_SEC:\n", "    if age < FRESH_SEC:\n"),
    "G02 FRESH window 20 min": ("FRESH_SEC = 900 ", "FRESH_SEC = 1200 "),
    "G03 one-hour boundary inclusive (60 min exactly -> NOT ACTIONABLE)": ("    if age > RECOVERY_SEC:\n", "    if age >= RECOVERY_SEC:\n"),
    "G04 recovery window 2 h": ("RECOVERY_SEC = 3600 ", "RECOVERY_SEC = 7200 "),
    "G05 re-check price may be 6 min old": ("t_now - int(t_px) > PRICE_FRESH_SEC:", "t_now - int(t_px) > PRICE_FRESH_SEC + 60:"),
    "G06 a quote not marked live accepted": ("if px is None or not now.get(\"live\") or t_px is None", "if px is None or t_px is None"),
    "G07 LATE limit inclusive": ("    if abs(mv) >= lim:\n", "    if abs(mv) > lim:\n"),
    "G08 LATE limit one-sided (moves toward TP ignored)": ("    if abs(mv) >= lim:\n", "    if -mv >= lim:\n"),
    "G09 traded-level check removed": ("    hit = _traded(bars, int(t_close), d, entry, sl_px, tp_px)\n", "    hit = None\n"),
    "G10 the bar opening at the close is skipped": ("int(t) < t_close:", "int(t) <= t_close:"),
    "G11 stop / target swapped in the traded check": ("return \"SL\" if stop else \"TP\"", "return \"TP\" if stop else \"SL\""),
    "G12 DELAYED label not shown": ("                out.append(delayed_line(fz, off))", "                pass"),
    # --- the three 2026-11-12 fixes undone ---
    "G13 fix 1 undone: unpriced signal inside the hour re-checked": (
        "    if entry is None:                                      # a signal without a price cannot be re-checked\n"
        "        return {**out, \"state\": \"NOT ACTIONABLE\", \"why\": \"no signal price to re-check it\"}\n",
        "    if entry is None:\n        return {**out, \"state\": \"FRESH\"}\n"),
    "G14 fix 1 undone: unpriced signals not classified": ("            if m[\"type\"] == \"SIGNAL\" and m[\"t\"] > since:\n",
                                                          "            if m[\"type\"] == \"SIGNAL\" and m[\"t\"] > since and m.get(\"px\") is not None:\n"),
    "G15 fix 2 undone: oldest-first pruning": (
        "        drop = [k for k, v in g.items() if v.get(\"state\") != \"NOT ACTIONABLE\"] + \\\n",
        "        drop = list(g) + \\\n"),
    "G16 fix 2 weakened: no hold period": ("GATE_HOLD_SEC = 14 * 86400", "GATE_HOLD_SEC = 0"),
    "G17 fix 3 undone: a FRESH repeat of a quiet plan implies a position": (
        "out.append(repeat_line(m, tf, rp, off, quiet=rp.get(\"id\") in ((ctx or {}).get(\"quiet\") or ())))",
        "out.append(repeat_line(m, tf, rp, off))"),
    # --- other ways back to actionable ---
    "G18 a DELAYED repeat of a quiet plan stays DELAYED": (
        "if fz_rp and fz_rp[\"state\"] != \"FRESH\" and rp.get(\"id\") in gate_quiet(state, \"plan\"):",
        "if False and fz_rp and fz_rp[\"state\"] != \"FRESH\" and rp.get(\"id\") in gate_quiet(state, \"plan\"):"),
    "G19 quiet plans forgotten (follow-ups reach the phone)": (
        "    return {int(k.split(\":\", 1)[1]) for k, v in (state.get(\"fresh_gate\") or {}).items()\n",
        "    return set() and {int(k.split(\":\", 1)[1]) for k, v in (state.get(\"fresh_gate\") or {}).items()\n"),
    "G20 RECORD ONLY lines reach the phone": ("    return [x for x in lines if not x.startswith(RECORD_ONLY)]",
                                              "    return list(lines)"),
    "G21 no NOT ACTIONABLE summary line": ("        out.insert(stale_at, stale_line(\"engine signal\" + (\"s\" if len(stale) > 1 else \"\"), stale))",
                                           "        pass"),
    "G22 4h breakout path ungated": ("fz = freshness(e[\"t_close\"], d, x, SETUP_SL_PX, ENG_PX, now, [p, p15h, p5h])",
                                     "fz = {\"state\": \"FRESH\"}"),
    "G23 setup path ungated": ("fz = freshness(e[\"t\"] + 900, d, x, SETUP_SL_PX, ENG_PX, now, [p, p5s])",
                               "fz = {\"state\": \"FRESH\"}"),
    "G24 grab test path ungated": (
        "fzs[tr[\"id\"]] = freshness(int(tr[\"t\"]) + TF_SEC.get(tf, 0), tr[\"dir\"], tr[\"entry\"], GRAB_SL, GRAB_TP,\n"
        "                                          tr[\"alert\"], [p, same5])",
        "fzs[tr[\"id\"]] = {\"state\": \"FRESH\"}"),
}


def main() -> int:
    res, survived = {}, []
    for name, (a, b) in M.items():
        d = os.path.join(W, "r")
        shutil.rmtree(d, ignore_errors=True)
        for sub in ("quantum", "tests"):
            shutil.copytree(os.path.join(REPO, sub), os.path.join(d, sub), ignore=shutil.ignore_patterns("__pycache__"))
        p = os.path.join(d, "quantum", "notify.py")
        s = open(p).read()
        assert s.count(a) == 1, (name, s.count(a))
        open(p, "w").write(s.replace(a, b))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", *TESTS],
                           cwd=d, capture_output=True, text=True)
        failed = [ln.split("::")[1].split(" ")[0] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        if r.returncode == 0:
            survived.append(name)
        res[name] = {"killed": r.returncode != 0, "failing_tests": failed, "rc": r.returncode}
        print(("KILLED  " if r.returncode else "SURVIVED"), name, "->", len(failed), "failing test(s)", flush=True)
    json.dump(res, open(os.path.join(W, "mutation_stale_gate.json"), "w"), indent=1)
    print(f"{len(M) - len(survived)} of {len(M)} mutants killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
