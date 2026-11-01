"""Experiments for hypotheses 01 (sine wave) and 02 (solar-noon peak)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import statistics

from .locations import Location
from .open_meteo import Fetcher, fetch_hourly, to_solar_days, urllib_fetch
from .solar import solar_noon_hour
from .wave_fit import WaveFit, fit_day, signed_offset_hours

MIN_SAMPLES_PER_DAY = 22


@dataclass(frozen=True)
class DayResult:
    """One fitted day."""

    day: date
    fit: WaveFit
    peak_offset_h: float  # fitted peak minus solar noon
    trough_offset_h: float  # fitted trough minus solar midnight
    observed_peak_offset_h: float  # warmest sample minus solar noon
    observed_trough_offset_h: float  # coolest sample minus solar midnight


@dataclass(frozen=True)
class LocationSummary:
    """Aggregate over all days at one location."""

    location: Location
    days: int
    mean_amplitude: float
    median_rmse: float
    median_fitted_peak_offset_h: float
    median_observed_peak_offset_h: float
    median_observed_trough_offset_h: float


def analyse_days(
    solar_days: dict[date, list[tuple[float, float]]],
) -> list[DayResult]:
    """Fit each complete day and compare its extremes with solar noon/midnight."""
    results = []
    for day, samples in sorted(solar_days.items()):
        if len(samples) < MIN_SAMPLES_PER_DAY:
            continue
        noon = solar_noon_hour(day)
        midnight = (noon + 12.0) % 24.0
        fit = fit_day(samples)
        hot = max(samples, key=lambda s: s[1])[0]
        cold = min(samples, key=lambda s: s[1])[0]
        results.append(
            DayResult(
                day,
                fit,
                signed_offset_hours(fit.peak_hour, noon),
                signed_offset_hours(fit.trough_hour, midnight),
                signed_offset_hours(hot, noon),
                signed_offset_hours(cold, midnight),
            )
        )
    return results


def summarise(location: Location, results: list[DayResult]) -> LocationSummary:
    """Reduce per-day results to medians (robust to odd weather days)."""
    if not results:
        raise ValueError(f"{location.name}: no complete days")
    med = statistics.median
    return LocationSummary(
        location,
        len(results),
        statistics.fmean(r.fit.amplitude for r in results),
        med(r.fit.rmse for r in results),
        med(r.peak_offset_h for r in results),
        med(r.observed_peak_offset_h for r in results),
        med(r.observed_trough_offset_h for r in results),
    )


def run(
    locations: list[Location],
    start: date,
    end: date,
    fetch: Fetcher = urllib_fetch,
) -> list[LocationSummary]:
    """Fetch, fit and summarise every location for ``start``..``end``."""
    out = []
    for loc in locations:
        samples = fetch_hourly(loc, start, end, fetch)
        days = to_solar_days(samples, loc.longitude)
        out.append(summarise(loc, analyse_days(days)))
    return out


def format_table(summaries: list[LocationSummary]) -> str:
    """Plain-text table, one row per location."""
    head = (
        f"{'location':<14}{'kind':<10}{'days':>5}{'amp C':>8}{'rmse C':>8}"
        f"{'fit peak-noon h':>17}{'obs peak-noon h':>17}{'obs low-midn h':>16}"
    )
    rows = [head]
    for s in summaries:
        rows.append(
            f"{s.location.name:<14}{s.location.kind:<10}{s.days:>5}"
            f"{s.mean_amplitude:>8.1f}{s.median_rmse:>8.2f}"
            f"{s.median_fitted_peak_offset_h:>17.1f}"
            f"{s.median_observed_peak_offset_h:>17.1f}"
            f"{s.median_observed_trough_offset_h:>16.1f}"
        )
    return "\n".join(rows)
