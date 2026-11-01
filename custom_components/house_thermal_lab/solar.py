"""Solar timing in local mean solar time."""

from __future__ import annotations

from datetime import date
import math


def equation_of_time_minutes(day: date) -> float:
    """Equation of time in minutes (apparent minus mean solar time), approx."""
    b = 2 * math.pi * (day.timetuple().tm_yday - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def solar_noon_hour(day: date) -> float:
    """Hour of true solar noon on the local-mean-solar-time clock."""
    return 12.0 - equation_of_time_minutes(day) / 60.0
