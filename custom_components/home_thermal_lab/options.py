"""Turn the setup forms' text fields into the values the sensors use.

The web setup (``config_flow.py``) cannot show nested lists, so roofs and
dimmed lights are typed as short text. This module (standard library only, so
it is tested without Home Assistant) converts between that text and the
structures the YAML configuration uses.
"""

from __future__ import annotations

import math

FACES = ("N", "E", "S", "W")
KW_MODES = ("off", "fan", "heat_low", "heat_high", "cool")
POWER_UNITS = ("kW", "BTU/h")
BTU_H_TO_KW = 0.00029307
TON_TO_KW = 12000 * BTU_H_TO_KW  # a ton of cooling is 12,000 BTU/h


class FieldError(ValueError):
    """A text field of a setup form could not be read."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _pitch(word: str) -> float:
    """A pitch in degrees (``30``) or as a rise over 12 (``4:12``) or any run."""
    if ":" in word:
        rise, _, run = word.partition(":")
        rise_n, run_n = float(rise), float(run)
        if rise_n < 0 or run_n <= 0:
            raise ValueError
        return math.degrees(math.atan2(rise_n, run_n))
    return float(word)


def parse_roofs(text: str) -> list[list]:
    """``"S 30, W 4:12"`` to ``[["S", 30.0], ["W", 18.43]]``: face and pitch.

    The pitch is in degrees, or a ratio of rise to run such as ``4:12``.

    Raises:
        FieldError: A part is not a face letter followed by a pitch.
    """
    roofs = []
    for part in text.replace(";", ",").split(","):
        words = part.split()
        if not words:
            continue
        try:
            if len(words) != 2 or words[0].upper() not in FACES:
                raise ValueError
            roofs.append([words[0].upper(), _pitch(words[1])])
        except ValueError:
            raise FieldError("roofs", f"not 'face pitch': {part.strip()!r}") from None
    return roofs


def format_roofs(roofs: list) -> str:
    """The inverse of ``parse_roofs``; pitches that are n:12 show that way."""

    def show(pitch: float) -> str:
        for rise in range(25):
            if abs(math.degrees(math.atan2(rise, 12)) - pitch) < 0.01:
                return f"{rise}:12"
        return f"{pitch:g}"

    return ", ".join(f"{face} {show(pitch)}" for face, pitch in roofs)


def resolve_sun(data: dict, house: dict) -> dict:
    """A sub-entry's settings with the house's rotation and roofs filled in.

    The house holds the rotation, the roofs (face and pitch, one per face) and a
    default ``shade_below``. A room lists the faces of the roofs it has windows
    in; this turns them back into ``[face, pitch]`` pairs, as the YAML does. A
    room's own ``shade_below`` wins, and settings saved by an older version (a
    room's own rotation and ``[face, pitch]`` roofs) still work.
    """
    out = dict(data)
    pitches = {face: pitch for face, pitch in house.get("roofs", [])}
    roofs = []
    for roof in data.get("roofs", []):
        if isinstance(roof, str):
            if roof in pitches:
                roofs.append([roof, pitches[roof]])
        else:
            roofs.append(list(roof))
    out["roofs"] = roofs
    if house.get("rotation") is not None:
        out["rotation"] = house["rotation"]
    if "shade_below" not in out and house.get("shade_below") is not None:
        out["shade_below"] = house["shade_below"]
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
        values: The form, with a number for each mode in ``KW_MODES``, and
            optionally ``cool_tons``, cooling in tons (which sets ``cool``).
        unit: ``kW``, or ``BTU/h`` to convert (gas input, for instance).
    """
    factor = BTU_H_TO_KW if unit == "BTU/h" else 1.0
    table = {
        mode: float(values[mode]) * factor
        for mode in KW_MODES
        if values.get(mode) not in (None, "")
    }
    if values.get("cool_tons") not in (None, ""):
        table["cool"] = float(values["cool_tons"]) * TON_TO_KW
    return table
