"""Can a door's state be read from the temperatures either side? (hypothesis 09)

Ground truth is the contact sensor on the S basement bedroom door
(``binary_sensor.s_basement_bedroom_door``). the S basement bedroom is compared with
three nearby basement rooms (the zone 2 thermostat and the NE and SE basement
bedrooms). In 15 minute bins, labelled open (door open for more than half the
bin) or closed (shut the whole bin), it measures two features per partner:

* the temperature gradient ``|room - partner|`` (an open door should shrink it);
* the rate mismatch ``|dRoom/dt - dPartner/dt|`` (an open door should make the
  two rooms move together).

For each feature it reports the median when open and when closed and the area
under the ROC curve (0.5 is a coin flip, 1.0 perfect separation, below 0.5 means
the feature points the other way). It also repeats the comparison for quiet
night bins (sun down, no zone heating), where the fewest other things move
temperatures. Finally it gives the change in gradient across long open and long
closed stretches.

Usage::

    uv run python scripts/door_state.py --days 14
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import statistics
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import ROOMS, ZONES, _bin_means, _overlap_fraction

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

DOOR = "binary_sensor.s_basement_bedroom_door"
TARGET = "S basement"
PARTNERS = ["Z2 basement", "NE basement", "SE basement"]
MIN_PER_CLASS = 10


def auc(open_values: np.ndarray, closed_values: np.ndarray) -> float:
    """Chance a random open bin has a larger value than a random closed one."""
    if len(open_values) == 0 or len(closed_values) == 0:
        return float("nan")
    wins = (open_values[:, None] > closed_values[None, :]).sum()
    ties = (open_values[:, None] == closed_values[None, :]).sum()
    return float((wins + 0.5 * ties) / (len(open_values) * len(closed_values)))


def _report(label: str, feature: np.ndarray, is_open, is_closed, unit: str) -> None:
    o, c = feature[is_open], feature[is_closed]
    o, c = o[~np.isnan(o)], c[~np.isnan(c)]
    if len(o) < MIN_PER_CLASS or len(c) < MIN_PER_CLASS:
        print(f"    {label:<14} too few bins (open {len(o)}, closed {len(c)})")
        return
    print(
        f"    {label:<14} open {np.median(o):5.2f} (n={len(o):3d})  "
        f"closed {np.median(c):5.2f} (n={len(c):3d}) {unit}  "
        f"AUC for 'open is larger' {auc(o, c):.2f}"
    )


def main() -> None:
    """Print the door classification summary."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    door_states = fetch_states(args.ha_url, token, DOOR, start, end)
    open_fraction = _overlap_fraction(
        runs_from_states(door_states, end, {"on"}), start, bins, width
    )
    is_open = open_fraction > 0.5
    is_closed = open_fraction == 0.0
    # Door history may start after `start`; only use bins since its first state.
    first = datetime.fromisoformat(door_states[0]["last_changed"]).astimezone(UTC)
    valid = np.array([start + i * width >= first for i in range(bins)])
    is_open &= valid
    is_closed &= valid
    print(
        f"{bins} bins of {args.bin} min; door open >half the bin: "
        f"{int(is_open.sum())}, closed all bin: {int(is_closed.sum())}\n"
    )

    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
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
    mids = [start + (i + 0.5) * width for i in range(bins)]
    night = np.array([solar_elevation_degrees(m, lat, lon) < -6.0 for m in mids])
    quiet = night & (furnace == 0)

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url,
            token,
            [ROOMS[TARGET], *(ROOMS[n] for n in PARTNERS)],
            start,
            end,
            period="5minute",
        )
    )
    target = _bin_means(stats.get(ROOMS[TARGET], []), start, bins, width)
    d_target = np.full(bins, np.nan)
    d_target[:-1] = (target[1:] - target[:-1]) / hours

    for name in PARTNERS:
        partner = _bin_means(stats.get(ROOMS[name], []), start, bins, width)
        d_partner = np.full(bins, np.nan)
        d_partner[:-1] = (partner[1:] - partner[:-1]) / hours
        gradient = np.abs(target - partner)
        mismatch = np.abs(d_target - d_partner)
        print(f"{TARGET} vs {name}")
        print("  all bins")
        _report("gradient", gradient, is_open, is_closed, "C")
        _report("rate mismatch", mismatch, is_open, is_closed, "C/h")
        print("  quiet night bins (sun down, no heating)")
        _report("gradient", gradient, is_open & quiet, is_closed & quiet, "C")
        _report("rate mismatch", mismatch, is_open & quiet, is_closed & quiet, "C/h")

        # Change in gradient over stretches of at least 6 bins (90 min at 15 min)
        spans = {"open": [], "closed": []}
        labels = np.where(is_open, 1, np.where(is_closed, 0, -1))
        i = 0
        while i < bins:
            j = i
            while j + 1 < bins and labels[j + 1] == labels[i]:
                j += 1
            if labels[i] >= 0 and j - i + 1 >= 6:
                g0, g1 = gradient[i], gradient[j]
                if not (np.isnan(g0) or np.isnan(g1)):
                    spans["open" if labels[i] else "closed"].append(g1 - g0)
            i = j + 1
        for kind, vals in spans.items():
            if vals:
                print(
                    f"  gradient change across {kind} stretches of 90+ min: "
                    f"median {statistics.median(vals):+.2f} C (n={len(vals)})"
                )
        print()


if __name__ == "__main__":
    main()
