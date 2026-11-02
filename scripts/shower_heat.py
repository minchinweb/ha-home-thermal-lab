"""Showers from bathroom humidity, and the heat they leave behind (hypothesis 18).

Water use is not metered, but a shower shows clearly in the bathroom's relative
humidity. An event starts when humidity rises by at least ``--rise`` points
within ``--window`` minutes. For each event, on 5-minute readings:

* start, peak humidity and the rise in relative and absolute humidity (g/m3);
* the bathroom temperature at the start, its peak within the next hour, and
  the rise; and how long until humidity falls back halfway;
* the same temperature rise for the neighbouring rooms, to see whether the
  heat spreads.

A rough heat figure: the moisture added to the bathroom air (absolute humidity
rise times the room's air volume) carries ``2.45 kJ/g`` of latent heat; the
sensible part is the air's temperature rise times its heat capacity. Both are
small next to the hot water itself (about 8 kWh for an 8 minute shower), most
of which goes down the drain; the walls and the house's air exchange take the
rest. The event list is the useful output for now: a log of showers to use as
an input for the other hypotheses.

Usage::

    uv run python scripts/shower_heat.py --days 14
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import math
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import ROOMS, _bin_means

from custom_components.home_thermal_lab.ha_history import fetch_time_zone
from custom_components.home_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)

BATHROOMS = {
    "Upstairs bath": (
        "sensor.upstairs_bathroom_temp_humidity_sensor_temperature",
        "sensor.upstairs_bathroom_temp_humidity_sensor_humidity",
        ["N bedroom", "Z3 master"],
    ),
    "Main floor bath": (
        "sensor.main_floor_bathroom_temp_humidity_temperature",
        "sensor.main_floor_bathroom_temp_humidity_humidity",
        ["Z1 kitchen"],
    ),
}
AIR_VOLUME = 12.0  # m3, a small bathroom
AIR_HEAT = 1.2  # kJ per m3 per C


def absolute_humidity(temp_c: float, rh: float) -> float:
    """Water vapour in g/m3 from temperature and relative humidity (Magnus)."""
    sat = 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))  # hPa
    return sat * rh * 2.1674 / (273.15 + temp_c)


def main() -> None:
    """Print the shower log and a summary."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--rise", type=float, default=8.0, help="RH points")
    p.add_argument("--window", type=int, default=15, help="minutes")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    width = timedelta(minutes=5)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    entities = [e for t, h, _ in BATHROOMS.values() for e in (t, h)]
    entities += list(ROOMS.values())
    stats = asyncio.run(
        fetch_statistics_from_url(args.ha_url, token, entities, start, end, "5minute")
    )
    w = max(int(args.window / 5), 1)
    hour = 12
    for bath, (t_ent, h_ent, neighbours) in BATHROOMS.items():
        temp = _bin_means(stats.get(t_ent, []), start, bins, width)
        rh = _bin_means(stats.get(h_ent, []), start, bins, width)
        if np.isnan(rh).all():
            print(f"{bath}: no humidity data\n")
            continue
        others = {
            n: _bin_means(stats.get(ROOMS[n], []), start, bins, width)
            for n in neighbours
        }
        events = []
        i = w
        while i < bins - hour:
            base = rh[i - w]
            if np.isnan(base) or np.isnan(rh[i]) or rh[i] - base < args.rise:
                i += 1
                continue
            s = i - w
            seg = rh[s : s + hour]
            peak_i = s + int(np.nanargmax(seg))
            half = base + (rh[peak_i] - base) / 2
            decay = next(
                (k for k in range(peak_i, min(peak_i + 48, bins)) if rh[k] <= half),
                None,
            )
            t_seg = temp[s : s + hour]
            row = {
                "when": start + s * width,
                "rh0": base,
                "rh_peak": rh[peak_i],
                "t0": temp[s],
                "t_rise": np.nanmax(t_seg) - temp[s],
                "t_peak_min": int(np.nanargmax(t_seg)) * 5,
                "half_min": None if decay is None else (decay - peak_i) * 5,
                "abs_rise": absolute_humidity(temp[peak_i], rh[peak_i])
                - absolute_humidity(temp[s], base),
                "others": {
                    n: np.nanmax(v[s : s + hour]) - v[s] for n, v in others.items()
                },
            }
            events.append(row)
            i = peak_i + hour
        print(f"{bath}: {len(events)} showers in {args.days} days")
        if not events:
            print()
            continue
        print(
            f"  {'local start':<17}{'RH':>12}{'abs g/m3':>10}{'temp rise':>10}"
            f"{'at min':>7}{'half min':>9}  neighbours (temp rise in the hour)"
        )
        for e in events:
            half = "-" if e["half_min"] is None else f"{e['half_min']}"
            nb = ", ".join(f"{n} {v:+.2f}" for n, v in e["others"].items())
            print(
                f"  {e['when'].astimezone(tz):%a %m-%d %H:%M}"
                f"{e['rh0']:>6.0f}->{e['rh_peak']:<4.0f}{e['abs_rise']:>+10.1f}"
                f"{e['t_rise']:>+10.2f}{e['t_peak_min']:>7}{half:>9}  {nb}"
            )
        abs_rise = np.median([e["abs_rise"] for e in events])
        t_rise = np.median([e["t_rise"] for e in events])
        latent = abs_rise * AIR_VOLUME * 2.45 / 3600.0  # kWh
        sensible = t_rise * AIR_VOLUME * AIR_HEAT / 3600.0
        print(
            f"  median: humidity +{abs_rise:.1f} g/m3, temperature +{t_rise:.2f} C; "
            f"in {AIR_VOLUME:g} m3 of air that is about {latent * 1000:.0f} Wh latent "
            f"and {sensible * 1000:.1f} Wh sensible (air only)\n"
        )


if __name__ == "__main__":
    main()
