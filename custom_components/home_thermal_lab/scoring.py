"""Score forecasts as they were issued, and correct the outdoor forecast.

Standard library only. Two ideas from ClimateAdvisor (hypothesis 16):

* **Forecasts as issued.** A forecast is only tested fairly against what was
  known when it was made. The forecast sensor's recorded history *is* that
  archive: each state is the room temperature it predicted some hours ahead.
  ``score`` matches each one with the room temperature when that time came, and
  reports the mean absolute error, the mean signed error (bias) and the error
  in the predicted *change* (ClimateAdvisor's measure, which leaves out any
  error in the starting reading).
* **Outdoor forecast bias.** ``outdoor_bias`` compares the forecast's recent
  hours with the outdoor sensor; ``apply_bias`` shifts the forecast by that
  amount when it is large enough to matter and there is enough to go on.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
import math

from .learn import bin_held

Series = list[tuple[datetime, float]]


@dataclass(frozen=True)
class Issued:
    """One forecast as it was made.

    Attributes:
        issued: When it was made.
        lead_hours: How far ahead it looked.
        predicted: The room temperature it predicted for ``issued + lead``.
        start: The room temperature when it was made, if known.
    """

    issued: datetime
    lead_hours: float
    predicted: float
    start: float | None = None


@dataclass(frozen=True)
class Score:
    """Errors of the forecasts at one lead.

    Attributes:
        mae: Mean absolute error, C.
        bias: Mean of predicted minus actual, C (positive: forecasts ran warm).
        rmse: Root mean square error, C.
        change_mae: Mean absolute error of the predicted change from the start,
            C; None when no forecast recorded its start.
        n: Forecasts scored.
    """

    mae: float
    bias: float
    rmse: float
    change_mae: float | None
    n: int


def held_at(series: Series, when: datetime, max_age: timedelta) -> float | None:
    """The last reading at or before ``when``, if not older than ``max_age``."""
    times = [t for t, _ in series]
    k = bisect_right(times, when) - 1
    if k < 0 or when - series[k][0] > max_age:
        return None
    return series[k][1]


def score(
    issued: list[Issued],
    actual: Series,
    now: datetime,
    max_age: timedelta = timedelta(hours=6),
) -> dict[float, Score]:
    """Score every forecast whose time has come, grouped by lead.

    Args:
        issued: The forecasts as made.
        actual: The room temperature readings, oldest first.
        now: Forecasts for later than this are not scored yet.
        max_age: Oldest reading to take as the temperature at a time (a sensor
            that reports only on a change holds its value).
    """
    errors: dict[float, list[float]] = {}
    changes: dict[float, list[float]] = {}
    for f in issued:
        due = f.issued + timedelta(hours=f.lead_hours)
        if due > now:
            continue
        value = held_at(actual, due, max_age)
        if value is None:
            continue
        errors.setdefault(f.lead_hours, []).append(f.predicted - value)
        if f.start is not None:
            then = held_at(actual, f.issued, max_age)
            if then is not None:
                changes.setdefault(f.lead_hours, []).append(
                    (f.predicted - f.start) - (value - then)
                )
    out = {}
    for lead, errs in sorted(errors.items()):
        moves = changes.get(lead)
        out[lead] = Score(
            sum(abs(e) for e in errs) / len(errs),
            sum(errs) / len(errs),
            math.sqrt(sum(e * e for e in errs) / len(errs)),
            sum(abs(e) for e in moves) / len(moves) if moves else None,
            len(errs),
        )
    return out


def outdoor_bias(
    measured: Series,
    forecast: list[tuple[datetime, float]],
    since: datetime,
    until: datetime,
) -> tuple[float, int]:
    """Mean of measured minus forecast outdoor temperature over past hours.

    Args:
        measured: Outdoor sensor readings, oldest first.
        forecast: ``(hour end, temperature)`` per forecast hour (Open-Meteo's
            hourly values, as the hour ending at that time).
        since: Earliest hour end to compare.
        until: Latest hour end to compare (normally now).

    Returns:
        The bias (positive: the sensor reads warmer than the forecast) and the
        number of hours compared.
    """
    diffs = []
    hour = timedelta(hours=1)
    for end, temp in forecast:
        if not since <= end <= until:
            continue
        mean = bin_held(measured, end - hour, 1, hour)[0]
        if mean is not None:
            diffs.append(mean - temp)
    if not diffs:
        return 0.0, 0
    return sum(diffs) / len(diffs), len(diffs)


def apply_bias(
    temps: list[float],
    bias: float,
    hours: int,
    min_hours: int = 12,
    min_abs: float = 0.3,
    cap: float = 4.0,
) -> tuple[list[float], float]:
    """Shift forecast temperatures by the measured bias, within limits.

    As ClimateAdvisor's weather-bias correction: nothing below ``min_abs`` or
    with fewer than ``min_hours`` compared, and never more than ``cap``.

    Returns:
        The temperatures and the correction applied.
    """
    if hours < min_hours or abs(bias) < min_abs:
        return list(temps), 0.0
    shift = max(-cap, min(cap, bias))
    return [t + shift for t in temps], shift


def issued_from_rows(rows: list[dict]) -> list[Issued]:
    """The forecasts in a forecast sensor's recorded history.

    Each row is a recorded state as a dict (``state`` and ``attributes``): the
    state is the forecast 3 hours ahead, the attributes hold ``issued``,
    ``start``, ``predicted_1h`` and ``predicted_6h``. A row repeated for the same
    ``issued`` (an attribute-only change) counts once.
    """
    out = []
    seen = set()
    for r in rows:
        attrs = r.get("attributes") or {}
        stamp = attrs.get("issued")
        if not stamp or stamp in seen:
            continue
        seen.add(stamp)
        issued = datetime.fromisoformat(stamp)
        start = attrs.get("start")
        for lead, value in (
            (3.0, r.get("state")),
            (1.0, attrs.get("predicted_1h")),
            (6.0, attrs.get("predicted_6h")),
        ):
            try:
                predicted = float(value)
            except (TypeError, ValueError):
                continue
            out.append(Issued(issued, lead, predicted, start))
    return out
