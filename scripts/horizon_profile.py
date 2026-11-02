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

import itertools

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

from custom_components.home_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.home_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.home_thermal_lab.hvac import runs_from_states
from custom_components.home_thermal_lab.irradiance import fetch_irradiance
from custom_components.home_thermal_lab.solar import (
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
    """Fit one room's windows and roof faces with stepped horizons.

    ``roof_mode`` is ``none`` (roof unshaded), ``shared`` (roof uses the wall
    horizon) or ``separate`` (roof has its own horizon). The horizon vector has
    ``SECTORS`` entries, or twice that for ``separate`` (walls then roof).
    """

    def __init__(self, y, diff, sector, elevation, walls, roofs, roof_mode):
        self.y, self.diff = y, diff
        self.sector, self.elevation = sector, elevation
        self.walls, self.roofs = walls, roofs  # lists of (beam, diffuse)
        self.roof_mode = roof_mode if roofs else "none"

    @property
    def size(self) -> int:
        """Length of the horizon vector."""
        return SECTORS * (2 if self.roof_mode == "separate" else 1)

    def design(self, horizon: np.ndarray) -> np.ndarray:
        """Design matrix for a horizon vector."""
        wall_clear = self.elevation >= horizon[self.sector]
        if self.roof_mode == "separate":
            roof_clear = self.elevation >= horizon[SECTORS + self.sector]
        elif self.roof_mode == "shared":
            roof_clear = wall_clear
        else:
            roof_clear = np.ones(len(self.y), dtype=bool)
        cols = [self.diff, np.ones(len(self.y))]
        cols += [beam * wall_clear + diffuse for beam, diffuse in self.walls]
        cols += [beam * roof_clear + diffuse for beam, diffuse in self.roofs]
        return np.column_stack(cols)

    def sse(self, horizon: np.ndarray, rows: np.ndarray) -> tuple[float, np.ndarray]:
        """Least-squares error and coefficients on ``rows``."""
        x = self.design(horizon)[rows]
        beta, *_ = np.linalg.lstsq(x, self.y[rows], rcond=None)
        return float(np.sum((self.y[rows] - x @ beta) ** 2)), beta

    def fit_horizon(self, rows: np.ndarray, beam_ref: np.ndarray) -> np.ndarray:
        """Coordinate descent over the sector horizons."""
        horizon = np.zeros(self.size)
        usable = [
            k
            for k in range(SECTORS)
            if ((self.sector == k) & rows & (beam_ref > 20)).sum() >= MIN_SECTOR_BINS
        ]
        slots = [
            k + SECTORS * layer for layer in range(self.size // SECTORS) for k in usable
        ]
        for _ in range(PASSES):
            for k in slots:
                best = (np.inf, horizon[k])
                for h in HORIZON_GRID:
                    trial = horizon.copy()
                    trial[k] = h
                    err, _ = self.sse(trial, rows)
                    if err < best[0] - 1e-12:
                        best = (err, h)
                horizon[k] = best[1]
        return horizon


def _cells(horizon: np.ndarray, covered: list[bool]) -> str:
    """One column per sector; ``.`` where the sun was too rarely seen."""
    return "".join(
        f"{horizon[k]:>9.0f}" if covered[k] else f"{'.':>9}" for k in range(SECTORS)
    )


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
    header = "".join(f"{lo:>4.0f}-{hi:<4.0f}" for lo, hi in itertools.pairwise(edges))
    print(f"{'room':<13}{'n':>5}  clear-sun height (deg) by sun azimuth: {header}")
    print(
        f"{'':<20}CV RMSE C/h: {'cooling law':>12}{'no shading':>12}{'walls only':>12}"
        f"{'roof shared':>13}{'roof own':>10}"
    )
    for name, spec in WINDOWS.items():
        if not spec["walls"]:
            print(f"{name:<13}       no window that sees direct sun")
            continue
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
        walls = [
            (np.nan_to_num(beam(f, 90.0)), np.nan_to_num(diffuse(90.0)))
            for f in spec["walls"]
        ]
        roofs = []
        for face_name, tilt in spec["roof"]:
            tilt = args.pitch if tilt is None else tilt
            roofs.append(
                (np.nan_to_num(beam(face_name, tilt)), np.nan_to_num(diffuse(tilt)))
            )
        ref = np.maximum(
            np.nan_to_num(beam(spec["walls"][0], 90.0)), np.nan_to_num(beam("S", 90.0))
        )
        covered = [
            ((sector == k) & rows & (ref > 20)).sum() >= MIN_SECTOR_BINS
            for k in range(SECTORS)
        ]
        y0, d0 = np.nan_to_num(y), np.nan_to_num(diff)
        models = {
            mode: RoomFit(y0, d0, sector, elevation, walls, roofs, mode)
            for mode in ("none", "shared", "separate")
        }
        base_x = np.column_stack([d0, np.ones(bins)])

        errors = {k: [] for k in ("base", "flat", "none", "shared", "separate")}
        for d in np.unique(day_index[rows]):
            test = rows & (day_index == d)
            train = rows & (day_index != d)
            if test.sum() < 4 or train.sum() < MIN_BINS:
                continue
            beta = np.linalg.lstsq(base_x[train], y0[train], rcond=None)[0]
            errors["base"].extend((y0[test] - base_x[test] @ beta) ** 2)
            flat = models["none"]
            zero = np.zeros(flat.size)
            _, beta = flat.sse(zero, train)
            errors["flat"].extend((y0[test] - flat.design(zero)[test] @ beta) ** 2)
            for mode, model in models.items():
                h = model.fit_horizon(train, ref)
                _, beta = model.sse(h, train)
                errors[mode].extend((y0[test] - model.design(h)[test] @ beta) ** 2)

        walls_only = models["none"].fit_horizon(rows, ref)
        print(
            f"{name:<13}{int(rows.sum()):>5}  {_cells(walls_only, covered)}   (walls)"
        )
        if roofs:
            own = models["separate"].fit_horizon(rows, ref)
            print(f"{'':<20}{_cells(own[SECTORS:], covered)}   (roof, own horizon)")
        rmse = {k: np.sqrt(np.mean(v)) for k, v in errors.items()}
        print(
            f"{'':<20}{'':>13}{rmse['base']:>12.3f}{rmse['flat']:>12.3f}"
            f"{rmse['none']:>12.3f}"
            + (
                f"{rmse['shared']:>13.3f}{rmse['separate']:>10.3f}"
                if roofs
                else f"{'-':>13}{'-':>10}"
            )
        )
    print(
        "\n'.' = sun spent fewer than 5 sunny bins in that sector. A height of 0 means"
        "\nclear, 30 means blocked at every height seen. CV = leave one day out."
    )


if __name__ == "__main__":
    main()
