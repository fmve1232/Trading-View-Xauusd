"""IA-01 (audit 2026-11-14): the RECORD line under each 15m engine signal is computed, not fixed text. History is counted
once per trade idea, as the research corrected it (B10: 12 of 23 in 2020-22; B13: 11 of 24 in 2023-24, 15m-4h pooled),
and the live part is the registered engine test: B15-ENGINE-FWD until Amendment F, B15b-ENGINE-FWD since, with B15's final
record shown apart once it has ended (never pooled); every rate carries its Wilson 95% interval. Expected values are
computed by hand (Wilson, z = 1.96), not with the module's own helper."""
import json
import os

import pytest

from quantum import notify as N
from tests.test_alert_sixty import T, _pay, _sig


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("ALERT_MODE", "PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "PLAN_TP2_USD"):
        monkeypatch.delenv(k, raising=False)


def test_history_is_counted_per_idea_with_its_interval_and_no_retracted_figure():
    line = N.signal_record_line(None)
    assert line.startswith("RECORD of engine signals, one count per trade idea, TP1 +$13 before SL -$13 "
                           "(no edge 50%, break-even 51%)")
    assert "2020-22 15m 12 of 23 = 52% (95% 33%-71%)" in line
    assert "2023-24 15m-4h 11 of 24 = 46% (95% 28%-65%)" in line
    assert "live B15b: no result yet" in line and line.endswith("B15b collecting, no verdict; no edge shown")
    for retracted in ("64%", "61%", "of 70", "of 44", "above 60%"):
        assert retracted not in line


def test_the_live_part_follows_the_record():
    a = N.signal_record_line({"n": 13, "tp": 5, "verdict": None})
    b = N.signal_record_line({"n": 14, "tp": 6, "verdict": None})
    assert "live B15b, 15m-4h 5 of 13 = 38% (95% 18%-64%)" in a
    assert a != b and "6 of 14" in b                                       # a fixed string cannot pass this


def test_a_verdict_is_shown_and_only_a_proven_one_drops_no_edge_shown():
    p = N.signal_record_line({"n": 30, "tp": 21, "verdict": {"verdict": "PROVEN", "at_n": 30, "utc": 0}})
    assert "21 of 30 = 70% (95% 52%-83%)" in p and p.endswith("B15b PROVEN at 30 results")
    q = N.signal_record_line({"n": 100, "tp": 40, "verdict": {"verdict": "NOT PROVEN", "at_n": 100, "utc": 0}})
    assert q.endswith("B15b NOT PROVEN at 100 results; no edge shown") and "40 of 100 = 40% (95% 31%-50%)" in q


def _book(store, trades, verdict=None, fname=N.ENG_FILE, tid=N.ENG_ID, **kw):
    os.makedirs(os.path.join(store, N.GRAB_DIR), exist_ok=True)
    with open(os.path.join(store, N.GRAB_DIR, fname), "w") as f:
        json.dump({"id": tid, "started_utc": T - 86400, "trades": trades, "checks": [], "verdict": verdict, **kw}, f)


def test_snapshot_counts_decided_results_only(tmp_path):
    store = str(tmp_path)
    assert N.eng_snapshot(store) is None and N.eng_snapshot(None) is None
    _book(store, [{"status": "TP"}, {"status": "SL"}, {"status": "SL"}, {"status": "EXPIRED"}])
    assert N.eng_snapshot(store) == {"n": 3, "tp": 1, "verdict": None, "since": "2 Nov", "label": "B15", "ended": False}
    assert N.eng_snapshot(store, N.ENG_B_ID) is None                                    # B15b's own file, not B15's
    with open(os.path.join(store, N.GRAB_DIR, N.ENG_FILE), "w") as f:
        f.write("{not json")
    assert N.eng_snapshot(store) is None


def test_the_phone_gets_the_live_record_of_the_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "sixty")
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay("15m", T - 900)}, ["15m"], sent_t=T)                       # position only
    _book(store, [{"status": "TP"}] * 5 + [{"status": "SL"}] * 8, fname=N.ENG_B_FILE, tid=N.ENG_B_ID)   # B15b, live
    _book(store, [{"status": "TP"}] * 4 + [{"status": "SL"}] * 5, ended_utc=T)                      # B15, ended
    N.run(store, {"15m": _pay("15m", T + 2700, [_sig(T + 2700, 3906.34, -1)])}, ["15m"], sent_t=T + 3600 + 300)
    rec = [x for b in sent for x in b if x.startswith("RECORD of engine signals")]
    assert len(rec) == 1 and "live B15b since 2 Nov, 15m-4h 5 of 13 = 38% (95% 18%-64%)" in rec[0]
    assert "B15, engine before Amendment F (ended) 4 of 9 = 44% (95% 19%-73%)" in rec[0]          # apart, not pooled
    assert "18 of 22" not in rec[0] and "9 of 22" not in rec[0] and rec[0].endswith("B15b collecting, no verdict; no edge shown")


def test_first_run_of_the_amended_engine_shows_b15b_with_no_result(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "sixty")
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay("15m", T - 900)}, ["15m"], sent_t=T)                       # position only
    with open(os.path.join(store, N.GRAB_DIR, N.ENG_FILE)) as f, open(os.path.join(store, N.GRAB_DIR, N.ENG_B_FILE)) as g:
        assert json.load(f)["ended_utc"] == json.load(g)["started_utc"] == T                  # the run wires the switch
    os.remove(os.path.join(store, N.GRAB_DIR, N.ENG_B_FILE))                            # production at the merge: alert
    _book(store, [{"status": "TP"}] * 4 + [{"status": "SL"}] * 5)                       # state and B15, no B15b file yet
    N.run(store, {"15m": _pay("15m", T + 2700, [_sig(T + 2700, 3906.34, -1)])}, ["15m"], sent_t=T + 3600 + 300)
    rec = [x for b in sent for x in b if x.startswith("RECORD of engine signals")]
    assert len(rec) == 1 and "live B15b: no result yet" in rec[0] and "live B15:" not in rec[0]
