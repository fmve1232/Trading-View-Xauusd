"""Phase B5c (quantum/research/b5c_dukascopy.py) on SYNTHETIC Dukascopy files and a mocked server. No network, no real
data. Checks: the .bi5 decoder, 15-minute sums (OFI, queue and tick imbalance), retries and the resumable cache, no
look-ahead, the unit check, and the full command end to end."""
import json
import lzma
import os

import numpy as np
import pandas as pd
import pytest

from quantum.research import b2, history
from quantum.research import b5c_dukascopy as C
from quantum.research import harness as H


def _bi5(rows):
    """rows: (ms, ask, bid, ask volume, bid volume) in Dukascopy units -> compressed .bi5 bytes."""
    return lzma.compress(b"".join(C.REC.pack(*r) for r in rows), format=lzma.FORMAT_ALONE)


class _Resp:
    def __init__(self, code, content=b""):
        self.status_code, self.content = code, content


def test_bi5_round_trip_and_empty_file():
    rows = [(10, 1850250, 1850100, 1.5, 2.25), (3_599_000, 1851000, 1850800, 0.5, 4.0)]
    t = C.parse_bi5(_bi5(rows))
    assert t.shape == (2, 5) and t[0].tolist() == [10, 1850250, 1850100, 1.5, 2.25] and t[1, 0] == 3_599_000
    assert C.parse_bi5(b"").shape == (0, 5)


def test_hour_bars_ofi_queue_and_tick_imbalance():
    h0 = pd.Timestamp("2021-03-01 10:00", tz="UTC")
    rows = [(1_000, 1000, 990, 5, 5),               # bar 0
            (2_000, 1010, 1000, 5, 5),               # bid and ask up: OFI +5 (new bid) +5 (old ask)
            (3_000, 1010, 1000, 5, 15),              # bid queue grows: OFI +15 -5 -5 +5
            (900_500, 1010, 1000, 0, 0),             # bar 1: no volume, q undefined (last tick)
            (2_700_000, 1000, 990, 8, 2)]            # bar 3: mid down
    s = C.hour_bars(C.parse_bi5(_bi5(rows)), h0)
    assert list(s.index) == [h0, h0 + pd.Timedelta(minutes=15), h0 + pd.Timedelta(minutes=45)]
    b0 = s.iloc[0]
    assert b0["n"] == 3 and b0["ofi"] == pytest.approx(10 + 10) and b0["up"] == 1 and b0["down"] == 0
    assert b0["qsum"] == pytest.approx(0 + 0 + 0.5) and b0["qn"] == 3 and b0["qlast"] == pytest.approx(0.5)
    assert b0["spread_sum"] == pytest.approx(30) and b0["mid_last"] == pytest.approx(1005)
    b1 = s.iloc[1]
    assert b1["qn"] == 0 and np.isnan(b1["qlast"])             # the last tick's q, not the last valid one
    assert s.iloc[2]["down"] == 1 and s.iloc[2]["qlast"] == pytest.approx(-0.6)


def test_fetch_retries_404_and_gives_up(monkeypatch):
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    t = pd.Timestamp("2021-03-01 10:00", tz="UTC")
    seen = []
    assert C.fetch_hour(t, lambda url, timeout: seen.append(url) or _Resp(404)) == b""
    assert seen[0].endswith("/XAUUSD/2021/02/01/10h_ticks.bi5")         # Dukascopy months count from 0
    codes = iter([503, 500, 200])
    assert C.fetch_hour(t, lambda url, timeout: _Resp(next(codes), b"x")) == b"x"

    def boom(url, timeout):
        raise ConnectionError("reset")
    assert C.fetch_hour(t, boom) is None


def test_days_cache_resume_and_saturdays(tmp_path, monkeypatch):
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    day = pd.Timestamp("2021-03-02", tz="UTC")
    good = _bi5([(1_000, 1000, 990, 5, 5)])
    calls = {"n": 0}

    def flaky(url, timeout):
        calls["n"] += 1
        return _Resp(500) if url.endswith("/13h_ticks.bi5") else _Resp(200, good)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as pool:
        df, m = C.load_day(day, str(tmp_path), pool, flaky)
        assert df is None and m["failed_hours"] == 1 and not (tmp_path / "days").exists()   # nothing cached
        df, m = C.load_day(day, str(tmp_path), pool, lambda url, timeout: _Resp(200, good))
        assert len(df) == 24 and m["hours"] == 24
        n = calls["n"]
        df2, m2 = C.load_day(day, str(tmp_path), pool, flaky)                            # from the cache
        assert calls["n"] == n and m2 == {"cached": 1}
        pd.testing.assert_frame_equal(df2, df, check_freq=False, check_dtype=False)
        sat, ms = C.load_day(pd.Timestamp("2021-03-06", tz="UTC"), str(tmp_path), pool, flaky)
        assert len(sat) == 0 and calls["n"] == n and ms["hours"] == 0
        bad, mb = C.load_day(pd.Timestamp("2021-03-03", tz="UTC"), str(tmp_path), pool, lambda url, timeout: _Resp(200, b"<html>"))
        assert bad is None and mb["failed_hours"] == 24                                   # not LZMA: retried next run


def _raw(bars=3000, seed=2, start="2021-01-04"):
    g = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=bars, freq="15min", tz="UTC")
    n = g.integers(20, 400, bars).astype(float)
    up = np.floor(n * g.uniform(0.3, 0.5, bars))
    return pd.DataFrame({"n": n, "ofi": g.normal(0, 40, bars), "depth": n * g.uniform(2, 6, bars), "qsum": g.normal(0, 3, bars),
                         "qn": n, "qlast": g.uniform(-1, 1, bars), "up": up, "down": np.floor(n * 0.4), "spread_sum": n * 300.0,
                         "mid_last": 1800_000.0 + np.cumsum(g.normal(0, 500, bars))}, index=idx)


def test_features_use_only_past_bars_and_scale():
    raw = _raw(4000)
    full = C.finish_features(raw, 1000.0)
    for k in (2500, 3700):
        part = C.finish_features(raw.iloc[:k], 1000.0)
        pd.testing.assert_frame_equal(part[list(C.MODEL_FEATURES)], full[list(C.MODEL_FEATURES)].iloc[:k], check_freq=False)
    assert full["spread"].iloc[0] == pytest.approx(0.3) and full["mid"].iloc[0] == pytest.approx(raw["mid_last"].iloc[0] / 1000)
    assert (full["timb15"].abs() <= 1).all() and full["ofi60"].iloc[3:].notna().all()


def test_unit_check_detects_the_scale_and_stops_on_a_mismatch():
    raw = _raw(500)
    m15 = pd.DataFrame({"close": raw["mid_last"] / 1000 + 0.2}, index=raw.index)
    scale, gap, rel = C.price_scale(raw, m15)
    assert scale == 1000.0 and gap == pytest.approx(0.2, abs=1e-6) and rel < 0.001
    m15_bad = m15 * 1.03
    scale, gap, rel = C.price_scale(raw, m15_bad)
    assert rel > C.ALIGN_MAX


def _spot(idx, seed=5):
    g = np.random.default_rng(seed)
    c = 1800 + np.cumsum(g.normal(0, 2.0, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + g.uniform(0, 1.5, len(c)),
                         "low": np.minimum(o, c) - g.uniform(0, 1.5, len(c)), "close": c, "volume": 0.0}, index=idx)


def test_main_end_to_end_with_a_mocked_dukascopy(tmp_path, monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 48)
    monkeypatch.setattr(H, "DEV", (pd.Timestamp("2021-01-04", tz="UTC"), pd.Timestamp("2021-02-18", tz="UTC")))
    idx = pd.date_range("2021-01-04", "2021-02-18", freq="15min", tz="UTC", inclusive="left")
    idx = idx[idx.dayofweek != 5]
    m15 = _spot(idx)
    monkeypatch.setattr(history, "load", lambda *a, **k: m15)
    close = m15["close"]
    g = np.random.default_rng(8)

    def fake_fetch(t, get=None):
        rows = []
        for q in range(4):
            bar = t + pd.Timedelta(minutes=15 * q)
            if bar not in close.index:
                continue
            mid = close[bar] * 1000
            for j in range(int(g.integers(3, 10))):           # tick counts vary, as in real data
                half = int(g.integers(100, 400))
                rows.append((q * 900_000 + j * 90_000 + 1, int(mid + half + g.integers(-80, 80)), int(mid - half + g.integers(-80, 80)),
                             float(g.uniform(1, 9)), float(g.uniform(1, 9))))
        return _bi5(rows) if rows else b""
    monkeypatch.setattr(C, "fetch_hour", fake_fetch)
    out, trials, cache = tmp_path / "r.json", tmp_path / "t.jsonl", tmp_path / "cache"
    argv = ["--cache", str(cache), "--out", str(out), "--trials", str(trials), "--spot", "unused", "--workers", "2"]
    assert C.main(argv) == 0
    r = json.loads(out.read_text())
    assert r["set"] == "B5c" and r["price_units_per_usd"] == 1000.0 and r["median_gap_usd"] < 0.5 and r["cost_usd"] == 0.0
    kinds = [t["kind"] for t in r["trials"]]
    assert kinds.count("rule") == 30 and kinds.count("model") == 3 and r["family"]["trials"] == 33
    assert "by_ofi15_decile" in r["execution"] and r["failed_days"] == 0
    assert r["integrity"]["failures"] == [] and r["integrity"]["best_lag_bars"] == 0 and (tmp_path / "r_integrity.json").exists()
    lines = [json.loads(x) for x in trials.read_text().splitlines()]
    assert len(lines) == 33 and all(x["phase"] == "B5c" and x["partition"] == "development" for x in lines)
    assert len(os.listdir(cache / "days")) > 40
    with pytest.raises(SystemExit, match="already exists"):
        C.main(argv)


def test_declared_constants():
    assert C.LAGS == (-2, -1, 0, 1, 2) and C.LAG_MIN_CORR == 0.8
    assert C.INSTRUMENT == "XAUUSD" and C.RULE_FEATURES == ("ofi15", "ofi60", "qimb15", "qlast", "timb15") and len(C.MODEL_FEATURES) == 8
    assert set(C.DIRECTIONAL) == set(C.MODEL_FEATURES) - {"ntr_z", "spread"} and C.Q2 == "ofi15" and C.ALIGN_MAX == 0.005
    assert [m.name for m in C.MODELS] == ["LOGIT"]


def test_lag_check_detects_a_shifted_clock():
    """Amendment A1: aligned bars peak at lag 0; a one-bar clock offset is detected and would stop the run."""
    idx = pd.date_range("2021-01-04", periods=3000, freq="15min", tz="UTC")
    m15 = _spot(idx)
    raw = pd.DataFrame({"mid_last": m15["close"] * 1000}, index=idx)
    ok = C.lag_check(raw, m15, 1000.0)
    assert ok["best_lag_bars"] == 0 and ok["corr_by_lag_bars"][0] > 0.99
    shifted = raw.copy()
    shifted.index = shifted.index + pd.Timedelta(minutes=15)                  # Dukascopy clock one bar late
    bad = C.lag_check(shifted, m15, 1000.0)
    assert bad["best_lag_bars"] != 0 and bad["corr_by_lag_bars"][0] < C.LAG_MIN_CORR


def test_hour_bars_integrity_counts_and_no_clamping():
    """Amendment A2: a tick stamped past its hour is counted and dropped (never clamped into the last bar); duplicate
    milliseconds, crossed quotes and the longest silence in a bar are counted."""
    rows = [(1_000, 2_000_500, 2_000_000, 1.0, 1.0), (1_000, 2_000_600, 2_000_100, 1.0, 1.0),       # duplicate ms
            (400_000, 2_000_000, 2_000_000, 1.0, 1.0),                                              # crossed (ask <= bid)
            (2_800_000, 2_001_000, 2_000_500, 1.0, 1.0), (3_700_000, 2_005_000, 2_004_500, 1.0, 1.0)]  # the last: outside the hour
    b = C.hour_bars(C.parse_bi5(_bi5(rows)), pd.Timestamp("2021-01-04 10:00", tz="UTC"))
    assert b["n"].sum() == 4 and b["out_of_hour"].sum() == 1 and b["dup_ms"].sum() == 1 and b["crossed"].sum() == 1
    assert b.loc[pd.Timestamp("2021-01-04 10:45", tz="UTC"), "n"] == 1                       # the 3.7m-ms tick is not here
    first = b.loc[pd.Timestamp("2021-01-04 10:00", tz="UTC")]
    assert first["max_gap_s"] == pytest.approx(500.0) and first["mid_first"] == pytest.approx(2_000_250)


def _aligned(n_days=60, seed=11):
    idx = pd.date_range("2021-01-04", periods=96 * n_days, freq="15min", tz="UTC")
    idx = idx[idx.day_of_week != 5]
    m15 = _spot(idx, seed)
    raw = pd.DataFrame({"n": 20.0, "mid_last": m15["close"] * 1000, "mid_first": m15["open"] * 1000, "dup_ms": 0.0, "crossed": 0.0,
                        "max_gap_s": 60.0, "out_of_hour": 0.0}, index=idx)
    return raw, m15


def test_integrity_report_passes_aligned_data_and_reports_every_figure():
    raw, m15 = _aligned()
    r = C.integrity_report(raw, m15, 1000.0)
    assert r["failures"] == [] and r["best_lag_bars"] == 0 and r["offset_minutes"] == 0 and r["quarantined_days"] == []
    assert set(r["lags"]["by_session"]) == {"ASIA", "LONDON", "NY", "OFF"} and r["lags"]["by_year"][2021]["best_lag_bars"] == 0
    assert abs(r["basis_close_usd"]["p50"]) < 1e-9 and r["timestamps"]["weekly_open"]["median_min"] == 0
    assert r["missing"]["spot_bars_without_ticks"] == 0 and r["ticks"]["crossed_share"] == 0


def test_a_bad_day_is_quarantined_not_shifted():
    raw, m15 = _aligned()
    bad = raw.index.normalize() == pd.Timestamp("2021-01-20", tz="UTC")
    raw.loc[bad, "mid_last"] *= 1.02                                                         # a 2% basis for one day
    r = C.integrity_report(raw, m15, 1000.0)
    assert r["quarantined_days"] == ["2021-01-20"] and r["failures"] == []
    q = C.quarantine(raw, r["quarantined_days"])
    assert q.loc[bad].isna().all().all() and (q.loc[~bad, "mid_last"] == raw.loc[~bad, "mid_last"]).all()


def test_a_session_clock_offset_stops_the_run():
    raw, m15 = _aligned()
    asia = (raw.index.hour < 7)
    shifted = raw["mid_last"].shift(1)                                                       # Asian bars one bar late
    raw.loc[asia, "mid_last"] = shifted[asia]
    r = C.integrity_report(raw, m15, 1000.0)
    assert any("by_session ASIA" in f for f in r["failures"])


def test_a_cache_written_before_a2_is_fetched_again(tmp_path):
    day = pd.Timestamp("2021-01-04", tz="UTC")
    os.makedirs(tmp_path / "days")
    pd.DataFrame({"n": [1.0]}, index=[day]).to_csv(tmp_path / "days" / "2021-01-04.csv", index_label="bar")
    calls = []

    def fake(t, get=None):
        calls.append(t)
        return b""
    import concurrent.futures as cf
    old = C.fetch_hour
    C.fetch_hour = fake
    try:
        with cf.ThreadPoolExecutor(2) as pool:
            _df, meta = C.load_day(day, str(tmp_path), pool)
    finally:
        C.fetch_hour = old
    assert len(calls) == 24 and meta.get("cached") is None


def test_the_real_download_path_uses_the_http_session(monkeypatch):
    """Amendment A3 defect fix: _session() (the HTTP session) was shadowed by the session-label helper, so every real
    download raised TypeError. The other tests inject `get` and could not see it; this one takes the default path."""
    import requests
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    seen = []

    def fake_get(self, url, timeout=None):
        seen.append((url, self.headers.get("User-Agent")))
        return _Resp(404)
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(C, "_local", C.threading.local())
    assert isinstance(C._session(), requests.Session)
    assert C.fetch_hour(pd.Timestamp("2021-03-01 10:00", tz="UTC")) == b""
    assert seen and seen[0][0].endswith("/XAUUSD/2021/02/01/10h_ticks.bi5") and "quantum" in seen[0][1]
    assert list(C._session_of(pd.DatetimeIndex(["2021-01-04 03:00", "2021-01-04 08:00", "2021-01-04 13:00", "2021-01-04 22:00"],
                                                tz="UTC"))) == ["ASIA", "LONDON", "NY", "OFF"]
