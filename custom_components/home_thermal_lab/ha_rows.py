"""Read Home Assistant's recorder into plain rows (needs Home Assistant).

Rows are dicts with ``state``, ``last_changed``, ``last_updated`` and
``attributes``, the shape the standard-library modules (``hvac.py``,
``calls.py``) and the scripts' REST loader use.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial

from homeassistant.components.recorder import get_instance, history


def as_dict(state) -> dict:
    """A Home Assistant state as a plain row."""
    return {
        "state": state.state,
        "last_changed": state.last_changed.isoformat(),
        "last_updated": state.last_updated.isoformat(),
        "attributes": dict(state.attributes),
    }


async def recorded(hass, entity_ids: list[str], start: datetime, end: datetime):
    """Every recorded state (attribute changes too) per entity, as dicts."""
    found = await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            end,
            entity_ids,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )
    return {e: [as_dict(s) for s in found.get(e, [])] for e in entity_ids}


def numbers(rows: list[dict]) -> list[tuple[datetime, float]]:
    """``(time, value)`` for every row with a number for its state, oldest first."""
    out = []
    for r in rows:
        try:
            value = float(r["state"])
        except (TypeError, ValueError):
            continue
        out.append((datetime.fromisoformat(r["last_changed"]).astimezone(UTC), value))
    return sorted(out)
