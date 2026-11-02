"""Predict each room's temperature for the coming day (hypothesis 16).

A rolling-origin backtest. At local midnight of every test day, using only data
from before that moment, predictors forecast the 24 hourly room temperatures of
the day ahead:

* **A persistence**: the last hour's temperature, held.
* **B yesterday**: the same hours as the day before.
* **C profile**: the mean of the previous 7 days at each hour.
* **D profile + offset**: C plus the gap between now and the profile at midnight,
  decaying with a time constant tau fitted per room on earlier days.
* **E + outdoor**: D plus a term for the accumulated difference between that
  day's outdoor temperature and the profile's.
* **F + sun**: E plus the accumulated difference in sunlight on the room's
  windows and roof faces (see ``scripts/solar_windows.py`` for the layout; rooms
  without a layout get no sun term). Light is unshaded.
* **G + shaded sun**: F with a fixed tree-and-house horizon: beam light is cut
  when the sun is below ``--horizon`` degrees and between 120 and 210 degrees of
  azimuth (the south-east to south block found in ``scripts/horizon_profile.py``).

Outdoor temperature and sunlight are the *measured* values, as if the forecast
were perfect, so E to G show the most weather information can add; a real
forecast would do a little worse. The thermostat setpoint is deliberately not an
input: it is what this prediction is meant to produce (hypothesis 17).

Each score is the RMSE in C over the 24 hours, averaged over test days. the owner's
office and the office air-quality sensor are one room. The first test day is
the 10th day of data, and tau and the coefficients are fit on all earlier days
only.

Usage::

    uv run python scripts/predict_day.py --days 40
"""

from __future__ import annotations

import argparse
import asyncio
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
from regress_rooms import OUTDOOR, ROOMS, _bin_means
from solar_windows import WINDOWS

from custom_components.house_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_time_zone,
)
from custom_components.house_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.house_thermal_lab.irradiance import (
    fetch_irradiance,
    light_on_surfaces,
)
from custom_components.house_thermal_lab.solar import (
    solar_azimuth_degrees,
    solar_elevation_degrees,
)

TRAIL = 7
FIRST_TEST = 10
MIN_TRAIN = 3
TAUS = [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
SAME_ROOM = ("Office sensor", "Office AQ")
HOURS = np.arange(24)
METHODS = [
    "A persist",
    "B yesterday",
    "C profile",
    "D +offset",
    "E +outdoor",
    "F +sun",
    "G +shaded",
]
SUN_ROOM = {"Office": "Z4 office"}  # merged series -> WINDOWS key


def _trailing(values: np.ndarray, d: int, lag: int = 0) -> np.ndarray:
    """Mean over the TRAIL days before day ``d - lag`` (NaN-safe)."""
    block = values[max(d - lag - TRAIL, 0) : d - lag]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return (
            np.nanmean(block, axis=0)
            if len(block)
            else np.full(values.shape[1], np.nan)
        )


def _day_inputs(room: np.ndarray, extras: list[np.ndarray], d: int):
    """What is known at midnight of day ``d`` (and the weather of day ``d``)."""
    profile = _trailing(room, d)
    start = room[d - 1, 23]
    base_start = _trailing(room[:, 23:24], d, lag=1)[0]
    cums = [np.cumsum(x[d] - _trailing(x, d)) for x in extras]
    return profile, start, base_start, cums


def _fit(room, extras, days, tau):
    """Least-squares coefficients for the extras on the given days; and the SSE."""
    rows, targets = [], []
    for j in days:
        profile, start, base_start, cums = _day_inputs(room, extras, j)
        target = room[j] - profile - (start - base_start) * np.exp(-HOURS / tau)
        ok = ~np.isnan(target)
        for c in cums:
            ok &= ~np.isnan(c)
        if not ok.any():
            continue
        targets.append(target[ok])
        rows.append(np.column_stack([c[ok] for c in cums]) if cums else None)
    if not targets:
        return np.zeros(len(extras)), np.inf
    y = np.concatenate(targets)
    if extras:
        x = np.vstack(rows)
        k, *_ = np.linalg.lstsq(x, y, rcond=None)
        resid = y - x @ k
    else:
        k, resid = np.zeros(0), y
    return k, float(np.sum(resid**2))


def _predict(room, extras, d, tau, k):
    profile, start, base_start, cums = _day_inputs(room, extras, d)
    pred = profile + (start - base_start) * np.exp(-HOURS / tau)
    for coef, c in zip(k, cums, strict=True):
        pred = pred + coef * np.nan_to_num(c)
    return pred


def _best(room, extras, train):
    """Pick tau on the training days; return (tau, coefficients)."""
    tau = min(TAUS, key=lambda t: _fit(room, extras, train, t)[1])
    return tau, _fit(room, extras, train, tau)[0]


def _room_light(spec, held, azimuth, elevation, rotation, pitch, block):
    """Hourly light on a room windows and roof faces (W/m2, summed).

    ``block`` is None for unshaded, else a function (azimuth, elevation) that
    says whether the beam is blocked.
    """
    roofs = [(face, pitch if tilt is None else tilt) for face, tilt in spec["roof"]]
    total = np.zeros(len(held))
    for i, h in enumerate(held):
        if h is None:
            total[i] = np.nan
            continue
        shaded = block is not None and block(azimuth[i], elevation[i])
        total[i] = light_on_surfaces(
            h, azimuth[i], elevation[i], spec["walls"], roofs, rotation, shaded
        )
    return total


def main() -> None:
    """Run the backtest and print the table."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=40)
    p.add_argument("--rotation", type=float, default=10.4)
    p.add_argument("--pitch", type=float, default=45.0)
    p.add_argument("--horizon", type=float, default=18.0, help="degrees")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    lat, lon = fetch_home_position(args.ha_url, token)
    midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (midnight - timedelta(days=args.days)).astimezone(UTC)
    end = midnight.astimezone(UTC)
    width = timedelta(hours=1)
    bins = args.days * 24

    stats = asyncio.run(
        fetch_statistics_from_url(
            args.ha_url,
            token,
            [OUTDOOR, *ROOMS.values()],
            start,
            end,
            period="hour",
        )
    )

    def hourly(entity: str) -> np.ndarray:
        series = _bin_means(stats.get(entity, []), start, bins, width)
        return series.reshape(args.days, 24)

    out = hourly(OUTDOOR)
    rooms = {name: hourly(e) for name, e in ROOMS.items()}
    pair = np.stack([rooms.pop(n) for n in SAME_ROOM])
    count = (~np.isnan(pair)).sum(axis=0)
    rooms["Office"] = np.where(
        count > 0, np.nansum(pair, axis=0) / np.maximum(count, 1), np.nan
    )

    by_end = {r.time: r for r in fetch_irradiance(lat, lon, args.days + 2)}
    mids = [start + (i + 0.5) * width for i in range(bins)]
    elevation = np.array([solar_elevation_degrees(m, lat, lon) for m in mids])
    azimuth = np.array([solar_azimuth_degrees(m, lat, lon) for m in mids])
    held = [
        by_end.get(m.replace(minute=0, second=0, microsecond=0) + width) for m in mids
    ]

    def block(az: float, el: float) -> bool:
        return 120.0 <= az < 210.0 and el < args.horizon

    light = {}
    for name in rooms:
        spec = WINDOWS.get(SUN_ROOM.get(name, name))
        if spec is None:
            continue
        args_light = (held, azimuth, elevation, args.rotation, args.pitch)
        light[name] = (
            _room_light(spec, *args_light, None).reshape(args.days, 24),
            _room_light(spec, *args_light, block).reshape(args.days, 24),
        )

    print(
        f"{args.days} local days to {midnight:%Y-%m-%d} ({tz.key}); test days "
        f"{FIRST_TEST} to {args.days - 1}; weather measured, standing in for a "
        "perfect forecast\n"
    )
    print(f"{'room':<14}{'days':>5}" + "".join(f"{m:>12}" for m in METHODS))
    totals = {m: [] for m in METHODS}
    lead = {m: ([], []) for m in METHODS}
    for name, room in rooms.items():
        have = int((~np.isnan(room).all(axis=1)).sum())
        if have < 18:
            print(f"{name:<14}  too little data ({have} of {args.days} days)")
            continue
        scores = {m: [] for m in METHODS}
        has_sun = name in light
        for d in range(FIRST_TEST, args.days):
            if np.isnan(room[d]).all() or np.isnan(room[d - 1, 23]):
                continue
            train = [j for j in range(TRAIL, d) if not np.isnan(room[j]).all()]
            profile, start_t, base_start, _ = _day_inputs(room, [], d)
            if np.isnan(profile).any() or np.isnan(base_start):
                continue
            if len(train) < MIN_TRAIN:
                continue
            feats = {
                "D +offset": [],
                "E +outdoor": [out],
                "F +sun": [out, light[name][0]] if has_sun else [out],
                "G +shaded": [out, light[name][1]] if has_sun else [out],
            }
            preds = {
                "A persist": np.full(24, start_t),
                "B yesterday": room[d - 1],
                "C profile": profile,
            }
            for m, extras in feats.items():
                tau, k = _best(room, extras, train)
                preds[m] = _predict(room, extras, d, tau, k)
            if any(np.isnan(v).any() for v in preds.values()):
                continue
            for m, pred in preds.items():
                err = room[d] - pred
                if np.isnan(err).all():
                    continue
                scores[m].append(np.sqrt(np.nanmean(err**2)))
                lead[m][0].append(np.sqrt(np.nanmean(err[:6] ** 2)))
                lead[m][1].append(np.sqrt(np.nanmean(err[6:] ** 2)))
        n = len(scores["E +outdoor"])
        if n == 0:
            print(f"{name:<14}  no usable test days")
            continue
        row = f"{name:<14}{n:>5}"
        for m in METHODS:
            v = float(np.mean(scores[m][:n]))
            totals[m].append(v)
            row += f"{v:>12.2f}"
        row += "" if has_sun else "   (no window layout: F, G = E)"
        print(row)
    print(
        f"{'mean of rooms':<19}"
        + "".join(f"{np.nanmean(totals[m]):>12.3f}" for m in METHODS)
    )
    print(f"\n{'mean RMSE by lead time':<26}" + "".join(f"{m:>12}" for m in METHODS))
    for label, i in (("hours 0-5", 0), ("hours 6-23", 1)):
        print(
            f"  {label:<24}"
            + "".join(f"{np.nanmean(lead[m][i]):>12.3f}" for m in METHODS)
        )


if __name__ == "__main__":
    main()
