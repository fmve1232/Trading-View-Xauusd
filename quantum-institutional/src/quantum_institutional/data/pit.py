"""Point-in-time access. Master prompt sections 30, 70, 71, 72.

This is the smallest module in the package and the one most likely to decide
whether any backtest result is real.

THE RULE
--------
A query for "what did the system know at time T" returns only records whose
``publication_time <= T``. Not ``event_time`` -- the September CPI reference
month begins on 1 September and the number does not exist until 13:30 UTC on
release day. Not ``received_time`` -- that is a property of this machine, and
filtering on it makes a backtest irreproducible on different hardware.

REVISIONS
---------
A macro series gets revised. The revised value did not exist at T, so
:func:`visible_at` returns the ORIGINAL release. This is why
:class:`~quantum_institutional.data.contracts.MacroValue` keeps
``revision_of`` rather than overwriting in place: an overwrite is
unrecoverable, and it silently improves every historical backtest.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, TypeVar

from ..errors import LookaheadError

__all__ = ["Publishable", "assert_no_lookahead", "latest_visible", "visible_at"]


class Publishable(Protocol):
    """Anything with a publication time."""

    publication_time: datetime


T = TypeVar("T", bound=Publishable)


def visible_at(records: Iterable[T], as_of: datetime) -> list[T]:
    """Records publicly available at ``as_of``, oldest first.

    The comparison is ``<=``: a record published exactly at ``as_of`` IS
    visible. That choice matters at event boundaries -- a bar timestamped
    13:30:00 and a CPI print published 13:30:00 are simultaneous, and excluding
    the print would understate what a live system would have seen.

    Ties are broken by publication time only; the input order is otherwise
    preserved, so two records with the same publication time keep their
    ingestion order rather than being reordered non-deterministically.
    """
    _require_utc(as_of)
    visible = [r for r in records if r.publication_time <= as_of]
    visible.sort(key=lambda r: r.publication_time)
    return visible


def latest_visible(records: Iterable[T], as_of: datetime) -> T | None:
    """Most recent record available at ``as_of``, or ``None``.

    ``None`` means "nothing was published yet", which is a real state at the
    start of a series and must be handled by the caller. It is not an error and
    it is not zero.
    """
    visible = visible_at(records, as_of)
    return visible[-1] if visible else None


def assert_no_lookahead(records: Iterable[T], as_of: datetime, *, context: str = "") -> None:
    """Raise if any record post-dates ``as_of``.

    Use this as a tripwire inside feature computation, where the filtering has
    supposedly already happened. It raises :class:`LookaheadError` rather than
    degrading, because a leak is a bug in the code, not a gap in the data --
    degrading would hide it behind a quality flag and let the backtest finish.
    """
    _require_utc(as_of)
    leaked = [r for r in records if r.publication_time > as_of]
    if leaked:
        first = min(r.publication_time for r in leaked)
        raise LookaheadError(
            f"{len(leaked)} record(s) post-date as_of={as_of.isoformat()}; "
            f"earliest leak at {first.isoformat()}" + (f" [{context}]" if context else "")
        )


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"as_of must be timezone-aware UTC; got naive {value!r}")
