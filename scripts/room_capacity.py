"""Effective heat capacity and window aperture per room (hypotheses 06, 11, 13).

The fits elsewhere give everything in C per hour. With the measured supply
airflow (``scripts/room_geometry.py``) they can be put in watts:

1. All bins, per room::

       dT/dt = a * diff + c + sum_z b_z * call_z + sum_f g_f * light_f

   over every zone ``z``, its own included, and the room's window walls ``f``
   (unshaded light, so the sun does not land in the bleed terms). ``b_z`` is how
   fast the room warms, in C/h, while ``z`` calls. Night bins alone would be
   cleaner, but z2 only calls in the day.
2. The heat that call brings in is ``airflow_z * air heat * supply rise``. The
   supply rise (supply air minus room air, at the register) is not measured, so
   it is ``--supply-rise``. The effective heat capacity is that heat over
   ``b_z``. It includes the air, the drywall, the furniture and whatever open
   rooms next door share the heat, so it is many times the air alone. Zones that
   send less than ``MIN_CFM`` into the room are skipped, and the room's value is
   the median over the rest.
3. Day bins with the room's own zone not calling, as in
   ``scripts/solar_windows.py`` (unshaded light: beam plus half the diffuse light
   on each window wall), plus the bleed terms. A window gain ``g`` in C/h per
   W/m2 times the capacity is watts per W/m2 of sun, which is an effective
   aperture in m2. It is shown next to the glass area estimated from the photos.
   Shading, curtains and glass that passes only part of the sun all make the
   aperture smaller than the glass.

Usage::

    uv run python scripts/room_capacity.py --days 15 --supply-rise 25
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
from regress_rooms import OUTDOOR, ROOMS, ZONES, _bin_means, _ols, _overlap_fraction
from room_geometry import ROOM_GEOMETRY
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
from custom_components.home_thermal_lab.wind import FACES

MIN_CFM = 50.0
MIN_BINS = 40


def main() -> None:
    """Print each room's effective heat capacity and window apertures."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=15)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--rotation", type=float, default=10.4, help="degrees clockwise")
    p.add_argument(
        "--supply-rise", type=float, default=25.0, help="supply air above room, K"
    )
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    mids = [start + (i + 0.5) * width for i in range(bins)]
    elevation = np.array([solar_elevation_degrees(m, lat, lon) for m in mids])
    azimuth = np.array([solar_azimuth_degrees(m, lat, lon) for m in mids])
    by_end = {r.time: r for r in fetch_irradiance(lat, lon, args.days + 1)}
    held = [
        by_end.get(m.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        for m in mids
    ]
    face = {
        f: np.array(
            [
                h.on_face(f, azimuth[i] - args.rotation, elevation[i]) if h else np.nan
                for i, h in enumerate(held)
            ]
        )
        for f in FACES
    }
    known = np.array([h is not None for h in held])
    day = (elevation > 3.0) & known

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
    called = [z for z in ZONES if heat[z].sum() > 0]
    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, [OUTDOOR, *ROOMS.values()], start, end, period="5minute"
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)

    print(
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; zones that called: "
        f"{', '.join(called)}; supply air {args.supply_rise:.0f} K above the room\n"
    )
    print(
        f"{'room':<13}{'air m3':>7}{'air kJ/K':>9}  bleed C/h per call (cfm)"
        f"{'':<16}{'C_eff MJ/K':>11}{'x air':>6}"
    )
    capacity = {}
    for name, geo in ROOM_GEOMETRY.items():
        if name not in ROOMS:
            continue
        room = _bin_means(stats.get(ROOMS[name], []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        walls = WINDOWS.get(name, {}).get("walls", [])
        sel = ~np.isnan(y) & ~np.isnan(diff) & known
        if sel.sum() < MIN_BINS:
            continue
        x = np.column_stack(
            [
                diff[sel],
                np.ones(sel.sum()),
                *(heat[z][sel] for z in called),
                *(np.nan_to_num(face[f])[sel] for f in walls),
            ]
        )
        b, s, _ = _ols(x, y[sel])
        cells, values = [], []
        for i, z in enumerate(called):
            rate, se, cfm = b[2 + i], s[2 + i], geo.airflow_cfm.get(z, 0.0)
            cells.append(f"{z} {rate:+.2f} ({cfm:.0f})")
            if cfm >= MIN_CFM and rate > 2 * se and rate > 0:
                watts = geo.supply_w_per_k(z) * args.supply_rise
                values.append(watts * 3600.0 / rate)
        if values:
            capacity[name] = float(np.median(values))
            tail = f"{capacity[name] / 1e6:>11.1f}{capacity[name] / geo.air_heat:>6.0f}"
        else:
            tail = f"{'-':>11}{'-':>6}"
        print(
            f"{name:<13}{geo.volume_m3:>7.1f}{geo.air_heat / 1000:>9.0f}  "
            f"{', '.join(cells):<40}{tail}"
        )

    print("\nWindow aperture from the daytime gains (unshaded light, bleed terms in):")
    print(
        f"{'room':<13}{'face':>5}{'gain mC/h/Wm2':>15}"
        f"{'aperture m2':>13}{'glass m2':>10}"
    )
    for name, spec in WINDOWS.items():
        geo = ROOM_GEOMETRY.get(name)
        if name not in capacity or not spec["walls"] or geo is None:
            continue
        z = ZONE_OF_ROOM[name]
        room = _bin_means(stats.get(ROOMS[name], []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        own_off = (heat[z] == 0) & (np.concatenate([[1.0], heat[z][:-1]]) == 0)
        sel = day & own_off & ~np.isnan(y) & ~np.isnan(diff)
        if sel.sum() < MIN_BINS:
            continue
        others = [o for o in called if o != z]
        cols = [diff[sel], np.ones(sel.sum()), *(heat[o][sel] for o in others)]
        cols += [face[f][sel] for f in spec["walls"]]
        b, _, _ = _ols(np.column_stack(cols), y[sel])
        for i, f in enumerate(spec["walls"]):
            g = b[2 + len(others) + i]
            aperture = g * capacity[name] / 3600.0
            glass = geo.glass_m2(f)
            shown = "?" if glass is None else f"{glass:.1f}"
            print(f"{name:<13}{f:>5}{g * 1000:>+15.2f}{aperture:>+13.1f}{shown:>10}")
    print(
        "\nC_eff scales with --supply-rise; the bleed and gains do not. Window glass"
        "\nareas are photo estimates. Aperture is negative where the fit cannot tell"
        "\nthe sun from the time of day (see hypothesis 11)."
    )


if __name__ == "__main__":
    main()
