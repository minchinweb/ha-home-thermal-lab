"""Whole-house power around equipment events (hypothesis 14)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hvac import Run

PowerSeries = list[tuple[datetime, float]]


def power_series(states: list[dict]) -> PowerSeries:
    """Read a power sensor's state history as ``(utc_time, value)`` pairs.

    Args:
        states: State dicts with ``state`` and ``last_changed``.

    Returns:
        Readings, oldest first, skipping non-numeric states.
    """
    out = []
    for s in states:
        try:
            value = float(s["state"])
        except (TypeError, ValueError):
            continue
        out.append((datetime.fromisoformat(s["last_changed"]).astimezone(UTC), value))
    return sorted(out)


def time_weighted_mean(
    series: PowerSeries, start: datetime, end: datetime
) -> float | None:
    """Average a held-value series over ``start``..``end``.

    Args:
        series: Readings, oldest first; each holds until the next one.
        start: Start of the window.
        end: End of the window.

    Returns:
        The time-weighted mean, or ``None`` if nothing was recorded in or
        before the window.
    """
    if end <= start:
        return None
    total = 0.0
    seconds = 0.0
    held = None
    for t, v in series:
        if t <= start:
            held = v
            continue
        if held is not None:
            stop = min(t, end)
            total += held * (stop - start).total_seconds()
            seconds += (stop - start).total_seconds()
        held = v
        start = min(t, end)
        if t >= end:
            break
    if held is not None and start < end:
        total += held * (end - start).total_seconds()
        seconds += (end - start).total_seconds()
    return total / seconds if seconds else None


@dataclass(frozen=True)
class Step:
    """Power before, during and after one event.

    Attributes:
        when: The event time (UTC).
        before: Mean power in the window before the event (kW).
        during: Mean power while it ran (kW).
        after: Mean power in the window after it ended (kW).
    """

    when: datetime
    before: float
    during: float
    after: float

    @property
    def rise(self) -> float:
        """Power while running minus power just before (kW)."""
        return self.during - self.before

    @property
    def fall(self) -> float:
        """Power just after the end minus power while running (kW)."""
        return self.after - self.during


def steps_around(
    runs: list[Run],
    series: PowerSeries,
    window_minutes: float = 10.0,
    settle_minutes: float = 1.0,
    min_minutes: float = 8.0,
) -> list[Step]:
    """Measure power before, during and after each run.

    Args:
        runs: Equipment runs.
        series: Whole-house power readings.
        window_minutes: Length of the before and after windows.
        settle_minutes: Skipped at each edge to let the step settle.
        min_minutes: Shortest run to use.

    Returns:
        One step per usable run.
    """
    gap = timedelta(minutes=settle_minutes)
    window = timedelta(minutes=window_minutes)
    out = []
    for run in runs:
        if run.minutes < min_minutes:
            continue
        before = time_weighted_mean(series, run.start - window, run.start - gap)
        during = time_weighted_mean(series, run.start + gap, run.end - gap)
        after = time_weighted_mean(series, run.end + gap, run.end + window)
        if None in (before, during, after):
            continue
        out.append(Step(run.start, before, during, after))
    return out


def median_or_nan(values: list[float]) -> float:
    """Median of ``values``, or ``nan`` when empty."""
    return statistics.median(values) if values else float("nan")
