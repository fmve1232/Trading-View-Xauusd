"""PROPOSED Amendment F (F1-F4; docs/audit/AMENDMENT_F_PROPOSAL.md; NOT IN FORCE until the operator approves and merges).

F1  the previous week's high / low (PWH / PWL) cover EVERY bar of that NY trading week (IA-05);
F3  the calibration veto and the negative-EV veto are shadow flags: only the TQ floor and the risk lock block a signal;
F3b the race-grid EV does not enter trade quality;
F4  two unused definitions are gone.
Each test is written so that the production engine (51f9142d8) fails it."""
import math

import numpy as np
import pandas as pd
import pytest

from quantum import config as C
from quantum import engine, holdout
from quantum.config import DEFAULT
from quantum.data import sources
from quantum.data.market import load_synthetic

PRODUCTION_KEY = "5e4630924d663fc5:a6f2be58c74887ed"


def _independent_prev_week(base: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """The definition, computed apart from the engine: the trading day starts at 17:00 New York (bar OPEN time + 7 h,
    NY clock); the week is that day's ISO week; PWH / PWL on a bar = the max high / min low of ALL bars of the previous
    week in the series (NaN in the first week)."""
    ny = base.index.tz_convert("America/New_York")
    td = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)
    iso = pd.DatetimeIndex(td).isocalendar()
    wk = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    df = pd.DataFrame({"w": wk, "h": base["high"].to_numpy(float), "l": base["low"].to_numpy(float)})
    wh, wl = df.groupby("w", sort=False)["h"].max(), df.groupby("w", sort=False)["l"].min()
    order = list(dict.fromkeys(wk))
    prev = {order[k]: order[k - 1] for k in range(1, len(order))}
    ph = np.array([wh[prev[w]] if w in prev else np.nan for w in wk])
    pl = np.array([wl[prev[w]] if w in prev else np.nan for w in wk])
    return ph, pl


@pytest.mark.parametrize("tf, bars, seed", [("15m", 2400, 11), ("1h", 1200, 8), ("4h", 600, 11)])   # seeds on which the
def test_f1_weekly_range_matches_an_independent_computation(tf, bars, seed):                         # production engine differs
    m = load_synthetic(tf, bars=bars, seed=seed)
    res = engine.run(m, DEFAULT)
    ph, pl = _independent_prev_week(m.base)
    eh, el = np.asarray(res.rows["pwh"], float), np.asarray(res.rows["pwl"], float)
    for mine, eng, name in ((ph, eh, "PWH"), (pl, el, "PWL")):
        both = np.isfinite(mine) & np.isfinite(eng)
        assert both.sum() > bars // 2, name                              # most bars are compared
        assert np.array_equal(np.isfinite(mine), np.isfinite(eng)), name  # defined on the same bars
        assert np.abs(eng[both] - mine[both]).max() == 0.0, (tf, name)   # and identical (0 differences)


def test_f1_a_day_opening_bar_that_sets_the_weekly_high_counts():
    """Hand-built: the week's highest high is on the FIRST bar of a mid-week trading day (17:00 NY). The production
    engine skipped that bar, so its PWH next week was lower than the true high."""
    m = load_synthetic("1h", bars=600, seed=3)
    b = m.base.copy()
    ny = b.index.tz_convert("America/New_York")
    td = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)
    first_of_day = np.r_[True, td[1:] != td[:-1]]
    iso = pd.DatetimeIndex(td).isocalendar()
    wk = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    first_of_week = np.r_[True, wk[1:] != wk[:-1]]
    weeks = list(dict.fromkeys(wk))
    w2 = weeks[2]                                                        # a full week with a full week after it
    cand = np.flatnonzero(first_of_day & ~first_of_week & (wk == w2))
    j = int(cand[1])                                                     # e.g. Tuesday's opening bar
    top = float(b["high"].max()) + 50.0
    b.iloc[j, b.columns.get_loc("high")] = top
    m.base = b
    res = engine.run(m, DEFAULT)
    nxt = np.flatnonzero(wk == weeks[3])
    assert np.asarray(res.rows["pwh"], float)[nxt].min() == top          # every bar of the next week sees it


def _applied(R, i):
    return bool(R["tq_floor_veto"][i]) or (DEFAULT.use_risk_limits and bool(R["risk_lock"][i]))


def test_f3_only_the_tq_floor_and_the_risk_lock_block_a_signal():
    shadow_bars = 0
    for seed in (6, 7, 11):
        res = engine.run(load_synthetic("15m", bars=1500, seed=seed), DEFAULT)
        R = res.rows
        for i in range(len(R["should_buy"])):
            buy, sell = bool(R["should_buy"][i]), bool(R["should_sell"][i])
            assert bool(R["exec_buy"][i]) == (buy and not _applied(R, i)), (seed, i)
            assert bool(R["exec_sell"][i]) == (sell and not _applied(R, i)), (seed, i)
            if (buy or sell) and not _applied(R, i) and (bool(R["cal_veto"][i]) or bool(R["ev_veto"][i])):
                shadow_bars += 1                                         # a shadow flag on, the signal still taken
        for e in res.events:
            if e["type"] == "VETO":
                assert e["why"] in ("TQ", "RISK"), e
    assert shadow_bars >= 1, "no bar with a shadow flag on a taken signal: the test could not see the old vetoes"


def test_f3b_trade_quality_does_not_read_the_ev(monkeypatch):
    m = load_synthetic("15m", bars=1200, seed=7)
    base = engine.run(m, DEFAULT).rows
    orig = engine.trade_plan

    def shifted(*a, **k):
        p = dict(orig(*a, **k))
        if not (isinstance(p.get("ev"), float) and math.isnan(p["ev"])):
            p["ev"] = p["ev"] + 3.0                                     # a very different EV on every bar that has one
        return p
    monkeypatch.setattr(engine, "trade_plan", shifted)
    other = engine.run(load_synthetic("15m", bars=1200, seed=7), DEFAULT).rows
    assert any(a != b for a, b in zip(base["plan_ev"], other["plan_ev"]) if not (isinstance(a, float) and math.isnan(a)))
    assert list(base["tq"]) == list(other["tq"])


def test_f4_unused_definitions_are_gone():
    assert not hasattr(C.Config(), "commission_per_oz")
    assert not hasattr(sources, "_empty")


def test_the_proposal_changes_the_freeze_key_and_says_so():
    """Merging this branch restarts the frozen holdout by design: the key differs from production's."""
    assert holdout.freeze_key(DEFAULT) != PRODUCTION_KEY
