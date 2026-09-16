"""System health. Master prompt sections 41, 54 and 68.

Reports what the system can currently stand behind. The design rule is that
health is COMPUTED from real checks, never asserted: a component with no check
wired up reports ``OFFLINE`` with the reason "not implemented", which is the
honest state during early phases and is visible on the dashboard as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..errors import Quality
from ..version import Stamp, current_stamp

__all__ = ["ComponentHealth", "SystemHealth", "collect_health"]


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    component: str
    quality: Quality
    detail: str
    last_update: datetime | None = None


@dataclass(frozen=True, slots=True)
class SystemHealth:
    checked_at: datetime
    stamp: Stamp
    components: list[ComponentHealth] = field(default_factory=list)

    @property
    def overall(self) -> Quality:
        """Worst component wins. Section 40: no HIGH CONFIDENCE on stale data."""
        return Quality.worst(*(c.quality for c in self.components)) if self.components else Quality.OFFLINE

    @property
    def signals_permitted(self) -> bool:
        """Whether the data-quality gate (section 41) would allow a signal."""
        return self.overall.is_tradeable


def collect_health() -> SystemHealth:
    """Collect current component health.

    Every component below is ``OFFLINE / not implemented`` because none of them
    exist yet. This function is written to be extended one component at a time,
    and the checklist in ``docs/ACCEPTANCE.md`` is not tickable for a component
    until its entry here performs a real check.
    """
    not_implemented = [
        ("market_data", "Phase 15"),
        ("macro", "Phase 14"),
        ("news", "Phase 14"),
        ("database", "Phase 18"),
        ("realtime", "Phase 19"),
        ("model", "Phase 13"),
    ]
    return SystemHealth(
        checked_at=datetime.now(UTC),
        stamp=current_stamp(),
        components=[
            ComponentHealth(name, Quality.OFFLINE, f"not implemented ({phase})")
            for name, phase in not_implemented
        ],
    )
