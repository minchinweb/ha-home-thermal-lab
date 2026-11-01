"""Furnace/AC runs from on/off call-state history (hypotheses 05-07)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, tzinfo

_BAD_STATES = frozenset({"unknown", "unavailable", ""})


@dataclass(frozen=True)
class Run:
    """One continuous period in the ``on`` state.

    Attributes:
        start: Start of the run (UTC).
        end: End of the run (UTC).
    """

    start: datetime
    end: datetime

    @property
    def minutes(self) -> float:
        """Length of the run in minutes."""
        return (self.end - self.start).total_seconds() / 60.0


def runs_from_states(
    states: list[dict],
    until: datetime,
    on_states: frozenset[str] | set[str] = frozenset({"on"}),
    attribute: str | None = None,
) -> list[Run]:
    """Turn a state history into runs where the value is one of ``on_states``.

    Unavailable periods end a run (we can't know what happened during them).

    Args:
        states: Home Assistant state dicts. Needs ``last_changed``, or
            ``last_updated`` and ``attributes`` when reading an attribute.
        until: When the last state stops holding (timezone-aware).
        on_states: Values that count as running.
        attribute: Read this attribute (e.g. ``hvac_action`` of a ``climate``
            entity) instead of the state.

    Returns:
        Runs, oldest first.
    """
    events = []
    for s in states:
        if attribute is None:
            value, stamp = s["state"], s["last_changed"]
        else:
            value = s.get("attributes", {}).get(attribute)
            stamp = s["last_updated"]
        events.append((datetime.fromisoformat(stamp).astimezone(UTC), value))
    events.sort(key=lambda e: e[0])
    events.append((until.astimezone(UTC), None))
    runs = []
    start = None
    for when, value in events:
        if value in on_states:
            start = start or when
            continue
        if start is not None:
            if when > start:
                runs.append(Run(start, when))
            start = None
    return runs


@dataclass(frozen=True)
class DailyUse:
    """Run time on one local day.

    Attributes:
        day: The local date.
        hours: Hours the equipment ran.
        runs: Number of runs that started that day.
    """

    day: date
    hours: float
    runs: int


def daily_use(runs: list[Run], tz: tzinfo, days: list[date]) -> list[DailyUse]:
    """Total run time and run count per local day, including days with none.

    Args:
        runs: Runs in UTC.
        tz: The local time zone.
        days: The local dates to report.

    Returns:
        One entry per requested day.
    """
    seconds: dict[date, float] = defaultdict(float)
    starts: dict[date, int] = defaultdict(int)
    for run in runs:
        starts[run.start.astimezone(tz).date()] += 1
        cursor = run.start
        while cursor < run.end:
            local = cursor.astimezone(tz)
            midnight = datetime.combine(
                local.date() + timedelta(days=1), datetime.min.time(), tzinfo=tz
            )
            stop = min(run.end, midnight.astimezone(UTC))
            seconds[local.date()] += (stop - cursor).total_seconds()
            cursor = stop
    return [DailyUse(d, seconds[d] / 3600.0, starts[d]) for d in days]


def run_summary(runs: list[Run], use: list[DailyUse]) -> dict[str, float]:
    """Headline numbers for a set of runs.

    Args:
        runs: Runs in UTC.
        use: Per-day use over the same period.

    Returns:
        Mean hours and runs per day, median and longest run minutes, and the
        share of days with any run.
    """
    return {
        "hours_per_day": statistics.fmean(u.hours for u in use) if use else 0.0,
        "runs_per_day": statistics.fmean(u.runs for u in use) if use else 0.0,
        "median_run_min": statistics.median(r.minutes for r in runs) if runs else 0.0,
        "longest_run_min": max((r.minutes for r in runs), default=0.0),
        "days_with_run": (sum(u.runs > 0 for u in use) / len(use)) if use else 0.0,
    }
