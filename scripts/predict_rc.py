"""Backtest the zone model with a simulated thermostat (hypothesis 16, revised).

The day forecast of the forecast sensor, run on history. At local midnight of
every test day, using only data from before it, each predictor forecasts the
96 quarter-hours of the day ahead in each zone (z1 to z4, the zone's room):

* **A persistence**: the midnight temperature, held.
* **C profile**: the mean of the previous 7 days at each quarter-hour.
* **D profile + offset**: C plus the gap at midnight, fading with a time
  constant chosen on the training days (``predict_day.py``'s best predictor).
* **R1 one-step**: the zone model (``dT/dt = a (outdoor - T) + c + g light``)
  fitted on 15 minute rates, with the thermostat simulated (heating rate ``h``
  learned from the calls; heat below setpoint - deadband, off at the setpoint).
* **R4 block**: the same, fitted on hour-long block rates.
* **RM multi-step**: R4 refined on 3 hour simulated paths.
* **RM held**: RM with the midnight setpoint held all day.
* **RM yday**: RM with yesterday's setpoints repeated (what the live forecast
  sensor does: it does not know the thermostat's program). R1, R4 and RM follow
  the day's recorded setpoints, standing in for a known schedule.

Weather is the *measured* value, as if the forecast were perfect (as in
``predict_day.py``). The model is fitted on the ``--train`` days before each
midnight. Scores are RMSE (C) over the day, split into hours 0-5 and 6-23,
averaged over test days. Zones whose fit is unphysical (a <= 0: the z1 and z3
thermostats are off and the rooms are driven by the rest of the house) are
still simulated, and flagged.

Usage::

    uv run python scripts/predict_rc.py --days 14
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from predict_day import _room_light
from regress_rooms import OUTDOOR, ROOMS, _bin_means, _overlap_fraction
from shadow_control import ZONE_ROOM, _setpoints
from solar_windows import WINDOWS

from custom_components.home_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
    fetch_time_zone,
)
from custom_components.home_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.home_thermal_lab.hvac import runs_from_states
from custom_components.home_thermal_lab.irradiance import fetch_irradiance
from custom_components.home_thermal_lab.learn import (
    ZoneData,
    fit_heat_rate,
    fit_no_heat,
    model_of,
    problem,
    refine_multistep,
)
from custom_components.home_thermal_lab.shadow import Thermostat, simulate_heated
from custom_components.home_thermal_lab.solar import (
    solar_azimuth_degrees,
    solar_elevation_degrees,
)

PER_DAY = 96
TAUS = [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
METHODS = [
    "A persist",
    "C profile",
    "D +offset",
    "R1",
    "R4",
    "RM",
    "RM held",
    "RM yday",
]


def _lst(a: np.ndarray) -> list:
    return [None if np.isnan(v) else float(v) for v in a]


def _profile(room: np.ndarray, start: int) -> np.ndarray:
    days = [room[start - k * PER_DAY : start - (k - 1) * PER_DAY] for k in range(1, 8)]
    days = [d for d in days if len(d) == PER_DAY]
    if not days:
        return np.full(PER_DAY, np.nan)
    with np.errstate(all="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(np.vstack(days), axis=0)


def _offset_tau(room: np.ndarray, origins: list[int]) -> float:
    """The fading time of the midnight gap that fits the training days best."""
    lead = np.arange(PER_DAY) * 0.25

    def sse(tau: float) -> float:
        total = 0.0
        for o in origins:
            prof = _profile(room, o)
            gap = room[o - 1] - prof[-1] if not np.isnan(room[o - 1]) else np.nan
            pred = prof + gap * np.exp(-lead / tau)
            err = room[o : o + PER_DAY] - pred
            total += float(np.nansum(err**2))
        return total

    return min(TAUS, key=sse) if origins else 8.0


def _rc(model, room, t_out, light, heat_sp, o, deadband, now_on):
    """Simulate the day from midnight with the thermostat."""
    if any(np.isnan(t_out[o : o + PER_DAY])) or np.isnan(room[o - 1]):
        return np.full(PER_DAY, np.nan)
    stat = Thermostat(list(heat_sp), deadband, now_on)
    path, _ = simulate_heated(
        float(room[o - 1]),
        list(t_out[o : o + PER_DAY]),
        list(light[o : o + PER_DAY]),
        model,
        0.25,
        stat,
    )
    return np.array(path[1:])


def main() -> None:
    """Run the backtest and print the table."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--train", type=int, default=7, help="days of history per fit")
    p.add_argument("--first", type=int, default=4, help="first test day")
    p.add_argument("--deadband", type=float, default=0.1)
    p.add_argument("--rotation", type=float, default=10.4)
    p.add_argument("--pitch", type=float, default=45.0)
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    width = timedelta(minutes=15)
    today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (today - timedelta(days=args.days)).astimezone(UTC)
    end = today.astimezone(UTC)
    bins = int((end - start) / width)
    hours = 0.25

    by_end = {r.time: r for r in fetch_irradiance(lat, lon, args.days + 2)}
    mids = [start + (i + 0.5) * width for i in range(bins)]
    elevation = np.array([solar_elevation_degrees(m, lat, lon) for m in mids])
    azimuth = np.array([solar_azimuth_degrees(m, lat, lon) for m in mids])
    held = [
        by_end.get(m.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        for m in mids
    ]

    def block(az: float, el: float) -> bool:
        return 120.0 <= az < 210.0 and el < 18.0

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url, token, [OUTDOOR, *ROOMS.values()], start, end, period="5minute"
        )
    )
    t_out = _bin_means(stats.get(OUTDOOR, []), start, bins, width)
    print(
        f"{args.days} days to {today:%Y-%m-%d} ({tz}), 15 minute bins; fits on "
        f"{args.train} days before each midnight; first test day {args.first}; "
        f"deadband {args.deadband:g} C; weather measured\n"
    )

    scores: dict[str, dict[str, list]] = {
        m: {"all": [], "0-5": [], "6-23": []} for m in METHODS
    }
    by_zone: dict[str, dict[str, list]] = {}
    notes = []
    for zone, room_name in ZONE_ROOM.items():
        states = fetch_states(
            args.ha_url, token, f"climate.{zone}", start, end, with_attributes=True
        )
        heat = _overlap_fraction(
            runs_from_states(states, end, {"heating"}, "hvac_action"),
            start,
            bins,
            width,
        )
        setpoint = _setpoints(states, start, bins, width)
        room = _bin_means(stats.get(ROOMS[room_name], []), start, bins, width)
        spec = WINDOWS.get(room_name)
        light = (
            np.nan_to_num(
                _room_light(
                    spec, held, azimuth, elevation, args.rotation, args.pitch, block
                )
            )
            if spec
            else np.zeros(bins)
        )
        zone_scores = {m: [] for m in METHODS}
        for d in range(args.first, args.days):
            o = d * PER_DAY
            lo = max(0, o - args.train * PER_DAY)
            data = ZoneData(
                _lst(room[lo:o]),
                _lst(t_out[lo:o]),
                list(light[lo:o]),
                list(heat[lo:o]),
                hours,
            )
            fits = {
                "R1": fit_no_heat(*_fit_args(data), block=1),
                "R4": fit_no_heat(*_fit_args(data), block=4),
            }
            if fits["R4"] is not None and problem(fits["R4"]) is None:
                fits["RM"] = refine_multistep(fits["R4"], data)
            else:
                fits["RM"] = fits["R4"]
            if d == args.days - 1:
                f = fits["RM"]
                notes.append(
                    f"{zone}: last fit {f.method if f else '-'} "
                    + (
                        f"a {f.a:.4f} c {f.c:.3f} g {f.g:.6f}, problem {problem(f)}"
                        if f
                        else "none"
                    )
                )
            actual = room[o : o + PER_DAY]
            if np.isnan(actual).all() or np.isnan(room[o - 1]):
                continue
            prof = _profile(room, o)
            origins = [
                k * PER_DAY for k in range(max(1, d - args.train), d) if k * PER_DAY > 0
            ]
            tau = _offset_tau(room, origins)
            lead = np.arange(PER_DAY) * 0.25
            preds = {
                "A persist": np.full(PER_DAY, room[o - 1]),
                "C profile": prof,
                "D +offset": prof + (room[o - 1] - prof[-1]) * np.exp(-lead / tau),
            }
            now_on = heat[o - 1] > 0
            if np.isnan(setpoint).all():
                sp_day = np.full(PER_DAY, -50.0)  # thermostat off: never heats
            else:
                sp_day = np.nan_to_num(
                    setpoint[o : o + PER_DAY], nan=float(np.nanmean(setpoint))
                )
            for key in ("R1", "R4", "RM"):
                f = fits[key]
                if f is None:
                    continue
                model = model_of(f, fit_heat_rate(model_of(f), data))
                preds[key] = _rc(
                    model, room, t_out, light, sp_day, o, args.deadband, now_on
                )
                if key == "RM":
                    sp0 = setpoint[o - 1]
                    held_sp = np.full(PER_DAY, sp0 if not np.isnan(sp0) else sp_day[0])
                    preds["RM held"] = _rc(
                        model,
                        room,
                        t_out,
                        light,
                        held_sp,
                        o,
                        args.deadband,
                        now_on,
                    )
                    yday = setpoint[o - PER_DAY : o]
                    if len(yday) == PER_DAY and not np.isnan(yday).all():
                        preds["RM yday"] = _rc(
                            model,
                            room,
                            t_out,
                            light,
                            np.nan_to_num(yday, nan=float(np.nanmean(yday))),
                            o,
                            args.deadband,
                            now_on,
                        )
            for m, pred in preds.items():
                err = actual - pred
                if np.isnan(err).all():
                    continue
                with np.errstate(all="ignore"):
                    whole = float(np.sqrt(np.nanmean(err**2)))
                    early = float(np.sqrt(np.nanmean(err[:24] ** 2)))
                    late = float(np.sqrt(np.nanmean(err[24:] ** 2)))
                scores[m]["all"].append(whole)
                scores[m]["0-5"].append(early)
                scores[m]["6-23"].append(late)
                zone_scores[m].append(whole)
        by_zone[zone] = zone_scores

    print(f"{'predictor':<11}{'all':>7}{'h 0-5':>8}{'h 6-23':>8}{'n':>5}")
    for m in METHODS:
        s = scores[m]
        if not s["all"]:
            continue
        print(
            f"{m:<11}{np.mean(s['all']):>7.3f}{np.mean(s['0-5']):>8.3f}"
            f"{np.mean(s['6-23']):>8.3f}{len(s['all']):>5}"
        )
    print("\nby zone (RMSE over the day, mean of test days)")
    print(f"{'zone':<6}" + "".join(f"{m:>11}" for m in METHODS))
    for zone, zs in by_zone.items():
        print(
            f"{zone:<6}"
            + "".join(
                f"{np.mean(zs[m]):>11.3f}" if zs[m] else f"{'-':>11}" for m in METHODS
            )
        )
    print()
    for n in notes:
        print(n)


def _fit_args(data: ZoneData):
    return data.room, data.outdoor, data.light, data.heating, data.hours


if __name__ == "__main__":
    main()
