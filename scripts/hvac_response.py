"""How each zone's temperature responds to furnace runs (hypotheses 05, 13).

The zone board means the furnace runs whenever any zone calls for heat, so
episodes are the union of every zone's heating runs. For each zone this reports
the rise during an episode, the rate, how far it keeps rising afterwards (the
overshoot, a first measure of thermal momentum) and how long that takes, split
by whether the zone itself was calling. Uses each climate entity's
``current_temperature`` attribute, so it reaches back as far as the recorder
keeps states.

Usage::

    uv run python scripts/hvac_response.py --days 10 --zones z1 z2 z3 z4
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

from custom_components.house_thermal_lab.ha_history import fetch_states
from custom_components.house_thermal_lab.hvac import runs_from_states
from custom_components.house_thermal_lab.hvac_response import (
    analyse_responses,
    merge_runs,
    temperature_series,
)


def _med(values: list[float]) -> str:
    return f"{statistics.median(values):.2f}" if values else "-"


def main() -> None:
    """Print one row per zone and own-call group."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--zones", nargs="+", default=["z1", "z2", "z3", "z4"])
    p.add_argument("--window", type=float, default=60.0, help="follow-up minutes")
    p.add_argument("--min-minutes", type=float, default=3.0)
    p.add_argument("--merge-gap", type=float, default=5.0, help="minutes")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
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
    if not episodes:
        print("no heating episodes")
        return
    print(
        f"{len(episodes)} whole-house heating episodes in {args.days} days "
        f"(median {statistics.median(e.minutes for e in episodes):.0f} min)\n"
    )
    print(
        f"{'zone':<6}{'own call':<10}{'n':>4}{'rise C':>8}{'rate C/h':>10}"
        f"{'overshoot C':>13}{'to peak min':>13}"
    )
    for z in args.zones:
        series = temperature_series(states[z])
        responses = analyse_responses(
            episodes, series, own[z], args.window, args.min_minutes
        )
        for label, flag in (("yes", True), ("no", False)):
            rs = [r for r in responses if r.own_call is flag]
            print(
                f"{z:<6}{label:<10}{len(rs):>4}{_med([r.rise for r in rs]):>8}"
                f"{_med([r.rate_per_h for r in rs]):>10}"
                f"{_med([r.overshoot for r in rs]):>13}"
                f"{_med([r.minutes_to_peak for r in rs]):>13}"
            )


if __name__ == "__main__":
    main()
