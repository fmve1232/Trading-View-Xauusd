"""Inventory and wiring check of the production Python (quantum/, quantum/data/; research code excluded).

For every production module: its first docstring line, size, internal imports, whether it is a frozen engine source
(holdout.ENGINE_SOURCES), the environment variables it reads, and its module-level constants with their values.

Two checks that the unit tests also enforce (tests/test_inventory.py):
  * switches: every environment variable the production code reads is passed by .github/workflows/quantum-site.yml
    (or is listed in RUNNER_PROVIDED / OTHER_WORKFLOW with the reason), so no documented switch is disconnected;
  * unreferenced: every module-level function, class and UPPER_CASE constant of a production module is referenced
    somewhere outside its own definition (production code, the site, the workflows, audit tools or the scheduler);
    one referenced only by tests is reported apart.

Environment reads are found from the code, not from comments: direct os.environ.get / os.getenv / os.environ[...] calls
with a literal name, and calls with a literal first argument to any helper whose body passes its parameter to
os.environ.get (e.g. notify._env_float, plan_cfg's num, confirm_entry._num).

  python3 audit/tools/inventory.py [--json out.json] [--md out.md]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "quantum-site.yml")
RUNNER_PROVIDED = {"GITHUB_STEP_SUMMARY": "set by GitHub Actions", "GITHUB_SHA": "set by GitHub Actions",
                   "GITHUB_RUN_ID": "set by GitHub Actions"}
OTHER_WORKFLOW = {"DATABENTO_API_KEY": "research-orderflow.yml (quantum/data/sources.py reads it for the B5 study only)"}
# Definitions that production code does not call by design, each with its reason (the check fails on any other).
REFERENCE = {
    ("quantum/contract.py", "price_to_money"): "Python reference of site/costs.js priceToMoney (tests/test_contract.py, tests/costs.test.mjs)",
    ("quantum/contract.py", "money_to_price"): "Python reference of site/costs.js moneyToPrice",
    ("quantum/contract.py", "lots_for_risk"): "Python reference of site/costs.js lotsForRisk (the site's sizing)",
    ("quantum/contract.py", "trade_money"): "Python reference of site/costs.js tradeMoney (the site's money per trade)",
    ("quantum/cost_profiles.py", "round_trip_cost_per_oz"): "Python reference of the profiles' round trip the site computes from cost_profiles.export()",
    ("quantum/cost_profiles.py", "BASES"): "the profile bases the tests validate export() against",
    ("quantum/confirm_panel.py", "verify_events"): "audit check of the confirmation event log's hash chain (tests/test_confirm_panel.py)",
}
SEARCH = ("quantum", "site", "audit/tools", ".github/workflows", "scheduler", "relay")


def production_files() -> list[str]:
    out = []
    for sub in ("quantum", os.path.join("quantum", "data")):
        d = os.path.join(ROOT, sub)
        out += sorted(os.path.join(sub, f) for f in os.listdir(d) if f.endswith(".py") and f != "__init__.py")
    return out


def _is_environ_get(node: ast.AST) -> bool:
    f = node.func if isinstance(node, ast.Call) else None
    if isinstance(f, ast.Attribute) and f.attr == "get" and isinstance(f.value, ast.Attribute) and f.value.attr == "environ":
        return True
    return isinstance(f, ast.Attribute) and f.attr == "getenv" and isinstance(f.value, ast.Name) and f.value.id == "os"


def env_helpers(trees: dict) -> set[str]:
    """Names of functions (any depth) that pass one of their own parameters to os.environ.get / os.getenv."""
    names = set()
    for tree in trees.values():
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {a.arg for a in fn.args.args}
            for c in ast.walk(fn):
                if _is_environ_get(c) and c.args and isinstance(c.args[0], ast.Name) and c.args[0].id in params:
                    names.add(fn.name)
    return names


def env_reads(tree: ast.AST, helpers: set[str]) -> set[str]:
    out = set()
    for c in ast.walk(tree):
        if isinstance(c, ast.Call) and c.args and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str):
            f = c.func
            fname = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if _is_environ_get(c) or fname in helpers:
                out.add(c.args[0].value)
        if isinstance(c, ast.Subscript) and isinstance(c.value, ast.Attribute) and c.value.attr == "environ" and \
                isinstance(c.slice, ast.Constant) and isinstance(c.slice.value, str):
            out.add(c.slice.value)
    return {x for x in out if re.fullmatch(r"[A-Z][A-Z0-9_]*", x)}


def constants(tree: ast.Module, src: str) -> dict:
    out = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for t in targets:
            names = [t] if isinstance(t, ast.Name) else list(t.elts) if isinstance(t, ast.Tuple) else []
            for k, n in enumerate(names):
                if isinstance(n, ast.Name) and re.fullmatch(r"[A-Z][A-Z0-9_]*", n.id) and node.value is not None:
                    v = node.value.elts[k] if isinstance(node.value, ast.Tuple) and len(names) > 1 else node.value
                    try:
                        out[n.id] = ast.literal_eval(v)
                    except (ValueError, SyntaxError, TypeError):
                        seg = ast.get_source_segment(src, v) or ""
                        out[n.id] = "(expression) " + " ".join(seg.split())[:120]
    return out


def definitions(tree: ast.Module, src: str) -> list[str]:
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
    return out + list(constants(tree, src))


def workflow_env() -> set[str]:
    txt = open(WORKFLOW, encoding="utf-8").read()
    return set(re.findall(r"^\s+([A-Z][A-Z0-9_]*):\s*\$\{\{", txt, flags=re.M))


def corpus(exclude_tests: bool) -> dict[str, str]:
    out = {}
    for sub in SEARCH + (() if exclude_tests else ("tests",)):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", "research")]   # research code is not production
            for f in files:
                if f.endswith((".py", ".js", ".yml", ".yaml", ".html", ".toml")):
                    p = os.path.join(root, f)
                    out[os.path.relpath(p, ROOT)] = open(p, encoding="utf-8", errors="replace").read()
    return out


def unreferenced(trees: dict, srcs: dict) -> tuple[list, list]:
    """(never referenced outside its definition, referenced by tests only). Word tokens are counted once per file."""
    word = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    tokens = {p: Counter(word.findall(t)) for p, t in corpus(False).items()}
    none, tests_only = [], []
    for rel, tree in trees.items():
        for name in definitions(tree, srcs[rel]):
            own = tokens.get(rel, Counter())[name]
            other = sum(c[name] for p, c in tokens.items() if p != rel and not p.startswith("tests"))
            if own > 1 or other or (rel, name) in REFERENCE:
                continue
            if any(c[name] for p, c in tokens.items() if p.startswith("tests")):
                tests_only.append((rel, name))
            else:
                none.append((rel, name))
    return none, tests_only


def build() -> dict:
    sys.path.insert(0, ROOT)
    from quantum import holdout
    from quantum.config import DEFAULT
    srcs = {rel: open(os.path.join(ROOT, rel), encoding="utf-8").read() for rel in production_files()}
    trees = {rel: ast.parse(s) for rel, s in srcs.items()}
    helpers = env_helpers(trees)
    mods, reads = [], {}
    for rel, tree in trees.items():
        doc = (ast.get_docstring(tree) or "").strip().splitlines()
        imp = sorted({(n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level >= 1} |
                     {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level >= 1 and not n.module
                      for a in n.names})
        env = sorted(env_reads(tree, helpers))
        for e in env:
            reads.setdefault(e, []).append(rel)
        eng = os.path.relpath(rel, "quantum").replace(os.sep, "/") in holdout.ENGINE_SOURCES
        mods.append({"module": rel, "lines": srcs[rel].count("\n"), "doc": doc[0] if doc else "", "imports": imp,
                     "engine_source": eng, "env": env, "constants": constants(tree, srcs[rel])})
    passed = workflow_env()
    missing = sorted(e for e in reads if e not in passed and e not in RUNNER_PROVIDED and e not in OTHER_WORKFLOW)
    none, tests_only = unreferenced(trees, srcs)
    return {"modules": mods, "env_reads": reads, "env_helpers": sorted(helpers), "workflow_env": sorted(passed),
            "env_not_passed": missing, "passed_not_read": sorted(e for e in passed if e not in reads),
            "unreferenced": none, "tests_only": tests_only, "engine_config": DEFAULT.to_dict(),
            "freeze_key": holdout.freeze_key(DEFAULT), "engine_sources": list(holdout.ENGINE_SOURCES)}


def markdown(r: dict) -> str:
    L = ["# Production Python inventory (generated by audit/tools/inventory.py)", "",
         f"{len(r['modules'])} modules, {sum(m['lines'] for m in r['modules']):,} lines. Engine sources are frozen by the "
         "freeze key; every other module is outside it.", "",
         "| Module | Lines | Engine source | Reads | What it is |", "|---|---:|:---:|---|---|"]
    for m in r["modules"]:
        L.append(f"| `{m['module']}` | {m['lines']} | {'yes' if m['engine_source'] else ''} | "
                 f"{', '.join('`' + e + '`' for e in m['env']) or ''} | {m['doc'].replace('|', '/')} |")
    L += ["", "## Switches", "", f"Read by the code and passed by quantum-site.yml: {len(r['env_reads']) - len(r['env_not_passed'])} "
          f"of {len(r['env_reads'])}. Not passed (disconnected): {', '.join(r['env_not_passed']) or 'none'}.", "",
          "Passed by the workflow but not read by production Python (used by a workflow step itself or by the Actions "
          f"runner): {', '.join(r['passed_not_read']) or 'none'}.", "", "## Unreferenced definitions", "",
          f"Never referenced outside their own definition: {', '.join(f'`{a}:{b}`' for a, b in r['unreferenced']) or 'none'}.", "",
          f"Referenced by tests only: {', '.join(f'`{a}:{b}`' for a, b in r['tests_only']) or 'none'}.", "",
          "## Engine configuration (quantum/config.py; frozen: any change restarts the forward test)", "",
          f"Freeze key `{r['freeze_key']}` over {', '.join(r['engine_sources'])} and these defaults (the Pine input "
          "defaults, never tuned on this price history).", "",
          " · ".join(f"`{k}` {json.dumps(v, default=str)}" for k, v in r["engine_config"].items()), "",
          "## Constants (every module-level UPPER_CASE value, as in the code)", ""]
    for m in r["modules"]:
        if not m["constants"]:
            continue
        L += [f"### `{m['module']}`", ""]
        for k, v in m["constants"].items():
            s = json.dumps(v, default=str, ensure_ascii=False) if not isinstance(v, str) else v
            L.append(f"- `{k}` = {s if len(s) <= 200 else s[:200] + ' …'}")
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    r = build()
    if a.json:
        json.dump(r, open(a.json, "w"), indent=1, default=str, ensure_ascii=False)
    if a.md:
        open(a.md, "w").write(markdown(r))
    print(f"{len(r['modules'])} production modules; switches read {len(r['env_reads'])}, not passed by the workflow: "
          f"{r['env_not_passed'] or 'none'}; unreferenced: {r['unreferenced'] or 'none'}; tests only: {len(r['tests_only'])}")
    return 1 if r["env_not_passed"] or r["unreferenced"] or r["tests_only"] else 0


if __name__ == "__main__":
    sys.exit(main())
