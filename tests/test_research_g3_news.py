"""quantum/research/g3_news.py (G3-NEWS): timestamp verification between two sources, windows, races, the market check,
block rules and stop behaviour, worked by hand. No research data and no network needed."""
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from quantum.research import b8_news
from quantum.research import g3_news as G
from quantum.research import harness as H

NY = ZoneInfo("America/New_York")


def test_an_event_enters_only_when_both_sources_agree():
    cpi = [d for d in b8_news.DATES["CPI"] if d >= "2021-01-01"][:3]
    official = {"CPI": {"dates": [*cpi[:2], "2021-03-11"]},              # one date differs from B8's
                "NFP": {"dates": []},                                   # official reading unavailable
                "FOMC": {"statement_dates": b8_news.DATES["FOMC"][:2], "press_conference_dates": ["2020-04-29"]},
                "PCE": {"dates": ["2021-01-29"]}}
    v = G.verify(official)
    kinds = {(e["kind"], e["date"]) for e in v["agreed"]}
    assert ("CPI", cpi[0]) in kinds and ("CPI", cpi[1]) in kinds and ("CPI", "2021-03-11") not in kinds
    assert {"kind": "CPI", "date": cpi[2], "in": "B8 only"} in v["disagreements"]
    assert {"kind": "CPI", "date": "2021-03-11", "in": "official only"} in v["disagreements"]
    assert v["counts"]["NFP"] == 0 and any(d["kind"] == "NFP" and d["date"] is None for d in v["disagreements"])
    assert v["counts"]["FOMC_PRESS"] == 1 and v["counts"]["PCE"] == 1
    assert next(e for e in v["agreed"] if e["kind"] == "PCE")["needs_market_check"]
    assert any(e["kind"] == "FOMC_STATEMENT" and e["date"] == "2020-01-29" for e in v["agreed"])   # inside (from 2020-01-24)
    assert G.verify({"CPI": {"dates": ["2019-12-11"]}})["counts"]["CPI"] == 0                     # before the partition
    # release instants in New York time, daylight saving handled
    assert datetime.fromtimestamp(G.utc("CPI", "2021-07-13"), NY).strftime("%H:%M") == "08:30"
    assert datetime.fromtimestamp(G.utc("FOMC_PRESS", "2021-01-27"), NY).strftime("%H:%M") == "14:30"


def test_windows_by_hand():
    e = {"kind": "CPI", "date": "2021-07-13", "t": G.utc("CPI", "2021-07-13")}
    assert G.window_of(e["t"] - 31 * 60, [e])[0] == "NORMAL"
    assert G.window_of(e["t"] - 30 * 60, [e])[0] == "PRE"
    assert G.window_of(e["t"], [e])[0] == "DURING"
    assert G.window_of(e["t"] + 15 * 60, [e])[0] == "POST"
    assert G.window_of(e["t"] + 119 * 60, [e])[0] == "LATE"
    assert G.window_of(e["t"] + 120 * 60, [e])[0] == "NORMAL"


def _p5(rows, start):
    t = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC").as_unit("s").asi8
    a = np.array(rows, float)
    return {"t": t, "o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3]}


def test_race_by_hand():
    P5 = _p5([(2000, 2003, 1999, 2002), (2002, 2011, 2001, 2010), (2010, 2010, 1980, 1985)], "2021-07-13T12:30:00Z")
    t0 = int(P5["t"][0])
    assert G.race(P5, t0, True, 2000.0, 1990.0, 2010.0) == "TARGET"
    assert G.race(P5, t0, True, 2000.0, 1990.0, 2020.0) == "STOP"
    assert G.race(P5, t0, False, 2000.0, 2011.0, 1990.0) == "STOP"         # bar 2 touches both: the stop
    assert G.race(P5, t0 + 86400 * 30, True, 2000.0, 1990.0, 2010.0) == "NONE"


def test_market_ratio_by_hand():
    idx = pd.date_range("2021-06-01", "2021-08-31", freq="15min", tz="UTC")
    df = pd.DataFrame({"open": 1800.0, "high": 1801.0, "low": 1799.0, "close": 1800.0}, index=idx)   # range 2
    t = G.utc("CPI", "2021-07-13")
    df.loc[pd.Timestamp(t, unit="s", tz="UTC"), ["high", "low"]] = [1806.0, 1796.0]                  # range 10
    assert G.market_ratio(df, t, {"2021-07-13"}) == 5.0
    assert G.market_ratio(df, t + 60, {"2021-07-13"}) is None                                       # not on a bar


def _trade(entry_time, exit_time, r, **kw):
    t = {"dir": "LONG", "entry_time": entry_time, "exit_time": exit_time, "entry": 2000.0, "sl": 1990.0, "tp1": 2010.0,
         "r": r, "exit": 2000.0, "exit_reason": "FLIP", "open": False}
    t.update(kw)
    return t


def test_block_rules_and_stop_behaviour_by_hand():
    e = {"kind": "CPI", "date": "2021-07-13", "t": G.utc("CPI", "2021-07-13")}     # 12:30 UTC
    P5 = _p5([(2000, 2011, 1999, 2010)] * 300, "2021-07-13T10:00:00Z")
    tr = [_trade("2021-07-13T12:15:00+00:00", "2021-07-13T13:00:00+00:00", 1.0),   # fills 12:30: at the release
          _trade("2021-07-13T11:00:00+00:00", "2021-07-13T13:30:00+00:00", -1.0, exit_reason="SL_GAP", exit=1985.0),
          _trade("2021-07-14T11:00:00+00:00", "2021-07-14T12:00:00+00:00", 0.5)]
    b = G.blocks(tr, 900, [e], P5, H.seeded_rng(1))
    assert b["no entry -15..+15"]["removed"] == 1 and b["no entry -15..+15"]["removed_mean_net_r"] == 1.0
    assert b["no entry -15..+15"]["false_exclusion_share"] == 1.0                    # it reached TP1 first
    assert b["no entry -30..+60"]["removed"] == 1                                    # 11:15 fill is 75 min before
    assert b["no hold across"]["removed"] == 1 and b["no hold across"]["removed_mean_net_r"] == -1.0
    assert b["no hold across"]["change_mean_net_r"] == round(0.75 - 0.5 / 3 * 1, 4)
    s = G.stop_behaviour(tr, 900, [e])
    # stop behaviour counts every trade whose life [fill, exit) contains the release, the one filled at it included;
    # the hold-across block removes only positions opened BEFORE the release
    assert s["with_release"]["trades"] == 2 and s["with_release"]["gap_exits"] == 1
    assert s["with_release"]["mean_gap_beyond_stop_usd"] == 5.0 and s["without"]["trades"] == 1


def test_bootstrap_and_corrections_by_hand():
    rng = H.seeded_rng(0)
    assert G.boot_mean([0.5], rng)["ci95"] is None
    bm = G.boot_mean([1.0] * 10, rng)
    assert bm["mean"] == 1.0 and bm["ci95"] == [1.0, 1.0] and bm["p_two_sided"] == 0.0
    assert G.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06] and G.bh([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]
