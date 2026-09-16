"""Section 11 aggregation: deterministic, no lookahead, unit-safe volume."""

from __future__ import annotations

import pytest
from tests.conftest import EPOCH, make_bar

from quantum_institutional.data.aggregation import aggregate, bucket_start
from quantum_institutional.data.contracts import Timeframe, VolumeType
from quantum_institutional.errors import Quality


def five_minutes() -> list:
    """Five 1m bars whose OHLC makes the aggregate's identity checkable."""
    return [
        make_bar(0, open_=100.0, high=101.0, low=99.5, close=100.5),
        make_bar(1, open_=100.5, high=103.0, low=100.0, close=102.0),  # the high
        make_bar(2, open_=102.0, high=102.5, low=98.0, close=99.0),  # the low
        make_bar(3, open_=99.0, high=100.0, low=98.5, close=99.5),
        make_bar(4, open_=99.5, high=100.5, low=99.0, close=100.2),  # the close
    ]


class TestOhlcv:
    def test_ohlc_comes_from_first_max_min_last(self) -> None:
        bar = aggregate(five_minutes(), Timeframe.M5)[0]
        assert (bar.open, bar.high, bar.low, bar.close) == (100.0, 103.0, 98.0, 100.2)

    def test_volume_sums_when_the_type_is_uniform(self) -> None:
        bar = aggregate(five_minutes(), Timeframe.M5)[0]
        assert bar.volume == 500.0
        assert bar.volume_type is VolumeType.TICK

    def test_mixed_volume_types_produce_none_not_a_meaningless_sum(self) -> None:
        """Section 7: tick counts and exchange contracts do not add."""
        bars = five_minutes()
        bars[2] = make_bar(2, open_=102.0, high=102.5, low=98.0, close=99.0, volume_type=VolumeType.EXCHANGE)
        aggregated = aggregate(bars, Timeframe.M5)[0]
        assert aggregated.volume is None
        assert aggregated.volume_type is VolumeType.NONE

    def test_bar_is_left_aligned_to_the_bucket_start(self) -> None:
        assert aggregate(five_minutes(), Timeframe.M5)[0].event_time == EPOCH


class TestNoLookahead:
    def test_incomplete_bucket_is_dropped_by_default(self) -> None:
        """The last bucket of a live series has a close that has not happened."""
        assert aggregate(five_minutes()[:3], Timeframe.M5) == []

    def test_incomplete_bucket_is_degraded_when_explicitly_requested(self) -> None:
        bar = aggregate(five_minutes()[:3], Timeframe.M5, include_partial=True)[0]
        assert bar.quality is Quality.DEGRADED

    def test_only_the_trailing_bucket_is_partial(self) -> None:
        bars = [make_bar(i) for i in range(7)]  # one full 5m bucket plus two bars
        assert len(aggregate(bars, Timeframe.M5)) == 1
        assert len(aggregate(bars, Timeframe.M5, include_partial=True)) == 2


class TestQualityPropagation:
    def test_worst_source_quality_wins(self) -> None:
        bars = five_minutes()
        bars[1] = make_bar(1, open_=100.5, high=103.0, low=100.0, close=102.0)
        object.__setattr__(bars[1], "quality", Quality.STALE)
        assert aggregate(bars, Timeframe.M5)[0].quality is Quality.STALE


class TestRejections:
    def test_non_multiple_timeframe_is_rejected(self) -> None:
        """3m into 5m would straddle buckets; refuse rather than approximate."""
        bars = [make_bar(i, timeframe=Timeframe.M3) for i in range(5)]
        with pytest.raises(ValueError, match="whole multiple"):
            aggregate(bars, Timeframe.M5)

    def test_downsampling_is_rejected(self) -> None:
        bars = [make_bar(i, timeframe=Timeframe.M5) for i in range(3)]
        with pytest.raises(ValueError, match="shorter"):
            aggregate(bars, Timeframe.M1)

    def test_weekly_is_refused_rather_than_thursday_anchored(self) -> None:
        """The Unix epoch is a Thursday. Silent Thursday weeks would be wrong."""
        with pytest.raises(ValueError, match="session calendar"):
            aggregate(five_minutes(), Timeframe.W1)

    def test_mixed_symbols_are_rejected(self) -> None:
        bars = five_minutes()
        bars[1] = make_bar(1, symbol="XAGUSD")
        with pytest.raises(ValueError, match="mixed symbols"):
            aggregate(bars, Timeframe.M5)

    def test_empty_input_is_empty_output(self) -> None:
        assert aggregate([], Timeframe.M5) == []


class TestDeterminism:
    def test_input_order_does_not_change_the_result(self) -> None:
        forward = aggregate(five_minutes(), Timeframe.M5)
        reversed_ = aggregate(list(reversed(five_minutes())), Timeframe.M5)
        assert forward == reversed_

    def test_bucket_start_is_idempotent(self) -> None:
        start = bucket_start(EPOCH.replace(minute=37), Timeframe.H1)
        assert bucket_start(start, Timeframe.H1) == start
