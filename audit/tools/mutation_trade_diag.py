"""Mutation test of the G4 per-trade diagnostics (read-only on the repo).

Usage: python audit/tools/mutation_trade_diag.py <empty scratch dir> [--json out.json]
Each mutant is applied to a COPY of quantum/trade_diag.py in the scratch dir; tests/test_trade_diag.py must fail on it.
A mutant that survives is a rule the tests do not pin down; the run exits 1 if any survives.
"""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
M = {
    "M01 a bar touching stop and target counts as the target": ("kt is not None and (ks is None or kt < ks)", "kt is not None and (ks is None or kt <= ks)"),
    "M02 the stop bar's favourable side counted": ('ends, k_end, upto = "STOP", ks, ks ', 'ends, k_end, upto = "STOP", ks, ks + 1 '),
    "M03 race window not cut at the last target": ('"ALL_TARGETS", k_all, k_all + 1', '"ALL_TARGETS", k_all, len(o)'),
    "M04 the still-forming bar is read": ("(t + 300 <= t_now)", "(t <= t_now)"),
    "M05 append ignores the run time": ("B = bars5(store_dir, now)", "B = bars5(store_dir)"),
    "M06 exit-price cap removed (exit below the fill)": ("ll[-1], hh[-1] = max(ll[-1], xp), e", "ll[-1], hh[-1] = ll[-1], e"),
    "M07 exit-price cap removed (exit above the fill)": ("hh[-1], ll[-1] = min(hh[-1], xp), e", "hh[-1], ll[-1] = hh[-1], e"),
    "M08 next-open race not required to be decided": ('if "UNDECIDED" in (win["ends"], win_n["ends"]):', 'if win["ends"] == "UNDECIDED":'),
    "M09 fill at the signal bar's open": ('t_fill = ts(t["entry_time"]) + sec', 't_fill = ts(t["entry_time"])'),
    "M10 a target gapped at the open ignored": ("(h >= px) | (o >= px) if long", "(h >= px) if long"),
    "M11 a long stop gapped at the open ignored": ("(l <= sl) | (o <= sl) if long", "(l <= sl) if long"),
    "M12 a logged record written again": ("if key in seen:\n            continue", "if False:\n            continue"),
    "M13 the ledger merge duplicates lines": ('fresh = [r for r in rows if r["key"] not in have]', "fresh = rows"),
    "M14 news day taken in UTC, not New York": ("datetime.fromtimestamp(t_fill, NY).date()", "datetime.fromtimestamp(t_fill, timezone.utc).date()"),
    "M15 a record written before the exit bar is stored": ("if t_exit_bar + sec > t_last:", "if t_exit_bar > t_last:"),
    "M16 next-open entry from the engine's fill": ("o0 = float(o[0])", "o0 = e"),
    "M17 session-close gap measured from the signal open": ('"first_bar_gap_min": round((int(T[j0]) - t_fill) / 60.0, 1)', '"first_bar_gap_min": round((int(T[j0]) - t_fill + sec) / 60.0, 1)'),
    "M18 an undecided race written before the horizon": ('ends, k_end, upto = ("HORIZON" if horizon_over else "UNDECIDED"), len(o) - 1, len(o)', 'ends, k_end, upto = "HORIZON", len(o) - 1, len(o)'),
    "M19 one malformed trade stops the run": ("except (KeyError, TypeError, ValueError) as e:", "except ZeroDivisionError as e:"),
}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    w = argv[0]
    out = argv[argv.index("--json") + 1] if "--json" in argv else os.path.join(w, "mutation.json")
    res = {}
    for name, (a, b) in M.items():
        d = os.path.join(w, "r")
        shutil.rmtree(d, ignore_errors=True)
        for sub in ("quantum", "tests", "audit/tools"):
            shutil.copytree(os.path.join(REPO, sub), os.path.join(d, sub), ignore=shutil.ignore_patterns("__pycache__"))
        p = os.path.join(d, "quantum", "trade_diag.py")
        with open(p) as f:
            s = f.read()
        assert s.count(a) == 1, name
        with open(p, "w") as f:
            f.write(s.replace(a, b))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-p", "no:cacheprovider",
                            "tests/test_trade_diag.py"], cwd=d, capture_output=True, text=True, check=False)
        failed = [x.split("::")[1].split(" ")[0] for x in r.stdout.splitlines() if x.startswith("FAILED")]
        res[name] = failed
        print(("KILLED  " if failed else "SURVIVED"), name, "->", len(failed), "test(s) failed", flush=True)
    shutil.rmtree(os.path.join(w, "r"), ignore_errors=True)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    survived = [k for k, v in res.items() if not v]
    print(f"{len(res) - len(survived)} of {len(res)} killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
