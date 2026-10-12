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
    out = macro_panel.build(str(chart), fetch=fetch)
    keys = {it["key"]: it for it in out["items"]}
    assert set(keys) == {"DXY", "USDJPY", "US10Y", "WTI"}
    assert not keys["WTI"]["ok"] and "blocked" in keys["WTI"]["note"]
    d = keys["DXY"]
    assert d["ok"] and len(d["spark"]["v"]) == 192 and len(d["spark"]["gold"]) == 192 and d["gold"] in (-1, 0, 1)
    assert abs(d["change"] - (d["last"] - d["ref"])) < 1e-3
