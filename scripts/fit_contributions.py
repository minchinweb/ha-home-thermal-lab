"""Fit the contribution-chart terms per zone and print them as YAML.

The coefficients of ``custom_components/house_thermal_lab/contributions.py``::

    dT/dt = a * (outdoor - T) + c + g * light + h * own_heat
          + x * other_heat + p * plug_kw

on every bin (heating included, unlike the shadow fit), from the zone
thermostat's room sensor. ``other_heat`` is the largest share of the bin that
any other zone was heating; ``plug_kw`` the zone's metered plugs. Light uses the
window and roof layout of ``scripts/solar_windows.py`` with the fixed
south-east horizon. Paste the printed ``terms:`` into the ``contributions:``
entry of the sensor configuration.

Usage::

    uv run python scripts/fit_contributions.py --days 11
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

from appliance_heat import light_power
from envfile import load_env
from predict_day import _room_light
from regress_rooms import OUTDOOR, ROOMS, ZONES, _bin_means, _ols, _overlap_fraction
from solar_windows import WINDOWS

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

ZONE_ROOM = {
    "z1": "Z1 kitchen",
    "z2": "Z2 basement",
    "z3": "Z3 master",
    "z4": "Z4 office",
}
ZONE_PLUGS = {
    "z1": [
        "sensor.kitchen_fridge_plug_power",
        "sensor.kitchen_kitchen_computers_plug_power",
    ],
    "z4": ["sensor.office_office_computer_plug_power"],
}
ZONE_LIGHTS = {"z4": ["office lights"]}  # modelled, see appliance_heat.LIGHTS
NAMES = ["a", "c", "g", "h", "x", "p"]


def main() -> None:
    """Print a ``terms:`` line per zone."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=11)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--rotation", type=float, default=10.4)
    p.add_argument("--pitch", type=float, default=45.0)
    p.add_argument("--horizon", type=float, default=18.0)
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    plugs = sorted({e for es in ZONE_PLUGS.values() for e in es})
    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url,
            token,
            [OUTDOOR, *ROOMS.values(), *plugs],
            start,
            end,
            "5minute",
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    lights = light_power(args.ha_url, token, start, end, bins, width)
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
    by_end = {r.time: r for r in fetch_irradiance(lat, lon, args.days + 2)}
    mids = [start + (i + 0.5) * width for i in range(bins)]
    elevation = np.array([solar_elevation_degrees(m, lat, lon) for m in mids])
    azimuth = np.array([solar_azimuth_degrees(m, lat, lon) for m in mids])
    held = [
        by_end.get(m.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        for m in mids
    ]

    def block(az: float, el: float) -> bool:
        return 120.0 <= az < 210.0 and el < args.horizon

    print(f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; C/h terms\n")
    for z in ZONES:
        name = ZONE_ROOM[z]
        room = _bin_means(stats.get(ROOMS[name], []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        spec = WINDOWS.get(name)
        light = (
            np.nan_to_num(
                _room_light(
                    spec, held, azimuth, elevation, args.rotation, args.pitch, block
                )
            )
            if spec
            else np.zeros(bins)
        )
        other = np.max(np.stack([heat[o] for o in ZONES if o != z]), axis=0)
        kw = np.zeros(bins)
        for e in ZONE_PLUGS.get(z, []):
            kw += np.nan_to_num(_bin_means(stats.get(e, []), start, bins, width)) / 1000
        for lamp in ZONE_LIGHTS.get(z, []):
            kw += np.nan_to_num(lights[lamp])
        cols = [t_out - room, np.ones(bins), light, heat[z], other, kw]
        keep = [True, True, spec is not None, heat[z].any(), True, z in ZONE_PLUGS]
        x = np.column_stack([c for c, k in zip(cols, keep, strict=True) if k])
        names = [n for n, k in zip(NAMES, keep, strict=True) if k]
        ok = ~np.isnan(y) & ~np.isnan(x).any(axis=1)
        beta, se, r2 = _ols(x[ok], y[ok])
        terms = ", ".join(f"{n}: {b:.4g}" for n, b in zip(names, beta, strict=True))
        errs = ", ".join(f"{n} +-{s:.2g}" for n, s in zip(names, se, strict=True))
        print(f"{z} ({name}, n={int(ok.sum())}, R2 {r2:.2f})")
        print(f"  terms: {{{terms}}}")
        print(f"  standard errors: {errs}\n")
    print(
        "a < 0 is not physical (the room warming as it gets colder outside); treat "
        "such a\nzone's chart as unreliable. z1 and z3 never call for heat, so h is "
        "left out there."
    )


if __name__ == "__main__":
    main()
