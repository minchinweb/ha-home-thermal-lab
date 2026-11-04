"""Backtest the zone model with a simulated thermostat (hypothesis 16, revised).

The day forecast of the forecast sensor, run on history. At local midnight of
every test day, using only data from before it, each predictor forecasts the
96 quarter-hours of the day ahead in each zone (z1 to z4, the zone's room):

* **A persistence**: the midnight temperature, held.
* **C profile**: the mean of the previous 7 days at each quarter-hour.
* **D profile + offset**: C plus the gap at midnight, fading with a time
  constant chosen on the training days (``routine.forecast_d``).
* **RM**: the one-zone model (``dT/dt = a (outdoor - T) + c + g light``) fitted
  on hour-long block rates and refined on 3 hour simulated paths, with the
  thermostat simulated (heating rate ``h`` learned from the calls; heat below
  setpoint - deadband, off at the setpoint).
* **RN meas**: RM with the neighbour terms (``n (neighbour - T) + x other``:
  the neighbours' temperature and furnace calls, hypotheses 06 and 10),
  simulated alone with the neighbours *as measured*: an upper bound, since the
  neighbours' day is not known at midnight.
* **RN house**: the same models, the four zones simulated together
  (``shadow.simulate_house``), so each zone's neighbours are forecast too.
* **RNL house**: RN house with the furnace's delivery lag (``lag``, chosen per
  zone by ``learn.fit_furnace_lag``: the start lag and overshoot of 13).
* **RNL yday**: RNL house with yesterday's setpoints repeated in every zone
  (what a live forecast knows).
* **H house** and **H yday**: the hybrid (``routine.hybrid``): D, plus RNL's
  path with the day's weather and setpoints minus RNL's path with the typical
  day's (the previous 7 days' mean at each quarter-hour).

All but RNL yday and H yday follow the day's recorded setpoints, standing in
for a known schedule.

``--neighbours house`` (default) takes the mean of the other three zones as a
zone's neighbour and the sum of their calls as ``other``; ``--neighbours z4``
takes z4 (the zone that heats) alone for z1 to z3.

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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
import warnings
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
    FURNACE_LAGS,
    NoHeatFit,
    ZoneData,
    fit_furnace_lag,
    fit_heat_rate,
    fit_no_heat,
    heated_error,
    heated_starts,
    model_of,
    problem,
    refine_multistep,
)
from custom_components.home_thermal_lab.routine import (
    fill,
    fit_offset_tau,
    forecast_d,
    hybrid,
    typical,
)
from custom_components.home_thermal_lab.shadow import (
    HouseZone,
    Thermostat,
    simulate_heated,
    simulate_house,
)
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
    "RM",
    "RN meas",
    "RN house",
    "RNL house",
    "RNL yday",
    "H house",
    "H yday",
]


def _lst(a: np.ndarray) -> list:
    return [None if np.isnan(v) else float(v) for v in a]


def _profile(room: np.ndarray, start: int) -> np.ndarray:
    days = [room[start - k * PER_DAY : start - (k - 1) * PER_DAY] for k in range(1, 8)]
    days = [d for d in days if len(d) == PER_DAY]
    if not days:
        return np.full(PER_DAY, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
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


def _offset_pred(room: np.ndarray, o: int, d: int, train: int) -> np.ndarray:
    """Predictor D from midnight ``o`` (day ``d``)."""
    prof = _profile(room, o)
    origins = [k * PER_DAY for k in range(max(1, d - train), d) if k * PER_DAY > 0]
    tau = _offset_tau(room, origins)
    lead = np.arange(PER_DAY) * 0.25
    return prof + (room[o - 1] - prof[-1]) * np.exp(-lead / tau)


def _rc(
    model, room, t_out, light, heat_sp, o, deadband, now_on, neighbour=None, other=None
):
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
        neighbour=None if neighbour is None else list(np.nan_to_num(neighbour)),
        other=None if other is None else list(other),
    )
    return np.array(path[1:])


def _neighbour_series(rooms: dict, heats: dict, zone: str, mode: str):
    """The zone's neighbour temperature and other zones' calls, per bin.

    ``house``: the mean of the other zones' rooms, and the sum of their calls.
    ``z4``: z4's room and calls (for z4 itself, as ``house``).
    ``hub``: the zone whose furnace calls ran longest is the hub; every other
    zone's neighbour is the hub, and the hub's are all the others (what the
    integration does when no neighbours are configured; here, as ``z4``).
    """
    others = [z for z in rooms if z != zone]
    if mode == "hub":
        hub = max(rooms, key=lambda z: float(np.nansum(heats[z])))
        near = others if zone == hub else [hub]
    else:
        near = ["z4"] if mode == "z4" and zone != "z4" else others
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        temp = np.nanmean(np.vstack([rooms[z] for z in near]), axis=0)
    calls = np.sum(np.vstack([heats[z] for z in near]), axis=0)
    return temp, calls, near


def _score(scores, zone_scores, m, actual, pred) -> None:
    err = actual - pred
    if np.isnan(err).all():
        return
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        whole = float(np.sqrt(np.nanmean(err**2)))
        early = float(np.sqrt(np.nanmean(err[:24] ** 2)))
        late = float(np.sqrt(np.nanmean(err[24:] ** 2)))
    scores[m]["all"].append(whole)
    scores[m]["0-5"].append(early)
    scores[m]["6-23"].append(late)
    zone_scores[m].append(whole)


def _fit(data: ZoneData) -> NoHeatFit | None:
    """Hour-block fit, refined on 3 hour paths when it is physical."""
    f = fit_no_heat(
        data.room,
        data.outdoor,
        data.light,
        data.heating,
        data.hours,
        block=4,
        neighbour=data.neighbour,
        other=data.other,
    )
    if f is not None and problem(f) is None:
        return refine_multistep(f, data)
    return f


def _describe(f: NoHeatFit | None) -> str:
    if f is None:
        return "none"
    return (
        f"{f.method} a {f.a:.4f} c {f.c:.3f} g {f.g:.6f} n {f.n:.4f} x {f.x:.3f}, "
        f"problem {problem(f)}"
    )


def _issued_outdoor(directory, measured, start, bins, width):
    """Each test day's outdoor temperature as forecast at its midnight.

    Reads the outdoor records of the forecast archive (``archive.py``): for each
    day, the last forecast issued at or before the day's first bin, which gives
    the temperature of the hour each bin falls in. Bins it does not cover keep
    the measured temperature.
    """
    from custom_components.home_thermal_lab import archive

    records = sorted(
        archive.read(
            directory,
            "outdoor",
            start - timedelta(days=2),
            start + bins * width,
        ),
        key=lambda r: archive.parse_instant(r["at"]),
    )
    out = measured.copy()
    used = 0
    for first in range(0, bins, PER_DAY):
        issue = start + first * width
        before = [r for r in records if archive.parse_instant(r["at"]) <= issue]
        if not before:
            continue
        by_end = {
            archive.parse_instant(h[0]): h[1]
            for h in before[-1]["hours"]
            if h[1] is not None
        }
        for i in range(first, min(first + PER_DAY, bins)):
            mid = start + (i + 0.5) * width
            end = mid.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            if end in by_end:
                out[i] = by_end[end]
                used += 1
    print(f"issued outdoor forecasts used for {used} of {bins} bins")
    return out


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
    p.add_argument(
        "--neighbours",
        choices=["house", "z4", "hub"],
        default="hub",
        help="the RN zones' neighbours: the other zones, z4, or the zone that "
        "heats most (for it, the others)",
    )
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    p.add_argument(
        "--archive",
        type=Path,
        help="a copy of the forecast archive directory; the outdoor forecast for "
        "each test day is then the one issued at its midnight, not the measured "
        "temperature (days with no record there fall back to measured)",
    )
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
        f"deadband {args.deadband:g} C; neighbours {args.neighbours}; "
        "weather measured\n"
    )

    zones = list(ZONE_ROOM)
    rooms, heats, setpoints, lights = {}, {}, {}, {}
    for zone, room_name in ZONE_ROOM.items():
        states = fetch_states(
            args.ha_url, token, f"climate.{zone}", start, end, with_attributes=True
        )
        heats[zone] = _overlap_fraction(
            runs_from_states(states, end, {"heating"}, "hvac_action"),
            start,
            bins,
            width,
        )
        setpoints[zone] = _setpoints(states, start, bins, width)
        rooms[zone] = _bin_means(stats.get(ROOMS[room_name], []), start, bins, width)
        spec = WINDOWS.get(room_name)
        lights[zone] = (
            np.nan_to_num(
                _room_light(
                    spec, held, azimuth, elevation, args.rotation, args.pitch, block
                )
            )
            if spec
            else np.zeros(bins)
        )
    near = {z: _neighbour_series(rooms, heats, z, args.neighbours) for z in zones}
    scores: dict[str, dict[str, list]] = {
        m: {"all": [], "0-5": [], "6-23": []} for m in METHODS
    }
    by_zone: dict[str, dict[str, list]] = {z: {m: [] for m in METHODS} for z in zones}
    notes = []
    index = {z: i for i, z in enumerate(zones)}
    out_list = _lst(t_out)
    t_fc = t_out
    if args.archive is not None:
        t_fc = _issued_outdoor(args.archive, t_out, start, bins, width)
    for d in range(args.first, args.days):
        o = d * PER_DAY
        lo = max(0, o - args.train * PER_DAY)
        plans, ydays, usual_sp, now_on = {}, {}, {}, {}
        models_n, models_l, offsets = {}, {}, {}
        for zone in zones:
            room, heat, setpoint, light = (
                rooms[zone],
                heats[zone],
                setpoints[zone],
                lights[zone],
            )
            neighbour, other, _ = near[zone]
            data = ZoneData(
                _lst(room[lo:o]),
                _lst(t_out[lo:o]),
                list(light[lo:o]),
                list(heat[lo:o]),
                hours,
            )
            data_n = ZoneData(
                data.room,
                data.outdoor,
                data.light,
                data.heating,
                hours,
                neighbour=_lst(neighbour[lo:o]),
                other=list(other[lo:o]),
                setpoint=_lst(setpoint[lo:o]),
            )
            fit = fit_no_heat(*_fit_args(data), block=4)
            fit_rm = (
                refine_multistep(fit, data)
                if fit is not None and problem(fit) is None
                else fit
            )
            fit_n = _fit(data_n)
            room_l = _lst(room)
            origins = [k * PER_DAY for k in range(max(1, d - args.train), d)]
            tau = fit_offset_tau(room_l, origins, PER_DAY, hours)
            offsets[zone] = np.array(
                [
                    np.nan if v is None else v
                    for v in forecast_d(room_l, o, PER_DAY, hours, tau)
                ]
            )
            if np.isnan(setpoint).all():
                sp_day = np.full(PER_DAY, -50.0)  # thermostat off: never heats
                yday_sp = usual = sp_day
            else:
                known = setpoint[lo:o][~np.isnan(setpoint[lo:o])]
                fallback = float(np.mean(known) if known.size else np.nanmean(setpoint))
                sp_day = np.nan_to_num(setpoint[o : o + PER_DAY], nan=fallback)
                yday = setpoint[o - PER_DAY : o]
                yday_sp = (
                    np.nan_to_num(yday, nan=fallback)
                    if not np.isnan(yday).all()
                    else None
                )
                usual = np.array(fill(typical(_lst(setpoint), o, PER_DAY), fallback))
            plans[zone], ydays[zone], usual_sp[zone] = sp_day, yday_sp, usual
            now_on[zone] = heat[o - 1] > 0
            models_n[zone] = models_l[zone] = None
            if fit_n is not None:
                m = model_of(fit_n, fit_heat_rate(model_of(fit_n), data_n))
                models_n[zone] = m
                lag_h, _ = fit_furnace_lag(m, data_n, args.deadband)
                models_l[zone] = replace(m, lag=lag_h)
            if d == args.days - 1:
                notes.append(f"{zone}: RM   {_describe(fit_rm)}")
                notes.append(f"{zone}: RN   {_describe(fit_n)}")
                if models_l[zone] is not None:
                    notes.append(
                        f"{zone}: h {models_l[zone].h:.2f} C/h, "
                        f"furnace lag {models_l[zone].lag:g} h, offset tau {tau:g} h"
                    )
                    starts = heated_starts(data_n, 24, 8)
                    errs = [
                        heated_error(
                            replace(models_l[zone], lag=v),
                            data_n,
                            starts,
                            24,
                            args.deadband,
                        )
                        for v in FURNACE_LAGS
                    ]
                    notes.append(
                        f"{zone}: 6 h heated-path RMSE by lag "
                        + ", ".join(
                            f"{v:g} h {e:.3f}"
                            for v, e in zip(FURNACE_LAGS, errs, strict=True)
                            if e is not None
                        )
                    )

            actual = room[o : o + PER_DAY]
            if np.isnan(actual).all() or np.isnan(room[o - 1]):
                continue
            preds = {
                "A persist": np.full(PER_DAY, room[o - 1]),
                "C profile": _profile(room, o),
                "D +offset": offsets[zone],
            }
            if fit_rm is not None:
                model = model_of(fit_rm, fit_heat_rate(model_of(fit_rm), data))
                preds["RM"] = _rc(
                    model, room, t_fc, light, sp_day, o, args.deadband, now_on[zone]
                )
            if models_n[zone] is not None:
                preds["RN meas"] = _rc(
                    models_n[zone],
                    room,
                    t_fc,
                    light,
                    sp_day,
                    o,
                    args.deadband,
                    now_on[zone],
                    neighbour[o : o + PER_DAY],
                    other[o : o + PER_DAY],
                )
            for m, pred in preds.items():
                _score(scores, by_zone[zone], m, actual, pred)

        # The zones together: each one's neighbours simulated, not measured.
        if (
            any(models_n[z] is None for z in zones)
            or any(np.isnan(rooms[z][o - 1]) for z in zones)
            or np.isnan(t_fc[o : o + PER_DAY]).any()
        ):
            continue
        day_out = list(t_fc[o : o + PER_DAY])
        usual_out = fill(typical(out_list, o, PER_DAY), float(np.nanmean(t_out[lo:o])))

        def house(models, plan, outdoor, light_of, o=o, now_on=now_on):
            zs = [
                HouseZone(
                    models[z],
                    float(rooms[z][o - 1]),
                    light_of(z),
                    Thermostat(list(plan[z]), args.deadband, now_on[z]),
                    neighbours=tuple(index[m] for m in near[z][2]),
                    others=tuple(index[m] for m in near[z][2]),
                )
                for z in zones
            ]
            return [path for path, _ in simulate_house(zs, outdoor, hours)]

        def today_light(z, o=o):
            return list(lights[z][o : o + PER_DAY])

        def usual_light(z, o=o):
            return fill(typical(list(lights[z]), o, PER_DAY), 0.0)

        runs = {
            "RN house": house(models_n, plans, day_out, today_light),
            "RNL house": house(models_l, plans, day_out, today_light),
        }
        usual_run = house(models_l, usual_sp, usual_out, usual_light)
        runs["H house"] = [
            hybrid(_lst(offsets[z]), today, usual)
            for z, today, usual in zip(zones, runs["RNL house"], usual_run, strict=True)
        ]
        if all(ydays[z] is not None for z in zones):
            runs["RNL yday"] = house(models_l, ydays, day_out, today_light)
            runs["H yday"] = [
                hybrid(_lst(offsets[z]), today, usual)
                for z, today, usual in zip(
                    zones, runs["RNL yday"], usual_run, strict=True
                )
            ]
        for name, paths in runs.items():
            for z, path in zip(zones, paths, strict=True):
                actual = rooms[z][o : o + PER_DAY]
                if np.isnan(actual).all():
                    continue
                if name.startswith("H"):
                    pred = np.array([np.nan if v is None else v for v in path])
                else:
                    pred = np.array(path[1:])
                _score(scores, by_zone[z], name, actual, pred)

    print(f"{'predictor':<11}{'all':>7}{'h 0-5':>8}{'h 6-23':>8}{'n':>5}")
    for m in METHODS:
        s = scores[m]
        if not s["all"]:
            continue
        print(
            f"{m:<11}{np.mean(s['all']):>7.3f}{np.mean(s['0-5']):>8.3f}"
            f"{np.mean(s['6-23']):>8.3f}{len(s['all']):>5}"
        )
    print("\nby zone (RMSE over the day, mean of test days; n in brackets)")
    print(f"{'zone':<6}" + "".join(f"{m:>11}" for m in METHODS))
    for zone, zs in by_zone.items():
        print(
            f"{zone:<6}"
            + "".join(
                f"{np.mean(zs[m]):>7.3f}({len(zs[m]):>2})" if zs[m] else f"{'-':>11}"
                for m in METHODS
            )
        )
    print()
    for n in notes:
        print(n)


def _fit_args(data: ZoneData):
    return data.room, data.outdoor, data.light, data.heating, data.hours


if __name__ == "__main__":
    main()
