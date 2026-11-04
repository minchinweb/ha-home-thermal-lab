"""A zone's day ahead: forecast room temperature, furnace duty and target band.

Standard library only. This is hypothesis 16 as revised after reading
ClimateAdvisor: the zone's own model (``shadow.ZoneModel``, with the heating
rate ``h``) driven by the outdoor forecast and the sunlight on the room, with
the thermostat simulated as an on/off heater that stops at the setpoint
(``shadow.simulate_heated``). The integration does not know the thermostat's
program, so it assumes today repeats yesterday (``schedule_by_slot`` and
``setpoints_ahead``): in the backtest (``scripts/predict_rc.py``) that came
within 0.02 C of knowing the day's setpoints, where holding the current
setpoint all day was off by 2.9 C in a zone with a night setback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .shadow import Thermostat, ZoneModel, simulate_heated
from .target import Band, TargetWave, setpoint_band, target_at

SLOTS = 96  # quarter-hours in a day


def slot_of(local: datetime) -> int:
    """The quarter-hour of the (local) day."""
    return (local.hour * 60 + local.minute) // 15


def schedule_by_slot(
    setpoints: list[tuple[datetime, float]], end: datetime
) -> list[float | None]:
    """The setpoint of each quarter-hour slot over the day before ``end``.

    Args:
        setpoints: ``(local time, setpoint)`` changes, oldest first.
        end: The end of the day to read (local time).

    Returns:
        96 values: for each slot, the setpoint in force at the last time of day
        in that slot before ``end`` (None if nothing was recorded by then).
    """
    out: list[float | None] = []
    start = end - timedelta(days=1)
    for k in range(SLOTS):
        offset = timedelta(minutes=15 * k)
        when = start.replace(hour=0, minute=0, second=0, microsecond=0) + offset
        while when + timedelta(days=1) <= end:
            when += timedelta(days=1)
        if when < start:
            when += timedelta(days=1)
        value = None
        for t, v in setpoints:
            if t > when:
                break
            value = v
        out.append(value)
    return out


def setpoints_ahead(
    now_setpoint: float, schedule: list[float | None] | None, slots: list[int]
) -> list[float]:
    """The setpoint for each step: the current one until the program changes.

    The current setpoint holds (so a change made by hand today stands) until
    yesterday's program changed at that time of day; from then on the program
    is followed.
    """
    if not schedule or not slots:
        return [now_setpoint] * len(slots)
    out = []
    following = False
    first = schedule[slots[0]]
    for slot in slots:
        value = schedule[slot]
        if not following and value is not None and value != first:
            following = True
        out.append(value if following and value is not None else now_setpoint)
    return out


@dataclass(frozen=True)
class Outlook:
    """The forecast from now, one entry per step boundary (now first).

    Attributes:
        times: Time of each point.
        temps: Forecast room temperature.
        duty: Fraction of the step after each point the furnace runs (the last
            point has none and gets 0).
        outdoor: Outdoor temperature over the step after each point.
        bands: Target band at each point.
    """

    times: list[datetime]
    temps: list[float]
    duty: list[float]
    outdoor: list[float]
    bands: list[Band]

    def at(self, hours: float) -> float | None:
        """Forecast temperature ``hours`` after the first point, if covered."""
        if not self.times:
            return None
        step = (self.times[1] - self.times[0]) if len(self.times) > 1 else None
        if step is None:
            return self.temps[0] if hours == 0 else None
        k = round(timedelta(hours=hours) / step)
        return self.temps[k] if 0 <= k < len(self.temps) else None


def band_at(
    wave: TargetWave | None, setpoint: float, tolerance: float, local_hour: float
) -> Band:
    """The target band: the wave when configured, else the setpoint band."""
    if wave is None:
        return setpoint_band(setpoint, tolerance)
    return target_at(wave, local_hour)


def build_outlook(
    now: datetime,
    room: float,
    model: ZoneModel,
    outdoor: list[float],
    light: list[float],
    step_hours: float,
    setpoint: float | list[float],
    local_hours: list[float],
    deadband: float = 0.1,
    heating: bool = False,
    wall: list[float] | None = None,
    ground: float = 0.0,
    wave: TargetWave | None = None,
    tolerance: float = 0.5,
) -> Outlook:
    """Simulate the zone forward from ``now``.

    Args:
        now: Start time.
        room: Room temperature now.
        model: The zone model; ``h`` 0 means the furnace cannot be simulated
            and the forecast is the no-heat path.
        outdoor: Outdoor temperature over each step.
        light: Light on the windows and roof over each step.
        step_hours: Step length.
        setpoint: Heating setpoint, held, or one per step (``setpoints_ahead``).
        local_hours: Local clock hour at each point (one more than steps).
        deadband: How far below the setpoint a call starts.
        heating: Whether a call is running now.
        wall: Lagged light on sunlit solid walls over each step.
        ground: Ground temperature.
        wave: The target wave, if configured.
        tolerance: Band below the setpoint when there is no wave.
    """
    steps = len(outdoor)
    if isinstance(setpoint, list):
        plan = setpoint or [0.0]
    else:
        plan = [setpoint] * max(steps, 1)
    stat = Thermostat(plan, deadband, heating)
    temps, duty = simulate_heated(
        room, outdoor, light, model, step_hours, stat, wall, ground
    )
    return outlook_from_path(
        now, temps, duty, outdoor, plan, local_hours, step_hours, wave, tolerance
    )


def outlook_from_path(
    now: datetime,
    temps: list[float],
    duty: list[float],
    outdoor: list[float],
    plan: list[float],
    local_hours: list[float],
    step_hours: float,
    wave: TargetWave | None = None,
    tolerance: float = 0.5,
) -> Outlook:
    """An outlook from a forecast made elsewhere (``house.forecast_house``).

    Args:
        now: Start time.
        temps: Room temperature at each step boundary (now first).
        duty: Share of each step the furnace runs.
        outdoor: Outdoor temperature over each step.
        plan: Heating setpoint per step.
        local_hours: Local clock hour at each point (one more than steps).
        step_hours: Step length.
        wave: The target wave, if configured.
        tolerance: Band below the setpoint when there is no wave.
    """
    steps = len(outdoor)
    plan = plan or [0.0]
    step = timedelta(hours=step_hours)
    times = [now + k * step for k in range(steps + 1)]
    return Outlook(
        times,
        temps,
        [*duty, 0.0],
        [*outdoor, outdoor[-1] if outdoor else 0.0],
        [
            band_at(wave, plan[min(k, len(plan) - 1)], tolerance, h)
            for k, h in enumerate(local_hours[: steps + 1])
        ],
    )


def outlook_points(
    outlook: Outlook,
    every: int = 2,
    digits: int = 2,
    extra: dict[str, list[float] | None] | None = None,
) -> list[dict]:
    """Chart points: every ``every``-th step, with the duty averaged over them.

    ``extra`` gives further per-step shares (such as the cooling call or the
    fan), averaged over the same spans and keyed as they should appear.
    """
    extra = extra or {}
    out = []
    for k in range(0, len(outlook.times), every):
        span = outlook.duty[k : k + every]
        band = outlook.bands[k]
        point = {
            "t": outlook.times[k].isoformat(),
            "temp": round(outlook.temps[k], digits),
            "outdoor": round(outlook.outdoor[k], digits),
            "heat": round(sum(span) / len(span), digits) if span else 0.0,
            "lower": round(band.lower, digits),
            "upper": round(band.upper, digits),
        }
        for key, series in extra.items():
            if series is None:
                continue
            part = series[k : k + every]
            point[key] = round(sum(part) / len(part), digits) if part else 0.0
        out.append(point)
    return out
