"""Measure how far the house is rotated off the compass grid, from OpenStreetMap.

Finds the building outline around the Home Assistant home position (Overpass
API), takes the length-weighted bearing of its walls modulo 90 degrees, and
reports the rotation of the "south" wall away from true south, positive when
the south-facing wall looks a little west of south. The web setup does the same
and draws the result.

Usage::

    uv run python scripts/house_orientation.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env

from custom_components.home_thermal_lab.ha_history import fetch_home_position
from custom_components.home_thermal_lab.orientation import (
    choose_outline,
    fetch_outlines,
    wall_rotation,
)


def main() -> None:
    """Print each nearby building and its rotation."""
    load_env()
    lat, lon = fetch_home_position(os.environ["HA_URL"], os.environ["HA_TOKEN"])
    outlines = fetch_outlines(lat, lon)
    print(f"{len(outlines)} building outline(s) within 40 m of the home position")
    chosen = choose_outline(outlines, (lat, lon))
    for outline in outlines:
        turn, squareness = wall_rotation(outline)
        mark = "  <- the one used" if outline is chosen else ""
        print(
            f"  {len(outline) - 1} walls; main wall bearing {turn % 90:.1f} deg "
            f"from north (mod 90), squareness {squareness:.2f}; rotation off the "
            f"grid {turn:+.1f} deg{mark}"
        )
    if not outlines:
        print("nothing mapped there; a measurement from an aerial photo is needed")


if __name__ == "__main__":
    main()
