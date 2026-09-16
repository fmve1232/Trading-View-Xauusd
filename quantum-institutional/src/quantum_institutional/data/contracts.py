"""Typed records for everything that enters the system. Sections 7, 8, 70.

Plain frozen dataclasses, not pydantic models, on purpose: these types are
imported by every engine, and the engines must stay free of API-framework
dependencies (section 5). Pydantic appears only at the API boundary.

THE THREE TIMESTAMPS
--------------------
Every record that can be revised carries three distinct times, because
collapsing them is how backtests leak:

``event_time``        when the thing happened, or the bar opened.
``publication_time``  when the information became PUBLICLY AVAILABLE. This is
                      the only one a point-in-time query may filter on.
``received_time``     when this system got it. Used for latency, never for
                      filtering -- filtering on it would make a backtest depend
                      on the speed of the machine that ran the ingest.

A CPI print for the September reference month has an event_time in September, a
publication_time at 13:30 UTC on release day, and a received_time a few hundred
milliseconds later. A model that sees it before 13:30 UTC is leaking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ..errors import Quality

__all__ = [
    "Bar",
    "Instrument",
    "MacroValue",
    "NewsItem",
    "Quote",
    "Timeframe",
    "VolumeType",
]


class VolumeType(StrEnum):
    """What a volume number actually counts. Section 7: never mix these.

    Broker tick volume counts price CHANGES, not contracts. Averaging it with
    exchange volume produces a number that means nothing.
    """

    TICK = "TICK"  # broker tick count (most spot XAUUSD feeds)
    EXCHANGE = "EXCHANGE"  # matched contracts on an exchange
    FUTURES = "FUTURES"  # COMEX GC / MGC contract volume
    OTC_ESTIMATE = "OTC_ESTIMATE"
    NONE = "NONE"  # feed supplies no volume


class Timeframe(StrEnum):
    """Supported bar intervals. Section 10."""

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1H"
    H2 = "2H"
    H4 = "4H"
    H6 = "6H"
    H12 = "12H"
    D1 = "1D"
    W1 = "1W"

    @property
    def seconds(self) -> int:
        """Nominal length in seconds.

        Weekly is the nominal 7 days. Calendar-aware alignment (sessions,
        holidays, the Sunday open) belongs in the aggregation layer, not in a
        constant -- see :mod:`quantum_institutional.data.aggregation`.
        """
        return _TIMEFRAME_SECONDS[self]

    @property
    def is_derivable(self) -> bool:
        """Whether this timeframe can be built from 1m bars deterministically."""
        return self.seconds % _TIMEFRAME_SECONDS[Timeframe.M1] == 0


_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M3: 180,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1_800,
    Timeframe.H1: 3_600,
    Timeframe.H2: 7_200,
    Timeframe.H4: 14_400,
    Timeframe.H6: 21_600,
    Timeframe.H12: 43_200,
    Timeframe.D1: 86_400,
    Timeframe.W1: 604_800,
}


@dataclass(frozen=True, slots=True)
class Instrument:
    """A tradeable or observable series. Section 8.

    ``symbol`` is this system's canonical name; ``provider_symbol`` is whatever
    the feed calls it. They are kept apart so that XAUUSD spot from two brokers
    remains two records that can be reconciled (section 69), rather than one
    record that silently took whichever arrived last.
    """

    symbol: str
    asset_class: str
    provider_symbol: str | None = None
    exchange: str | None = None
    quote_currency: str = "USD"


@dataclass(frozen=True, slots=True)
class Quote:
    """A bid/ask observation. Section 7."""

    symbol: str
    event_time: datetime
    bid: float
    ask: float
    source: str
    received_time: datetime
    quality: Quality = Quality.OK

    def __post_init__(self) -> None:
        _require_utc(self.event_time, "event_time")
        _require_utc(self.received_time, "received_time")

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def latency_s(self) -> float:
        """Feed latency. Diagnostic only -- never a filter (see module docstring)."""
        return (self.received_time - self.event_time).total_seconds()


@dataclass(frozen=True, slots=True)
class Bar:
    """An OHLCV bar. Sections 7 and 11.

    ``event_time`` is the bar's OPEN, left-aligned, always UTC. The convention
    is fixed here rather than per-provider because a feed that labels bars by
    close time shifts every signal by one bar if it is normalised anywhere
    later than ingestion.
    """

    symbol: str
    timeframe: Timeframe
    event_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    volume_type: VolumeType
    source: str
    quality: Quality = Quality.OK

    def __post_init__(self) -> None:
        _require_utc(self.event_time, "event_time")

    @property
    def close_time(self) -> datetime:
        """Exclusive end of the bar's interval."""
        from datetime import timedelta

        return self.event_time + timedelta(seconds=self.timeframe.seconds)

    @property
    def is_ohlc_consistent(self) -> bool:
        """``high >= max(open, close)`` and ``low <= min(open, close)``."""
        return self.high >= max(self.open, self.close) and self.low <= min(self.open, self.close)


@dataclass(frozen=True, slots=True)
class MacroValue:
    """One macroeconomic observation. Sections 21 and 70.

    ``revision_of`` points at the ``series_id`` release this supersedes. A
    point-in-time query returns the value as first published, not the revised
    one, because the revised number did not exist at the historical timestamp.
    """

    series_id: str
    event_time: datetime
    publication_time: datetime
    value: float
    source: str
    received_time: datetime
    revision_of: str | None = None
    quality: Quality = Quality.OK

    def __post_init__(self) -> None:
        _require_utc(self.event_time, "event_time")
        _require_utc(self.publication_time, "publication_time")
        _require_utc(self.received_time, "received_time")


@dataclass(frozen=True, slots=True)
class NewsItem:
    """One news or calendar item. Sections 22 and 23.

    ``sentiment`` is ``None`` until a scored model exists. It is NOT defaulted
    to 0.0 -- a neutral score and an absent score are different claims, and
    section 83 forbids inventing the difference away.
    """

    news_id: str
    headline: str
    publication_time: datetime
    source: str
    received_time: datetime
    event_category: str | None = None
    importance: str | None = None
    sentiment: float | None = None
    reference_url: str | None = None
    quality: Quality = Quality.OK

    def __post_init__(self) -> None:
        _require_utc(self.publication_time, "publication_time")
        _require_utc(self.received_time, "received_time")


def _require_utc(value: datetime, field_name: str) -> None:
    """Reject naive datetimes at construction.

    A naive datetime is the single most common source of an off-by-one-session
    bug: it compares fine, sorts fine, and is wrong by the local offset. There
    is no correct default timezone to assume, so this raises.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware; got naive {value!r}")
    if value.utcoffset() != UTC.utcoffset(None):
        raise ValueError(
            f"{field_name} must be UTC; got offset {value.utcoffset()}. "
            "Normalise at ingestion, not downstream."
        )
