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
from regress_rooms import POWER, ZONES

from custom_components.home_thermal_lab.ha_history import fetch_states
from custom_components.home_thermal_lab.hvac import HIGH, runs_from_states, stage_runs
from custom_components.home_thermal_lab.hvac_response import merge_runs
from custom_components.home_thermal_lab.learn import blower_kw, edge_steps
from custom_components.home_thermal_lab.power import power_series


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
    power = power_series(fetch_states(args.ha_url, token, POWER, start, end))
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
    steps_by_kind = edge_steps(power, heat, blower, high, args.edge, args.noise)
    print(
        f"{len(power)} power readings over {args.days} days; median step in kW, "
        f"{args.edge:g} min either side\n"
    )
    for kind, steps in steps_by_kind.items():
        if steps:
            q = statistics.quantiles(steps, n=4) if len(steps) >= 4 else [0, 0, 0]
            print(
                f"  {kind:<14} {len(steps):>4} edges: median "
                f"{statistics.median(steps):+.3f} kW "
                f"(quartiles {q[0]:+.3f} to {q[2]:+.3f})"
            )
        else:
            print(f"  {kind:<14} no clean edges")
    learned, _ = blower_kw(steps_by_kind)
    print(f"\nwhat the integration would learn (kW per state): {learned}")


if __name__ == "__main__":
    main()
