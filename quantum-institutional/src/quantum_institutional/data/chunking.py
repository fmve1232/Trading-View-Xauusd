"""Resumable chunked processing. Master prompt section 61.

Historical XAUUSD at 1m resolution is tens of millions of bars. Section 61:
never require the entire dataset in memory. This module supplies the plan and
the checkpoint; the actual fetch and store are the caller's.

A checkpoint records the last COMPLETED chunk. Resuming re-runs nothing that
finished and re-runs everything that did not, which means a chunk handler must
be idempotent -- an interrupted chunk may have written some rows already.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

__all__ = ["Checkpoint", "Chunk", "plan_chunks", "resume_from"]


@dataclass(frozen=True, slots=True)
class Chunk:
    """Half-open interval ``[start, end)``.

    Half-open so that consecutive chunks never both claim the same boundary
    bar, which would duplicate one bar per chunk across a full ingest.
    """

    index: int
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class Checkpoint:
    job_id: str
    last_completed_index: int
    last_completed_end: datetime
    rows_written: int


def plan_chunks(start: datetime, end: datetime, chunk: timedelta) -> list[Chunk]:
    """Split ``[start, end)`` into chunks of at most ``chunk``.

    The final chunk is truncated at ``end`` rather than overshooting, so a plan
    never requests data beyond the requested window.
    """
    if chunk <= timedelta(0):
        raise ValueError("chunk must be positive")
    if end <= start:
        return []
    chunks: list[Chunk] = []
    cursor, index = start, 0
    while cursor < end:
        stop = min(cursor + chunk, end)
        chunks.append(Chunk(index=index, start=cursor, end=stop))
        cursor, index = stop, index + 1
    return chunks


def resume_from(chunks: list[Chunk], checkpoint: Checkpoint | None) -> list[Chunk]:
    """Drop chunks already completed according to ``checkpoint``.

    Matching is by ``end`` timestamp, not by index: a re-plan with a different
    chunk size changes every index but not the timeline, and resuming by index
    after a re-plan would skip or repeat arbitrary spans.
    """
    if checkpoint is None:
        return list(chunks)
    return [c for c in chunks if c.end > checkpoint.last_completed_end]
