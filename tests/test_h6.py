"""Arm H6 "No score veto" (audit/PREREGISTRATION.md Amendment 12): the rule as written, no look-ahead, own freeze key."""
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from quantum import arm_h6, engine, holdout
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic


def _res(buy=1, sell=0, tqf=False, ev=False, cal=False, lock=False):
    n = 3
    F = {"c": np.full(n, 2000.0)}
    R = {"should_buy": [0, 0, buy], "should_sell": [0, 0, sell], "tq_floor_veto": [False, False, tqf], "ev_veto": [False, False, ev],
         "cal_veto": [False, False, cal], "risk_lock": [False, False, lock],
         "plan_sl": [1990.0] * n, "plan_tp1": [2010.0] * n, "plan_tp2": [2020.0] * n}
    return SimpleNamespace(F=F, rows=R)


def test_only_the_score_veto_is_removed():
    cfg = DEFAULT
    assert arm_h6.evaluate(_res(), cfg)["exec_buy"] == [0, 0, 1]
    ev = arm_h6.evaluate(_res(cal=True), cfg)
    assert ev["exec_buy"] == [0, 0, 1] and ev["score_vetoed"] == [0, 0, 1]          # the score veto does not block H6
    for kw in ({"tqf": True}, {"buy": 0}):                                             # every applied veto / gate still does
        assert not any(arm_h6.evaluate(_res(**kw), cfg)["exec_buy"]), kw
    # PROPOSED Amendment F (F3): the EV flag is a shadow value the engine no longer applies, so H6 does not apply it either
    assert arm_h6.evaluate(_res(ev=True), cfg)["exec_buy"] == [0, 0, 1]
    assert arm_h6.evaluate(_res(buy=0, sell=1), cfg)["exec_sell"] == [0, 0, 1]
    locked = arm_h6.evaluate(_res(lock=True), cfg)["exec_buy"][-1]
    assert locked == (0 if cfg.use_risk_limits else 1)                                  # the risk lock as the engine applies it


def test_plan_is_the_engines_own():
    ev = arm_h6.evaluate(_res(), DEFAULT)
    assert (ev["plan_sl"][2], ev["plan_tp1"][2], ev["plan_tp2"][2]) == (1990.0, 2010.0, 2020.0)


def test_equals_the_engine_on_every_bar():
    """PROPOSED Amendment F (F3): the engine applies no calibration veto, so H6 (the engine without it) equals the
    treatment arm on every bar and no trade is 'score-vetoed'. The amendment closes H6 at merge."""
    taken = 0
    for seed in (6, 7):
        m = load_synthetic("15m", bars=1500, seed=seed)
        res = engine.run(m, DEFAULT)
        ev = arm_h6.evaluate(res, DEFAULT)
        R = res.rows
        for i in range(len(res.F["c"])):
            assert ev["exec_buy"][i] == int(bool(R["exec_buy"][i])) and ev["exec_sell"][i] == int(bool(R["exec_sell"][i])), (seed, i)
            taken += ev["exec_buy"][i] + ev["exec_sell"][i]
        assert sum(ev["score_vetoed"]) == 0
    assert taken >= 1, "no signal taken: the comparison would be empty"


def test_no_lookahead():
    m = load_synthetic("15m", bars=1500, seed=6)
    res = engine.run(m, DEFAULT)
    full = arm_h6.evaluate(res, DEFAULT)
    n = len(res.F["c"])
    k = 1000
    cut = SimpleNamespace(F={kk: (v[:k] if hasattr(v, "__len__") and not isinstance(v, (str, dict)) and len(v) == n else v)
                             for kk, v in res.F.items()}, rows={kk: v[:k] for kk, v in res.rows.items()})
    part = arm_h6.evaluate(cut, DEFAULT)
    assert part["exec_buy"] == full["exec_buy"][:k] and part["exec_sell"] == full["exec_sell"][:k]


def test_own_freeze_key_outside_the_engine_key(tmp_path):
    ek = holdout.freeze_key(DEFAULT)
    k = arm_h6.freeze_key(ek)
    assert k.startswith(ek + ":") and len(k.split(":")) == 3 and "arm_h6.py" not in holdout.ENGINE_SOURCES
    m = holdout.load_or_freeze_arm(str(tmp_path), "h6", k, datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc))
    assert m["status"] == "STARTED"


def test_every_trade_opens_on_an_h6_signal():
    m = load_synthetic("15m", bars=1500, seed=6)
    res = engine.run(m, DEFAULT)
    trades, ev = arm_h6.simulate(res, DEFAULT)
    assert all(ev["exec_buy"][t["entry_i"]] or ev["exec_sell"][t["entry_i"]] for t in trades)
    assert all((t["dir"] == "LONG") == bool(ev["exec_buy"][t["entry_i"]]) for t in trades)


def test_amendment_f_closes_h6_read_only(tmp_path):
    """Amendment F closes H6: the page shows its final record; no manifest or ledger is written, restarted or archived."""
    import json
    import os
    from quantum import report
    hd = tmp_path / "holdout"
    hd.mkdir()
    key = "5e4630924d663fc5:a6f2be58c74887ed:7c4ac023578836c6"
    man = {"arm": "h6", "freeze_key": key, "freeze_utc": "2026-11-03T23:47:43+00:00", "status": "ACTIVE", "history": []}
    led = [{"freeze_key": key, "entry_time": "2026-11-05T10:00:00+00:00", "dir": "LONG", "r": 1.0, "pts": 13.0, "tp1_hit": True, "bars": 4},
           {"freeze_key": key, "entry_time": "2026-11-06T10:00:00+00:00", "dir": "SHORT", "r": -1.0, "pts": -13.0, "tp1_hit": False, "bars": 2},
           {"freeze_key": key, "entry_time": "2026-11-07T10:00:00+00:00", "dir": "LONG", "r": 2.0, "pts": 26.0, "tp1_hit": True, "bars": 9}]
    (hd / "manifest_h6.json").write_text(json.dumps(man))
    (hd / "15m_h6.json").write_text(json.dumps(led))
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in hd.rglob("*")}
    mk = SimpleNamespace(synthetic=False, tf="15m")
    out = report.h6_section(mk, None, DEFAULT, {"freeze_key": "1f88aad357497da4:4440d52587f5cc6b"},
                            datetime(2026, 11, 16, tzinfo=timezone.utc), str(tmp_path), None)
    assert out["closed"].startswith("Closed by Amendment F") and "no verdict" in out["closed"]
    assert out["freeze"] == man and out["forward"]["n"] == 3 and abs(out["forward"]["win_rate"] - 200 / 3) < 1e-9
    assert "signals" not in out and "signal_now" not in out                         # H6's signals are the engine's now
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in hd.rglob("*")} == before     # nothing written or moved
    assert not os.path.exists(hd / "archive")
    empty = report.h6_section(mk, None, DEFAULT, {}, datetime(2026, 11, 16, tzinfo=timezone.utc), str(tmp_path / "none"), None)
    assert empty["freeze"] is None and empty["forward"] == {"n": 0}
    syn = report.h6_section(SimpleNamespace(synthetic=True, tf="15m"), None, DEFAULT, {}, datetime(2026, 11, 16, tzinfo=timezone.utc),
                            str(tmp_path), None)
    assert syn["freeze"] is None and syn["forward"] == {"n": 0}                        # a synthetic run reads no store
