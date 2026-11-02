"""Relative size of the low (W1) and high (W2) heating stages (hypothesis 05).

For each zone, compares how fast its room sensors warm during low-stage and
high-stage stretches of heating calls, each as the rate above the room's drift
over the half hour before the call. The first minutes of every stretch are
skipped while the furnace and ducts warm up. The ratio of the two median
excess rates estimates high / low output for that zone. Rooms in the zone are
averaged per stretch.

Usage::

    uv run python scripts/furnace_stage_ratio.py --days 10 --skip 3
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
from furnace_stages import HIGH, LOW, stage_runs
from hvac_bleed_matrix import _sensor_series
from regress_rooms import ROOMS, ZONES
from thermal_momentum import ZONE_OF_ROOM

from custom_components.home_thermal_lab.ha_history import fetch_states
from custom_components.home_thermal_lab.hvac_response import value_at


def _rate(series, a: datetime, b: datetime) -> float | None:
    va, vb = value_at(series, a), value_at(series, b)
    if va is None or vb is None or b <= a:
        return None
    return (vb - va) / ((b - a).total_seconds() / 3600.0)


def main() -> None:
    """Print the stage comparison per zone."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--skip", type=float, default=3.0, help="minutes to skip")
    p.add_argument("--min-minutes", type=float, default=8.0, help="stretch length")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    skip = timedelta(minutes=args.skip)
    before = timedelta(minutes=30)
    for z in ZONES:
        st = fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        low, high = stage_runs(st, end, LOW), stage_runs(st, end, HIGH)
        if not high:
            print(f"{z}: no high-stage runs")
            continue
        rooms = [
            _sensor_series(fetch_states(args.ha_url, token, ROOMS[n], start, end))
            for n, zone in ZONE_OF_ROOM.items()
            if zone == z
        ]

        def excess(
            a: datetime, b: datetime, base: datetime, rooms=rooms
        ) -> float | None:
            vals = []
            for s in rooms:
                run = _rate(s, a + skip, b)
                drift = _rate(s, base - before, base)
                if run is not None and drift is not None:
                    vals.append(run - drift)
            return statistics.mean(vals) if vals else None

        # low stretches: low runs not overlapping any high run
        lows = [
            r
            for r in low
            if r.minutes >= args.min_minutes
            and not any(h.start < r.end and h.end > r.start for h in high)
        ]
        # low stretch before the step up, and high stretches
        stepped = []
        for h in high:
            lead = [
                r
                for r in low
                if r.end >= h.start - timedelta(minutes=2) and r.start < h.start
            ]
            if lead:
                stepped.append((lead[-1].start, h))
        lo_alone = [
            x for r in lows if (x := excess(r.start, r.end, r.start)) is not None
        ]
        lo_pre = [
            x
            for s, h in stepped
            if (h.start - s).total_seconds() / 60 >= args.min_minutes
            and (x := excess(s, h.start, s)) is not None
        ]
        hi = [
            x
            for s, h in stepped
            if h.minutes >= args.min_minutes
            and (x := excess(h.start, h.end, s)) is not None
        ]

        def med(v):
            return f"{statistics.median(v):+.2f} (n={len(v)})" if v else "-"

        print(
            f"{z}: low alone {med(lo_alone)}; low before step-up {med(lo_pre)}; "
            f"high {med(hi)} C/h above prior drift"
        )
        low_all = lo_alone + lo_pre
        if low_all and hi and statistics.median(low_all) > 0:
            ratio = statistics.median(hi) / statistics.median(low_all)
            print(f"    high / low = {ratio:.2f}")


if __name__ == "__main__":
    main()
