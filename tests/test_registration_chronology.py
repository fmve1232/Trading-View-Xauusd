"""audit/tools/registration_chronology.py on a throwaway git repository with a scripted push history: which push first
brought each commit, which commit started a study's trial lines and its code, and what counts as defining a study."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import registration_chronology as C


def _git(d, *a):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, check=True, env=env).stdout.strip()


def _commit(d, path, text, msg):
    p = os.path.join(d, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)
    _git(d, "add", path)
    _git(d, "commit", "-q", "-m", msg)
    return _git(d, "rev-parse", "HEAD")


def _repo(tmp_path):
    d = str(tmp_path / "r")
    os.makedirs(d)
    _git(d, "init", "-q", "-b", "main")
    a = _commit(d, "research/registrations/X1.json", json.dumps({"id": "X1", "created_utc": "2026-01-01"}), "register X1")
    b = _commit(d, "research/trials.jsonl", json.dumps({"phase": "X1", "part": "development"}) + "\n", "first X1 trial")
    c = _commit(d, "quantum/research/x1.py", 'M = ("X1", "X2")\n', "a mention, not a definition")
    e = _commit(d, "quantum/research/x1b.py", 'REG = "X1"\n', "X1 code")
    return d, a, b, c, e


def test_the_first_push_that_brought_each_commit(tmp_path):
    d, a, b, c, e = _repo(tmp_path)
    acts = [{"ref": "refs/heads/main", "activity_type": "branch_creation", "before": C.ZERO, "after": a, "timestamp": "2026-01-01T10:00:00Z"},
            {"ref": "refs/heads/main", "activity_type": "push", "before": a, "after": e, "timestamp": "2026-01-01T12:00:00Z"},
            {"ref": "refs/heads/market-data", "activity_type": "force_push", "before": a, "after": "f" * 40, "timestamp": "2026-01-01T09:00:00Z"},
            {"ref": "refs/heads/gone", "activity_type": "push", "before": a, "after": "e" * 40, "timestamp": "2026-01-01T11:00:00Z"}]
    found, stats = C.first_push(d, acts, {a, b, c, e})
    assert found[a]["utc"] == "2026-01-01T10:00:00Z"
    assert found[b]["utc"] == found[e]["utc"] == "2026-01-01T12:00:00Z"
    assert stats["skipped_refs"] == 1 and stats["unresolved"] == 1          # the store, and a commit not in the clone


def test_a_study_starts_with_its_first_trial_line_and_its_code_with_a_definition_not_a_mention(tmp_path):
    d, a, b, _mention, e = _repo(tmp_path)
    assert C.study_firsts(d, ["main"]) == {"X1": {b: ""}}
    assert C.code_firsts(d, ["main"], "X1") == {e: ""}                        # c only mentions "X1" in a tuple
    assert list(C.registration_adds(d, ["main"])) == ["X1.json"] and a in C.registration_adds(d, ["main"])["X1.json"]


def test_what_defines_a_study_in_code():
    yes = [("B30", '+REG = "B30"'), ("B24-CONFIRM-FWD", '+ID, FILE = "B24-CONFIRM-FWD", "B24-CONFIRM-FWD.json"'),
           ("B9-GRAB-FWD", '+GRAB_ID = "B9-GRAB-FWD"'), ("B15b-ENGINE-FWD", '+ENG_B_ID, ENG_B_FILE = "B15b-ENGINE-FWD", "x"'),
           ("B30", '+        rec = {"phase": "B30", "partition": "development"}')]
    no = ['+M15 = ("A", "B0", "B15", "B30", "B60")', '+# B30 compares four thresholds', '-REG = "B30"', '+REG = "B300"']
    for sid, line in yes:
        assert C.defines(sid).search(line), line
    for line in no:
        assert not C.defines("B30").search(line), line
