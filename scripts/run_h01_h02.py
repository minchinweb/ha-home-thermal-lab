"""Run hypotheses 01 and 02 against Open-Meteo history from the command line.

Usage (from the repository root)::

    python scripts/run_h01_h02.py 2025-01-01 2025-12-31
    python scripts/run_h01_h02.py 2025-06-01 2025-06-30 --location "Name,lat,lon,kind"

``--location`` may be repeated; with none given the example locations are used.
"""

import argparse
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from custom_components.house_thermal_lab.experiments import format_table, run  # noqa: E402
from custom_components.house_thermal_lab.locations import (  # noqa: E402
    EXAMPLE_LOCATIONS,
    Location,
)


def _parse_location(text: str) -> Location:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) not in (3, 4):
        raise argparse.ArgumentTypeError("expected 'name,lat,lon[,kind]'")
    kind = parts[3] if len(parts) == 4 else "other"
    return Location(parts[0], float(parts[1]), float(parts[2]), kind)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("start", type=date.fromisoformat)
    p.add_argument("end", type=date.fromisoformat)
    p.add_argument("--location", action="append", type=_parse_location)
    args = p.parse_args()
    locations = args.location or list(EXAMPLE_LOCATIONS)
    print(format_table(run(locations, args.start, args.end)))


if __name__ == "__main__":
    main()
