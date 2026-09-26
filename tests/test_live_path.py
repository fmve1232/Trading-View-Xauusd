"""The live download/assembly path, with the network replaced by fakes shaped like the real
responses (Yahoo intraday = bar-open timestamps, Yahoo daily = midnight trade dates, FRED =
observation dates, CFTC = release-time index). Catches assembly bugs before the first real run."""
import numpy as np
import pandas as pd
import pytest

from quantum import pipeline
from quantum.data import market as mk
from quantum.data import sources


END = pd.Timestamp("2026-09-24 20:00", tz="UTC")


def _bars(start, periods, freq, px, seed):
    idx = mk._trading_index(start, periods, freq)
    idx = idx[idx <= END]
    return mk._gbm(idx, px, 0.001, np.random.default_rng(seed))


@pytest.fixture
def fake_net(monkeypatch):
    cache = {}

    def yahoo(symbol, interval, rng):
        if symbol == "XAUUSD=X":
            raise sources.FetchError("yahoo XAUUSD=X: no bars")      # spot unavailable -> futures fallback
        key = (symbol, interval)
        if key not in cache:
            base = {"GC=F": 2650.0, "SI=F": 31.0, "DX-Y.NYB": 104.0, "^TNX": 4.3, "EURUSD=X": 1.08, "^GSPC": 5900.0, "^VIX": 16.0}[symbol]
            seed = abs(hash(key)) % 1000
            if interval == "1d":
                d = _bars("2023-01-02", 1400, "1D", base, seed)
                d.index = d.index.normalize()
                d = d[d.index.dayofweek < 5]
            elif interval == "60m":
                d = _bars("2025-06-01", 12000, "60min", base, seed)
            else:
                mins = int(interval[:-1])
                d = _bars("2026-07-27", int(60 * 24 * 60 / mins), f"{mins}min", base, seed)
            cache[key] = d
        return cache[key]

    def fred(sid):
        idx = pd.date_range("2024-01-01", "2026-09-01", freq="B", tz="UTC")
        return pd.Series(np.linspace(4.5, 3.8, len(idx)), index=idx)

    def cot():
        rel = pd.date_range("2024-01-05", "2026-09-25", freq="W-FRI", tz="UTC") + pd.Timedelta(hours=19, minutes=30)
        n = len(rel)
        return pd.DataFrame({"nc_long": np.linspace(2e5, 3e5, n), "nc_short": np.linspace(8e4, 5e4, n),
                             "open_interest": 4.5e5 + np.sin(np.arange(n)) * 1e4,
                             "asof": (rel - pd.Timedelta(days=3)).tz_localize(None).normalize()}, index=rel)

    monkeypatch.setattr(sources, "yahoo", yahoo)
    monkeypatch.setattr(sources, "fred", fred)
    monkeypatch.setattr(sources, "cftc_gold_cot", cot)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)


def test_live_pipeline_offline(fake_net, tmp_path):
    out, store = tmp_path / "out", tmp_path / "store"
    rc = pipeline.main(["--out", str(out), "--store", str(store), "--tfs", "15m,4h"])
    assert rc == 0
    import json
    ix = json.loads((out / "index.json").read_text())
    assert not ix["errors"], ix["errors"]
    p = json.loads((out / "15m.json").read_text())
    assert p["meta"]["price_source"] == "yahoo:GC=F" and not p["meta"]["synthetic"]
    st = {s["name"]: s for s in p["data_status"]}
    assert st["GC=F_15m"]["ok"] and not st["XAUUSD=X_15m"]["ok"]
    assert p["macro"]["gc"]["enabled"] is False            # price IS futures: confirmation layer off
    assert p["macro"]["DXY"]["valid"] and p["macro"]["cot"]["valid"]
    assert (store / "holdout_manifest.json").exists()
    assert any(d.name.startswith("GC_F_15m") for d in store.iterdir())
    # a second run merges into the store instead of duplicating it
    assert pipeline.main(["--out", str(out), "--store", str(store), "--tfs", "15m"]) == 0
    df = mk.store.load(str(store), "GC=F_15m")
    assert df.index.is_unique
