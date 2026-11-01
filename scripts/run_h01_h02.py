"""Run hypotheses 01 and 02 against Open-Meteo (and optionally Home Assistant).

Usage (from the repository root)::

    uv run python scripts/run_h01_h02.py 2025-01-01 2025-12-31 --group-by season
    uv run python scripts/run_h01_h02.py 2025-01-01 2025-12-31 --plot-dir plots

``--location "name,lat,lon,kind"`` may be repeated; with none given the example
locations are used.

To add a Home Assistant sensor, set ``HA_TOKEN`` (a long-lived access token) and
pass ``--ha-url`` and ``--ha-entity``. The home position comes from Home
Assistant, and weather classes come from Open-Meteo for that position.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, time
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from custom_components.house_thermal_lab.experiments import (
    GROUP_BY,
    analyse_with_external_weather,
    format_table,
    group_results,
    run,
    summarise,
)
from custom_components.house_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_sensor_history,
)
from custom_components.house_thermal_lab.locations import (
    EXAMPLE_LOCATIONS,
    Location,
    home_location,
)
from custom_components.house_thermal_lab.open_meteo import fetch_hourly


def _parse_location(text: str) -> Location:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) not in (3, 4):
        raise argparse.ArgumentTypeError("expected 'name,lat,lon[,kind]'")
    kind = parts[3] if len(parts) == 4 else "other"
    return Location(parts[0], float(parts[1]), float(parts[2]), kind)


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.lower())


def main() -> None:
    """Parse arguments, run the experiments and print (and plot) the results."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("start", type=date.fromisoformat)
    p.add_argument("end", type=date.fromisoformat)
    p.add_argument("--location", action="append", type=_parse_location)
    p.add_argument("--group-by", choices=GROUP_BY, default="all")
    p.add_argument("--plot-dir", type=Path, help="write one PNG per location here")
    p.add_argument("--ha-url", help="Home Assistant URL, e.g. http://ha.local:8123")
    p.add_argument("--ha-entity", help="temperature sensor entity id")
    args = p.parse_args()

    plot = None
    if args.plot_dir:
        from plot_profiles import plot_location

        args.plot_dir.mkdir(parents=True, exist_ok=True)

        def plot(loc: Location, results: list) -> None:
            if results:
                name = f"{_slug(loc.name)}_{args.group_by}.png"
                plot_location(loc, results, args.group_by, args.plot_dir / name)

    locations = args.location or list(EXAMPLE_LOCATIONS)
    summaries = run(
        locations, args.start, args.end, group_by=args.group_by, on_results=plot
    )

    if args.ha_url and args.ha_entity:
        token = os.environ["HA_TOKEN"]
        lat, lon = fetch_home_position(args.ha_url, token)
        here = home_location(lat, lon, f"HA {args.ha_entity}")
        start = datetime.combine(args.start, time.min, tzinfo=UTC)
        end = datetime.combine(args.end, time.max, tzinfo=UTC)
        sensor = fetch_sensor_history(args.ha_url, token, args.ha_entity, start, end)
        weather = fetch_hourly(here, args.start, args.end)
        results = analyse_with_external_weather(sensor, weather, here)
        if plot:
            plot(here, results)
        summaries.extend(
            summarise(here, group, label)
            for label, group in group_results(results, args.group_by).items()
        )

    print(format_table(summaries))


if __name__ == "__main__":
    main()
