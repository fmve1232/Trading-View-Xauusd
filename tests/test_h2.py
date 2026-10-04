"""Arm H2 "Sweep and Value" (audit/PREREGISTRATION.md Amendment 5): the rules as written,
no look-ahead, its own freeze key, and the report payload it feeds."""
import json
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantum import arm_h2, engine, holdout, report
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic

NAN = math.nan


def _res(n=12, **over):
    """A minimal engine result: flat trend-up context, value area 2000-2010, swing low 1999."""
    idx = pd.date_range("2026-10-05 08:00", periods=n, freq="1h", tz="UTC")
    c = np.full(n, 2005.0); o = c.copy(); h = c + 1.0; l = c - 1.0
    F = {"index": idx, "o": o, "h": h, "l": l, "c": c, "ema20": np.full(n, 2004.0), "ema100": np.full(n, 2000.0),
         "ema200": np.full(n, 1990.0), "atr": np.full(n, 5.0), "session_quality": np.full(n, 60),
         "sess_spread": np.full(n, 0.3), "session_label": np.array(["LON"] * n), "mkt_regime": np.array(["NORMAL"] * n)}
    R = {"vpoc": [2008.0] * n, "vah": [2012.0] * n, "val": [2001.0] * n, "active_sup": [1999.0] * n, "active_res": [2015.0] * n}
    for k, v in over.items():
        (F if k in F else R)[k] = v
    return SimpleNamespace(F=F, rows=R, events=[])


def _long_setup(res, j=6, i=7):
    F = res.F
    F["l"][j], F["c"][j], F["h"][j] = 1997.0, 2002.0, 2003.0      # wick below swing low 1999 and VAL 2001, close back above
    F["h"][i - 1] = 2003.0
    F["c"][i], F["h"][i] = 2004.0, 2004.5                         # close above the previous bar's high: confirmation
    return res


def test_long_signal_and_plan_follow_the_written_rules():
    ev = arm_h2.evaluate(_long_setup(_res()))
    assert [i for i, x in enumerate(ev["exec_buy"]) if x] == [7] and not any(ev["exec_sell"])
    # stop = min(low[6..7]) - 0.1 ATR = 1997 - 0.5; R = 2004 - 1996.5 = 7.5
    assert ev["plan_sl"][7] == pytest.approx(1996.5)
    # POC 2008 is only 4 away (< 1R) -> TP1 = entry + 1R = 2011.5; TP2 = nearer of VAH 2012 / swing high 2015 above TP1
    assert ev["plan_tp1"][7] == pytest.approx(2011.5) and ev["plan_tp2"][7] == pytest.approx(2012.0)
    assert ev["sweep_bar"][7] == 6


@pytest.mark.parametrize("breaker", ["trend", "value", "confirmation", "session", "stale"])
def test_each_rule_is_required(breaker):
    r = _long_setup(_res())
    # each rule is broken on every bar of the window (6..9), since a later bar may still confirm
    if breaker == "trend":
        r.F["ema20"][6:] = 1999.0                                 # EMA20 below EMA100
    elif breaker == "value":
        r.rows["val"] = [1996.0] * 12                             # the sweep low 1997 is above VAL
    elif breaker == "confirmation":
        r.F["c"][7:], r.F["h"][7:] = 2002.5, 2003.0               # never closes above the previous high
    elif breaker == "session":
        r.F["session_quality"][6:] = 20
    elif breaker == "stale":                                      # sweep 4 bars before the confirmation
        r = _res(); r.F["l"][3], r.F["c"][3] = 1997.0, 2002.0; r.F["h"][6] = 2003.0; r.F["c"][7], r.F["h"][7] = 2004.0, 2004.5
    assert not any(arm_h2.evaluate(r)["exec_buy"])


def test_one_signal_per_sweep_and_pool_sweep_events_count():
    r = _long_setup(_res())
    r.F["c"][8], r.F["h"][8] = 2005.0, 2005.5                     # a second confirming bar for the same sweep
    assert sum(arm_h2.evaluate(r)["exec_buy"]) == 1
    r2 = _res(); r2.rows["active_sup"] = [NAN] * 12               # no swing level: only the engine's PDL/PWL/PML sweep
    r2.F["l"][6], r2.F["c"][6], r2.F["h"][6] = 2000.0, 2002.0, 2003.0
    r2.F["c"][7], r2.F["h"][7] = 2004.0, 2004.5
    assert not any(arm_h2.evaluate(r2)["exec_buy"])
    r2.events = [{"type": "SWEEP", "dir": 1, "i": 6}]
    assert arm_h2.evaluate(r2)["exec_buy"][7] == 1


def test_short_is_the_mirror():
    r = _res(ema20=np.full(12, 1996.0), ema100=np.full(12, 2000.0), ema200=np.full(12, 2010.0))
    r.rows.update(vah=[2009.0] * 12, val=[1995.0] * 12, vpoc=[2001.0] * 12, active_res=[2011.0] * 12, active_sup=[1990.0] * 12)
    F = r.F
    F["h"][6], F["c"][6], F["l"][6] = 2013.0, 2008.0, 2007.0      # wick above swing high 2011 and VAH 2009, close back below
    F["l"][6] = 2007.0
    F["c"][7], F["l"][7] = 2006.0, 2005.5                         # close below the previous low 2007
    ev = arm_h2.evaluate(r)
    assert ev["exec_sell"][7] == 1 and not any(ev["exec_buy"])
    assert ev["plan_sl"][7] == pytest.approx(2013.5)              # max(high[6..7]) + 0.1 ATR


def test_no_lookahead():
    rng = np.random.default_rng(3)
    n = 400
    base = _res(n)
    walk = 2000 + np.cumsum(rng.normal(0, 2, n))
    base.F.update(c=walk, o=walk - rng.normal(0, 1, n), h=walk + abs(rng.normal(1, 1, n)), l=walk - abs(rng.normal(1, 1, n)),
                  ema20=walk - 1, ema100=walk - 3, ema200=walk - 8)
    base.rows.update(val=list(walk - 2), vah=list(walk + 6), vpoc=list(walk + 2), active_sup=list(walk - 1.5), active_res=list(walk + 9))
    full = arm_h2.evaluate(base)
    for k in (150, 260, 399):
        cut = SimpleNamespace(F={kk: (v[:k] if hasattr(v, "__len__") and len(v) == n else v) for kk, v in base.F.items()},
                              rows={kk: v[:k] for kk, v in base.rows.items()}, events=[])
        part = arm_h2.evaluate(cut)
        assert part["exec_buy"] == full["exec_buy"][:k] and part["exec_sell"] == full["exec_sell"][:k]
    assert sum(full["exec_buy"]) + sum(full["exec_sell"]) > 0, "the random walk should produce some H2 signals"


def test_own_freeze_key_and_manifest(tmp_path):
    ek = holdout.freeze_key(DEFAULT)
    k = arm_h2.freeze_key(ek)
    assert k.startswith(ek + ":") and len(k.split(":")) == 3
    assert "arm_h2.py" not in holdout.ENGINE_SOURCES and "report.py" not in holdout.ENGINE_SOURCES
    t0 = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)
    m1 = holdout.load_or_freeze_arm(str(tmp_path), "h2", k, t0)
    m2 = holdout.load_or_freeze_arm(str(tmp_path), "h2", k, t0 + timedelta(hours=5))
    assert m1["freeze_utc"] == m2["freeze_utc"] == t0.isoformat() and m2["status"] == "ACTIVE"
    m3 = holdout.load_or_freeze_arm(str(tmp_path), "h2", k + "x", t0 + timedelta(days=1))
    assert m3["status"] == "RESET" and m3["history"][0]["freeze_key"] == k
    assert (tmp_path / "holdout" / "manifest_h2.json").exists()


def test_report_payload_has_h2_and_second_based_forming_time():
    m = load_synthetic("1h", bars=900, seed=11)
    res = engine.run(m, DEFAULT, "treatment")
    now = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)
    man = {"freeze_key": holdout.freeze_key(DEFAULT), "freeze_utc": now.isoformat(), "status": "ACTIVE"}
    p = report.build(m, res, None, DEFAULT, man, now, None)
    h = p["h2"]
    assert "error" not in h and len(h["rules"]) == 5 and set(h["checklist"]) == {"long", "short"}
    assert all(abs(s["t"] - p["chart"]["t"][-1]) < 10 ** 10 for s in h["signals"]), "signal times are epoch seconds"
    if p["meta"].get("forming"):
        assert p["meta"]["forming"]["t"] < 10 ** 10, "forming bar time is epoch seconds, not nanoseconds"
    json.dumps(p, allow_nan=False)
