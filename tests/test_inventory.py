"""Wiring of the production Python (audit/tools/inventory.py): every switch the code reads can be set from the workflow,
and no module-level definition is unused (or used only by tests) without a stated reason."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "audit", "tools"))
import inventory  # noqa: E402


def test_every_switch_the_code_reads_is_passed_by_the_workflow_and_nothing_is_unused():
    r = inventory.build()
    assert r["env_not_passed"] == [], r["env_not_passed"]
    assert r["unreferenced"] == [] and r["tests_only"] == [], (r["unreferenced"], r["tests_only"])
    assert {"ALERT_SWEEPS", "BREAKOUT_TFS", "PLAN", "ACCOUNT_USD", "CONFIRM_MIN_USD"} <= set(r["env_reads"])
    assert {"_env_float", "num", "_num"} <= set(r["env_helpers"])          # reads through helpers are found too


def test_the_reasons_cover_only_definitions_that_exist():
    r = inventory.build()
    defined = {(m["module"], k) for m in r["modules"] for k in m["constants"]}
    import ast
    for rel, name in inventory.REFERENCE:
        src = open(os.path.join(inventory.ROOT, rel)).read()
        names = {n.name for n in ast.parse(src).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        assert name in names or (rel, name) in defined, (rel, name)
