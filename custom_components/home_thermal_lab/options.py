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


FACE_WORDS = {"N": "North", "E": "East", "S": "South", "W": "West"}


def _auto_name(face: str, taken: set[str]) -> str:
    base = FACE_WORDS[face]
    name, n = base, 2
    while name in taken:
        name, n = f"{base} {n}", n + 1
    return name


def normalise_roofs(roofs: list) -> list[list]:
    """Roofs as ``[name, face, pitch]``; bare ``[face, pitch]`` pairs are named.

    Pairs (from the YAML, or saved by an earlier version) get ``North``,
    ``West``, ``West 2`` and so on, skipping names already in use.
    """
    taken = {r[0] for r in roofs if len(r) == 3}
    out = []
    for roof in roofs:
        if len(roof) == 3:
            out.append(list(roof))
        else:
            name = _auto_name(roof[0], taken)
            taken.add(name)
            out.append([name, roof[0], roof[1]])
    return out


def parse_roofs(text: str) -> list[list]:
    """``"Front=S 30, W 4:12"`` to ``[["Front", "S", 30.0], ["West", "W", 18.43]]``.

    Each roof is a face and a pitch (degrees, or a ratio of rise to run such as
    ``4:12``), with an optional ``name=`` in front. Rooms refer to a roof by its
    name, so a pitch can be edited without losing the link. A roof without a
    name is called after its face (``West``, ``West 2``); the form shows the
    names from then on.

    Raises:
        FieldError: A part is not ``[name=]face pitch``, or a name repeats.
    """
    parts: list[tuple[str | None, str, float]] = []
    for part in text.replace(";", ",").split(","):
        if not part.strip():
            continue
        name, sep, spec = part.rpartition("=")
        words = spec.split()
        try:
            if len(words) != 2 or words[0].upper() not in FACES:
                raise ValueError
            parts.append(
                (
                    name.strip() if sep and name.strip() else None,
                    words[0].upper(),
                    _pitch(words[1]),
                )
            )
        except ValueError:
            raise FieldError(
                "roofs", f"not '[name=]face pitch': {part.strip()!r}"
            ) from None
    given = [n for n, _, _ in parts if n]
    if len(given) != len(set(given)):
        raise FieldError("roofs", "two roofs have the same name")
    taken = set(given)
    roofs = []
    for name, face, pitch in parts:
        if name is None:
            name = _auto_name(face, taken)
            taken.add(name)
        roofs.append([name, face, pitch])
    return roofs


def roof_renames(old: list, new: list) -> dict[str, str]:
    """Which roofs were renamed between two versions of the house's roofs.

    The roofs are edited as text, so a rename looks like one name going and
    another arriving. A name that disappeared is taken to be renamed to a new
    name on the same face (in order); anything else is a roof removed or added.

    Returns:
        Old name to new name.
    """
    old_roofs = normalise_roofs(old)
    new_roofs = normalise_roofs(new)
    kept = {name for name, _, _ in new_roofs} & {name for name, _, _ in old_roofs}
    gone = [(name, face) for name, face, _ in old_roofs if name not in kept]
    added = [
        (name, face)
        for name, face, _ in new_roofs
        if name not in {n for n, _, _ in old_roofs}
    ]
    renames: dict[str, str] = {}
    for name, face in gone:
        for k, (new_name, new_face) in enumerate(added):
            if new_face == face:
                renames[name] = new_name
                del added[k]
                break
    return renames


def roof_label(face: str, pitch: float) -> str:
    """``"W 4:12"``: a roof's name on the forms; n:12 pitches show as a ratio."""
    for rise in range(25):
        if abs(math.degrees(math.atan2(rise, 12)) - pitch) < 0.01:
            return f"{face} {rise}:12"
    return f"{face} {pitch:g}"


def format_roofs(roofs: list) -> str:
    """The inverse of ``parse_roofs``, with every roof's name shown."""
    return ", ".join(
        f"{name}={roof_label(face, pitch)}"
        for name, face, pitch in normalise_roofs(roofs)
    )


def resolve_sun(data: dict, house: dict) -> dict:
    """A sub-entry's settings with the house's rotation and roofs filled in.

    The house holds the rotation, its named roofs (face and pitch; several may
    share a face) and a default ``shade_below``. A room lists the roofs it has
    windows in by name; this turns them into ``[face, pitch]`` pairs, as the
    YAML does, so a pitch edited on the house reaches every room that uses the
    roof. A room's own ``shade_below`` wins. Older saved settings still work: a
    label such as ``"W 4:12"`` finds the roof with that face and pitch, a bare
    face (``"W"``) means every roof on that face, and a room's own ``[face,
    pitch]`` roofs and rotation are kept.
    """
    out = dict(data)
    house_roofs = normalise_roofs(house.get("roofs", []))
    by_name = {name: [face, pitch] for name, face, pitch in house_roofs}
    by_label = {roof_label(f, p): [f, p] for _, f, p in house_roofs}
    roofs: list[list] = []
    for roof in data.get("roofs", []):
        if not isinstance(roof, str):
            roofs.append(list(roof))
        elif roof in by_name:
            roofs.append(list(by_name[roof]))
        elif roof in by_label:
            roofs.append(list(by_label[roof]))
        else:
            face = roof.split()[0].upper() if roof.split() else ""
            roofs += [[f, p] for _, f, p in house_roofs if f == face]
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
