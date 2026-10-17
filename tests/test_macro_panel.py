"""Macro panel (display only): correlation on shared bars, the gold implication, failures reported."""
import json

import numpy as np
import pandas as pd

from quantum import holdout, macro_panel


def _frame(vals, start="2026-10-12 00:00"):
    idx = pd.date_range(start, periods=len(vals), freq="15min", tz="UTC")
    v = np.asarray(vals, float)
    return pd.DataFrame({"open": v, "high": v, "low": v, "close": v, "volume": 0.0}, index=idx)


def test_outside_the_freeze_key():
    assert "macro_panel.py" not in holdout.ENGINE_SOURCES


def test_correlation_uses_shared_bars_only():
    rng = np.random.default_rng(1)
    g = 4000 + np.cumsum(rng.normal(0, 2, 200))
    gold = pd.Series(g, index=_frame(g).index)
    inv = _frame(100 - (g - 4000) * 0.01)["close"]           # moves exactly against gold
    r, n = macro_panel.correlation(inv, gold)
    assert r < -0.99 and n == 96
    shifted = inv.copy(); shifted.index = shifted.index + pd.Timedelta(minutes=7)   # no common bars
    assert macro_panel.correlation(shifted, gold) == (None, 0)


def test_gold_implication_measured_then_textbook():
    assert macro_panel.implication(+0.5, -0.6, -1) == {"gold": -1, "basis": "measured r -0.60"}     # DXY up, r<0 -> red
    assert macro_panel.implication(-0.5, -0.6, -1)["gold"] == 1                                    # DXY down -> green
    assert macro_panel.implication(+0.5, +0.05, -1) == {"gold": -1, "basis": "textbook relation (measured r weak)"}
    assert macro_panel.implication(+1.0, None, +1)["gold"] == 1                                    # oil up -> green
    assert macro_panel.implication(0.0, -0.9, -1)["gold"] == 0
    # Bitcoin: no textbook relation, so only a clear measured r colours it
    assert macro_panel.implication(+500.0, 0.1, 0) == {"gold": 0, "basis": "no established relation (measured r weak)"}
    assert macro_panel.implication(+500.0, 0.4, 0)["gold"] == 1


def test_build_reports_each_instrument_and_never_raises(tmp_path):
    rng = np.random.default_rng(2)
    g = 4000 + np.cumsum(rng.normal(0, 2, 300))
    chart = tmp_path / "15m.json"
    t = [int(x.timestamp()) for x in _frame(g).index]
    chart.write_text(json.dumps({"chart": {"t": t, "c": list(g)}}))

    def fetch(sym, interval, rng_):
        if sym == "CL=F":
            raise OSError("blocked")
        return _frame(100 + np.cumsum(np.random.default_rng(len(sym)).normal(0, 0.1, 300)))
    def fred(sid):
        if sid == "T10YIE":
            raise OSError("fred down")
        idx = pd.date_range("2026-06-01", periods=80, freq="B", tz="UTC")
        return pd.Series(1.8 + np.arange(80) * 0.01, index=idx)                   # steadily rising
    out = macro_panel.build(str(chart), fetch=fetch, fetch_daily=fred)
    keys = {it["key"]: it for it in out["items"]}
    assert set(keys) == {"DXY", "EURUSD", "JPYUSD", "US10Y", "WTI", "BTC", "REALYLD", "BREAKEVEN", "US2Y"}
    ry = keys["REALYLD"]
    assert ry["ok"] and ry["daily"] and ry["trend"] == 1 and ry["gold"] == -1 and ry["corr"] is None   # real yield rising: gold down
    assert keys["US2Y"]["gold"] == -1 and not keys["BREAKEVEN"]["ok"] and "fred down" in keys["BREAKEVEN"]["note"]
    assert not keys["WTI"]["ok"] and "blocked" in keys["WTI"]["note"]
    d = keys["DXY"]
    assert d["ok"] and len(d["spark"]["v"]) == 192 and len(d["spark"]["gold"]) == 192 and d["gold"] in (-1, 0, 1)
    assert abs(d["change"] - (d["last"] - d["ref"])) < 1e-3


def test_small_prices_keep_their_precision():
    v = 0.0065 + np.arange(200) * 1e-7                      # JPY/USD-sized values
    it = macro_panel.item("JPYUSD", "JPY / USD", "JPYUSD=X", 1, "", 6, _frame(v), None)
    assert it["last"] == round(v[-1], 8) and it["change"] != 0 and abs(it["change"] - (it["last"] - it["ref"])) < 1e-9
    assert len(set(it["spark"]["v"])) > 100


def test_live_yield_bridge_recovers_the_slope_and_rejects_bad_fits():
    rng = np.random.default_rng(3)
    dp = rng.normal(0, 0.05, 400)
    dp[200] = 2.5                                           # a contract roll: dropped, not fitted
    p = 112 + np.cumsum(dp)
    y = 4.1 + np.cumsum(-0.14 * np.where(np.abs(dp) > 1, 0, dp) + rng.normal(0, 0.001, 400))
    b = macro_panel.bridge(_frame(y)["close"], _frame(p)["close"])
    assert b["ok"] and abs(b["beta"] + 0.14) < 0.01 and b["r2"] > 0.9 and b["n"] == 398
    assert not macro_panel.bridge(_frame(y)["close"], _frame(112 - (p - 112))["close"])["ok"]   # wrong sign
    assert not macro_panel.bridge(_frame(y[:30])["close"], _frame(p[:30])["close"])["ok"]       # too few bars


def test_live_bridge_anchors_on_the_last_completed_bar():
    dp = np.random.default_rng(5).normal(0, 0.05, 100)
    p, y = _frame(112 + np.cumsum(dp)), _frame(4.1 - 0.14 * np.cumsum(dp))
    L = macro_panel.live_bridge(y, "ZN=F", lambda s, i, r: p)
    assert L["ok"] and L["anchor_v"] == round(float(y["close"].iloc[-2]), 5)
    assert L["anchor_t"] == int(y.index[-2].timestamp()) + 900
    assert macro_panel.live_bridge(y, "ZN=F", lambda s, i, r: (_ for _ in ()).throw(OSError("blocked")))["ok"] is False
