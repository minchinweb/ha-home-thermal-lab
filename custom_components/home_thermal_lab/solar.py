"""Solar timing in local mean solar time."""

from __future__ import annotations

from datetime import UTC, date, datetime
import math


def equation_of_time_minutes(day: date) -> float:
    """Equation of time in minutes (apparent minus mean solar time), approx."""
    b = 2 * math.pi * (day.timetuple().tm_yday - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def solar_noon_hour(day: date) -> float:
    """Hour of true solar noon on the local-mean-solar-time clock."""
    return 12.0 - equation_of_time_minutes(day) / 60.0


def solar_elevation_degrees(when: datetime, latitude: float, longitude: float) -> float:
    """Approximate height of the sun above the horizon.

    Good to about a degree, which is enough to tell day from night.

    Args:
        when: The moment (timezone-aware).
        latitude: Degrees north.
        longitude: Degrees east.

    Returns:
        Elevation in degrees (negative below the horizon).
    """
    utc = when.astimezone(UTC)
    day = utc.timetuple().tm_yday
    declination = math.radians(23.44) * math.sin(2 * math.pi * (284 + day) / 365.0)
    solar_hours = (
        utc.hour
        + utc.minute / 60.0
        + utc.second / 3600.0
        + longitude / 15.0
        + equation_of_time_minutes(utc.date()) / 60.0
    )
    hour_angle = math.radians(15.0 * (solar_hours - 12.0))
    lat = math.radians(latitude)
    sin_elevation = math.sin(lat) * math.sin(declination) + math.cos(lat) * math.cos(
        declination
    ) * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elevation))))


def solar_azimuth_degrees(when: datetime, latitude: float, longitude: float) -> float:
    """Compass direction of the sun, degrees clockwise from north.

    Args:
        when: The moment (timezone-aware).
        latitude: Degrees north.
        longitude: Degrees east.

    Returns:
        Azimuth in degrees, 0 to 360 (180 is due south).
    """
    utc = when.astimezone(UTC)
    day = utc.timetuple().tm_yday
    declination = math.radians(23.44) * math.sin(2 * math.pi * (284 + day) / 365.0)
    solar_hours = (
        utc.hour
        + utc.minute / 60.0
        + utc.second / 3600.0
        + longitude / 15.0
        + equation_of_time_minutes(utc.date()) / 60.0
    )
    hour_angle = math.radians(15.0 * (solar_hours - 12.0))
    lat = math.radians(latitude)
    south_based = math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat) - math.tan(declination) * math.cos(lat),
    )
    return (math.degrees(south_based) + 180.0) % 360.0
