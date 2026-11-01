"""High-confidence confirmation (quantum/confirm.py): data quality and the nine-layer approval.
Brief section 13: 1 stale data, 2 missing candles, 3 duplicates, 4 timestamps, 5 rate limits, 6-7 primary and fallback
failure, 12 spread / cost limit, 14 news, 15 conflicting timeframes, 16 sideways, 17 volatility expansion,
22 insufficient observations, 23 calibration (model not validated), 26 missing risk limits, 27 invalid prices,
29 out-of-order data; plus the futures-fallback block and the rule that nothing is CONFIRMED without a validated model."""
import itertools
import json
import random
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantum import confirm, pipeline
from quantum.data import market as mk
from quantum.data import sources, store
from tests.test_live_path import fake_net  # noqa: F401  (pytest fixture)

NOW = datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc)          # Wednesday 10:00 New York: market open


def _market(n=400, end="2026-10-28 13:45", tf="15min", sec=900, src="twelvedata:XAU/USD", synthetic=False, status=None):
    idx = pd.date_range(end=end, periods=n * 2, freq=tf, tz="UTC")
    idx = idx[~sources.gold_shut(idx)][-n:]
    c = 4000 + np.cumsum(np.sin(np.arange(len(idx))) * 0.5)
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.3, "low": np.minimum(o, c) - 0.3, "close": c, "volume": 0.0}, index=idx)
    return SimpleNamespace(base=df, tf_sec=sec, price_source=src, status=status or {}, synthetic=synthetic)


def _ids(dq, ok=False):
    return {c["id"] for c in dq["checks"] if c["ok"] is ok}


def test_clean_data_is_ok():
    dq = confirm.data_quality(_market(), NOW)
    assert dq["status"] == "OK" and dq["market_open"] and not dq["reasons"]


def test_stale_data_blocks_while_the_market_is_open():
    dq = confirm.data_quality(_market(), datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc))
    assert dq["status"] == "UNAVAILABLE" and "fresh" in _ids(dq)


def test_market_closed_is_not_stale_but_cannot_trade():
    m = _market(end="2026-10-30 20:45")                              # Friday close
    dq = confirm.data_quality(m, datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc))
    assert not dq["market_open"] and "fresh" not in _ids(dq) and dq["status"] == "OK"
    out = confirm.approve({**_x(), "data": dq, "market_open": False})
    assert out["status"] == "NO TRADE" and out["layers"][0]["detail"] == "market closed"


@pytest.mark.parametrize("mutate, check", [
    (lambda df: pd.concat([df, df.iloc[[-1]]]), "duplicates"),
    (lambda df: df.iloc[list(range(len(df) - 3)) + [len(df) - 2, len(df) - 3, len(df) - 1]], "order"),
    (lambda df: df.set_axis(df.index[:-1].append(pd.DatetimeIndex([df.index[-1] + pd.Timedelta(seconds=60)]))), "grid"),
    (lambda df: df.assign(close=np.r_[df["close"].to_numpy()[:-1], 0.0]), "prices"),
    (lambda df: df.assign(high=np.r_[df["high"].to_numpy()[:-1], np.nan]), "prices"),
    (lambda df: df.drop(df.index[-5:-3]), "missing_recent"),
])
def test_bad_bars_block(mutate, check):
    m = _market()
    m.base = mutate(m.base)
    dq = confirm.data_quality(m, NOW)
    assert dq["status"] == "UNAVAILABLE" and check in _ids(dq), dq["reasons"]


def test_older_holes_degrade_and_market_shut_gaps_do_not_count():
    m = _market()
    assert "missing_older" not in _ids(confirm.data_quality(m, NOW))   # the window spans daily breaks: explained
    m.base = m.base.drop(m.base.index[-150:-148])
    dq = confirm.data_quality(m, NOW)
    assert dq["status"] == "DEGRADED" and "missing_older" in _ids(dq)


def test_a_bar_that_has_not_closed_blocks():
    dq = confirm.data_quality(_market(end="2026-10-28 14:00"), NOW)
    assert dq["status"] == "UNAVAILABLE" and "closed" in _ids(dq)


@pytest.mark.parametrize("src, status, expect", [
    ("yahoo:GC=F", None, "UNAVAILABLE"),                              # futures: a different instrument
    ("yahoo:XAUUSD=X", None, "DEGRADED"),                             # spot fallback
    ("twelvedata:XAU/USD", {"XAU/USD_15m": SimpleNamespace(source="store (live fetch failed)")}, "DEGRADED"),
])
def test_sources_and_fallbacks_are_named(src, status, expect):
    assert confirm.data_quality(_market(src=src, status=status), NOW)["status"] == expect


def test_synthetic_data_blocks():
    assert confirm.data_quality(_market(synthetic=True), NOW)["status"] == "UNAVAILABLE"


# ---------------- approval ----------------
def _x(**kw):
    x = {"data": {"status": "OK", "reasons": []}, "market_open": True, "regime": "STRONG TR", "signal": {"dir": 1, "bars_since": 0},
         "htf": {"4H": 1, "1H": 1}, "profile": {"tp": 10.0, "sl": 10.0}, "level_ahead": None, "cost_px": 0.8, "atr": 6.0,
         "news": {"in_window": False}, "risk_lock": False, "race": {"n": 400, "win": 380, "random": 0.5}, "model": {"validated": False},
         "target": 0.9}
    x.update(kw)
    return x


def _state(out, i):
    return next(lay["state"] for lay in out["layers"] if lay["id"] == i)


@pytest.mark.parametrize("kw, status, layer", [
    ({"data": {"status": "UNAVAILABLE", "reasons": ["x"]}}, "DATA UNAVAILABLE", 1),
    ({"signal": {"dir": 0, "bars_since": 0}}, "WAIT FOR CONFIRMATION", 3),
    ({"signal": {"dir": 1, "bars_since": 2}}, "NO TRADE", 4),
    ({"news": {"in_window": True}}, "NO TRADE", 7),
    ({"cost_px": 2.0}, "NO TRADE", 7),                                # 33% of 1 ATR
    ({"risk_lock": True}, "NO TRADE", 8),
    ({"risk_lock": None}, "NO TRADE", 8),                             # missing risk limits
    ({}, "MODEL NOT VALIDATED", 6),
])
def test_each_layer_rejects_with_its_reason(kw, status, layer):
    out = confirm.approve(_x(**kw))
    assert out["status"] == status
    assert _state(out, layer) in ("fail", "wait", "not_validated")
    assert any(r.startswith(f"L{layer} ") for r in out["reasons"])


def test_validated_model_needs_evidence_and_the_lower_bound():
    v = {"validated": True}
    assert confirm.approve(_x(model=v, race={"n": 100, "win": 99, "random": 0.5}))["status"] == "INSUFFICIENT EVIDENCE"
    assert confirm.approve(_x(model=v, race={"n": 400, "win": 352, "random": 0.5}))["status"] == "NO TRADE"   # 88%: lower bound < 90%
    pt = confirm.approve(_x(model=v, race={"n": 200, "win": 184, "random": 0.5}))   # 92% point estimate, lower bound 87.5%
    assert pt["probability"]["p"] > 0.9 > pt["probability"]["lo"] and pt["status"] == "NO TRADE"
    ok = confirm.approve(_x(model=v, race={"n": 400, "win": 384, "random": 0.5}))                              # 96%: lower bound 93.6%
    assert ok["status"] == "CONFIRMED BUY" and ok["probability"]["lo"] > 0.9
    assert confirm.approve(_x(model=v, race={"n": 400, "win": 384}, signal={"dir": -1, "bars_since": 0}))["status"] == "CONFIRMED SELL"


def test_warnings_do_not_reject_without_evidence():
    v = {"validated": True}
    good = {"n": 400, "win": 384, "random": 0.5}
    conflict = confirm.approve(_x(model=v, race=good, htf={"4H": -1, "1H": -1}))                 # 15: conflicting timeframes
    assert _state(conflict, 3) == "warn" and conflict["status"] == "CONFIRMED BUY"
    abn = confirm.approve(_x(model=v, race=good, regime="ABNORMAL"))                             # 17: volatility expansion
    assert _state(abn, 2) == "warn" and abn["status"] == "CONFIRMED BUY"
    rng = confirm.approve(_x(model=v, race=good, regime="RANGE"))                                # 16: sideways
    assert _state(rng, 2) == "info"
    near = confirm.approve(_x(model=v, race=good, level_ahead={"name": "PDH", "dist": 4.0}))
    assert _state(near, 5) == "warn" and "PDH" in next(lay["detail"] for lay in near["layers"] if lay["id"] == 5)


def test_nothing_is_confirmed_without_a_validated_model():
    rnd = random.Random(5)
    for _ in range(600):
        x = _x(signal={"dir": rnd.choice([-1, 0, 1]), "bars_since": rnd.choice([0, 0, 1])}, regime=rnd.choice(["RANGE", "ABNORMAL", "STRONG TR"]),
               htf={"4H": rnd.choice([-1, 0, 1, None]), "1H": rnd.choice([-1, 0, 1, None])}, cost_px=rnd.uniform(0.1, 3), atr=rnd.uniform(1, 12),
               news={"in_window": rnd.random() < 0.2}, risk_lock=rnd.choice([False, False, True, None]),
               race={"n": rnd.randint(0, 3000), "win": 0} if rnd.random() < 0.5 else None, profile={"tp": rnd.choice([10, 15, 20]), "sl": 10})
        if x["race"]:
            x["race"]["win"] = int(x["race"]["n"] * rnd.random())
        assert not confirm.approve(x)["status"].startswith("CONFIRMED")


def test_levels_and_race_cell_lookup():
    R = {"pdh": np.array([4010.0]), "pdl": np.array([3990.0]), "vah": np.array([np.nan])}
    lv = confirm.levels(R, {"res": [{"price": 4004.0}], "sup": [{"price": 3998.0}]}, 0, 4000.0)
    assert lv["above"][0] == {"name": "S/R", "dist": 4.0} and lv["below"][0] == {"name": "S/R", "dist": 2.0}
    assert confirm.level_ahead(lv, 1)["dist"] == 4.0 and confirm.level_ahead(lv, -1)["dist"] == 2.0 and confirm.level_ahead(lv, 0) is None
    race = {"tp_grid": [10.0, 20.0], "sl_grid": [10.0], "random": {"long": {"n": 10, "win": [[6], [3]]}, "short": {"n": 10, "win": [[4], [2]]}},
            "sources": [{"key": "engine", "n": 5, "long": 4, "short": 1, "win": [[3], [1]], "sample": "in-sample"}]}
    assert confirm.race_cell(race, 10.0, 10.0, d=1) == {"n": 5, "win": 3, "random": 0.6, "sample": "in-sample"}
    assert confirm.race_cell(race, 10.0, 10.0, d=0)["random"] == pytest.approx((4 * 0.6 + 1 * 0.4) / 5)
    assert confirm.race_cell(race, 12.5, 10.0) is None and confirm.race_cell({"error": "x"}, 10.0, 10.0) is None


# ---------------- end to end and the API layer ----------------
def test_futures_fallback_reaches_the_panel_as_data_unavailable(fake_net, tmp_path):  # noqa: F811
    out, st = tmp_path / "out", tmp_path / "store"
    assert pipeline.main(["--out", str(out), "--store", str(st), "--tfs", "15m"]) == 0
    p = json.loads((out / "15m.json").read_text())
    hc = p["hc"]
    assert "error" not in hc and hc["data"]["status"] == "UNAVAILABLE"
    assert any("FUTURES" in r for r in hc["data"]["reasons"])
    assert {v["status"] for v in hc["profiles"].values()} <= {"DATA UNAVAILABLE"}
    assert set(hc["profiles"]) == {"A", "B", "C"} and hc["model"]["validated"] is False


class _Resp:
    def __init__(self, code):
        self.status_code = code


def test_rate_limits_retry_with_backoff_and_client_errors_do_not(monkeypatch):
    calls, sleeps = [], []
    seq = iter([429, 503, 200])
    monkeypatch.setattr(sources, "requests", SimpleNamespace(get=lambda *a, **k: calls.append(1) or _Resp(next(seq))))
    monkeypatch.setattr(sources.time, "sleep", lambda s: sleeps.append(s))
    assert sources._get("https://example.test").status_code == 200
    assert len(calls) == 3 and sleeps == [1, 2]
    calls.clear()
    monkeypatch.setattr(sources, "requests", SimpleNamespace(get=lambda *a, **k: calls.append(1) or _Resp(403)))
    with pytest.raises(sources.FetchError):
        sources._get("https://example.test")
    assert len(calls) == 1                                           # a 4xx is not retried


def test_network_errors_give_up_after_the_last_try(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise ConnectionError("down")
    monkeypatch.setattr(sources, "requests", SimpleNamespace(get=boom))
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    with pytest.raises(sources.FetchError):
        sources._get("https://example.test", tries=4)
    assert len(calls) == 4


def test_primary_failure_uses_the_named_fallback_and_total_failure_raises(fake_net, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test")
    monkeypatch.setattr(sources, "twelvedata", lambda *a, **k: (_ for _ in ()).throw(sources.FetchError("twelvedata: credits")))
    dl = mk.download_all(None, ("15m", "60m"))
    assert dl.price_source == "yahoo:GC=F"                             # spot also fails in the fixture -> futures, named
    assert "credits" in dl.status["XAU/USD_15m"].note
    monkeypatch.setattr(sources, "yahoo", lambda *a, **k: (_ for _ in ()).throw(sources.FetchError("yahoo down")))
    with pytest.raises(sources.FetchError):
        mk.download_all(None, ("15m", "60m"))


def test_store_merge_dedupes_newer_wins_and_sorts():
    idx = pd.date_range("2026-10-28 10:00", periods=4, freq="15min", tz="UTC")
    old = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    new = pd.DataFrame({"close": [30.0, 5.0]}, index=pd.DatetimeIndex([idx[2], idx[3] + pd.Timedelta(minutes=15)]))
    m = store.merge(old, new.iloc[::-1])
    assert m.index.is_unique and m.index.is_monotonic_increasing and m.loc[idx[2], "close"] == 30.0 and len(m) == 5


def test_payload_profiles_are_the_declared_ones():
    assert confirm.PROFILES == {"A": {"tp": 10.0, "sl": 10.0}, "B": {"tp": 15.0, "sl": 10.0}, "C": {"tp": 20.0, "sl": 10.0}}
    assert confirm.TARGET == 0.90 and confirm.MIN_EVIDENCE_N == 184 and confirm.MODEL["validated"] is False
    assert list(itertools.islice(confirm.PROFILES, 3)) == ["A", "B", "C"]
