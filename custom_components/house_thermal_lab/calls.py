"""Heating calls of one zone, and how its thermostat responds (05, 13).

A call is a run of ``hvac_action == "heating"`` on an Ecobee climate entity. Its
stage comes from ``equipment_running``: ``auxHeat1`` is W1 (low stage),
``auxHeat2`` is W2 (high stage). A call that reaches W2 at any point is
"stepped" (it started on low and escalated), otherwise "low".

For each call, against the thermostat's ``current_temperature``:

* **lag**: minutes from the call starting until the reading first rises above
  its value at the start (the time for warm air to reach the sensor);
* **rise**: reading at the end minus reading at the start;
* after the call stops, within ``after_minutes``: the **overshoot** (highest
  reading minus the reading at the end), then the **dip** (lowest reading after
  that peak, minus the reading at the end: the forced warm air is gone) and the
  **rebound** (highest reading after the dip minus the dip: walls and furniture
  giving back heat as the room evens out).

Plain Python only, so it runs inside Home Assistant and in the scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import statistics

LOW = "auxHeat1"
HIGH = "auxHeat2"
MIN_STEP = 0.05  # C; Ecobee readings move in about 0.06 C (0.1 F) steps


@dataclass(frozen=True)
class Call:
    """One heating call."""

    start: datetime
    end: datetime
    high_minutes: float

    @property
    def minutes(self) -> float:
        """Length of the call."""
        return (self.end - self.start).total_seconds() / 60.0

    @property
    def stage(self) -> str:
        """``stepped`` if the high stage ran at all, else ``low``."""
        return "stepped" if self.high_minutes > 0 else "low"


@dataclass(frozen=True)
class Response:
    """How the thermostat reading moved during and after a call (C, minutes)."""

    call: Call
    start_temp: float
    rise: float
    lag: float | None
    overshoot: float | None
    dip: float | None
    dip_minutes: float | None
    rebound: float | None


def _when(row: dict) -> datetime:
    return datetime.fromisoformat(row["last_updated"]).astimezone(UTC)


def calls_from_states(states: list[dict], until: datetime) -> list[Call]:
    """Heating calls from a climate entity's history (with attributes).

    Args:
        states: State dicts with ``attributes`` and ``last_updated``.
        until: When the last state stops holding.

    Returns:
        Calls, oldest first. A call still running at ``until`` ends there.
    """
    rows = sorted(states, key=_when)
    calls = []
    began = None
    high = 0.0
    prev_time = None
    prev_high = False
    for row in [*rows, None]:
        if row is None:
            when, heating, is_high = until.astimezone(UTC), False, False
        else:
            attrs = row.get("attributes", {})
            when = _when(row)
            heating = attrs.get("hvac_action") == "heating"
            is_high = HIGH in (attrs.get("equipment_running") or "").split(",")
        if began is not None and prev_high and prev_time is not None:
            high += (when - prev_time).total_seconds() / 60.0
        if heating and began is None:
            began, high = when, 0.0
        elif not heating and began is not None:
            if when > began:
                calls.append(Call(began, when, high))
            began = None
        prev_time, prev_high = when, heating and is_high
    return calls


def temperature_series(states: list[dict]) -> list[tuple[datetime, float]]:
    """The thermostat's ``current_temperature`` readings, oldest first."""
    out = []
    for row in states:
        value = row.get("attributes", {}).get("current_temperature")
        if value is not None:
            out.append((_when(row), float(value)))
    return sorted(out)


def _held(series, when: datetime) -> float | None:
    value = None
    for t, v in series:
        if t > when:
            break
        value = v
    return value


def respond(
    call: Call,
    series: list[tuple[datetime, float]],
    after_minutes: float = 90.0,
    next_start: datetime | None = None,
) -> Response | None:
    """Measure one call's response; ``None`` without a reading at its start.

    The after-call window stops early at ``next_start`` (the next call), so a
    following call's heat is not counted as the rebound.
    """
    t0 = _held(series, call.start)
    t1 = _held(series, call.end)
    if t0 is None or t1 is None:
        return None
    lag = None
    for t, v in series:
        if t <= call.start:
            continue
        if t > call.end:
            break
        if v >= t0 + MIN_STEP:
            lag = (t - call.start).total_seconds() / 60.0
            break
    stop = call.end + timedelta(minutes=after_minutes)
    if next_start is not None:
        stop = min(stop, next_start)
    after = [(t, v) for t, v in series if call.end < t <= stop]
    overshoot = dip = dip_minutes = rebound = None
    if after:
        values = [t1] + [v for _, v in after]
        times = [call.end] + [t for t, _ in after]
        peak_i = max(range(len(values)), key=lambda i: (values[i], -i))
        overshoot = values[peak_i] - t1
        tail = range(peak_i, len(values))
        low_i = min(tail, key=lambda i: (values[i], i))
        dip = values[low_i] - t1
        dip_minutes = (times[low_i] - call.end).total_seconds() / 60.0
        rebound = max(values[low_i:]) - values[low_i]
    return Response(call, t0, t1 - t0, lag, overshoot, dip, dip_minutes, rebound)


def responses(
    calls: list[Call], series: list[tuple[datetime, float]], after_minutes=90.0
) -> list[Response]:
    """``respond`` for every call, stopping each window at the next call."""
    out = []
    for i, call in enumerate(calls):
        nxt = calls[i + 1].start if i + 1 < len(calls) else None
        r = respond(call, series, after_minutes, nxt)
        if r is not None:
            out.append(r)
    return out


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def summarise(items: list[Response]) -> dict:
    """Counts, min, median and max per stage, for a sensor's attributes."""
    out: dict = {"calls": len(items)}
    for stage in ("low", "stepped"):
        group = [r for r in items if r.call.stage == stage]
        minutes = [r.call.minutes for r in group]
        out[stage] = {
            "calls": len(group),
            "min_minutes": round(min(minutes), 1) if minutes else None,
            "median_minutes": _median(minutes),
            "max_minutes": round(max(minutes), 1) if minutes else None,
            "median_high_minutes": _median([r.call.high_minutes for r in group]),
            "median_rise": _median([r.rise for r in group]),
            "median_lag_minutes": _median([r.lag for r in group if r.lag is not None]),
            "no_rise_calls": sum(1 for r in group if r.lag is None),
            "median_overshoot": _median(
                [r.overshoot for r in group if r.overshoot is not None]
            ),
            "median_dip": _median([r.dip for r in group if r.dip is not None]),
            "median_dip_minutes": _median(
                [r.dip_minutes for r in group if r.dip_minutes is not None]
            ),
            "median_rebound": _median(
                [r.rebound for r in group if r.rebound is not None]
            ),
        }
    return out
