"""Point-in-time access -- the leakage tripwire. Sections 30, 70-72."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quantum_institutional.data.contracts import MacroValue
from quantum_institutional.data.pit import assert_no_lookahead, latest_visible, visible_at
from quantum_institutional.errors import LookaheadError

RELEASE_DAY = datetime(2026, 9, 10, tzinfo=UTC)


def cpi(published_at: datetime, value: float, revision_of: str | None = None) -> MacroValue:
    """A CPI print. ``event_time`` is the reference month, deliberately earlier."""
    return MacroValue(
        series_id="CPIAUCSL",
        event_time=datetime(2026, 9, 1, tzinfo=UTC),
        publication_time=published_at,
        value=value,
        source="synthetic",
        received_time=published_at + timedelta(milliseconds=300),
        revision_of=revision_of,
    )


class TestPublicationTimeIsTheOnlyFilter:
    def test_the_1330_utc_example_from_section_30(self) -> None:
        release = RELEASE_DAY.replace(hour=13, minute=30)
        print_ = cpi(release, 3.1)
        assert visible_at([print_], release - timedelta(seconds=1)) == []
        assert visible_at([print_], release) == [print_]

    def test_reference_month_does_not_make_it_visible(self) -> None:
        """The value exists for September but not ON 1 September."""
        release = RELEASE_DAY.replace(hour=13, minute=30)
        print_ = cpi(release, 3.1)
        assert visible_at([print_], datetime(2026, 9, 2, tzinfo=UTC)) == []

    def test_boundary_is_inclusive(self) -> None:
        """A bar and a print at the same instant: a live system sees both."""
        release = RELEASE_DAY.replace(hour=13, minute=30)
        assert len(visible_at([cpi(release, 3.1)], release)) == 1


class TestRevisions:
    def test_the_original_release_is_returned_not_the_revision(self) -> None:
        first = cpi(RELEASE_DAY.replace(hour=13, minute=30), 3.1)
        later = RELEASE_DAY.replace(hour=13, minute=30) + timedelta(days=30)
        revised = cpi(later, 2.9, revision_of="CPIAUCSL")
        as_of = RELEASE_DAY.replace(hour=14)
        assert latest_visible([first, revised], as_of) is first
        assert latest_visible([first, revised], as_of).value == 3.1

    def test_revision_becomes_visible_only_after_it_is_published(self) -> None:
        first = cpi(RELEASE_DAY.replace(hour=13, minute=30), 3.1)
        later = RELEASE_DAY.replace(hour=13, minute=30) + timedelta(days=30)
        revised = cpi(later, 2.9, revision_of="CPIAUCSL")
        assert latest_visible([first, revised], RELEASE_DAY + timedelta(days=40)) is revised


class TestEmptyAndErrors:
    def test_nothing_published_yet_is_none_not_zero(self) -> None:
        assert latest_visible([cpi(RELEASE_DAY, 3.1)], RELEASE_DAY - timedelta(days=1)) is None

    def test_naive_as_of_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            visible_at([], datetime(2026, 9, 10))  # noqa: DTZ001 -- the point of the test

    def test_tripwire_raises_rather_than_degrading(self) -> None:
        release = RELEASE_DAY.replace(hour=13, minute=30)
        with pytest.raises(LookaheadError, match="post-date"):
            assert_no_lookahead([cpi(release, 3.1)], release - timedelta(minutes=1), context="feature build")

    def test_tripwire_passes_on_clean_input(self) -> None:
        release = RELEASE_DAY.replace(hour=13, minute=30)
        assert_no_lookahead([cpi(release, 3.1)], release)
