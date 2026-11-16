"""Deployment smoke test (quantum/smoke.py): the live site must serve this run's files, byte-identical, and fresh data."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from quantum import smoke

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
BASE = "https://example.invalid/site/"


@pytest.fixture
def site(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "index.html").write_text("<title>XAUUSD Quantum</title>")
    (tmp_path / "app.js").write_text("console.log(1)")
    (tmp_path / "data" / "index.json").write_text(json.dumps({"generated_utc": (NOW - timedelta(minutes=3)).isoformat()}))
    (tmp_path / "data" / "15m.json").write_text('{"chart": {"t": [1]}}')
    return tmp_path


def live(site, **override):
    """A fake of the deployed site: the built files unless overridden with (status, body)."""
    def get(url):
        rel = url.split("?")[0][len(BASE):] or "index.html"
        if rel in override:
            return override[rel]
        return 200, (site / rel).read_bytes()
    return get


def test_a_healthy_deploy_has_no_problem_and_checks_every_built_file(site):
    seen = []
    get = live(site)
    assert smoke.check(BASE, str(site), lambda u: (seen.append(u), get(u))[1], NOW, bust="7") == []
    assert [u[len(BASE):] for u in seen] == ["?v=7", "index.html?v=7", "app.js?v=7", "data/15m.json?v=7", "data/index.json?v=7"]
    assert smoke.check(BASE.rstrip("/"), str(site), live(site), NOW) == []          # a URL without the trailing slash


def test_a_stale_or_missing_or_unreachable_file_is_named(site):
    old = json.dumps({"generated_utc": (NOW - timedelta(hours=7)).isoformat()}).encode()
    p = smoke.check(BASE, str(site), live(site, **{"data/index.json": (200, old)}), NOW)
    assert len(p) == 1 and p[0].startswith("data/index.json: the live file differs from this run's")
    p = smoke.check(BASE, str(site), live(site, **{"app.js": (404, b"")}), NOW)
    assert p == ["app.js: HTTP 404"]
    p = smoke.check(BASE, str(site), live(site, **{"data/15m.json": (0, b"timed out")}), NOW)
    assert p == ["data/15m.json: HTTP 0 (timed out)"]
    p = smoke.check(BASE, str(site), live(site, **{"index.html": (200, b"<html>404</html>")}), NOW)
    assert [x.split(":")[0] for x in p] == ["(root URL)", "index.html"]              # the root must serve index.html


def test_old_data_is_a_problem_even_when_the_files_match(site):
    (site / "data" / "index.json").write_text(json.dumps({"generated_utc": (NOW - timedelta(minutes=46)).isoformat()}))
    p = smoke.check(BASE, str(site), live(site), NOW)
    assert len(p) == 1 and "46 min before this check (limit 45)" in p[0]
    (site / "data" / "index.json").write_text("{}")
    assert "cannot read generated_utc" in smoke.check(BASE, str(site), live(site), NOW)[0]
    (site / "data" / "index.json").unlink()
    assert smoke.check(BASE, str(site), live(site), NOW)[0].startswith("the build has no index.html or data/index.json")


def test_main_retries_then_passes_or_fails_the_step(site, monkeypatch, capsys, tmp_path):
    (site / "data" / "index.json").write_text(json.dumps({"generated_utc": datetime.now(timezone.utc).isoformat()}))
    summ = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    calls, waits = {"n": 0}, []
    good = live(site)

    def slow(url):                                   # Pages still serves the previous deployment on the first two attempts
        if url.endswith("-1") or url.endswith("-2"):
            calls["n"] += 1
            return (200, b"previous deployment") if "app.js" in url else good(url)
        return good(url)
    args = ["--url", BASE, "--site", str(site), "--attempts", "4", "--wait", "9"]
    assert smoke.main(args, get=slow, sleep=waits.append) == 0
    assert waits == [9.0, 9.0] and "byte-identical (attempt 3)" in capsys.readouterr().out
    assert smoke.main(args, get=live(site, **{"app.js": (503, b"")}), sleep=waits.append) == 1
    out = capsys.readouterr().out
    assert out.startswith("::error title=deployment smoke test::smoke test FAILED after 4 attempts: app.js: HTTP 503")
    assert len(waits) == 5 and "FAILED after 4 attempts" in summ.read_text()         # no wait after the last attempt


def test_the_workflow_runs_the_smoke_test_right_after_the_deploy_and_does_not_hide_a_failure():
    with open(".github/workflows/quantum-site.yml") as f:
        wf = f.read()
    i, j = wf.index("uses: actions/deploy-pages@v4"), wf.index("python -m quantum.smoke")
    assert i < j and "continue-on-error" not in wf[i:j] and wf[i:j].count("- name:") == 1     # the very next step
    assert 'python -m quantum.smoke --url "${{ steps.deploy.outputs.page_url }}" --site site' in wf
