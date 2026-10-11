"""Arm H3 "Sweep-to-Value" (audit/PREREGISTRATION.md Amendment 7 section 3, the Pine line's H2 rule):
the rules as written, no look-ahead, its own freeze key, and the alerts it feeds."""
import copy
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantum import arm_h3, engine, holdout, notify
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic

NAN = math.nan
N = 30


def _res(n=N):
    """Flat context at 2005, ATR 4, POC 2008 / VAH 2012 / VAL 2001; a 5-bar swing low at bar 8 (low 1999)."""
    idx = pd.date_range("2026-10-05 08:00", periods=n, freq="1h", tz="UTC")
    c = np.full(n, 2005.0); h = c + 1.0; l = c - 1.0
    l[8] = 1999.0                                          # pivot low (5 left, 5 right), confirmed at bar 13
    F = {"index": idx, "o": c.copy(), "h": h, "l": l, "c": c, "atr": np.full(n, 4.0),
         "sess_spread": np.full(n, 0.3), "session_label": np.array(["LON"] * n), "mkt_regime": np.array(["NORMAL"] * n),
         "ema20": c.copy(), "ema100": c.copy(), "ema200": c.copy(), "session_quality": np.full(n, 60)}
    R = {"vpoc": [2008.0] * n, "vah": [2012.0] * n, "val": [2001.0] * n}
    return SimpleNamespace(F=F, rows=R, events=[])


@pytest.fixture
def scores(monkeypatch):
    s = {"60": 100.0, "240": 80.0, "D": 20.0}              # 2 of 3 up -> trend up
    monkeypatch.setattr(arm_h3, "htf_scores", lambda market, n: {k: np.full(n, v) for k, v in s.items()})
    return s


def _long_setup(r, i=16):
    r.F["l"][i], r.F["c"][i], r.F["h"][i] = 1997.0, 2003.0, 2004.0    # wick below 1999, close back above, below POC
    return r


def test_long_signal_and_plan_follow_the_written_rules(scores):
    ev = arm_h3.evaluate(_long_setup(_res()), None)
    assert [i for i, x in enumerate(ev["exec_buy"]) if x] == [16] and not any(ev["exec_sell"])
    # R = 2003 - (1997 - 0.15 x 4) = 6.6 (between 2 and 20); stop = 1996.4
    assert ev["plan_sl"][16] == pytest.approx(1996.4)
    # TP1 = max(POC 2008, 2003 + 6.6) = 2009.6; TP2 = max(VAH 2012, 2003 + 13.2) = 2016.2
    assert ev["plan_tp1"][16] == pytest.approx(2009.6) and ev["plan_tp2"][16] == pytest.approx(2016.2)
    assert ev["swept"][16] == 1999.0


def test_the_swing_is_consumed_once_traded_through(scores):
    r = _long_setup(_res())
    r.F["l"][20], r.F["c"][20], r.F["h"][20] = 1996.0, 2003.0, 2004.0  # a second wick: the level is already used
    assert sum(arm_h3.evaluate(r, None)["exec_buy"]) == 1
    r2 = _res()
    r2.F["l"][14], r2.F["c"][14] = 1998.0, 1998.5                     # trades through and CLOSES below: no sweep
    r2.F["l"][16], r2.F["c"][16] = 1997.0, 2003.0                     # and the level is gone afterwards
    assert not any(arm_h3.evaluate(r2, None)["exec_buy"])


def test_a_pivot_is_not_liquidity_before_it_is_confirmed(scores):
    r = _res()
    r.F["l"][11], r.F["c"][11], r.F["h"][11] = 1997.0, 2003.0, 2004.0  # bar 11 < 13: the pivot at 8 is not confirmed yet
    assert not any(arm_h3.evaluate(r, None)["exec_buy"])


@pytest.mark.parametrize("breaker", ["trend", "value", "risk_small", "risk_large", "no_poc"])
def test_each_rule_is_required(scores, breaker):
    r = _long_setup(_res())
    if breaker == "trend":
        scores["240"] = 50.0                                          # only 1 of 3 up
    elif breaker == "value":
        r.rows["vpoc"] = [2002.0] * N                                 # close 2003 above the POC: no discount
    elif breaker == "risk_small":
        r.F["atr"][:] = 20.0                                          # R = 6 + 3 = 9 < 0.5 x 20
        r.F["l"][16] = 1998.9; r.F["c"][16] = 2004.9
    elif breaker == "risk_large":
        r.F["atr"][:] = 1.0; r.F["l"][16] = 1990.0                    # R = 13.15 > 5 x 1
    elif breaker == "no_poc":
        r.rows["vpoc"] = [NAN] * N
    assert not any(arm_h3.evaluate(r, None)["exec_buy"])


def test_short_is_the_mirror(monkeypatch):
    monkeypatch.setattr(arm_h3, "htf_scores", lambda market, n: {k: np.full(n, 0.0) for k in arm_h3.HTF_KEYS})
    r = _res()
    r.F["l"][8] = 2004.0
    r.F["h"][8] = 2011.0                                              # pivot high
    r.rows.update(vpoc=[2002.0] * N, val=[1990.0] * N)
    r.F["h"][16], r.F["c"][16], r.F["l"][16] = 2013.0, 2007.0, 2006.0
    ev = arm_h3.evaluate(r, None)
    assert ev["exec_sell"][16] == 1 and not any(ev["exec_buy"])
    # R = 2013 + 0.6 - 2007 = 6.6; TP1 = min(POC 2002, 2000.4) = 2000.4; TP2 = min(VAL 1990, 1993.8) = 1990
    assert ev["plan_sl"][16] == pytest.approx(2013.6)
    assert ev["plan_tp1"][16] == pytest.approx(2000.4) and ev["plan_tp2"][16] == pytest.approx(1990.0)


def test_trend_scores_use_completed_higher_timeframe_bars_only():
    m = load_synthetic("15m", bars=900, seed=7)
    n = len(m.base)
    sc = arm_h3.htf_scores(m, n)
    assert set(sc) == {"60", "240", "D"} and all(len(v) == n for v in sc.values())
    # cutting the HTF series after a chart bar's close changes nothing up to that bar
    k = 600
    t_close = m.close_times[k]
    m2 = copy.copy(m)
    m2.htf = {key: df[df.index < t_close] for key, df in m.htf.items()}
    sc2 = arm_h3.htf_scores(m2, n)
    for key in sc:
        np.testing.assert_array_equal(sc[key][:k + 1], sc2[key][:k + 1])


def test_no_lookahead_on_the_engine_output():
    m = load_synthetic("15m", bars=1500, seed=9)
    res = engine.run(m, DEFAULT)
    full = arm_h3.evaluate(res, m)
    n = len(res.F["c"])
    for k in (700, 1100, n - 1):
        mc = copy.copy(m)
        mc.base = m.base.iloc[:k]
        cut = SimpleNamespace(F={kk: (v[:k] if hasattr(v, "__len__") and not isinstance(v, (str, dict)) and len(v) == n else v)
                                 for kk, v in res.F.items()},
                              rows={kk: v[:k] for kk, v in res.rows.items()}, events=[])
        part = arm_h3.evaluate(cut, mc)
        assert part["exec_buy"] == full["exec_buy"][:k] and part["exec_sell"] == full["exec_sell"][:k]
    assert sum(full["exec_buy"]) + sum(full["exec_sell"]) > 0, "the synthetic series should produce some H3 signals"


def test_own_freeze_key_and_manifest(tmp_path):
    ek = holdout.freeze_key(DEFAULT)
    k = arm_h3.freeze_key(ek)
    assert k.startswith(ek + ":") and len(k.split(":")) == 3
    assert "arm_h3.py" not in holdout.ENGINE_SOURCES
    t0 = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)
    m1 = holdout.load_or_freeze_arm(str(tmp_path), "h3", k, t0)
    m2 = holdout.load_or_freeze_arm(str(tmp_path), "h3", k, t0 + timedelta(hours=5))
    assert m1["freeze_utc"] == m2["freeze_utc"] == t0.isoformat() and m2["status"] == "ACTIVE"
    assert (tmp_path / "holdout" / "manifest_h3.json").exists()


def test_structure_and_setup_alerts_are_information_only():
    p = {"meta": {"tf": "1h"}, "decisions": [],
         "markers": [{"t": 10, "type": "BOS", "dir": 1}, {"t": 10, "type": "SWEEP", "dir": -1}, {"t": 5, "type": "MSS", "dir": 1}],
         "h3": {"signals": [{"t": 12, "dir": "LONG", "entry": 4100.0, "sl": 4090.0, "tp1": 4110.0, "tp2": 4120.0}]}}
    lines = notify.messages(p, 6)
    assert lines == ["XAUUSD 1h BOS▲ SWEEP-HIGH | info, not a DECISION",
                     "XAUUSD 1h H3 BUY entry 4100.00 SL 4090.00 TP1 4110.00 TP2 4120.00 | info, not a DECISION"]
