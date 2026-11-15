"""IA-19 / IA-21 (audit 2026-11-14). The pipeline exits 0 when any timeframe published, so a failed timeframe showed only
inside index.json; a non-fatal step now turns every such problem into an Actions warning. Production installed unpinned
dependencies; it and the PR checks now install requirements.lock (exact versions, equal to what production ran).
Plain-text workflow checks: PyYAML is not a dependency of the production test gate."""
import os
import re

from packaging.requirements import Requirement

from quantum import holdout, run_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_problem_is_reported():
    ok = {"errors": {}, "timeframes": {tf: {} for tf in ("15m", "30m", "1h", "4h", "5m")}, "alerts": {}}
    assert run_check.problems(ok, ["15m", "30m", "1h", "4h", "5m"]) == []
    part = {"errors": {"4h": "ValueError: boom", "download": "FetchError: twelvedata 429"},
            "timeframes": {"15m": {}, "1h": {}}, "alerts": {}}
    assert run_check.problems(part, ["15m", "30m", "1h", "4h"]) == [
        "4h: ValueError: boom", "download: FetchError: twelvedata 429", "30m: no payload this run"]
    assert run_check.problems({"errors": {}, "timeframes": {"15m": {}}}, ["15m"]) == ["alerts: the notifier did not run"]
    assert run_check.problems(None, ["15m"]) == ["index.json missing or unreadable: the pipeline published nothing"]


def test_the_cli_warns_and_never_fails(tmp_path, capsys, monkeypatch):
    idx = tmp_path / "index.json"
    idx.write_text('{"errors": {"30m": "KeyError: x\\nline two :: 50%"}, "timeframes": {"15m": {}}, "alerts": {}}')
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert run_check.main(["--index", str(idx), "--tfs", "15m,30m"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "::warning title=pipeline partial failure::30m: KeyError: x line two : : 50%25"   # one line, escaped
    assert out[-1] == "run check: 1 problem(s)" and "30m: KeyError" in summary.read_text()
    assert run_check.main(["--index", str(tmp_path / "missing.json")]) == 0                      # still exit 0
    assert "index.json missing" in capsys.readouterr().out


def _steps(name):
    with open(os.path.join(ROOT, ".github", "workflows", name)) as f:
        return ["      - " + b for b in re.split(r"\n      - ", f.read())[1:]]


def test_the_check_runs_right_after_the_pipeline_and_is_non_fatal():
    steps = _steps("quantum-site.yml")
    ip = next(i for i, b in enumerate(steps) if b.startswith("      - name: Run pipeline"))
    c = steps[ip + 1]
    assert c.startswith("      - name: Pipeline completeness") and "continue-on-error: true" in c and "always()" in c
    assert "python -m quantum.run_check --index site/data/index.json --tfs 15m,30m,1h,4h,5m" in c
    assert "--tfs 15m,30m,1h,4h,5m" in steps[ip]                       # the same timeframes the pipeline builds
    assert "run_check.py" not in holdout.ENGINE_SOURCES


def test_production_and_pr_checks_install_the_lock():
    for wf in ("quantum-site.yml", "pr-checks.yml"):
        code = "\n".join(_steps(wf))
        assert "pip install -r requirements.lock" in code and "pip install -r requirements.txt" not in code, wf


def test_the_lock_pins_every_requirement_exactly():
    pins = {}
    with open(os.path.join(ROOT, "requirements.lock")) as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            m = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([0-9][A-Za-z0-9.]*)", ln)
            assert m, ln                                               # name==version, nothing looser
            pins[m.group(1).lower()] = m.group(2)
    with open(os.path.join(ROOT, "requirements.txt")) as f:
        reqs = [Requirement(x) for x in f.read().split("\n") if x.strip() and not x.startswith("#")]
    for r in reqs:
        assert r.name.lower() in pins and r.specifier.contains(pins[r.name.lower()]), r
