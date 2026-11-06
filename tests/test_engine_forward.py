"""B15-ENGINE-FWD (research/registrations/B15-ENGINE-FWD.json): the engine's own signal alerts, TP1 +$13 before
SL -$13, scored from the plans' recorded results; checks only at 30, 40 ... 100; Wilson 95% lower bound > 51.0%."""
import json

import pytest

from quantum import notify

T0 = 1794000000


def _rec(i, result, t_dec=None, px=13.0, tf="15m", **kw):
    t = T0 + 900 * i if t_dec is None else t_dec
    return {"id": i, "tf": tf, "t": t - 900, "t_dec": t, "dir": 1, "entry": 4000.0, "sl": 4000.0 - px, "tp": 4000.0 + px,
            "sl_usd": 650, "tp_usd": 650, "lot": 0.5, "result": result, "t_res": t + 600, **kw}


def test_registration_matches_the_code():
    with open("research/registrations/B15-ENGINE-FWD.json") as f:
        reg = json.load(f)
    assert reg["approved_by_operator"] is True and reg["rule"]["take_profit_1_price"] == notify.ENG_PX == reg["rule"]["stop_loss_price"]
    assert notify.ENG_BE == pytest.approx(0.51) and notify.ENG_DEADLINE == "2027-06-30"
    assert "21/30, 27/40, 33/50, 39/60, 44/70, 50/80, 56/90, 61/100" in reg["primary_test"]["proven"]
    need = {L: next(k for k in range(L + 1) if notify._wilson(k, L)[0] > notify.ENG_BE) for L in notify.ENG_LOOKS}
    assert need == {30: 21, 40: 27, 50: 33, 60: 39, 70: 44, 80: 50, 90: 56, 100: 61}


def test_trades_are_the_plans_since_the_start_at_13_dollars():
    vlog = [_rec(0, "TP", t_dec=T0 - 1), _rec(1, "TP"), _rec(2, "SL"), _rec(3, "BOTH"), _rec(4, "EXPIRED"),
            _rec(5, "TP", px=10.0), _rec(6, "TP", tp2_result="TP2")]
    tr, excl = notify.eng_trades(vlog, T0)
    assert [(x["id"], x["status"]) for x in tr] == [(1, "TP"), (2, "SL"), (3, "SL"), (4, "EXPIRED"), (6, "TP")]
    assert excl == 1 and tr[-1]["tp2_result"] == "TP2"


def test_verdict_only_at_the_looks():
    win29 = [_rec(i, "TP" if i < 21 else "SL") for i in range(29)]
    tr, _ = notify.eng_trades(win29, T0)
    v = notify.eng_verdict(tr, {}, T0 + 10**6)
    assert v["verdict"] is None and v["checks"] == [] and v["status"].startswith("COLLECTING: 29 results, 72% TP1 first; first check at 30")
    tr30, _ = notify.eng_trades(win29 + [_rec(29, "SL")], T0)
    v = notify.eng_verdict(tr30, {}, T0 + 10**6)
    assert v["checks"][0]["n"] == 30 and v["checks"][0]["tp"] == 21 and v["verdict"]["verdict"] == "PROVEN"
    tr30b, _ = notify.eng_trades([_rec(i, "TP" if i < 20 else "SL") for i in range(30)], T0)
    v = notify.eng_verdict(tr30b, {}, T0 + 10**6)
    assert v["verdict"] is None and v["checks"][0]["proven"] is False and v["next_check"] == 40
    tr100, _ = notify.eng_trades([_rec(i, "TP" if i % 2 else "SL") for i in range(100)], T0)
    assert notify.eng_verdict(tr100, {}, T0 + 10**6)["verdict"]["verdict"] == "NOT PROVEN"
    late = notify.eng_verdict(tr30b, {}, int(notify.datetime(2027, 7, 1, tzinfo=notify.timezone.utc).timestamp()))
    assert late["verdict"]["verdict"] == "NOT PROVEN"                                    # the deadline


def test_record_is_saved_and_a_check_is_announced_once(tmp_path):
    store = str(tmp_path)
    lines, blk = notify.eng_run(store, [], [], T0)                                       # first run: the start
    assert lines == [] and blk["status"] == "COLLECTING: no result yet; first check at 30" and blk["started_utc"] == T0
    vlog = [_rec(i + 1, "TP" if i < 22 else "SL") for i in range(30)]
    lines, blk = notify.eng_run(store, vlog, [], T0 + 86400)
    assert len(lines) == 2 and lines[0].startswith("ENGINE TEST (B15-ENGINE-FWD) CHECK at 30 results: TP1 first 22/30 = 73%")
    assert "PROVEN at 30 results" in lines[1] and blk["by_tf"] == {"15m": {"n": 30, "tp": 22}}
    rec = json.loads((tmp_path / "research_forward" / "B15-ENGINE-FWD.json").read_text())
    assert rec["started_utc"] == T0 and len(rec["trades"]) == 30 and rec["verdict"]["verdict"] == "PROVEN"
    again, _ = notify.eng_run(store, vlog, [], T0 + 2 * 86400)
    assert again == []                                                                   # nothing repeated


def test_run_publishes_the_engine_test(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "send", lambda lines: ["test"])
    for k in ("PLAN", "PLAN_TP2_USD", "PLAN_TP_USD", "PLAN_SL_USD", "PLAN_LOT"):
        monkeypatch.delenv(k, raising=False)
    pay = {"15m": {"meta": {"tf": "15m", "synthetic": False, "generated_utc": "2026-11-06T13:00:00+00:00"}, "markers": [],
                   "decisions": [], "news": None, "chart": {"t": [T0], "h": [None], "l": [None]}}}
    rep = notify.run(str(tmp_path), pay, ["15m"], sent_t=T0 + 60)
    assert rep["engine_test"]["id"] == "B15-ENGINE-FWD" and rep["engine_test"]["n"] == 0
    assert (tmp_path / "research_forward" / "B15-ENGINE-FWD.json").exists()
