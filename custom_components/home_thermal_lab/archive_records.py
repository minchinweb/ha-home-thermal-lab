"""Build the archive's records (standard library only).

The room record and the forecast sensor's attributes share some names
(``start``, ``setpoint``, ``method``, ``neighbours``, the leads). ``shared``
builds those once, for both, so the two cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime

from . import archive

PARAM_NAMES = ("a", "b", "n", "x", "c", "g", "w", "h", "e", "y", "f")


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def shared(
    start: float,
    setpoint: float | None,
    method: str,
    neighbours: list[str],
    leads: dict[int, float | None],
) -> dict:
    """The names a room record and the sensor's attributes have in common."""
    return {
        "start": round(start, 2),
        "setpoint": setpoint,
        "method": method,
        "neighbours": list(neighbours),
        "predicted_1h": _round(leads.get(1)),
        "predicted_6h": _round(leads.get(6)),
    }


def lead_map(leads: dict[int, float | None]) -> dict[str, float | None]:
    """``{"1": t, "3": t, "6": t}`` rounded, with null where there is none."""
    return {str(k): _round(v) for k, v in leads.items()}


def room_record(
    *,
    at: datetime,
    zone: str,
    name: str,
    shared_fields: dict,
    fallback: str | None,
    outdoor_at: datetime | None,
    outdoor_shift: float,
    fit_at: str | None,
    params: dict[str, float | None],
    leads: dict[int, float | None],
    leads_d: dict[int, float | None],
    path: list[list] | None = None,
) -> dict:
    """One ``room`` record."""
    record = {
        "v": archive.SCHEMA,
        "kind": "room",
        "at": at.isoformat(),
        "zone": zone,
        "name": name,
        "method": shared_fields["method"],
        "fallback": fallback,
        "start": shared_fields["start"],
        "setpoint": shared_fields["setpoint"],
        "program": "yesterday",
        "outdoor_at": None if outdoor_at is None else outdoor_at.isoformat(),
        "outdoor_shift": round(outdoor_shift, 2),
        "fit_at": fit_at,
        "params": {k: _round(params.get(k), 6) for k in PARAM_NAMES},
        "neighbours": shared_fields["neighbours"],
        "leads": lead_map(leads),
        "leads_d": lead_map(leads_d),
    }
    if path is not None:
        record["path"] = path
    return record


def outdoor_record(
    *,
    at: datetime,
    model: str,
    lat: float,
    lon: float,
    bias: float | None,
    bias_hours: int,
    hours: list[tuple[datetime, float, float, float, float]],
) -> dict:
    """One ``outdoor`` record; ``hours`` are the forecast hours only."""
    return {
        "v": archive.SCHEMA,
        "kind": "outdoor",
        "at": at.isoformat(),
        "source": "open-meteo",
        "model": model,
        "lat": lat,
        "lon": lon,
        "bias": _round(bias, 3),
        "bias_hours": bias_hours,
        "hours": [
            [t.isoformat(), _round(temp), _round(dni, 1), _round(diff, 1), _round(c, 0)]
            for t, temp, dni, diff, c in hours
        ],
    }


def path_points(temps: list[float], step_minutes: int = 15) -> list[list]:
    """The full path as ``[[minutes_ahead, t], …]``."""
    return [[k * step_minutes, round(t, 2)] for k, t in enumerate(temps)]


def d_leads(
    room: float, d: list[float | None] | None, leads: tuple[int, ...], step_hours: float
) -> dict[int, float | None]:
    """D's temperature at each lead (null where D has none)."""
    out: dict[int, float | None] = {}
    for lead in leads:
        k = round(lead / step_hours)  # d[k - 1] is the step k after now
        out[lead] = d[k - 1] if d is not None and 0 < k <= len(d) else None
    return out
