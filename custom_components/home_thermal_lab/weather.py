"""Classify days by season and weather."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from .readings import SolarReading

# WMO weather interpretation codes, as used by Open-Meteo.
_SNOW = frozenset({71, 73, 75, 77, 85, 86})
_RAIN = frozenset({51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82})
_STORM = frozenset({95, 96, 99})
_FOG = frozenset({45, 48})

# Hours of a given weather before it names the whole day.
_MIN_HOURS = 3
# Mean cloud cover (percent) boundaries between sunny, partly cloudy and cloudy.
_SUNNY_BELOW = 25
_CLOUDY_ABOVE = 75

SEASONS = ("winter", "spring", "summer", "autumn")
WEATHER_CLASSES = ("sunny", "partly cloudy", "cloudy", "fog", "rain", "snow", "storm")
UNKNOWN = "unknown"


def season(day: date, latitude: float) -> str:
    """Meteorological season, flipped for the southern hemisphere.

    Args:
        day: The date.
        latitude: Latitude in degrees; negative means southern hemisphere.

    Returns:
        One of ``winter``, ``spring``, ``summer`` or ``autumn``.
    """
    index = (day.month % 12) // 3  # Dec-Feb 0, Mar-May 1, Jun-Aug 2, Sep-Nov 3
    if latitude < 0:
        index = (index + 2) % 4
    return SEASONS[index]


def classify_weather(readings: list[SolarReading]) -> str:
    """Name a day's weather from its hourly codes and cloud cover.

    Precipitation wins (snow, then rain), then storms and fog; otherwise the
    mean cloud cover decides between sunny, partly cloudy and cloudy.

    Args:
        readings: The day's readings.

    Returns:
        One of ``WEATHER_CLASSES``, or ``unknown`` with no weather data.
    """
    codes = [r.weather_code for r in readings if r.weather_code is not None]
    if codes:
        if any(c in _STORM for c in codes):
            return "storm"
        if sum(c in _SNOW for c in codes) >= _MIN_HOURS:
            return "snow"
        if sum(c in _RAIN for c in codes) >= _MIN_HOURS:
            return "rain"
        if sum(c in _FOG for c in codes) >= _MIN_HOURS:
            return "fog"
    clouds = [r.cloud_cover for r in readings if r.cloud_cover is not None]
    if not clouds:
        return UNKNOWN
    mean = sum(clouds) / len(clouds)
    if mean < _SUNNY_BELOW:
        return "sunny"
    if mean < _CLOUDY_ABOVE:
        return "partly cloudy"
    return "cloudy"
