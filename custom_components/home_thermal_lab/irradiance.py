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
        cloud_cover: Cloud cover in percent (0 clear, 100 overcast).
    """

    time: datetime
    direct_normal: float
    diffuse: float
    cloud_cover: float = 0.0

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

    def beam_on_plane(
        self, face: str, tilt: float, azimuth: float, elevation: float
    ) -> float:
        """Beam irradiance on a tilted plane (zero when the sun is behind it).

        Args:
            face: Direction the plane faces: ``N``, ``E``, ``S`` or ``W``.
            tilt: Angle of the plane from horizontal, in degrees (90 is a wall).
            azimuth: Sun compass azimuth in degrees.
            elevation: Sun elevation in degrees.
        """
        if elevation <= 0:
            return 0.0
        el, tl = math.radians(elevation), math.radians(tilt)
        cos_incidence = math.sin(el) * math.cos(tl) + math.cos(el) * math.sin(
            tl
        ) * math.cos(math.radians(azimuth - FACES[face]))
        return self.direct_normal * max(cos_incidence, 0.0)

    def diffuse_on_plane(self, tilt: float, elevation: float) -> float:
        """Diffuse light a plane sees: ``(1 + cos(tilt)) / 2`` of the sky's."""
        if elevation <= 0:
            return 0.0
        return self.diffuse * (1 + math.cos(math.radians(tilt))) / 2

    def on_plane(
        self, face: str, tilt: float, azimuth: float, elevation: float
    ) -> float:
        """Beam plus diffuse irradiance on a tilted plane (a roof face, say)."""
        return self.beam_on_plane(face, tilt, azimuth, elevation) + (
            self.diffuse_on_plane(tilt, elevation)
        )


def build_url(latitude: float, longitude: float, past_days: int) -> str:
    """Build the forecast URL for recent hourly irradiance in GMT."""
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "past_days": past_days,
            "forecast_days": 1,
            "hourly": "direct_normal_irradiance,diffuse_radiation,cloud_cover",
            "timezone": "GMT",
        }
    )
    return f"{FORECAST_URL}?{query}"


def parse_irradiance(body: dict) -> list[Irradiance]:
    """Turn the API body into readings, skipping hours with missing values."""
    hourly = body.get("hourly", {})
    out = []
    clouds = hourly.get("cloud_cover") or []
    for i, (stamp, direct, diffuse) in enumerate(
        zip(
            hourly.get("time", []),
            hourly.get("direct_normal_irradiance", []),
            hourly.get("diffuse_radiation", []),
            strict=False,
        )
    ):
        if direct is None or diffuse is None:
            continue
        when = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        cloud = clouds[i] if i < len(clouds) and clouds[i] is not None else 0.0
        out.append(Irradiance(when, float(direct), float(diffuse), float(cloud)))
    return out


def fetch_irradiance(
    latitude: float,
    longitude: float,
    past_days: int,
    fetch: Fetcher = urllib_fetch,
) -> list[Irradiance]:
    """Fetch recent hourly irradiance (blocking)."""
    return parse_irradiance(fetch(build_url(latitude, longitude, past_days)))


def horizontal(reading: Irradiance, elevation: float) -> float:
    """Global irradiance on a flat surface (a stand-in for a shallow roof)."""
    if elevation <= 0:
        return 0.0
    return reading.direct_normal * math.sin(math.radians(elevation)) + reading.diffuse


def light_on_surfaces(
    reading: Irradiance,
    azimuth: float,
    elevation: float,
    walls: list[str],
    roofs: list[tuple[str, float]],
    rotation: float = 0.0,
    shaded: bool = False,
) -> float:
    """Summed light (W/m2) on the window walls and roof faces of one room.

    Args:
        reading: The hour's irradiance.
        azimuth: Sun compass azimuth in degrees.
        elevation: Sun elevation in degrees.
        walls: Window faces, each one of ``N``, ``E``, ``S``, ``W``.
        roofs: Roof faces as ``(face, tilt in degrees)``.
        rotation: Degrees the house is turned clockwise from the compass grid.
        shaded: Drop the beam light (trees and neighbours block the sun), keeping
            the diffuse sky light.
    """
    rel = azimuth - rotation
    scale = 0.0 if shaded else 1.0
    total = 0.0
    for face in walls:
        total += scale * reading.beam_on_plane(
            face, 90.0, rel, elevation
        ) + reading.diffuse_on_plane(90.0, elevation)
    for face, tilt in roofs:
        total += scale * reading.beam_on_plane(
            face, tilt, rel, elevation
        ) + reading.diffuse_on_plane(tilt, elevation)
    return total


def light_on_planes(
    reading: Irradiance,
    azimuth: float,
    elevation: float,
    planes: list,
) -> float:
    """Summed light (W/m2) on planes given by compass azimuth.

    Args:
        reading: The hour's irradiance.
        azimuth: Sun compass azimuth in degrees.
        elevation: Sun elevation in degrees.
        planes: ``[azimuth, tilt, shade_below]`` for each plane: the compass
            bearing it faces, degrees from horizontal, and the sun elevation
            below which the south-east to south-west beam is blocked.
    """
    if elevation <= 0:
        return 0.0
    total = 0.0
    el = math.radians(elevation)
    for plane_azimuth, tilt, shade_below in planes:
        tl = math.radians(tilt)
        cos_incidence = math.sin(el) * math.cos(tl) + math.cos(el) * math.sin(
            tl
        ) * math.cos(math.radians(azimuth - plane_azimuth))
        if not (120.0 <= azimuth < 210.0 and elevation < shade_below):
            total += reading.direct_normal * max(cos_incidence, 0.0)
        total += reading.diffuse_on_plane(tilt, elevation)
    return total
