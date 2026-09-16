"""Provider interfaces. Master prompt sections 6 and 83.

Engines depend on these abstract classes, never on a vendor SDK. Swapping a
data source is then a config change and a new subclass, not a rewrite
(section 5).

EVERY METHOD MAY RAISE ``DataUnavailable``
-----------------------------------------
That is the contract, and it is the reason these are abstract rather than
duck-typed: a provider that returns an empty list where it means "I could not
reach the API" is indistinguishable from one that means "there were genuinely
no bars in that window". The first is an outage the system must degrade on; the
second is a fact. Implementations MUST raise for the first and return empty for
the second.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..contracts import Bar, MacroValue, NewsItem, Quote, Timeframe

__all__ = ["MacroProvider", "MarketDataProvider", "NewsProvider", "Provider"]


class Provider(ABC):
    """Common identity and liveness surface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier, stored on every record this provider produces."""

    @abstractmethod
    def health(self) -> bool:
        """Whether the provider is reachable right now.

        Must not raise. A provider that throws from its own health check cannot
        be monitored, which defeats section 54.
        """


class MarketDataProvider(Provider):
    """Prices. Section 6."""

    @abstractmethod
    def get_latest_quote(self, symbol: str) -> Quote:
        """Most recent bid/ask. Raises ``DataUnavailable`` if the feed is down."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        """Bars in ``[start, end)``, oldest first.

        Half-open to match :class:`~...chunking.Chunk`, so chunked ingestion
        does not duplicate boundary bars.

        Implementations must NOT return a partial final bar. If the feed
        includes one, drop it -- an in-progress bar has a close that has not
        happened.
        """


class NewsProvider(Provider):
    """Headlines and calendar items. Sections 22 and 23."""

    @abstractmethod
    def get_news(self, start: datetime, end: datetime, symbols: list[str] | None = None) -> list[NewsItem]:
        """Items PUBLISHED in ``[start, end)``.

        Filtered on publication time, not event time, so the window means "what
        became known" rather than "what happened".
        """


class MacroProvider(Provider):
    """Macroeconomic series. Sections 21 and 70."""

    @abstractmethod
    def get_macro(self, series_id: str, start: datetime, end: datetime) -> list[MacroValue]:
        """Observations for ``series_id``, as first published.

        Implementations must populate ``publication_time`` from the provider's
        release timestamp. Where a provider supplies only the reference period,
        the implementation must raise ``DataUnavailable`` rather than defaulting
        ``publication_time`` to ``event_time`` -- that default backdates every
        release to the start of its reference period and leaks weeks of future
        information into every historical bar.
        """
