"""Regress every room's temperature change on the things that drive it.

For each room sensor, on fixed time bins (default 30 minutes)::

    dT/dt = k * (T_out - T_room)        envelope loss to the outside (k = 1/tau)
          + h_z * (heat call in zone z)   for z1..z4, as a fraction of the bin
          + s * sin(sun elevation)        daytime only, a solar-gain proxy
          + p * (whole-house power, kW)   electrical use turned into heat
          + c

The fan-only call is left out: the union of the zones' fan calls covers essentially
all the time, so it cannot be told apart from the constant. All rates are in
degrees C per hour. The four zone terms show which zone's
heating each room really responds to (its own zone and the leakage into the
others), so they also reveal which zone a sensor belongs to. Ordinary least
squares with standard errors; ``*`` marks coefficients more than two standard
errors from zero. An exploratory fit for hypotheses 04, 05, 06, 11, 13 and 14,
not a final model.

Usage::

    uv run python scripts/regress_rooms.py --days 10 --bin 30
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import math
import os
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env, real_entity

from custom_components.home_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.home_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.home_thermal_lab.hvac import Run, runs_from_states
from custom_components.home_thermal_lab.solar import solar_elevation_degrees

OUTDOOR = "sensor.edmonton_temperature"
POWER = "sensor.eagle_00bb9c_power_demand"
ZONES = ["z1", "z2", "z3", "z4"]
ROOMS = {  # placeholders map to real ids through HA_ENTITY_ALIASES in .env
    "Z1 kitchen": "sensor.z1_temperature",
    "Z2 basement": "sensor.z2_temperature",
    "Z3 master": "sensor.z3_temperature",
    "Z4 office": "sensor.z4_temperature",
    "W bedroom": "sensor.w_bedroom_thermostat_temperature",
    "S basement": "sensor.s_basement_bedroom_temperature",
    "N bedroom": "sensor.n_bedroom_temperature",
    "NE basement": "sensor.ne_basement_bedroom_temp_humidity_temperature",
    "SE basement": "sensor.se_basement_bedroom_temp_humidity_temperature",
    "Upstairs bath": "sensor.upstairs_bathroom_temp_humidity_sensor_temperature",
    "Office sensor": "sensor.multisensor_6_air_temperature",
    "Office AQ": "sensor.office_office_air_quality_temperature",
}
ROOMS = {name: real_entity(entity) for name, entity in ROOMS.items()}
TERMS = ["k_out", "h_z1", "h_z2", "h_z3", "h_z4", "sun", "kW", "const"]


def _bin_means(readings, start, bins, width):
    """Average readings into bins; ``nan`` where a bin has none."""
    sums = np.zeros(bins)
    counts = np.zeros(bins)
    for r in readings:
        i = int((r.time.replace(tzinfo=UTC) - start) / width)
        if 0 <= i < bins:
            sums[i] += r.temperature
            counts[i] += 1
    with np.errstate(invalid="ignore"):
        return np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)


def _overlap_fraction(runs: list[Run], start, bins, width):
    """Fraction of each bin covered by ``runs``."""
    out = np.zeros(bins)
    seconds = width.total_seconds()
    for run in runs:
        first = max(int((run.start - start) / width), 0)
        last = min(int((run.end - start) / width), bins - 1)
        for i in range(first, last + 1):
            lo = start + i * width
            hi = lo + width
            overlap = (min(run.end, hi) - max(run.start, lo)).total_seconds()
            if overlap > 0:
                out[i] += overlap / seconds
    return np.clip(out, 0.0, 1.0)


def _ols(x: np.ndarray, y: np.ndarray):
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    dof = max(len(y) - x.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    cov = sigma2 * np.linalg.pinv(x.T @ x)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else float("nan")
    return beta, se, r2


def _cell(value: float, se: float) -> str:
    star = "*" if se > 0 and abs(value) > 2 * se else " "
    return f"{value:+7.2f}{star}"


def main() -> None:
    """Fit and print one row per room."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--bin", type=int, default=30, help="minutes")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0

    entities = [OUTDOOR, POWER, *ROOMS.values()]
    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, entities, start, end, period="5minute"
        )
    )
    missing = [e for e in entities if e not in stats]
    if missing:
        print("no 5-minute statistics for:", ", ".join(missing), file=sys.stderr)
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    power = _bin_means(stats.get(POWER, []), start, bins, width)

    climate = {
        z: fetch_states(
            args.ha_url, token, f"climate.{z}", start, end, with_attributes=True
        )
        for z in ZONES
    }
    heat = {
        z: _overlap_fraction(
            runs_from_states(climate[z], end, {"heating"}, "hvac_action"),
            start,
            bins,
            width,
        )
        for z in ZONES
    }
    fan_runs = [
        r
        for z in ZONES
        for r in runs_from_states(climate[z], end, {"fan"}, "hvac_action")
    ]
    fan = _overlap_fraction(fan_runs, start, bins, width)
    mids = [start + (i + 0.5) * width for i in range(bins)]
    sun = np.array(
        [
            max(math.sin(math.radians(solar_elevation_degrees(m, lat, lon))), 0.0)
            for m in mids
        ]
    )

    print(
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; "
        f"heat-call coverage z1..z4: "
        + " ".join(f"{h.mean():.0%}" for h in heat.values())
        + f"; fan {fan.mean():.0%}\n"
    )
    print(
        f"{'room':<16}{'n':>5}{'R2':>6}  "
        + "".join(f"{t:>9}" for t in TERMS)
        + "  tau h"
    )
    for name, entity in ROOMS.items():
        room = _bin_means(stats.get(entity, []), start, bins, width)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        columns = [
            t_out - room,
            heat["z1"],
            heat["z2"],
            heat["z3"],
            heat["z4"],
            sun,
            power,
            np.ones(bins),
        ]
        x = np.column_stack(columns)
        ok = ~np.isnan(x).any(axis=1) & ~np.isnan(y)
        if ok.sum() < 3 * len(TERMS):
            print(f"{name:<16}{int(ok.sum()):>5}  too little data")
            continue
        beta, se, r2 = _ols(x[ok], y[ok])
        tau = 1.0 / beta[0] if beta[0] > 0 else float("nan")
        print(
            f"{name:<16}{int(ok.sum()):>5}{r2:>6.2f}  "
            + "".join(f"{_cell(b, s):>9}" for b, s in zip(beta, se, strict=True))
            + f"  {tau:5.0f}"
        )
    print("\nunits: C per hour per unit of each term; * = beyond 2 standard errors")


if __name__ == "__main__":
    main()
