"""Can occupancy be read from room temperature changes? (hypothesis 15)

Ground truth: Home Assistant occupancy sensors for the kitchen (z1), basement
(z2) and office (z4). The master bedroom one is left out (it reads occupied
whenever the register fan spins) and so are the rooms of z3. For the office, the
Z4 occupancy sensor is the one used: the Williams Office motion sensor fires
only inside its occupied periods, and the occupancy sensor tracks the office CO2
better.

Three views, each per room, using only bins where the room's own zone is not
calling for heat:

* quiet night: ``dT/dt = a * (outdoor - room) + c + b * occupied`` (sun down, no
  zone heating anywhere);
* all day: the same with a sun term ``sin(elevation)`` when the sun is up;
* events: mean rate of change in the two bins after an occupancy onset minus the
  two bins before it, and the reverse for departures (both should be positive
  if people warm the room).

It also gives the AUC of the cooling residual as a detector and of office CO2.

Usage::

    uv run python scripts/occupancy.py --days 14
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import math
import os
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from appliance_heat import light_power
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
    "z4": "binary_sensor.office_occupancy",
}
CO2 = "sensor.office_office_air_quality_co2"
MIN_BINS = 30
MIN_PER_CLASS = 10
EDGE = 2  # bins either side of an onset or departure
HOLD = 4  # bins an occupied or empty spell must last to count as an event


PLUGS = {
    "fridge": "sensor.kitchen_fridge_plug_power",
    "kitchen PCs": "sensor.kitchen_kitchen_computers_plug_power",
    "office PC": "sensor.office_office_computer_plug_power",
}
ZONE_PLUGS = {"z1": ["fridge", "kitchen PCs"], "z4": ["office PC", "office lights"]}


def _fraction(entity, args, token, start, end, bins, width):
    states = fetch_states(args.ha_url, token, entity, start, end)
    if not states:
        return np.full(bins, np.nan)
    return _overlap_fraction(runs_from_states(states, end, {"on"}), start, bins, width)


def _cell(value: float, se: float) -> str:
    star = "*" if se > 0 and abs(value) > 2 * se else " "
    return f"{value:+.3f}{star}"


def _events(occupied: np.ndarray, ok: np.ndarray, y: np.ndarray) -> list[float]:
    """Rate after minus before an onset, and before minus after a departure."""
    out = []
    bins = len(occupied)
    for i in range(EDGE + 1, bins - HOLD):
        before_empty = not occupied[i - EDGE : i].any()
        after_full = occupied[i : i + HOLD].all()
        before_full = occupied[i - EDGE : i].all()
        after_empty = not occupied[i : i + HOLD].any()
        window = slice(i - EDGE, i + EDGE)
        if not ok[window].all():
            continue
        before, after = y[i - EDGE : i].mean(), y[i : i + EDGE].mean()
        if before_empty and after_full:
            out.append(after - before)
        elif before_full and after_empty:
            out.append(before - after)
    return out


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
    print(f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}")
    for z, f in occ.items():
        print(f"  {ZONE_OCCUPANCY[z]:<42} occupied {np.nanmean(f > 0.5):.0%} of bins")

    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in ZONES
    }
    runs = {
        z: runs_from_states(climate[z], end, {"heating"}, "hvac_action") for z in ZONES
    }
    heat = {z: _overlap_fraction(runs[z], start, bins, width) for z in ZONES}
    furnace = _overlap_fraction(
        merge_runs([r for rs in runs.values() for r in rs]), start, bins, width
    )
    mids = [start + (i + 0.5) * width for i in range(bins)]
    elevation = np.array([solar_elevation_degrees(m, lat, lon) for m in mids])
    night = elevation < NIGHT_ELEVATION
    sun = np.where(elevation > 0, np.sin(np.radians(np.clip(elevation, 0, 90))), 0.0)
    quiet = night & (furnace == 0) & (np.concatenate([[1.0], furnace[:-1]]) == 0)

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url,
            token,
            [OUTDOOR, CO2, *ROOMS.values(), *PLUGS.values()],
            start,
            end,
            period="5minute",
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    plug = {
        k: _bin_means(stats.get(e, []), start, bins, width) / 1000.0
        for k, e in PLUGS.items()
    }
    plug |= light_power(args.ha_url, token, start, end, bins, width)

    print(
        f"\nquiet night bins: {int(quiet.sum())}\n\n"
        f"{'room':<16}{'zone':>5}{'night n':>8}{'b night':>10}{'AUC':>6}"
        f"{'day n':>7}{'b all day':>11}{'events':>8}{'event C/h':>11}"
        f"{'b + plug':>10}{'plug C/h/kW':>13}"
    )
    for name, entity in ROOMS.items():
        if name == "Office AQ":
            continue  # same room as Office sensor; averaged into that row
        z = ZONE_OF_ROOM[name]
        if z not in occ:
            print(f"{name:<16}{z:>5}  no usable occupancy sensor")
            continue
        room = _bin_means(stats.get(entity, []), start, bins, width)
        if name == "Office sensor":
            other = _bin_means(stats.get(ROOMS["Office AQ"], []), start, bins, width)
            both = np.vstack([room, other])
            count = (~np.isnan(both)).sum(axis=0)
            room = np.where(
                count > 0, np.nansum(both, axis=0) / np.maximum(count, 1), np.nan
            )
            name = "Office (W+AQ)"
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        o = occ[z]
        good = ~np.isnan(y) & ~np.isnan(diff) & ~np.isnan(o)
        own_off = (heat[z] == 0) & (np.concatenate([[1.0], heat[z][:-1]]) == 0)
        row = f"{name:<16}{z:>5}"

        sel = quiet & good
        if sel.sum() >= MIN_BINS:
            x = np.column_stack([diff[sel], np.ones(sel.sum()), o[sel]])
            b, s, _ = _ols(x, y[sel])
            base = _ols(x[:, :2], y[sel])[0]
            resid = y[sel] - x[:, :2] @ base
            full, empty = resid[o[sel] > 0.5], resid[o[sel] == 0]
            a = (
                auc(full, empty)
                if len(full) >= MIN_PER_CLASS and len(empty) >= MIN_PER_CLASS
                else float("nan")
            )
            row += f"{int(sel.sum()):>8}{_cell(b[2], s[2]):>10}{a:>6.2f}"
        else:
            row += f"{'-':>8}{'-':>10}{'-':>6}"

        sel = own_off & good
        if sel.sum() >= MIN_BINS:
            x = np.column_stack([diff[sel], np.ones(sel.sum()), sun[sel], o[sel]])
            b, s, _ = _ols(x, y[sel])
            row += f"{int(sel.sum()):>7}{_cell(b[3], s[3]):>11}"
        else:
            row += f"{'-':>7}{'-':>11}"

        ev = _events(o > 0.5, own_off & good, y)
        if len(ev) >= 3:
            mean, se = np.mean(ev), np.std(ev, ddof=1) / math.sqrt(len(ev))
            row += f"{len(ev):>8}{_cell(mean, se):>11}"
        else:
            row += f"{len(ev):>8}{'-':>11}"

        # all day again, with the zone's metered plugs as their own terms
        names = ZONE_PLUGS.get(z, [])
        cols = [diff, np.ones(bins), sun, o, *(plug[k] for k in names)]
        x_all = np.column_stack(cols)
        sel = own_off & good & ~np.isnan(x_all).any(axis=1)
        if names and sel.sum() >= MIN_BINS:
            b, s, _ = _ols(x_all[sel], y[sel])
            row += f"{_cell(b[3], s[3]):>10}" + "".join(
                f" {k} {_cell(b[4 + j], s[4 + j])}" for j, k in enumerate(names)
            )
        print(row)

    co2 = _bin_means(stats.get(CO2, []), start, bins, width)
    o4 = occ["z4"]
    d_co2 = np.full(bins, np.nan)
    d_co2[:-1] = (co2[1:] - co2[:-1]) / hours
    print(f"\n{CO2} against the office occupancy sensor (all bins):")
    for label, feature in (("CO2 level ppm", co2), ("CO2 rise ppm/h", d_co2)):
        full = feature[(o4 > 0.5) & ~np.isnan(feature)]
        empty = feature[(o4 == 0) & ~np.isnan(feature)]
        if len(full) >= MIN_PER_CLASS and len(empty) >= MIN_PER_CLASS:
            print(
                f"  {label:<16} occupied {np.median(full):7.0f} (n={len(full)})  "
                f"empty {np.median(empty):7.0f} (n={len(empty)})  "
                f"AUC {auc(full, empty):.2f}"
            )
    print("\n* = beyond two standard errors (bins are not independent)")


if __name__ == "__main__":
    main()
