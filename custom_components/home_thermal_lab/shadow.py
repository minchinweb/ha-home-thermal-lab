"""Shadow-mode furnace controller (hypothesis 17), standard library only.

Given a zone's no-heat model, the room temperature and setpoint now, and the
outdoor temperature and sunlight forecast, say whether the furnace could stay
off: the room is forecast to stay within a comfort band below the setpoint for
the next few hours. Nothing here switches anything; it only returns a decision
to log.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZoneModel:
    """No-heat model ``dT/dt = a * (outdoor - room) + c + g * light`` (per hour).

    Attributes:
        a: Cooling rate toward the outdoor temperature, per hour.
        c: Constant heat gain or loss, C per hour.
        g: Warming per unit of light on the room windows and roof, C per hour
            per W/m2.
    """

    a: float
    c: float
    g: float = 0.0


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


def simulate(
    start: float,
    outdoor: list[float],
    light: list[float],
    model: ZoneModel,
    step_hours: float,
) -> list[float]:
    """Forward-Euler room temperature with the furnace off.

    Args:
        start: Room temperature now.
        outdoor: Outdoor temperature at the start of each step.
        light: Light on the room windows and roof at the start of each step.
        model: The zone no-heat model.
        step_hours: Step length in hours.

    Returns:
        Temperatures at the start and end of every step (one more than steps).
    """
    path = [start]
    for t_out, lit in zip(outdoor, light, strict=False):
        t = path[-1]
        path.append(t + step_hours * (model.a * (t_out - t) + model.c + model.g * lit))
    return path


def decide(
    room: float,
    setpoint: float,
    outdoor: list[float],
    light: list[float],
    model: ZoneModel,
    step_hours: float = 0.25,
    tolerance: float = 0.5,
    max_dip: float = 0.5,
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

    Returns:
        The decision, with the numbers behind it.
    """
    path = simulate(room, outdoor, light, model, step_hours)
    floor = setpoint - tolerance
    shortfall = sum(max(floor - t, 0.0) for t in path) * step_hours
    return Decision(
        skip=shortfall <= max_dip,
        lowest=min(path) - setpoint,
        shortfall=shortfall,
        steps=len(path) - 1,
    )
