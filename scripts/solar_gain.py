"""Predict a room's solar gain from sun position and irradiance (hypothesis 11).

The office sensor and the office air-quality sensor are one room, so they are
averaged into a single "Office" series.

Two views, both in daytime bins when the room's own zone is not calling for heat
(this bin or the one before):

1. **By wall.** ``dT/dt = a * (outdoor - room) + c + sum over faces f of g_f *
   I_f``, where ``I_f`` is the irradiance (W/m2) on a vertical wall facing N, E,
   S or W (beam light from Open-Meteo times the cosine onto the wall, plus half
   the diffuse light). Scored on the last third of the days against the same
   model without the solar terms.
2. **By sun direction (shading).** Trees to the south and east and a low house
   immediately south mean the sun only reaches the windows once it is high enough
   for its compass direction. The room's cooling-law residual in sunny bins (beam
   above ``--sunny`` W/m2) is summed per sun-azimuth sector and elevation band and
   divided by the beam light, giving the warming per 100 W/m2 of beam. A gain that
   is near zero in a (direction, height) cell where the beam is strong marks a
   blocked sun path; the rest is the unshaded window.

Hourly irradiance is the mean of the preceding hour and is matched to the hour
that ends after the bin's midpoint.

Usage::

    uv run python scripts/solar_gain.py --days 14
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

import itertools

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

MIN_BINS = 40
MIN_ELEVATION = 3.0
SAME_ROOM = ("Office sensor", "Office AQ")
AZIMUTH_EDGES = [90, 135, 170, 205, 250, 280]
ELEVATION_EDGES = [0, 8, 14, 90]
SHADING_ROOMS = ["Z1 kitchen", "Z3 master", "N bedroom", "W bedroom", "Office"]


def _cell(value: float, se: float) -> str:
    star = "*" if se > 0 and abs(value) > 2 * se else " "
    return f"{value * 1000:+.2f}{star}"


def _room_series(stats, start, bins, width):
    series = {
        name: _bin_means(stats.get(entity, []), start, bins, width)
        for name, entity in ROOMS.items()
    }
    pair = np.vstack([series.pop(n) for n in SAME_ROOM])
    count = (~np.isnan(pair)).sum(axis=0)
    series["Office"] = np.where(
        count > 0, np.nansum(pair, axis=0) / np.maximum(count, 1), np.nan
    )
    return series


def main() -> None:
    """Print the by-wall fit and the shading table."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--sunny", type=float, default=100.0, help="beam W/m2 threshold")
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
    face = {
        f: np.array(
            [
                h.on_face(f, azimuth[i], elevation[i]) if h else np.nan
                for i, h in enumerate(held)
            ]
        )
        for f in FACES
    }
    beam = np.array([h.direct_normal if h else np.nan for h in held])
    day = (elevation > MIN_ELEVATION) & ~np.isnan(face["S"])

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

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, [OUTDOOR, *ROOMS.values()], start, end, period="5minute"
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    series = _room_series(stats, start, bins, width)
    zone_of = {**ZONE_OF_ROOM, "Office": "z4"}

    sunny = day & (beam >= args.sunny)
    print(
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; daytime bins "
        f"{int(day.sum())}, sunny bins (beam >= {args.sunny:.0f}) {int(sunny.sum())};"
        f" peak beam {np.nanmax(beam):.0f} W/m2"
    )
    print(
        "sun in the sunny bins: elevation "
        f"{elevation[sunny].min():.0f} to {elevation[sunny].max():.0f} deg, "
        f"azimuth {azimuth[sunny].min():.0f} to {azimuth[sunny].max():.0f} deg\n"
    )

    print("1. By wall (milli-C/h per W/m2 on the wall)")
    print(
        f"{'room':<16}{'n':>5}"
        + "".join(f"{'g_' + f:>9}" for f in FACES)
        + f"{'RMSE base':>11}{'RMSE solar':>12}"
    )
    split = bins * 2 // 3
    residual = {}
    for name, room in series.items():
        z = zone_of[name]
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        own_off = (heat[z] == 0) & (np.concatenate([[1.0], heat[z][:-1]]) == 0)
        sel = day & own_off & ~np.isnan(y) & ~np.isnan(diff)
        if sel.sum() < MIN_BINS:
            print(f"{name:<16}{int(sel.sum()):>5}  too little data")
            continue
        x_all = np.column_stack([diff, *(face[f] for f in FACES), np.ones(bins)])
        x_base = np.column_stack([diff, np.ones(bins)])
        train = sel & (np.arange(bins) < split)
        test = sel & (np.arange(bins) >= split)
        b, s, _ = _ols(x_all[sel], y[sel])
        row = f"{name:<16}{int(sel.sum()):>5}" + "".join(
            f"{_cell(b[i + 1], s[i + 1]):>9}" for i in range(len(FACES))
        )
        if train.sum() >= MIN_BINS and test.sum() >= 10:
            bs = _ols(x_all[train], y[train])[0]
            bb = _ols(x_base[train], y[train])[0]
            rs = np.sqrt(np.mean((y[test] - x_all[test] @ bs) ** 2))
            rb = np.sqrt(np.mean((y[test] - x_base[test] @ bb) ** 2))
            row += f"{rb:>11.2f}{rs:>12.2f}"
        else:
            row += f"{'-':>11}{'-':>12}"
        print(row)

        # residual of the cooling law fit where the sun is weak, for view 2
        dull = sel & (beam < 20)
        if dull.sum() >= MIN_BINS:
            base = _ols(x_base[dull], y[dull])[0]
            residual[name] = (y - x_base @ base, sel)

    print(
        "\n2. By sun direction: warming per 100 W/m2 of beam, C/h "
        f"(sunny bins; n in brackets)\n{'azimuth':>13}{'elevation':>11}"
        + "".join(f"{r[:11]:>14}" for r in SHADING_ROOMS)
    )
    for a0, a1 in itertools.pairwise(AZIMUTH_EDGES):
        for e0, e1 in itertools.pairwise(ELEVATION_EDGES):
            cell = sunny & (azimuth >= a0) & (azimuth < a1)
            cell &= (elevation >= e0) & (elevation < e1)
            if cell.sum() < 4:
                continue
            row = f"{a0:>5}-{a1:<7}{e0:>4}-{e1:<6}"
            for name in SHADING_ROOMS:
                if name not in residual:
                    row += f"{'-':>14}"
                    continue
                r, sel = residual[name]
                use = cell & sel & ~np.isnan(r)
                if use.sum() < 4:
                    row += f"{'-':>14}"
                    continue
                gain = r[use].sum() / beam[use].sum() * 100.0
                row += f"{gain:>+9.2f} ({use.sum():>2})"
            print(row)
    print(
        "\n* = beyond two standard errors (bins are not independent). RMSE is in C/h "
        "on the last third of the days."
    )


if __name__ == "__main__":
    main()
