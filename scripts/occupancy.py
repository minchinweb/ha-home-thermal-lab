"""Can occupancy be read from room temperature changes? (hypothesis 15)

Ground truth: the four zone occupancy sensors in Home Assistant, the office
motion sensor, the office CO2 sensor and the two phone ``person`` entities.
In quiet night bins (sun down, no zone heating), each room's rate of change is
fit as ``dT/dt = a * (outdoor - room) + c + b * occupied`` where ``occupied`` is
the fraction of the bin its zone sensor reported presence. ``b`` is the extra
warming (C/h) when the zone is occupied. It then reports how well the cooling
residual alone separates occupied from empty bins (AUC), and how well office CO2
does.

Usage::

    uv run python scripts/occupancy.py --days 14
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

from door_state import auc
from envfile import load_env
from regress_rooms import (
    OUTDOOR,
    ROOMS,
    ZONES,
    _bin_means,
    _ols,
    _overlap_fraction,
)
from thermal_momentum import NIGHT_ELEVATION, ZONE_OF_ROOM

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

ZONE_OCCUPANCY = {
    "z1": "binary_sensor.kitchen_occupancy",
    "z2": "binary_sensor.z2_occupancy",
    "z3": "binary_sensor.master_bedroom_occupancy",
    "z4": "binary_sensor.office_occupancy",
}
MOTION = "binary_sensor.multisensor_6_motion_detection"
CO2 = "sensor.z4_office_carbon_dioxide"
PEOPLE = ["person.adult_1", "person.adult_2"]
MIN_BINS = 30
MIN_PER_CLASS = 10


def _fraction(entity, args, token, start, end, bins, width, states="on"):
    states_list = fetch_states(args.ha_url, token, entity, start, end)
    if not states_list:
        return np.full(bins, np.nan)
    return _overlap_fraction(
        runs_from_states(states_list, end, {states}), start, bins, width
    )


def _cell(value: float, se: float) -> str:
    star = "*" if se > 0 and abs(value) > 2 * se else " "
    return f"{value:+.3f}{star}"


def main() -> None:
    """Print the occupancy summary."""
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

    occ = {
        z: _fraction(e, args, token, start, end, bins, width)
        for z, e in ZONE_OCCUPANCY.items()
    }
    motion = _fraction(MOTION, args, token, start, end, bins, width)
    home = np.sum(
        [_fraction(e, args, token, start, end, bins, width, "home") for e in PEOPLE],
        axis=0,
    )
    print(f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}")
    for z, f in occ.items():
        print(f"  {ZONE_OCCUPANCY[z]:<42} occupied {np.nanmean(f > 0.5):.0%} of bins")
    print(f"  {MOTION:<42} motion in {np.nanmean(motion > 0):.0%} of bins")
    print(f"  phones home (both adults) mean {np.nanmean(home):.1f}\n")

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
    mids = [start + (i + 0.5) * width for i in range(bins)]
    night = np.array(
        [solar_elevation_degrees(m, lat, lon) < NIGHT_ELEVATION for m in mids]
    )
    quiet = night & (furnace == 0) & (np.concatenate([[1.0], furnace[:-1]]) == 0)

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url,
            token,
            [OUTDOOR, CO2, *ROOMS.values()],
            start,
            end,
            period="5minute",
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)

    print(
        f"quiet night bins: {int(quiet.sum())}\n\n"
        f"{'room':<16}{'zone':>5}{'n':>5}{'occ n':>7}{'b C/h':>10}"
        f"{'AUC resid':>11}"
    )
    for name, entity in ROOMS.items():
        z = ZONE_OF_ROOM[name]
        room = _bin_means(stats.get(entity, []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        o = occ[z]
        sel = quiet & ~np.isnan(y) & ~np.isnan(diff) & ~np.isnan(o)
        if sel.sum() < MIN_BINS:
            print(f"{name:<16}{z:>5}{int(sel.sum()):>5}  too little data")
            continue
        x = np.column_stack([diff[sel], np.ones(sel.sum()), o[sel]])
        b, s, _ = _ols(x, y[sel])
        base = _ols(x[:, :2], y[sel])[0]
        resid = y[sel] - x[:, :2] @ base
        opened, empty = resid[o[sel] > 0.5], resid[o[sel] == 0]
        a = (
            auc(opened, empty)
            if len(opened) >= MIN_PER_CLASS and len(empty) >= MIN_PER_CLASS
            else float("nan")
        )
        print(
            f"{name:<16}{z:>5}{int(sel.sum()):>5}{int((o[sel] > 0.5).sum()):>7}"
            f"{_cell(b[2], s[2]):>10}{a:>11.2f}"
        )

    co2 = _bin_means(stats.get(CO2, []), start, bins, width)
    o4 = occ["z4"]
    sel = ~np.isnan(co2) & ~np.isnan(o4)
    d_co2 = np.full(bins, np.nan)
    d_co2[:-1] = (co2[1:] - co2[:-1]) / hours
    print("\noffice CO2 against the office occupancy sensor (all bins):")
    for label, feature in (("CO2 level ppm", co2), ("CO2 rise ppm/h", d_co2)):
        f = feature[sel]
        oc, em = f[(o4[sel] > 0.5) & ~np.isnan(f)], f[(o4[sel] == 0) & ~np.isnan(f)]
        if len(oc) >= MIN_PER_CLASS and len(em) >= MIN_PER_CLASS:
            print(
                f"  {label:<16} occupied {np.median(oc):7.0f} (n={len(oc)})  "
                f"empty {np.median(em):7.0f} (n={len(em)})  "
                f"AUC {auc(oc, em):.2f}"
            )
    print("\n* = beyond two standard errors (bins are not independent)")


if __name__ == "__main__":
    main()
