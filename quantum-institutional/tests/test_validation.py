"""Section 12 validation checks."""

from __future__ import annotations

from datetime import timedelta

from tests.conftest import EPOCH, make_bar

from quantum_institutional.data.contracts import Timeframe, VolumeType
from quantum_institutional.data.validation import validate_bars
from quantum_institutional.errors import Quality


def test_clean_series_passes(minute_bars) -> None:
    report = validate_bars(minute_bars, Timeframe.M1)
    assert report.ok
    assert report.quality is Quality.OK
    assert report.total == 5


def test_empty_series_is_an_issue_not_a_vacuous_pass() -> None:
    """ "Zero bars, no problems" is the report most likely to be misread."""
    report = validate_bars([], Timeframe.M1)
    assert not report.ok
    assert "empty_dataset" in report.by_check()


def test_ohlc_violation_is_fatal(minute_bars) -> None:
    minute_bars[2] = make_bar(2, open_=100.0, high=99.0, low=98.0, close=98.5)
    report = validate_bars(minute_bars, Timeframe.M1)
    assert report.quality is Quality.INVALID
    assert report.by_check()["ohlc_consistency"] == 1


def test_gap_is_degraded_not_invalid(minute_bars) -> None:
    """A hole in the data is usable with a known hole; contradictory data is not."""
    del minute_bars[2]
    report = validate_bars(minute_bars, Timeframe.M1)
    assert report.quality is Quality.DEGRADED
    assert report.by_check()["gap"] == 1
    assert "1 missing bar(s)" in report.issues[0].detail


def test_duplicate_timestamp_is_detected(minute_bars) -> None:
    minute_bars.append(make_bar(2))
    report = validate_bars(minute_bars, Timeframe.M1)
    assert report.by_check()["duplicate_timestamp"] == 1


def test_out_of_order_bars_are_detected(minute_bars) -> None:
    minute_bars[1], minute_bars[3] = minute_bars[3], minute_bars[1]
    report = validate_bars(minute_bars, Timeframe.M1)
    assert "chronological_order" in report.by_check()
    assert report.quality is Quality.INVALID


def test_off_grid_timestamp_is_detected() -> None:
    """A feed labelling bars by CLOSE time lands every bar off the open grid."""
    shifted = make_bar(0, start=EPOCH + timedelta(seconds=17))
    report = validate_bars([shifted], Timeframe.M1)
    assert "timeframe_alignment" in report.by_check()


def test_negative_volume_is_detected() -> None:
    report = validate_bars([make_bar(0, volume=-1.0)], Timeframe.M1)
    assert "negative_volume" in report.by_check()


def test_missing_volume_is_optional() -> None:
    bars = [make_bar(0, volume=None, volume_type=VolumeType.NONE)]
    assert "missing_volume" in validate_bars(bars, Timeframe.M1).by_check()
    assert validate_bars(bars, Timeframe.M1, expect_volume=False).ok


def test_timeframe_mismatch_is_detected(minute_bars) -> None:
    report = validate_bars(minute_bars, Timeframe.M5)
    assert "timeframe_mismatch" in report.by_check()
