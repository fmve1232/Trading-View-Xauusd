"""Phase B3 (quantum/research/b3.py): sequences use only past bars; the trend reads completed 1h bars only; the
confirmation entry is exact; the grid is the declared one."""
import numpy as np
import pandas as pd

from quantum.research import b2, b3
from tests.test_research_b2 import _walk


def test_declared_grid_and_targets():
    assert b3.TARGETS == {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
    assert b3.SETUPS[:9] == b2.SETUPS and b3.SETUPS[9:] == ("SEQ_SWEEP_MSS", "SEQ_SWEEP_MSS_FVG")
    n = sum(len(b3.combos(s)) for s in b3.SETUPS) * len(b2.TFS) * len(b3.TARGETS)
    assert n == 210
    assert ("none", False) not in b3.combos("BOS")          # B2 already ran the unfiltered, unconfirmed version


def test_sequences_use_only_past_bars_and_follow_their_parts():
    df = _walk(4000, seed=9)
    base = b2.signals(df)
    full = b3.sequences(df, base)
    assert (full["SEQ_SWEEP_MSS"] != 0).sum() >= 3
    for k in (1500, 2600):
        part = b3.sequences(df.iloc[:k], b2.signals(df.iloc[:k]))
        for name in full:
            assert np.array_equal(part[name], full[name][:k]), (name, k)
    brk, _ = b2._structure(*(df[x].to_numpy(float) for x in ("high", "low", "close")))
    s = full["SEQ_SWEEP_MSS"]
    assert np.all(brk[s != 0] == s[s != 0])                  # every sequence signal is a structure break in its direction
    f = full["SEQ_SWEEP_MSS_FVG"]
    assert np.all(base["FVG_RETEST"][f != 0] == f[f != 0])  # and every FVG step is an FVG retest in its direction


def test_trend_reads_the_last_completed_hour_only():
    idx = pd.date_range("2021-03-01", periods=400, freq="1h", tz="UTC")
    c = np.r_[np.linspace(1800, 1900, 300), np.linspace(1900, 1700, 100)]
    tr = b3.Trend(pd.DataFrame({"close": c}, index=idx))
    assert (tr.v[:200] == 0).all() and tr.v[299] == 1
    t_close = tr.t_close
    assert tr.at(np.array([t_close[299]]))[0] == tr.v[299]
    assert tr.at(np.array([t_close[299] - 1]))[0] == tr.v[298]          # one second before bar 299 closes: bar 298
    assert tr.at(np.array([int(idx[0].timestamp())]))[0] == 0            # before any bar closed


def _paths(c):
    idx = pd.date_range("2021-03-01", periods=len(c), freq="15min", tz="UTC")
    c = np.asarray(c, float)
    return b2.Paths(pd.DataFrame({"open": c, "high": c + 0.1, "low": c - 0.1, "close": c}, index=idx))


def test_confirmation_entry_is_exact(monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 4)
    # price 4000 so the confirmation distance is exactly $3
    P = _paths([4000, 4001, 4003.0, 4004, 4005, 4006, 4007, 4008, 4009, 4010, 4011, 4012, 4013, 4014])
    t0 = P.t[0]
    take, jj, t_e, p_e = b3.confirm(P, np.array([t0]), np.array([4000.0]), np.array([1.0]))
    assert take[0] and jj[0] == 2 and p_e[0] == 4003.0 and t_e[0] == P.t[2] + 900       # first close >= +3
    P2 = _paths([4000, 3999, 3997.0, 4005, 4006, 4007, 4008, 4009, 4010, 4011, 4012, 4013, 4014, 4015])
    assert not b3.confirm(P2, np.array([t0]), np.array([4000.0]), np.array([1.0]))[0][0]   # -3 came first
    P3 = _paths([4000] * 14)
    assert not b3.confirm(P3, np.array([t0]), np.array([4000.0]), np.array([1.0]))[0][0]   # never confirmed
    take, jj, _, p_e = b3.confirm(P2, np.array([t0]), np.array([4000.0]), np.array([-1.0]))
    assert take[0] and p_e[0] == 3997.0                                                  # the same path confirms a short


def test_family_aggregation_accepts_a_trial_without_trades():
    days = pd.DatetimeIndex(["2021-03-01", "2021-03-01", "2021-03-02"], tz="UTC")
    D = pd.DataFrame({"a": b3._daily(np.array([1.0, -0.5, 2.0]), days), "b": b3._daily(np.zeros(0), days[:0])}).fillna(0.0)
    D.index = pd.DatetimeIndex(D.index)
    assert D["a"].tolist() == [0.5, 2.0] and D["b"].tolist() == [0.0, 0.0]
    assert len(D.groupby(pd.Grouper(freq="W")).sum()) >= 1
