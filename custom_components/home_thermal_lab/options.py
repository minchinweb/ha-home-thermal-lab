"""Turn the setup forms' text fields into the values the sensors use.

The web setup (``config_flow.py``) cannot show nested lists, so dimmed lights
are typed as short text. This module (standard library only, so
it is tested without Home Assistant) converts between that text and the
structures the YAML configuration uses.
"""

from __future__ import annotations

KW_MODES = ("off", "fan", "heat_low", "heat_high", "cool")
POWER_UNITS = ("kW", "BTU/h")
# the house's ground-temperature wave, shared by its below-ground rooms
GROUND_KEYS = ("ground_mean", "ground_swing", "ground_coldest_day")
BTU_H_TO_KW = 0.00029307


class FieldError(ValueError):
    """A text field of a setup form could not be read."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def with_house(data: dict, house: dict) -> dict:
    """A sub-entry's settings with the house's ground wave filled in.

    The integration holds the ground-temperature wave shared by the house's
    below-ground rooms; a room's own values win. The house's rotation and roofs
    are House Structure's (``from_structure``).
    """
    out = dict(data)
    for key in GROUND_KEYS:
        if key not in out and house.get(key) is not None:
            out[key] = house[key]
    return out


def parse_lights(text: str) -> dict[str, float]:
    """``"light.office=105, light.hall=40"`` to ``{entity: watts at full}``.

    Raises:
        FieldError: A part is not ``light.some_id=watts``.
    """
    lights = {}
    for part in text.replace(";", ",").split(","):
        if not part.strip():
            continue
        entity, sep, watts = part.partition("=")
        entity = entity.strip()
        try:
            if not sep or not entity.startswith("light."):
                raise ValueError
            lights[entity] = float(watts)
        except ValueError:
            raise FieldError(
                "lights", f"not 'light.id=watts': {part.strip()!r}"
            ) from None
    return lights


def format_lights(lights: dict) -> str:
    """The inverse of ``parse_lights``."""
    return ", ".join(f"{entity}={watts:g}" for entity, watts in lights.items())


def kw_table(values: dict, unit: str = "kW") -> dict[str, float]:
    """The powers (kW per furnace state) that were filled in.

    Args:
        values: The form, with a number for each mode in ``KW_MODES``.
        unit: ``kW``, or ``BTU/h`` to convert (gas input, for instance).
    """
    factor = BTU_H_TO_KW if unit == "BTU/h" else 1.0
    return {
        mode: float(values[mode]) * factor
        for mode in KW_MODES
        if values.get(mode) not in (None, "")
    }


# House Structure (https://github.com/minchinweb/ha-house-structure) publishes
# each room's parts in ``hass.data[STRUCTURE_DOMAIN]``, version 1.
STRUCTURE_DOMAIN = "house_structure"
STRUCTURE_EVENT = "house_structure_updated"
STRUCTURE_VERSION = 1


def structure_rooms(data: dict | None) -> dict[str, dict]:
    """House Structure's rooms by area id, or nothing if it is not set up."""
    if not data or data.get("version") != STRUCTURE_VERSION:
        return {}
    return data.get("rooms") or {}


def _planes(parts: list[dict]) -> list[list[float]]:
    """Distinct ``[azimuth, tilt, shade_below]`` planes, in order."""
    out: list[list[float]] = []
    for part in parts:
        plane = [
            float(part["azimuth"]),
            float(part["tilt"]),
            float(part.get("shade_below") or 0.0),
        ]
        if plane not in out:
            out.append(plane)
    return out


def _solid_m2(wall: dict) -> float | None:
    """A wall's area less its windows and doors, or ``None`` with no area."""
    if not wall.get("area_m2"):
        return None
    open_m2 = float(wall.get("glass_m2") or 0.0) + float(wall.get("door_m2") or 0.0)
    return max(float(wall["area_m2"]) - open_m2, 0.0)


def wall_planes(walls: list[dict]) -> list[list[float]]:
    """``[azimuth, tilt, shade_below, share]`` of a room's outside walls.

    The light on the walls is each wall's light times its share: its solid area
    (less its windows and doors) over the room's solid outside wall. So the sun
    on the wall around a window warms the room through the wall (the lagged
    ``w`` term), whether or not the blind is open, while the glass stays in the
    ``g`` term. A wall without an area takes the mean of the others' solid
    area, less its own glass. With no areas at all, each windowless wall counts
    the same and a wall with a window is left out, as it can't be split. Walls
    facing the same way are one plane, with their shares added.
    """
    known = [m2 for m2 in map(_solid_m2, walls) if m2 is not None]
    mean = sum(known) / len(known) if known else None
    solid = []
    for wall in walls:
        m2 = _solid_m2(wall)
        if m2 is None and mean is not None:
            m2 = max(mean - float(wall.get("glass_m2") or 0.0), 0.0)
        elif m2 is None:
            m2 = 0.0 if wall.get("glass_m2") else 1.0
        solid.append(m2)
    total = sum(solid)
    out: list[list[float]] = []
    for wall, m2 in zip(walls, solid, strict=True):
        if m2 <= 0:
            continue
        plane = [
            float(wall["azimuth"]),
            float(wall["tilt"]),
            float(wall.get("shade_below") or 0.0),
        ]
        for seen in out:
            if seen[:3] == plane:
                seen[3] += m2 / total
                break
        else:
            out.append([*plane, m2 / total])
    return [[*p[:3], round(p[3], 4)] for p in out]


def sensor_choices(data: dict, room: dict) -> list[str]:
    """The area's temperature sensors, when the zone can't tell which is its own.

    Empty when the zone picks its own room sensor, House Structure has one for
    the room (chosen in the area's settings, or the area's only one), or the
    area has none: then the thermostat's own reading is used without a doubt.
    """
    if data.get("room_entity") or room.get("temperature_entity"):
        return []
    choices = list(room.get("temperature_choices") or [])
    return choices if len(choices) > 1 else []


def from_structure(data: dict, room: dict, ground: bool = True) -> dict:
    """A zone's settings, filled in from its area's room in House Structure.

    The room's windows and roofs become the zone's window planes (the ``g``
    term), its outside walls its sunlit walls (``w``, by solid area; see
    ``wall_planes``), and its
    ``below_ground`` setting the zone's. The thermostat comes from the room's
    first register and the room sensor from the area, unless the zone names
    its own. House Structure's planes are already turned by the house's
    rotation (compass azimuths).

    Args:
        data: The zone's own settings (after ``with_house``).
        room: The room's summary.
        ground: Whether this kind of sensor takes ``below_ground``.
    """
    out = dict(data)
    if not out.get("climate_entity"):
        climates = [r["climate"] for r in room.get("registers", []) if r.get("climate")]
        if climates:
            out["climate_entity"] = climates[0]
    if not out.get("room_entity") and room.get("temperature_entity"):
        out["room_entity"] = room["temperature_entity"]
    if ground:
        out["below_ground"] = bool(room.get("below_ground"))
    windows = room.get("windows", []) + room.get("roofs", [])
    out["window_planes"] = _planes(windows)
    out["wall_planes"] = wall_planes(room.get("walls", []))
    return out


def has_walls(zone: dict) -> bool:
    """Whether the zone has sunlit solid walls (the lagged ``w`` term)."""
    return bool(zone.get("wall_planes"))
