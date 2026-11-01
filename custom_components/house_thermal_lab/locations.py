"""Locations of interest for comparing daily temperature waves.

Locations are plain data so users can supply their own. The intent is a mix
of ``home`` locations (where the user lives or has data for) and
``paradise`` locations (benign climates, e.g. tropical islands), but ``kind``
is a free-form label.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    """A place to fetch historical temperatures for."""

    name: str
    latitude: float
    longitude: float
    kind: str = "other"

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"{self.name}: latitude out of range")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"{self.name}: longitude out of range")


# Starting suggestions only; replace or extend via configuration.
EXAMPLE_LOCATIONS: tuple[Location, ...] = (
    Location("Edmonton", 53.5461, -113.4938, "home"),
    Location("Dieppe", 49.9229, 1.0777, "home"),
    Location("Tahiti", -17.6509, -149.4260, "paradise"),
)


def locations_from_config(items: list[dict]) -> list[Location]:
    """Build locations from config dicts: ``name``, ``latitude``, ``longitude``, ``kind``."""
    return [
        Location(
            name=item["name"],
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            kind=item.get("kind", "other"),
        )
        for item in items
    ]


def home_location(latitude: float, longitude: float, name: str = "Home") -> Location:
    """The Home Assistant home zone (``hass.config.latitude`` / ``longitude``)."""
    return Location(name, latitude, longitude, "home")
