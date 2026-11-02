"""Solar gain, window loss and roof gain per room (hypothesis 11, second model).

Each room has the windows the house owner described, instead of a fit over all
four walls:

* the N bedroom: a north window (second storey) and a roof deck above it;
* master bedroom: a south window and a roof deck;
* the W bedroom: a west window;
* office: an east window (limited winter light);
* kitchen: large south and west windows.

``--rotation`` turns every wall by that many degrees clockwise from the compass
grid (the house is slightly off north; see ``scripts/house_orientation.py``).

Per room, two fits in bins when its own zone is not calling for heat:

* day: ``dT/dt = a * diff + c + g_window * I_window [+ r * roof]``, where the
  window term is beam plus half diffuse light on that wall, and the roof term is
  light on a flat surface;
* night: ``dT/dt = a * diff + c + d * clear`` with ``clear`` the clear-sky
  fraction (1 - cloud cover), for bins with no furnace call anywhere. A negative
  ``d`` is a room losing extra heat to a clear sky (radiation out of the windows
  and roof) on top of the air-temperature term.

Usage::

    uv run python scripts/solar_windows.py --days 14 --rotation 0
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import (
    OUTDOOR,
    ROOMS,
    ZONES,
    _bin_means,
    _ols,
    _overlap_fraction,
)
from thermal_momentum import ZONE_OF_ROOM

from custom_components.house_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.house_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.house_thermal_lab.hvac import runs_from_states
from custom_components.house_thermal_lab.irradiance import fetch_irradiance
from custom_components.house_thermal_lab.solar import (
    solar_azimuth_degrees,
    solar_elevation_degrees,
)
from custom_components.house_thermal_lab.wind import FACES

# room -> window faces and roof faces (face, tilt in degrees; None = --pitch)
WINDOWS = {
    "N bedroom": {"walls": ["N"], "roof": [("E", None), ("W", None)]},
    "Z3 master": {"walls": ["S"], "roof": [("E", None), ("W", None)]},
    "W bedroom": {"walls": ["W"], "roof": []},
    "Z4 office": {"walls": ["E"], "roof": []},
    "Z1 kitchen": {"walls": ["S", "W", "N"], "roof": [("W", 14.04)]},
    "S basement": {"walls": ["S"], "roof": []},
    "SE basement": {"walls": ["S"], "roof": []},
    "NE basement": {"walls": ["E"], "roof": []},
}
MIN_BINS = 40
MIN_ELEVATION = 3.0


def _cell(value: float, se: float, scale: float = 1000.0) -> str:
    star = "*" if se > 0 and abs(value) > 2 * se else " "
    return f"{value * scale:+.2f}{star}"


def main() -> None:
    """Print the per-room window, roof and clear-sky fits."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--rotation", type=float, default=0.0, help="degrees clockwise")
    p.add_argument("--pitch", type=float, default=45.0, help="main roof tilt, degrees")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    by_end = {r.time: r for r in fetch_irradiance(lat, lon, args.days + 1)}
    mids = [start + (i + 0.5) * width for i in range(bins)]
    elevation = np.array([solar_elevation_degrees(m, lat, lon) for m in mids])
    azimuth = np.array([solar_azimuth_degrees(m, lat, lon) for m in mids])
    held = [
        by_end.get(m.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        for m in mids
    ]
    known = np.array([h is not None for h in held])
    # a wall turned `rotation` degrees clockwise sees the sun at azimuth - rotation
    face = {
        f: np.array(
            [
                h.on_face(f, azimuth[i] - args.rotation, elevation[i]) if h else np.nan
                for i, h in enumerate(held)
            ]
        )
        for f in FACES
    }
    planes: dict[tuple[str, float], np.ndarray] = {}

    def plane(face_name: str, tilt: float) -> np.ndarray:
        key = (face_name, tilt)
        if key not in planes:
            planes[key] = np.array(
                [
                    h.on_plane(
                        face_name, tilt, azimuth[i] - args.rotation, elevation[i]
                    )
                    if h
                    else np.nan
                    for i, h in enumerate(held)
                ]
            )
        return planes[key]

    clear = np.array([1.0 - h.cloud_cover / 100.0 if h else np.nan for h in held])
    day = (elevation > MIN_ELEVATION) & known
    night = (elevation < -6.0) & known

    heat = {}
    for z in ZONES:
        states = fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        heat[z] = _overlap_fraction(
            runs_from_states(states, end, {"heating"}, "hvac_action"),
            start,
            bins,
            width,
        )
    furnace_off = np.all(
        [(heat[z] == 0) & (np.concatenate([[1.0], heat[z][:-1]]) == 0) for z in ZONES],
        axis=0,
    )
    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, [OUTDOOR, *ROOMS.values()], start, end, period="5minute"
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)

    print(
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; wall rotation "
        f"{args.rotation:+.0f} deg; clear-sky fraction on night bins: mean "
        f"{np.nanmean(clear[night]):.2f}"
    )
    print("window and roof terms in mC/h per W/m2; clear-sky term in mC/h\n")
    for name, spec in WINDOWS.items():
        z = ZONE_OF_ROOM[name]
        room = _bin_means(stats.get(ROOMS[name], []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        own_off = (heat[z] == 0) & (np.concatenate([[1.0], heat[z][:-1]]) == 0)
        ok = ~np.isnan(y) & ~np.isnan(diff)

        sel = day & own_off & ok
        labels = [f"{f} wall" for f in spec["walls"]]
        cols = [diff[sel], np.ones(sel.sum()), *(face[f][sel] for f in spec["walls"])]
        for f, tilt in spec["roof"]:
            tilt = args.pitch if tilt is None else tilt
            labels.append(f"{f} roof {tilt:.0f}")
            cols.append(plane(f, tilt)[sel])
        row = f"{name:<12}{int(sel.sum()):>5} day"
        if sel.sum() >= MIN_BINS:
            b, s, _ = _ols(np.column_stack(cols), y[sel])
            row += "  " + "  ".join(
                f"{label} {_cell(b[2 + i], s[2 + i])}" for i, label in enumerate(labels)
            )
        else:
            row += "  too little data"

        sel = night & furnace_off & ok & ~np.isnan(clear)
        if sel.sum() >= MIN_BINS:
            x = np.column_stack([diff[sel], np.ones(sel.sum()), clear[sel]])
            b, s, _ = _ols(x, y[sel])
            row += f"  | night {int(sel.sum())}: clear sky {_cell(b[2], s[2])}"
        print(row)
    print("\n* = beyond two standard errors (bins are not independent)")


if __name__ == "__main__":
    main()
