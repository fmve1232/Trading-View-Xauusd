"""Mutation test of quantum/manual_ledger.py against tests/test_manual_ledger.py, on a scratch copy (the repository is
not touched). Each mutant breaks one ledger rule (chain, one trade at a time, no inferred execution, complete plans,
expiry, stop-first, statistics, phone text, privacy of the snapshot, the server clock); it is killed when the tests fail.

  python audit/tools/ledger_mutation.py <repo> <scratch dir> <out json>
"""
import json
import os
import shutil
import subprocess
import sys

repo, work, out = sys.argv[1:4]
MUTANTS = [
    ("hash not checked", 'if r.get("hash") != _digest(r):', "if False:"),
    ("prev not checked", 'if r.get("prev") != prev:', "if False:"),
    ("append ignores a broken chain", "        if broken:\n            raise LedgerError", "        if False:\n            raise LedgerError"),
    ("second open trade allowed", "            if slot is not None:\n                bad(r, f\"{slot} is still open", "            if False:\n                bad(r, f\"{slot} is still open"),
    ("blocked signals not marked", 'data["blocked_by"] = state["slot"]', "pass"),
    ("execution inferred from any source", 'if src not in CONFIRMERS:\n                bad(r, f"an execution', 'if False:\n                bad(r, f"an execution'),
    ("closure inferred from any source", 'if src not in CONFIRMERS:\n                bad(r, f"a closure', 'if False:\n                bad(r, f"a closure'),
    ("evidence not required", 'EXEC_REQUIRED = ("fill", "t_fill", "lot", "sl_actual", "evidence")', 'EXEC_REQUIRED = ("fill", "t_fill", "lot", "sl_actual")'),
    ("incomplete plans accepted", 'miss = [k for k in PLAN_REQUIRED if p.get(k) in (None, "")]', "miss = []"),
    ("level order not checked", 'bad.append("levels out of order', 'pass  # bad.append("levels out of order'),
    ("early expiry allowed", 'if utc(r["t"]) < utc(s["plan"]["expiry_utc"]):', "if False:"),
    ("target counted on the stop bar", "        if adv >= risk:\n            t_sl, mae = t + bar_sec, max(mae, adv)\n            break\n",
     "        if adv >= risk and False:\n            pass\n"),
    ("profit factor inverted", 'round(sum(wins) / -sum(losses), 3)', 'round(-sum(losses) / sum(wins), 3)'),
    ("losing streak never resets", "run = run + 1 if x < -0.005 else 0", "run = run + 1 if x < -0.005 else run"),
    ("accepted population = executed", '"3_accepted": [s for s in sigs if s["accepted"]]', '"3_accepted": [s for s in sigs if s["execution"]]'),
    ("expired signal still actionable on the phone", 'if why is None and utc(now) >= utc(p["expiry_utc"]):', "if False:"),
    ("entry deviation ignores the LATE rule", "round(late_frac * stop, 2) if _num(late_frac) else None", "round(stop, 2)"),
    ("snapshot leaks the fill", '"open": {"signal_id": open_["signal_id"], "side": open_["plan"]["direction"]}',
     '"open": {"signal_id": open_["signal_id"], "side": open_["plan"]["direction"], "fill": open_["execution"]["fill"]}'),
    ("server clock assumed to be UTC", '"t_open": t_srv - server_utc_offset_h * 3600 if server_utc_offset_h is not None else None', '"t_open": t_srv'),
    ("corrections overwrite without trace", 'ts["corrections"].append(', "(lambda *a, **k: None)("),
    ("duplicate C1 import allowed", 'if key in have or x.get("status") == "PENDING":', 'if x.get("status") == "PENDING":'),
    ("PKT shown as UTC", 'PKT = ZoneInfo("Asia/Karachi")', 'PKT = ZoneInfo("UTC")'),
]
MARK = ".ledger_mutation_scratch"
rp, wp = os.path.realpath(repo), os.path.realpath(work)
if wp == rp or rp.startswith(wp + os.sep):
    sys.exit("the scratch directory must not be the repository or contain it")
if os.path.exists(wp) and not os.path.exists(os.path.join(wp, MARK)):
    sys.exit(f"{wp} exists and was not made by this tool ({MARK} missing): give a new or empty path")


def fresh():
    """Recreate the scratch copy; only a directory this tool marked is ever removed."""
    if os.path.exists(os.path.join(wp, MARK)):
        shutil.rmtree(wp)
    os.makedirs(os.path.join(wp, "tests"))
    with open(os.path.join(wp, MARK), "w") as fh:
        fh.write("scratch copy for audit/tools/ledger_mutation.py\n")
    shutil.copytree(os.path.join(rp, "quantum"), os.path.join(wp, "quantum"), ignore=shutil.ignore_patterns("__pycache__", "research"))
    shutil.copy(os.path.join(rp, "tests", "test_manual_ledger.py"), os.path.join(wp, "tests"))


results = []
for name, a, b in MUTANTS:
    fresh()
    p = os.path.join(wp, "quantum", "manual_ledger.py")
    with open(p, encoding="utf-8") as fh:
        src = fh.read()
    n = src.count(a)
    if n != 1:
        results.append({"mutant": name, "applied": False, "count": n})
        continue
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(src.replace(a, b))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests/test_manual_ledger.py"],
                       cwd=wp, capture_output=True, text=True, timeout=300, check=False)
    results.append({"mutant": name, "applied": True, "killed": r.returncode != 0})
killed = sum(1 for x in results if x.get("killed"))
applied = sum(1 for x in results if x["applied"])
with open(out, "w") as fh:
    json.dump({"tool": "audit/tools/ledger_mutation.py (scratch copy; repository untouched)", "applied": applied, "killed": killed,
               "results": results}, fh, indent=1)
print(f"{killed} of {applied} applied mutants killed; not applied: {[x['mutant'] for x in results if not x['applied']]}")
print("survivors:", [x["mutant"] for x in results if x["applied"] and not x["killed"]])
