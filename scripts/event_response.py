"""Measure how rooms respond to a labelled event, such as cooking.

Give the local start and end time of the event (and optionally when it really
ended, for a follow-up window). It reports the whole-house energy above the
level just before it, and for every room sensor the temperature change during
the event and afterwards, against the room's drift over an equal stretch
beforehand. Pairs with ``scripts/power_check.py`` (hypotheses 11 and 14).

Usage (local time today)::

    uv run python scripts/event_response.py 18:08 18:45 --follow 60
    uv run python scripts/event_response.py 2026-11-01T18:08 2026-11-01T18:45
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env
from regress_rooms import POWER, ROOMS

from custom_components.home_thermal_lab.ha_history import (
    fetch_states,
    fetch_time_zone,
    urllib_fetch_auth,
)
from custom_components.home_thermal_lab.power import power_series, time_weighted_mean


def _parse(text: str, tz: ZoneInfo) -> datetime:
    if "T" in text or "-" in text:
        return datetime.fromisoformat(text).replace(tzinfo=tz)
    hour, minute = (int(p) for p in text.split(":"))
    today = datetime.now(tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return today


def _held(states: list[dict], when: datetime) -> float | None:
    value = None
    for s in states:
        if datetime.fromisoformat(s["last_changed"]) > when:
            break
        try:
            value = float(s["state"])
        except ValueError:
            continue
    return value


def main() -> None:
    """Print the energy and each room's response."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("start")
    p.add_argument("end")
    p.add_argument("--follow", type=float, default=0.0, help="minutes after the end")
    p.add_argument("--before", type=float, default=30.0, help="baseline minutes")
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    token = os.environ["HA_TOKEN"]
    tz = ZoneInfo(fetch_time_zone(args.ha_url, token))
    t0 = _parse(args.start, tz).astimezone(UTC)
    t1 = _parse(args.end, tz).astimezone(UTC)
    t2 = t1 + timedelta(minutes=args.follow)
    pre = t0 - timedelta(minutes=args.before)
    fetch_from = pre - timedelta(hours=2)
    fetch_to = min(t2, datetime.now(UTC)) + timedelta(minutes=1)

    power = power_series(fetch_states(args.ha_url, token, POWER, fetch_from, fetch_to))
    base = time_weighted_mean(power, pre, t0 - timedelta(seconds=30))
    during = time_weighted_mean(power, t0, min(t1, fetch_to))
    hours = (min(t1, fetch_to) - t0).total_seconds() / 3600.0
    print(
        f"event {t0.astimezone(tz):%H:%M}-{t1.astimezone(tz):%H:%M} "
        f"({hours * 60:.0f} min), furnace calls: ",
        end="",
    )
    calls = []
    for z in ("z1", "z2", "z3", "z4"):
        a = urllib_fetch_auth(
            args.ha_url.rstrip("/") + f"/api/states/climate.{z}", token
        )["attributes"]
        calls.append(f"{z}={a.get('hvac_action')}")
    print(", ".join(calls), "(now)")
    if base is not None and during is not None:
        print(
            f"whole-house power: {base:.2f} kW before, {during:.2f} kW during; "
            f"extra energy about {(during - base) * hours:.2f} kWh\n"
        )

    print(
        f"{'room':<16}{'before C/h':>11}{'during C/h':>12}{'excess C/h':>12}"
        f"{'follow C/h':>12}{'now-start C':>13}"
    )
    for name, entity in ROOMS.items():
        st = fetch_states(args.ha_url, token, entity, fetch_from, fetch_to)
        a, b, c = _held(st, pre), _held(st, t0), _held(st, min(t1, fetch_to))
        d = _held(st, min(t2, fetch_to))
        if None in (a, b, c):
            print(f"{name:<16}  no readings")
            continue
        before = (b - a) / (args.before / 60.0)
        run = (c - b) / hours if hours > 0 else float("nan")
        after = (
            (d - c) / ((min(t2, fetch_to) - t1).total_seconds() / 3600.0)
            if args.follow and d is not None and min(t2, fetch_to) > t1
            else float("nan")
        )
        print(
            f"{name:<16}{before:>+11.2f}{run:>+12.2f}{run - before:>+12.2f}"
            f"{after:>+12.2f}{c - b:>+13.2f}"
        )


if __name__ == "__main__":
    main()
