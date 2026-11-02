"""Furnace start lag, and the dip and rebound after a call (hypotheses 05, 13).

For every heating call of each zone, from the thermostat's own reading
(``custom_components/house_thermal_lab/calls.py`` does the measuring):

* how long until the heat shows at the thermostat (lag);
* how much it rose during the call;
* after the call: the overshoot, the dip once the forced warm air is gone, and
  the rebound as the room's surfaces give heat back.

Split by stage (low only, or stepped up to high) and by call length. The after
window stops at the next call, so short gaps between calls give short windows.

Usage::

    uv run python scripts/furnace_lag.py --days 11 --after 90
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
from regress_rooms import ZONES

from custom_components.house_thermal_lab.calls import (
    calls_from_states,
    responses,
    temperature_series,
)
from custom_components.house_thermal_lab.ha_history import fetch_states

LENGTHS = [(0, 10), (10, 20), (20, 40), (40, 1e9)]


def _med(values) -> str:
    values = [v for v in values if v is not None]
    return f"{statistics.median(values):+.2f}" if values else "   -"


def main() -> None:
    """Print one block per zone."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=11)
    p.add_argument("--after", type=float, default=90.0, help="minutes after a call")
    p.add_argument("--min-gap", type=float, default=30.0, help="minutes to next call")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    head = (
        f"{'calls':>6}{'min':>6}{'median':>7}{'max':>6}  {'lag min':>8}"
        f"{'no rise':>8}{'rise C':>8}{'overshoot':>10}{'dip C':>7}{'at min':>7}"
        f"{'rebound':>8}"
    )
    print(
        f"{args.days} days to {end:%Y-%m-%d %H:%M} UTC; after-call window "
        f"{args.after:g} min (dip and rebound only for calls with {args.min_gap:g}+ "
        "min before the next)\n"
    )
    for zone in ZONES:
        states = fetch_states(
            args.ha_url, token, f"climate.{zone}", start, end, with_attributes=True
        )
        calls = calls_from_states(states, end)
        if not calls:
            print(f"{zone}: no heating calls\n")
            continue
        series = temperature_series(states)
        items = responses(calls, series, args.after)
        gaps = {
            c.start: (calls[i + 1].start - c.end).total_seconds() / 60.0
            if i + 1 < len(calls)
            else 1e9
            for i, c in enumerate(calls)
        }
        print(f"{zone}  {'':<14}{head}")
        groups = [("low only", "low", None), ("stepped up", "stepped", None)]
        groups += [(f"{lo:g}-{hi:g} min", None, (lo, hi)) for lo, hi in LENGTHS[:-1]]
        groups.append((f"{LENGTHS[-1][0]:g}+ min", None, LENGTHS[-1]))
        for label, stage, span in groups:
            group = [
                r
                for r in items
                if (stage is None or r.call.stage == stage)
                and (span is None or span[0] <= r.call.minutes < span[1])
            ]
            if not group:
                continue
            spaced = [r for r in group if gaps[r.call.start] >= args.min_gap]
            minutes = [r.call.minutes for r in group]
            print(
                f"    {label:<14}{len(group):>6}{min(minutes):>6.0f}"
                f"{statistics.median(minutes):>7.0f}{max(minutes):>6.0f}  "
                f"{_med(r.lag for r in group):>8}"
                f"{sum(r.lag is None for r in group):>8}"
                f"{_med(r.rise for r in group):>8}"
                f"{_med(r.overshoot for r in spaced):>10}"
                f"{_med(r.dip for r in spaced):>7}"
                f"{_med(r.dip_minutes for r in spaced):>7}"
                f"{_med(r.rebound for r in spaced):>8}"
                f"   ({len(spaced)} spaced)"
            )
        print()
    print(
        "lag: minutes until the reading first rises; no rise: calls where it never "
        "did.\novershoot, dip and rebound are after the call ends, relative to the "
        "reading at the end;\n'at min' is when the dip bottoms out."
    )


if __name__ == "__main__":
    main()
