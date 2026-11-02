"""Does the furnace show up in whole-house power? (hypothesis 14)

Compares power just before, during and after whole-house heating episodes with
the same measurement at control times (same length, no heating nearby, spread
across the same days). Also prints the hour-of-day profile and counts large
power events by hour, which is where an electric stove or oven shows up.

Usage::

    uv run python scripts/power_check.py --days 10
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import random
import statistics
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env

from custom_components.house_thermal_lab.ha_history import (
    fetch_states,
    fetch_time_zone,
)
from custom_components.house_thermal_lab.hvac import Run, runs_from_states
from custom_components.house_thermal_lab.hvac_response import merge_runs
from custom_components.house_thermal_lab.power import (
    median_or_nan,
    power_series,
    steps_around,
    time_weighted_mean,
)

POWER = "sensor.eagle_00bb9c_power_demand"
ZONES = ["z1", "z2", "z3", "z4"]


def _controls(episodes: list[Run], start: datetime, end: datetime, n: int) -> list[Run]:
    """Random runs matching the episodes' lengths, away from any heating."""
    rng = random.Random(0)
    busy = [
        (e.start - timedelta(minutes=30), e.end + timedelta(minutes=30))
        for e in episodes
    ]
    out: list[Run] = []
    tries = 0
    while len(out) < n and tries < n * 200:
        tries += 1
        length = rng.choice(episodes).minutes
        s = start + timedelta(
            seconds=rng.uniform(0, (end - start).total_seconds() - length * 60)
        )
        e = s + timedelta(minutes=length)
        if all(e < b0 or s > b1 for b0, b1 in busy):
            out.append(Run(s, e))
    return out


def _line(label: str, steps: list) -> str:
    return (
        f"{label:<22}{len(steps):>4}"
        f"{median_or_nan([s.before for s in steps]):>9.2f}"
        f"{median_or_nan([s.rise for s in steps]):>+10.2f}"
        f"{median_or_nan([s.fall for s in steps]):>+10.2f}"
    )


def main() -> None:
    """Print the step comparison and the hour-of-day profile."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--min-minutes", type=float, default=8.0)
    p.add_argument("--big-kw", type=float, default=2.0, help="above the baseline")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    series = power_series(fetch_states(args.ha_url, token, POWER, start, end))
    own = []
    for z in ZONES:
        states = fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        own += runs_from_states(states, end, {"heating"}, "hvac_action")
    episodes = [e for e in merge_runs(own, 5.0) if e.minutes >= args.min_minutes]
    steps = steps_around(episodes, series, min_minutes=args.min_minutes)
    controls = steps_around(
        _controls(episodes, start, end, len(episodes)),
        series,
        min_minutes=args.min_minutes,
    )
    print(
        f"{len(series)} power readings; {len(episodes)} heating episodes of "
        f"{args.min_minutes:.0f}+ min\n"
    )
    print(f"{'':<22}{'n':>4}{'before kW':>9}{'rise kW':>10}{'fall kW':>10}")
    print(_line("heating episodes", steps))
    print(_line("control (no heating)", controls))

    by_hour: dict[int, list[float]] = defaultdict(list)
    hourly: dict[tuple, float] = {}
    t = start.replace(minute=0, second=0, microsecond=0)
    while t < end:
        mean = time_weighted_mean(series, t, t + timedelta(hours=1))
        if mean is not None:
            by_hour[t.astimezone(tz).hour].append(mean)
            hourly[(t.astimezone(tz).date(), t.astimezone(tz).hour)] = mean
        t += timedelta(hours=1)
    base = statistics.median(v for vs in by_hour.values() for v in vs)
    big: dict[int, int] = defaultdict(int)
    for (_, hour), mean in hourly.items():
        if mean > base + args.big_kw:
            big[hour] += 1
    print(
        f"\nhour of day (local): median kW, and hours above baseline "
        f"{base:.2f} + {args.big_kw:.1f} kW"
    )
    for hour in range(24):
        vs = by_hour.get(hour, [])
        print(f"{hour:02d}  {median_or_nan(vs):5.2f}  {'#' * big.get(hour, 0)}")


if __name__ == "__main__":
    main()
