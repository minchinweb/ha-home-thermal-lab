"""Measure how far the house is rotated off the compass grid, from OpenStreetMap.

Finds the building outline nearest the Home Assistant home position (Overpass
API), takes the length-weighted bearing of its walls modulo 90 degrees, and
reports the rotation of the "south" wall away from true south, positive when
the south-facing wall looks a little west of south.

Usage::

    uv run python scripts/house_orientation.py
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import itertools

from envfile import load_env

from custom_components.house_thermal_lab.ha_history import fetch_home_position

OVERPASS = "https://overpass-api.de/api/interpreter"


def _bearing(lat1, lon1, lat2, lon2) -> tuple[float, float]:
    """Bearing in degrees (0-180, wall direction) and length in metres."""
    dy = (lat2 - lat1) * 111_320.0
    dx = (lon2 - lon1) * 111_320.0 * math.cos(math.radians(lat1))
    return math.degrees(math.atan2(dx, dy)) % 180.0, math.hypot(dx, dy)


def main() -> None:
    """Print candidate buildings and their rotation."""
    load_env()
    lat, lon = fetch_home_position(os.environ["HA_URL"], os.environ["HA_TOKEN"])
    query = f'[out:json];way(around:40,{lat},{lon})["building"];out geom;'
    data = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(
        OVERPASS, data, headers={"User-Agent": "house-thermal-lab/0.1"}
    )
    with urllib.request.urlopen(request, timeout=60) as resp:
        ways = json.load(resp)["elements"]
    print(f"{len(ways)} building outline(s) within 40 m of the home position")
    for way in ways:
        pts = way["geometry"]
        sin_sum = cos_sum = 0.0
        for a, b in itertools.pairwise(pts):
            bearing, length = _bearing(a["lat"], a["lon"], b["lat"], b["lon"])
            # walls repeat every 90 degrees; average the angle times four
            sin_sum += length * math.sin(math.radians(4 * bearing))
            cos_sum += length * math.cos(math.radians(4 * bearing))
        turn = math.degrees(math.atan2(sin_sum, cos_sum)) / 4.0
        if turn > 45:
            turn -= 90
        coherence = math.hypot(sin_sum, cos_sum) / sum(
            _bearing(a["lat"], a["lon"], b["lat"], b["lon"])[1]
            for a, b in itertools.pairwise(pts)
        )
        print(
            f"  way {way['id']}: {len(pts) - 1} walls, tags "
            f"{way.get('tags', {})}; main wall bearing {turn % 90:.1f} deg from "
            f"north (mod 90), squareness {coherence:.2f}; "
            f"rotation off the grid {turn:+.1f} deg"
        )
    if not ways:
        print("nothing mapped there; a measurement from an aerial photo is needed")


if __name__ == "__main__":
    main()
