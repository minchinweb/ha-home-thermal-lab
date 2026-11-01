"""Summarise furnace and AC activity per zone from Home Assistant history.

A first look for hypotheses 05-07: how often, and for how long, does each zone
call for heating, cooling or the fan alone? Uses the ``hvac_action`` attribute
of ``climate.<zone>`` over the last ``--days`` days (the recorder keeps states
for ``purge_keep_days``; the climate entities are never in the statistics).

Usage::

    uv run python scripts/hvac_overview.py --days 30 --zones z1 z2 z3 z4
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env

from custom_components.house_thermal_lab.ha_history import (
    fetch_states,
    fetch_time_zone,
)
from custom_components.house_thermal_lab.hvac import (
    daily_use,
    run_summary,
    runs_from_states,
)

# `hvac_action` values of each zone's climate entity that count as each kind
KINDS = {
    "heating": {"heating"},
    "cooling": {"cooling"},
    "fan only": {"fan"},
}


def main() -> None:
    """Print one row per zone and kind of equipment."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--zones", nargs="+", default=["z1", "z2", "z3", "z4"])
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    today = end.astimezone(tz).date()
    days = [today - timedelta(days=n) for n in range(args.days, 0, -1)]  # complete days

    print(
        f"{'zone':<6}{'kind':<9}{'h/day':>7}{'runs/day':>10}{'median min':>12}"
        f"{'longest min':>13}{'days with run':>15}"
    )
    by_zone = {
        zone: fetch_states(
            args.ha_url, token, f"climate.{zone}", start, end, with_attributes=True
        )
        for zone in args.zones
    }
    for zone in args.zones:
        for kind, on_states in KINDS.items():
            states = by_zone[zone]
            runs = runs_from_states(states, end, on_states, "hvac_action")
            use = daily_use(runs, tz, days)
            s = run_summary(runs, use)
            print(
                f"{zone:<6}{kind:<9}{s['hours_per_day']:>7.1f}{s['runs_per_day']:>10.1f}"
                f"{s['median_run_min']:>12.0f}{s['longest_run_min']:>13.0f}"
                f"{s['days_with_run']:>15.0%}"
            )


if __name__ == "__main__":
    main()
