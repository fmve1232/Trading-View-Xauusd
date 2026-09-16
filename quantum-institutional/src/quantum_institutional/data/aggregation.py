"""Deterministic timeframe aggregation. Master prompt section 11.

Builds higher-timeframe bars from a lower-timeframe series. The output must be
byte-reproducible from the same input: no wall-clock, no iteration-order
dependence, no partial bars.

NO LOOKAHEAD
------------
A bucket is emitted only when it is COMPLETE, unless ``include_partial`` is
explicitly requested. The default exists because the last bucket of a live
series is always partial, and emitting it as a finished bar is the most common
way a live system sees a close that has not happened yet.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..errors import Quality
from .contracts import Bar, Timeframe, VolumeType

__all__ = ["aggregate", "bucket_start"]


def bucket_start(moment: datetime, timeframe: Timeframe) -> datetime:
    """Left-aligned start of the bucket containing ``moment``.

    Anchored to the Unix epoch, which is midnight UTC on a Thursday. For
    intraday timeframes and ``1D`` that is the conventional boundary. For
    ``1W`` it puts the week boundary on Thursday, which is NOT the convention
    any exchange uses, so weekly aggregation is rejected here rather than
    silently producing Thursday-anchored weeks -- see :func:`aggregate`.
    """
    seconds = timeframe.seconds
    epoch_seconds = int(moment.timestamp())
    return datetime.fromtimestamp(epoch_seconds - (epoch_seconds % seconds), tz=UTC)


def aggregate(
    source: list[Bar],
    target: Timeframe,
    *,
    include_partial: bool = False,
) -> list[Bar]:
    """Aggregate ``source`` bars into ``target`` bars.

    OHLCV follows section 11 exactly: open is the first source open, high the
    maximum, low the minimum, close the last source close, volume the sum.

    Volume is summed only when every contributing bar shares one
    :class:`VolumeType`. Mixed types produce ``volume=None`` with
    ``VolumeType.NONE`` rather than a sum, because adding broker tick counts to
    exchange contract counts yields a number with no unit (section 7).

    Quality is the WORST contributing quality, so one INVALID source bar makes
    the aggregate INVALID instead of averaging the problem away.

    Raises ``ValueError`` when the target is not a whole multiple of the source
    timeframe, or for weekly targets, whose boundary is a calendar question
    this function cannot answer (see :func:`bucket_start`).
    """
    if not source:
        return []

    if target is Timeframe.W1:
        raise ValueError(
            "weekly aggregation needs a session calendar (the epoch anchor puts "
            "the boundary on Thursday); use a calendar-aware aggregator"
        )

    source_tf = source[0].timeframe
    if any(bar.timeframe is not source_tf for bar in source):
        raise ValueError("source contains mixed timeframes")
    if target.seconds < source_tf.seconds:
        raise ValueError(f"cannot aggregate {source_tf.value} up to the shorter {target.value}")
    if target.seconds % source_tf.seconds != 0:
        raise ValueError(
            f"{target.value} is not a whole multiple of {source_tf.value}; "
            "aggregation would straddle bucket boundaries"
        )

    symbol = source[0].symbol
    if any(bar.symbol != symbol for bar in source):
        raise ValueError("source contains mixed symbols")

    ordered = sorted(source, key=lambda b: b.event_time)
    expected_count = target.seconds // source_tf.seconds

    buckets: dict[datetime, list[Bar]] = {}
    for bar in ordered:
        buckets.setdefault(bucket_start(bar.event_time, target), []).append(bar)

    out: list[Bar] = []
    for start in sorted(buckets):
        members = buckets[start]
        complete = len(members) == expected_count
        if not complete and not include_partial:
            continue

        volume_types = {m.volume_type for m in members}
        if len(volume_types) == 1 and all(m.volume is not None for m in members):
            volume: float | None = sum(m.volume for m in members)  # type: ignore[misc]
            volume_type = members[0].volume_type
        else:
            volume = None
            volume_type = VolumeType.NONE

        quality = Quality.worst(*(m.quality for m in members))
        if not complete:
            quality = Quality.worst(quality, Quality.DEGRADED)

        out.append(
            Bar(
                symbol=symbol,
                timeframe=target,
                event_time=start,
                open=members[0].open,
                high=max(m.high for m in members),
                low=min(m.low for m in members),
                close=members[-1].close,
                volume=volume,
                volume_type=volume_type,
                source=members[0].source,
                quality=quality,
            )
        )
    return out
