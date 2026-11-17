"""Does the furnace blower, on its own, even out the house? (hypothesis 08)

The zone board runs the blower whenever any thermostat asks for the fan, but
ignores fan-only requests while any zone calls for heat (or cool). Only the
zones calling for the fan get supply air; the cold-air returns, in nearly every
room, are not zoned and draw from every floor whenever the blower runs. So for
each room there are three states, with no heating in the bin or the one before:

* **supplied**: the blower on for the whole bin and the room's own zone calling
  for the fan for the whole bin (its supply registers blowing);
* **returns only**: the blower on for the whole bin (another zone's fan call)
  and the room's zone not calling at all (only the returns draw on the room);
* **still**: the blower off for the whole bin.

For each room ``gap = room - mean of the other rooms`` and, separately in each
state, ``d(gap)/dt = -k * gap + c`` is fitted. ``k`` (per hour) is the mixing
rate: about 0 means the gap does not close, and ``1 / k`` is the time to close
by about 63%. If the supply air mixes a room into the house, ``k_supplied`` is
the largest. Caution: ``k`` includes everything that closes the gap (walls,
doors, air leaks), and a still bin that follows a heat call measures the house
settling after it.

A second view groups rooms by floor and follows the basement-minus-upstairs gap
across fan switch-ons that follow at least ``--settle`` minutes of still air.

A third compares no-fan nights with fan nights, 23:00 to 05:00 local: how far
each floor cooled, and that drop per hour per kelvin of indoor-outdoor gap (so
nights of different weather compare), with each zone's fan share on the fan
nights.

Fan-off periods only exist on the no-fan nights of
``homeassistant/no_fan_nights.yaml`` (every thermostat's fan minimum on-time set
to 0), which the script finds from the thermostats' ``fan_min_on_time``.

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
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env, real_entity
from furnace_stages import stage_runs
from regress_rooms import ROOMS, ZONES, _bin_means, _ols, _overlap_fraction
from thermal_momentum import NIGHT_ELEVATION, ZONE_OF_ROOM

from custom_components.home_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
    fetch_time_zone,
)
from custom_components.home_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.home_thermal_lab.hvac import runs_from_states
from custom_components.home_thermal_lab.hvac_response import merge_runs
from custom_components.home_thermal_lab.solar import solar_elevation_degrees

REGISTER_FAN = "fan.master_bedroom_ad3958"
SAME_ROOM = ("Office sensor", "Office AQ")
BASEMENT = ["Z2 basement", "NE basement", "SE basement", "S basement"]
UPSTAIRS = ["Z3 master", "N bedroom", "Upstairs bath"]
# The Z2 thermostat (in the Theater) reads higher when the blower stops, so the
# basement bedrooms are a floor of their own in the night comparison (see 08).
FLOORS = {
    "basement bedrooms": ["NE basement", "SE basement", "S basement"],
    "Z2 thermostat": ["Z2 basement"],
    "main floor": ["Z1 kitchen", "Z4 office", "W bedroom", "Office"],
    "upstairs": UPSTAIRS,
}
OUTDOOR = "sensor.edmonton_temperature"
NIGHT_HOURS = (23, 6)  # 23:00 to 05:00 local
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
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    outdoor_entity = real_entity(OUTDOOR)
    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url,
            token,
            [*ROOMS.values(), outdoor_entity],
            start,
            end,
            period="5minute",
        )
    )
    outdoor = _bin_means(stats.get(outdoor_entity, []), start, bins, width)
    rooms = {
        n: _bin_means(stats.get(e, []), start, bins, width) for n, e in ROOMS.items()
    }
    pair = np.stack([rooms.pop(n) for n in SAME_ROOM])
    count = (~np.isnan(pair)).sum(axis=0)
    rooms["Office"] = np.where(
        count > 0, np.nansum(pair, axis=0) / np.maximum(count, 1), np.nan
    )

    heat_runs, blower_runs, zero_min, zone_fan = [], [], [], {}
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
        fan_runs = stage_runs(states, end, "fan")
        blower_runs += fan_runs
        zone_fan[z] = _overlap_fraction(merge_runs(fan_runs, 0.0), start, bins, width)
        zero_min.append(
            _overlap_fraction(
                runs_from_states(states, end, {0}, "fan_min_on_time"),
                start,
                bins,
                width,
            )
        )
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
    # no-fan nights (homeassistant/no_fan_nights.yaml): every fan minimum is 0
    experiment = known & (np.min(np.stack(zero_min), axis=0) >= 0.999)
    fan_only = no_heat & (blower >= 0.999)
    still = no_heat & (blower <= 0.001)
    print(
        f"{known.sum()} bins of {args.bin} min from {known_from:%Y-%m-%d %H:%M} "
        f"(start of thermostat history): heating or cooling "
        f"{(heat[known] > 0).mean():.0%}, fan only {fan_only[known].mean():.0%}, "
        f"still {still[known].mean():.0%}; register fan on "
        f"{register[known].mean():.0%}"
    )
    print(
        f"no-fan night bins (all fan minimums 0): {int(experiment.sum())}, of them "
        f"still {int((still & experiment).sum())}, fan only "
        f"{int((fan_only & experiment).sum())}"
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
    head = f"{'supplied':>16}{'returns only':>16}{'still':>16}"
    print(f"{'room':<15}{'zone':>5}{'mean gap C':>11}{head}   night:{head}")
    for idx, name in enumerate(names):
        zone = ZONE_OF_ROOM.get(name, "z4")  # "Office" is the two office sensors
        others = np.delete(temps, idx, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            gap = temps[idx] - np.nanmean(others, axis=0)
        rate = np.full(bins, np.nan)
        rate[:-1] = (gap[1:] - gap[:-1]) / hours
        # the state must hold over the bin and the next, as the rate spans both
        own = zone_fan[zone]
        supplied = fan_only & (own >= 0.999)
        returns = fan_only & (own <= 0.001)
        states = [
            s & np.concatenate([s[1:], [False]]) for s in (supplied, returns, still)
        ]
        row = f"{name:<15}{zone:>5}{np.nanmean(gap):>+11.2f}"
        row += "".join(_cell(_fit_k(gap, rate, s)) for s in states) + "       "
        row += "".join(_cell(_fit_k(gap, rate, s & night)) for s in states)
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

    _nights(start, end, width, tz, rooms, outdoor, heat, zone_fan, experiment)


def _nights(start, end, width, tz, rooms, outdoor, heat, zone_fan, experiment):
    """Section 3: each floor's cooling on no-fan nights against fan nights."""
    bins = len(heat)
    edge = max(int(timedelta(minutes=15) / width), 1)  # average 15 min at each end

    def at(group: list[str], i: int) -> float:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return float(
                np.nanmean([np.nanmean(rooms[n][i : i + edge]) for n in group])
            )

    first, last = NIGHT_HOURS
    print(
        f"\n3. No-fan nights against fan nights, {first:02d}:00 to "
        f"{last - 1:02d}:00 local: drop in C (per hour per K of indoor-outdoor gap, "
        "x1000); nights with heating over 5% left out"
    )
    print(
        f"{'night':<11}{'kind':<7}{'heat':>5}{'out C':>7}"
        + "".join(f"{f:>19}" for f in FLOORS)
        + "   fan share z1-z4"
    )
    found: dict[str, list[dict[str, tuple[float, float]]]] = {"no fan": [], "fan": []}
    day = start.astimezone(tz).date()
    while True:
        a = datetime(day.year, day.month, day.day, first, tzinfo=tz)
        b = a + timedelta(hours=24 - first + last - 1)
        day += timedelta(days=1)
        i, j = int((a - start) / width), int((b - start) / width)
        if i < 0:
            continue
        if b + timedelta(minutes=15) > end or j + edge > bins:
            break
        share = experiment[i:j].mean()
        kind = "no fan" if share > 0.9 else "fan" if share == 0 else None
        if kind is None or heat[i:j].mean() > 0.05:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out = float(np.nanmean(outdoor[i:j]))
        hours = (b - a).total_seconds() / 3600
        drops = {}
        for f, group in FLOORS.items():
            t0, t1 = at(group, i), at(group, j)
            drops[f] = (t1 - t0, (t1 - t0) / hours / (t0 - out) * 1000)
        found[kind].append(drops)
        fans = " ".join(f"{zone_fan[z][i:j].mean():>4.0%}" for z in ZONES)
        print(
            f"{a:%Y-%m-%d} {kind:<7}{heat[i:j].mean():>5.0%}{out:>7.1f}"
            + "".join(f"{d:>+11.2f} ({r:>+4.0f})" for d, r in drops.values())
            + f"   {fans}"
        )
    for kind, nights in found.items():
        if not nights:
            continue
        print(
            f"{'mean ' + kind:<18}{len(nights):>3} nights"
            + "".join(
                f"{np.mean([n[f][0] for n in nights]):>+11.2f} "
                f"({np.mean([n[f][1] for n in nights]):>+4.0f})"
                for f in FLOORS
            )
        )


if __name__ == "__main__":
    main()
