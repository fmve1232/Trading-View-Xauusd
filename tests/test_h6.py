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
    for kw in ({"tqf": True}, {"ev": True}, {"buy": 0}):                              # every other veto / gate still does
        assert not any(arm_h6.evaluate(_res(**kw), cfg)["exec_buy"]), kw
    assert arm_h6.evaluate(_res(buy=0, sell=1), cfg)["exec_sell"] == [0, 0, 1]
    locked = arm_h6.evaluate(_res(lock=True), cfg)["exec_buy"][-1]
    assert locked == (0 if cfg.use_risk_limits else 1)                                  # the risk lock as the engine applies it


def test_plan_is_the_engines_own():
    ev = arm_h6.evaluate(_res(), DEFAULT)
    assert (ev["plan_sl"][2], ev["plan_tp1"][2], ev["plan_tp2"][2]) == (1990.0, 2010.0, 2020.0)


def test_equals_the_engine_except_where_the_score_vetoed():
    """On the real engine: H6 == exec_buy / exec_sell on every bar where cal_veto is off; where it is on, H6 is the
    engine's should_buy / should_sell unless another veto or the risk lock blocks it."""
    vetoed_all = 0
    for seed in (6, 7):                       # seed 7 has a bar the score veto blocked and no other veto did
        vetoed_all += _equivalence(seed)
    assert vetoed_all >= 1, "no bar where H6 differs from the engine: the test would not see a broken rule"


def _equivalence(seed):
    m = load_synthetic("15m", bars=1500, seed=seed)
    res = engine.run(m, DEFAULT)
    ev = arm_h6.evaluate(res, DEFAULT)
    R = res.rows
    n = len(res.F["c"])
    vetoed = 0
    for i in range(n):
        cal = bool(R["cal_veto"][i])
        if not cal:
            assert ev["exec_buy"][i] == int(bool(R["exec_buy"][i])) and ev["exec_sell"][i] == int(bool(R["exec_sell"][i])), i
        else:
            other = bool(R["tq_floor_veto"][i]) or bool(R["ev_veto"][i]) or (DEFAULT.use_risk_limits and bool(R["risk_lock"][i]))
            assert ev["exec_buy"][i] == int(bool(R["should_buy"][i]) and not other), i
            assert ev["exec_sell"][i] == int(bool(R["should_sell"][i]) and not other), i
            vetoed += ev["exec_buy"][i] + ev["exec_sell"][i]
        assert not (ev["exec_buy"][i] and ev["exec_sell"][i])
    assert sum(ev["score_vetoed"]) == vetoed
    return vetoed


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
