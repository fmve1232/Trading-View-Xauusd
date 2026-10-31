"""Pine v84-v92 display items ported to the site (2026-11-01). Display only: no engine file, no freeze key change."""
import dataclasses
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from quantum import engine, holdout, news_calendar as nc, notify, report
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic


def _utc(e):
    return datetime.fromtimestamp(e["t"], timezone.utc).strftime("%Y-%m-%d %H:%M")


# ---------------- news calendar (Pine Visuals v86 / v92) ----------------
def test_calendar_is_the_pine_list_in_order_with_correct_dst():
    ev = nc.events()
    assert len(ev) == 38 and [e["t"] for e in ev] == sorted(e["t"] for e in ev)
    assert {e["name"] for e in ev} == {"NFP", "CPI", "FOMC"}
    by = {e["ny"]: e for e in ev}
    assert _utc(by["2026-10-28 14:00"]) == "2026-10-28 18:00"     # FOMC, EDT (UTC-4)
    assert _utc(by["2026-11-06 08:30"]) == "2026-11-06 13:30"     # NFP, EST (UTC-5) after 1 Nov
    assert _utc(by["2027-03-10 08:30"]) == "2027-03-10 13:30"     # CPI, still EST (US DST starts 14 Mar 2027)
    assert _utc(by["2027-03-17 14:00"]) == "2027-03-17 18:00"     # FOMC, EDT again
    assert ev[-1]["ny"].startswith(nc.VALID_UNTIL)
    assert "news_calendar.py" not in holdout.ENGINE_SOURCES


def test_window_boundaries_and_next():
    nfp = next(e for e in nc.events() if e["ny"] == "2026-11-06 08:30")
    t = nfp["t"]
    assert nc.state(t - 30 * 60)["in_window"] == nfp and nc.state(t + 30 * 60)["in_window"] == nfp
    assert nc.state(t - 30 * 60 - 1)["in_window"] is None and nc.state(t + 30 * 60 + 1)["in_window"] is None
    assert nc.state(t - 3600)["next"] == nfp
    assert nc.state(nc.events()[-1]["t"] + 1)["expired"]


# ---------------- checks: session n, churn, swept level ----------------
def test_session_count_rebuilt_from_outputs_matches_the_engine():
    """The engine publishes manip / cont percentages = count * 100 / n (NaN while n < 5). The rebuilt n must make both
    whole counts at every cut, and NaN exactly when n < 5."""
    mk = load_synthetic("1h", bars=900, seed=3)
    for k in (150, 420, 900):
        m = dataclasses.replace(mk, base=mk.base.iloc[:k])
        res = engine.run(m, DEFAULT)
        n = int(report.session_counts(res.F["cal"])[-1])
        se = res.last["session"]
        for pr in (se["manip_prob"], se["cont_prob"]):
            if n < 5:
                assert math.isnan(pr)
            else:
                assert abs(pr * n / 100 - round(pr * n / 100)) < 1e-6


def test_session_count_by_hand():
    idx = pd.date_range("2026-10-05", periods=9, freq="1h", tz="UTC")
    cal = pd.DataFrame({"in_asian": [1, 1, 0, 0, 0, 1, 0, 0, 1], "in_london": [0, 0, 1, 1, 0, 0, 1, 0, 0],
                        "in_ny": [0] * 9}, index=idx).astype(bool)
    # segments: A(0-1) L(2-3) off(4) A(5) L(6) off(7) A(8): at bar 8 two Asian sessions have closed
    assert report.session_counts(cal).tolist() == [0, 0, 0, 0, 0, 1, 1, 0, 2]


def test_churn_counts_direction_changes_in_the_last_20_bars():
    c = np.linspace(100, 110, 60)
    ev = [{"i": 10, "type": "BOS", "dir": 1}, {"i": 45, "type": "CHoCH", "dir": -1}, {"i": 50, "type": "BOS", "dir": 1},
          {"i": 52, "type": "BOS", "dir": 1}, {"i": 55, "type": "MSS", "dir": -1}, {"i": 55, "type": "BOS", "dir": 1}]
    ch = report.churn(ev, c)
    # last 20 bars = 40..59: bar 45 (+1 -> -1), bar 50 (-1 -> +1), bar 55 (bearish first -> -1); bar 10 is outside
    assert ch["flips"] == 3 and ch["churn"]
    assert report.churn(ev[:3], c)["flips"] == 2 and report.churn(ev[:2], c)["flips"] == 1 and not report.churn(ev[:2], c)["churn"]
    assert ch["efficiency"] == pytest.approx(1.0)           # a straight line: efficiency 1
    zig = np.array([100.0, 101.0] * 30)
    assert report.churn([], zig)["efficiency"] == pytest.approx(0.0) and report.churn([], zig)["flips"] == 0


def test_swept_levels_use_the_engine_condition():
    n = 3
    F = {"l": np.array([0, 0, 1989.0]), "h": np.array([0, 0, 2001.0]), "c": np.array([0, 0, 1995.0]),
         "pm_low": np.full(n, 1992.0), "pm_high": np.full(n, 2000.0)}
    R = {"pdl": np.full(n, 1990.0), "pwl": np.full(n, 1985.0), "pdh": np.full(n, 2005.0), "pwh": np.full(n, np.nan)}
    assert [x["name"] for x in report.swept_levels(R, F, 2, 1)] == ["PDL", "PML"]     # 1985 not touched
    assert [x["name"] for x in report.swept_levels(R, F, 2, -1)] == ["PMH"]           # PDH not reached, PWH NaN


# ---------------- alerts ----------------
def test_sweep_alert_names_the_level_and_news_alert_fires_once():
    payload = {"meta": {"tf": "15m"}, "markers": [{"t": 100, "type": "SWEEP", "dir": 1, "px": 1989.0,
                                                   "lvl": [{"name": "PDL", "px": 1990.0}]}], "decisions": []}
    lines = notify.structure_lines(payload, 50)
    assert lines and "SWEEP-LOW PDL 1990.00" in lines[0]
    news = nc.export()
    nfp = next(e for e in news["events"] if e["ny"] == "2026-11-06 08:30")
    out, last = notify.news_lines(news, nfp["t"] - 10 * 60, None)
    assert len(out) == 1 and "NFP" in out[0] and "13:30 UTC" in out[0] and last == nfp["t"]
    assert notify.news_lines(news, nfp["t"] + 5 * 60, last)[0] == []                  # once per event
    assert notify.news_lines(news, nfp["t"] - 3 * 3600, None)[0] == []                # not before the window


def test_report_payload_carries_checks_and_news_and_keys_are_unchanged():
    from quantum import arm_h2, arm_h3, arm_h4, arm_h5, arm_h6
    k = holdout.freeze_key(DEFAULT)
    assert k == "5e4630924d663fc5:60bb01794d03c9ac"
    assert [m.freeze_key(k)[-16:] for m in (arm_h2, arm_h3, arm_h4, arm_h5, arm_h6)] == \
        ["19433c9889d94f09", "0eb650f81d99803e", "090418672c210848", "40d438ea0c144199", "7c4ac023578836c6"]
    for f in ("report.py", "notify.py", "news_calendar.py", "cost_profiles.py"):
        assert f not in holdout.ENGINE_SOURCES
