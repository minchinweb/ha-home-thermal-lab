"""How a room's temperature responds to furnace runs (hypotheses 05 and 12)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .hvac import Run


def merge_runs(runs: list[Run], max_gap_minutes: float = 5.0) -> list[Run]:
    """Merge runs separated by short gaps into episodes.

    Args:
        runs: Runs from any number of sources (they may overlap).
        max_gap_minutes: Runs closer than this are joined.

    Returns:
        Non-overlapping episodes, oldest first.
    """
    merged: list[Run] = []
    for run in sorted(runs, key=lambda r: r.start):
        if merged and (run.start - merged[-1].end) <= timedelta(
            minutes=max_gap_minutes
        ):
            last = merged[-1]
            merged[-1] = Run(last.start, max(last.end, run.end))
        else:
            merged.append(run)
    return merged


def temperature_series(
    states: list[dict], attribute: str = "current_temperature"
) -> list[tuple[datetime, float]]:
    """Read a temperature attribute (e.g. a thermostat's) as a time series.

    Args:
        states: State dicts with ``attributes`` and ``last_updated``.
        attribute: The attribute to read.

    Returns:
        ``(utc_time, value)`` pairs, oldest first, skipping missing values.
    """
    out = []
    for s in states:
        value = s.get("attributes", {}).get(attribute)
        if value is None:
            continue
        when = datetime.fromisoformat(s["last_updated"]).astimezone(UTC)
        out.append((when, float(value)))
    return sorted(out)


def value_at(series: list[tuple[datetime, float]], when: datetime) -> float | None:
    """Return the last reading at or before ``when`` (a sensor holds its value).

    Args:
        series: Readings, oldest first.
        when: The time to look up (timezone-aware).

    Returns:
        The held value, or ``None`` if nothing was recorded yet.
    """
    held = None
    for t, v in series:
        if t > when:
            break
        held = v
    return held


@dataclass(frozen=True)
class RunResponse:
    """How one room's temperature responded to one heating episode.

    Attributes:
        start: Start of the episode (UTC).
        minutes: Length of the episode in minutes.
        t_start: Room temperature when it started.
        t_end: Room temperature when it ended.
        rise: ``t_end - t_start`` in degrees.
        rate_per_h: Rise per hour of running.
        overshoot: How much the room kept rising after the end (degrees above
            ``t_end``), within the follow-up window.
        minutes_to_peak: Minutes after the end until the room peaked.
        own_call: Whether this room's own thermostat was calling during it.
    """

    start: datetime
    minutes: float
    t_start: float
    t_end: float
    rise: float
    rate_per_h: float
    overshoot: float
    minutes_to_peak: float
    own_call: bool


def analyse_responses(
    episodes: list[Run],
    series: list[tuple[datetime, float]],
    own_runs: list[Run] | None = None,
    window_minutes: float = 60.0,
    min_minutes: float = 3.0,
) -> list[RunResponse]:
    """Measure a room's response to each heating episode.

    The follow-up window ends early if the next episode starts first, and
    episodes shorter than ``min_minutes`` are skipped (too short to resolve).

    Args:
        episodes: Whole-house heating episodes.
        series: The room's temperature readings.
        own_runs: Runs where this room's own thermostat called for heat.
        window_minutes: How long after the end to look for the peak.
        min_minutes: Shortest episode to analyse.

    Returns:
        One response per usable episode.
    """
    out = []
    own_runs = own_runs or []
    for i, ep in enumerate(episodes):
        if ep.minutes < min_minutes:
            continue
        limit = ep.end + timedelta(minutes=window_minutes)
        if i + 1 < len(episodes):
            limit = min(limit, episodes[i + 1].start)
        t0 = value_at(series, ep.start)
        t1 = value_at(series, ep.end)
        if t0 is None or t1 is None:
            continue
        after = [(t, v) for t, v in series if ep.end <= t <= limit]
        peak_time, peak = max(after, key=lambda tv: tv[1], default=(ep.end, t1))
        peak = max(peak, t1)
        out.append(
            RunResponse(
                start=ep.start,
                minutes=ep.minutes,
                t_start=t0,
                t_end=t1,
                rise=t1 - t0,
                rate_per_h=(t1 - t0) / (ep.minutes / 60.0),
                overshoot=peak - t1,
                minutes_to_peak=max((peak_time - ep.end).total_seconds() / 60.0, 0.0),
                own_call=any(r.start < ep.end and r.end > ep.start for r in own_runs),
            )
        )
    return out
