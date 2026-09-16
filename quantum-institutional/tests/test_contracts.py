"""Contract invariants. Sections 7 and 8."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from tests.conftest import make_bar

from quantum_institutional.data.contracts import Quote, Timeframe, VolumeType
from quantum_institutional.errors import Quality


class TestTimezoneEnforcement:
    def test_naive_datetime_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            make_bar(start=datetime(2026, 1, 5))  # noqa: DTZ001 -- the point of the test

    def test_non_utc_offset_is_rejected(self) -> None:
        """A correct instant in the wrong zone is still rejected.

        Accepting it would mean bars sort correctly and compare correctly while
        every session boundary is off by the offset.
        """
        ny = timezone(timedelta(hours=-5))
        with pytest.raises(ValueError, match="must be UTC"):
            make_bar(start=datetime(2026, 1, 5, tzinfo=ny))


class TestBar:
    @pytest.mark.parametrize(
        ("open_", "high", "low", "close", "consistent"),
        [
            (100.0, 101.0, 99.0, 100.5, True),
            (100.0, 100.0, 100.0, 100.0, True),  # flat bar is consistent
            (100.0, 99.0, 99.0, 100.0, False),  # high below open
            (100.0, 101.0, 100.5, 100.2, False),  # low above close
        ],
    )
    def test_ohlc_consistency(
        self, open_: float, high: float, low: float, close: float, consistent: bool
    ) -> None:
        bar = make_bar(open_=open_, high=high, low=low, close=close)
        assert bar.is_ohlc_consistent is consistent

    def test_close_time_is_exclusive(self) -> None:
        """The next bar opens exactly where this one closes -- no overlap, no gap."""
        first, second = make_bar(0), make_bar(1)
        assert first.close_time == second.event_time

    def test_volume_may_be_absent_without_becoming_zero(self) -> None:
        """Absent volume and zero volume are different claims (section 83)."""
        bar = make_bar(volume=None, volume_type=VolumeType.NONE)
        assert bar.volume is None


class TestQuote:
    def test_spread_and_mid(self) -> None:
        now = datetime(2026, 1, 5, tzinfo=UTC)
        quote = Quote("XAUUSD", now, bid=2000.0, ask=2000.4, source="synthetic", received_time=now)
        assert quote.mid == 2000.2
        assert round(quote.spread, 10) == 0.4

    def test_latency_is_measured_from_event_to_receipt(self) -> None:
        now = datetime(2026, 1, 5, tzinfo=UTC)
        quote = Quote("XAUUSD", now, 2000.0, 2000.4, "synthetic", now + timedelta(milliseconds=250))
        assert quote.latency_s == pytest.approx(0.25)


class TestQuality:
    def test_worst_input_wins(self) -> None:
        """One stale input degrades the output; it is not averaged away."""
        assert Quality.worst(Quality.OK, Quality.STALE, Quality.OK) is Quality.STALE

    def test_only_ok_and_degraded_may_back_a_signal(self) -> None:
        assert Quality.OK.is_tradeable
        assert Quality.DEGRADED.is_tradeable
        assert not Quality.STALE.is_tradeable
        assert not Quality.INVALID.is_tradeable
        assert not Quality.OFFLINE.is_tradeable

    def test_no_inputs_is_ok_not_offline(self) -> None:
        """A computation with no external inputs cannot be stale."""
        assert Quality.worst() is Quality.OK


class TestTimeframe:
    def test_every_timeframe_is_a_whole_number_of_minutes(self) -> None:
        for timeframe in Timeframe:
            assert timeframe.seconds % 60 == 0, timeframe
            assert timeframe.is_derivable, timeframe

    def test_seconds_are_strictly_increasing_in_declaration_order(self) -> None:
        """Guards a typo in the lookup table that would break aggregation checks."""
        values = [tf.seconds for tf in Timeframe]
        assert values == sorted(values) and len(set(values)) == len(values)
