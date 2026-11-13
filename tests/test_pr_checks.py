"""The pull-request checks workflow stays read-only, secret-free and deployment-free (operator approval 2026-11-13).

Plain-text checks on .github/workflows/pr-checks.yml (no YAML library: requirements.txt has none)."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "..", ".github", "workflows", "pr-checks.yml")


def _wf():
    with open(WF, encoding="utf-8") as f:
        return f.read()


def _code(text):
    """The workflow without its comment lines, so an explanatory comment cannot satisfy or break a check."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def test_triggers_are_pull_request_and_manual_only():
    on = re.search(r"^on:\n((?:[ \t]+.*\n|\n)+?)^\S", _code(_wf()) + "\nEND", re.M).group(1)
    keys = {m.group(1) for m in re.finditer(r"^  ([a-z_]+):", on, re.M)}
    assert keys == {"pull_request", "workflow_dispatch"}
    assert "pull_request_target" not in _code(_wf())   # a PR's code must never run with the base repo's privileges


def test_permissions_are_contents_read_only():
    code = _code(_wf())
    perms = re.findall(r"^\s*permissions:\s*\n((?:\s{2,}[a-z-]+:\s*\S+\n)+)", code, re.M)
    assert perms, "an explicit permissions block is required (the default token could be read-write)"
    for block in perms:
        scopes = dict(re.findall(r"([a-z-]+):\s*(\S+)", block))
        assert scopes == {"contents": "read"}, scopes
    assert not re.search(r"^\s*[a-z-]+:\s*write(-all)?\s*$", code, re.M)   # no scope anywhere is granted write
    assert "write-all" not in code


def test_no_secrets_and_no_credentials_kept():
    code = _code(_wf())
    assert "secrets." not in code
    assert "GITHUB_TOKEN" not in code and "github.token" not in code
    assert code.count("persist-credentials: false") == code.count("actions/checkout@")


def test_no_deployment_upload_push_or_notification():
    code = _code(_wf())
    for banned in ("deploy-pages", "upload-pages-artifact", "configure-pages", "upload-artifact", "git push",
                   "ntfy", "wrangler", "curl ", "environment:"):
        assert banned not in code, banned


def test_runs_the_production_gate_suite_and_the_reference_checks():
    code = _code(_wf())
    assert "pip install -r requirements.txt" in code            # the production gate's dependency set, nothing more
    assert "python -m pytest -q tests" in code                  # the same command as quantum-site.yml's gate
    assert "sha256sum -c audit/MANIFEST.sha256" in code
    assert re.search(r"for t in precheck pinelimits; do[^\n]*\n[^\n]*python audit/tools/\$t\.py artefacts/\*\.pine", code)
    for tool in ("undeclared", "order", "deadcode", "diag_parity"):
        assert f"python audit/tools/{tool}.py" in code, tool


def test_zero_exit_checkers_are_failed_on_their_counts():
    """undeclared.py, order.py and deadcode.py print findings but always exit 0: the workflow must grep their counts."""
    code = _code(_wf())
    for pattern in (r"\[1-9\]\[0-9\]\* unresolved", r"\[1-9\]\[0-9\]\* order violation", r"\[1-9\]\[0-9\]\* dead,"):
        assert re.search(pattern, code), pattern
    rx = re.compile(r": [1-9][0-9]* unresolved|: [1-9][0-9]* order violation|: [1-9][0-9]* dead,")
    assert rx.search("X.pine: 2 unresolved") and rx.search("X.pine: 10 order violation(s)") and rx.search("X.pine: 1 dead, 0")
    assert not rx.search("X.pine: 0 unresolved") and not rx.search("X.pine: 0 order violation(s)")
    assert not rx.search("X.pine: 0 dead, 0 retained (operator instruction), 12 structural")


def test_production_gate_is_untouched():
    """This workflow adds checks before a merge; it does not replace the gate in quantum-site.yml."""
    with open(os.path.join(HERE, "..", ".github", "workflows", "quantum-site.yml"), encoding="utf-8") as f:
        site = f.read()
    assert "run: python -m pytest -q tests" in site
