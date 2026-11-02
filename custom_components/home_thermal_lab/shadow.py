"""Shadow-mode furnace controller (hypothesis 17), standard library only.

Given a zone's no-heat model, the room temperature and setpoint now, and the
outdoor temperature and sunlight forecast, say whether the furnace could stay
off: the room is forecast to stay within a comfort band below the setpoint for
the next few hours. Nothing here switches anything; it only returns a decision
to log.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ZoneModel:
    """Zone model (per hour), ``dT/dt = a * (outdoor - room) + c + g * light``
    ``+ b * (ground - room) + w * wall_light + h * heat``.

    Attributes:
        a: Cooling rate toward the outdoor temperature, per hour.
        c: Constant heat gain or loss, C per hour.
        g: Warming per unit of light on the room windows and roof, C per hour
            per W/m2.
        b: Coupling to the ground, per hour (a room below ground).
        w: Warming per W/m2 of lagged light on sunlit solid walls.
        h: Warming while the zone's furnace call runs, C per hour (0 when not
            known: the simulated thermostat then cannot heat).
    """

    a: float
    c: float
    g: float = 0.0
    b: float = 0.0
    w: float = 0.0
    h: float = 0.0


@dataclass(frozen=True)
class Decision:
    """What the controller would do for a call that is starting now.

    Attributes:
        skip: True if the furnace could stay off over the look-ahead.
        lowest: Lowest forecast room temperature minus the setpoint, in C.
        shortfall: Degree-hours below the comfort band.
        steps: Number of look-ahead steps simulated.
    """

    skip: bool
    lowest: float
    shortfall: float
    steps: int


@dataclass(frozen=True)
class Thermostat:
    """A simple on/off heating thermostat for the simulation.

    Heat comes on when the room is below ``setpoint - deadband`` at the start of
    a step and goes off the moment the room reaches the setpoint (part way
    through a step if need be), as ClimateAdvisor's forecast does.

    Attributes:
        setpoints: Heating setpoint for each step.
        deadband: How far below the setpoint the room falls before heat starts.
        heating: Whether the call is running at the start.
    """

    setpoints: list[float]
    deadband: float = 0.5
    heating: bool = False


def _drive(
    model: ZoneModel, outdoor: float, light: float, wall: float, ground: float
) -> float:
    """Everything in the rate that does not depend on the room temperature."""
    return (
        model.a * outdoor
        + model.b * ground
        + model.c
        + model.g * light
        + model.w * wall
    )


def step(
    room: float,
    outdoor: float,
    light: float,
    model: ZoneModel,
    hours: float,
    wall: float = 0.0,
    ground: float = 0.0,
    heat: float = 0.0,
) -> float:
    """Room temperature after ``hours`` with the drivers held, solved exactly.

    The model is linear in the room temperature, ``dT/dt = q - k * T`` with
    ``k = a + b``, so over a step with fixed drivers the room moves along an
    exponential toward ``q / k``: no step-size error, and stable for any step
    (ClimateAdvisor's ODE step does the same).
    """
    k = model.a + model.b
    q = _drive(model, outdoor, light, wall, ground) + model.h * heat
    if abs(k) < 1e-12:
        return room + q * hours
    settle = q / k
    return settle + (room - settle) * math.exp(-k * hours)


def _hours_to_reach(
    room: float, target: float, q: float, k: float, hours: float
) -> float | None:
    """Hours until the room reaches ``target`` along one step, or None."""
    if abs(k) < 1e-12:
        if q <= 0:
            return None
        t = (target - room) / q
    else:
        settle = q / k
        if (settle - room) * (settle - target) <= 0 or settle == room:
            return None
        ratio = (target - settle) / (room - settle)
        if ratio <= 0:
            return None
        t = -math.log(ratio) / k
    return t if 0.0 <= t <= hours else None


def simulate(
    start: float,
    outdoor: list[float],
    light: list[float],
    model: ZoneModel,
    step_hours: float,
    wall: list[float] | None = None,
    ground: float = 0.0,
) -> list[float]:
    """Room temperature with the furnace off.

    Args:
        start: Room temperature now.
        outdoor: Outdoor temperature over each step.
        light: Light on the room windows and roof over each step.
        model: The zone model.
        step_hours: Step length in hours.
        wall: Lagged light on sunlit solid walls over each step.
        ground: Ground temperature.

    Returns:
        Temperatures at the start and end of every step (one more than steps).
    """
    path = [start]
    for k, (t_out, lit) in enumerate(zip(outdoor, light, strict=False)):
        on_wall = 0.0 if wall is None else wall[k]
        path.append(step(path[-1], t_out, lit, model, step_hours, on_wall, ground))
    return path


def simulate_heated(
    start: float,
    outdoor: list[float],
    light: list[float],
    model: ZoneModel,
    step_hours: float,
    thermostat: Thermostat,
    wall: list[float] | None = None,
    ground: float = 0.0,
) -> tuple[list[float], list[float]]:
    """Room temperature with a simulated thermostat running the furnace.

    Returns:
        The temperatures (one more than steps) and, for each step, the fraction
        of it the furnace ran.
    """
    path = [start]
    duty = []
    heating = thermostat.heating
    k = model.a + model.b
    for i, (t_out, lit) in enumerate(zip(outdoor, light, strict=False)):
        room = path[-1]
        on_wall = 0.0 if wall is None else wall[i]
        setpoint = thermostat.setpoints[min(i, len(thermostat.setpoints) - 1)]
        if model.h <= 0 or (heating and room >= setpoint):
            heating = False
        elif not heating and room < setpoint - thermostat.deadband:
            heating = True
        if not heating:
            path.append(step(room, t_out, lit, model, step_hours, on_wall, ground))
            duty.append(0.0)
            continue
        q = _drive(model, t_out, lit, on_wall, ground) + model.h
        reach = _hours_to_reach(room, setpoint, q, k, step_hours)
        if reach is None:
            path.append(step(room, t_out, lit, model, step_hours, on_wall, ground, 1.0))
            duty.append(1.0)
            continue
        rest = step_hours - reach
        path.append(step(setpoint, t_out, lit, model, rest, on_wall, ground))
        duty.append(reach / step_hours)
        heating = False
    return path, duty


def decide(
    room: float,
    setpoint: float,
    outdoor: list[float],
    light: list[float],
    model: ZoneModel,
    step_hours: float = 0.25,
    tolerance: float = 0.5,
    max_dip: float = 0.5,
    wall: list[float] | None = None,
    ground: float = 0.0,
) -> Decision:
    """Whether a heat call starting now could be skipped.

    Args:
        room: Room temperature now, C.
        setpoint: Heating setpoint now, C.
        outdoor: Forecast outdoor temperature per step.
        light: Forecast light on the room per step.
        model: The zone no-heat model.
        step_hours: Step length in hours.
        tolerance: Comfort band below the setpoint, C.
        max_dip: Most degree-hours allowed below that band.
        wall: Forecast lagged light on sunlit solid walls per step.
        ground: Ground temperature.

    Returns:
        The decision, with the numbers behind it.
    """
    path = simulate(room, outdoor, light, model, step_hours, wall, ground)
    floor = setpoint - tolerance
    shortfall = sum(max(floor - t, 0.0) for t in path) * step_hours
    return Decision(
        skip=shortfall <= max_dip,
        lowest=min(path) - setpoint,
        shortfall=shortfall,
        steps=len(path) - 1,
    )
