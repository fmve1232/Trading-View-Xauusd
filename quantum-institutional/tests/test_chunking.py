"""Section 61 chunk planning and resume."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from quantum_institutional.data.chunking import Checkpoint, plan_chunks, resume_from

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_chunks_tile_the_window_without_overlap() -> None:
    chunks = plan_chunks(START, START + timedelta(days=10), timedelta(days=3))
    assert (chunks[0].start, chunks[0].end) == (START, START + timedelta(days=3))
    for earlier, later in pairwise(chunks):
        assert earlier.end == later.start  # half-open: no boundary bar is in two chunks


def test_final_chunk_is_truncated_not_overshot() -> None:
    end = START + timedelta(days=10)
    assert plan_chunks(START, end, timedelta(days=3))[-1].end == end


def test_empty_and_inverted_windows_produce_no_chunks() -> None:
    assert plan_chunks(START, START, timedelta(days=1)) == []
    assert plan_chunks(START + timedelta(days=1), START, timedelta(days=1)) == []


def test_non_positive_chunk_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        plan_chunks(START, START + timedelta(days=1), timedelta(0))


def test_resume_drops_completed_chunks() -> None:
    chunks = plan_chunks(START, START + timedelta(days=10), timedelta(days=3))
    checkpoint = Checkpoint("job", last_completed_index=1, last_completed_end=chunks[1].end, rows_written=10)
    assert [c.index for c in resume_from(chunks, checkpoint)] == [2, 3]


def test_resume_matches_on_timestamp_so_a_replan_is_safe() -> None:
    """Re-planning with a different chunk size renumbers every index.

    Resuming by index after a re-plan would skip or repeat arbitrary spans;
    matching on the timeline cannot.
    """
    original = plan_chunks(START, START + timedelta(days=12), timedelta(days=3))
    checkpoint = Checkpoint(
        "job", last_completed_index=1, last_completed_end=original[1].end, rows_written=10
    )
    replanned = plan_chunks(START, START + timedelta(days=12), timedelta(days=2))
    remaining = resume_from(replanned, checkpoint)
    assert all(c.start >= checkpoint.last_completed_end for c in remaining)
    assert remaining[0].start == checkpoint.last_completed_end


def test_no_checkpoint_means_run_everything() -> None:
    chunks = plan_chunks(START, START + timedelta(days=6), timedelta(days=2))
    assert resume_from(chunks, None) == chunks
