"""Outage notice: the workflow condition (pinned to GitHub's own evaluation) and quantum/outage_notice.py.

The condition tests use a small evaluator of GitHub's expression rules. It is not trusted on its own: the first
test makes it reproduce every result GitHub itself produced in probe run 43172558297 (10 expressions x 10 failure
cases, tests/fixtures/outage_condition_probe.json). The workflow's condition must then be exactly the probed text,
and give the expected notice in every case.
"""
from __future__ import annotations

import ast
import json
import math
import os
import re
import urllib.error

import pytest

from quantum import outage_notice as on

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "quantum-site.yml")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "outage_condition_probe.json")

# What the operator asked for (2026-11-12): a notice when the alerts may be affected, none for Pages-only failures.
EXPECTED = {
    "ok": False,         # nothing failed
    "tests": True,       # test gate failed: no pipeline, no alerts (the 10 Nov outage)
    "loadstore": True,   # the store could not be loaded: no pipeline
    "pipeline": True,    # the pipeline (which sends the alerts) failed
    "savestore": True,   # alerts sent, their state not saved: they may be shown again
    "ledger": False,     # forward-ledger bookkeeping only: alerts unaffected
    "events": False,     # a continue-on-error display step: the run still succeeds
    "upload": False,     # Pages artifact upload only (run 3078)
    "deploy": False,     # Pages deploy only (runs 3038, 3094)
    "timeout": True,     # the job timed out in the pipeline: a hung run must not stay silent
}


# ----------------------------------------------------------------------------------------------------------------
# A minimal evaluator of GitHub Actions expressions (the subset the condition uses), calibrated below.
# ----------------------------------------------------------------------------------------------------------------
_TOK = re.compile(r"\s*(?:(\|\||&&|==|!=|!|\(|\)|,|\.)|('(?:[^']|'')*')|([A-Za-z_][A-Za-z0-9_-]*)|(\d+(?:\.\d+)?))")


def _tokens(s):
    pos, out = 0, []
    s = s.strip()
    while pos < len(s):
        m = _TOK.match(s, pos)
        if not m or m.end() == pos:
            raise ValueError(f"cannot parse at {s[pos:pos + 20]!r}")
        op, st, name, num = m.groups()
        out.append(("op", op) if op else ("str", st[1:-1].replace("''", "'")) if st else
                   ("name", name) if name else ("num", float(num)))
        pos = m.end()
    return out


def _num(v):
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        if v.strip() == "":
            return 0.0
        try:
            return float(v)
        except ValueError:
            return math.nan
    return math.nan


def _eq(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.casefold() == b.casefold()
    if type(a) is type(b) and not isinstance(a, (int, float)):
        return a == b
    x, y = _num(a), _num(b)
    return (not math.isnan(x)) and (not math.isnan(y)) and x == y


def _truthy(v):
    return not (v is None or v is False or v == "" or (isinstance(v, (int, float)) and not isinstance(v, bool)
                                                       and (v == 0 or math.isnan(v))))


def _str(v):
    return "" if v is None else ("true" if v is True else "false" if v is False else
                                 (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)))


def gh_eval(expr: str, ctx: dict):
    toks = _tokens(expr)
    i = 0

    def peek():
        return toks[i] if i < len(toks) else (None, None)

    def take(kind=None, val=None):
        nonlocal i
        t = peek()
        if (kind and t[0] != kind) or (val and t[1] != val):
            raise ValueError(f"expected {kind} {val}, got {t}")
        i += 1
        return t

    def p_or():
        v = p_and()
        while peek() == ("op", "||"):
            take()
            r = p_and()
            v = v if _truthy(v) else r
        return v

    def p_and():
        v = p_cmp()
        while peek() == ("op", "&&"):
            take()
            r = p_cmp()
            v = r if _truthy(v) else v
        return v

    def p_cmp():
        v = p_un()
        while peek() in (("op", "=="), ("op", "!=")):
            op = take()[1]
            r = p_un()
            v = _eq(v, r) if op == "==" else not _eq(v, r)
        return v

    def p_un():
        if peek() == ("op", "!"):
            take()
            return not _truthy(p_un())
        return p_prim()

    def p_prim():
        k, v = peek()
        if (k, v) == ("op", "("):
            take()
            r = p_or()
            take("op", ")")
            return r
        if k == "str":
            take()
            return v
        if k == "num":
            take()
            return v
        if k == "name":
            take()
            if v in ("true", "false", "null"):
                return {"true": True, "false": False, "null": None}[v]
            if peek() == ("op", "("):
                take()
                args = []
                while peek() != ("op", ")"):
                    args.append(p_or())
                    if peek() == ("op", ","):
                        take()
                take("op", ")")
                return _call(v, args)
            node = ctx.get(v)
            while peek() == ("op", "."):
                take()
                key = take("name")[1]
                node = node.get(key) if isinstance(node, dict) else None
            return node
        raise ValueError(f"unexpected {k} {v}")

    def _call(name, args):
        if name == "failure":
            return bool(ctx["_failure"])
        if name == "cancelled":
            return bool(ctx["_cancelled"])
        if name == "always":
            return True
        if name == "success":
            return not ctx["_failure"] and not ctx["_cancelled"]
        if name == "format":
            fmt, rest = args[0], args[1:]
            return re.sub(r"\{(\d+)\}", lambda m: _str(rest[int(m.group(1))]), fmt)
        raise ValueError(f"function {name} not modelled")

    out = p_or()
    if i != len(toks):
        raise ValueError(f"trailing tokens {toks[i:]}")
    return out


def _ctx(case: dict, vars_: dict | None = None) -> dict:
    return {"_failure": case["failure"], "_cancelled": case["cancelled"], "vars": dict(vars_ or {}),
            "steps": {k: {"outcome": v} for k, v in case["steps"].items()}}


def _fixture():
    with open(FIXTURE) as f:
        return json.load(f)


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def _notice_step() -> list[str]:
    lines = open(WORKFLOW).read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("- name: Outage notice"))
    ind = len(lines[start]) - len(lines[start].lstrip())
    end = next((j for j in range(start + 1, len(lines)) if lines[j].strip().startswith("- ")
                and len(lines[j]) - len(lines[j].lstrip()) == ind), len(lines))
    return lines[start:end]


def _notice_condition() -> str:
    step = _notice_step()
    k = next(i for i, ln in enumerate(step) if ln.strip().startswith("if:"))
    head = step[k].split("if:", 1)[1].strip()
    if head not in (">-", ">", "|", "|-"):
        return head
    ind = len(step[k]) - len(step[k].lstrip())
    body = []
    for ln in step[k + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= ind:
            break
        body.append(ln.strip())
    return " ".join(x for x in body if x)


# ----------------------------------------------------------------------------------------------------------------
# The workflow condition
# ----------------------------------------------------------------------------------------------------------------
def test_the_evaluator_reproduces_every_result_github_produced():
    fx = _fixture()
    assert len(fx["cases"]) == 10 and len(fx["expressions"]) == 10
    for cname, case in fx["cases"].items():
        for ename, expr in fx["expressions"].items():
            got = _truthy(gh_eval(expr, _ctx(case, fx["vars"])))
            assert got == case["github"][ename], (cname, ename)


def test_the_deployed_condition_never_ran_because_an_unset_variable_is_null():
    fx = _fixture()
    assert not any(c["github"]["DEPLOYED"] for c in fx["cases"].values())
    assert gh_eval("vars.OUTAGE_NOTICE != '0'", {"vars": {}}) is False          # null == '0' after coercion
    assert gh_eval("format('x{0}', vars.OUTAGE_NOTICE) != 'x0'", {"vars": {}}) is True


def test_the_workflow_condition_is_exactly_the_one_github_evaluated():
    assert _norm(_notice_condition()) == _norm(_fixture()["expressions"]["REAL"])


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_workflow_condition_sends_only_when_the_alerts_may_be_affected(case):
    fx = _fixture()
    c = fx["cases"][case]
    cond = _notice_condition()
    assert _truthy(gh_eval(cond, _ctx(c))) is EXPECTED[case]                   # variable unset (production today)
    assert _truthy(gh_eval(cond, _ctx(c, {"OUTAGE_NOTICE": "1"}))) is EXPECTED[case]
    assert _truthy(gh_eval(cond, _ctx(c, {"OUTAGE_NOTICE": "0"}))) is False    # the off switch
    assert c["github"]["REAL"] is EXPECTED[case]                                # and GitHub agreed


def test_every_probed_mutant_of_the_condition_is_caught():
    fx = _fixture()
    real = {c: v["github"]["REAL"] for c, v in fx["cases"].items()}
    for m in ("DEPLOYED", "PRA-FIRST", "M1-NO-SAVESTORE", "M2-AND", "M3-NO-OUTCOME", "M4-NULL-BUG", "M5-EQ"):
        assert any(v["github"][m] != real[c] for c, v in fx["cases"].items()), m


def test_the_step_ids_and_inputs_the_condition_reads_exist():
    text = open(WORKFLOW).read()
    assert re.search(r"- name: Run pipeline\n\s+id: pipeline\n", text)
    assert re.search(r"- name: Save the market-data store[^\n]*\n\s+id: savestore\n", text)
    step = "\n".join(_notice_step())
    assert "PIPELINE: ${{ steps.pipeline.outcome }}" in step
    assert "SAVESTORE: ${{ steps.savestore.outcome }}" in step
    assert "NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}" in step
    assert "python3 quantum/outage_notice.py" in step
    assert "continue-on-error: true" in step
    lines = text.splitlines()
    assert lines.index(_notice_step()[0]) > max(i for i, ln in enumerate(lines) if "deploy-pages" in ln)   # the last step


# ----------------------------------------------------------------------------------------------------------------
# quantum/outage_notice.py
# ----------------------------------------------------------------------------------------------------------------
OUTCOMES = ("success", "failure", "cancelled", "skipped", "")


@pytest.mark.parametrize("p", OUTCOMES)
@pytest.mark.parametrize("s", OUTCOMES)
def test_kind_covers_every_outcome_pair(p, s):
    want = "down" if p != "success" else ("state" if s != "success" else None)
    assert on.kind(p, s) == want


class FakeNtfy:
    """Records posts; answers polls from what was posted (the role ntfy's cache plays)."""

    def __init__(self, status=200, poll_error=None, post_error=None, extra=()):
        self.sent, self.polls, self.status = [], [], status
        self.poll_error, self.post_error, self.extra = poll_error, post_error, list(extra)

    def poll(self, topic, window_min):
        self.polls.append((topic, window_min))
        if self.poll_error:
            raise self.poll_error
        rows = [{"event": "open"}] + self.extra + [
            {"event": "message", "time": t, "tags": ["warning", on.OUTAGE_TAG], "message": b} for t, b in self.sent]
        return "\n".join(json.dumps(r) for r in rows) + "\nnot json\n"

    def post(self, topic, body):
        if self.post_error:
            raise self.post_error
        self.sent.append((self.now, body))
        return self.status

    def run(self, now, pipeline="failure", savestore="success", topic="t-secret"):
        self.now = now
        return on.run({"PIPELINE": pipeline, "SAVESTORE": savestore, "NTFY_TOPIC": topic}, now=now,
                      poll=self.poll, post=self.post)


T0 = 1_794_312_960          # 2026-11-10 12:16 UTC, the first failed run of the 10 Nov outage


def test_unaffected_alerts_send_nothing_and_do_not_even_poll():
    f = FakeNtfy()
    r = f.run(T0, pipeline="success", savestore="success")
    assert r["kind"] is None and not r["sent"] and f.sent == [] and f.polls == []


def test_no_topic_sends_nothing():
    f = FakeNtfy()
    r = f.run(T0, topic="")
    assert not r["sent"] and f.sent == [] and f.polls == []


def test_down_and_state_messages_are_distinct_and_timed():
    f = FakeNtfy()
    f.run(T0, pipeline="skipped", savestore="skipped")
    g = FakeNtfy()
    g.run(T0, pipeline="success", savestore="failure")
    down, state = f.sent[0][1], g.sent[0][1]
    assert down.startswith("XAUUSD SITE DOWN: the site run of 12:16 UTC failed")
    assert "re-checked against the live price or marked NOT ACTIONABLE" in down
    assert state.startswith("XAUUSD ALERT STATE NOT SAVED: the site run of 12:16 UTC sent its alerts")
    assert "Do not open a second trade for the same signal" in state


def test_the_10_nov_outage_gets_one_notice_and_a_reminder_every_three_hours():
    f = FakeNtfy()
    for k in range(37):                                           # 12:16 ... 21:16, every 15 min
        f.run(T0 + k * 900, pipeline="skipped", savestore="skipped")
    hours = [(t - T0) / 3600 for t, _ in f.sent]
    assert hours == [0.0, 3.0, 6.0, 9.0]


def test_a_pages_only_failure_never_blocks_a_later_notice():
    """The first PR-A version de-duplicated on ANY failed run in 60 min, so a Pages-only failure (no notice by
    design) silenced a pipeline failure 15 minutes later. De-duplication now reads delivered notices only."""
    f = FakeNtfy()
    assert f.run(T0, pipeline="success", savestore="success")["sent"] is False     # 3094-type run
    r = f.run(T0 + 900, pipeline="failure", savestore="success")
    assert r["sent"] is True and len(f.sent) == 1


def test_normal_alerts_in_the_topic_do_not_count_as_a_notice():
    alert = {"event": "message", "time": T0 - 60, "tags": [], "message": "XAUUSD 15m SELL ..."}
    tagged_other = {"event": "message", "time": T0 - 60, "tags": ["warning"], "message": "x"}
    f = FakeNtfy(extra=[alert, tagged_other])
    assert f.run(T0)["sent"] is True


def test_the_reminder_window_boundary():
    f = FakeNtfy()
    f.run(T0)
    assert f.run(T0 + on.REPEAT_MIN * 60 - 1)["sent"] is False
    assert f.run(T0 + on.REPEAT_MIN * 60)["sent"] is True


def test_fail_open_when_ntfys_record_cannot_be_read():
    f = FakeNtfy(poll_error=urllib.error.URLError("unreachable"))
    r = f.run(T0)
    assert r["sent"] is True and "unavailable" in r["dedupe"]


def test_a_refused_send_is_reported_not_raised_and_never_counted():
    f = FakeNtfy(status=429)
    r = f.run(T0)
    assert r["http"] == 429 and r["sent"] is False and r["why"] == "send failed"
    err = urllib.error.HTTPError("u", 500, "x", {}, None)
    g = FakeNtfy(post_error=err)
    r = g.run(T0)
    assert r["http"] == 500 and r["sent"] is False


def test_the_topic_never_appears_in_the_output(capsys, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "t-very-secret-topic")
    monkeypatch.setenv("PIPELINE", "failure")
    monkeypatch.setenv("SAVESTORE", "success")
    monkeypatch.setattr(on, "_poll", lambda topic, w: "")
    monkeypatch.setattr(on, "_post", lambda topic, body: 200)
    assert on.main() == 0
    out = capsys.readouterr().out
    assert "t-very-secret-topic" not in out and '"sent": true' in out


def test_http_requests_carry_the_tag_and_quote_the_topic(monkeypatch):
    seen = []

    class R:
        status = 200

        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        return R()

    monkeypatch.setattr(on.urllib.request, "urlopen", fake_urlopen)
    on._poll("a/b c", 180)
    on._post("a/b c", "hello")
    assert seen[0] == "https://ntfy.sh/a%2Fb%20c/json?poll=1&since=180m"
    req = seen[1]
    assert req.full_url == "https://ntfy.sh/a%2Fb%20c" and req.get_method() == "POST" and req.data == b"hello"
    assert on.OUTAGE_TAG in req.get_header("Tags").split(",") and req.get_header("Title") == on.TITLE


def test_the_module_is_stdlib_only_so_it_runs_when_pip_install_failed():
    tree = ast.parse(open(on.__file__).read())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"__future__", "json", "os", "sys", "time", "urllib"}, mods


def test_constants_are_the_reviewed_ones():
    assert on.REPEAT_MIN == 180 and on.OUTAGE_TAG == "xau-outage" and on.NTFY == "https://ntfy.sh"
