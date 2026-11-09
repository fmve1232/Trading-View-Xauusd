"""Phase D data layer on SYNTHETIC ticks and paths (no network, no real data): the Dukascopy extraction (sealed-period
guard, Phase D sums, one-minute bid / ask bars, B5c cache compatibility), the order-flow features (no look-ahead), and
the one-minute bid / ask race (hand cases, and exact agreement with B26 wherever a 15-minute bar is unambiguous)."""
import json
import lzma
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest

from quantum.research import b5c_dukascopy as C
from quantum.research import b26
from quantum.research import d_dukascopy as D
from quantum.research import d_features as DF
from quantum.research import d_m1 as M
from quantum.research import harness as H


def _bi5(rows):
    return lzma.compress(b"".join(C.REC.pack(*r) for r in rows), format=lzma.FORMAT_ALONE)


# ---------------- extraction ----------------
def test_sealed_period_is_refused_before_any_request():
    with pytest.raises(D.SealedPeriod):
        D.check_span(pd.Timestamp("2022-12-01", tz="UTC"), pd.Timestamp("2023-02-01", tz="UTC"))
    with pytest.raises(D.SealedPeriod):
        D.check_span(pd.Timestamp("2025-12-31", tz="UTC"), pd.Timestamp("2026-01-02", tz="UTC"))
    D.check_span(*H.DEV)                                                       # development ends where the seal starts
    assert D.span("y2026", now=pd.Timestamp("2026-11-09 13:00", tz="UTC")) == (pd.Timestamp("2026-01-01", tz="UTC"),
                                                                              pd.Timestamp("2026-11-09", tz="UTC"))
    edge = D.hours_of(pd.Timestamp("2023-01-24", tz="UTC"), *H.DEV)
    assert [t.hour for t in edge] == [0, 1]                                    # 02:00 onwards is sealed
    assert D.hours_of(pd.Timestamp("2020-01-24", tz="UTC"), *H.DEV)[0].hour == 2
    assert [t.hour for t in C.day_hours(pd.Timestamp("2023-01-24", tz="UTC"))] == [0, 1]   # B5c amendment A3
    with pytest.raises(D.SealedPeriod):
        D.fetch_sym("EURUSD", pd.Timestamp("2024-02-01 10:00", tz="UTC"), lambda url, timeout: None)
    seen = []
    with ThreadPoolExecutor(2) as pool:
        D.load_day(pd.Timestamp("2023-01-24", tz="UTC"), "/nonexistent-cache-not-written", pool,
                   lambda t: seen.append(t) or None, *H.DEV)
    assert [t.hour for t in seen] == [0, 1] or sorted(t.hour for t in seen) == [0, 1]


def test_pd_sums_count_every_registered_quantity():
    h0 = pd.Timestamp("2021-03-01 10:00", tz="UTC")
    rows = [(1_000, 1010, 1000, 2, 3),          # mid 1005, spread 10
            (2_000, 1012, 1000, 2, 3),          # ask up: mid +1, spread widens
            (2_500, 1012, 1002, 2, 3),          # bid up: mid +1, spread narrows
            (3_000, 1011, 1001, 2, 3),          # both down: mid -1
            (700_000, 1013, 1003, 2, 3),        # in the last five minutes: both up, mid +2
            (900_100, 1013, 1003, 1, 1)]        # bar 1, no change
    s = D.pd_sums(C.parse_bi5(_bi5(rows)), h0)
    b0 = s.iloc[0]
    assert b0["bid_up"] == 2 and b0["bid_dn"] == 1 and b0["ask_up"] == 2 and b0["ask_dn"] == 1
    assert b0["path_abs"] == pytest.approx(1 + 1 + 1 + 2) and b0["rv"] == pytest.approx(1 + 1 + 1 + 4)
    assert b0["spread_min"] == 10 and b0["spread_max"] == 12 and b0["spread_first"] == 10 and b0["spread_last"] == 10
    assert b0["flips"] == 2 and b0["run_max"] == 2 and b0["n_h1"] == 4 and b0["n_l5"] == 1 and b0["sec_active"] == 4
    assert b0["sw_up"] == 1 and b0["sw_dn"] == 1 and b0["mid_hi"] == 1008 and b0["mid_lo"] == 1005
    assert b0["ofi_l5"] == pytest.approx(3 + 2)                                # bid up (+new bid qty) and ask up (+old ask qty)
    assert s.iloc[1]["path_abs"] == 0 and s.iloc[1]["flips"] == 0


def test_m1_bars_keep_bid_and_ask_separately():
    h0 = pd.Timestamp("2021-03-01 10:00", tz="UTC")
    rows = [(1_000, 1010, 1000, 1, 1), (30_000, 1015, 1004, 1, 1), (59_000, 1008, 999, 1, 1), (125_000, 1011, 1001, 1, 1)]
    m = D.m1_bars(C.parse_bi5(_bi5(rows)), h0)
    assert list(m.index) == [h0, h0 + pd.Timedelta(minutes=2)]                 # the empty minute has no row
    assert m.iloc[0][["bid_o", "bid_h", "bid_l", "bid_c"]].tolist() == [1000, 1004, 999, 999]
    assert m.iloc[0][["ask_o", "ask_h", "ask_l", "ask_c"]].tolist() == [1010, 1015, 1008, 1008] and m.iloc[0]["n"] == 3


def test_extraction_writes_b5c_compatible_days_and_resumes(tmp_path):
    day = pd.Timestamp("2021-03-02", tz="UTC")
    g = H.seeded_rng(3)

    def fake(t):
        mid = 1_850_000 + int(g.integers(-500, 500))
        return _bi5([(j * 60_000 + 10, mid + 150, mid - 150, 1.0, 2.0) for j in range(60)])
    with ThreadPoolExecutor(2) as pool:
        fr, meta = D.load_day(day, str(tmp_path / "d"), pool, fake)
        assert meta["hours"] == 24 and len(fr["m1"]) == 24 * 60 and len(fr["days"]) == 96 and len(fr["dext"]) == 96
        b5c_df, _ = C.load_day(day, str(tmp_path / "d"), pool, lambda url, timeout: (_ for _ in ()).throw(AssertionError("refetch")))
        pd.testing.assert_frame_equal(b5c_df, fr["days"].astype(float), check_freq=False)    # B5c reads Phase D's file
        _again, m2 = D.load_day(day, str(tmp_path / "d"), pool, lambda t: (_ for _ in ()).throw(AssertionError("refetch")))
        assert m2 == {"cached": 1}


def test_probe_reports_unavailable_instruments_without_substitution():
    class R:
        def __init__(self, code, content=b""):
            self.status_code, self.content = code, content
    good = _bi5([(10, 1_100_000, 1_099_990, 1.0, 1.0)])
    pr = D.probe_intermarket(lambda url, timeout: R(200, good) if "/EURUSD/" in url else R(404))
    assert pr["EURUSD"]["available"] and not pr["XAGUSD"]["available"] and not pr["USDX"]["available"]


# ---------------- features ----------------
def _sums(bars=3000, seed=2):
    g = H.seeded_rng(seed)
    idx = pd.date_range("2021-01-04", periods=bars, freq="15min", tz="UTC")
    n = g.integers(20, 400, bars).astype(float)
    mid = 1800_000.0 + np.cumsum(g.normal(0, 500, bars))
    raw = pd.DataFrame({"n": n, "ofi": g.normal(0, 40, bars), "depth": n * g.uniform(2, 6, bars), "qsum": g.normal(0, 3, bars),
                        "qn": n, "qlast": g.uniform(-1, 1, bars), "up": np.floor(n * 0.4), "down": np.floor(n * 0.4),
                        "spread_sum": n * 300.0, "mid_last": mid, "mid_first": mid - g.normal(0, 200, bars), "dup_ms": 0.0,
                        "crossed": 0.0, "max_gap_s": 30.0, "out_of_hour": 0.0}, index=idx)
    dext = pd.DataFrame({c: g.uniform(1, 50, bars) for c in D.PD_COLS}, index=idx)
    dext["spread_min"], dext["spread_max"] = 250.0, 350.0
    dext["spread_sq"] = n * 300.0 ** 2 + n * 100.0
    dext["n_h1"] = np.floor(n / 2)
    return raw, dext


def test_order_flow_features_use_only_past_bars_and_cover_ten_families():
    raw, dext = _sums()
    full = DF.order_flow(raw, dext, 1000.0)
    assert set(DF.FAMILIES_OF) == set(range(1, 11)) and list(full.columns) == list(DF.OF_COLUMNS)
    for k in (2400, 2999):
        part = DF.order_flow(raw.iloc[:k], dext.iloc[:k], 1000.0)
        pd.testing.assert_frame_equal(part, full.iloc[:k], check_freq=False)
    assert full["nd_of_spread"].iloc[0] == pytest.approx(0.3) and full["nd_of_spread_sd"].iloc[0] == pytest.approx(0.01)
    gap = raw.copy()
    gap.iloc[100, gap.columns.get_loc("n")] = 0
    f2 = DF.order_flow(gap, dext, 1000.0)
    assert f2["nd_of_missing"].iloc[100] == 1 and f2.iloc[100].drop("nd_of_missing").isna().all()


# ---------------- the one-minute race ----------------
def _path(rows, t0="2021-03-01 10:00"):
    """rows: (bid_o, bid_h, bid_l, bid_c, spread) per minute."""
    idx = pd.date_range(t0, periods=len(rows), freq="1min", tz="UTC")
    r = np.asarray(rows, float)
    m = pd.DataFrame({"bid_o": r[:, 0], "bid_h": r[:, 1], "bid_l": r[:, 2], "bid_c": r[:, 3]}, index=idx)
    for a, b in (("ask_o", "bid_o"), ("ask_h", "bid_h"), ("ask_l", "bid_l"), ("ask_c", "bid_c")):
        m[a] = m[b] + r[:, 4]
    m["n"] = 1.0
    return M.from_dukascopy(m, 1.0), idx


def test_race_hand_cases():
    flat = [(100, 100.2, 99.8, 100, 0.3)] * 3
    P, idx = _path(flat + [(100, 116, 100, 115, 0.3)] + flat * 3)
    tend = int(idx[-1].timestamp()) + 60
    o = M.race(P, 0, 1, 15, 15, 0.0, 0.2, tend)
    assert o[0] == M.TP and o[2] == 3 and o[3] == pytest.approx(100.3 + 15)
    P, idx = _path(flat + [(100, 100, 84, 85, 0.3)] + flat)
    o = M.race(P, 0, 1, 15, 15, 0.0, 0.2, tend)
    assert o[0] == M.SL and o[3] == pytest.approx(100.3 - 15 - 0.2) and not o[5]
    P, idx = _path(flat + [(100, 116, 84, 100, 0.3)] + flat)                   # both levels in one minute
    o = M.race(P, 0, 1, 15, 15, 0.0, 0.2, tend)
    assert o[0] == M.AMB and o[1] == M.TP
    P, idx = _path(flat + [(80, 81, 79, 80, 0.3)] + flat)                      # a minute opening beyond the stop
    o = M.race(P, 0, 1, 15, 15, 0.0, 0.2, tend)
    assert o[0] == M.SL and o[5] and o[3] == pytest.approx(80 - 0.2)
    P, idx = _path(flat * 3)
    o = M.race(P, 0, -1, 15, 15, 0.0, 0.2, int(idx[5].timestamp()))           # SELL timing out at minute 5's open
    assert o[0] == M.TIMEOUT and o[2] == 4 and o[3] == pytest.approx(100 + 0.3 + 0.2)
    assert M.race(P, 0, 1, 15, 15, 0.0, 0.2, int(idx[-1].timestamp()) + 3600)[0] == M.OPEN


def _expand(m15: pd.DataFrame, seed=1):
    """Each 15-minute mid bar as 15 one-minute bars: open -> first extreme -> second extreme -> close (order random)."""
    g = H.seeded_rng(seed)
    rows, idx = [], []
    for t, (o, h, lo, c) in zip(m15.index, m15[["open", "high", "low", "close"]].to_numpy(), strict=True):
        e1, e2 = (h, lo) if g.uniform() < 0.5 else (lo, h)
        p = np.r_[np.linspace(o, e1, 6), np.linspace(e1, e2, 6)[1:], np.linspace(e2, c, 6)[1:]]
        for m in range(15):
            a, b = p[m], p[m + 1]
            rows.append((a, max(a, b), min(a, b), b))
            idx.append(t + pd.Timedelta(minutes=m))
    return pd.DataFrame(rows, columns=["o", "h", "l", "c"], index=pd.DatetimeIndex(idx))


def test_one_minute_race_agrees_with_b26_wherever_the_15m_bar_is_unambiguous():
    g = H.seeded_rng(7)
    idx = pd.date_range("2021-01-04", periods=1400, freq="15min", tz="UTC")
    idx = idx[(idx < pd.Timestamp("2021-01-08 21:00", tz="UTC")) | (idx >= pd.Timestamp("2021-01-11", tz="UTC"))]   # a closure
    c = 1800 + np.cumsum(g.normal(0, 4.0, len(idx)))
    o = np.r_[c[0], c[:-1]] + g.normal(0, 0.3, len(idx))
    wide = g.uniform(0, 1, len(c)) < 0.05                                      # a few bars wide enough to hold both levels
    ext = np.where(wide, 16.0, g.uniform(0, 3, len(c)))
    m15 = pd.DataFrame({"open": o, "high": np.maximum(o, c) + ext, "low": np.minimum(o, c) - ext,
                        "close": c}, index=idx)
    P15 = b26.make_path(m15, 900)
    x = _expand(m15)
    s, si, so = 0.30, 0.20, 0.20
    m1 = pd.DataFrame({"bid_o": x["o"] - s / 2, "bid_h": x["h"] - s / 2, "bid_l": x["l"] - s / 2, "bid_c": x["c"] - s / 2,
                       "ask_o": x["o"] + s / 2, "ask_h": x["h"] + s / 2, "ask_l": x["l"] + s / 2, "ask_c": x["c"] + s / 2, "n": 1.0})
    P1 = M.from_dukascopy(m1, 1.0)
    t15 = np.asarray(P15.t)
    agree = amb = 0
    for f in range(1, len(idx) - 200, 3):
        for d in (1, -1):
            r = b26.race(P15, f, d, s, si, so, 1.0, 192)
            t_end = int(t15[f + 191]) + 900
            w = M.race(P1, int(np.searchsorted(P1.t, t15[f])), d, 15.0, 15.0, si, so, t_end)
            if r[0] == b26.AMB:
                amb += 1
                assert w[0] in (M.TP, M.SL)                                    # resolved at one minute
                continue
            assert b26.OUTCOMES[r[0]] == M.NAMES[w[0]], (f, d)
            assert w[3] == pytest.approx(r[2], abs=1e-9), (f, d)
            agree += 1
    assert agree > 500 and amb > 0


def test_stop_entry_bounds_the_fill_minute():
    flat = [(100, 100.2, 99.8, 100, 0.3)] * 2
    P, idx = _path(flat + [(100, 106, 99.9, 105, 0.3)] + [(105, 125, 105, 124, 0.3)] + flat)
    t_dec = np.array([int(idx[0].timestamp())])
    t_end = np.array([int(idx[-1].timestamp()) + 60])
    st = M.stop_entry(P, t_dec, t_end, 1, 5.0, 3600, 15.0, 15.0, np.array([100.0]), np.array([1.0]))
    assert st["outcome"].iloc[0] == "TP" and st["net_worst"].iloc[0] == pytest.approx(15.0)
    P2, _ = _path(flat + [(100, 106, 80, 90, 0.3)] + flat)                 # the stop fills and SL is touched in that minute
    st2 = M.stop_entry(P2, t_dec, t_end, 1, 5.0, 3600, 15.0, 15.0, np.array([100.0]), np.array([1.0]))
    assert st2["outcome"].iloc[0] == "SL" and st2["outcome_best"].iloc[0] != "SL"


def test_mt5_path_needs_the_point_and_builds_the_ask():
    idx = pd.date_range("2026-02-02", periods=5, freq="1min", tz="UTC")
    m = pd.DataFrame({"open": 2000.0, "high": 2001.0, "low": 1999.0, "close": 2000.5, "spread_points": 25.0}, index=idx)
    with pytest.raises(ValueError):
        M.from_mt5(m, None)
    P = M.from_mt5(m, 0.01)
    assert P.ao[0] == pytest.approx(2000.25) and P.source.startswith("mt5")
    assert json.dumps({"ok": True})
    assert os.path.basename(M.__file__) == "d_m1.py"
