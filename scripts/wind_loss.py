"""Does wind speed or direction change how fast rooms cool? (hypothesis 12)

Uses the same overnight, no-heating bins as ``scripts/thermal_momentum.py``.
For each room it fits ``dT/dt = a * diff + b * wind * diff + c`` where ``diff``
is outdoor minus room temperature and ``wind`` is the hourly 10 m speed from
Open-Meteo in m/s. A positive ``b`` means each m/s of wind raises the room's
heat loss: ``a`` is 1/tau in calm air, ``a + b * wind`` in wind. It then fits
all rooms together with one wind term per face (N, E, S, W: wind speed times
the cosine of the angle onto that face) to look for a windward side.

Usage::

    uv run python scripts/wind_loss.py --days 10
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

from custom_components.house_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.house_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.house_thermal_lab.hvac import runs_from_states
from custom_components.house_thermal_lab.hvac_response import merge_runs
from custom_components.house_thermal_lab.solar import solar_elevation_degrees
from custom_components.house_thermal_lab.wind import FACES, fetch_wind

MIN_BINS = 30


def _cell(value: float, se: float) -> str:
    star = "*" if se > 0 and abs(value) > 2 * se else " "
    return f"{value:+.4f}{star}"


def main() -> None:
    """Print per-room and pooled wind fits."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
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

    by_hour = {w.time: w for w in fetch_wind(lat, lon, args.days + 1)}
    mids = [start + (i + 0.5) * width for i in range(bins)]
    held = [by_hour.get(m.replace(minute=0, second=0, microsecond=0)) for m in mids]
    speed = np.array([w.speed if w else np.nan for w in held])
    faces = {
        f: np.array([w.face_component(f) if w else np.nan for w in held]) for f in FACES
    }

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url,
            token,
            [OUTDOOR, *ROOMS.values()],
            start,
            end,
            period="5minute",
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in ZONES
    }
    furnace = _overlap_fraction(
        merge_runs(
            [
                r
                for z in ZONES
                for r in runs_from_states(climate[z], end, {"heating"}, "hvac_action")
            ]
        ),
        start,
        bins,
        width,
    )
    night = np.array([solar_elevation_degrees(m, lat, lon) < -6.0 for m in mids])
    quiet = (furnace == 0) & (np.concatenate([[1.0], furnace[:-1]]) == 0)
    base = night & quiet & ~np.isnan(speed)
    print(
        f"{bins} bins from {start:%Y-%m-%d}; usable night bins {int(base.sum())}; "
        f"wind at those bins: median {np.nanmedian(speed[base]):.1f}, "
        f"max {np.nanmax(speed[base]):.1f} m/s\n"
    )

    print(f"{'room':<16}{'n':>5}{'a (1/h)':>10}{'b per m/s':>11}{'tau calm h':>12}")
    pooled_x, pooled_y = [], []
    for name, entity in ROOMS.items():
        room = _bin_means(stats.get(entity, []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        sel = base & ~np.isnan(y) & ~np.isnan(diff)
        if sel.sum() < MIN_BINS:
            print(f"{name:<16}{int(sel.sum()):>5}  too little data")
            continue
        x = np.column_stack([diff[sel], speed[sel] * diff[sel], np.ones(sel.sum())])
        b, s, _ = _ols(x, y[sel])
        tau = f"{1 / b[0]:.0f}" if b[0] > 0 else "n/a"
        print(
            f"{name:<16}{int(sel.sum()):>5}{_cell(b[0], s[0]):>11}"
            f"{_cell(b[1], s[1]):>12}{tau:>12}"
        )
        cols = [diff[sel]] + [faces[f][sel] * diff[sel] for f in FACES]
        pooled_x.append(np.column_stack(cols))
        pooled_y.append(y[sel] - y[sel].mean())

    if pooled_x:
        x = np.vstack(pooled_x)
        y = np.concatenate(pooled_y)
        b, s, r2 = _ols(x, y)
        print(f"\npooled over {len(pooled_x)} rooms (R2 {r2:.2f}, n={len(y)}):")
        print(f"  calm-air rate a {_cell(b[0], s[0])} /h")
        for i, f in enumerate(FACES, start=1):
            print(f"  wind onto {f} face: {_cell(b[i], s[i])} /h per m/s")
        print("\n* = beyond two standard errors; bins are not independent, so")
        print("  the true standard errors are larger")


if __name__ == "__main__":
    main()
