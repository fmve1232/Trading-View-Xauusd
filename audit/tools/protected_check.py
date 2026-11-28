"""Protected-state check, run before and after every change (operator mandate 28 Nov 2026, Part 1.2). Read-only.

  python audit/tools/protected_check.py [--store <market-data store>] [--json out]

Checks, each PASS or FAIL:
  freeze_key        the key recomputed from this checkout (holdout.freeze_key(config.Config())) equals EXPECTED
  pine_count        artefacts/ holds exactly the seven protected Pine files
  pine_manifest     each of the seven hashes equals its line in audit/MANIFEST.sha256
  pine_prereg       the four hashes of audit/PREREGISTRATION.md section 2 (Master, Treatment, Control, Challenger)
  manifest_all      every file listed in audit/MANIFEST.sha256 has its recorded hash
  store_manifest    (with --store) the store's holdout_manifest.json carries EXPECTED as its freeze key
Exit 1 when any check fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)

EXPECTED = "1f88aad357497da4:4440d52587f5cc6b"
PINE = ("XAUUSD_Quantum_5_0_Diagnostics.pine", "XAUUSD_Quantum_5_0_EdgeCases.pine", "XAUUSD_Quantum_5_0_Master.pine",
        "XAUUSD_Quantum_5_0_Strategy.pine", "XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine",
        "XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine", "XAUUSD_Quantum_5_5_Visuals.pine")


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _manifest(root: str) -> dict:
    out = {}
    with open(os.path.join(root, "audit", "MANIFEST.sha256")) as f:
        for line in f:
            m = re.match(r"^([0-9a-f]{64})\s+\*?(.+)$", line.strip())
            if m:
                out[m.group(2)] = m.group(1)
    return out


def _prereg(root: str) -> dict:
    with open(os.path.join(root, "audit", "PREREGISTRATION.md")) as f:
        text = f.read()
    return {m.group(1): m.group(2) for m in re.finditer(r"^\| `([^`]+\.pine)`[^|]*\| `([0-9a-f]{64})` \|", text, re.MULTILINE)}


def check(root: str = ROOT, store: str | None = None) -> dict:
    from quantum import config, holdout
    res = {}
    key = holdout.freeze_key(config.Config())
    res["freeze_key"] = {"ok": key == EXPECTED, "found": key, "expected": EXPECTED}
    have = sorted(f for f in os.listdir(os.path.join(root, "artefacts")) if f.endswith(".pine"))
    res["pine_count"] = {"ok": have == sorted(PINE), "found": have}
    man = _manifest(root)
    pine = {f: _sha(os.path.join(root, "artefacts", f)) for f in PINE if os.path.exists(os.path.join(root, "artefacts", f))}
    bad = [f for f in PINE if man.get(f"artefacts/{f}") != pine.get(f)]
    res["pine_manifest"] = {"ok": not bad and len(pine) == 7, "mismatch": bad, "sha256": pine}
    pre = _prereg(root)
    bad_pre = [f for f, h in pre.items() if pine.get(f) != h]
    res["pine_prereg"] = {"ok": len(pre) == 4 and not bad_pre, "files": sorted(pre), "mismatch": bad_pre}
    bad_all = [p for p, h in man.items() if not os.path.exists(os.path.join(root, p)) or _sha(os.path.join(root, p)) != h]
    res["manifest_all"] = {"ok": not bad_all and len(man) > 0, "files": len(man), "mismatch": bad_all}
    if store:
        try:
            with open(os.path.join(store, "holdout_manifest.json")) as f:
                sk = json.load(f).get("freeze_key")
        except (OSError, ValueError) as e:
            sk = f"unreadable: {e}"
        res["store_manifest"] = {"ok": sk == EXPECTED, "found": sk}
    return {"verdict": "PASS" if all(v["ok"] for v in res.values()) else "FAIL", "checks": res}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    out = check(ROOT, a.store)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)
    for k, v in out["checks"].items():
        print(f"{'PASS' if v['ok'] else 'FAIL'}  {k}")
    print(out["verdict"])
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
