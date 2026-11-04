"""Turn recorded rows into the series the dashboard panel draws.

Standard library only (tested without Home Assistant); ``panel.py`` reads the
recorder and calls these. Times go out as milliseconds since the epoch, the
unit the chart's time axis uses.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math

from .hvac import runs_from_states

Point = list[float]  # [milliseconds, value]


def ms(when: datetime) -> int:
    """Milliseconds since the epoch."""
    return int(when.timestamp() * 1000)


def _value(row: dict, attribute: str | None) -> float | None:
    raw = (
        row.get("state")
        if attribute is None
        else (row.get("attributes") or {}).get(attribute)
    )
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def series(rows: list[dict], attribute: str | None = None) -> list[Point]:
    """``[ms, value]`` for every row with a number (the state, or an attribute).

    Consecutive repeats of the same value are dropped (attribute-only changes
    write rows that repeat the state); a missing value breaks the line (None).
    """
    out: list = []
    last = object()
    for row in rows:
        when = datetime.fromisoformat(row["last_updated"])
        value = _value(row, attribute)
        if value == last:
            continue
        out.append([ms(when), value])
        last = value
    return out


def archive(rows: list[dict]) -> list[Point]:
    """Forecasts as issued: each 3 hour forecast at the time it was made for.

    Rows are a forecast sensor's history (``issued`` attribute, state the
    forecast 3 hours on), so the chart can lay what was predicted over what
    happened, as ClimateAdvisor's dashed "predicted" lines do.
    """
    out = []
    seen = set()
    for row in rows:
        stamp = (row.get("attributes") or {}).get("issued")
        value = _value(row, None)
        if not stamp or value is None or stamp in seen:
            continue
        seen.add(stamp)
        out.append([ms(datetime.fromisoformat(stamp) + timedelta(hours=3)), value])
    return sorted(out)


def action_spans(rows: list[dict], end: datetime, action: str) -> list[list[int]]:
    """``[start ms, end ms]`` of each run of a thermostat's ``hvac_action``."""
    return [
        [ms(r.start), ms(r.end)]
        for r in runs_from_states(rows, end, {action}, "hvac_action")
    ]


def heating_spans(rows: list[dict], end: datetime) -> list[list[int]]:
    """``[start ms, end ms]`` of each heating call in a thermostat's history."""
    return action_spans(rows, end, "heating")


def merge_spans(spans: list[list[int]]) -> list[list[int]]:
    """The spans as one sorted list, with overlapping and touching ones joined."""
    out: list[list[int]] = []
    for start, stop in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], stop)
        else:
            out.append([start, stop])
    return out


def subtract_spans(spans: list[list[int]], cover: list[list[int]]) -> list[list[int]]:
    """The parts of ``spans`` that ``cover`` does not reach."""
    holes = merge_spans(cover)
    out: list[list[int]] = []
    for start, stop in merge_spans(spans):
        at = start
        for hole_start, hole_stop in holes:
            if hole_stop <= at or hole_start >= stop:
                continue
            if hole_start > at:
                out.append([at, hole_start])
            at = max(at, hole_stop)
            if at >= stop:
                break
        if at < stop:
            out.append([at, stop])
    return out


def span(values, step: float = 1.0) -> list[float] | None:
    """``[low, high]`` around ``values``, out to whole multiples of ``step``.

    The panel's fixed temperature axes: every zone's indoor chart uses one span,
    and the outdoor chart one span all year. ``None`` values are skipped;
    ``None`` comes back when nothing is left.
    """
    found = [v for v in values if v is not None and math.isfinite(v)]
    if not found:
        return None
    low = math.floor(min(found) / step) * step
    high = math.ceil(max(found) / step) * step
    if high <= low:
        high = low + step
    return [low, high]


def statistic_values(rows: list[dict]) -> list[float]:
    """Every ``min`` and ``max`` in long-term statistics rows."""
    out = []
    for row in rows:
        for key in ("min", "max"):
            value = row.get(key)
            if value is not None:
                out.append(float(value))
    return out


def setpoints(rows: list[dict]) -> list[float]:
    """Every heating and cooling setpoint in a thermostat's history."""
    out = []
    for row in rows:
        attrs = row.get("attributes") or {}
        for key in ("temperature", "target_temp_low", "target_temp_high"):
            try:
                out.append(float(attrs[key]))
            except (KeyError, TypeError, ValueError):
                continue
    return out


def same_thermostat(
    rooms: dict[str, dict], climate: str, skip: set[str]
) -> list[tuple[str, str]]:
    """``(area id, temperature sensor)`` of House Structure's rooms on ``climate``.

    A room is on the thermostat when one of its registers names it. Rooms
    without a temperature sensor, and sensors in ``skip`` (the zone's own), are
    left out; rooms come in area id order.
    """
    out = []
    for area_id, room in sorted(rooms.items()):
        sensor = room.get("temperature_entity")
        if not sensor or sensor in skip:
            continue
        if any(r.get("climate") == climate for r in room.get("registers", [])):
            out.append((area_id, sensor))
    return out


def future(points: list[dict]) -> dict[str, list[Point]]:
    """Split a forecast sensor's ``points`` into the panel's future series."""
    out: dict[str, list[Point]] = {
        k: [] for k in ("temp", "outdoor", "heat", "cool", "fan", "lower", "upper")
    }
    for p in points:
        when = ms(datetime.fromisoformat(p["t"]))
        for key, line in out.items():
            if p.get(key) is not None:
                line.append([when, p[key]])
    return out
