"""Shadow-mode controller: which furnace calls could have been skipped? (17)

Nothing is switched. For every heating call in each zone, over the recorded
history, it asks: if the furnace had stayed off, would the room have stayed
within ``--tolerance`` of its setpoint over the next ``--horizon`` hours (counting
the sun, the house's own warmth and the outdoor temperature), with at most
``--max-dip`` degree-hours below that band? If so the call is marked "skippable"
and its furnace minutes and estimated energy are totalled.

The no-heat forecast per zone is ``dT/dt = a * (outdoor - room) + c + g * light``,
fitted on the zone's own idle bins (``scripts/predict_day.py`` has the light on
the room's windows and roof). Weather is the measured value, standing in for a
forecast. Because the counterfactual can't be observed, the model is first
checked where it can: from every idle moment it forecasts 1, 2 and 3 hours ahead
and is compared with what happened and with holding the temperature constant.

The setpoint is the thermostat's own (the "wave" target of the component will
replace it later). Energy is the call's minutes in each furnace stage times the
stage output (80 000 BTU input, 95% efficient, low stage ``--low-fraction`` of
high); calls in different zones overlap, so the energy total is an upper bound.

Usage::

    uv run python scripts/shadow_control.py --days 14
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from furnace_stages import HIGH, LOW, _overlap, stage_runs
from predict_day import _room_light
from regress_rooms import OUTDOOR, ROOMS, ZONES, _bin_means, _ols, _overlap_fraction
from solar_windows import WINDOWS

from custom_components.house_thermal_lab.ha_history import (
    fetch_home_position,
    fetch_states,
)
from custom_components.house_thermal_lab.ha_statistics import (
    fetch_statistics_from_url,
)
from custom_components.house_thermal_lab.hvac import Run, runs_from_states
from custom_components.house_thermal_lab.irradiance import fetch_irradiance
from custom_components.house_thermal_lab.solar import (
    solar_azimuth_degrees,
    solar_elevation_degrees,
)

ZONE_ROOM = {
    "z1": "Z1 kitchen",
    "z2": "Z2 basement",
    "z3": "Z3 master",
    "z4": "Z4 office",
}
MIN_BINS = 60


def _setpoints(states: list[dict], start: datetime, bins: int, width: timedelta):
    """Heat setpoint in force at the start of every bin (NaN when not set)."""
    out = np.full(bins, np.nan)
    rows = []
    for s in states:
        attrs = s.get("attributes", {})
        value = attrs.get("temperature")
        if value is None:
            value = attrs.get("target_temp_low")
        when = datetime.fromisoformat(s["last_updated"]).astimezone(UTC)
        rows.append((when, np.nan if value is None else float(value)))
    j = 0
    current = np.nan
    for i in range(bins):
        t = start + i * width
        while j < len(rows) and rows[j][0] <= t:
            current = rows[j][1]
            j += 1
        out[i] = current
    return out


def _simulate(t0, weather, light, a, c, g, steps, hours):
    """Forward Euler no-heat forecast; returns the temperature at each step."""
    path = np.empty(steps + 1)
    path[0] = t0
    for k in range(steps):
        t = path[k]
        path[k + 1] = t + hours * (a * (weather[k] - t) + c + g * light[k])
    return path


def main() -> None:
    """Print the model check and the skippable-call summary."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--bin", type=int, default=15, help="minutes")
    p.add_argument("--horizon", type=float, default=3.0, help="hours to look ahead")
    p.add_argument("--tolerance", type=float, default=0.5, help="C below setpoint")
    p.add_argument("--max-dip", type=float, default=0.5, help="C.h below the band")
    p.add_argument("--rotation", type=float, default=10.4)
    p.add_argument("--pitch", type=float, default=45.0)
    p.add_argument("--furnace-btu", type=float, default=80000.0)
    p.add_argument("--afue", type=float, default=0.95)
    p.add_argument("--low-fraction", type=float, default=0.65)
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    lat, lon = fetch_home_position(args.ha_url, token)
    width = timedelta(minutes=args.bin)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    bins = int((end - start) / width)
    hours = width.total_seconds() / 3600.0
    steps = int(args.horizon / hours)
    high_kw = args.furnace_btu * args.afue * 0.00029307
    low_kw = high_kw * args.low_fraction

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
        f"{bins} bins of {args.bin} min from {start:%Y-%m-%d}; look-ahead "
        f"{args.horizon:g} h, band {args.tolerance:g} C below setpoint; furnace "
        f"{high_kw:.1f} kW high, {low_kw:.1f} kW low\n"
    )
    print(
        "1. Does the no-heat forecast work? (RMSE C at 1, 2, 3 h after any idle moment)"
    )
    print(
        f"{'zone':<14}{'idle starts':>12}{'model 1h':>10}{'2h':>6}{'3h':>6}"
        f"{'hold 1h':>10}{'2h':>6}{'3h':>6}"
    )
    summary = []
    for zone in ZONES:
        room_name = ZONE_ROOM[zone]
        states = fetch_states(
            args.ha_url, token, f"climate.{zone}", start, end, with_attributes=True
        )
        heating = runs_from_states(states, end, {"heating"}, "hvac_action")
        heat = _overlap_fraction(heating, start, bins, width)
        setpoint = _setpoints(states, start, bins, width)
        room = _bin_means(stats.get(ROOMS[room_name], []), start, bins, width)
        spec = WINDOWS.get(room_name)
        light = (
            _room_light(
                spec, held, azimuth, elevation, args.rotation, args.pitch, block
            )
            if spec
            else np.zeros(bins)
        )
        light = np.nan_to_num(light)
        y = np.full(bins, np.nan)
        y[:-1] = (room[1:] - room[:-1]) / hours
        diff = t_out - room
        idle = (heat == 0) & (np.concatenate([[1.0], heat[:-1]]) == 0)
        sel = idle & ~np.isnan(y) & ~np.isnan(diff)
        if sel.sum() < MIN_BINS:
            print(f"{zone:<14}  too little idle data")
            continue
        cols = [diff[sel], np.ones(sel.sum())]
        if spec:
            cols.append(light[sel])
        beta, _, _ = _ols(np.column_stack(cols), y[sel])
        a, c = beta[0], beta[1]
        g = beta[2] if spec else 0.0

        # check on idle stretches long enough to forecast across
        errs = {h: [] for h in (1, 2, 3)}
        holds = {h: [] for h in (1, 2, 3)}
        starts = 0
        for i in range(bins - steps):
            if np.isnan(room[i]) or not idle[i : i + steps + 1].all():
                continue
            if np.isnan(t_out[i : i + steps]).any():
                continue
            path = _simulate(room[i], t_out[i:], light[i:], a, c, g, steps, hours)
            starts += 1
            for lead_h, lead_errs in errs.items():
                k = int(lead_h / hours)
                if k <= steps and not np.isnan(room[i + k]):
                    lead_errs.append(room[i + k] - path[k])
                    holds[lead_h].append(room[i + k] - room[i])
        rmse = {
            h: np.sqrt(np.mean(np.square(v))) if v else np.nan for h, v in errs.items()
        }
        hold = {
            h: np.sqrt(np.mean(np.square(v))) if v else np.nan for h, v in holds.items()
        }
        print(
            f"{zone:<14}{starts:>12}{rmse[1]:>10.2f}{rmse[2]:>6.2f}{rmse[3]:>6.2f}"
            f"{hold[1]:>10.2f}{hold[2]:>6.2f}{hold[3]:>6.2f}"
        )

        # shadow decision for each call start
        high = stage_runs(states, end, HIGH)
        low = stage_runs(states, end, LOW)
        calls = skip = no_setpoint = 0
        minutes = skip_minutes = 0.0
        kwh = skip_kwh = 0.0
        dips = []
        deficits = []
        for run in heating:
            i = int((run.start - start) / width)
            if i < 1 or i + steps >= bins:
                continue
            m_high = _overlap(Run(run.start, run.end), high)
            m_low = max(_overlap(Run(run.start, run.end), low) - m_high, 0.0)
            energy = (m_high * high_kw + m_low * low_kw) / 60.0
            calls += 1
            minutes += run.minutes
            kwh += energy
            sp = setpoint[i]
            t0 = room[i - 1]
            if np.isnan(sp) or np.isnan(t0) or np.isnan(t_out[i : i + steps]).any():
                no_setpoint += 1
                continue
            path = _simulate(t0, t_out[i:], light[i:], a, c, g, steps, hours)
            floor = sp - args.tolerance
            shortfall = float(np.sum(np.clip(floor - path, 0, None)) * hours)
            lowest = float(path.min() - sp)
            deficits.append(sp - t0)
            if shortfall <= args.max_dip:
                skip += 1
                skip_minutes += run.minutes
                skip_kwh += energy
                dips.append((lowest, shortfall))
        summary.append(
            (
                zone,
                calls,
                skip,
                no_setpoint,
                minutes,
                skip_minutes,
                kwh,
                skip_kwh,
                dips,
                deficits,
            )
        )

    print("\n2. Heating calls the shadow controller would have skipped")
    print(
        f"{'zone':<6}{'calls':>7}{'skippable':>11}{'no setpoint':>13}"
        f"{'minutes':>9}{'skippable':>11}{'kWh':>7}{'skippable':>11}  median wait h"
    )
    tot = np.zeros(6)
    for (
        zone,
        calls,
        skip,
        nos,
        minutes,
        skip_minutes,
        kwh,
        skip_kwh,
        dips,
        deficits,
    ) in summary:
        wait = f"{np.median([d[0] for d in dips]):+.2f}" if dips else "-"
        below = f"{np.median(deficits):.2f}" if deficits else "-"
        print(
            f"{zone:<6}{calls:>7}{skip:>11}{nos:>13}{minutes:>9.0f}{skip_minutes:>11.0f}"
            f"{kwh:>7.1f}{skip_kwh:>11.1f}  {wait:>17}  {below:>12}"
        )
        tot += [calls, skip, minutes, skip_minutes, kwh, skip_kwh]
    print(
        f"{'all':<6}{tot[0]:>7.0f}{tot[1]:>11.0f}{'':>13}{tot[2]:>9.0f}{tot[3]:>11.0f}"
        f"{tot[4]:>7.1f}{tot[5]:>11.1f}"
    )
    print(
        "\nNothing was switched. The energy is an upper bound (zone calls overlap). "
        "A skipped call\nis only as good as the section 1 forecast."
    )


if __name__ == "__main__":
    main()
