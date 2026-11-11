"""B24-CONFIRM-FWD recorder (quantum/fwd_b24.py) against its registration (research/registrations/B24-CONFIRM-FWD.json)."""
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from quantum import fwd_b24 as fb
from quantum import notify

MON = int(datetime(2026, 11, 2, 0, 0, tzinfo=UTC).timestamp())       # a Monday


def _path5():
    """600 5m bars: flat 4000; the 15m bar 40 is the signal (close 4000), 41 confirms (close 4016), then a rise to 4045."""
    c = np.full(600, 4000.0)
    c[123:126] = [4006.0, 4011.0, 4016.0]
    c[126:141] = 4017.0
    c[141:161] = np.linspace(4018.0, 4045.0, 20)
    c[161:] = 4045.0
    o = np.concatenate([[4000.0], c[:-1]])
    h, lo_ = np.maximum(o, c) + 0.5, np.minimum(o, c) - 0.5
    t = MON + 300 * np.arange(600)
    return t, o, h, lo_, c


T5, O5, H5, L5, C5 = _path5()


def _payloads(n15: int, gen: int, forming_c=None, signal=True):
    """The site's payloads at a run that has the 15m bars 0 .. n15 - 1 (and the 5m bars inside them)."""
    n5 = 3 * n15
    t15 = [int(T5[3 * i]) for i in range(n15)]
    o15 = [float(O5[3 * i]) for i in range(n15)]
    h15 = [float(H5[3 * i:3 * i + 3].max()) for i in range(n15)]
    l15 = [float(L5[3 * i:3 * i + 3].min()) for i in range(n15)]
    c15 = [float(C5[3 * i + 2]) for i in range(n15)]
    mk = [{"t": t15[40], "type": "SIGNAL", "dir": 1, "px": c15[40], "tq": 62, "sl": 3987.0, "tp1": 4013.0, "tp2": 4020.0,
           "tp3": 4030.0}] if signal and n15 > 40 else []
    p15 = {"meta": {"tf": "15m", "synthetic": False, "price_source": "td", "generated_utc": datetime.fromtimestamp(gen, UTC).isoformat()},
           "markers": mk, "decisions": [], "news": None, "dashboard": {"checks": {"cost_pts": 0.85}},
           "chart": {"t": t15, "o": o15, "h": h15, "l": l15, "c": c15}}
    meta5 = {"tf": "5m", "synthetic": False, "price_source": "td", "generated_utc": datetime.fromtimestamp(gen, UTC).isoformat(),
             "forming": {"t": int(T5[n5]) if n5 < 600 else None, "c": forming_c} if forming_c is not None else None}
    p5 = {"meta": meta5, "markers": [], "decisions": [], "news": None,
          "chart": {"t": [int(x) for x in T5[:n5]], "o": O5[:n5].tolist(), "h": H5[:n5].tolist(), "l": L5[:n5].tolist(), "c": C5[:n5].tolist()}}
    return {"15m": p15, "5m": p5}


def _close(i15):
    return int(T5[3 * i15]) + 900


def test_a_signal_from_before_the_start_is_never_recorded(tmp_path):
    st: dict = {}
    fb.run(_payloads(45, _close(44)), st, _close(44), str(tmp_path))            # the first run already sees bar 40's signal
    fb.run(_payloads(60, _close(59)), st, _close(59), str(tmp_path))
    rec = json.loads((tmp_path / "research_forward" / fb.FILE).read_text())
    assert st["b24"]["rows"] == [] and rec["rows"] == []


def _drive(tmp_path):
    st: dict = {}
    fb.run(_payloads(30, _close(29)), st, _close(29), str(tmp_path))            # start: nothing yet
    fb.run(_payloads(41, _close(40)), st, _close(40), str(tmp_path))            # the signal bar closes: PENDING
    gen = _close(41) + 420                                                       # the run 7 minutes after the confirming close
    fb.run(_payloads(42, gen, forming_c=4017.5), st, gen, str(tmp_path))
    return st


def test_confirmation_records_the_close_the_executable_price_and_the_latency(tmp_path):
    st = _drive(tmp_path)
    r = st["b24"]["rows"][0]
    assert r["stage"] == "CONFIRMED" and r["t_conf"] == _close(41)
    assert r["A"]["px"] == 4016.0 and r["B"]["px"] == 4017.5 and r["B"]["live_quote"]
    assert r["latency_s"] == 420 and r["slippage"] == pytest.approx(1.5) and r["cost_model"] == 0.85
    assert r["stops"]["B"]["S13"] == 13.0 and r["stops"]["B"]["S10"] == 10.0
    assert r["stops"]["B"]["SATR"] is None or 5.0 <= r["stops"]["B"]["SATR"] <= 40.0


def test_exits_on_5m_bars_then_one_append_never_edited(tmp_path):
    st = _drive(tmp_path)
    fb.run(_payloads(199, _close(198)), st, _close(198), str(tmp_path))         # 48 h of 5m bars later
    path = tmp_path / "research_forward" / fb.FILE
    rec = json.loads(path.read_text())
    assert st["b24"]["rows"] == [] and len(rec["rows"]) == 1
    row = rec["rows"][0]
    assert row["res"]["B T15 S13"]["out"] == "TP" and row["res"]["B T20 S13"]["out"] == "TP"
    assert row["res"]["A T15 S13"]["out"] == "TP" and row["path"] == "5m"
    assert row["res"]["B T15 S13"]["net_op"] == pytest.approx(15.0 - 0.26)
    assert row["A"]["fixed24"]["mfe"] >= 28.0 and row["B"]["fixed24"] is not None
    before = path.read_text()
    fb.run(_payloads(199, _close(198) + 60), st, _close(198) + 60, str(tmp_path))
    assert json.loads(path.read_text())["rows"] == json.loads(before)["rows"]


def _trim(pl, i15):
    """The same payloads with the charts starting at 15m bar i15 (the site was down; older bars left the chart)."""
    for tf, k in (("15m", i15), ("5m", 3 * i15)):
        pl[tf]["chart"] = {c: v[k:] for c, v in pl[tf]["chart"].items()}
    return pl


def test_a_pending_row_whose_bars_left_the_chart_is_a_data_gap_not_a_decision(tmp_path):
    """Bars 41-49 were never examined (no run); from bar 50 price sits $17 above the trigger. Scanning on from the chart's
    first bar would invent a confirmation; the recorder closes the row as DATA GAP and counts it in no look."""
    st: dict = {}
    fb.run(_payloads(30, _close(29)), st, _close(29), str(tmp_path))
    fb.run(_payloads(41, _close(40)), st, _close(40), str(tmp_path))
    fb.run(_trim(_payloads(150, _close(149)), 50), st, _close(149), str(tmp_path))
    rec = json.loads((tmp_path / "research_forward" / fb.FILE).read_text())
    assert [r["stage"] for r in rec["rows"]] == ["DATA GAP"] and fb.primary(rec["rows"][0]) is None
    assert fb.weekly(rec["rows"], notify.trading_week(_close(40)), MON, "COLLECTING")["since_start"]["data_gap"] == 1


def test_a_confirmed_row_whose_exit_bars_left_the_chart_records_data_gap_exits(tmp_path):
    st = _drive(tmp_path)
    fb.run(_trim(_payloads(199, _close(198)), 100), st, _close(198), str(tmp_path))   # 5m bars 126-299 never examined
    rec = json.loads((tmp_path / "research_forward" / fb.FILE).read_text())
    row = rec["rows"][0]
    assert row["stage"] == "CONFIRMED" and {v["out"] for v in row["res"].values()} <= {"DATA GAP", "N/A"}
    assert row["A"]["fixed24"] == {"data_gap": True} and fb.primary(row) is None
    assert not (tmp_path / "research_forward" / (fb.FILE + ".tmp")).exists()


def _fake(k_wins, n, dir_=1, net_win=14.74, net_loss=-13.26):
    rows = []
    for i in range(n):
        win = i < k_wins
        rows.append({"dir": dir_, "res": {"B T15 S13": {"out": "TP" if win else "SL", "net_op": net_win if win else net_loss, "t_exit": i}}})
    return rows


def test_looks_and_thresholds_are_the_registered_ones():
    assert fb.wins_needed() == {30: 21, 50: 32, 75: 46, 100: 59} and fb.BREAK_EVEN == pytest.approx(13.26 / 28)
    c = fb.checks(_fake(21, 30), [], 0)
    assert [(x["hypothesis"], x["look"], x["result"]) for x in c if x["hypothesis"] == "H-ALL"] == [("H-ALL", 30, "PROVEN")]
    c = fb.checks(_fake(20, 30), [], 0)
    assert next(x for x in c if x["hypothesis"] == "H-ALL")["result"] == "CONTINUE"
    c = fb.checks(_fake(21, 30, net_win=1.0, net_loss=-13.26), [], 0)          # the rate passes, the money does not
    assert next(x for x in c if x["hypothesis"] == "H-ALL")["result"] == "CONTINUE"
    rows = _fake(55, 100)
    c = fb.checks(rows, [{"hypothesis": "H-ALL", "look": L, "result": "CONTINUE"} for L in (30, 50, 75)], 0)
    res = {(x["hypothesis"], x["look"]): x["result"] for x in c}
    assert res[("H-ALL", 100)] == "NOT PROVEN"
    assert res[("H-SELL", "test ended")] == "INSUFFICIENT EVIDENCE"       # A2: directions end with H-ALL, undecided


def test_a_weekly_report_is_appended_once_per_finished_week(tmp_path):
    st = _drive(tmp_path)
    nxt = MON + 7 * 86400 + 3600                                                 # the next trading week
    fb.run(_payloads(199, nxt), st, nxt, str(tmp_path))
    fb.run(_payloads(199, nxt + 900), st, nxt + 900, str(tmp_path))
    rec = json.loads((tmp_path / "research_forward" / fb.FILE).read_text())
    assert len(rec["weekly"]) == 1 and rec["weekly"][0]["label"] == "PRELIMINARY"
    w = rec["weekly"][0]["since_start"]
    assert w["confirmed"] == 1 and w["B T15 S13"]["n"] == 1 and w["latency_s_mean"] == 420


def test_the_phone_and_the_state_are_identical_with_the_recorder_on_or_off(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "all")
    monkeypatch.setenv("CONFIRM_PANEL", "0")
    out = {}
    for flag in ("0", "1"):
        monkeypatch.setenv("FWD_B24", flag)
        sent: list = []
        monkeypatch.setattr(notify, "send", lambda lines, sent=sent: sent.append(list(lines)) or [])
        store = tmp_path / flag
        store.mkdir()
        for n15, gen in ((30, _close(29)), (41, _close(40)), (42, _close(41) + 420)):
            rep = notify.run(str(store), _payloads(n15, gen, forming_c=4017.5 if n15 == 42 else None), ["15m"], sent_t=gen)
        st = json.loads((store / notify.STATE).read_text())
        out[flag] = (sent, {k: v for k, v in rep.items() if k != "b24"}, {k: v for k, v in st.items() if k != "b24"})
        assert ("b24" in rep) == (flag == "1") and "error" not in rep.get("b24", {})
    assert out["0"] == out["1"]


def test_amendment_a1_an_overshoot_of_the_20_cap_is_expired_and_never_confirmed(tmp_path):
    """B24-CONFIRM-FWD-A1: the signal bar 40 closes at 4000; the first 15m close $15 beyond is $25 beyond: EXPIRED
    (overshoot) with its move, never an entry, and counted apart in the weekly report."""
    st: dict = {}
    fb.run(_payloads(30, _close(29)), st, _close(29), str(tmp_path))
    fb.run(_payloads(41, _close(40)), st, _close(40), str(tmp_path))
    pl = _payloads(42, _close(41) + 420, forming_c=4025.5)
    pl["15m"]["chart"]["c"][41] = 4025.0
    pl["15m"]["chart"]["h"][41] = 4025.5
    fb.run(pl, st, _close(41) + 420, str(tmp_path))
    rec = json.loads((tmp_path / "research_forward" / fb.FILE).read_text())
    r = rec["rows"][0]
    assert r["stage"] == "EXPIRED" and r["why"] == "overshoot" and r["overshoot_usd"] == 25.0 and "A" not in r
    assert fb.primary(r) is None
    w = fb.weekly(rec["rows"], notify.trading_week(_close(40)), MON, "COLLECTING")["since_start"]
    assert w["expired"] == 1 and w["expired_overshoot"] == 1 and w["confirmed"] == 0


# ---- amendment A2 (research/registrations/B24-CONFIRM-FWD-A2.json): horizon and INSUFFICIENT EVIDENCE ----------------

T0 = int(datetime(2026, 11, 10, 9, 0, tzinfo=UTC).timestamp())
REG_A2 = Path(__file__).resolve().parent.parent / "research" / "registrations" / "B24-CONFIRM-FWD-A2.json"


def _fake_t(k_wins, n, t_first, step=86400, dirs=None):
    rows = []
    for i in range(n):
        win = i < k_wins
        rows.append({"dir": (dirs or [1])[i % len(dirs or [1])], "res": {"B T15 S13": {"out": "TP" if win else "SL",
                     "net_op": 14.74 if win else -13.26, "t_exit": t_first + i * step}}})
    return rows


def test_a2_the_horizon_is_twelve_calendar_years_after_the_start():
    assert fb.HORIZON_YEARS == 12 and not hasattr(fb, "DEADLINE")
    assert fb.horizon_end(T0) == int(datetime(2038, 11, 10, 9, 0, tzinfo=UTC).timestamp())
    leap = int(datetime(2028, 2, 29, 12, 0, tzinfo=UTC).timestamp())
    assert fb.horizon_end(leap) == int(datetime(2040, 2, 29, 12, 0, tzinfo=UTC).timestamp())          # 2040 is a leap year
    assert fb.years_after(leap, 1) == int(datetime(2029, 2, 28, 12, 0, tzinfo=UTC).timestamp())


def test_a2_before_the_horizon_nothing_ends_without_a_look():
    rows = _fake_t(20, 40, T0 + 86400)                                           # 40 decided, 20 of the first 30 won: CONTINUE
    c = fb.checks(rows, [], fb.horizon_end(T0) - 1, T0)
    assert [(x["hypothesis"], x["look"], x["result"]) for x in c] == [("H-ALL", 30, "CONTINUE"), ("H-BUY", 30, "CONTINUE")]


def test_a2_at_the_horizon_every_undecided_hypothesis_ends_insufficient_evidence():
    rows = _fake_t(20, 40, T0 + 86400)
    done = fb.checks(rows, [], T0 + 100 * 86400, T0)
    c = fb.checks(rows, done, fb.horizon_end(T0), T0)
    end = {x["hypothesis"]: x for x in c}
    assert {h: (x["look"], x["result"]) for h, x in end.items()} == {h: ("horizon", "INSUFFICIENT EVIDENCE")
                                                                    for h in ("H-ALL", "H-BUY", "H-SELL")}
    assert (end["H-ALL"]["decided"], end["H-ALL"]["last_look"]) == (40, 30)
    assert (end["H-SELL"]["decided"], end["H-SELL"]["last_look"]) == (0, None)
    assert fb.checks(rows, done + c, fb.horizon_end(T0) + 86400, T0) == []        # final: never written twice


def test_a2_a_result_resolved_after_the_horizon_is_never_counted():
    late = _fake_t(30, 30, fb.horizon_end(T0))                                   # 30 wins, all at or after the horizon
    c = fb.checks(late, [], fb.horizon_end(T0) + 40 * 86400, T0)
    assert all(x["result"] == "INSUFFICIENT EVIDENCE" and x["look"] == "horizon" and x["decided"] == 0 for x in c)
    assert len(c) == 3


def test_a2_the_test_ends_at_the_hundredth_result_and_directions_left_open_are_insufficient_evidence():
    """H-ALL proven at 30; BUY / SELL alternate and reach only 50 each by H-ALL's 100th result: they end there as
    INSUFFICIENT EVIDENCE (results after the 100th are recorded, never counted)."""
    rows = _fake_t(30, 100, T0 + 86400, step=3600, dirs=[1, -1]) + _fake_t(30, 30, T0 + 200 * 86400, dirs=[1])
    c = fb.checks(rows, [], T0 + 300 * 86400, T0)
    res = {(x["hypothesis"], x["look"]): x for x in c}
    assert res[("H-ALL", 30)]["result"] == "PROVEN" and ("H-ALL", 100) not in res
    for h in ("H-BUY", "H-SELL"):
        assert [x["result"] for x in c if x["hypothesis"] == h] == ["CONTINUE", "CONTINUE", "INSUFFICIENT EVIDENCE"]
        assert res[(h, "test ended")]["decided"] == 50 and res[(h, "test ended")]["last_look"] == 50


def test_a2_the_registered_looks_and_thresholds_are_unchanged_and_the_registration_matches_the_code():
    reg = json.loads(REG_A2.read_text())["machine_readable"]
    assert reg["horizon_years"] == fb.HORIZON_YEARS and tuple(reg["looks"]) == fb.LOOKS
    assert {int(k): v for k, v in reg["wins_needed"].items()} == fb.wins_needed() == {30: 21, 50: 32, 75: 46, 100: 59}
    assert reg["z"] == fb.Z and reg["break_even"] == pytest.approx(fb.BREAK_EVEN) and tuple(reg["end_states"]) == fb.ENDS


def test_a2_poisson_interval_is_the_exact_one():
    assert fb.poisson_ci(9, 8.1) == pytest.approx([0.508071, 2.109235], abs=1e-6)       # scipy chi2, computed offline
    assert fb.poisson_ci(0, 1.0) == pytest.approx([0.0, 3.688879], abs=1e-6)
    assert fb.poisson_ci(23, 56.9) == pytest.approx([0.256239, 0.606525], abs=1e-6)


def test_a2_the_annual_report_reads_frequency_never_outcomes():
    rows = _fake_t(10, 20, T0 + 86400, step=7 * 86400, dirs=[1, -1])
    for r in rows:
        r.update(stage="CONFIRMED", t_conf=r["res"]["B T15 S13"]["t_exit"] - 3600)
    a = fb.annual(rows, T0, 1)
    flipped = json.loads(json.dumps(rows))
    for r in flipped:
        x = r["res"]["B T15 S13"]
        x["out"], x["net_op"] = ("SL", -13.26) if x["out"] == "TP" else ("TP", 14.74)
    assert fb.annual(flipped, T0, 1) == a
    h = a["hypotheses"]["H-ALL"]
    assert h["confirmations"] == 20 and h["decided"] == 20 and h["next_look"] == 30
    assert h["months_to_next_look"]["point"] == pytest.approx(10 / (20 / a["months"]))
    assert a["label"].startswith("DESCRIPTIVE")


def test_a2_run_ends_insufficient_evidence_at_the_horizon_with_one_report_per_year(tmp_path):
    st = _drive(tmp_path)
    fb.run(_payloads(199, _close(198)), st, _close(198), str(tmp_path))         # the one result resolves (TP)
    t_end = fb.horizon_end(st["b24"]["started"])
    out = fb.run(_payloads(199, t_end), st, t_end, str(tmp_path))
    rec = json.loads((tmp_path / "research_forward" / fb.FILE).read_text())
    assert out["status"] == "INSUFFICIENT EVIDENCE" and out["label"] == "INSUFFICIENT EVIDENCE"
    assert out["results"] == {h: "INSUFFICIENT EVIDENCE" for h in ("H-ALL", "H-BUY", "H-SELL")}
    assert out["in_sample"] == 1 and out["horizon_end_utc"] == t_end
    assert [a["year"] for a in rec["annual"]] == list(range(1, 13)) and rec["horizon_end_utc"] == t_end
    assert rec["weekly"][-1]["label"].startswith("ENDED: INSUFFICIENT EVIDENCE")
    assert rec["amendments"][-1].endswith("B24-CONFIRM-FWD-A2.json")
    fb.run(_payloads(199, t_end + 900), st, t_end + 900, str(tmp_path))
    rec2 = json.loads((tmp_path / "research_forward" / fb.FILE).read_text())
    assert rec2["checks"] == rec["checks"] and rec2["annual"] == rec["annual"]


# ---- A2 fail-safe and the void start of 2026-11-10 (operator decision 2026-11-11) ---------------------------------

@pytest.mark.parametrize(("val", "want"), [(None, False), ("", False), ("0", False), ("yes", False), ("true", False),
                                           ("1", True), (" 1 ", True)])
def test_a2_the_recorder_is_off_unless_fwd_b24_is_exactly_1(monkeypatch, val, want):
    if val is None:
        monkeypatch.delenv("FWD_B24", raising=False)
    else:
        monkeypatch.setenv("FWD_B24", val)
    assert fb.on() is want


VOID_T = 1794346534                                                              # 2026-11-10T21:35:34Z


def _void_store(tmp_path, rows=0, other=True):
    rf = tmp_path / "research_forward"
    rf.mkdir(parents=True)
    rec = {"registration": "research/registrations/B24-CONFIRM-FWD.json", "started_utc": VOID_T,
           "rows": [{"id": i} for i in range(rows)], "checks": [], "weekly": []}
    (rf / fb.FILE).write_text(json.dumps(rec))
    if other:                                                                    # a stand-in for another test's record
        (rf / "B9-GRAB-FWD.json").write_text(json.dumps({"id": "B9-GRAB-FWD", "trades": [1, 2]}))
    state = {"b24": {"started": VOID_T, "rows": [], "seen": {"k": 1}, "week": "w"}, "plans": [{"id": 7}], "confirm": {"x": 1}}
    return rf, rec, state


def test_a2_the_void_start_is_moved_aside_once_and_nothing_else_is_touched(tmp_path):
    rf, rec, state = _void_store(tmp_path)
    v = fb.void_premature(state, str(tmp_path), VOID_T + 3600)
    assert v["voided_start_utc"] == VOID_T and v["rows_in_record"] == 0 and v["moved_to"] == "B24-CONFIRM-FWD.void-20261110T213534Z.json"
    assert "b24" not in state and state["plans"] == [{"id": 7}] and state["confirm"] == {"x": 1}
    kept = json.loads((rf / v["moved_to"]).read_text())
    assert kept["record"] == rec and kept["state"]["started"] == VOID_T and kept["registration"].endswith("A2.json")
    tomb = json.loads((rf / fb.FILE).read_text())
    assert tomb["void"] is True and tomb["voided_start_utc"] == VOID_T and tomb["moved_to"] == v["moved_to"]
    assert json.loads((rf / "B9-GRAB-FWD.json").read_text()) == {"id": "B9-GRAB-FWD", "trades": [1, 2]}
    snap = {p.name: p.read_bytes() for p in rf.iterdir()}
    assert fb.void_premature(state, str(tmp_path), VOID_T + 7200) is None                # idempotent
    assert {p.name: p.read_bytes() for p in rf.iterdir()} == snap


def test_a2_a_legitimate_start_is_never_voided(tmp_path):
    rf = tmp_path / "research_forward"
    rf.mkdir()
    rec = {"started_utc": VOID_T + 86400, "rows": [{"id": 1}], "checks": [], "weekly": []}
    (rf / fb.FILE).write_text(json.dumps(rec))
    state = {"b24": {"started": VOID_T + 86400, "rows": []}}
    assert fb.void_premature(state, str(tmp_path), VOID_T + 2 * 86400) is None
    assert state["b24"]["started"] == VOID_T + 86400 and json.loads((rf / fb.FILE).read_text()) == rec
    assert fb.void_premature({}, None, 0) is None and fb.void_premature({}, str(tmp_path / "none"), 0) is None


def test_a2_after_the_void_a_later_approved_start_begins_afresh(tmp_path):
    rf, _, state = _void_store(tmp_path)
    fb.void_premature(state, str(tmp_path), VOID_T + 3600)
    fb.run(_payloads(30, _close(29)), state, _close(29), str(tmp_path))
    rec = json.loads((rf / fb.FILE).read_text())
    assert state["b24"]["started"] == _close(29) and rec["started_utc"] == _close(29) and "void" not in rec
    assert rec["amendments"][-1].endswith("A2.json") and rec["rows"] == []
    assert (rf / "B24-CONFIRM-FWD.void-20261110T213534Z.json").exists()


def test_a2_the_void_runs_inside_the_alerts_without_changing_the_phone(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "all")
    monkeypatch.setenv("CONFIRM_PANEL", "0")
    monkeypatch.delenv("FWD_B24", raising=False)
    out = {}
    for name in ("void", "clean"):
        store = tmp_path / name
        store.mkdir()
        if name == "void":
            _, _, st0 = _void_store(store, other=False)
            (store / notify.STATE).write_text(json.dumps({"b24": st0["b24"]}))
        sent: list = []
        monkeypatch.setattr(notify, "send", lambda lines, sent=sent: sent.append(list(lines)) or [])
        for n15, gen in ((30, _close(29)), (41, _close(40)), (42, _close(41) + 420)):
            rep = notify.run(str(store), _payloads(n15, gen, forming_c=4017.5 if n15 == 42 else None), ["15m"], sent_t=gen)
        st = json.loads((store / notify.STATE).read_text())
        out[name] = (sent, {k: v for k, v in rep.items() if k != "b24_void"}, st)
        assert "b24" not in st and "b24" not in rep                                  # off: unset means off
    assert out["void"] == out["clean"]
    rf = tmp_path / "void" / "research_forward"
    assert json.loads((rf / fb.FILE).read_text())["void"] is True
    assert (rf / "B24-CONFIRM-FWD.void-20261110T213534Z.json").exists()
