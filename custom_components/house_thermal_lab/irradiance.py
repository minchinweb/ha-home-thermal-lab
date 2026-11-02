"""Hourly solar irradiance from Open-Meteo (hypothesis 11).

Uses the forecast endpoint with ``past_days``. Open-Meteo reports radiation as
the mean over the *preceding* hour, so a reading stamped 13:00 covers 12:00 to
13:00.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
import urllib.parse

from .open_meteo import Fetcher, urllib_fetch
from .wind import FACES, FORECAST_URL


@dataclass(frozen=True)
class Irradiance:
    """Mean irradiance over the hour ending at ``time`` (UTC), in W/m2.

    Attributes:
        time: End of the hour.
        direct_normal: Beam irradiance on a surface facing the sun.
        diffuse: Diffuse irradiance on a horizontal surface.
    """

    time: datetime
    direct_normal: float
    diffuse: float

    def on_face(self, face: str, azimuth: float, elevation: float) -> float:
        """Irradiance on a vertical wall.

        Args:
            face: One of ``N``, ``E``, ``S``, ``W`` (the way the wall looks).
            azimuth: Sun compass azimuth in degrees.
            elevation: Sun elevation in degrees.

        Returns:
            Beam on the wall (zero when the sun is behind it or down) plus half
            the diffuse light (a vertical wall sees half the sky).
        """
        if elevation <= 0:
            return 0.0
        cos_incidence = math.cos(math.radians(elevation)) * math.cos(
            math.radians(azimuth - FACES[face])
        )
        return self.direct_normal * max(cos_incidence, 0.0) + 0.5 * self.diffuse


def build_url(latitude: float, longitude: float, past_days: int) -> str:
    """Build the forecast URL for recent hourly irradiance in GMT."""
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "past_days": past_days,
            "forecast_days": 1,
            "hourly": "direct_normal_irradiance,diffuse_radiation",
            "timezone": "GMT",
        }
    )
    return f"{FORECAST_URL}?{query}"


def parse_irradiance(body: dict) -> list[Irradiance]:
    """Turn the API body into readings, skipping hours with missing values."""
    hourly = body.get("hourly", {})
    out = []
    for stamp, direct, diffuse in zip(
        hourly.get("time", []),
        hourly.get("direct_normal_irradiance", []),
        hourly.get("diffuse_radiation", []),
        strict=False,
    ):
        if direct is None or diffuse is None:
            continue
        when = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        out.append(Irradiance(when, float(direct), float(diffuse)))
    return out


def fetch_irradiance(
    latitude: float,
    longitude: float,
    past_days: int,
    fetch: Fetcher = urllib_fetch,
) -> list[Irradiance]:
    """Fetch recent hourly irradiance (blocking)."""
    return parse_irradiance(fetch(build_url(latitude, longitude, past_days)))
