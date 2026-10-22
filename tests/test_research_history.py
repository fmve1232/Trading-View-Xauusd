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
