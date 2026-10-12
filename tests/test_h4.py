"""Arm H4 "Playbook" (audit/PREREGISTRATION.md Amendment 8): the rule as written, no look-ahead, own freeze key."""
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from quantum import arm_h4, engine, holdout
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic

NAN = math.nan


def _res(closes, **levels):
    n = len(closes)
    c = np.asarray(closes, float)
    F = {"c": c, "o": c, "h": c + 0.5, "l": c - 0.5, "aatr": np.full(n, 4.0), "reg_sl_mult": np.full(n, 1.5),
         "pm_high": np.full(n, NAN), "pm_low": np.full(n, NAN), "index": None, "sess_spread": np.full(n, 0.3)}
    rows = {k: [NAN] * n for k in ("pdh", "pdl", "pwh", "pwl", "eqh", "eql", "cdh", "cdl", "active_res", "active_sup", "vah", "val", "vpoc")}
    for k, v in levels.items():
        (F if k in ("pm_high", "pm_low") else rows)[k] = [v] * n if not isinstance(v, list) else v
    return SimpleNamespace(F=F, rows=rows)


def test_playbook_geometry_follows_the_written_rule():
    # price 2000, ATR 4, stop distance D = 6; levels below 1990 (trigger) 1985 (< 1 D away) 1970 1950; above 2008 2030
    r = _res([2000.0] * 3, cdl=1990.0, val=1985.0, pdl=1970.0, pwl=1950.0, cdh=2008.0, pdh=2030.0)
    pb = arm_h4.playbook(r, 2)
    s, b = pb["sell"], pb["buy"]
    assert pb["stop_dist"] == pytest.approx(6.0)
    assert (s["trigger"], s["tname"], s["stop"]) == (1990.0, "Day low", 1996.0)
    assert (s["tp1"], s["tp1n"], s["tp2"], s["tp2n"]) == (1970.0, "PDL", 1950.0, "PWL")       # 1985 is < 1 D beyond: skipped
    assert (b["trigger"], b["stop"], b["tp1"], b["tp1n"]) == (2008.0, 2002.0, 2030.0, "PDH")
    assert b["tp2"] == b["tp1"]                                                                 # no second level
    r2 = _res([2000.0] * 3, cdl=1990.0)
    assert arm_h4.playbook(r2, 2)["sell"]["tp1"] == pytest.approx(1978.0) and arm_h4.playbook(r2, 2)["sell"]["tp1n"] == "2R"


def test_trigger_needs_a_close_beyond_it_and_uses_the_previous_bars_playbook():
    lv = dict(cdl=1990.0, pdl=1970.0, cdh=2008.0, pdh=2030.0)
    ev = arm_h4.evaluate(_res([2000.0, 1995.0, 1989.0, 1988.0], **lv))
    assert ev["exec_sell"] == [0, 0, 1, 0]                                   # 1989 closes below 1990
    assert ev["plan_sl"][2] == pytest.approx(1996.0) and ev["plan_tp1"][2] == 1970.0
    ev = arm_h4.evaluate(_res([2000.0, 2009.0], **lv))
    assert ev["exec_buy"] == [0, 1]
    ev = arm_h4.evaluate(_res([2000.0, 1969.0], **lv))                       # already beyond TP1: no signal
    assert not any(ev["exec_sell"])
    ev = arm_h4.evaluate(_res([2000.0, 1990.2], **lv))                       # touch, but no close below
    assert not any(ev["exec_sell"])


def test_gap_from_price_and_merging():
    r = _res([2000.0] * 2, cdl=1999.8, val=1990.0, pdl=1990.1)              # 1999.8 is within 0.1 ATR of price
    s = arm_h4.playbook(r, 1)["sell"]
    assert s["trigger"] == 1990.0                                            # 1990.0 and 1990.1 merged (< 0.05 ATR)


def test_no_lookahead_on_the_engine_output():
    m = load_synthetic("15m", bars=1500, seed=4)
    res = engine.run(m, DEFAULT)
    full = arm_h4.evaluate(res)
    n = len(res.F["c"])
    for k in (600, 1000, n - 1):
        cut = SimpleNamespace(F={kk: (v[:k] if hasattr(v, "__len__") and not isinstance(v, (str, dict)) and len(v) == n else v)
                                 for kk, v in res.F.items()}, rows={kk: v[:k] for kk, v in res.rows.items()})
        part = arm_h4.evaluate(cut)
        assert part["exec_buy"] == full["exec_buy"][:k] and part["exec_sell"] == full["exec_sell"][:k]
    assert sum(full["exec_buy"]) + sum(full["exec_sell"]) > 0
    trades, _ = arm_h4.simulate(res, DEFAULT)
    assert all((t["dir"] == "LONG") == (t["sl"] < t["entry"]) for t in trades if "sl" in t)


def test_own_freeze_key_and_outside_the_engine_key(tmp_path):
    ek = holdout.freeze_key(DEFAULT)
    k = arm_h4.freeze_key(ek)
    assert k.startswith(ek + ":") and len(k.split(":")) == 3
    assert "arm_h4.py" not in holdout.ENGINE_SOURCES
    t0 = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
    m = holdout.load_or_freeze_arm(str(tmp_path), "h4", k, t0)
    assert m["status"] == "STARTED" and holdout.load_or_freeze_arm(str(tmp_path), "h4", k, t0 + timedelta(hours=1))["status"] == "ACTIVE"
