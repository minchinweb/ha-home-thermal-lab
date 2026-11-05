"""The Heat flow overlay on House Structure's House tab: where heat is going now.

House Structure draws an overlay's flows at its drawing's anchors (see its
``tabs.ordered_overlays``). This works the flows out, in watts for the current
moment, positive into a room:

* ``between``: each pair of rooms that share a wall or a floor, their
  temperature difference times the conductance between them. The
  conductance is the shared area times a nominal U-value (``INTERNAL_WALL_U``
  across a wall, ``FLOOR_U`` through a floor), unless a room's zone has fitted
  the coupling to its neighbours (``n``, hypotheses 06 and 10): then that
  zone's ``n`` is shared out over its neighbours by area. With both rooms
  fitted, the mean of the two is used. Each flow points from the warmer room.
* ``outside``: the zone's fitted loss to outdoors (``a``) times the room's
  difference from the outdoor temperature, shared out over the room's outside
  walls by area, one value per face.
* ``heating``: the zone's learned heating rate ``h`` while its thermostat
  calls for heat. House Structure shares it out over the room's outlets.
* ``solar``: the zone's fitted sun term ``g`` times the light on its windows
  and roofs: the gain the model credits the room with. When House Structure's
  own figure for the glass differs from it by more than half, a note says so.

A fitted rate (per hour) becomes watts through the room's heat capacity, its
air volume times air's (as Manual J's "UA fitted" column does). The
furnishings and walls store heat too, so these watts are low by the same
factor in every room: they compare rooms with each other, not with a meter.

A room with no zone, or whose zone has no model yet, gets only the ``between``
flows, and a note says so. Standard library only.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

# W/m2K, with the air films on both sides: an uninsulated stud partition with
# drywall each side (about R-0.5 m2K/W), and a floor between storeys (joists,
# subfloor and the ceiling below, about R-0.7)
INTERNAL_WALL_U = 2.0
FLOOR_U = 1.4
AIR_HEAT_CAPACITY_J_M3K = 1200.0 * 1005.0  # air at about 20 C
DEFAULT_HEIGHT_M = 2.4  # a room with a floor area but no height
SOLAR_DIFFER = 0.5  # note when the model and the glass differ by more than this
SOLAR_NOTICE_W = 20.0  # ...and the larger of the two is at least this


@dataclass(frozen=True)
class ZoneNow:
    """One zone's fitted terms and what it is doing now.

    Attributes:
        name: The zone's name, for the notes.
        a: Loss to outdoors, per hour.
        g: Warming per W/m2 of light on its windows and roofs, C per hour.
        h: Warming while its furnace call runs, C per hour.
        n: Coupling to the neighbouring zones, per hour (0 when not fitted).
        heating: Whether its thermostat is calling for heat now.
        light: The light on its windows and roofs now, W/m2 (None if unknown).
    """

    name: str
    a: float
    g: float = 0.0
    h: float = 0.0
    n: float = 0.0
    heating: bool = False
    light: float | None = None


def capacity(room: dict) -> float | None:
    """A room's air heat capacity, J/K, from its volume (or floor and height)."""
    volume = room.get("volume_m3")
    if not volume and room.get("floor_m2"):
        height = room.get("height_m") or DEFAULT_HEIGHT_M
        volume = float(room["floor_m2"]) * float(height)
    return float(volume) * AIR_HEAT_CAPACITY_J_M3K if volume else None


def _watts(rate_per_h: float, capacity_j_k: float) -> float:
    """A rate (C per hour, or per hour times a difference) as watts."""
    return rate_per_h * capacity_j_k / 3600.0


def _links(rooms: dict[str, dict]) -> dict[str, list[tuple[str, float, str]]]:
    """Each room's neighbouring rooms: ``(area, shared m2, beside/above/below)``.

    The area is the internal wall's, or for a room above or below, the smaller
    of the two floors. A neighbour that isn't a room (a garage with no parts),
    or with no area to go by, is left out.
    """
    out: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for area, room in rooms.items():
        walls: dict[str, float] = defaultdict(float)
        for wall in room.get("internal_walls") or []:
            walls[wall.get("other_area_id")] += float(wall.get("area_m2") or 0.0)
        for item in room.get("neighbours") or []:
            other = item.get("area_id")
            if other not in rooms or other == area:
                continue
            position = item.get("position") or "beside"
            shared = item.get("area_m2") or walls.get(other)
            if not shared and position != "beside":
                floors = [rooms[k].get("floor_m2") for k in (area, other)]
                shared = min(float(f) for f in floors) if all(floors) else None
            if shared:
                out[area].append((other, float(shared), position))
    return out


def _between(
    rooms: dict[str, dict],
    temperatures: dict[str, float],
    zones: dict[str, ZoneNow],
    capacities: dict[str, float],
) -> list[dict]:
    links = _links(rooms)
    # each room's fitted conductance to each neighbour, W/K
    fitted: dict[tuple[str, str], float] = {}
    for area, items in links.items():
        zone = zones.get(area)
        if zone is None or zone.n <= 0 or area not in capacities:
            continue
        total = sum(shared for _, shared, _ in items)
        for other, shared, _ in items:
            fitted[(area, other)] = _watts(zone.n, capacities[area]) * shared / total
    out = []
    seen: set[tuple[str, str]] = set()
    for area, items in links.items():
        for other, shared, position in items:
            pair = tuple(sorted((area, other)))
            if pair in seen:
                continue
            seen.add(pair)
            if area not in temperatures or other not in temperatures:
                continue
            fits = [fitted[k] for k in ((area, other), (other, area)) if k in fitted]
            if fits:
                ua = sum(fits) / len(fits)
            else:
                ua = shared * (INTERNAL_WALL_U if position == "beside" else FLOOR_U)
            w = ua * (temperatures[area] - temperatures[other])
            warm, cool = (area, other) if w >= 0 else (other, area)
            out.append({"from": warm, "to": cool, "w": round(abs(w), 1)})
    return out


def _faces(room: dict) -> dict[str, float]:
    """A room's outside walls by face, with their area (1 each if none is typed)."""
    faces: dict[str, float] = defaultdict(float)
    walls = [w for w in room.get("walls") or [] if w.get("face")]
    sized = any(w.get("area_m2") for w in walls)
    for wall in walls:
        faces[wall["face"]] += float(wall.get("area_m2") or 0.0) if sized else 1.0
    return {face: m2 for face, m2 in faces.items() if m2 > 0}


def flows(
    rooms: dict[str, dict],
    names: dict[str, str],
    temperatures: dict[str, float],
    outdoor: float | None,
    zones: dict[str, ZoneNow],
    glass: dict[str, float] | None = None,
) -> dict:
    """The Heat flow overlay's answer, without ``as_of``.

    Args:
        rooms: House Structure's rooms by area id (its summary's ``rooms``).
        names: The rooms' names by area id, for the notes.
        temperatures: Each room's temperature now, C, where known.
        outdoor: The outdoor temperature now, C.
        zones: The fitted zones by their room's area id.
        glass: House Structure's sun through each room's windows now, W.

    Returns:
        ``{"between", "outside", "heating", "solar", "notes"}``, as House
        Structure's overlay contract has them.
    """
    glass = glass or {}
    notes: list[str] = []
    capacities = {area: c for area in rooms if (c := capacity(rooms[area])) is not None}
    outside, heating, solar = [], [], []
    unfitted, no_size, no_walls = [], [], []

    def name(area: str) -> str:
        return names.get(area) or rooms[area].get("title") or area

    for area in sorted(rooms, key=name):
        zone = zones.get(area)
        if zone is None:
            unfitted.append(name(area))
            continue
        if area not in capacities:
            no_size.append(name(area))
            continue
        cap = capacities[area]
        room_t = temperatures.get(area)
        faces = _faces(rooms[area])
        if room_t is not None and outdoor is not None:
            if not faces:
                no_walls.append(name(area))
            else:
                total = _watts(zone.a * (outdoor - room_t), cap)
                whole = sum(faces.values())
                outside += [
                    {"room": area, "face": face, "w": round(total * m2 / whole, 1)}
                    for face, m2 in sorted(faces.items())
                ]
        if zone.heating and zone.h > 0:
            heating.append({"room": area, "w": round(_watts(zone.h, cap), 1)})
        if zone.light is not None and zone.g > 0:
            model = _watts(zone.g * zone.light, cap)
            if model > 0:
                solar.append({"room": area, "w": round(model, 1)})
            seen = glass.get(area)
            larger = max(model, seen or 0.0)
            if (
                seen is not None
                and larger >= SOLAR_NOTICE_W
                and abs(model - seen) > SOLAR_DIFFER * larger
            ):
                notes.append(
                    f"{name(area)}: the model credits {model:.0f} W of sun, "
                    f"House Structure's windows let in {seen:.0f} W."
                )
    if unfitted:
        notes.append(
            "No fitted zone yet, so only the flows through inside walls and "
            "floors: " + ", ".join(unfitted) + "."
        )
    if no_size:
        notes.append(
            "No volume or floor area in House Structure, so the fit can't be "
            "turned into watts: " + ", ".join(no_size) + "."
        )
    if no_walls:
        notes.append(
            "No outside walls in House Structure, so the loss to outdoors isn't "
            "drawn: " + ", ".join(no_walls) + "."
        )
    if outdoor is None:
        notes.append("No outdoor temperature now, so no loss to outdoors.")
    missing = sorted(name(a) for a in rooms if a not in temperatures)
    if missing:
        notes.append("No temperature now: " + ", ".join(missing) + ".")
    notes.append(
        "Watts from the fit use each room's air alone as its heat capacity, so "
        "they compare rooms rather than match a meter."
    )
    return {
        "between": _between(rooms, temperatures, zones, capacities),
        "outside": outside,
        "heating": heating,
        "solar": solar,
        "notes": notes,
    }
