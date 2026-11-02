"""Predict a room's solar gain from sun position and irradiance (hypothesis 11).

For every room, in daytime bins when its own zone is not calling for heat (this
bin or the one before), fits::

    dT/dt = a * (outdoor - room) + c + sum over faces f of g_f * I_f

where ``I_f`` is the irradiance (W/m2) on a vertical wall facing N, E, S or W:
beam light from Open-Meteo times the cosine of the angle onto the wall, plus half
the diffuse light. ``g_f`` is that face's warming in C/h per W/m2. Each room is
then validated on held-out days: the model is fit on the first two thirds of the
days and scored on the last third, against the same model without the solar
terms. Hourly irradiance is the mean of the preceding hour and is matched to the
hour that ends after the bin's midpoint.

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


def _cell(value: float, se: float) -> str:
    star = "*" if se > 0 and abs(value) > 2 * se else " "
    return f"{value * 1000:+.2f}{star}"


def main() -> None:
    """Print one row per room."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--bin", type=int, default=15, help="minutes")
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
    day = (elevation > MIN_ELEVATION) & ~np.isnan(face["S"])

    runs = {}
    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in ZONES
    }
    for z in ZONES:
        runs[z] = _overlap_fraction(
            runs_from_states(climate[z], end, {"heating"}, "hvac_action"),
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

    peak = {f: np.nanmax(face[f][day]) for f in FACES}
    clear = np.nanmax([h.direct_normal for h in held if h is not None])
    print(
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; daytime bins "
        f"{int(day.sum())}; peak beam {clear:.0f} W/m2; peak on a wall: "
        + ", ".join(f"{f} {v:.0f}" for f, v in peak.items())
        + " W/m2\n"
    )
    print(
        f"{'room':<16}{'n':>5}"
        + "".join(f"{'g_' + f + ' mC/h':>11}" for f in FACES)
        + f"{'RMSE base':>11}{'RMSE solar':>12}"
    )
    split = bins * 2 // 3
    for name, entity in ROOMS.items():
        z = ZONE_OF_ROOM[name]
        room = _bin_means(stats.get(entity, []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        own_off = (runs[z] == 0) & (np.concatenate([[1.0], runs[z][:-1]]) == 0)
        sel = day & own_off & ~np.isnan(y) & ~np.isnan(diff)
        if sel.sum() < MIN_BINS:
            print(f"{name:<16}{int(sel.sum()):>5}  too little data")
            continue
        cols = [diff] + [face[f] for f in FACES]
        x_all = np.column_stack([*cols, np.ones(bins)])
        x_base = np.column_stack([diff, np.ones(bins)])
        train = sel.copy()
        train[split:] = False
        test = sel.copy()
        test[:split] = False
        b, s, _ = _ols(x_all[sel], y[sel])
        row = f"{name:<16}{int(sel.sum()):>5}" + "".join(
            f"{_cell(b[i + 1], s[i + 1]):>11}" for i in range(len(FACES))
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
    print(
        "\ng is in milli-C/h per W/m2 on the wall (* = beyond two standard errors;"
        "\nbins are not independent). RMSE is in C/h on the last third of the days."
    )


if __name__ == "__main__":
    main()
