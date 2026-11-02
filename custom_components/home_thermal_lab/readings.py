"""Plain data types shared by the data sources and the experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Reading:
    """One hourly observation at a place, timestamped in UTC.

    Attributes:
        time: Naive UTC timestamp.
        temperature: Air temperature in degrees Celsius.
        weather_code: WMO weather code, when known.
        cloud_cover: Cloud cover in percent, when known.
    """

    time: datetime
    temperature: float
    weather_code: int | None = None
    cloud_cover: float | None = None


@dataclass(frozen=True)
class SolarReading:
    """A reading on the local-mean-solar-time clock.

    Attributes:
        hour: Hours since local solar midnight, in [0, 24).
        temperature: Air temperature in degrees Celsius.
        weather_code: WMO weather code, when known.
        cloud_cover: Cloud cover in percent, when known.
    """

    hour: float
    temperature: float
    weather_code: int | None = None
    cloud_cover: float | None = None
