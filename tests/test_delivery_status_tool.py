"""audit/tools/delivery_status.py (decision B, 2026-11-26): the five statuses recomputed from attempt records alone,
checked against quantum/notify.py's own delivery_status on hand-made records of every delivery path."""
import json
import os
import sys

import pytest

from quantum import notify as N

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import delivery_status as D

NV = "NOT_VERIFIABLE"


def att(attempt, ok, request=True, channel="ntfy", part="1/1", http=None):
    return {"channel": channel, "attempt": attempt, "ok": ok, "request": request, "part": part, "http": http,
            "notif_key": "k", "t_run": 1, "stream": "breakouts"}


CASES = {
    "accepted": ([att(1, True, http=200)], ("YES", "NO", "NO")),
    "failed then the retry accepted": ([att(1, False, http=503), att(2, True, http=200)], ("YES", "YES", "YES")),
    "both attempts refused (the 22 Nov 429)": ([att(1, False, http=429), att(2, False, http=429)], ("NO", "YES", "YES")),
    "cache showed attempt 1 arrived": ([att(1, False), att(2, True, request=False)], ("YES", "YES", "NO")),
    "an earlier run's acceptance": ([att(0, True, request=False)], ("YES", "NO", "NO")),
    "not retryable (401)": ([att(1, False, http=401)], ("NO", "YES", "NO")),
    "no channel configured": ([att(0, False, request=False, channel=None)], ("NOT_CONFIGURED", "YES", "NO")),
    "split: part 1 accepted, part 2 refused twice": (
        [att(1, True, part="1/2"), att(1, False, part="2/2"), att(2, False, part="2/2")], ("PARTLY", "YES", "YES")),
    "ntfy refused, telegram accepted": ([att(1, False, http=503), att(2, False, http=503), att(1, True, channel="telegram")],
                                        ("NO", "YES", "YES")),
}


@pytest.mark.parametrize("name", list(CASES))
def test_the_tool_and_the_system_agree_on_every_delivery_path(name):
    recs, (sent, failed, retried) = CASES[name]
    want = {"SENT_TO_NTFY": sent, "PHONE_DELIVERY": NV, "PHONE_DISPLAY": NV, "SEND_FAILED": failed, "RETRY_ATTEMPTED": retried}
    assert D.status(recs) == want
    assert N.delivery_status(recs) == want
    assert D.NAMES == N.STATUS_NAMES


def test_the_report_groups_attempts_into_messages_and_flags_a_stored_status_that_disagrees(tmp_path):
    a = [dict(r, notif_key="a", t_run=10) for r in CASES["failed then the retry accepted"][0]]
    b = [dict(r, notif_key="b", t_run=20) for r in CASES["both attempts refused (the 22 Nov 429)"][0]]
    c = [dict(att(1, True), notif_key="c", t_run=30, status=dict(N.delivery_status([att(1, True)]), SENT_TO_NTFY="NO"))]
    d = tmp_path / "notifications"
    d.mkdir()
    (d / "2026-11-22.jsonl").write_text("".join(json.dumps(r) + "\n" for r in a + b + c))
    rep = D.report(D.read(str(d)))
    assert (rep["attempt_records"], rep["messages"], rep["messages_with_stored_status"]) == (5, 3, 1)
    assert rep["status_distribution"]["SENT_TO_NTFY"] == {"YES": 2, "NO": 1}
    assert rep["status_distribution"]["PHONE_DELIVERY"] == {NV: 3} and rep["status_distribution"]["PHONE_DISPLAY"] == {NV: 3}
    assert [m["notif_key"] for m in rep["not_fully_accepted"]] == ["b"] and rep["not_fully_accepted"][0]["http_failures"] == [429]
    assert [m["notif_key"] for m in rep["stored_vs_recomputed_disagreements"]] == ["c"]
    assert D.main([str(d)]) == 1                       # a disagreement fails the tool
