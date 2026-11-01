"""Run hypotheses 01 and 02 against Open-Meteo (and optionally Home Assistant).

Usage (from the repository root)::

    uv run python scripts/run_h01_h02.py 2025-01-01 2025-12-31 --group-by season
    uv run python scripts/run_h01_h02.py 2025-01-01 2025-12-31 --plot-dir plots

``--location "name,lat,lon,kind"`` may be repeated; with none given the example
locations are used.

Settings (HA_URL, HA_TOKEN, HA_ENTITY) are read from a git-ignored ``.env`` file
(copy ``.env.example``) or from the environment.

By default Home Assistant data comes from long-term statistics (hourly, kept
indefinitely), falling back to recorder state history; see ``--ha-source``.

To find sensor entity ids, run with ``--ha-list``. To add a Home Assistant
sensor, set ``HA_URL``, ``HA_TOKEN`` (a long-lived access token) and ``HA_ENTITY``
(or pass ``--ha-url`` and ``--ha-entity``, which may be repeated; HA_ENTITY
can list several separated by commas). The home position comes from Home
Assistant, and weather classes come from Open-Meteo for that position.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime, time
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env

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
    list_temperature_sensors,
)
from custom_components.house_thermal_lab.ha_statistics import fetch_statistics_from_url
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
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("start", type=date.fromisoformat)
    p.add_argument("end", type=date.fromisoformat)
    p.add_argument("--location", action="append", type=_parse_location)
    p.add_argument("--group-by", choices=GROUP_BY, default="all")
    p.add_argument("--plot-dir", type=Path, help="write one PNG per location here")
    p.add_argument(
        "--ha-url",
        default=os.environ.get("HA_URL"),
        help="Home Assistant URL (default: HA_URL)",
    )
    p.add_argument(
        "--ha-entity",
        action="append",
        help="sensor entity id; repeat for several (default: HA_ENTITY, which "
        "may hold several separated by commas)",
    )
    p.add_argument(
        "--ha-source",
        choices=("auto", "statistics", "history"),
        default="auto",
        help="long-term statistics (hourly, kept indefinitely), recorder state "
        "history (as long as purge_keep_days), or statistics with history as "
        "the fallback (default)",
    )
    p.add_argument(
        "--ha-list", action="store_true", help="list temperature sensors and exit"
    )
    args = p.parse_args()

    if args.ha_list:
        for entity_id, name, state in list_temperature_sensors(
            args.ha_url, os.environ["HA_TOKEN"]
        ):
            print(f"{entity_id:<55} {state:>12}  {name}")
        return

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

    entities = args.ha_entity or [
        e for e in os.environ.get("HA_ENTITY", "").replace(",", " ").split() if e
    ]
    if args.ha_url and entities:
        token = os.environ["HA_TOKEN"]
        lat, lon = fetch_home_position(args.ha_url, token)
        start = datetime.combine(args.start, time.min, tzinfo=UTC)
        end = datetime.combine(args.end, time.max, tzinfo=UTC)
        weather = fetch_hourly(home_location(lat, lon), args.start, args.end)
        stats = {}
        if args.ha_source in {"auto", "statistics"}:
            stats = asyncio.run(
                fetch_statistics_from_url(args.ha_url, token, entities, start, end)
            )
        for entity in entities:
            here = home_location(lat, lon, entity)
            if entity in stats:
                sensor = stats[entity]
            elif args.ha_source == "statistics":
                print(f"{entity}: no long-term statistics", file=sys.stderr)
                continue
            else:
                sensor = fetch_sensor_history(args.ha_url, token, entity, start, end)
            results = analyse_with_external_weather(sensor, weather, here)
            if not results:
                print(
                    f"{entity}: fewer than 22 hourly readings on every day, so "
                    "nothing to analyse (is the history too short or too sparse?)",
                    file=sys.stderr,
                )
                continue
            if plot:
                plot(here, results)
            summaries.extend(
                summarise(here, group, label)
                for label, group in group_results(results, args.group_by).items()
            )

    print(format_table(summaries))


if __name__ == "__main__":
    main()
