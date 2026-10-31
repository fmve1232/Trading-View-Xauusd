"""Amendment 11 research history: paging backwards to the floor or the feed's first bar, then forwards; no duplicates."""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from quantum.data import store
from quantum.research import history

FEED_START = pd.Timestamp("2018-06-01", tz="UTC")
NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
ALL = pd.date_range(FEED_START, NOW, freq="1h", tz="UTC")


def feed(symbol, interval, apikey, end=None, start=None):
    idx = ALL[ALL <= end][-history.PAGE:] if end is not None else ALL[ALL >= start][: history.PAGE]
    if not len(idx):
        return None
    v = np.arange(len(idx), dtype=float) + 2000.0
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1, "close": v, "volume": 0.0}, index=idx)


def test_backfills_to_the_feeds_first_bar_then_stops(tmp_path):
    rec = history.backfill(str(tmp_path), "XAU/USD", "1h", "KEY", "2010-01-01", fetch=feed, sleep_s=0, now=NOW, log=lambda *_: None)
    got = store.load(str(tmp_path), history.series_name("XAU/USD", "1h"))
    assert got.index.min() == FEED_START and got.index.max() == ALL[-1]
    assert got.index.is_unique and len(got) == len(ALL)
    assert rec["stop"] == "the feed has no older bars" and rec["rows"] == len(ALL)
    log = [json.loads(x) for x in open(tmp_path / "_history_log.jsonl")]
    assert log[-1]["series"] == "TD_XAU_USD_1h" and "KEY" not in open(tmp_path / "_history_log.jsonl").read()


def test_respects_the_floor_and_resumes(tmp_path):
    history.backfill(str(tmp_path), "XAU/USD", "1h", "K", "2024-01-01", fetch=feed, sleep_s=0, now=NOW, log=lambda *_: None)
    got = store.load(str(tmp_path), "TD_XAU_USD_1h")
    assert got.index.min() >= pd.Timestamp("2024-01-01", tz="UTC")
    rec = history.backfill(str(tmp_path), "XAU/USD", "1h", "K", "2024-01-01", fetch=feed, sleep_s=0, now=NOW, log=lambda *_: None)
    assert rec["stop"] == "reached the start date" and rec["calls"] == 1      # nothing older to fetch; one forward call


def test_max_calls_bounds_one_run(tmp_path):
    rec = history.backfill(str(tmp_path), "XAU/USD", "1h", "K", "2010-01-01", fetch=feed, sleep_s=0, now=NOW, max_calls=2, log=lambda *_: None)
    assert rec["calls"] == 2 and rec["stop"] == "max calls"


def test_an_error_is_logged_with_the_key_redacted(tmp_path):
    def bad(symbol, interval, apikey, end=None, start=None):
        raise RuntimeError("https://api.twelvedata.com/time_series?apikey=SECRET -> plan limit")
    try:
        history.backfill(str(tmp_path), "XAU/USD", "1h", "SECRET", "2010-01-01", fetch=bad, sleep_s=0, now=NOW, log=lambda *_: None)
        raise AssertionError("expected an error")
    except Exception as e:  # noqa: BLE001
        assert "SECRET" not in str(e)
    rec = json.loads(open(tmp_path / "_history_log.jsonl").read().splitlines()[-1])
    assert rec["stop"] == "error" and "plan limit" in rec["error"] and "SECRET" not in rec["error"]


def test_minute_limit_waits_and_day_limit_stops_cleanly(tmp_path):
    n = {"k": 0}

    def flaky(symbol, interval, apikey, end=None, start=None):
        n["k"] += 1
        if n["k"] == 2:
            raise history.MinuteLimit("run out of api credits for the current minute")
        if n["k"] == 4:
            raise history.DayLimit("run out of api credits for the day")
        return feed(symbol, interval, apikey, end=end, start=start)
    rec = history.backfill(str(tmp_path), "XAU/USD", "1h", "K", "2010-01-01", fetch=flaky, sleep_s=0, now=NOW, log=lambda *_: None)
    assert rec["stop"] == "daily credit limit (resumes next run)" and rec["error"] is None and rec["rows"] == 2 * history.PAGE
    rec = history.backfill(str(tmp_path), "XAU/USD", "1h", "K", "2010-01-01", fetch=feed, sleep_s=0, now=NOW, log=lambda *_: None)
    assert rec["stop"] == "the feed has no older bars" and rec["rows"] == len(ALL)        # the next run resumes


def test_404_before_the_first_bar_is_the_end_of_the_feed(tmp_path):
    from quantum.data import sources

    def feed404(symbol, interval, apikey, end=None, start=None):
        if end is not None and end < FEED_START:
            raise sources.FetchError("https://api.twelvedata.com/time_series -> HTTP 404")
        return feed(symbol, interval, apikey, end=end, start=start)
    rec = history.backfill(str(tmp_path), "XAU/USD", "1h", "K", "2010-01-01", fetch=feed404, sleep_s=0, now=NOW, log=lambda *_: None)
    assert rec["stop"] == "the feed has no older bars" and rec["error"] is None and rec["first"] == FEED_START.isoformat()


def test_load_drops_market_shut_bars(tmp_path):
    """D-R1: the research loader removes the 24/7 quote bars printed while spot gold is shut."""
    from quantum.data import store
    idx = pd.date_range("2025-03-07 20:00", "2025-03-09 23:00", freq="1h", tz="UTC")   # Fri 20:00 .. Sun 23:00 UTC
    df = pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 0.0}, index=idx)
    store.save(str(tmp_path), history.series_name("XAU/USD", "1h"), df)
    got = history.load(str(tmp_path), "XAU/USD", "1h")
    assert 0 < len(got) < len(df)
    assert not (got.index.dayofweek == 5).any()                       # no Saturday bars
    assert got.index.min() == idx[0] and got.index.max() == idx[-1]    # Friday before the close and Sunday after the open kept
