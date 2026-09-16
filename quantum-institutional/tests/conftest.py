"""Shared fixtures.

All synthetic. Nothing here is market data and nothing here may be used as a
parity baseline -- these values exercise code paths, they do not represent
XAUUSD. Parity baselines come from the exported TradingView series described in
``docs/PARITY_PLAN.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quantum_institutional.data.contracts import Bar, Timeframe, VolumeType

EPOCH = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)  # a Monday, on every grid


def make_bar(
    index: int = 0,
    timeframe: Timeframe = Timeframe.M1,
    *,
    open_: float = 2000.0,
    high: float = 2001.0,
    low: float = 1999.0,
    close: float = 2000.5,
    volume: float | None = 100.0,
    volume_type: VolumeType = VolumeType.TICK,
    symbol: str = "XAUUSD",
    start: datetime = EPOCH,
) -> Bar:
    return Bar(
        symbol=symbol,
        timeframe=timeframe,
        event_time=start + timedelta(seconds=timeframe.seconds * index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_type=volume_type,
        source="synthetic",
    )


@pytest.fixture
def minute_bars() -> list[Bar]:
    """Five clean, contiguous 1m bars."""
    return [make_bar(i) for i in range(5)]
