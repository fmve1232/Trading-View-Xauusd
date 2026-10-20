"""Arm H5 "High confidence" (audit/PREREGISTRATION.md Amendment 10): the rule as written, no look-ahead, own freeze key."""
import math
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from quantum import arm_h5, engine, holdout
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic

NAN = math.nan


def _res(n=3, buy=1, label="BULL", s240=80.0, sD=70.0, macro=True, sq=60):
    F = {"c": np.full(n, 2000.0), "htf_scores": {"240": np.full(n, s240), "D": np.full(n, sD)},
         "macro_bull": np.full(n, macro), "macro_bear": np.full(n, False), "session_quality": np.full(n, sq)}
    R = {"exec_buy": [0] * (n - 1) + [buy], "exec_sell": [0] * n, "bias_label": [label] * n,
         "plan_sl": [1990.0] * n, "plan_tp1": [2010.0] * n, "plan_tp2": [2020.0] * n}
    return SimpleNamespace(F=F, rows=R)


def test_all_five_conditions_are_required():
    assert arm_h5.evaluate(_res(), 900)["exec_buy"] == [0, 0, 1]
    for kw in ({"buy": 0}, {"label": "BULL-ISH"}, {"s240": 55.0}, {"sD": 40.0}, {"macro": False}, {"sq": 13}):
        assert not any(arm_h5.evaluate(_res(**kw), 900)["exec_buy"]), kw


def test_htf_layers_live_only_above_the_chart():
    # on a 4H chart only the 1D layer is live, so the 4H score is ignored; on a 1D chart none is live: no signal
    assert arm_h5.evaluate(_res(s240=10.0), 14400)["exec_buy"][-1] == 1
    assert not any(arm_h5.evaluate(_res(), 86400)["exec_buy"])


def test_plan_is_the_engines_own():
    ev = arm_h5.evaluate(_res(), 900)
    assert (ev["plan_sl"][2], ev["plan_tp1"][2], ev["plan_tp2"][2]) == (1990.0, 2010.0, 2020.0)


def test_no_lookahead_and_subset_of_engine_signals():
    m = load_synthetic("15m", bars=1500, seed=6)
    res = engine.run(m, DEFAULT)
    full = arm_h5.evaluate(res, m.tf_sec)
    n = len(res.F["c"])
    for i in range(n):                                  # every H5 signal is an engine signal on the same bar
        assert not full["exec_buy"][i] or res.rows["exec_buy"][i]
        assert not full["exec_sell"][i] or res.rows["exec_sell"][i]
    k = 1000
    cut = SimpleNamespace(F={kk: (v[:k] if hasattr(v, "__len__") and not isinstance(v, (str, dict)) and len(v) == n else
                                  {a: b[:k] for a, b in v.items()} if isinstance(v, dict) and kk == "htf_scores" else v)
                             for kk, v in res.F.items()}, rows={kk: v[:k] for kk, v in res.rows.items()})
    part = arm_h5.evaluate(cut, m.tf_sec)
    assert part["exec_buy"] == full["exec_buy"][:k] and part["exec_sell"] == full["exec_sell"][:k]


def test_own_freeze_key_outside_the_engine_key(tmp_path):
    ek = holdout.freeze_key(DEFAULT)
    k = arm_h5.freeze_key(ek)
    assert k.startswith(ek + ":") and len(k.split(":")) == 3 and "arm_h5.py" not in holdout.ENGINE_SOURCES
    m = holdout.load_or_freeze_arm(str(tmp_path), "h5", k, datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc))
    assert m["status"] == "STARTED"
