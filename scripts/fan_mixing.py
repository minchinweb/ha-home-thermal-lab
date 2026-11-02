"""Does the furnace blower, on its own, even out the house? (hypothesis 08)

The zone board runs the blower for every zone whenever any thermostat asks for
the fan, but ignores fan-only requests while any zone calls for heat (or cool).
So the clean comparison is between two whole-house states, with no heating in
the bin or the one before:

* **fan only**: the blower on for the whole bin (some thermostat's
  ``equipment_running`` includes ``fan``) and no zone heating;
* **still**: the blower off for the whole bin.

The cold-air returns in nearly every room are always open, so with the blower on
air is pulled from every room and pushed back through the supply registers. If
that mixes the house, every room's gap to the rest of the house should close
faster with the fan on. For each room ``gap = room - mean of the other rooms``
and, separately in each state, ``d(gap)/dt = -k * gap + c`` is fitted. ``k`` (per
hour) is the mixing rate: about 0 means the gap does not close, and ``1 / k`` is
the time to close by about 63%. The expectation is ``k_fan > k_still`` for every
room, most for the basement (warmed by the rest of the house) and the master
bedroom (cooled toward it in summer).

A second view groups rooms by floor and follows the basement-minus-upstairs gap
across fan switch-ons that follow at least ``--settle`` minutes of still air.

The master bedroom's register fan (``fan.master_bedroom_ad3958``) runs on its
own; its share is reported for the master bedroom rows but not separated.

Usage::

    uv run python scripts/fan_mixing.py --days 14 --bin 15
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
from furnace_stages import stage_runs
from regress_rooms import ROOMS, ZONES, _bin_means, _ols, _overlap_fraction
from thermal_momentum import NIGHT_ELEVATION

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

REGISTER_FAN = "fan.master_bedroom_ad3958"
SAME_ROOM = ("Office sensor", "Office AQ")
BASEMENT = ["Z2 basement", "NE basement", "SE basement", "S basement"]
UPSTAIRS = ["Z3 master", "N bedroom", "Upstairs bath"]
MIN_BINS = 20


def _fit_k(gap: np.ndarray, rate: np.ndarray, sel: np.ndarray):
    """Mixing rate k (per hour) and its standard error, or None."""
    ok = sel & ~np.isnan(gap) & ~np.isnan(rate)
    if ok.sum() < MIN_BINS:
        return None
    beta, se, _ = _ols(np.column_stack([gap[ok], np.ones(ok.sum())]), rate[ok])
    return -beta[0], se[0], int(ok.sum())


def _cell(fit) -> str:
    if fit is None:
        return f"{'-':>16}"
    k, se, n = fit
    star = "*" if se > 0 and abs(k) > 2 * se else " "
    return f"{k:+7.3f}{star}({n:>4})  "


def main() -> None:
    """Print the mixing rates and the switch-on study."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--settle", type=int, default=60, help="minutes of still air")
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
            args.ha_url, token, list(ROOMS.values()), start, end, period="5minute"
        )
    )
    rooms = {
        n: _bin_means(stats.get(e, []), start, bins, width) for n, e in ROOMS.items()
    }
    pair = np.stack([rooms.pop(n) for n in SAME_ROOM])
    count = (~np.isnan(pair)).sum(axis=0)
    rooms["Office"] = np.where(
        count > 0, np.nansum(pair, axis=0) / np.maximum(count, 1), np.nan
    )

    heat_runs, blower_runs = [], []
    known_from = start
    for z in ZONES:
        states = fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        if states:
            first = datetime.fromisoformat(states[0]["last_updated"]).astimezone(UTC)
            known_from = max(known_from, first)
        heat_runs += runs_from_states(
            states, end, {"heating", "cooling"}, "hvac_action"
        )
        blower_runs += stage_runs(states, end, "fan")
    heat = _overlap_fraction(merge_runs(heat_runs, 0.0), start, bins, width)
    blower = _overlap_fraction(merge_runs(blower_runs, 0.0), start, bins, width)
    register = _overlap_fraction(
        runs_from_states(
            fetch_states(args.ha_url, token, REGISTER_FAN, start, end), end, {"on"}
        ),
        start,
        bins,
        width,
    )
    elevation = np.array(
        [
            solar_elevation_degrees(start + (i + 0.5) * width, lat, lon)
            for i in range(bins)
        ]
    )
    night = elevation < NIGHT_ELEVATION

    known = np.array([start + i * width >= known_from for i in range(bins)])
    no_heat = known & (heat == 0) & (np.concatenate([[1.0], heat[:-1]]) == 0)
    fan_only = no_heat & (blower >= 0.999)
    still = no_heat & (blower <= 0.001)
    print(
        f"{known.sum()} bins of {args.bin} min from {known_from:%Y-%m-%d %H:%M} "
        f"(start of thermostat history): heating or cooling "
        f"{(heat[known] > 0).mean():.0%}, fan only {fan_only[known].mean():.0%}, "
        f"still {still[known].mean():.0%}; register fan on "
        f"{register[known].mean():.0%}"
    )
    shares = [(0, 0.001), (0.001, 0.5), (0.5, 0.999), (0.999, 2.0)]
    print(
        "blower share in no-heat bins: "
        + ", ".join(
            f"{lo:.0%}-{min(hi, 1):.0%}: "
            f"{((blower >= lo) & (blower < hi) & no_heat).sum()}"
            for lo, hi in shares
        )
        + "\n"
    )

    names = list(rooms)
    temps = np.stack([rooms[n] for n in names])
    print(
        "1. Mixing rate k (per hour) of each room's gap to the rest of the house"
        " (* beyond 2 s.e.; bins)"
    )
    head = f"{'fan only':>16}{'still':>16}"
    print(f"{'room':<15}{'mean gap C':>11}{head}   night:{head}")
    for idx, name in enumerate(names):
        others = np.delete(temps, idx, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            gap = temps[idx] - np.nanmean(others, axis=0)
        rate = np.full(bins, np.nan)
        rate[:-1] = (gap[1:] - gap[:-1]) / hours
        both = np.concatenate([fan_only[1:], [False]])
        calm = np.concatenate([still[1:], [False]])
        row = (
            f"{name:<15}{np.nanmean(gap):>+11.2f}"
            f"{_cell(_fit_k(gap, rate, fan_only & both))}"
            f"{_cell(_fit_k(gap, rate, still & calm))}       "
            f"{_cell(_fit_k(gap, rate, fan_only & both & night))}"
            f"{_cell(_fit_k(gap, rate, still & calm & night))}"
        )
        print(row)

    def floor(group: list[str]) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(np.stack([rooms[n] for n in group]), axis=0)

    split = floor(BASEMENT) - floor(UPSTAIRS)
    print(
        "\n2. Basement minus upstairs (master, N bedroom, bath) around fan switch-ons "
        f"after {args.settle}+ min still"
    )
    settle = max(int(args.settle / args.bin), 1)
    look = max(int(60 / args.bin), 1)
    rows = []
    for i in range(settle, bins - look):
        if not fan_only[i] or fan_only[i - 1] or not still[i - settle : i].all():
            continue
        if not fan_only[i : i + look].all():
            continue
        before = split[i - 1] - split[i - 1 - min(look, settle - 1)]
        after = split[i + look - 1] - split[i - 1]
        if math.isnan(before) or math.isnan(after):
            continue
        rows.append((start + i * width, split[i - 1], before, after))
    if not rows:
        print("  none: the blower is rarely off long enough before it starts")
    for when, gap0, before, after in rows:
        print(
            f"  {when:%m-%d %H:%M} gap {gap0:+.2f} C; change in the hour before "
            f"{before:+.2f}, after switch-on {after:+.2f}"
        )
    if rows:
        b = np.array([r[2] for r in rows])
        a = np.array([r[3] for r in rows])
        print(
            f"  median: before {np.median(b):+.2f}, after {np.median(a):+.2f} "
            f"({len(rows)} switch-ons)"
        )


if __name__ == "__main__":
    main()
