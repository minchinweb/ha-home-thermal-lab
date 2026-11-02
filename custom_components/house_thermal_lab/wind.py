"""Hourly wind speed and direction from Open-Meteo (hypothesis 12).

Uses the forecast endpoint with ``past_days``, which (unlike the archive) has
data up to the present hour.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
import urllib.parse

from .open_meteo import Fetcher, urllib_fetch

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FACES = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}


@dataclass(frozen=True)
class WindReading:
    """Wind at one hour.

    Attributes:
        time: Start of the hour (UTC).
        speed: Speed in metres per second.
        direction: Direction the wind comes *from*, degrees clockwise from north.
    """

    time: datetime
    speed: float
    direction: float

    def face_component(self, face: str) -> float:
        """Speed blowing onto a face (0 when the wind comes from behind it).

        Args:
            face: One of ``N``, ``E``, ``S``, ``W`` (the way the face looks).

        Returns:
            Speed times the cosine of the angle between wind and face, floored at 0.
        """
        angle = math.radians(self.direction - FACES[face])
        return self.speed * max(math.cos(angle), 0.0)


def build_url(latitude: float, longitude: float, past_days: int) -> str:
    """Build the forecast URL for recent hourly wind in GMT."""
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "past_days": past_days,
            "forecast_days": 1,
            "hourly": "wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "ms",
            "timezone": "GMT",
        }
    )
    return f"{FORECAST_URL}?{query}"


def parse_wind(body: dict) -> list[WindReading]:
    """Turn the API body into readings, skipping hours with missing values."""
    hourly = body.get("hourly", {})
    out = []
    for stamp, speed, direction in zip(
        hourly.get("time", []),
        hourly.get("wind_speed_10m", []),
        hourly.get("wind_direction_10m", []),
        strict=False,
    ):
        if speed is None or direction is None:
            continue
        when = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        out.append(WindReading(when, float(speed), float(direction)))
    return out


def fetch_wind(
    latitude: float,
    longitude: float,
    past_days: int,
    fetch: Fetcher = urllib_fetch,
) -> list[WindReading]:
    """Fetch recent hourly wind (blocking)."""
    return parse_wind(fetch(build_url(latitude, longitude, past_days)))
