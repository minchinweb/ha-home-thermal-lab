"""Turn the setup forms' text fields into the values the sensors use.

The web setup (``config_flow.py``) cannot show nested lists, so roofs and
dimmed lights are typed as short text. This module (standard library only, so
it is tested without Home Assistant) converts between that text and the
structures the YAML configuration uses.
"""

from __future__ import annotations

FACES = ("N", "E", "S", "W")
KW_MODES = ("off", "fan", "heat_low", "heat_high", "cool")


class FieldError(ValueError):
    """A text field of a setup form could not be read."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def parse_roofs(text: str) -> list[list]:
    """``"S 30, W 30"`` to ``[["S", 30.0], ["W", 30.0]]``: face and pitch in degrees.

    Raises:
        FieldError: A part is not a face letter followed by a number.
    """
    roofs = []
    for part in text.replace(";", ",").split(","):
        words = part.split()
        if not words:
            continue
        try:
            if len(words) != 2 or words[0].upper() not in FACES:
                raise ValueError
            roofs.append([words[0].upper(), float(words[1])])
        except ValueError:
            raise FieldError("roofs", f"not 'face pitch': {part.strip()!r}") from None
    return roofs


def format_roofs(roofs: list) -> str:
    """The inverse of ``parse_roofs``, for showing a saved value in the form."""
    return ", ".join(f"{face} {pitch:g}" for face, pitch in roofs)


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


def kw_table(values: dict) -> dict[str, float]:
    """Keep only the powers (kW per furnace state) that were filled in."""
    return {
        mode: float(values[mode])
        for mode in KW_MODES
        if values.get(mode) not in (None, "")
    }
