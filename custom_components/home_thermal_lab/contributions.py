"""What each effect added to or took from a room's temperature (for a chart).

A zone's temperature change is split into the terms the hypotheses measure::

    dT/dt = a * (outdoor - T)        "outdoor"     envelope loss (04, 13)
          + c                        "house"       the rest of the house (10)
          + g * light                "sun"         light on windows and roof (11)
          + h * own_heat             "furnace"     the zone's own calls (05)
          + x * other_heat           "crossover"   other zones' calls (06)
          + p * plug_kw              "appliances"  metered plugs (14)

all in C/h. Around "now", with the current temperature as the baseline:

* **history**: the measured temperature at each past step equals the current
  one minus everything that happened since. Each term's share of that is its
  rate summed from the step to now, with the opposite sign; the part the model
  does not explain is the "unexplained" term, so the stack adds up exactly to the
  measured temperature.
* **forecast**: the same terms summed forward from now, with the forecast
  outdoor temperature and light and a simple thermostat (heat below the setpoint
  minus a deadband, until the setpoint), so the furnace term shows when it would
  be needed.

Each point holds the cumulative contribution of every term relative to the
baseline (positive above it, negative below), ready to draw as stacked areas.
Plain Python, so it runs inside Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

TERMS = ("outdoor", "house", "sun", "furnace", "crossover", "appliances")


@dataclass(frozen=True)
class ZoneTerms:
    """Coefficients of one zone (C/h, per C, per W/m2, per kW)."""

    a: float
    c: float
    g: float = 0.0
    h: float = 0.0
    x: float = 0.0
    p: float = 0.0


@dataclass(frozen=True)
class Inputs:
    """Drivers over one step (fractions of the step for the calls)."""

    outdoor: float
    light: float = 0.0
    own_heat: float = 0.0
    other_heat: float = 0.0
    plug_kw: float = 0.0


def rates(model: ZoneTerms, room: float, step: Inputs) -> dict[str, float]:
    """Each term's rate (C/h) with the room at ``room``."""
    return {
        "outdoor": model.a * (step.outdoor - room),
        "house": model.c,
        "sun": model.g * step.light,
        "furnace": model.h * step.own_heat,
        "crossover": model.x * step.other_heat,
        "appliances": model.p * step.plug_kw,
    }


def history(
    model: ZoneTerms,
    temps: list[float | None],
    steps: list[Inputs | None],
    step_hours: float,
) -> list[dict[str, float] | None]:
    """Cumulative contributions from each past step up to now.

    Args:
        model: The zone's coefficients.
        temps: Measured temperature at the start of each step, plus now as the
            last item (``len(steps) + 1`` values; ``None`` where missing).
        steps: Drivers over each step (``None`` where missing).
        step_hours: Length of a step.

    Returns:
        One dict per entry of ``temps``: for each term (and "unexplained") the
        amount to add to the current temperature to get the one at that time.
        The last entry (now) is all zeros. ``None`` where the chain is broken
        by a missing value; everything before a gap is ``None`` too.
    """
    n = len(steps)
    zero = dict.fromkeys((*TERMS, "unexplained"), 0.0)
    out: list[dict[str, float] | None] = [None] * (n + 1)
    out[n] = dict(zero)
    running = dict(zero)
    for i in range(n - 1, -1, -1):
        step, t0, t1 = steps[i], temps[i], temps[i + 1]
        if step is None or t0 is None or t1 is None:
            break
        r = rates(model, t0, step)
        explained = 0.0
        for term, rate in r.items():
            running[term] -= rate * step_hours
            explained += rate * step_hours
        running["unexplained"] -= (t1 - t0) - explained
        out[i] = dict(running)
    return out


def forecast(
    model: ZoneTerms,
    start: float,
    steps: list[Inputs],
    step_hours: float,
    setpoint: float | None = None,
    deadband: float = 0.5,
    heating: bool = False,
) -> tuple[list[float], list[dict[str, float]]]:
    """Simulate forward from ``start``; returns temperatures and contributions.

    With a ``setpoint``, the zone's own heat comes on below
    ``setpoint - deadband`` and goes off at the setpoint (``heating`` is the
    state at the start); ``own_heat`` in ``steps`` is then ignored.
    """
    temps = [start]
    running = dict.fromkeys(TERMS, 0.0)
    cumulative = [dict(running)]
    room = start
    for step in steps:
        if setpoint is not None:
            if heating and room >= setpoint:
                heating = False
            elif not heating and room < setpoint - deadband:
                heating = True
            step = Inputs(
                step.outdoor,
                step.light,
                1.0 if heating else 0.0,
                step.other_heat,
                step.plug_kw,
            )
        r = rates(model, room, step)
        for term, rate in r.items():
            running[term] += rate * step_hours
        room += sum(r.values()) * step_hours
        temps.append(room)
        cumulative.append(dict(running))
    return temps, cumulative


def held_values(
    series: list[tuple[datetime, float]], times: list[datetime]
) -> list[float | None]:
    """The last reading at or before each time (``series`` oldest first)."""
    out: list[float | None] = []
    j, value = 0, None
    for t in times:
        while j < len(series) and series[j][0] <= t:
            value = series[j][1]
            j += 1
        out.append(value)
    return out


def dimmer_kw(rows: list[dict], watts: float) -> list[tuple[datetime, float]]:
    """Electrical power (kW) of dimmed lights from a ``light`` entity's history.

    Off (or unavailable) is 0; on is ``watts * brightness / 255``, taking LED
    power as roughly proportional to the dimmer level. Rows need ``state``,
    ``last_updated`` and ``attributes``.
    """
    out = []
    for r in rows:
        level = 0.0
        if r.get("state") == "on":
            brightness = (r.get("attributes") or {}).get("brightness")
            level = 1.0 if brightness is None else float(brightness) / 255.0
        when = datetime.fromisoformat(r["last_updated"])
        out.append((when, watts * level / 1000.0))
    return sorted(out)


def on_fraction(
    runs: list[tuple[datetime, datetime]], start: datetime, n: int, step: timedelta
) -> list[float]:
    """Fraction of each of ``n`` steps from ``start`` covered by ``runs``."""
    out = [0.0] * n
    seconds = step.total_seconds()
    for a, b in runs:
        first = max(int((a - start) / step), 0)
        last = min(int((b - start) / step), n - 1)
        for i in range(first, last + 1):
            lo = start + i * step
            overlap = (min(b, lo + step) - max(a, lo)).total_seconds()
            if overlap > 0:
                out[i] = min(out[i] + overlap / seconds, 1.0)
    return out


def chart_points(
    now: datetime,
    step: timedelta,
    past: list[dict[str, float] | None],
    past_temps: list[float | None],
    future: list[dict[str, float]],
    future_temps: list[float],
    every: int = 1,
    digits: int = 2,
) -> list[dict]:
    """Merge history and forecast into a list of points for the chart.

    ``past`` and ``past_temps`` end at now; ``future`` and ``future_temps``
    start at now (that point is not repeated). Only every ``every``-th step is
    kept (counted from now), to keep the attribute small.
    """
    points = []
    n = len(past) - 1
    for i, (c, t) in enumerate(zip(past, past_temps, strict=True)):
        if c is None or t is None or (n - i) % every:
            continue
        when = now - (n - i) * step
        points.append(
            {"t": when.isoformat(), "temp": round(t, digits)}
            | {k: round(v, digits) for k, v in c.items()}
        )
    for i, (c, t) in enumerate(zip(future, future_temps, strict=True)):
        if i == 0 or i % every:
            continue
        points.append(
            {"t": (now + i * step).isoformat(), "temp": round(t, digits), "forecast": 1}
            | {k: round(v, digits) for k, v in c.items()}
        )
    return points
