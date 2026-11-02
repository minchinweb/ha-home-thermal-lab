"""Measure how far the house is turned off the compass grid, and draw it.

The building outline comes from OpenStreetMap (Overpass API). The rotation is
the length-weighted bearing of its walls modulo 90 degrees, positive when the
house is turned clockwise from north, which is the same as its south-facing
wall looking a little west of south (``scripts/house_orientation.py`` prints it
for the Home Assistant home position). Standard library only.
"""

from __future__ import annotations

import itertools
import json
import math
import urllib.parse
import urllib.request

OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
METRES_PER_DEGREE = 111_320.0

Point = tuple[float, float]  # (latitude, longitude)


def _metres(a: Point, b: Point) -> tuple[float, float]:
    """East and north distance in metres from ``a`` to ``b``."""
    return (
        (b[1] - a[1]) * METRES_PER_DEGREE * math.cos(math.radians(a[0])),
        (b[0] - a[0]) * METRES_PER_DEGREE,
    )


def wall_rotation(outline: list[Point]) -> tuple[float, float]:
    """Rotation off the compass grid, and how square the outline is.

    Walls repeat every 90 degrees, so the angles are multiplied by four before
    averaging (weighted by wall length).

    Args:
        outline: The corners, in order (a closed way repeats the first).

    Returns:
        The rotation in degrees, in (-45, 45], and the squareness from 0 to 1
        (1 when every wall lies on one grid).

    Raises:
        ValueError: The outline has no walls.
    """
    sin_sum = cos_sum = total = 0.0
    for a, b in itertools.pairwise(outline):
        east, north = _metres(a, b)
        length = math.hypot(east, north)
        bearing = math.degrees(math.atan2(east, north)) % 180.0
        sin_sum += length * math.sin(math.radians(4 * bearing))
        cos_sum += length * math.cos(math.radians(4 * bearing))
        total += length
    if total == 0:
        raise ValueError("the outline has no walls")
    turn = math.degrees(math.atan2(sin_sum, cos_sum)) / 4.0
    if turn > 45:
        turn -= 90
    return turn, math.hypot(sin_sum, cos_sum) / total


def _inside(point: Point, outline: list[Point]) -> bool:
    lat, lon = point
    inside = False
    for (lat1, lon1), (lat2, lon2) in itertools.pairwise(outline):
        if (lat1 > lat) != (lat2 > lat) and lon < lon1 + (lat - lat1) * (
            lon2 - lon1
        ) / (lat2 - lat1):
            inside = not inside
    return inside


def choose_outline(outlines: list[list[Point]], home: Point) -> list[Point] | None:
    """The outline around ``home``, else the one with the nearest corner."""
    for outline in outlines:
        if _inside(home, outline):
            return outline
    if not outlines:
        return None
    return min(
        outlines,
        key=lambda o: min(math.hypot(*_metres(home, p)) for p in o),
    )


def fetch_outlines(lat: float, lon: float, radius: int = 40) -> list[list[Point]]:
    """Building outlines within ``radius`` metres of a position (blocking)."""
    query = f'[out:json];way(around:{radius},{lat},{lon})["building"];out geom;'
    body = urllib.parse.urlencode({"data": query}).encode()
    error: OSError | None = None
    for url in OVERPASS:  # the public servers are often busy; try each
        request = urllib.request.Request(
            url, body, headers={"User-Agent": "home-thermal-lab/0.1"}
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as resp:
                ways = json.load(resp)["elements"]
            break
        except OSError as err:
            error = err
    else:
        raise error or OSError("no Overpass server answered")
    return [[(p["lat"], p["lon"]) for p in way["geometry"]] for way in ways]


def outline_svg(outline: list[Point], rotation: float, size: int = 280) -> str:
    """A drawing of the building with true north and the rotated south wall.

    The faint cross is true north-south and east-west; the arrow points the way
    the house's south wall faces with the given rotation.
    """
    home = outline[0]
    xs, ys = [], []
    for p in outline:
        east, north = _metres(home, p)
        xs.append(east)
        ys.append(north)
    cx_m, cy_m = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    scale = size * 0.5 / span
    mid = size / 2

    def at(east: float, north: float) -> str:
        return f"{mid + (east - cx_m) * scale:.1f},{mid - (north - cy_m) * scale:.1f}"

    polygon = " ".join(at(x, y) for x, y in zip(xs, ys, strict=True))
    azimuth = math.radians(180.0 + rotation)
    reach = size * 0.42
    tip_x = mid + reach * math.sin(azimuth)
    tip_y = mid - reach * math.cos(azimuth)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" font-family="sans-serif" font-size="13">'
        f'<line x1="{mid}" y1="6" x2="{mid}" y2="{size - 6}" stroke="#888" '
        f'stroke-width="1" stroke-dasharray="4 4"/>'
        f'<line x1="6" y1="{mid}" x2="{size - 6}" y2="{mid}" stroke="#888" '
        f'stroke-width="1" stroke-dasharray="4 4"/>'
        f'<polygon points="{polygon}" fill="rgba(110,150,220,0.35)" '
        f'stroke="#4a78c8" stroke-width="2"/>'
        f'<line x1="{mid}" y1="{mid}" x2="{tip_x:.1f}" y2="{tip_y:.1f}" '
        f'stroke="#e0562b" stroke-width="3"/>'
        f'<circle cx="{tip_x:.1f}" cy="{tip_y:.1f}" r="5" fill="#e0562b"/>'
        f'<text x="{mid + 6}" y="18" fill="#888">N</text>'
        f'<text x="6" y="{size - 8}" fill="#e0562b">'
        f"south wall faces {180.0 + rotation:.0f}° (rotation {rotation:+.1f}°)"
        f"</text></svg>"
    )
