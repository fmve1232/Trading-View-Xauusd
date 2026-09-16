"""Execution mode. Master prompt sections 63 and 65.

PAPER is the default and LIVE requires an explicit, exact opt-in. There is no
inference, no "looks like production so probably live", and no partial match.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ExecutionMode"]


class ExecutionMode(StrEnum):
    #: Generate signals, record hypothetical fills, place no orders.
    PAPER = "PAPER"
    #: Place real orders. Reached only by setting EXECUTION_MODE=LIVE exactly.
    LIVE = "LIVE"

    @classmethod
    def from_env(cls, raw: str | None) -> ExecutionMode:
        """Parse the mode, defaulting to PAPER.

        Raises ``ValueError`` on an unrecognised value rather than defaulting,
        so a typo fails the deploy instead of silently changing behaviour. The
        comparison is case-sensitive after stripping: ``live`` is accepted,
        ``LIVE_TEST`` is not.
        """
        if raw is None or raw.strip() == "":
            return cls.PAPER
        normalised = raw.strip().upper()
        if normalised not in (cls.PAPER.value, cls.LIVE.value):
            raise ValueError(
                f"EXECUTION_MODE must be PAPER or LIVE, got {raw!r}. Refusing to guess; set it explicitly."
            )
        return cls(normalised)

    @property
    def places_orders(self) -> bool:
        return self is ExecutionMode.LIVE
