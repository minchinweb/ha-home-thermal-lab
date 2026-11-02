"""Fit a horizon (shading) profile for each room's windows (hypothesis 11).

Trees to the south and east and a low house just south block the low sun. For
each room this fits ``dT/dt = a * diff + c + sum_f g_f * L_f`` over daytime bins
when the room's own zone is not heating, where each window's light is::

    L_f = beam_f * [sun elevation >= horizon(sun azimuth)] + diffuse_f

The horizon is a step per 30 degree sector of sun azimuth (90 to 270): the lowest
sun height at which that sector is clear, chosen from a grid by coordinate
descent on the fit error, with the gains ``g`` refit for every candidate. Roof
faces are treated as unshaded (they sit above the trees and the house to the
south). Every model is scored by leave-one-day-out cross-validation: the
horizon is re-fit with each day held out, then used to predict that day. Three
models are compared: the cooling law alone, windows without shading
(horizon = 0), and windows with the fitted horizon.

Sectors the sun never crossed in sunny bins are left at 0 and shown as ``.``.

Usage::

    uv run python scripts/horizon_profile.py --days 14 --rotation 10.4
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
    _overlap_fraction,
)
from solar_windows import WINDOWS
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

SECTOR_START = 90.0
SECTOR_WIDTH = 30.0
SECTORS = 6
HORIZON_GRID = np.arange(0.0, 31.0, 3.0)
MIN_SECTOR_BINS = 5
MIN_BINS = 60
PASSES = 3
MIN_ELEVATION = 3.0


class RoomFit:
    """Fit one room's windows with a stepped horizon."""

    def __init__(self, y, diff, sector, elevation, wall_beam, wall_diffuse, roofs):
        self.y, self.diff = y, diff
        self.sector, self.elevation = sector, elevation
        self.wall_beam, self.wall_diffuse = wall_beam, wall_diffuse
        self.roofs = roofs

    def design(self, horizon: np.ndarray) -> np.ndarray:
        """Design matrix for a horizon (one elevation per sector)."""
        clear = self.elevation >= horizon[self.sector]
        cols = [self.diff, np.ones(len(self.y))]
        for beam, diffuse in zip(self.wall_beam, self.wall_diffuse, strict=True):
            cols.append(beam * clear + diffuse)
        cols.extend(self.roofs)
        return np.column_stack(cols)

    def sse(self, horizon: np.ndarray, rows: np.ndarray) -> tuple[float, np.ndarray]:
        """Least-squares error and coefficients on ``rows``."""
        x = self.design(horizon)[rows]
        beta, *_ = np.linalg.lstsq(x, self.y[rows], rcond=None)
        return float(np.sum((self.y[rows] - x @ beta) ** 2)), beta

    def fit_horizon(self, rows: np.ndarray, beam_ref: np.ndarray) -> np.ndarray:
        """Coordinate descent over the sector horizons."""
        horizon = np.zeros(SECTORS)
        usable = [
            k
            for k in range(SECTORS)
            if ((self.sector == k) & rows & (beam_ref > 20)).sum() >= MIN_SECTOR_BINS
        ]
        for _ in range(PASSES):
            for k in usable:
                best = (np.inf, horizon[k])
                for h in HORIZON_GRID:
                    trial = horizon.copy()
                    trial[k] = h
                    err, _ = self.sse(trial, rows)
                    if err < best[0] - 1e-12:
                        best = (err, h)
                horizon[k] = best[1]
        return horizon


def main() -> None:
    """Print the fitted horizons and cross-validated errors."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--rotation", type=float, default=10.4, help="degrees clockwise")
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
    rel = azimuth - args.rotation
    sector = np.clip(
        ((azimuth - SECTOR_START) // SECTOR_WIDTH).astype(int), 0, SECTORS - 1
    )
    day_index = np.array([(m - start).days for m in mids])
    day = (elevation > MIN_ELEVATION) & known

    def beam(face: str, tilt: float) -> np.ndarray:
        return np.array(
            [
                h.beam_on_plane(face, tilt, rel[i], elevation[i]) if h else np.nan
                for i, h in enumerate(held)
            ]
        )

    def diffuse(tilt: float) -> np.ndarray:
        return np.array(
            [
                h.diffuse_on_plane(tilt, elevation[i]) if h else np.nan
                for i, h in enumerate(held)
            ]
        )

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

    print(
        f"{bins} bins from {start:%Y-%m-%d}; rotation {args.rotation:+.1f} deg, "
        f"roof {args.pitch:.0f} deg; sun azimuth sectors of {SECTOR_WIDTH:.0f} deg "
        f"from {SECTOR_START:.0f}\n"
    )
    edges = SECTOR_START + SECTOR_WIDTH * np.arange(SECTORS + 1)
    header = "".join(
        f"{lo:>4.0f}-{hi:<4.0f}" for lo, hi in zip(edges, edges[1:], strict=False)
    )
    print(f"{'room':<13}{'n':>5}  clear-sun height (deg) by sun azimuth: {header}")
    print(f"{'':<20}{'CV RMSE C/h: cooling law':>26}{'no shading':>12}{'horizon':>10}")
    for name, spec in WINDOWS.items():
        z = ZONE_OF_ROOM[name]
        room = _bin_means(stats.get(ROOMS[name], []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        own_off = (heat[z] == 0) & (np.concatenate([[1.0], heat[z][:-1]]) == 0)
        rows = day & own_off & ~np.isnan(y) & ~np.isnan(diff)
        if rows.sum() < MIN_BINS:
            print(f"{name:<13}{int(rows.sum()):>5}  too little data")
            continue
        walls = spec["walls"]
        roofs = []
        for face_name, tilt in spec["roof"]:
            tilt = args.pitch if tilt is None else tilt
            roofs.append(
                np.array(
                    [
                        h.on_plane(face_name, tilt, rel[k], elevation[k])
                        if h
                        else np.nan
                        for k, h in enumerate(held)
                    ]
                )
            )
        fit = RoomFit(
            np.nan_to_num(y),
            np.nan_to_num(diff),
            sector,
            elevation,
            [np.nan_to_num(beam(f, 90.0)) for f in walls],
            [np.nan_to_num(diffuse(90.0)) for _ in walls],
            [np.nan_to_num(r) for r in roofs],
        )
        # reference beam for deciding which sectors have enough sunny bins
        ref = np.nan_to_num(beam(walls[0], 90.0))
        ref = np.maximum(ref, np.nan_to_num(beam("S", 90.0)))

        horizon = fit.fit_horizon(rows, ref)
        covered = [
            ((sector == k) & rows & (ref > 20)).sum() >= MIN_SECTOR_BINS
            for k in range(SECTORS)
        ]

        errors = {"base": [], "flat": [], "horizon": []}
        for d in np.unique(day_index[rows]):
            test = rows & (day_index == d)
            train = rows & (day_index != d)
            if test.sum() < 4 or train.sum() < MIN_BINS:
                continue
            base_x = np.column_stack([fit.diff, np.ones(bins)])
            beta = np.linalg.lstsq(base_x[train], fit.y[train], rcond=None)[0]
            errors["base"].extend((fit.y[test] - base_x[test] @ beta) ** 2)
            zero = np.zeros(SECTORS)
            _, beta = fit.sse(zero, train)
            errors["flat"].extend((fit.y[test] - fit.design(zero)[test] @ beta) ** 2)
            h = fit.fit_horizon(train, ref)
            _, beta = fit.sse(h, train)
            errors["horizon"].extend((fit.y[test] - fit.design(h)[test] @ beta) ** 2)
        cells = "".join(
            f"{horizon[k]:>9.0f}" if covered[k] else f"{'.':>9}" for k in range(SECTORS)
        )
        print(f"{name:<13}{int(rows.sum()):>5}  {cells}")
        print(
            f"{'':<20}{np.sqrt(np.mean(errors['base'])):>26.3f}"
            f"{np.sqrt(np.mean(errors['flat'])):>12.3f}"
            f"{np.sqrt(np.mean(errors['horizon'])):>10.3f}"
        )
    print(
        "\n'.' = sun spent fewer than 5 sunny bins in that sector. A height of 0 means"
        "\nclear, 30 means blocked at every height seen. CV = leave one day out."
    )


if __name__ == "__main__":
    main()
