"""Build the Manual J/S/D project from House Structure's published rooms.

Standard library only. House Structure (``hass.data["house_structure"]``)
gives each room's volume, below-ground flag, walls and roofs (area, glass,
azimuth and tilt) and windows (glass, transmittance and the wall or roof they
are in). It does not yet give wall or roof R-values, or a window's glazing and
frame, so those come from ``Nominal``: house-level defaults.

Internal walls are not counted as losses. A neighbouring room is taken to be
at the same temperature, as Manual J does for a heated neighbour.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .manual import (
    Design,
    Element,
    Project,
    Room,
    Run,
    Segment,
    Surface,
    envelope_scale,
    room_capacity,
    ua_from_rate,
    window_u,
)

CFM_TO_M3S = 0.000471947
IN2_TO_M2 = 0.00064516
FT_TO_M = 0.3048

# Imperial R-values converted to m² K/W: R-20 is 3.5, R-35 is 6.2.
R_20_SI = 3.5
R_35_SI = 6.2


@dataclass(frozen=True)
class Nominal:
    """House-level defaults for what House Structure does not yet record.

    Attributes:
        wall_r: Nominal R-value of outside walls, m² K/W.
        roof_r: Nominal R-value of roofs, m² K/W.
        glazing: ``double`` or ``triple``, for every window.
        frame: ``vinyl``, ``wood`` or ``aluminium``, for every window.
        ach: Infiltration, air changes per hour (or from a blower-door test).
        occupants: Occupants per area id, for cooling.
    """

    wall_r: float = R_20_SI
    roof_r: float = R_35_SI
    glazing: str = "double"
    frame: str = "vinyl"
    ach: float = 0.35
    occupants: dict[str, int] = field(default_factory=dict)


def _face(azimuth: float) -> str:
    """The nearest compass face (N, E, S or W) to an azimuth in degrees."""
    return ("N", "E", "S", "W")[round(azimuth / 90.0) % 4]


def _volume(summary: dict) -> float | None:
    """The room's air volume: given, or floor area times height."""
    if summary.get("volume_m3"):
        return summary["volume_m3"]
    if summary.get("floor_m2") and summary.get("height_m"):
        return summary["floor_m2"] * summary["height_m"]
    return None


def build_project(
    rooms: dict[str, dict],
    nominal: Nominal,
    design: Design,
    names: dict[str, str] | None = None,
) -> tuple[Project, list[str]]:
    """A Manual J project from the rooms House Structure publishes.

    Args:
        rooms: House Structure's rooms by area id (``structure_rooms``).
        nominal: House-level defaults for R-values, glazing and infiltration.
        design: Design conditions.
        names: Optional display names by area id (defaults to the room title).

    Returns:
        The project and a list of warnings (rooms skipped, and what was assumed).
    """
    names = names or {}
    warnings: list[str] = []
    built: list[Room] = []
    runs: list[Run] = []
    for area_id, summary in rooms.items():
        name = names.get(area_id) or summary.get("title") or area_id
        volume = _volume(summary)
        if not volume:
            warnings.append(
                f"{name}: no volume, so the room is not in the calculation."
            )
            continue
        below = bool(summary.get("below_ground"))
        surfaces: list[Surface] = []
        for i, wall in enumerate(summary.get("walls", []), start=1):
            net = (wall.get("area_m2") or 0.0) - (wall.get("glass_m2") or 0.0)
            if net > 0:
                r = wall.get("r_value_si") or nominal.wall_r
                surfaces.append(Surface(f"wall {i}", "wall", net, r=r, ground=below))
        for i, roof in enumerate(summary.get("roofs", []), start=1):
            net = (roof.get("area_m2") or 0.0) - (roof.get("glass_m2") or 0.0)
            if net > 0:
                r = roof.get("r_value_si") or nominal.roof_r
                surfaces.append(Surface(f"roof {i}", "roof", net, r=r, face="H"))
        for i, win in enumerate(summary.get("windows", []), start=1):
            glass = win.get("glass_m2") or 0.0
            if glass <= 0:
                continue
            face = "H" if win.get("in") == "roof" else _face(win.get("azimuth") or 0.0)
            glazing = win.get("glazing") or nominal.glazing
            frame = win.get("frame") or nominal.frame
            surfaces.append(
                Surface(
                    f"window {i}",
                    "window",
                    glass,
                    u=window_u(glazing, frame),
                    shgc=win.get("transmittance") or 0.0,
                    face=face,
                )
            )
        if not surfaces:
            warnings.append(f"{name}: no walls, roofs or windows with sizes.")
        room = Room(
            name=name,
            volume=volume,
            surfaces=tuple(surfaces),
            ach=nominal.ach,
            people=nominal.occupants.get(area_id, 0),
        )
        built.append(room)
        for j, reg in enumerate(summary.get("registers", []), start=1):
            if reg.get("duct") and reg.get("free_area_in2"):
                runs.append(_run(reg, name, j))
    if not built:
        raise ValueError("no room has enough data for a Manual J")
    warnings.append(
        "Wall and roof R-values and window glazing and frame are the house defaults, "
        "not measured."
    )
    return Project(rooms=tuple(built), design=design, runs=tuple(runs)), warnings


def _run(reg: dict, room: str, index: int) -> Run:
    """A register's duct as a Manual D run (its segments from the plenum)."""
    segments = []
    for seg in reg["duct"]:
        length = seg["length_ft"] * FT_TO_M
        flow = seg["flow_cfm"] * CFM_TO_M3S if seg.get("flow_cfm") else None
        k = seg.get("fittings_k") or 0.0
        if seg["shape"] == "round":
            segments.append(
                Segment.round_in(
                    seg["diameter_in"], length, k, flow, bool(seg.get("trunk"))
                )
            )
        else:
            segments.append(
                Segment.rect_in(
                    seg["width_in"],
                    seg["height_in"],
                    length,
                    k,
                    flow,
                    bool(seg.get("trunk")),
                )
            )
    flow = reg["flow_cfm"] * CFM_TO_M3S if reg.get("flow_cfm") else None
    return Run(
        name=reg.get("title") or f"{room} register {index}",
        room=room,
        register_area_m2=reg["free_area_in2"] * IN2_TO_M2,
        segments=tuple(segments),
        flow_m3s=flow,
    )


def envelope_from_fit(
    rooms: dict[str, dict],
    rates: dict[str, float],
    capacities: dict[str, float],
    fixed_ua: dict[str, float],
    infiltration: dict[str, float],
    nominal: Nominal,
) -> dict[str, dict]:
    """Each room's measured envelope: its walls' and roofs' R-values, from its fit.

    For each room with a fitted rate ``a`` (per hour, from the zone fit), the
    measured conductance is ``a * C / 3600``. The room's infiltration and
    windows (their nominal U-values, in ``fixed_ua``) come off the top, and the
    walls and roofs are scaled to what is left (``envelope_scale``).

    Args:
        rooms: House Structure's rooms by area id.
        rates: The fitted cooling rate ``a`` per area id, per hour.
        capacities: Each room's heat capacity, J/K (``room_capacities``).
        fixed_ua: Each room's window conductance, W/K (nominal U times area).
        infiltration: Each room's infiltration conductance, W/K (``infiltration_ua``).
        nominal: The house defaults (only the element R-values are scaled).

    Returns:
        By area id: ``scale``, the derived ``elements`` and ``warnings``. Rooms
        without a fitted rate or capacity are left out.
    """
    out: dict[str, dict] = {}
    for area_id, summary in rooms.items():
        if area_id not in rates or area_id not in capacities:
            continue
        elements = []
        for kind, items in (
            ("wall", summary.get("walls", [])),
            ("roof", summary.get("roofs", [])),
        ):
            for i, item in enumerate(items, start=1):
                net = (item.get("area_m2") or 0.0) - (item.get("glass_m2") or 0.0)
                if net <= 0:
                    continue
                r = item.get("r_value_si") or (
                    nominal.wall_r if kind == "wall" else nominal.roof_r
                )
                elements.append(Element(f"{kind} {i}", net, r))
        if not elements:
            continue
        measured = ua_from_rate(rates[area_id], capacities[area_id])
        target_fixed = fixed_ua.get(area_id, 0.0) + infiltration.get(area_id, 0.0)
        out[area_id] = envelope_scale(elements, target_fixed, measured)
    return out


def room_capacities(rooms: dict[str, dict]) -> dict[str, float]:
    """Each room's heat capacity (air only), J/K, by area id."""
    return {
        area_id: room_capacity(volume)
        for area_id, summary in rooms.items()
        if (volume := _volume(summary))
    }
