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
    ``+ b * (ground - room) + w * wall_light + h * heat``
    ``+ n * (neighbour - room) + x * other_heat``.

    Attributes:
        a: Cooling rate toward the outdoor temperature, per hour.
        c: Constant heat gain or loss, C per hour.
        g: Warming per unit of light on the room windows and roof, C per hour
            per W/m2.
        b: Coupling to the ground, per hour (a room below ground).
        w: Warming per W/m2 of lagged light on sunlit solid walls.
        h: Warming while the zone's furnace call runs, C per hour (0 when not
            known: the simulated thermostat then cannot heat).
        n: Coupling to the rest of the house (the mean temperature of the
            neighbouring zones), per hour: in an open house, a zone whose own
            thermostat is off is warmed mostly by the zones that heat
            (hypotheses 06 and 10).
        x: Warming while other zones' furnace calls run, C per hour per call
            (warm air through open doors and a leaking damper, 06).
        lag: The furnace's delivery lag, hours: the heat reaching the room
            follows the call as a first-order lag, so it starts slowly and keeps
            arriving after the call stops (the start lag and overshoot of 13).
            0 means at once.
    """

    a: float
    c: float
    g: float = 0.0
    b: float = 0.0
    w: float = 0.0
    h: float = 0.0
    n: float = 0.0
    x: float = 0.0
    lag: float = 0.0


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
    model: ZoneModel,
    outdoor: float,
    light: float,
    wall: float,
    ground: float,
    neighbour: float = 0.0,
    other: float = 0.0,
) -> float:
    """Everything in the rate that does not depend on the room temperature."""
    return (
        model.a * outdoor
        + model.b * ground
        + model.n * neighbour
        + model.c
        + model.g * light
        + model.w * wall
        + model.x * other
    )


def _k(model: ZoneModel) -> float:
    """How fast the room settles: the sum of its couplings, per hour."""
    return model.a + model.b + model.n


def step(
    room: float,
    outdoor: float,
    light: float,
    model: ZoneModel,
    hours: float,
    wall: float = 0.0,
    ground: float = 0.0,
    heat: float = 0.0,
    neighbour: float = 0.0,
    other: float = 0.0,
) -> float:
    """Room temperature after ``hours`` with the drivers held, solved exactly.

    The model is linear in the room temperature, ``dT/dt = q - k * T`` with
    ``k = a + b + n``, so over a step with fixed drivers the room moves along an
    exponential toward ``q / k``: no step-size error, and stable for any step
    (ClimateAdvisor's ODE step does the same).
    """
    k = _k(model)
    q = _drive(model, outdoor, light, wall, ground, neighbour, other) + model.h * heat
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
    neighbour: list[float] | None = None,
    other: list[float] | None = None,
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
        neighbour: The neighbouring zones' temperature over each step (for a
            model with ``n``).
        other: The share of each step their calls run (for ``x``).

    Returns:
        Temperatures at the start and end of every step (one more than steps).
    """
    path = [start]
    for k, (t_out, lit) in enumerate(zip(outdoor, light, strict=False)):
        path.append(
            step(
                path[-1],
                t_out,
                lit,
                model,
                step_hours,
                0.0 if wall is None else wall[k],
                ground,
                0.0,
                0.0 if neighbour is None else neighbour[k],
                0.0 if other is None else other[k],
            )
        )
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
    neighbour: list[float] | None = None,
    other: list[float] | None = None,
) -> tuple[list[float], list[float]]:
    """Room temperature with a simulated thermostat running the furnace.

    ``neighbour`` and ``other`` (the neighbouring zones' temperature, and the
    share of each step their calls ran) matter only for a model with ``n`` or
    ``x``; to simulate the zones together, use ``simulate_house``.

    Returns:
        The temperatures (one more than steps) and, for each step, the fraction
        of it the furnace ran.
    """
    path = [start]
    duty = []
    heating = thermostat.heating
    pipe = model.h if heating else 0.0
    for i, (t_out, lit) in enumerate(zip(outdoor, light, strict=False)):
        after, ran, heating, pipe = heated_step(
            path[-1],
            heating,
            thermostat.setpoints[min(i, len(thermostat.setpoints) - 1)],
            thermostat.deadband,
            model,
            step_hours,
            t_out,
            lit,
            0.0 if wall is None else wall[i],
            ground,
            0.0 if neighbour is None else neighbour[i],
            0.0 if other is None else other[i],
            pipe,
        )
        path.append(after)
        duty.append(ran)
    return path, duty


def heated_step(
    room: float,
    heating: bool,
    setpoint: float,
    deadband: float,
    model: ZoneModel,
    hours: float,
    outdoor: float,
    light: float,
    wall: float = 0.0,
    ground: float = 0.0,
    neighbour: float = 0.0,
    other: float = 0.0,
    pipe: float = 0.0,
) -> tuple[float, float, bool, float]:
    """One step of the simulated thermostat.

    With a delivery lag (``model.lag``), the step is taken in sub-steps of
    about a minute, the thermostat checking the room at each, and ``pipe`` (the
    heat arriving, C per hour) carried from step to step.

    Returns:
        The room temperature after the step, the share of the step the furnace
        ran, whether the call is still running, and the heat arriving at the end
        (``pipe``; 0 without a lag).
    """
    if model.lag > 0 and model.h > 0:
        return _lagged_step(
            room,
            heating,
            setpoint,
            deadband,
            model,
            hours,
            (outdoor, light, wall, ground),
            (neighbour, other),
            pipe,
        )
    if model.h <= 0 or (heating and room >= setpoint):
        heating = False
    elif not heating and room < setpoint - deadband:
        heating = True
    rest = (wall, ground)
    near = (neighbour, other)
    if not heating:
        after = step(room, outdoor, light, model, hours, *rest, 0.0, *near)
        return after, 0.0, False, 0.0
    q = _drive(model, outdoor, light, wall, ground, neighbour, other) + model.h
    reach = _hours_to_reach(room, setpoint, q, _k(model), hours)
    if reach is None:
        after = step(room, outdoor, light, model, hours, *rest, 1.0, *near)
        return after, 1.0, True, 0.0
    after = step(setpoint, outdoor, light, model, hours - reach, *rest, 0.0, *near)
    return after, reach / hours, False, 0.0


SUB_STEP_HOURS = 1.0 / 60.0


def _lagged_step(
    room: float,
    heating: bool,
    setpoint: float,
    deadband: float,
    model: ZoneModel,
    hours: float,
    weather: tuple[float, float, float, float],
    near: tuple[float, float],
    pipe: float,
) -> tuple[float, float, bool, float]:
    """``heated_step`` with the furnace's delivery lag, in sub-steps."""
    outdoor, light, wall, ground = weather
    count = max(1, math.ceil(hours / SUB_STEP_HOURS - 1e-9))
    dt = hours / count
    fade = math.exp(-dt / model.lag)
    ran = 0.0
    for _ in range(count):
        if heating and room >= setpoint:
            heating = False
        elif not heating and room < setpoint - deadband:
            heating = True
        target = model.h if heating else 0.0
        # Mean heat arriving over the sub-step, the pipe relaxing toward target.
        mean = target + (pipe - target) * model.lag / dt * (1.0 - fade)
        pipe = target + (pipe - target) * fade
        room = step(
            room, outdoor, light, model, dt, wall, ground, mean / model.h, *near
        )
        ran += dt if heating else 0.0
    return room, ran / hours, heating, pipe


@dataclass(frozen=True)
class HouseZone:
    """One zone of a house simulated as a whole (``simulate_house``).

    Attributes:
        model: The zone model.
        start: Room temperature now.
        light: Light on the windows and roof over each step.
        thermostat: The zone's thermostat (a setpoint of -50 C never heats).
        wall: Lagged light on sunlit solid walls over each step.
        ground: Ground temperature.
        neighbours: Indices of the zones whose mean temperature is this zone's
            neighbour (the model's ``n`` term).
        others: Indices of the zones whose calls warm this one (``x``).
    """

    model: ZoneModel
    start: float
    light: list[float]
    thermostat: Thermostat
    wall: list[float] | None = None
    ground: float = 0.0
    neighbours: tuple[int, ...] = ()
    others: tuple[int, ...] = ()


def simulate_house(
    zones: list[HouseZone], outdoor: list[float], step_hours: float
) -> list[tuple[list[float], list[float]]]:
    """Simulate the zones together, each with its thermostat in the loop.

    Over each step a zone sees its neighbours' temperatures at the start of the
    step and the share of the step before that their calls ran, so the zones can
    be stepped one at a time (the leak lags by one step).

    Returns:
        For each zone, its temperatures (one more than steps) and its duty.
    """
    paths = [[z.start] for z in zones]
    duties: list[list[float]] = [[] for _ in zones]
    heating = [z.thermostat.heating for z in zones]
    pipes = [z.model.h if on else 0.0 for z, on in zip(zones, heating, strict=True)]
    last = [1.0 if on else 0.0 for on in heating]
    for i, t_out in enumerate(outdoor):
        now = [p[-1] for p in paths]
        for j, z in enumerate(zones):
            near = (
                sum(now[m] for m in z.neighbours) / len(z.neighbours)
                if z.neighbours
                else 0.0
            )
            sp = z.thermostat.setpoints[min(i, len(z.thermostat.setpoints) - 1)]
            after, ran, heating[j], pipes[j] = heated_step(
                now[j],
                heating[j],
                sp,
                z.thermostat.deadband,
                z.model,
                step_hours,
                t_out,
                z.light[i],
                0.0 if z.wall is None else z.wall[i],
                z.ground,
                near,
                sum(last[m] for m in z.others),
                pipes[j],
            )
            paths[j].append(after)
            duties[j].append(ran)
        last = [d[-1] for d in duties]
    return list(zip(paths, duties, strict=True))


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
    neighbour: list[float] | None = None,
    other: list[float] | None = None,
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
        neighbour: The neighbouring zones' forecast temperature per step.
        other: The share of each step their calls are forecast to run.

    Returns:
        The decision, with the numbers behind it.
    """
    path = simulate(
        room, outdoor, light, model, step_hours, wall, ground, neighbour, other
    )
    floor = setpoint - tolerance
    shortfall = sum(max(floor - t, 0.0) for t in path) * step_hours
    return Decision(
        skip=shortfall <= max_dip,
        lowest=min(path) - setpoint,
        shortfall=shortfall,
        steps=len(path) - 1,
    )
