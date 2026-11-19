"""W5 Entry Price Intelligence (quantum/entry_intel.py): the entry band and the entry check worked by hand at the N1
defaults (lot 0.46 = 46 oz, sizing cost $0.97 / oz, budget $650, stop $13, TP1 $13 on half, TP2 $20 on the rest), the
sizing rule shared with notify.plan_cfg, the path record's races (hand-worked bars, a gap, an ambiguous bar, the horizon),
no look-ahead (run by run equals one pass), and that the module never changes C1, the phone or any other record.

BUY at 4000.00: stop 3987.00, TP1 4013.00, TP2 4020.00.
  budget limit  3987 + 650 / 46 - 0.97 = 4000.16  (the alert's lot loses more than $650 above it)
  R:R limit     u = (0.5 x (4013 + 4020) - 0.97 + (3987 - 0.97)) / 2 = 4000.78  (net R:R 1.00)
  at 4000.10    loss 46 x (13.10 + 0.97) = $647.22, R:R (0.5 x 12.90 + 0.5 x 19.90 - 0.97) / 14.07 = 1.097: WITHIN PLAN
  at 4000.50    loss 46 x 14.47 = $665.62 > $650; 0.44 lot keeps $636.68; R:R 15.03 / 14.47 = 1.039: RESIZE
  at 4001.00    R:R 14.53 / 14.97 = 0.971 < 1: OUTSIDE PLAN (0.42 lot would keep the budget: 650 / 1497 = 0.434)
"""
import copy
import json
import os

import pytest

from quantum import confirm_entry as C1
from quantum import entry_intel as E
from quantum import notify as N

T0 = 1794405600                         # 2026-11-11 14:00 UTC (Wed)
KEYS = ("CONFIRM_MIN_USD", "CONFIRM_CAP_USD", "PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_TP2_USD", "PLAN_COST_PER_LOT",
        "PLAN_RISK_PCT", "ACCOUNT_USD", "PLAN_SIZING", "PLAN_LOT_MAX", "MT5_PRICE_OFFSET", "ENTRY_INTEL")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def _pl():
    return N.plan_cfg()


def _sizing(pl):
    return {"step": pl["lot_step"], "lot_max": pl["lot_max"]}


def _active(d=1, entry=4000.0, t_conf=T0 + 1800):
    pl = _pl()
    return {"id": 7, "tf": "15m", "dir": d, "p0": entry - d * 10.0, "t_close": T0 + 900, "status": "ACTIVE",
            "conf": {"t": t_conf, "px": entry, "move": 10.0, "tier": "MINIMUM"}, "plan": C1.plan_at(entry, d, pl),
            "entry_bar": t_conf - 900, "events": [], "touch": {}}


def test_the_n1_defaults_are_the_hand_worked_ones():
    pl = _pl()
    assert (pl["lot"], pl["size_cost_oz"], pl["budget"], pl["sl_px"], pl["lot_step"]) == (0.46, 0.97, 650.0, 13.0, 0.02)


@pytest.mark.parametrize("d", [1, -1])
def test_the_band_worked_by_hand_both_sides(d):
    p = C1.plan_at(4000.0, d, _pl())
    b = E.band(p, d)
    assert b["budget_px"] == pytest.approx(4000.0 + d * 0.16, abs=0.006) and b["rr_px"] == pytest.approx(4000.0 + d * 0.78, abs=0.006)
    assert b["far_px"] == b["budget_px"] and b["far_resized_px"] == b["rr_px"] and b["far_by"] == "budget"
    assert b["stop"] == 4000.0 - d * 13.0 and b["tp1"] == 4000.0 + d * 13.0
    assert E.rr_at(d * p["entry"], p, d) == pytest.approx(p["rr_net"])            # the same R:R as C1's plan at the entry
    assert E.rr_at(d * b["rr_px"], p, d) == pytest.approx(1.0, abs=2e-3)


@pytest.mark.parametrize("env", [{}, {"PLAN_RISK_PCT": "1.3"}, {"ACCOUNT_USD": "100000"}, {"PLAN_COST_PER_LOT": "250"},
                                 {"PLAN_TP2_USD": "0"}, {"PLAN_LOT_MAX": "0.3"}, {"PLAN_SL_USD": "325"}])
def test_the_sizing_rule_is_plan_cfgs(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    pl = _pl()
    assert E.lot_for(pl["sl_px"], pl["size_cost_oz"], pl["budget"], pl["lot_step"], pl["lot_max"]) == pl["lot"]


@pytest.mark.parametrize("d", [1, -1])
@pytest.mark.parametrize("x, word, lot_b", [(4000.10, "WITHIN PLAN", 0.46), (4000.50, "RESIZE", 0.44), (4001.00, "OUTSIDE PLAN", 0.42),
                                            (3995.00, "WITHIN PLAN", 0.72), (3987.00, "OUTSIDE PLAN", None), (4013.50, "OUTSIDE PLAN", None)])
def test_the_entry_check_worked_by_hand(d, x, word, lot_b):
    px = 4000.0 + d * (x - 4000.0)
    a = E.assess(_active(d), {"px": px, "t": T0 + 1800 + 60, "live": True}, T0 + 1800 + 120, _sizing(_pl()))
    assert a["word"] == word and a["dev_usd"] == pytest.approx(4000.0 - x, abs=1e-9)
    if lot_b is not None:
        assert a["lot_budget"] == lot_b
    if x == 4000.10:
        assert a["loss_alert_lot"] == pytest.approx(647.22) and a["rr_now"] == pytest.approx(1.097, abs=1e-3) and a["why"] == []
        assert a["cost_share"] == pytest.approx(0.97 / 14.07, abs=1e-3)
    if x == 4000.50:
        assert a["loss_alert_lot"] == pytest.approx(665.62) and a["loss_lot_budget"] == pytest.approx(636.68)
        assert "over the $650 budget" in a["why"][0] and a["rr_now"] == pytest.approx(1.039, abs=1e-3)
    if x == 4001.00:
        assert "below 1" in a["why"][0] and a["rr_now"] == pytest.approx(0.971, abs=1e-3)
    if x == 3987.00:
        assert a["why"] == ["price is at or beyond the alert's stop"]
    if x == 4013.50:
        assert "TP1 is already reached" in a["why"][0]


def test_the_check_never_reopens_what_c1_closed_and_needs_a_fresh_price():
    sz, now = _sizing(_pl()), {"px": 4000.0, "t": T0 + 1800, "live": False}
    for st in ("PENDING", "REJECTED", "TP1", "SL", "EXPIRED", "INVALIDATED"):
        assert E.assess({**_active(), "status": st}, now, T0 + 1900, sz) is None
    assert E.assess(_active(), now, T0 + 1800 + C1.FRESH_SEC + 1, sz) is None             # C1's window has passed
    a = E.assess(_active(), {"px": 4000.0, "t": T0 + 1800 - C1.FRESH_SEC - 1, "live": False}, T0 + 1800 + 60, sz)
    assert a["word"] == "NOT CHECKED" and "min old" in a["why"][0]
    assert E.assess(_active(), None, T0 + 1860, sz)["word"] == "NOT CHECKED"


# ---------------- the path record ----------------
def _chart(bars, t0=T0 + 900):
    t = [t0 + 900 * k for k in range(len(bars))]
    o, h, l, c = (list(x) for x in zip(*bars))
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


def _race(bars, d=1, e=4000.0, t_now=None):
    ch = _chart(bars)
    r = E._race_new(e, 13.0, T0 + 900)
    E._advance(r, d, ch, t_now if t_now is not None else ch["t"][-1] + 900, 0.97)
    return r


def test_three_targets_are_raced_separately_against_the_stop():
    r = _race([(4000, 4005, 3998, 4004), (4004, 4010.2, 4003, 4009), (4009, 4012, 3986.5, 3990), (3990, 4030, 3989, 4025)])
    assert r["res"]["10"] == ["TP", T0 + 2700, 4010.0, pytest.approx((10 - 0.97) / 13.97, abs=1e-3)]
    assert r["res"]["15"][:3] == ["SL", T0 + 3600, 3987.0] and r["res"]["20"][0] == "SL" and r["res"]["15"][3] == -1.0
    assert r["n"] == 3 and r["mfe"] == 12.0 and r["mae"] == 13.5                             # the 4th bar is never read


def test_an_ambiguous_bar_counts_as_the_stop_and_a_gap_fills_at_the_open():
    r = _race([(4000, 4011, 3986, 4000)])
    assert [r["res"][k][0] for k in ("10", "15", "20")] == ["AMBIGUOUS", "SL", "SL"]
    g = _race([(4000, 4004, 3999, 4003), (3980, 3982, 3975, 3978)])
    assert g["res"]["10"][:3] == ["SL", T0 + 2700, 3980.0] and g["res"]["10"][3] == pytest.approx((-20 - 0.97) / 13.97, abs=1e-3)
    assert g["res"]["10"][3] < -1.0                                                     # the loss exceeds the plan


def test_the_horizon_leaves_an_undecided_race_open_with_its_mark():
    r = _race([(4000, 4001, 3999, 4000.5)] * (E.HOLD + 5))
    assert r["n"] == E.HOLD and all(v is None for v in r["res"].values()) and r["mark"][1] == 4000.5


def test_no_look_ahead_run_by_run_equals_one_pass():
    bars = [(4000, 4003, 3998, 4002), (4002, 4006, 4001, 4005), (4005, 4011, 4004, 4010), (4010, 4016, 4009, 4015),
            (4015, 4015.5, 3996, 3997), (3997, 4000, 3986, 3988)]
    one = _race(bars)
    ch = _chart(bars)
    r = E._race_new(4000.0, 13.0, T0 + 900)
    for k in range(len(bars) + 1):
        t_now = T0 + 900 + 900 * k
        E._advance(r, 1, ch, t_now, 0.97)
        assert all(v[1] <= t_now for v in r["res"].values() if v is not None)               # only bars closed by then
        assert r["scanned"] + 900 <= t_now or r["n"] == 0
    assert r == one


# ---------------- through C1 and notify ----------------
def _c1_setup(st, close=4012.40, t_now=None):
    sig = {"t": T0, "type": "SIGNAL", "dir": 1, "px": 4000.0}
    C1.open_from(st, {"meta": {"tf": "15m", "price_source": "td"}, "markers": [sig]}, None)
    n = 2                                   # the confirming close is the run's latest closed bar (C1's freshness rule)
    ch = _chart([(4000, 4000.5, 3999.5, 4000), (4000, 4013, 3999, close)], t0=T0)
    ch.update({k: [None] * n for k in ("pdh", "pdl", "pwh", "pwl")})
    t_now = t_now if t_now is not None else T0 + 2 * 900 + 60
    C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": ch, "markers": [sig]}, t_now, _pl(), 0.0, None)
    return ch


def test_run_reads_c1_and_never_writes_it():
    st = {"epi": {"since": T0, "paths": [], "log": [], "last": {}}}
    ch = _c1_setup(st)
    before = copy.deepcopy(st["c1"])
    rep = E.run(st, {"meta": {"tf": "15m"}, "chart": ch}, _pl(), {"px": 4012.40, "t": T0 + 1800, "live": False}, T0 + 1800 + 60)
    assert st["c1"] == before and rep["ok"] and [a["word"] for a in rep["live"]] == ["WITHIN PLAN"]
    x = st["epi"]["paths"][0]
    assert x["p0_race"]["e"] == 4000.0 and x["p0_race"]["from"] == T0 + 900
    assert x["entry_race"]["e"] == 4012.40 and x["entry_race"]["D"] == 13.0 and x["entry_race"]["from"] == T0 + 1800
    assert x["used_share"] == pytest.approx(12.40 / 13.0, abs=1e-3)                 # P0's best move so far: +$13.00
    assert st["epi"]["log"][0]["word"] == "WITHIN PLAN"


def test_setups_before_the_module_started_are_not_recorded_and_the_switch_turns_it_off(monkeypatch):
    st = {"epi": {"since": T0 + 10 ** 6, "paths": [], "log": [], "last": {}}}
    ch = _c1_setup(st)
    E.run(st, {"meta": {"tf": "15m"}, "chart": ch}, _pl(), None, T0 + 1860)
    assert st["epi"]["paths"] == []
    monkeypatch.setenv("ENTRY_INTEL", "0")
    st2 = {}
    assert E.run(st2, {"meta": {"tf": "15m"}, "chart": ch}, _pl(), None, T0 + 1860) == {"id": E.ID, "on": False} and st2 == {}


def test_the_summary_counts_decided_races_and_the_waiting_difference():
    r_tp = {"res": {"10": ["TP", 1, 1.0, 0.646], "15": ["SL", 2, 1.0, -1.0], "20": None}}
    r_sl = {"res": {"10": ["AMBIGUOUS", 1, 1.0, -1.0], "15": ["SL", 1, 1.0, -1.0], "20": ["SL", 1, 1.0, -1.0]}}
    s = E.summary([{"p0_race": r_tp, "entry_race": r_sl}, {"p0_race": r_sl}])
    assert s["p0_race"]["per"]["10"]["tp"] == 1 and s["p0_race"]["per"]["10"]["n"] == 2 and s["p0_race"]["per"]["20"]["n"] == 1
    assert s["entry_race"]["per"]["10"] == {"tp": 0, "n": 1, "wilson": C1.wilson(0, 1), "mean_r": -1.0}
    assert s["waiting_10"] == {"n": 1, "mean_diff_r": pytest.approx(-1.646)}


def _payload(n, edits, markers):
    t = [T0 + 900 * k for k in range(n)]
    o, h, l, c = [4000.0] * n, [4000.5] * n, [3999.5] * n, [4000.0] * n
    for j, (oo, hh, ll, cc) in edits.items():
        o[j], h[j], l[j], c[j] = oo, hh, ll, cc
    ch = {"t": t, "o": o, "h": h, "l": l, "c": c, "pdh": [None] * n, "pdl": [None] * n, "pwh": [None] * n, "pwl": [None] * n}
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": "2026-11-10T14:00:00+00:00", "price_source": "td"},
            "markers": markers, "decisions": [], "dashboard": {}, "chart": ch}


def _scenario(store, monkeypatch, on):
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.delenv("ALERT_MODE", raising=False)
    if not on:
        monkeypatch.setenv("ENTRY_INTEL", "0")
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"] if lines else [])
    sig = {"t": T0 + 900, "type": "SIGNAL", "dir": 1, "px": 4000.0, "tq": 70, "sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0, "tp3": 4030.0}
    N.run(store, {"15m": _payload(1, {}, [])}, ["15m"], sent_t=T0 + 900)
    N.run(store, {"15m": _payload(2, {}, [sig])}, ["15m"], sent_t=T0 + 1800 + 300)
    reps = [N.run(store, {"15m": _payload(3, {2: (4000, 4013, 3999, 4012.40)}, [sig])}, ["15m"], sent_t=T0 + 2700 + 300)]
    reps.append(N.run(store, {"15m": _payload(5, {2: (4000, 4013, 3999, 4012.40), 3: (4012.4, 4023, 4012, 4022),
                                                     4: (4022, 4023, 4020, 4021)}, [sig])}, ["15m"], sent_t=T0 + 4500 + 300))
    return sent, reps, json.load(open(os.path.join(store, N.STATE)))


def test_the_phone_and_every_other_record_are_unchanged(tmp_path, monkeypatch):
    sent1, reps1, st1 = _scenario(str(tmp_path / "on"), monkeypatch, True)
    monkeypatch.undo()
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    sent0, reps0, st0 = _scenario(str(tmp_path / "off"), monkeypatch, False)
    assert sent1 == sent0                                                     # the phone: identical
    assert {k: v for k, v in st1.items() if k != "epi"} == st0 and "epi" not in st0
    for r1, r0 in zip(reps1, reps0):
        assert {k: v for k, v in r1.items() if k != "entry_intel"} == {k: v for k, v in r0.items() if k != "entry_intel"}
        assert r0["entry_intel"] == {"id": E.ID, "on": False}
    ei = reps1[0]["entry_intel"]
    assert ei["ok"] and [a["word"] for a in ei["live"]] == ["WITHIN PLAN"] and ei["live"][0]["entry"] == 4012.40
    assert reps1[1]["entry_intel"]["live"] == []                              # the window has passed: no check, no word
    path = st1["epi"]["paths"][0]
    assert path["entry_race"]["res"]["10"][0] == "TP" and path["p0_race"]["res"]["10"][0] == "TP"
    assert path["p0_race"]["res"]["20"][0] == "TP" and path["entry_race"]["res"]["20"] is None


def test_the_website_card_prints_python_s_band_and_labels_it():
    js = open(os.path.join(os.path.dirname(__file__), "..", "site", "app.js")).read()
    assert js.count("function entryIntelCard(EI)") == 1 and "${c1Card(A.c1)}${entryIntelCard(A.entry_intel)}" in js
    card = js[js.index("function entryIntelCard(EI)"):js.index("function shadowCard(SH)")]
    assert "arithmetic of the alert's plan, not a forecast" in card and "RECORD, NOT A VALIDATED SIGNAL" in card
    assert "no broker bid / ask is connected" in card and "The planned loss is not a maximum" in card
    assert "LIVE.px" not in card and "probability" in card and "chance" not in card    # no live recompute; no odds


def test_the_module_is_not_an_engine_source_and_sends_nothing():
    from quantum import holdout
    assert "entry_intel.py" not in holdout.ENGINE_SOURCES
    src = open(E.__file__).read()
    imports = sorted(line.strip() for line in src.splitlines() if line.startswith(("import ", "from ")))
    assert imports == ["from . import confirm_entry as C1", "from __future__ import annotations", "import math", "import os"]
    assert "send(" not in src and "requests" not in src and "urllib" not in src         # no network, no phone


def test_the_decision_record_keeps_one_line_per_change_of_word():
    st = {"epi": {"since": T0, "paths": [], "log": [], "last": {}}}
    ch = _c1_setup(st)
    p15 = {"meta": {"tf": "15m"}, "chart": ch}
    for px_ in (4012.40, 4012.45, 4012.80, 4012.90):                                   # WITHIN, WITHIN, RESIZE, RESIZE
        E.run(st, p15, _pl(), {"px": px_, "t": T0 + 1800 + 30, "live": True}, T0 + 1800 + 60)
    assert [x["word"] for x in st["epi"]["log"]] == ["WITHIN PLAN", "RESIZE"] and st["epi"]["last"] == {"1": "RESIZE"}
