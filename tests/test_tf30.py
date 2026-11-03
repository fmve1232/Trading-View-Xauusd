"""The 30-minute timeframe (audit/PREREGISTRATION.md Amendment 15): the only engine change is a table entry and its
data maps. The four existing timeframes are pinned, the 30m engine output has no look-ahead, its data comes from
Twelve Data '30min' with the Sunday-reopen repair applied, and it reaches the alerts and the workflow."""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from quantum import config, engine, notify
from quantum.data import market as mk
from quantum.data import sources


def test_30m_is_added_and_the_other_timeframes_are_unchanged():
    assert config.TIMEFRAMES["30m"] == {"sec": 1800, "yahoo": "30m", "range": "60d"}
    assert {k: v for k, v in config.TIMEFRAMES.items() if k != "30m"} == {
        "5m": {"sec": 300, "yahoo": "5m", "range": "60d"},
        "15m": {"sec": 900, "yahoo": "15m", "range": "60d"},
        "1h": {"sec": 3600, "yahoo": "60m", "range": "730d"},
        "4h": {"sec": 14400, "yahoo": "60m", "range": "730d", "resample_from": "1h"},
    }
    assert config.ENGINE_VERSION == "Q7.2-web.8"
    assert notify.TF_SEC["30m"] == 1800


@pytest.fixture(scope="module")
def m30():
    return mk.load_synthetic("30m", bars=2600, seed=11)


def test_engine_runs_on_30m_bars_without_look_ahead(m30):
    ix = m30.base.index
    assert m30.tf_sec == 1800 and (ix.minute % 30 == 0).all() and (ix.second == 0).all()
    assert engine.outcome_n_for(1800) == 3 and engine.hist_max_for(1800) == 4500
    res = engine.run(m30, config.DEFAULT)
    k = 2300
    r2 = engine.run(dataclasses.replace(m30, base=m30.base.iloc[:k]), config.DEFAULT)
    for key in ("bull", "bear", "tq", "plan_sl", "plan_tp1", "cal_p_long", "struct"):
        a, b = res.rows[key][:k], r2.rows[key]
        assert np.allclose(np.nan_to_num(a, nan=-9), np.nan_to_num(b, nan=-9)), key
    assert list(res.rows["exec_buy"][:k]) == list(r2.rows["exec_buy"])


def _bars(freq, n=400, start="2026-10-05 00:00"):
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    c = 4000 + np.cumsum(np.random.default_rng(3).normal(0, 1, n))
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 0.0}, index=idx)


def test_30m_data_is_twelve_data_30min_with_the_reopen_repair(monkeypatch):
    asked, repaired = [], []
    freq = {"5min": "5min", "15min": "15min", "30min": "30min", "1h": "60min", "1day": "1D"}

    def td(sym, interval, key, outputsize=5000):
        asked.append(interval)
        return _bars(freq[interval])

    def boom(*a, **k):
        raise sources.FetchError("offline")

    real = sources.repair_reopen

    def rr(df, sec, m5=None):
        repaired.append(sec)
        return real(df, sec, m5) if m5 is not None or sec == 300 else df

    monkeypatch.setenv("TWELVEDATA_API_KEY", "test")
    monkeypatch.setattr(sources, "twelvedata", td)
    for nm in ("yahoo", "fred", "cftc_gold_cot"):
        monkeypatch.setattr(sources, nm, boom)
    monkeypatch.setattr(sources, "repair_reopen", rr)
    dl = mk.download_all(None, ("15m", "30m", "5m", "60m"))
    assert asked == ["15min", "30min", "5min", "1h", "1day"]                # one more call per run: 5, not 4
    assert dl.price_source == "twelvedata:XAU/USD" and "30m" in dl.prim
    assert sorted(repaired) == [300, 900, 1800, 3600]                      # 30m gets the reopen repair like 15m / 1h


def test_the_site_workflow_runs_30m():
    with open(".github/workflows/quantum-site.yml") as f:
        wf = f.read()
    assert "--tfs 15m,30m,1h,4h,5m" in wf
    with open("site/app.js") as f:
        js = f.read()
    assert 'const TFS = ["5m", "15m", "30m", "1h", "4h"];' in js and '"30m": 1800' in js
