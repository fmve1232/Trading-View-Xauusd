"""Provider registry. Master prompt sections 5 and 6.

Resolves a provider NAME from configuration to an implementation, so nothing in
the engine imports a vendor package.

No provider implementations ship in this repository yet. That is deliberate:
section 83 forbids fabricated API responses, and a stub that returns plausible
prices is exactly that. Until a real adapter is written and credentialed,
resolution fails loudly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from ...errors import DataUnavailable
from .base import MacroProvider, MarketDataProvider, NewsProvider, Provider

__all__ = ["register", "registered_names", "resolve"]

P = TypeVar("P", bound=Provider)

_REGISTRY: dict[str, Callable[[], Provider]] = {}


def register(name: str, factory: Callable[[], Provider]) -> None:
    """Register a provider factory under ``name``.

    Re-registering a name raises. Silent replacement would let an import
    ordering change swap the live data source without any diff to show for it.
    """
    if name in _REGISTRY:
        raise ValueError(f"provider {name!r} is already registered")
    _REGISTRY[name] = factory


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def resolve(name: str, expected: type[P]) -> P:
    """Instantiate the provider registered as ``name``.

    Raises :class:`DataUnavailable` when nothing is registered, and
    ``TypeError`` when the registered provider is the wrong kind -- a news
    provider wired into the market slot should fail at startup, not on the
    first quote.
    """
    factory = _REGISTRY.get(name)
    if factory is None:
        available = ", ".join(registered_names()) or "none"
        raise DataUnavailable(
            f"provider:{name}",
            f"no provider registered under that name (registered: {available})",
        )
    instance = factory()
    if not isinstance(instance, expected):
        raise TypeError(f"provider {name!r} is {type(instance).__name__}, expected {expected.__name__}")
    return instance


# Convenience aliases that make the expected kind explicit at the call site.
def resolve_market(name: str) -> MarketDataProvider:
    # The ABC is used for the isinstance() check inside resolve(); it is never
    # instantiated here, which is what type-abstract guards against.
    return resolve(name, MarketDataProvider)  # type: ignore[type-abstract]


def resolve_news(name: str) -> NewsProvider:
    return resolve(name, NewsProvider)  # type: ignore[type-abstract]


def resolve_macro(name: str) -> MacroProvider:
    return resolve(name, MacroProvider)  # type: ignore[type-abstract]
