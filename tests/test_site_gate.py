"""The quantum-site gate job: a scheduled (backup) run stands down while the dispatcher is keeping its 15-minute slots.

The step's own shell script is taken from the workflow and run with bash; only `curl` (the GitHub API) is replaced by a
stub that answers with the last dispatched run's start time. Runs 3442 and 3477 (17 Nov) came 10 and 11 minutes after a
dispatched run, passed the former 10-minute rule, and the site was deployed twice within minutes; the two smoke-test
failures of the following 191 runs both followed such a pair."""
import os
import stat
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

WF = ".github/workflows/quantum-site.yml"


def _gate_script() -> str:
    lines = open(WF).read().splitlines()
    i = lines.index("      - id: g")
    j = next(k for k in range(i, len(lines)) if lines[k].strip() == "run: |")
    body = []
    for ln in lines[j + 1:]:
        if ln.strip() and not ln.startswith(" " * 10):
            break
        body.append(ln[10:])
    return "\n".join(body) + "\n"


def _gate(tmp_path, event: str, last_age_sec: float | None, api_fails: bool = False) -> tuple[str, str]:
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    curl = stub / "curl"
    if api_fails:
        curl.write_text("#!/bin/sh\nexit 22\n")
    elif last_age_sec is None:
        curl.write_text('#!/bin/sh\necho \'{"total_count": 0, "workflow_runs": []}\'\n')
    else:
        t = (datetime.now(timezone.utc) - timedelta(seconds=last_age_sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
        curl.write_text(f'#!/bin/sh\necho \'{{"workflow_runs": [{{"created_at": "{t}", "event": "workflow_dispatch"}}]}}\'\n')
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    out, summ = tmp_path / "out", tmp_path / "summary"
    out.write_text("")
    summ.write_text("")
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "EVENT": event, "REPO": "o/r", "GH_TOKEN": "x",
           "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summ)}
    r = subprocess.run(["bash", "-e", "-c", _gate_script()], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return out.read_text().strip(), summ.read_text()


@pytest.mark.parametrize("age, run", [
    (60, "false"),       # the dispatcher ran a minute ago
    (597, "false"),      # under the former 10-minute rule as well
    (630, "false"),      # run 3442: 10 min after a dispatch, the next one due in 5 (ran under the 10-minute rule)
    (680, "false"),      # run 3477: 11 min after a dispatch
    (880, "false"),
    (930, "true"),       # the dispatcher missed its slot: the backup runs
    (1600, "true"),
])
def test_a_scheduled_run_stands_down_while_the_dispatcher_keeps_its_slots(tmp_path, age, run):
    got, summ = _gate(tmp_path, "schedule", age)
    assert got == f"run={run}"
    assert ("stands down" in summ) == (run == "false")


def test_dispatched_runs_always_run_and_a_failing_api_never_blocks_the_backup(tmp_path):
    assert _gate(tmp_path, "workflow_dispatch", 30)[0] == "run=true"
    assert _gate(tmp_path, "schedule", None)[0] == "run=true"                 # no dispatcher configured
    assert _gate(tmp_path, "schedule", None, api_fails=True)[0] == "run=true"  # the API did not answer


def test_the_window_matches_the_dispatchers_period():
    wf = open(WF).read()
    assert '[ "$age" -lt 900 ]' in wf and "-lt 600" not in wf
    assert 'crons = ["1,16,31,46 * * * *"]' in open("scheduler/wrangler.toml").read()     # every 15 minutes
    assert "in the last 15 minutes" in open("scheduler/README.md").read()
    assert "in the last 15 minutes" in open("scheduler/worker.js").read()
