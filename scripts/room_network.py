"""Room-to-room coupling from idle periods, as a network (hypothesis 10).

The single-room cooling law ``dT/dt = a * (outdoor - room) + c`` lumps all
heat from the rest of the house into ``c``. Here each room also gets one term
per zone, for the pull of that zone's other rooms::

    dT_i/dt = a_i * (outdoor - T_i) + sum_z k_iz * (mean T of zone z - T_i) + c_i

fitted on bins with no heating anywhere (this bin and the one before). Zone
means stand in for physical neighbours (there is no floor plan in the data) and
keep the fit small. ``k_iz`` (per hour) is the coupling from zone ``z`` to room
``i``: positive means room ``i`` moves toward that zone's temperature.

The network is only worth having if it predicts better, so both models are
scored by leave-one-day-out cross-validation (RMSE of the next-bin change).

Important: the "static" (no fan) state of the hypothesis is not in the data. The
four Ecobees' fan minimum on-times keep the blower running with gaps of at most
about 12 minutes (see 08), so these are couplings with the fan on. A true static
measurement needs nights with the fan minimum set to zero.

Usage::

    uv run python scripts/room_network.py --days 11 --bin 15
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
import warnings

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import OUTDOOR, ROOMS, ZONES, _bin_means, _ols, _overlap_fraction
from thermal_momentum import NIGHT_ELEVATION, ZONE_OF_ROOM

from custom_components.home_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.home_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.home_thermal_lab.hvac import runs_from_states
from custom_components.home_thermal_lab.hvac_response import merge_runs
from custom_components.home_thermal_lab.solar import solar_elevation_degrees

MIN_BINS = 60


def _cv(x: np.ndarray, y: np.ndarray, day: np.ndarray) -> float:
    """Leave-one-day-out RMSE."""
    errs = []
    for d in np.unique(day):
        train, test = day != d, day == d
        if train.sum() <= x.shape[1] + 5 or not test.any():
            continue
        beta, *_ = np.linalg.lstsq(x[train], y[train], rcond=None)
        errs.append(y[test] - x[test] @ beta)
    if not errs:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(np.concatenate(errs)))))


def main() -> None:
    """Print the coupling table."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=11)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--all-day", action="store_true", help="include daytime bins")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, [OUTDOOR, *ROOMS.values()], start, end, "5minute"
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    temps = {
        n: _bin_means(stats.get(e, []), start, bins, width) for n, e in ROOMS.items()
    }

    runs, known_from = [], start
    for z in ZONES:
        states = fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        if states:
            first = datetime.fromisoformat(states[0]["last_updated"]).astimezone(UTC)
            known_from = max(known_from, first)
        runs += runs_from_states(states, end, {"heating"}, "hvac_action")
    heat = _overlap_fraction(merge_runs(runs, 0.0), start, bins, width)
    mids = [start + (i + 0.5) * width for i in range(bins)]
    elevation = np.array([solar_elevation_degrees(m, lat, lon) for m in mids])
    sun = np.where(elevation > 0, np.sin(np.radians(np.clip(elevation, 0, 90))), 0.0)
    known = np.array([start + i * width >= known_from for i in range(bins)])
    idle = known & (heat == 0) & (np.concatenate([[1.0], heat[:-1]]) == 0)
    if not args.all_day:
        idle &= elevation < NIGHT_ELEVATION
    day = np.array([int(i * hours // 24) for i in range(bins)])

    print(
        f"{int(idle.sum())} idle {'' if args.all_day else 'night '}bins of "
        f"{args.bin} min from {known_from:%Y-%m-%d %H:%M}; k in per hour "
        "(* beyond 2 s.e.)\n"
    )
    print(
        f"{'room':<15}{'n':>5}{'CV single':>10}{'CV network':>11}{'a out':>8}"
        + "".join(f"{'k ' + z:>9}" for z in ZONES)
    )
    for name, room in temps.items():
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        cols = [t_out - room, np.ones(bins)]
        if args.all_day:
            cols.append(sun)
        n_single = len(cols)
        for z in ZONES:
            mates = [temps[m] for m in temps if ZONE_OF_ROOM.get(m) == z and m != name]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                # a room alone in its zone gets a zero column (no estimate)
                zmean = np.nanmean(np.stack(mates), axis=0) if mates else room
            cols.append(zmean - room)
        x = np.column_stack(cols)
        ok = idle & ~np.isnan(y) & ~np.isnan(x).any(axis=1)
        if ok.sum() < MIN_BINS:
            print(f"{name:<15}  too little data")
            continue
        cv1 = _cv(x[ok][:, :n_single], y[ok], day[ok])
        cv2 = _cv(x[ok], y[ok], day[ok])
        beta, se, _ = _ols(x[ok], y[ok])

        def cell(j: int, beta=beta, se=se) -> str:
            star = "*" if se[j] > 0 and abs(beta[j]) > 2 * se[j] else " "
            return f"{beta[j]:+8.2f}{star}"

        print(
            f"{name:<15}{int(ok.sum()):>5}{cv1:>10.3f}{cv2:>11.3f}{cell(0)[1:]}"
            + "".join(cell(n_single + j) for j in range(len(ZONES)))
        )
    print(
        "\nCV: leave-one-day-out RMSE of the next-bin rate (C/h); lower is better. "
        "Fan on in\nalmost every bin, so these are not the no-fan ('static') "
        "couplings of the hypothesis."
    )


if __name__ == "__main__":
    main()
