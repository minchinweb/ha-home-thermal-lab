"""Experiments for hypotheses 01 (sine wave) and 02 (solar-noon peak).

Also measures the daily range (peak minus bottom) and how all of these change
by season and by the day's weather.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import statistics
from typing import TYPE_CHECKING

from .open_meteo import Fetcher, fetch_hourly, to_solar_days, urllib_fetch
from .solar import solar_noon_hour
from .stats import percentile
from .wave_fit import WaveFit, fit_day, signed_offset_hours
from .weather import (
    SEASONS,
    UNKNOWN,
    WEATHER_CLASSES,
    classify_weather,
    season,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from .locations import Location
    from .readings import Reading, SolarReading

MIN_SAMPLES_PER_DAY = 22
BAND_PERCENTILES = (10, 25, 50, 75, 90)
GROUP_BY = ("all", "season", "weather")


@dataclass(frozen=True)
class DayResult:
    """One fitted day.

    Attributes:
        day: The solar day.
        fit: The 24 h sinusoid fitted to the day.
        season: Season name (hemisphere-adjusted).
        weather: Weather class, or ``unknown``.
        peak_offset_h: Fitted peak minus solar noon, in hours.
        trough_offset_h: Fitted trough minus solar midnight, in hours.
        observed_peak_offset_h: Warmest hour minus solar noon.
        observed_trough_offset_h: Coolest hour minus solar midnight.
        observed_range: Warmest minus coolest reading, in degrees.
        peak_to_trough_h: Hours from the warmest hour forward to the coolest.
        profile: ``(hour, temperature minus the day's mean)`` for each reading.
    """

    day: date
    fit: WaveFit
    season: str
    weather: str
    peak_offset_h: float
    trough_offset_h: float
    observed_peak_offset_h: float
    observed_trough_offset_h: float
    observed_range: float
    peak_to_trough_h: float
    profile: tuple[tuple[float, float], ...]

    @property
    def fitted_range(self) -> float:
        """Peak-to-bottom range of the fitted sinusoid (twice its amplitude)."""
        return 2 * self.fit.amplitude


@dataclass(frozen=True)
class GroupSummary:
    """Aggregate over a group of days at one location.

    Attributes:
        location: The place.
        group: Group label (``all``, a season or a weather class).
        days: Number of days.
        mean_amplitude: Mean fitted amplitude, in degrees.
        median_rmse: Median root-mean-square error of the daily fits.
        median_fitted_peak_offset_h: Median fitted peak minus solar noon.
        median_observed_peak_offset_h: Median warmest hour minus solar noon.
        median_observed_trough_offset_h: Median coolest hour minus solar midnight.
        mean_observed_range: Mean warmest-minus-coolest, in degrees.
        mean_fitted_range: Mean peak-to-bottom of the fitted sinusoids.
        median_peak_to_trough_h: Median hours from the warmest to coolest hour.
    """

    location: Location
    group: str
    days: int
    mean_amplitude: float
    median_rmse: float
    median_fitted_peak_offset_h: float
    median_observed_peak_offset_h: float
    median_observed_trough_offset_h: float
    mean_observed_range: float
    mean_fitted_range: float
    median_peak_to_trough_h: float


def analyse_days(
    solar_days: dict[date, list[SolarReading]],
    latitude: float = 0.0,
    weather_by_day: dict[date, str] | None = None,
) -> list[DayResult]:
    """Fit each complete day and compare its extremes with solar noon/midnight.

    Args:
        solar_days: Readings for each solar day.
        latitude: Latitude, for the season.
        weather_by_day: Weather class to use instead of classifying each day
            from its own readings (e.g. when temperatures come from a home
            sensor and weather from Open-Meteo).

    Returns:
        One result per day with enough readings, oldest first.
    """
    results = []
    for day, readings in sorted(solar_days.items()):
        if len(readings) < MIN_SAMPLES_PER_DAY:
            continue
        samples = [(r.hour, r.temperature) for r in readings]
        noon = solar_noon_hour(day)
        midnight = (noon + 12.0) % 24.0
        fit = fit_day(samples)
        hot = max(samples, key=lambda s: s[1])
        cold = min(samples, key=lambda s: s[1])
        mean = statistics.fmean(t for _, t in samples)
        weather = (
            weather_by_day.get(day, UNKNOWN)
            if weather_by_day is not None
            else classify_weather(readings)
        )
        results.append(
            DayResult(
                day=day,
                fit=fit,
                season=season(day, latitude),
                weather=weather,
                peak_offset_h=signed_offset_hours(fit.peak_hour, noon),
                trough_offset_h=signed_offset_hours(fit.trough_hour, midnight),
                observed_peak_offset_h=signed_offset_hours(hot[0], noon),
                observed_trough_offset_h=signed_offset_hours(cold[0], midnight),
                observed_range=hot[1] - cold[1],
                peak_to_trough_h=(cold[0] - hot[0]) % 24.0,
                profile=tuple((h, t - mean) for h, t in samples),
            )
        )
    return results


def group_results(results: list[DayResult], by: str) -> dict[str, list[DayResult]]:
    """Split results into labelled groups.

    Args:
        results: Per-day results.
        by: ``all``, ``season`` or ``weather``.

    Returns:
        Results per group label, in a natural order (calendar or severity).

    Raises:
        ValueError: If ``by`` is not one of ``GROUP_BY``.
    """
    if by not in GROUP_BY:
        raise ValueError(f"group by must be one of {GROUP_BY}, not {by!r}")
    if by == "all":
        return {"all": list(results)}
    order = SEASONS if by == "season" else (*WEATHER_CLASSES, UNKNOWN)
    groups: dict[str, list[DayResult]] = defaultdict(list)
    for r in results:
        groups[getattr(r, by)].append(r)
    return {label: groups[label] for label in order if label in groups}


def summarise(
    location: Location, results: list[DayResult], group: str = "all"
) -> GroupSummary:
    """Reduce per-day results to means and medians (robust to odd days).

    Args:
        location: The place.
        results: Per-day results for the group.
        group: Group label.

    Returns:
        The summary.

    Raises:
        ValueError: If ``results`` is empty.
    """
    if not results:
        raise ValueError(f"{location.name}: no complete days")
    med = statistics.median
    mean = statistics.fmean
    return GroupSummary(
        location=location,
        group=group,
        days=len(results),
        mean_amplitude=mean(r.fit.amplitude for r in results),
        median_rmse=med(r.fit.rmse for r in results),
        median_fitted_peak_offset_h=med(r.peak_offset_h for r in results),
        median_observed_peak_offset_h=med(r.observed_peak_offset_h for r in results),
        median_observed_trough_offset_h=med(
            r.observed_trough_offset_h for r in results
        ),
        mean_observed_range=mean(r.observed_range for r in results),
        mean_fitted_range=mean(r.fitted_range for r in results),
        median_peak_to_trough_h=med(r.peak_to_trough_h for r in results),
    )


def average_fit(results: list[DayResult]) -> tuple[float, float]:
    """Average the daily fits as vectors, so peak hours average sensibly.

    Args:
        results: Per-day results.

    Returns:
        ``(amplitude, peak_hour)`` of the average sinusoid.
    """
    omega = 2 * math.pi / 24.0
    x = statistics.fmean(
        r.fit.amplitude * math.cos(omega * r.fit.peak_hour) for r in results
    )
    y = statistics.fmean(
        r.fit.amplitude * math.sin(omega * r.fit.peak_hour) for r in results
    )
    return math.hypot(x, y), (math.atan2(y, x) / omega) % 24.0


def profile_bands(
    results: list[DayResult], percentiles: tuple[int, ...] = BAND_PERCENTILES
) -> dict[int, dict[int, float]]:
    """Percentile bands of temperature (relative to each day's mean) by hour.

    Args:
        results: Per-day results.
        percentiles: Which percentiles to compute.

    Returns:
        ``{percentile: {hour: value}}`` for the hours that have data.
    """
    by_hour: dict[int, list[float]] = defaultdict(list)
    for r in results:
        for hour, anomaly in r.profile:
            by_hour[int(hour)].append(anomaly)
    return {
        q: {h: percentile(v, q) for h, v in sorted(by_hour.items())}
        for q in percentiles
    }


def analyse_with_external_weather(
    sensor_readings: list[Reading],
    weather_readings: list[Reading],
    location: Location,
) -> list[DayResult]:
    """Analyse a local sensor, taking each day's weather from another source.

    Args:
        sensor_readings: Hourly readings from the sensor (e.g. Home Assistant).
        weather_readings: Hourly readings with weather codes or cloud cover
            (e.g. Open-Meteo for the same place and dates).
        location: Where the sensor is.

    Returns:
        One result per day with enough sensor readings.
    """
    weather_days = to_solar_days(weather_readings, location.longitude)
    weather = {day: classify_weather(r) for day, r in weather_days.items()}
    days = to_solar_days(sensor_readings, location.longitude)
    return analyse_days(days, location.latitude, weather)


def run(
    locations: list[Location],
    start: date,
    end: date,
    fetch: Fetcher = urllib_fetch,
    group_by: str = "all",
    on_results: Callable[[Location, list[DayResult]], None] | None = None,
) -> list[GroupSummary]:
    """Fetch, fit and summarise every location for ``start``..``end``.

    Args:
        locations: Places to analyse.
        start: First day, inclusive.
        end: Last day, inclusive.
        fetch: Function that fetches a URL as JSON (replaceable in tests).
        group_by: ``all``, ``season`` or ``weather``.
        on_results: Called with each location's per-day results (for plots).

    Returns:
        One summary per location and group.
    """
    out = []
    for loc in locations:
        readings = fetch_hourly(loc, start, end, fetch)
        days = to_solar_days(readings, loc.longitude)
        results = analyse_days(days, loc.latitude)
        if on_results is not None:
            on_results(loc, results)
        out.extend(
            summarise(loc, group, label)
            for label, group in group_results(results, group_by).items()
        )
    return out


def format_table(summaries: list[GroupSummary]) -> str:
    """Format summaries as a plain-text table.

    Args:
        summaries: One row each.

    Returns:
        The table, one row per summary.
    """
    width = max([8, *(len(s.location.name) for s in summaries)]) + 2
    head = (
        f"{'location':<{width}}{'kind':<9}{'group':<14}{'days':>5}{'amp C':>7}"
        f"{'rmse C':>8}{'range C':>9}{'fit pk-noon h':>15}"
        f"{'obs pk-noon h':>15}{'obs lo-midn h':>15}{'pk->lo h':>10}"
    )
    rows = [head]
    rows.extend(
        f"{s.location.name:<{width}}{s.location.kind:<9}{s.group:<14}{s.days:>5}"
        f"{s.mean_amplitude:>7.1f}{s.median_rmse:>8.2f}"
        f"{s.mean_observed_range:>9.1f}"
        f"{s.median_fitted_peak_offset_h:>15.1f}"
        f"{s.median_observed_peak_offset_h:>15.1f}"
        f"{s.median_observed_trough_offset_h:>15.1f}"
        f"{s.median_peak_to_trough_h:>10.1f}"
        for s in summaries
    )
    return "\n".join(rows)
