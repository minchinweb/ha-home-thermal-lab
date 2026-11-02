"""Predict each room's temperature for the coming day (hypothesis 16).

A rolling-origin backtest. At local midnight of every test day, using only data
from before that moment, five predictors forecast the 24 hourly room
temperatures of the day ahead:

* **A persistence**: the last hour's temperature, held.
* **B yesterday**: the same hours as the day before.
* **C profile**: the mean of the previous 7 days at each hour.
* **D profile + offset**: C plus the gap between now and the profile at midnight,
  decaying with a time constant tau fitted per room on earlier days.
* **E profile + offset + outdoor**: D plus a term for the outdoor temperature
  that day compared with the profile's outdoor temperature (a running sum, since
  a room responds to the accumulated difference). The outdoor temperature used
  is the *measured* one, as if the forecast were perfect, so E shows the most that
  weather information can add; a real forecast would do a little worse.

Each score is the RMSE in C over the 24 hours, averaged over test days. the owner's
office and the office air-quality sensor are one room. The first test day is
the 10th day of data, and tau and the outdoor coefficient are fit on all earlier
days only.

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

from custom_components.house_thermal_lab.ha_history import (
    fetch_time_zone,
)
from custom_components.house_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)

TRAIL = 7
FIRST_TEST = 10
MIN_TRAIN = 3
TAUS = [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
SAME_ROOM = ("Office sensor", "Office AQ")
HOURS = np.arange(24)
METHODS = ["A persist", "B yesterday", "C profile", "D +offset", "E +outdoor"]


def _hourly(series_fn, days: int) -> np.ndarray:
    return series_fn().reshape(days, 24)


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


def _features(room: np.ndarray, out: np.ndarray, d: int):
    """Everything known at midnight of day ``d`` plus the outdoor day itself."""
    profile = _trailing(room, d)
    start = room[d - 1, 23]
    base_start = _trailing(room[:, 23:24], d, lag=1)[0]
    out_profile = _trailing(out, d)
    cum_out = np.cumsum(out[d] - out_profile)
    return profile, start, base_start, cum_out


def _fit(room, out, days, tau, with_outdoor):
    """Least-squares outdoor coefficient on the given training days."""
    num = den = 0.0
    for j in days:
        profile, start, base_start, cum_out = _features(room, out, j)
        target = room[j] - profile - (start - base_start) * np.exp(-HOURS / tau)
        ok = ~np.isnan(target) & ~np.isnan(cum_out)
        if not ok.any():
            continue
        if with_outdoor:
            num += float(np.sum(target[ok] * cum_out[ok]))
            den += float(np.sum(cum_out[ok] ** 2))
    k = num / den if (with_outdoor and den > 0) else 0.0
    sse = 0.0
    for j in days:
        profile, start, base_start, cum_out = _features(room, out, j)
        pred = profile + (start - base_start) * np.exp(-HOURS / tau) + k * cum_out
        err = room[j] - pred
        sse += float(np.nansum(err**2))
    return k, sse


def main() -> None:
    """Run the backtest and print the table."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=40)
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    now_local = datetime.now(tz)
    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
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
    out = _hourly(
        lambda: _bin_means(stats.get(OUTDOOR, []), start, bins, width), args.days
    )
    rooms = {
        name: _hourly(
            lambda e=e: _bin_means(stats.get(e, []), start, bins, width), args.days
        )
        for name, e in ROOMS.items()
    }
    pair = np.stack([rooms.pop(n) for n in SAME_ROOM])
    count = (~np.isnan(pair)).sum(axis=0)
    rooms["Office"] = np.where(
        count > 0, np.nansum(pair, axis=0) / np.maximum(count, 1), np.nan
    )

    print(
        f"{args.days} local days to {midnight:%Y-%m-%d} ({tz.key}); test days "
        f"{FIRST_TEST} to {args.days - 1}; outdoor measured, standing in for a "
        "perfect forecast\n"
    )
    print(
        f"{'room':<14}{'days':>5}"
        + "".join(f"{m:>13}" for m in METHODS)
        + "   tau h   k"
    )
    totals = {m: [] for m in METHODS}
    horizon = {m: ([], []) for m in METHODS}
    for name, room in rooms.items():
        if (~np.isnan(room).all(axis=1)).sum() < 18:
            have = int((~np.isnan(room).all(axis=1)).sum())
            print(f"{name:<14}  too little data ({have} of {args.days} days)")
            continue
        scores = {m: [] for m in METHODS}
        taus, ks = [], []
        for d in range(FIRST_TEST, args.days):
            if np.isnan(room[d]).all() or np.isnan(room[d - 1, 23]):
                continue
            train = [j for j in range(TRAIL, d) if not np.isnan(room[j]).all()]
            profile, start_t, base_start, cum_out = _features(room, out, d)
            if np.isnan(profile).any() or np.isnan(base_start):
                continue
            preds = {
                "A persist": np.full(24, start_t),
                "B yesterday": room[d - 1],
                "C profile": profile,
            }
            if len(train) >= MIN_TRAIN:
                best_d = min(TAUS, key=lambda t: _fit(room, out, train, t, False)[1])
                preds["D +offset"] = profile + (start_t - base_start) * np.exp(
                    -HOURS / best_d
                )
                best_e = min(TAUS, key=lambda t: _fit(room, out, train, t, True)[1])
                k, _ = _fit(room, out, train, best_e, True)
                preds["E +outdoor"] = (
                    profile
                    + (start_t - base_start) * np.exp(-HOURS / best_e)
                    + k * np.nan_to_num(cum_out)
                )
                taus.append(best_e)
                ks.append(k)
            else:
                continue
            for m, pred in preds.items():
                err = room[d] - pred
                if np.isnan(err).all() or np.isnan(pred).any():
                    break
                scores[m].append(np.sqrt(np.nanmean(err**2)))
                horizon[m][0].append(np.sqrt(np.nanmean(err[:6] ** 2)))
                horizon[m][1].append(np.sqrt(np.nanmean(err[6:] ** 2)))
        n = len(scores["E +outdoor"])
        if n == 0:
            print(f"{name:<14}  no usable test days")
            continue
        row = f"{name:<14}{n:>5}"
        for m in METHODS:
            v = float(np.mean(scores[m][:n])) if scores[m] else float("nan")
            totals[m].append(v)
            row += f"{v:>13.2f}"
        row += f"{np.median(taus):>8.0f}{np.median(ks):>8.3f}"
        print(row)
    print(
        f"{'mean of rooms':<19}"
        + "".join(f"{np.nanmean(totals[m]):>13.2f}" for m in METHODS)
    )
    print("\nmean RMSE by lead time:           " + "".join(f"{m:>13}" for m in METHODS))
    for label, i in (("hours 0-5", 0), ("hours 6-23", 1)):
        print(
            f"  {label:<31}"
            + "".join(f"{np.nanmean(horizon[m][i]):>13.2f}" for m in METHODS)
        )


if __name__ == "__main__":
    main()
