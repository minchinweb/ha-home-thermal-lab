"""Heat from the plug-metered appliances: kitchen fridge and computers, office
computer, and the office's dimmed lights (hypothesis 14).

The lights have no meter: their power is modelled as 105 W (7 LED bulbs of
about 15 W) times the dimmer level.

For each room, on bins where its own zone is not heating (this bin and the one
before), fits::

    dT/dt = a * (outdoor - room) + c + s * sin(sun elevation) + sum_k p_k * P_k

with ``P_k`` each plug's power in kW. If every watt became heat in the zone,
``p_k`` would be about ``1 / C_zone``, about 0.6 C/h per kW for a 600 sq ft
zone of 1.7 kWh/C (see 13). A plug whose power hardly changes cannot be told
apart from the constant, so its spread is shown too.

A second view is an event study: every sustained step in a plug's power (at
least ``--step`` W, held ``--hold`` minutes either side) compares the room's
rate of change after with before, scaled per kW of step.

Usage::

    uv run python scripts/appliance_heat.py --days 11 --bin 15
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import math
import os
from pathlib import Path
import sys
import warnings

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import OUTDOOR, ROOMS, _bin_means, _ols, _overlap_fraction

from custom_components.home_thermal_lab.contributions import dimmer_kw, held_values
from custom_components.home_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.home_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.home_thermal_lab.hvac import runs_from_states
from custom_components.home_thermal_lab.solar import solar_elevation_degrees

PLUGS = {
    "fridge": "sensor.kitchen_fridge_plug_power",
    "kitchen PCs": "sensor.kitchen_kitchen_computers_plug_power",
    "office PC": "sensor.office_office_computer_plug_power",
}
# room label -> (sensors averaged, zone, plugs tested)
# Lights on a dimmer: entity -> watts at full brightness (7 bulbs of about 15 W)
LIGHTS = {"office lights": ("light.office_main_lights", 105.0)}
TARGETS = {
    "Kitchen (z1)": (["Z1 kitchen"], "z1", ["fridge", "kitchen PCs"]),
    "Office (sensor+AQ)": (
        ["Office sensor", "Office AQ"],
        "z4",
        ["office PC", "office lights"],
    ),
    "Z4 office": (["Z4 office"], "z4", ["office PC", "office lights"]),
}
C_ZONE = 1.7  # kWh/C per 600 sq ft zone (hypothesis 13)


def light_power(url, token, start, end, bins, width) -> dict[str, np.ndarray]:
    """Mean kW per bin of each dimmed light in ``LIGHTS`` (modelled, not metered)."""
    out = {}
    for name, (entity, watts) in LIGHTS.items():
        rows = fetch_states(url, token, entity, start, end, with_attributes=True)
        series = [(t.astimezone(UTC), v) for t, v in dimmer_kw(rows, watts)]
        sub = 5  # samples per bin
        times = [
            start + (i + (k + 0.5) / sub) * width
            for i in range(bins)
            for k in range(sub)
        ]
        held = np.array(
            [np.nan if v is None else v for v in held_values(series, times)]
        )
        out[name] = held.reshape(bins, sub).mean(axis=1)
    return out


def _mean(series: list[np.ndarray]) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.stack(series), axis=0)


def _rate(values: np.ndarray, hours: float) -> np.ndarray:
    out = np.full(len(values), np.nan)
    out[:-1] = (values[1:] - values[:-1]) / hours
    return out


def main() -> None:
    """Print the regression and the step study."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=11)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--step", type=float, default=60.0, help="W")
    p.add_argument("--hold", type=int, default=45, help="minutes")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    entities = [OUTDOOR, *ROOMS.values(), *PLUGS.values()]
    stats = asyncio.run(
        fetch_statistics_from_url(args.ha_url, token, entities, start, end, "5minute")
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    power = {
        k: _bin_means(stats.get(e, []), start, bins, width) / 1000.0
        for k, e in PLUGS.items()
    }
    power |= light_power(args.ha_url, token, start, end, bins, width)
    sun = np.array(
        [
            max(
                math.sin(
                    math.radians(
                        solar_elevation_degrees(start + (i + 0.5) * width, lat, lon)
                    )
                ),
                0.0,
            )
            for i in range(bins)
        ]
    )
    heat = {}
    for zone in ("z1", "z4"):
        states = fetch_states(
            args.ha_url, token, f"climate.{zone}", start, end, with_attributes=True
        )
        h = _overlap_fraction(
            runs_from_states(states, end, {"heating"}, "hvac_action"),
            start,
            bins,
            width,
        )
        heat[zone] = (h == 0) & (np.concatenate([[1.0], h[:-1]]) == 0)

    print(f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}")
    print(
        "plug power, kW: "
        + ", ".join(
            f"{k} mean {np.nanmean(v):.3f} (spread {np.nanstd(v):.3f})"
            for k, v in power.items()
        )
    )
    print(
        f"\n1. Regression (own zone not heating); p in C/h per kW, if all the heat "
        f"stayed in the zone about {1 / C_ZONE:.2f}"
    )
    for label, (sensors, zone, plugs) in TARGETS.items():
        room = _mean(
            [_bin_means(stats.get(ROOMS[s], []), start, bins, width) for s in sensors]
        )
        y = _rate(room, hours)
        cols = [t_out - room, np.ones(bins), sun, *(power[k] for k in plugs)]
        x = np.column_stack(cols)
        ok = heat[zone] & ~np.isnan(y) & ~np.isnan(x).any(axis=1)
        if ok.sum() < 50:
            print(f"  {label}: too little data")
            continue
        beta, se, r2 = _ols(x[ok], y[ok])
        terms = ", ".join(
            f"{k} {beta[3 + j]:+.2f} +- {se[3 + j]:.2f}" for j, k in enumerate(plugs)
        )
        print(f"  {label:<15} n={ok.sum():<5} R2 {r2:.2f}  {terms}")

    print(
        f"\n2. Steps of {args.step:g}+ W held {args.hold} min: room rate after minus "
        "before (C/h), per kW of step"
    )
    n = max(int(args.hold / args.bin), 2)
    for label, (sensors, zone, plugs) in TARGETS.items():
        room = _mean(
            [_bin_means(stats.get(ROOMS[s], []), start, bins, width) for s in sensors]
        )
        for k in plugs:
            pw = power[k]
            found = []
            for i in range(n, bins - n):
                before, after = pw[i - n : i], pw[i : i + n]
                if np.isnan(before).any() or np.isnan(after).any():
                    continue
                step = after.mean() - before.mean()
                if abs(step) * 1000 < args.step:
                    continue
                if (
                    before.std() * 1000 > args.step / 3
                    or after.std() * 1000 > args.step / 3
                ):
                    continue
                if not (heat[zone][i - n : i + n].all()):
                    continue
                r0 = room[i - n : i + 1]
                r1 = room[i : i + n + 1]
                if np.isnan(r0).any() or np.isnan(r1).any():
                    continue
                t = np.arange(n + 1) * hours
                change = np.polyfit(t, r1, 1)[0] - np.polyfit(t, r0, 1)[0]
                found.append((step, change))
                pw = pw.copy()
                pw[i : i + n] = np.nan  # one event per step
            if not found:
                print(f"  {label:<15} {k:<12} no clean steps")
                continue
            per_kw = np.array([c / s for s, c in found])
            ups = sum(1 for s, _ in found if s > 0)
            print(
                f"  {label:<15} {k:<12} {len(found)} steps ({ups} up), median step "
                f"{np.median([abs(s) for s, _ in found]) * 1000:.0f} W: "
                f"{np.median(per_kw):+.2f} C/h per kW"
            )


if __name__ == "__main__":
    main()
