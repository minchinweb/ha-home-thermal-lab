"""Whole-house power by appliance, then the stove against room temperatures.

Stage 1 regresses whole-house power on the washer's plug power, whether the dryer
is running or cooling down, and whether the furnace is running. Stage 2 takes
what is left over (after removing a rolling baseline) as a proxy for stove and
oven use, and lists the bursts. Stage 3 regresses each room's rate of
temperature change on that proxy, now and one bin earlier, alongside the usual
drivers, to see which rooms the stove warms and by how much (hypotheses 11
and 14).

There is no stove or oven sensor, so the proxy also holds anything else
unmetered (printers, the dishwasher, the dryer's heat if its status is wrong).
All rates are degrees C per hour; ``*`` marks coefficients beyond two standard
errors.

Usage::

    uv run python scripts/regress_power.py --days 10 --bin 15
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import math
import os
from pathlib import Path
import statistics
import sys
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import (
    OUTDOOR,
    POWER,
    ROOMS,
    ZONES,
    _bin_means,
    _cell,
    _ols,
    _overlap_fraction,
)

from custom_components.house_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
    fetch_time_zone,
)
from custom_components.house_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.house_thermal_lab.hvac import runs_from_states
from custom_components.house_thermal_lab.hvac_response import merge_runs
from custom_components.house_thermal_lab.solar import solar_elevation_degrees

WASHER_POWER = "sensor.washing_machine_plug_power"  # watts
DRYER_STATUS = "sensor.dryer_current_status"
BIG_KW = 1.0
MIN_BINS = 2


def _rolling_median(values: np.ndarray, half: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        window = values[max(0, i - half) : i + half + 1]
        window = window[~np.isnan(window)]
        if len(window):
            out[i] = np.median(window)
    return out


def main() -> None:
    """Run the three stages and print them."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    entities = [OUTDOOR, POWER, WASHER_POWER, *ROOMS.values()]
    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, entities, start, end, period="5minute"
        )
    )
    house = _bin_means(stats.get(POWER, []), start, bins, width)
    washer = _bin_means(stats.get(WASHER_POWER, []), start, bins, width) / 1000.0
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)

    dryer_states = fetch_states(args.ha_url, token, DRYER_STATUS, start, end)
    dryer_run = _overlap_fraction(
        runs_from_states(dryer_states, end, {"running"}), start, bins, width
    )
    dryer_cool = _overlap_fraction(
        runs_from_states(dryer_states, end, {"cooling"}), start, bins, width
    )
    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in ZONES
    }
    heat = {
        z: _overlap_fraction(
            runs_from_states(climate[z], end, {"heating"}, "hvac_action"),
            start,
            bins,
            width,
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

    # Stage 1: whole-house power by appliance
    x1 = np.column_stack([np.ones(bins), washer, dryer_run, dryer_cool, furnace])
    ok = ~np.isnan(x1).any(axis=1) & ~np.isnan(house)
    beta, se, r2 = _ols(x1[ok], house[ok])
    print(
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; dryer running "
        f"{dryer_run.mean():.1%} of the time, cooling {dryer_cool.mean():.1%}\n"
    )
    print("Stage 1: whole-house kW =")
    for name, b, s in zip(
        [
            "base load",
            "washer plug (kW per kW)",
            "dryer running",
            "dryer cooling",
            "furnace running",
        ],
        beta,
        se,
        strict=True,
    ):
        print(f"  {name:<26}{_cell(b, s)} kW")
    print(f"  R2 = {r2:.2f}, n = {int(ok.sum())}\n")

    # Stage 2: what is left over
    fitted = x1 @ beta
    resid = house - fitted
    baseline = _rolling_median(resid, half=int(3 * 60 / args.bin))
    other = np.clip(resid - baseline, 0.0, None)
    big = other >= BIG_KW
    print(
        f"Stage 2: unexplained bursts >= {BIG_KW:.1f} kW above baseline (stove proxy)"
    )
    i = 0
    events = []
    while i < bins:
        if big[i]:
            j = i
            while j + 1 < bins and big[j + 1]:
                j += 1
            if j - i + 1 >= MIN_BINS:
                events.append((i, j))
            i = j + 1
        else:
            i += 1
    for a, b in events[:20]:
        when = (start + a * width).astimezone(tz)
        print(
            f"  {when:%a %m-%d %H:%M}  {(b - a + 1) * args.bin:4d} min  "
            f"mean +{other[a : b + 1].mean():.1f} kW"
        )
    hist = {}
    for a, _ in events:
        h = (start + a * width).astimezone(tz).hour
        hist[h] = hist.get(h, 0) + 1
    print(
        f"  {len(events)} bursts; start hours (local): {dict(sorted(hist.items()))}\n"
    )

    # Stage 3: each room against the stove proxy
    mids = [start + (k + 0.5) * width for k in range(bins)]
    sun = np.array(
        [
            max(math.sin(math.radians(solar_elevation_degrees(m, lat, lon))), 0.0)
            for m in mids
        ]
    )
    other_lag = np.concatenate([[0.0], other[:-1]])
    terms = [
        "k_out",
        "h_z2",
        "h_z4",
        "sun",
        "dryer",
        "washer",
        "stove",
        "stove-1",
        "const",
    ]
    print("Stage 3: room dT/dt (C/h) against the stove proxy (kW above baseline)")
    print(f"{'room':<16}{'n':>5}{'R2':>6}  " + "".join(f"{t:>9}" for t in terms))
    for name, entity in ROOMS.items():
        room = _bin_means(stats.get(entity, []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        x = np.column_stack(
            [
                t_out - room,
                heat["z2"],
                heat["z4"],
                sun,
                dryer_run,
                washer,
                other,
                other_lag,
                np.ones(bins),
            ]
        )
        ok = ~np.isnan(x).any(axis=1) & ~np.isnan(y)
        if ok.sum() < 3 * len(terms):
            print(f"{name:<16}{int(ok.sum()):>5}  too little data")
            continue
        b, s, r2 = _ols(x[ok], y[ok])
        print(
            f"{name:<16}{int(ok.sum()):>5}{r2:>6.2f}  "
            + "".join(f"{_cell(v, e):>9}" for v, e in zip(b, s, strict=True))
        )
    print("\nunits: C per hour per unit of each term; * = beyond 2 standard errors")
    print(
        f"median proxy while a burst is on: {statistics.median(other[big]):.1f} kW"
        if big.any()
        else "no bursts found"
    )


if __name__ == "__main__":
    main()
