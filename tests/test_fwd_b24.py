"""B24-CONFIRM-FWD recorder (quantum/fwd_b24.py) against its registration (research/registrations/B24-CONFIRM-FWD.json)."""
import json
from datetime import UTC, datetime

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
    assert res[("H-ALL", 100)] == "NOT PROVEN" and res[("H-SELL", "test ended")] == "NOT PROVEN"   # directions end with H-ALL


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
