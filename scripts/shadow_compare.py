"""Compare the shadow sensors' log with what the thermostats actually did (17).

Reads the history of each shadow sensor (``sensor.shadow_<zone name>``, created by
``custom_components/house_thermal_lab/sensor.py``) and of the matching thermostat.
For every heating call that started after the sensor began logging, it takes the
last decision made before the call and reports whether the controller would have
skipped it, how long and how large the call was, and how far the room fell
below setpoint during the next ``--look-ahead`` hours despite the heating.

Usage::

    uv run python scripts/shadow_compare.py --zone z4=sensor.shadow_z4_office \\
        --zone z2=sensor.shadow_z2_basement --days 7
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


def _when(row: dict) -> datetime:
    return datetime.fromisoformat(row["last_updated"]).astimezone(UTC)


def main() -> None:
    """Print one summary line per zone."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zone", action="append", required=True, help="z4=sensor.shadow_x")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--look-ahead", type=float, default=3.0, help="hours")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    print(
        f"{'zone':<6}{'decisions':>10}{'calls':>7}{'would skip':>12}"
        f"{'minutes':>9}{'skipped':>9}{'median dip C':>14}{'worst dip C':>13}"
    )
    for item in args.zone:
        zone, sensor = item.split("=", 1)
        log = [
            r
            for r in fetch_states(
                args.ha_url, token, sensor, start, end, with_attributes=True
            )
            if r["state"] in ("skip", "heat")
        ]
        climate = fetch_states(
            args.ha_url, token, f"climate.{zone}", start, end, with_attributes=True
        )
        calls = runs_from_states(climate, end, {"heating"}, "hvac_action")
        if not log:
            print(f"{zone:<6}  no shadow decisions logged yet")
            continue
        logged_from = _when(log[0])
        counted = skipped = 0
        minutes = skipped_minutes = 0.0
        dips = []
        for run in calls:
            if run.start < logged_from:
                continue
            before = [r for r in log if _when(r) <= run.start]
            if not before:
                continue
            decision = before[-1]
            counted += 1
            minutes += run.minutes
            window_end = run.start + timedelta(hours=args.look_ahead)
            rooms = [
                (r["attributes"].get("current_temperature"), r["attributes"])
                for r in climate
                if run.start <= _when(r) <= window_end
            ]
            setpoint = decision["attributes"].get("setpoint")
            temps = [t for t, _ in rooms if t is not None]
            if setpoint is not None and temps:
                dips.append(min(temps) - float(setpoint))
            if decision["state"] == "skip":
                skipped += 1
                skipped_minutes += run.minutes
        median = f"{statistics.median(dips):+.2f}" if dips else "-"
        worst = f"{min(dips):+.2f}" if dips else "-"
        print(
            f"{zone:<6}{len(log):>10}{counted:>7}{skipped:>12}{minutes:>9.0f}"
            f"{skipped_minutes:>9.0f}{median:>14}{worst:>13}"
        )
    print(
        "\nA dip is the lowest thermostat reading in the look-ahead minus the setpoint,"
        "\nwith the heating that actually ran. Nothing was switched."
    )


if __name__ == "__main__":
    main()
