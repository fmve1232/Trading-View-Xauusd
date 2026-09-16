"""Configuration, read from the environment. Master prompt sections 5 and 66.

Two rules shape this module:

* No secret has a default. A missing credential raises
  :class:`~quantum_institutional.errors.DataUnavailable` at the point of use,
  rather than silently falling back to an anonymous or demo endpoint.
* The quant engine never imports a vendor SDK. Provider choice is a string
  here, resolved through the provider registry, so a data source can be
  swapped without touching an engine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final

from .errors import DataUnavailable
from .execution.mode import ExecutionMode

__all__ = ["Settings", "load_settings"]

#: Freshness budgets in seconds, by feed class. A feed older than its budget is
#: STALE and cannot back a production signal (section 41). These are operational
#: limits chosen on principle, not parameters fitted to results.
DEFAULT_FRESHNESS_BUDGET_S: Final[dict[str, int]] = {
    "market": 60,
    "macro": 86_400,
    "news": 900,
}


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    execution_mode: ExecutionMode
    database_url: str | None
    market_provider: str
    news_provider: str | None
    macro_provider: str | None
    freshness_budget_s: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_FRESHNESS_BUDGET_S))

    def require_database_url(self) -> str:
        if not self.database_url:
            raise DataUnavailable("database_url", "DATABASE_URL is not set in the environment")
        return self.database_url


def load_settings() -> Settings:
    """Read settings from the environment.

    ``EXECUTION_MODE`` defaults to PAPER and must be set explicitly to go live
    (sections 63 and 65). An unrecognised value is an error, not a fallback to
    PAPER -- a typo in a deploy config should stop the deploy, not quietly
    change what the system does.
    """
    return Settings(
        environment=os.environ.get("ENVIRONMENT", "development"),
        execution_mode=ExecutionMode.from_env(os.environ.get("EXECUTION_MODE")),
        database_url=os.environ.get("DATABASE_URL") or None,
        market_provider=os.environ.get("MARKET_PROVIDER", "unset"),
        news_provider=os.environ.get("NEWS_PROVIDER") or None,
        macro_provider=os.environ.get("MACRO_PROVIDER") or None,
    )
