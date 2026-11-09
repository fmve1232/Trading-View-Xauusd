"""research/tools/mt5_m1_check.py on SYNTHETIC MT5 exports (no real data): encodings and separators, server time -> UTC
(fixed offset, IANA zone and the NY+7 convention), the partition guard, integrity (discontinuities, Saturday bars,
coverage), the per-week clock check that catches a daylight-saving convention mismatch, and the command end to end."""
import io
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "tools"))
import mt5_m1_check as M


def _frame(utc_idx, close, server_idx, spread=25):
    o = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"<DATE>": server_idx.strftime("%Y.%m.%d"), "<TIME>": server_idx.strftime("%H:%M:%S"), "<OPEN>": np.round(o, 2),
                         "<HIGH>": np.round(np.maximum(o, close) + 0.1, 2), "<LOW>": np.round(np.minimum(o, close) - 0.1, 2),
                         "<CLOSE>": np.round(close, 2), "<TICKVOL>": 10, "<VOL>": 0, "<SPREAD>": spread})


def _export(utc_idx, close, server_offset_h=2, sep="\t", encoding="utf-8"):
    st = utc_idx.tz_convert(None) + pd.Timedelta(hours=server_offset_h)
    text = _frame(utc_idx, close, st).to_csv(sep=sep, index=False)
    return io.BytesIO(text.encode(encoding))


def _ny7_export(utc_idx, close, encoding="utf-16"):
    st = utc_idx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
    return io.BytesIO(_frame(utc_idx, close, st).to_csv(sep="\t", index=False).encode(encoding))


def _walk(n, seed=4):
    return 2000 + np.cumsum(np.random.default_rng(seed).normal(0, 0.3, n))


def _ref(idx, close):
    return pd.Series(close, index=idx).resample("15min", label="left", closed="left").last().dropna()


def test_parse_convert_integrity_and_clock():
    idx = M.trading_minutes(pd.Timestamp("2021-01-11", tz="UTC"), pd.Timestamp("2021-01-23", tz="UTC"))
    close = _walk(len(idx))
    meta = {}
    raw = M.read_export(_export(idx, close), meta)
    assert meta["encoding"] == "utf-8" and meta["separator"] == "tab" and meta["unparsed_time"] == 0 and meta["price_decimals_max"] <= 2
    good = M.to_utc(raw, offset_hours=2)
    assert good.index[0] == idx[0]
    rep = M.integrity(good, point=0.01)
    assert rep["rows"] == len(idx) and rep["duplicates"] == 0 and rep["bad_ohlc"] == 0 and rep["gaps_weekend_or_holiday"] == 1
    assert rep["saturday_bars"] == 0 and rep["bars_in_ny_17h_break"] == 0 and rep["spread_usd"]["median"] == pytest.approx(0.25)
    ref = _ref(idx, close)
    ck = M.clock_check(good, ref)
    assert ck["aligned"] and ck["best_shift_hours"] == 0 and ck["median_abs_close_gap"] < 0.01 and ck["misaligned_weeks"] == []
    wrong = M.to_utc(raw, offset_hours=0)                    # the server offset forgotten
    ck2 = M.clock_check(wrong, ref)
    assert not ck2["aligned"] and ck2["best_shift_hours"] == -2


def test_encodings_separators_and_header_variants():
    idx = M.trading_minutes(pd.Timestamp("2021-02-01", tz="UTC"), pd.Timestamp("2021-02-02", tz="UTC"))
    close = _walk(len(idx))
    base = M.read_export(_export(idx, close))
    for enc, sep, label in (("utf-16", "\t", "utf-16 (BOM)"), ("utf-16-le", "\t", "utf-16-le (no BOM)"),
                            ("utf-8-sig", ",", "utf-8 (BOM)"), ("utf-8", ";", "utf-8")):
        meta = {}
        got = M.read_export(_export(idx, close, sep=sep, encoding=enc), meta)
        assert meta["encoding"] == label
        pd.testing.assert_frame_equal(got, base)
    plain = _frame(idx, close, idx.tz_convert(None)).rename(columns=lambda c: c.strip("<>").lower())
    got = M.read_export(io.StringIO(plain.to_csv(sep="\t", index=False)))
    assert len(got) == len(idx)


def test_rejects_a_non_export_and_counts_unreadable_rows():
    with pytest.raises(ValueError):
        M.read_export(io.StringIO("a\tb\n1\t2\n"))
    idx = pd.date_range("2021-01-11", periods=500, freq="1min", tz="UTC")
    f = _frame(idx, np.full(500, 2000.0), idx.tz_convert(None)).astype(str)
    f.loc[3, "<TIME>"] = "25:61:00"
    f.loc[7, "<CLOSE>"] = "n/a"
    meta = {}
    raw = M.read_export(io.StringIO(f.to_csv(sep="\t", index=False)), meta)
    assert meta["unparsed_time"] == 1 and meta["unparsed_number"] == 1 and len(raw) == 498
    raw.iloc[10, raw.columns.get_loc("low")] = 2100.0         # low above the close
    assert M.integrity(raw)["bad_ohlc"] == 1


def test_ny_plus_7_and_a_daylight_saving_mismatch_is_caught_per_week():
    """A broker on NY+7 (GMT+2/+3 on the US dates) read as Europe/Athens is an hour wrong from the US to the EU change
    (2021-03-14 -> 03-28): the overall peak can stay at 0, so only the per-week check catches it."""
    idx = M.trading_minutes(pd.Timestamp("2021-02-01", tz="UTC"), pd.Timestamp("2021-05-01", tz="UTC"))
    close = _walk(len(idx), seed=9)
    raw = M.read_export(_ny7_export(idx, close))
    right = M.to_utc(raw, server_tz="NY+7")
    assert len(right) == len(idx) and (right.index == idx).all()
    ref = _ref(idx, close)
    assert M.clock_check(right, ref)["aligned"]
    wrong = M.to_utc(raw, server_tz="Europe/Athens")
    ck = M.clock_check(wrong, ref)
    assert not ck["aligned"] and ck["best_shift_hours"] == 0                   # the overall peak alone would pass
    assert set(ck["misaligned_weeks"]) >= {"2021-W11", "2021-W12"} and all(w.startswith("2021-W1") for w in ck["misaligned_weeks"])
    s = M.suggest_zone(raw, ref)
    assert s["NY+7"]["misaligned_weeks"] == 0 and s["Europe/Athens"]["misaligned_weeks"] >= 2


def test_partition_guard_drops_sealed_rows_before_any_figure():
    idx = pd.DatetimeIndex(["2020-01-10 10:00", "2022-06-01 10:00", "2023-01-24 01:59", "2023-01-24 02:00", "2024-03-01 10:00",
                            "2025-12-31 23:59", "2026-01-01 00:00", "2026-05-01 10:00"], tz="UTC")
    m1 = pd.DataFrame({"close": np.arange(len(idx), dtype=float)}, index=idx)
    kept, rep = M.partition_guard(m1)
    assert list(kept["close"]) == [1.0, 2.0, 6.0, 7.0]
    assert rep == {"kept_development": 2, "kept_2026": 2, "dropped_sealed": 3, "dropped_before_development": 1}


def test_discontinuities_saturday_bars_scale_change_and_coverage():
    idx = M.trading_minutes(pd.Timestamp("2021-01-04", tz="UTC"), pd.Timestamp("2021-03-01", tz="UTC"))
    close = _walk(len(idx), seed=3)
    m1 = pd.DataFrame({"open": np.r_[close[0], close[:-1]], "close": close, "tickvol": 5.0, "spread_points": 20.0}, index=idx)
    m1["high"], m1["low"] = m1[["open", "close"]].max(axis=1) + 0.1, m1[["open", "close"]].min(axis=1) - 0.1
    m1.iloc[5000, m1.columns.get_loc("open")] += 10.0                          # a $10 jump between consecutive minutes
    m1.iloc[5000, m1.columns.get_loc("high")] += 10.0
    r = M.integrity(m1)
    assert r["discontinuities"]["jumps"] == 1 and r["discontinuities"]["largest"][0]["t"] == str(idx[5000])
    assert r["coverage"]["by_month"]["2021-01"]["coverage"] == pytest.approx(1.0) and r["coverage"]["months_below_90pct"] == []
    thin = m1.drop(m1.index[(m1.index.month == 2) & (m1.index.day < 15)])
    assert "2021-02" in M.integrity(thin)["coverage"]["months_below_90pct"]
    sat = pd.concat([m1, m1.iloc[:1].set_axis(pd.DatetimeIndex(["2021-01-09 12:00"], tz="UTC"))]).sort_index()
    assert M.integrity(sat)["saturday_bars"] == 1
    x10 = m1.copy()
    x10.loc[x10.index.month == 2, ["open", "high", "low", "close"]] *= 10                 # a digits change
    assert [c["month"] for c in M.integrity(x10)["scale_changes"]] == ["2021-02"]


def test_main_end_to_end(tmp_path):
    idx = M.trading_minutes(pd.Timestamp("2026-02-02", tz="UTC"), pd.Timestamp("2026-02-21", tz="UTC"))
    close = _walk(len(idx), seed=5)
    f = tmp_path / "XAUUSD_M1.csv"
    f.write_bytes(_ny7_export(idx, close).getvalue())
    ref = _ref(idx, close)
    rp = tmp_path / "ref.csv"
    pd.DataFrame({"time": ref.index.astype(str), "close": ref.to_numpy()}).to_csv(rp, index=False)
    rep_p, out = tmp_path / "rep.json", tmp_path / "m1_utc.csv"
    assert M.main(["--file", str(f), "--server-tz", "NY+7", "--broker", "Test", "--symbol", "XAUUSD", "--point", "0.01",
                   "--reference", str(rp), "--report", str(rep_p), "--write-utc", str(out)]) == 0
    rep = json.loads(rep_p.read_text())
    assert rep["verdict"] == "USABLE" and rep["read"]["encoding"] == "utf-16 (BOM)" and rep["source"]["point_matches_decimals"]
    assert rep["partitions"]["kept_2026"] == len(idx) and out.exists() and json.loads((tmp_path / "m1_utc.csv.json").read_text())
    assert M.main(["--file", str(f), "--server-tz", "NY+7", "--report", str(rep_p)]) == 1            # no clock check
    rep = json.loads(rep_p.read_text())
    assert rep["verdict"] == "NOT USABLE" and rep["source"]["broker"] == "NOT SUPPLIED" and "clock NOT CHECKED" in rep["reasons"][-1]
