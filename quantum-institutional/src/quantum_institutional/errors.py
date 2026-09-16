"""Failure vocabulary. Master prompt sections 68 and 83.

The rule these types enforce: a missing input must never become a silent
number. Every function that cannot compute an honest answer either raises
:class:`DataUnavailable` or returns a value whose :class:`Quality` says it is
not trustworthy. Nothing substitutes a default and carries on.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["DataUnavailable", "LookaheadError", "Quality", "QuantumError", "ValidationFailed"]


class Quality(StrEnum):
    """Trust level attached to any value that leaves an engine.

    Ordered worst-to-best is deliberate: a pipeline stage takes the MINIMUM of
    its inputs' qualities, so one stale input degrades the result rather than
    being averaged away.
    """

    OFFLINE = "OFFLINE"  # the source is not reachable at all
    INVALID = "INVALID"  # present but failed validation; do not use
    STALE = "STALE"  # last good value, older than its freshness budget
    DEGRADED = "DEGRADED"  # usable, but a non-critical input is missing
    OK = "OK"

    @property
    def rank(self) -> int:
        return _QUALITY_ORDER.index(self)

    @classmethod
    def worst(cls, *qualities: Quality) -> Quality:
        """Combine input qualities. One STALE input makes the output STALE."""
        if not qualities:
            return cls.OK
        return min(qualities, key=lambda q: q.rank)

    @property
    def is_tradeable(self) -> bool:
        """Only OK and DEGRADED may back a production signal (section 41)."""
        return self in (Quality.OK, Quality.DEGRADED)


_QUALITY_ORDER = [
    Quality.OFFLINE,
    Quality.INVALID,
    Quality.STALE,
    Quality.DEGRADED,
    Quality.OK,
]


class QuantumError(Exception):
    """Base for every error this package raises."""


class DataUnavailable(QuantumError):
    """The honest answer is "we do not have this".

    Raised instead of returning a plausible default. Master prompt section 83:
    never substitute invented values. The ``reason`` is required because
    "unavailable" without a cause is not actionable at 3am.
    """

    def __init__(self, what: str, reason: str) -> None:
        self.what = what
        self.reason = reason
        super().__init__(f"DATA_UNAVAILABLE: {what} -- {reason}")


class ValidationFailed(QuantumError):
    """A dataset failed a check in :mod:`quantum_institutional.data.validation`."""

    def __init__(self, check: str, detail: str) -> None:
        self.check = check
        self.detail = detail
        super().__init__(f"VALIDATION_FAILED [{check}]: {detail}")


class LookaheadError(QuantumError):
    """Information was requested that did not exist at the requested time.

    This is a programming error, not a data error, so it raises rather than
    degrading. Master prompt sections 70-72.
    """
