"""Turn recorded rows into the series the dashboard panel draws.

Standard library only (tested without Home Assistant); ``panel.py`` reads the
recorder and calls these. Times go out as milliseconds since the epoch, the
unit the chart's time axis uses.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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


def heating_spans(rows: list[dict], end: datetime) -> list[list[int]]:
    """``[start ms, end ms]`` of each heating call in a thermostat's history."""
    return [
        [ms(r.start), ms(r.end)]
        for r in runs_from_states(rows, end, {"heating"}, "hvac_action")
    ]


def future(points: list[dict]) -> dict[str, list[Point]]:
    """Split a forecast sensor's ``points`` into the panel's future series."""
    out: dict[str, list[Point]] = {
        k: [] for k in ("temp", "outdoor", "heat", "lower", "upper")
    }
    for p in points:
        when = ms(datetime.fromisoformat(p["t"]))
        for key, line in out.items():
            if p.get(key) is not None:
                line.append([when, p[key]])
    return out
