"""Thermal momentum of each room (hypotheses 13 and 10).

Three measurements per room sensor:

* **Cool-down time constant.** In stretches with the sun down and no zone
  heating (this bin or the one before), regress the room's rate of change on
  ``outdoor - room``. The slope is ``1/tau`` (tau = C / UA, in hours); the
  intercept is the heat the room gains or loses from elsewhere in the house
  (static flux, hypothesis 10).
* **Wave lag and damping.** Fit a 24 h sinusoid to the whole period for the
  room and for outdoors; report the room's amplitude ratio and how many hours
  it lags the outdoor wave.
* **Heat-up rate.** The room's median warming rate (C/h) in bins where its own
  zone is calling for heat and the sun is down, after removing the cool-down
  term.

If ``--furnace-btu`` (rated input, high stage) is given, whole-house conductance
UA is estimated from the stage-weighted furnace output over the period (heat in
= heat out), and
tau then gives an overall thermal mass C = tau * UA. That is a rough number: it
assumes the house is in balance over the period and ignores solar gain, people
and appliances.

Usage::

    uv run python scripts/thermal_momentum.py --days 10 --bin 15 --furnace-btu 80000
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import math
import os
from pathlib import Path
import statistics
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from furnace_stages import HIGH, LOW, stage_runs
from regress_rooms import (
    OUTDOOR,
    ROOMS,
    ZONES,
    _bin_means,
    _ols,
    _overlap_fraction,
)

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

NIGHT_ELEVATION = -6.0
MIN_BINS = 30
ZONE_OF_ROOM = {
    "Z1 kitchen": "z1",
    "Z2 basement": "z2",
    "NE basement": "z2",
    "SE basement": "z2",
    "S basement": "z2",
    "Z3 master": "z3",
    "N bedroom": "z3",
    "Upstairs bath": "z3",
    "Z4 office": "z4",
    "W bedroom": "z4",
    "Office sensor": "z4",
    "Office AQ": "z4",
}


def _wave(times_h: np.ndarray, values: np.ndarray) -> tuple[float, float] | None:
    """Fit a 24 h sinusoid; return (amplitude, peak hour since the epoch mod 24)."""
    ok = ~np.isnan(values)
    if ok.sum() < 24:
        return None
    w = 2 * math.pi / 24.0
    x = np.column_stack(
        [np.ones(ok.sum()), np.sin(w * times_h[ok]), np.cos(w * times_h[ok])]
    )
    beta, *_ = np.linalg.lstsq(x, values[ok], rcond=None)
    amp = math.hypot(beta[1], beta[2])
    peak = (math.atan2(beta[1], beta[2]) / w) % 24.0
    return amp, peak


def main() -> None:
    """Print one row per room."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--furnace-btu", type=float, default=None, help="high-stage input")
    p.add_argument("--afue", type=float, default=0.95)
    p.add_argument("--low-fraction", type=float, default=0.65, help="low / high input")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    entities = [OUTDOOR, *ROOMS.values()]
    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, entities, start, end, period="5minute"
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in ZONES
    }
    runs = {
        z: runs_from_states(climate[z], end, {"heating"}, "hvac_action") for z in ZONES
    }
    heat = {z: _overlap_fraction(runs[z], start, bins, width) for z in ZONES}
    furnace = _overlap_fraction(
        merge_runs([r for rs in runs.values() for r in rs]), start, bins, width
    )
    mids = [start + (i + 0.5) * width for i in range(bins)]
    night = np.array(
        [solar_elevation_degrees(m, lat, lon) < NIGHT_ELEVATION for m in mids]
    )
    quiet = (furnace == 0) & (np.concatenate([[1.0], furnace[:-1]]) == 0)
    times_h = np.array([(m - start).total_seconds() / 3600.0 for m in mids])
    # hours since midnight UTC of the start day, so lags are comparable
    offset = start.hour + start.minute / 60.0
    times_h = times_h + offset

    out_wave = _wave(times_h, t_out)
    print(
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; "
        f"night+quiet bins: {int((night & quiet).sum())}; "
        f"furnace duty {furnace.mean():.0%}"
    )
    if out_wave:
        print(f"outdoor wave amplitude {out_wave[0]:.1f} C\n")
    print(
        f"{'room':<16}{'n':>5}{'tau h':>8}{'+-':>6}{'static C/h':>12}"
        f"{'amp ratio':>11}{'lag h':>7}{'heat-up C/h':>13}"
    )
    taus = []
    means = []
    for name, entity in ROOMS.items():
        room = _bin_means(stats.get(entity, []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        sel = night & quiet & ~np.isnan(y) & ~np.isnan(diff)
        row = f"{name:<16}{int(sel.sum()):>5}"
        k = None
        if sel.sum() >= MIN_BINS:
            x = np.column_stack([diff[sel], np.ones(sel.sum())])
            b, s, _ = _ols(x, y[sel])
            k = b[0]
            if b[0] > 0 and b[0] > 2 * s[0]:
                tau = 1.0 / b[0]
                row += f"{tau:>8.1f}{tau * s[0] / b[0]:>6.1f}"
                taus.append(tau)
            else:
                row += f"{'n/a':>8}{'':>6}"
            row += f"{b[1]:>+12.2f}"
        else:
            row += f"{'too little':>26}"
        rw = _wave(times_h, room)
        if rw and out_wave and out_wave[1] is not None:
            lag = (rw[1] - out_wave[1]) % 24.0
            if lag > 12:
                lag -= 24.0
            row += f"{rw[0] / out_wave[0]:>11.2f}{lag:>+7.1f}"
        else:
            row += f"{'-':>11}{'-':>7}"
        z = ZONE_OF_ROOM[name]
        own = (heat[z] > 0.9) & night & ~np.isnan(y) & ~np.isnan(diff)
        if own.sum() >= 3 and k is not None:
            gain = y[own] - k * diff[own]
            row += f"{statistics.median(gain):>+13.2f}"
        else:
            row += f"{'-':>13}"
        means.append(np.nanmean(room))
        print(row)

    if args.furnace_btu and taus:
        high_out_kw = args.furnace_btu * args.afue * 0.00029307
        high = _overlap_fraction(
            merge_runs([r for z in ZONES for r in stage_runs(climate[z], end, HIGH)]),
            start,
            bins,
            width,
        )
        low = _overlap_fraction(
            merge_runs([r for z in ZONES for r in stage_runs(climate[z], end, LOW)]),
            start,
            bins,
            width,
        )
        low_only = np.clip(low - high, 0.0, 1.0)
        mean_kw = high_out_kw * (args.low_fraction * low_only.mean() + high.mean())
        indoor = float(np.mean(means))
        outdoor = float(np.nanmean(t_out))
        delta = indoor - outdoor
        if delta > 1:
            ua = mean_kw / delta  # kW per C
            tau = statistics.median(taus)
            print(
                f"\nwhole house: indoor {indoor:.1f} C, outdoor {outdoor:.1f} C, "
                f"mean furnace output {mean_kw:.2f} kW "
                f"(high stage {high_out_kw:.1f} kW)"
                f"\n  UA ~ {ua * 1000:.0f} W/C; median tau {tau:.1f} h"
                f"\n  C ~ {tau * ua:.1f} kWh/C (rough; ignores sun, people, appliances)"
            )


if __name__ == "__main__":
    main()
