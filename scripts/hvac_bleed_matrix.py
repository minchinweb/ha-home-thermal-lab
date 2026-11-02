"""Crossover bleed matrix: every room sensor against every calling combination.

Rows are room sensors (the four zone thermostats plus the other rooms); columns
are the sets of zones calling for heat during a whole-house episode (for
example ``z4`` alone, ``z2`` alone, or ``z2+z4`` together). Each cell is the
room's median extra warming rate in degrees C per hour, over its drift in an
equally long quiet stretch just before, and the number of episodes. Day and
night are pooled; ``scripts/hvac_bleed.py`` splits them. Hypothesis 06.

Usage::

    uv run python scripts/hvac_bleed_matrix.py --days 10 --min-minutes 10
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import ROOMS, ZONES

from custom_components.home_thermal_lab.ha_history import fetch_states
from custom_components.home_thermal_lab.hvac import Run, runs_from_states
from custom_components.home_thermal_lab.hvac_response import (
    analyse_responses,
    merge_runs,
    temperature_series,
)

MIN_EPISODES = 3


def _sensor_series(states: list[dict]):
    rows = []
    for s in states:
        try:
            value = float(s["state"])
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "attributes": {"current_temperature": value},
                "last_updated": s["last_changed"],
            }
        )
    return temperature_series(rows)


def main() -> None:
    """Print the matrix."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--min-minutes", type=float, default=10.0)
    p.add_argument("--window", type=float, default=60.0)
    p.add_argument("--merge-gap", type=float, default=5.0)
    p.add_argument(
        "--max-age",
        type=float,
        default=15.0,
        help="skip episodes where the room's last reading is older than this (minutes)",
    )
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in ZONES
    }
    own = {
        z: runs_from_states(climate[z], end, {"heating"}, "hvac_action") for z in ZONES
    }
    episodes = [
        e
        for e in merge_runs([r for rs in own.values() for r in rs], args.merge_gap)
        if e.minutes >= args.min_minutes
    ]

    def callers(ep: Run) -> str:
        zs = [
            z
            for z in ZONES
            if any(r.start < ep.end and r.end > ep.start for r in own[z])
        ]
        return "+".join(zs)

    groups: dict[str, list[Run]] = defaultdict(list)
    for ep in episodes:
        groups[callers(ep)].append(ep)
    labels = sorted(
        (g for g, eps in groups.items() if len(eps) >= MIN_EPISODES),
        key=lambda g: (-len(groups[g]), g),
    )
    print(
        f"{len(episodes)} episodes of {args.min_minutes:.0f}+ min; callers: "
        + ", ".join(f"{g} ({len(groups[g])})" for g in sorted(groups))
        + "\n"
    )
    print(f"{'room':<16}" + "".join(f"{g:>14}" for g in labels))
    for name, entity in ROOMS.items():
        series = _sensor_series(fetch_states(args.ha_url, token, entity, start, end))
        cells = []
        for g in labels:
            rs = analyse_responses(
                groups[g], series, [], args.window, 0.0, args.max_age
            )
            ex = [r.excess_rate_per_h for r in rs if r.excess_rate_per_h is not None]
            cells.append(
                f"{statistics.median(ex):+6.2f} (n={len(ex):2d})" if ex else "-"
            )
        print(f"{name:<16}" + "".join(f"{c:>14}" for c in cells))
    print("\ncells: median extra warming rate, C per hour above prior drift")


if __name__ == "__main__":
    main()
