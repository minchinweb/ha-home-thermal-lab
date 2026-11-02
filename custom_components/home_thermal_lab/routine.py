"""The house's routine: the profile forecast (D) and the hybrid (hypothesis 16).

Standard library only. Values are binned series (one per quarter-hour, None
where unknown), and ``origin`` is the first bin to forecast: everything before
it is known.

* ``typical``: the mean of the last ``days`` days at each quarter-hour ahead.
* ``offset_path``: predictor D, the typical day plus the gap between the room
  now and its typical value, fading with time constant ``tau``. In the
  backtests this beat every physical model: it carries what the models do not
  know (people, cooking, the thermostat's habits).
* ``hybrid``: D plus what the zone model says *differs* today: the model run
  with today's forecast and setpoints, minus the model run from the same start
  with the typical day's weather and setpoints. A cold snap or a changed
  setpoint moves the forecast; the routine is left to D.
"""

from __future__ import annotations

import math

PER_DAY = 96
OFFSET_TAUS = (2.0, 4.0, 8.0, 16.0, 32.0, 64.0)  # hours


def typical(
    values: list, origin: int, steps: int, days: int = 7, per_day: int = PER_DAY
) -> list[float | None]:
    """Mean of the previous ``days`` days at the time of day of each step ahead.

    Only bins before ``origin`` count. Step ``k`` (bin ``origin + k``) averages
    the bins one, two, ... days earlier.
    """
    out: list[float | None] = []
    for k in range(steps):
        seen = []
        for d in range(1, days + 1):
            j = origin + k - d * per_day
            if 0 <= j < origin and values[j] is not None:
                seen.append(values[j])
        out.append(sum(seen) / len(seen) if seen else None)
    return out


def offset_path(
    profile: list[float | None],
    last: float,
    last_typical: float | None,
    step_hours: float,
    tau: float,
) -> list[float | None]:
    """Predictor D: the typical day plus the gap now, fading over ``tau`` hours.

    Args:
        profile: Typical value of each step ahead (``typical``).
        last: The value just before the first step (now).
        last_typical: Its typical value (``typical`` from one bin earlier).
        step_hours: Step length.
        tau: Fading time of the gap, hours.
    """
    gap = 0.0 if last_typical is None else last - last_typical
    return [
        None if p is None else p + gap * math.exp(-k * step_hours / tau)
        for k, p in enumerate(profile)
    ]


def forecast_d(
    values: list,
    origin: int,
    steps: int,
    step_hours: float,
    tau: float,
    days: int = 7,
) -> list[float | None]:
    """Predictor D from ``origin`` (the value at ``origin - 1`` is "now")."""
    last = values[origin - 1]
    if last is None:
        return [None] * steps
    profile = typical(values, origin, steps, days)
    before = typical(values, origin - 1, 1, days)[0]
    return offset_path(profile, last, before, step_hours, tau)


def fit_offset_tau(
    values: list,
    origins: list[int],
    steps: int,
    step_hours: float,
    taus: tuple[float, ...] = OFFSET_TAUS,
    days: int = 7,
) -> float:
    """The fading time of D that fits the forecasts from ``origins`` best."""

    def sse(tau: float) -> float:
        total = 0.0
        for o in origins:
            path = forecast_d(values, o, steps, step_hours, tau, days)
            for k, p in enumerate(path):
                j = o + k
                if p is not None and j < len(values) and values[j] is not None:
                    total += (values[j] - p) ** 2
        return total

    return min(taus, key=sse) if origins else 8.0


def hybrid(
    d_path: list[float | None], today: list[float], usual: list[float]
) -> list[float | None]:
    """D plus the model's departure: ``today`` minus ``usual``, step by step.

    ``today`` and ``usual`` are model paths from the same start (one more point
    than steps, the start first); ``d_path`` has one value per step.
    """
    out: list[float | None] = []
    for k, d in enumerate(d_path):
        if d is None or k + 1 >= len(today) or k + 1 >= len(usual):
            out.append(d)
        else:
            out.append(d + today[k + 1] - usual[k + 1])
    return out


def fill(values: list[float | None], fallback: float) -> list[float]:
    """Unknown values replaced by the last known one (or ``fallback``)."""
    out = []
    last = fallback
    for v in values:
        if v is not None:
            last = v
        out.append(last)
    return out
