"""Measure heat bleeding into other zones when one zone calls (hypotheses 05, 09).

The zoning valves leak, so a heat call in one zone warms the others too, the
kitchen most of all. This looks only at episodes where a single zone called for
heat, then reports how fast each zone (calling or not) warmed compared with its
drift just before. Episodes are split into night (sun below -6 degrees) and day
(above 5 degrees) so solar gain does not masquerade as bleed.

Usage::

    uv run python scripts/hvac_bleed.py --days 10 --min-minutes 15
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env

from custom_components.house_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.house_thermal_lab.hvac import Run, runs_from_states
from custom_components.house_thermal_lab.hvac_response import (
    analyse_responses,
    merge_runs,
    temperature_series,
)
from custom_components.house_thermal_lab.solar import solar_elevation_degrees

NIGHT_BELOW = -6.0
DAY_ABOVE = 5.0


def _period(episode: Run, lat: float, lon: float) -> str | None:
    middle = episode.start + (episode.end - episode.start) / 2
    elevation = solar_elevation_degrees(middle, lat, lon)
    if elevation < NIGHT_BELOW:
        return "night"
    if elevation > DAY_ABOVE:
        return "day"
    return None  # twilight: skip


def _med(values: list[float]) -> str:
    return f"{statistics.median(values):+.2f}" if values else "-"


def main() -> None:
    """Print bleed into each zone, by calling zone and time of day."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--zones", nargs="+", default=["z1", "z2", "z3", "z4"])
    p.add_argument("--min-minutes", type=float, default=15.0)
    p.add_argument("--window", type=float, default=60.0)
    p.add_argument("--merge-gap", type=float, default=5.0)
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    states = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in args.zones
    }
    own = {
        z: runs_from_states(states[z], end, {"heating"}, "hvac_action")
        for z in args.zones
    }
    episodes = merge_runs([r for runs in own.values() for r in runs], args.merge_gap)

    def callers(ep: Run) -> list[str]:
        return [
            z
            for z in args.zones
            if any(r.start < ep.end and r.end > ep.start for r in own[z])
        ]

    minutes = f"{args.min_minutes:.0f}"
    print(f"{len(episodes)} episodes; single-caller ones of {minutes}+ min:\n")
    print(
        f"{'caller':<8}{'when':<7}{'zone':<6}{'n':>4}{'rate C/h':>10}"
        f"{'drift C/h':>11}{'excess C/h':>12}"
    )
    series = {z: temperature_series(states[z]) for z in args.zones}
    for caller in args.zones:
        for when in ("night", "day"):
            chosen = [
                ep
                for ep in episodes
                if ep.minutes >= args.min_minutes
                and callers(ep) == [caller]
                and _period(ep, lat, lon) == when
            ]
            if not chosen:
                continue
            for z in args.zones:
                rs = analyse_responses(chosen, series[z], own[z], args.window, 0.0)
                excess = [
                    r.excess_rate_per_h for r in rs if r.excess_rate_per_h is not None
                ]
                base = [
                    r.baseline_rate_per_h
                    for r in rs
                    if r.baseline_rate_per_h is not None
                ]
                print(
                    f"{caller:<8}{when:<7}{z:<6}{len(excess):>4}"
                    f"{_med([r.rate_per_h for r in rs]):>10}"
                    f"{_med(base):>11}{_med(excess):>12}"
                )
            print()


if __name__ == "__main__":
    main()
