"""The day ahead for all of a house's zones together (hypothesis 16).

Standard library only. The zones are simulated together
(``shadow.simulate_house``), each zone's model taking its neighbours' forecast
temperatures and calls (the ``n`` and ``x`` terms), and each with its thermostat
in the loop. Where a zone has history, its forecast is the hybrid
(``routine.hybrid``): the profile forecast D, plus the simulated path with the
day's forecast weather and setpoints, minus the simulated path from the same
start with the typical day's. In the backtest (``scripts/predict_rc.py``) the
hybrid with yesterday's setpoints beat D over the day (0.44 against 0.46 C) and
clearly over the first 6 hours (0.19 against 0.27 C), where the models alone did
not beat D at all.

A zone without a usable model is held at its temperature in the simulation (so
its neighbours still see it) and forecast by D alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .routine import fill, forecast_d, hybrid, typical
from .shadow import HouseZone, Thermostat, ZoneModel, simulate_house

HELD = ZoneModel(0.0, 0.0)  # dT/dt = 0: a zone held where it is


@dataclass(frozen=True)
class ZoneHistory:
    """A zone's recent history in bins, for the profile and the typical day.

    Attributes:
        start: Start time of bin 0.
        room: Room temperature per bin (None when unknown).
        outdoor: Outdoor temperature per bin.
        light: Light on the windows and roof per bin.
        wall: Lagged light on sunlit solid walls per bin.
        setpoint: Heating setpoint per bin (None when off or unknown).
        tau: The fading time of D's gap, hours (``routine.fit_offset_tau``).
    """

    start: datetime
    room: list
    outdoor: list
    light: list[float]
    wall: list[float]
    setpoint: list
    tau: float


@dataclass(frozen=True)
class ZoneNow:
    """One zone's state now and its drivers ahead.

    Attributes:
        model: The zone model (None: no usable model; held, and forecast by D).
        room: Room temperature now.
        heating: Whether its call is running now.
        plan: Heating setpoint per step (-50 C never heats).
        deadband: The simulated thermostat's deadband.
        light: Light on the windows and roof per step.
        wall: Lagged wall light per step.
        ground: Ground temperature.
        neighbours: Indices (in the list of zones) of the zones whose mean
            temperature and calls drive this one's ``n`` and ``x`` terms.
        history: The zone's history, for D and the hybrid (None: model only).
    """

    model: ZoneModel | None
    room: float
    heating: bool
    plan: list[float]
    deadband: float
    light: list[float]
    wall: list[float]
    ground: float = 0.0
    neighbours: tuple[int, ...] = ()
    history: ZoneHistory | None = None


@dataclass(frozen=True)
class ZoneAhead:
    """One zone's forecast.

    Attributes:
        temps: Room temperature at each step boundary (now first).
        duty: Share of each step the zone's furnace runs (simulated).
        method: ``hybrid``, ``model`` or ``profile`` (D alone).
    """

    temps: list[float]
    duty: list[float]
    method: str


def _origin(history: ZoneHistory, now: datetime, step: timedelta) -> int:
    """The bin of ``now`` in the history (may lie past its end)."""
    return max(1, int((now - history.start) / step))


def _padded(values: list, length: int) -> list:
    return list(values[:length]) + [None] * max(0, length - len(values))


def _profile_d(
    history: ZoneHistory, room: float, origin: int, steps: int, step_hours: float
) -> list[float | None]:
    """D from ``origin``, the room now standing in for the bin before it."""
    room_bins = _padded(history.room, origin)
    room_bins[origin - 1] = room
    return forecast_d(room_bins, origin, steps, step_hours, history.tau)


def _usual(values: list, origin: int, steps: int, fallback: float) -> list[float]:
    return fill(typical(_padded(values, origin), origin, steps), fallback)


def forecast_house(
    now: datetime, zones: list[ZoneNow], outdoor: list[float], step_hours: float
) -> list[ZoneAhead]:
    """Forecast every zone over ``len(outdoor)`` steps from ``now``.

    Args:
        now: Start time.
        zones: The zones, each with its neighbours as indices into this list.
        outdoor: Forecast outdoor temperature per step.
        step_hours: Step length.

    Returns:
        One forecast per zone, in order.
    """
    steps = len(outdoor)
    step = timedelta(hours=step_hours)

    def run(plans, outdoors, lights, walls):
        house = [
            HouseZone(
                z.model or HELD,
                z.room,
                lights[i],
                Thermostat(plans[i], z.deadband, z.heating),
                walls[i],
                z.ground,
                neighbours=z.neighbours,
                others=z.neighbours,
            )
            for i, z in enumerate(zones)
        ]
        return simulate_house(house, outdoors, step_hours)

    today = run(
        [z.plan for z in zones],
        outdoor,
        [z.light for z in zones],
        [z.wall for z in zones],
    )
    with_history = [z.history for z in zones if z.history is not None]
    usual = None
    if with_history:
        ref = with_history[0]
        o = _origin(ref, now, step)
        usual_out = _usual(ref.outdoor, o, steps, outdoor[0] if outdoor else 0.0)
        plans, lights, walls = [], [], []
        for z in zones:
            h = z.history
            if h is None:
                plans.append(z.plan)
                lights.append(z.light)
                walls.append(z.wall)
                continue
            zo = _origin(h, now, step)
            plans.append(_usual(h.setpoint, zo, steps, z.plan[0] if z.plan else -50.0))
            lights.append(_usual(h.light, zo, steps, 0.0))
            walls.append(_usual(h.wall, zo, steps, 0.0))
        usual = run(plans, usual_out, lights, walls)

    out = []
    for i, z in enumerate(zones):
        path, duty = today[i]
        if z.history is None or usual is None:
            out.append(ZoneAhead(path, duty, "model" if z.model else "held"))
            continue
        o = _origin(z.history, now, step)
        d = _profile_d(z.history, z.room, o, steps, step_hours)
        if all(v is None for v in d):
            out.append(ZoneAhead(path, duty, "model" if z.model else "held"))
            continue
        mixed = hybrid(d, path, usual[i][0])
        temps = [z.room] + [
            p if v is None else v for v, p in zip(mixed, path[1:], strict=False)
        ]
        out.append(ZoneAhead(temps, duty, "hybrid" if z.model else "profile"))
    return out


def hub_neighbours(
    heat_hours: dict[str, float], configured: dict[str, list[str]] | None = None
) -> dict[str, tuple[str, ...]]:
    """Each zone's neighbours: as configured, else by the hub rule.

    The hub is the zone whose furnace calls ran longest. Every other zone's
    neighbour is the hub, and the hub's neighbours are all the others. In the
    backtest that beat taking every other zone as each zone's neighbours
    (0.44 against 0.49 C over the day): in an open house the zones that do not
    heat are warmed by the one that does.

    Args:
        heat_hours: Hours of furnace calls per zone (keys in order).
        configured: Neighbours set by hand per zone (an empty list: the rule).
    """
    keys = list(heat_hours)
    configured = configured or {}
    out: dict[str, tuple[str, ...]] = {}
    hub = max(keys, key=lambda k: heat_hours[k]) if keys else None
    for key in keys:
        chosen = configured.get(key) or []
        if chosen:
            out[key] = tuple(k for k in chosen if k in heat_hours and k != key)
        elif key == hub:
            out[key] = tuple(k for k in keys if k != key)
        else:
            out[key] = (hub,) if hub is not None and heat_hours[hub] > 0 else ()
    return out


def neighbour_inputs(
    aheads: list[ZoneAhead], neighbours: tuple[int, ...]
) -> tuple[list[float], list[float]] | None:
    """The neighbours' mean forecast temperature and summed duty, per step."""
    if not neighbours:
        return None
    steps = min(len(aheads[m].duty) for m in neighbours)
    temps = [
        sum(aheads[m].temps[k] for m in neighbours) / len(neighbours)
        for k in range(steps)
    ]
    duty = [sum(aheads[m].duty[k] for m in neighbours) for k in range(steps)]
    return temps, duty
