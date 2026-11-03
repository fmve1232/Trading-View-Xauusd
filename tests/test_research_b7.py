"""Phase B7 (quantum/research/b7_macro.py) on SYNTHETIC macro series: directions use only data known before the
08:00 UTC entry (Yahoo: the previous close; FRED: 2 business days earlier; COT: the last released report), small moves
do not fire, and the study runs end to end with a planted relation."""
import numpy as np
import pandas as pd

from quantum.research import b2
from quantum.research import b7_macro as B


def _daily(n=600, seed=1, start="2019-01-01"):
    g = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n, tz="UTC")
    return pd.Series(100 + np.cumsum(g.normal(0, 1, n)), index=idx)


def test_yahoo_direction_uses_the_previous_close_only():
    s = _daily()
    days = s.index[400:420]
    d = B.series_direction(s, days, 1, -1, fred_lag=False)
    s2 = s.copy()
    s2.loc[days[5]:] += 50                                  # moves dated on / after entry day 5 must not matter for day 5
    d2 = B.series_direction(s2, days, 1, -1, fred_lag=False)
    assert d[5] == d2[5] and np.all(d[:5] == d2[:5])
    big = s.copy()
    big.iloc[399] = big.iloc[398] + 10                       # a large rise the day before day[0]
    assert B.series_direction(big, days[:1], 1, -1, fred_lag=False)[0] == -1     # dollar up -> gold SELL


def test_fred_direction_lags_two_business_days_and_small_moves_do_not_fire():
    s = _daily()
    mon = pd.Timestamp("2020-06-15", tz="UTC")              # a Monday
    s = s.copy()
    s.loc[pd.Timestamp("2020-06-12", tz="UTC")] += 40        # Friday's value: not yet published on Monday morning
    assert B.series_direction(s, pd.DatetimeIndex([mon]), 1, -1, fred_lag=True)[0] == \
        B.series_direction(s.drop(pd.Timestamp("2020-06-12", tz="UTC")), pd.DatetimeIndex([mon]), 1, -1, fred_lag=True)[0]
    flat = pd.Series(np.r_[np.linspace(100, 101, 500), 101.0001], index=pd.bdate_range("2018-01-01", periods=501, tz="UTC"))
    assert B.series_direction(flat, flat.index[-1:] + pd.Timedelta(days=1), 1, 1, fred_lag=False)[0] == 0


def test_cot_uses_reports_released_before_the_entry():
    rel = pd.date_range("2017-01-06 20:30", periods=300, freq="7D", tz="UTC")
    g = np.random.default_rng(3)
    cot = pd.DataFrame({"nc_long": 200000 + g.normal(0, 5000, 300), "nc_short": 50000 + g.normal(0, 5000, 300),
                        "open_interest": 500000.0}, index=rel)
    cot.iloc[-2, cot.columns.get_loc("nc_long")] = 400000    # extreme long in the second-to-last report
    t_before_last = rel[-1] - pd.Timedelta(hours=1)
    contra, flow = B.cot_directions(cot, pd.DatetimeIndex([t_before_last]))
    assert contra[0] == -1 and flow[0] == 1                  # crowded long -> SELL; net rose -> follow BUY


def _spot(days=520, seed=5):
    idx = pd.date_range("2020-02-03", periods=days * 96, freq="15min", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    g = np.random.default_rng(seed)
    c = 1800 + np.cumsum(g.normal(0, 1.2, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.6, "low": np.minimum(o, c) - 0.6, "close": c}, index=idx)


def test_study_end_to_end_and_a_planted_relation_is_found(monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 48)
    m15 = _spot()
    days = pd.DatetimeIndex(sorted(set(m15.index.normalize())))
    c08 = m15["close"][m15.index.strftime("%H:%M") == "07:45"]
    c20 = m15["close"][m15.index.strftime("%H:%M") == "19:45"]
    move = (c20.groupby(c20.index.normalize()).last() - c08.groupby(c08.index.normalize()).last()).reindex(days).fillna(0)
    # plant: the dollar's change dated the day BEFORE each day is minus that day's gold move (a strong, known-in-advance signal)
    dxy = pd.Series(100 - move.shift(-1).fillna(0).cumsum().to_numpy(), index=days)
    noise = _daily(len(days), 9, "2020-02-03").set_axis(days)
    yahoo = {"dxy": dxy, "tnx": noise, "vix": noise, "oil": noise}
    fred = {"real": noise, "be": noise}
    res = B.study(m15, yahoo, fred, None)
    tm = {t["id"]: t for t in res["trials"]}
    assert len(res["trials"]) == 22 and res["family"]["trials"] >= 16
    assert tm["daily USD1 08UTC T13"]["win_rate"] > tm["daily USD1 08UTC T13"]["random_same_mix"] + 0.1
    assert tm["daily USD1 08UTC T13"]["drift_08_20_usd_at_4000"] > 0
    assert tm["daily COT_CONTRA 08UTC T13"]["n"] == 0                          # no COT data -> no signals, nothing invented
    assert abs(tm["daily VIX1 08UTC T13"]["z_vs_random"]) < 3


def test_declared_constants():
    assert B.TARGETS == {"T13": (13.0, 13.0), "T10": (10.0, 10.0)} and (B.MED_OBS, B.FRED_LAG_BD, B.COT_Z_N, B.COT_Z) == (252, 2, 156, 1.0)
    assert [r[0] for r in B.RULES] == ["USD1", "USD5", "NOM1", "REAL1", "REAL5", "VIX1", "OIL5", "BE5"]
    assert B.YAHOO["dxy"] == "DX-Y.NYB" and B.FRED["real"] == "DFII10" and B.ENTRY_OPEN_UTC == "07:45"


def test_fetch_records_failures_without_inventing_data(monkeypatch):
    def boom(*a, **k):
        raise B.sources.FetchError("blocked")
    monkeypatch.setattr(B.sources, "yahoo", boom)
    monkeypatch.setattr(B.sources, "fred", boom)
    monkeypatch.setattr(B.sources, "cftc_gold_cot", boom)
    y, f, cot, status = B.fetch()
    assert y == {} and f == {} and cot is None and all("FAILED" in v for v in status.values())
