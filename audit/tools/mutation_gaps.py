"""Mutation test of the Amendment 14 fill rule (read-only on the repo).

Usage: python audit/tools/mutation_gaps.py <empty scratch dir>
Each mutant is applied to a COPY of quantum/backtest.py in the scratch dir; tests/test_backtest_gaps.py must fail on it.
M05 and M14 are equivalent mutants (no input can distinguish them; see audit/WEB7_VERIFICATION_2026-11-01.md)."""
import os, shutil, subprocess, sys, json
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")); W = sys.argv[1]
M = {
 "M01 stop gap filled at the stop price (web.6 optimism)": ('_close(pos, oi, i, idx, stop_lbl + "_GAP", trades)', '_close(pos, pos["sl"], i, idx, stop_lbl + "_GAP", trades)'),
 "M02 whole rule removed (revert to web.6)": ("gap_ok = not math.isnan(oi)", "gap_ok = False"),
 "M03 TP2 open-gap removed": ('if gap_ok and beyond(pos["tp2"]):', 'if False and beyond(pos["tp2"]):'),
 "M04 TP1 open-gap removed": ('elif gap_ok and not pos["tp1_done"] and beyond(pos["tp1"]):', 'elif False:'),
 "M05 TP2 gap forgets TP1's half": ('                if not pos["tp1_done"]:\n                    pos["legs"].append((0.5, oi))\n                    pos["qty"] -= 0.5\n                    pos["tp1_done"] = True\n                _close(pos, oi, i, idx, "TP2", trades)', '                pos["tp1_done"] = True\n                _close(pos, oi, i, idx, "TP2", trades)'),
 "M06 TP gap filled at the limit, not the open": ('_close(pos, oi, i, idx, "TP2", trades)', '_close(pos, pos["tp2"], i, idx, "TP2", trades)'),
 "M07 long stop test strict (<)": ("through = (lambda lvl: oi <= lvl) if lg", "through = (lambda lvl: oi < lvl) if lg"),
 "M08 short stop test strict (>)": ("else (lambda lvl: oi >= lvl)       # past the stop", "else (lambda lvl: oi > lvl)       # past the stop"),
 "M09 short stop direction inverted": ("else (lambda lvl: oi >= lvl)       # past the stop", "else (lambda lvl: oi <= lvl)       # past the stop"),
 "M10 short target direction inverted": ("else (lambda lvl: oi <= lvl)        # past a target", "else (lambda lvl: oi >= lvl)        # past a target"),
 "M11 breakeven stop never gaps": ('if gap_ok and through(pos["sl"]):', 'if gap_ok and not pos["tp1_done"] and through(pos["sl"]):'),
 "M12 gap exit charged a second cost": ('net = gross - pos["cost"]', 'net = gross - pos["cost"] * (2.0 if why.endswith("_GAP") else 1.0)'),
 "M13 labels: breakeven never named": ('stop_lbl = "BE" if pos["sl"] == pos["entry"] and pos["tp1_done"] else "SL"', 'stop_lbl = "SL"'),
 "M14 stop checked before targets at the open": ('            if gap_ok and beyond(pos["tp2"]):', '            if gap_ok and through(pos["sl"]):\n                _close(pos, oi, i, idx, stop_lbl + "_GAP", trades); pos = None\n            elif gap_ok and beyond(pos["tp2"]):'),
 "M15 partial at the open sized 100%": ('            elif gap_ok and not pos["tp1_done"] and beyond(pos["tp1"]):\n                pos["legs"].append((0.5, oi))\n                pos["qty"] -= 0.5', '            elif gap_ok and not pos["tp1_done"] and beyond(pos["tp1"]):\n                pos["legs"].append((1.0, oi))\n                pos["qty"] -= 1.0'),
}
res = {}
for name, (a, b) in M.items():
    d = os.path.join(W, "r")
    shutil.rmtree(d, ignore_errors=True)
    for sub in ("quantum", "tests", "audit/tools"):
        shutil.copytree(os.path.join(REPO, sub), os.path.join(d, sub), ignore=shutil.ignore_patterns("__pycache__"))
    p = os.path.join(d, "quantum", "backtest.py"); s = open(p).read()
    assert s.count(a) == 1, name
    open(p, "w").write(s.replace(a, b))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "tests/test_backtest_gaps.py"], cwd=d, capture_output=True, text=True)
    failed = [l.split("::")[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    res[name] = failed
    print(("KILLED  " if failed else "SURVIVED"), name, "->", ", ".join(f[:7] for f in failed) or "-", flush=True)
json.dump(res, open(os.path.join(W, "mutation.json"), "w"), indent=1)
