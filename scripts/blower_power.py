"""Electrical power of the furnace blower, from whole-house power (for an energy
sensor; hypotheses 08 and 14).

The Eagle meter reads whole-house power about every 30 seconds. The blower's
draw shows as a step whenever it switches, so three kinds of edge are measured
(median power in the ``--edge`` minutes after minus before):

* **fan on / fan off**: the blower starting or stopping with no zone heating
  (only the short gaps the fan minimum on-times leave, see 08);
* **heat on / heat off**: a heating call starting or ending while the blower was
  already running for the fan (the extra draw of heating: inducer, igniter,
  gas valve and a faster blower);
* **to high stage**: a call stepping up from W1 to W2.

Edges within ``--edge`` minutes of another edge are skipped, as are edges where
power moved by more than ``--noise`` kW on either side (another appliance).

Usage::

    uv run python scripts/blower_power.py --days 10
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
from furnace_stages import HIGH, stage_runs
from regress_rooms import POWER, ZONES

from custom_components.home_thermal_lab.ha_history import fetch_states
from custom_components.home_thermal_lab.hvac import runs_from_states
from custom_components.home_thermal_lab.hvac_response import merge_runs


def _power_series(states: list[dict]) -> list[tuple[datetime, float]]:
    out = []
    for s in states:
        try:
            value = float(s["state"])
        except ValueError:
            continue
        out.append((datetime.fromisoformat(s["last_changed"]).astimezone(UTC), value))
    return sorted(out)


def _window(series, lo: datetime, hi: datetime) -> list[float]:
    return [v for t, v in series if lo <= t < hi]


def main() -> None:
    """Print the median step for each kind of edge."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--edge", type=float, default=2.0, help="minutes either side")
    p.add_argument("--noise", type=float, default=0.3, help="kW spread allowed")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    power = _power_series(fetch_states(args.ha_url, token, POWER, start, end))
    heat_runs, fan_runs, high_runs = [], [], []
    for z in ZONES:
        states = fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        heat_runs += runs_from_states(states, end, {"heating"}, "hvac_action")
        fan_runs += stage_runs(states, end, "fan")
        high_runs += stage_runs(states, end, HIGH)
    heat = merge_runs(heat_runs, 0.0)
    blower = merge_runs(fan_runs, 0.0)
    high = merge_runs(high_runs, 0.0)
    edge = timedelta(minutes=args.edge)

    def heating_near(t: datetime) -> bool:
        return any(r.start - edge <= t <= r.end + edge for r in heat)

    def blower_on(t: datetime) -> bool:
        return any(r.start <= t < r.end for r in blower)

    events: dict[str, list[datetime]] = {
        "fan on": [r.start for r in blower if not heating_near(r.start)],
        "fan off": [r.end for r in blower if not heating_near(r.end)],
        "heat on": [r.start for r in heat if blower_on(r.start - edge)],
        "heat off": [r.end for r in heat if blower_on(r.end + edge)],
        "to high stage": [r.start for r in high],
    }
    all_edges = sorted(t for ts in events.values() for t in ts)
    print(
        f"{len(power)} power readings over {args.days} days; median step in kW, "
        f"{args.edge:g} min either side\n"
    )
    for kind, times in events.items():
        steps = []
        for t in times:
            if any(
                0 < abs((o - t).total_seconds()) < args.edge * 60 for o in all_edges
            ):
                continue
            before = _window(power, t - edge, t)
            after = _window(power, t, t + edge)
            if len(before) < 2 or len(after) < 2:
                continue
            if (
                max(before) - min(before) > args.noise
                or max(after) - min(after) > args.noise
            ):
                continue
            steps.append(statistics.median(after) - statistics.median(before))
        if steps:
            q = statistics.quantiles(steps, n=4) if len(steps) >= 4 else [0, 0, 0]
            print(
                f"  {kind:<14} {len(steps):>4} edges: median "
                f"{statistics.median(steps):+.3f} kW "
                f"(quartiles {q[0]:+.3f} to {q[2]:+.3f})"
            )
        else:
            print(f"  {kind:<14} no clean edges")


if __name__ == "__main__":
    main()
