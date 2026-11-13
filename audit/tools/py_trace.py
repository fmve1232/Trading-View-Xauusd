"""Read-only static scan of the production Python (quantum/, not quantum/research/): uncalled functions, silent exception
handlers, and the reach of every feature the engine computes (decision, display, or nothing).

  python3 -I audit/tools/py_trace.py <checkout> <out.json>

Static analysis narrows the search; it does not prove a path is live or dead (dynamic access such as F[name] built from a
variable is invisible to it). Every "uncalled" or "never read" result is a candidate to check by hand."""
from __future__ import annotations

import ast
import json
import os
import re
import sys

ROOT, OUT = sys.argv[1], sys.argv[2]
PROD = [os.path.join(ROOT, "quantum", f) for f in sorted(os.listdir(os.path.join(ROOT, "quantum"))) if f.endswith(".py")] + \
       [os.path.join(ROOT, "quantum", "data", f) for f in sorted(os.listdir(os.path.join(ROOT, "quantum", "data"))) if f.endswith(".py")]
OTHER = []
for d in ("tests", "audit/tools", ".github/workflows", "site"):
    for r, _, fs in os.walk(os.path.join(ROOT, d)):
        OTHER += [os.path.join(r, f) for f in fs if f.endswith((".py", ".yml", ".js", ".html"))]
src = {p: open(p, encoding="utf-8").read() for p in PROD}
other = {p: open(p, encoding="utf-8", errors="replace").read() for p in OTHER}
rel = lambda p: os.path.relpath(p, ROOT)


def uses(name, texts):
    rx = re.compile(r"\b" + re.escape(name) + r"\b")
    return sum(len(rx.findall(t)) for t in texts)


# 1. top-level functions never referenced outside their own definition
uncalled, test_only = [], []
for p, s in src.items():
    for node in ast.parse(s).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nm = node.name
            if nm.startswith("__") or nm == "main":
                continue
            in_prod = uses(nm, src.values()) - 1                  # minus its own def line
            in_tests = uses(nm, [t for q, t in other.items() if "/tests/" in q])
            in_tools = uses(nm, [t for q, t in other.items() if "/tests/" not in q])
            if in_prod <= 0:
                (test_only if in_tests else uncalled).append({"file": rel(p), "line": node.lineno, "function": nm,
                                                              "refs_tests": in_tests, "refs_tools_site_workflows": in_tools})

# 2. exception handlers: broad ones, and the subset whose body neither records nor re-raises
broad, silent = 0, []
for p, s in src.items():
    lines = s.splitlines()
    for node in ast.walk(ast.parse(s)):
        if isinstance(node, ast.ExceptHandler):
            t = node.type
            name = (t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else
                    "tuple" if isinstance(t, ast.Tuple) else "bare")
            if name in ("Exception", "BaseException", "bare"):
                broad += 1
                body = node.body
                records = any(isinstance(b, (ast.Raise, ast.Return)) for b in body) or any(
                    isinstance(n, (ast.Call, ast.Assign, ast.AugAssign, ast.Raise)) for b in body for n in ast.walk(b))
                if not records:
                    silent.append({"file": rel(p), "line": node.lineno, "code": lines[node.lineno - 1].strip()[:110],
                                   "body": " / ".join(lines[b.lineno - 1].strip() for b in body)[:110]})

# 3. feature reach: keys written into F in features.py, and where they are read
feat = src[os.path.join(ROOT, "quantum", "features.py")]
keys = set(re.findall(r'F\["([A-Za-z0-9_]+)"\]\s*=', feat)) | set(re.findall(r'F\[f"\{name\}_([a-z0-9]+)"\]', feat))
for m in re.finditer(r"F\.update\(([^)]*)\)", feat, re.S):
    keys |= set(re.findall(r"([A-Za-z0-9_]+)=", m.group(1)))
decision = ("engine.py", "analog.py", "backtest.py", "arm_h2.py", "arm_h3.py", "arm_h4.py", "arm_h5.py", "arm_h6.py", "trade_race.py")
reach = {}
for k in sorted(keys):
    rd = [os.path.basename(p) for p, s in src.items() if not p.endswith("features.py") and re.search(r'["\']' + re.escape(k) + r'["\']', s)]
    rd_feat = len(re.findall(r'F\["' + re.escape(k) + r'"\](?!\s*=[^=])', feat)) + len(re.findall(r"\b" + re.escape(k) + r"\b", feat)) - 1
    reach[k] = {"read_by": rd, "decision": any(r in decision for r in rd), "display": "report.py" in rd or "confirm.py" in rd,
                "used_inside_features": rd_feat > 1}
cls = {"decision": sorted(k for k, v in reach.items() if v["decision"]),
       "display_and_feeds_other_features": sorted(k for k, v in reach.items() if not v["decision"] and v["display"] and v["used_inside_features"]),
       "display_only": sorted(k for k, v in reach.items() if not v["decision"] and v["display"] and not v["used_inside_features"]),
       "internal_only": sorted(k for k, v in reach.items() if not v["decision"] and not v["display"] and v["used_inside_features"]),
       "never_read": sorted(k for k, v in reach.items() if not v["read_by"] and not v["used_inside_features"])}
res = {"files": [rel(p) for p in PROD], "uncalled_functions": uncalled, "test_only_functions": test_only,
       "broad_exception_handlers": broad, "silent_broad_handlers": silent,
       "feature_keys": len(keys), "feature_reach_counts": {k: len(v) for k, v in cls.items()}, "feature_reach": cls}
json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps({k: res[k] for k in ("broad_exception_handlers", "feature_keys", "feature_reach_counts")}, indent=1))
print("uncalled:", [(u["file"], u["function"], u["refs_tools_site_workflows"]) for u in uncalled])
print("test-only:", [(u["file"], u["function"]) for u in test_only])
print("silent broad handlers:", len(silent))
for x in silent:
    print("  ", x["file"], x["line"], "|", x["code"], "->", x["body"])
for k, v in cls.items():
    print(k, len(v), v[:80])
