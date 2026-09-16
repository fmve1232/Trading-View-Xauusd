"""Dataset validation. Master prompt section 12.

Pure functions over sequences of :class:`~...contracts.Bar`. No I/O, no
provider knowledge, so every check is testable with a handful of synthetic
bars.

Checks RETURN a report rather than raising. A single bad bar in ten years of
history is a data-quality fact to be recorded (section 12: "store validation
results"), not a reason to abort an ingest. The caller decides the threshold at
which a dataset is unusable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ..errors import Quality
from .contracts import Bar, Timeframe

__all__ = ["Issue", "ValidationReport", "validate_bars"]


@dataclass(frozen=True, slots=True)
class Issue:
    check: str
    detail: str
    index: int | None = None


@dataclass(slots=True)
class ValidationReport:
    total: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def quality(self) -> Quality:
        """Dataset-level quality.

        Any OHLC inconsistency or ordering violation is INVALID: those make the
        series internally contradictory, and an indicator computed over it is
        meaningless. Gaps and missing volume are DEGRADED -- the data is
        usable, with a known hole.
        """
        if not self.issues:
            return Quality.OK
        fatal = {
            "ohlc_consistency",
            "chronological_order",
            "duplicate_timestamp",
            "timeframe_alignment",
        }
        if any(issue.check in fatal for issue in self.issues):
            return Quality.INVALID
        return Quality.DEGRADED

    def by_check(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.check] = counts.get(issue.check, 0) + 1
        return counts


def validate_bars(bars: list[Bar], timeframe: Timeframe, *, expect_volume: bool = True) -> ValidationReport:
    """Run every section-12 check over a bar series.

    An empty series is reported as an issue rather than passing vacuously --
    "zero bars, no problems" is the report most likely to be mistaken for
    success.

    KNOWN LIMITATION: ``gap`` is calendar-blind, so every XAUUSD weekend and
    every holiday close is reported as a gap. That is correct as a statement of
    the data and useless as an alert. A session calendar lands in Phase 20 and
    will downgrade expected closes; until then, filter ``gap`` issues by
    weekday before alerting on them.
    """
    report = ValidationReport(total=len(bars))

    if not bars:
        report.issues.append(Issue("empty_dataset", "no bars supplied"))
        return report

    step = timedelta(seconds=timeframe.seconds)
    seen: dict[object, int] = {}

    for index, bar in enumerate(bars):
        if bar.timeframe is not timeframe:
            report.issues.append(
                Issue(
                    "timeframe_mismatch",
                    f"bar is {bar.timeframe.value}, expected {timeframe.value}",
                    index,
                )
            )

        if not bar.is_ohlc_consistent:
            report.issues.append(
                Issue(
                    "ohlc_consistency",
                    f"O={bar.open} H={bar.high} L={bar.low} C={bar.close} "
                    "violates high >= max(O,C) or low <= min(O,C)",
                    index,
                )
            )

        if bar.high < bar.low:
            report.issues.append(Issue("ohlc_consistency", f"high {bar.high} < low {bar.low}", index))

        if bar.volume is not None and bar.volume < 0:
            report.issues.append(Issue("negative_volume", f"volume={bar.volume}", index))

        if expect_volume and bar.volume is None:
            report.issues.append(Issue("missing_volume", "volume is None but was expected", index))

        # Bar opens must land on the timeframe grid. An off-grid bar means the
        # feed is labelling by close time, or the timeframe is mislabelled --
        # both corrupt every aggregation built on top.
        if bar.event_time.timestamp() % timeframe.seconds != 0:
            report.issues.append(
                Issue(
                    "timeframe_alignment",
                    f"{bar.event_time.isoformat()} is not on the {timeframe.value} grid",
                    index,
                )
            )

        key = (bar.symbol, bar.event_time)
        if key in seen:
            report.issues.append(
                Issue("duplicate_timestamp", f"{bar.event_time.isoformat()} also at index {seen[key]}", index)
            )
        else:
            seen[key] = index

        if index > 0:
            previous = bars[index - 1]
            if bar.event_time < previous.event_time:
                report.issues.append(
                    Issue(
                        "chronological_order",
                        f"{bar.event_time.isoformat()} precedes {previous.event_time.isoformat()}",
                        index,
                    )
                )
            elif bar.event_time - previous.event_time > step:
                missing = int((bar.event_time - previous.event_time) / step) - 1
                report.issues.append(
                    Issue(
                        "gap",
                        f"{missing} missing bar(s) between {previous.event_time.isoformat()} "
                        f"and {bar.event_time.isoformat()}",
                        index,
                    )
                )

    return report
