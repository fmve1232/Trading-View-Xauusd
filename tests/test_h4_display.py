"""research/03 §7 display fixes: the archived previous-engine record and the entry overshoot (display only)."""
import json
import math

import pytest

from quantum import holdout, report
from quantum.config import DEFAULT

OLD = "5e4630924d663fc5:6f3964ad97813cc9:090418672c210848"
OTHER = "5e4630924d663fc5:92b67584f33cc1f0:090418672c210848"


def _t(r, k=OLD, et="2026-10-20T10:00:00+00:00"):
    return {"r": r, "pts": r * 5, "tp1_hit": r > 0, "bars": 3, "dir": "LONG", "exit_reason": "SL" if r < 0 else "TP2",
            "open": False, "freeze_key": k, "entry_time": et}


def test_previous_record_reads_only_the_previous_key(tmp_path):
    arch = tmp_path / "holdout" / "archive"
    arch.mkdir(parents=True)
    led = [_t(-1.0), _t(1.0), _t(-0.5), _t(2.0, OTHER), dict(_t(1.0), open=True)]
    (arch / "15m_h4.json").write_text(json.dumps(led))
    man4 = {"history": [{"freeze_key": OTHER, "freeze_utc": "2026-10-11"}, {"freeze_key": OLD, "freeze_utc": "2026-10-17T21:26:18", "ended_utc": "2026-10-31T17:23:01"}]}
    man = {"history": [{"freeze_key": OLD.rsplit(":", 1)[0], "engine_version": "Q7.2-web.6"}]}
    p = report.previous_record(str(tmp_path), "15m", "h4", man4, man, DEFAULT)
    assert p["n"] == 3 and p["engine_version"] == "Q7.2-web.6"            # OTHER key and the open trade excluded
    assert p["avg_r"] == pytest.approx(-0.5 / 3) and p["win_rate"] == pytest.approx(100 / 3)
    assert p["from"].startswith("2026-10-17") and p["to"].startswith("2026-10-31")
    assert report.previous_record(str(tmp_path), "1h", "h4", man4, man, DEFAULT) is None   # no archive file
    assert report.previous_record(str(tmp_path), "15m", "h4", {"history": []}, man, DEFAULT) is None


def test_entry_based_reward_risk_formula():
    """Entry e = trigger + ov*D beyond: risk D(1+ov), reward |tp1 - trigger| - ov*D -> (rr - ov) / (1 + ov)."""
    trig, D, tp1, ov = 100.0, 10.0, 121.0, 0.24
    e = trig + ov * D
    want = (tp1 - e) / (e - (trig - D))
    assert want == pytest.approx((2.1 - ov) / (1 + ov))
    assert math.isclose(want, 1.5, abs_tol=0.01)


def test_keys_unchanged():
    assert holdout.freeze_key(DEFAULT) == "5e4630924d663fc5:60bb01794d03c9ac"
