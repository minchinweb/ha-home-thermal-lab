"""Furnace heating stage (W1 low, W2 high) from the Ecobee thermostats.

The Ecobee climate entities report ``equipment_running`` (for example
``auxHeat1,fan`` or ``auxHeat2,fan``). With a two-stage furnace wired to W1 and
W2, ``auxHeat1`` is the low stage and ``auxHeat2`` the high stage. This lists,
per zone and for whole-house episodes, how long each stage ran, how calls
start and whether they step up, and the whole-house power in each stage
(hypotheses 05 and 13).

Usage::

    uv run python scripts/furnace_stages.py --days 10
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import POWER, ZONES

from custom_components.home_thermal_lab.ha_history import fetch_states
from custom_components.home_thermal_lab.hvac import HIGH, LOW, Run, stage_runs
from custom_components.home_thermal_lab.hvac_response import merge_runs
from custom_components.home_thermal_lab.power import power_series, time_weighted_mean


def _overlap(a: Run, runs: list[Run]) -> float:
    return sum(
        max((min(a.end, r.end) - max(a.start, r.start)).total_seconds(), 0.0) / 60.0
        for r in runs
    )


def main() -> None:
    """Print the stage summary."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--min-minutes", type=float, default=3.0)
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    low, high = {}, {}
    for z in ZONES:
        st = fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        low[z] = stage_runs(st, end, LOW)
        high[z] = stage_runs(st, end, HIGH)
        values = Counter(
            s["attributes"].get("equipment_running") for s in st if "attributes" in s
        )
        print(
            f"{z}: low {sum(r.minutes for r in low[z]):6.0f} min in {len(low[z])} "
            f"runs; high {sum(r.minutes for r in high[z]):6.0f} min in "
            f"{len(high[z])} runs; values seen: "
            + ", ".join(f"{k!r}" for k in values if k)
        )

    all_low = [r for z in ZONES for r in low[z]]
    all_high = [r for z in ZONES for r in high[z]]
    episodes = [
        e for e in merge_runs(all_low + all_high, 5.0) if e.minutes >= args.min_minutes
    ]
    kinds: Counter[str] = Counter()
    lengths: dict[str, list[float]] = {"low only": [], "high only": [], "both": []}
    escalate: list[float] = []
    for e in episodes:
        lo = _overlap(e, all_low) > 0
        hi = _overlap(e, all_high) > 0
        kind = "both" if lo and hi else "high only" if hi else "low only"
        kinds[kind] += 1
        lengths[kind].append(e.minutes)
        if lo and hi:
            first_hi = min(
                (r.start for r in all_high if r.start < e.end and r.end > e.start),
                default=None,
            )
            if first_hi is not None:
                escalate.append(max((first_hi - e.start).total_seconds() / 60.0, 0.0))
    print(f"\n{len(episodes)} whole-house episodes of {args.min_minutes:.0f}+ min")
    for kind, n in kinds.items():
        median = statistics.median(lengths[kind])
        print(
            f"  {kind:<10}{n:>4} episodes, median {median:.0f} "
            f"min (longest {max(lengths[kind]):.0f})"
        )
    if escalate:
        print(
            f"  steps up to high after a median {statistics.median(escalate):.0f} min "
            f"(range {min(escalate):.0f}-{max(escalate):.0f})"
        )

    series = power_series(fetch_states(args.ha_url, token, POWER, start, end))
    print("\nwhole-house power (kW), settling 1 min at each edge")
    for label, runs in (("low stage", all_low), ("high stage", all_high)):
        means = []
        for r in runs:
            if r.minutes >= 4:
                m = time_weighted_mean(
                    series,
                    r.start + timedelta(minutes=1),
                    r.end - timedelta(minutes=1),
                )
                if m is not None:
                    means.append(m)
        if means:
            print(
                f"  {label:<11} n={len(means):>3} median {statistics.median(means):.2f}"
            )


if __name__ == "__main__":
    main()
