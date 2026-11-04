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
    rho_cp,
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


def _height(summary: dict) -> float | None:
    """The room's height: given, or volume over floor area."""
    if summary.get("height_m"):
        return summary["height_m"]
    volume = _volume(summary)
    if volume and summary.get("floor_m2"):
        return volume / summary["floor_m2"]
    return None


def ground_fraction(summary: dict) -> float:
    """The share (0 to 1) of a room's walls that are below grade.

    A basement with a below-grade depth has its walls below the grade line for
    that depth, so the share is the depth over the room's height. Without a
    depth, a below-ground room's walls are all taken as below grade.
    """
    if not summary.get("below_ground"):
        return 0.0
    depth = summary.get("below_grade_m")
    height = _height(summary)
    if depth is None or not height:
        return 1.0
    return min(max(depth / height, 0.0), 1.0)


def build_project(
    rooms: dict[str, dict],
    nominal: Nominal,
    design: Design,
    names: dict[str, str] | None = None,
    ducts: dict[str, dict] | None = None,
) -> tuple[Project, list[str]]:
    """A Manual J project from the rooms House Structure publishes.

    Args:
        rooms: House Structure's rooms by area id (``structure_rooms``).
        nominal: House-level defaults for R-values, glazing and infiltration.
        design: Design conditions.
        names: Optional display names by area id (defaults to the room title).
        ducts: House Structure's shared duct sections by name (``ducts`` in its
            summary); registers name the section they hang off.

    Returns:
        The project and a list of warnings (rooms skipped, and what was assumed).
    """
    names = names or {}
    warnings: list[str] = []
    built: list[Room] = []
    pending: list[tuple[dict, str, int]] = []
    for area_id, summary in rooms.items():
        name = names.get(area_id) or summary.get("title") or area_id
        volume = _volume(summary)
        if not volume:
            warnings.append(
                f"{name}: no volume, so the room is not in the calculation."
            )
            continue
        below = ground_fraction(summary)
        if summary.get("below_ground") and summary.get("below_grade_m") is None:
            warnings.append(
                f"{name}: no below-grade depth, so all its walls are taken as below "
                "grade."
            )
        surfaces: list[Surface] = []
        for i, wall in enumerate(summary.get("walls", []), start=1):
            net = (wall.get("area_m2") or 0.0) - (wall.get("glass_m2") or 0.0)
            if net > 0:
                r = wall.get("r_value_si") or nominal.wall_r
                if below > 0:
                    surfaces.append(
                        Surface(
                            f"wall {i} below grade",
                            "wall",
                            net * below,
                            r=r,
                            ground=True,
                        )
                    )
                if below < 1:
                    surfaces.append(
                        Surface(f"wall {i}", "wall", net * (1 - below), r=r)
                    )
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
            if (reg.get("duct") or reg.get("upstream")) and reg.get("free_area_in2"):
                pending.append((reg, name, j))
    if not built:
        raise ValueError("no room has enough data for a Manual J")
    warnings.append(
        "Wall and roof R-values and window glazing and frame are the house defaults, "
        "not measured."
    )
    runs = _runs(pending, ducts or {}, warnings)
    return Project(rooms=tuple(built), design=design, runs=tuple(runs)), warnings


def _segment(seg: dict, flow_m3s: float | None, trunk: bool) -> Segment:
    """A duct segment as House Structure stores it (feet and inches)."""
    length = seg["length_ft"] * FT_TO_M
    k = seg.get("fittings_k") or 0.0
    if seg["shape"] == "round":
        return Segment.round_in(seg["diameter_in"], length, k, flow_m3s, trunk)
    return Segment.rect_in(
        seg["width_in"], seg["height_in"], length, k, flow_m3s, trunk
    )


def _chain(upstream: str | None, sections: dict[str, dict]) -> list[str]:
    """The shared sections from the plenum down to ``upstream`` (none if None)."""
    chain: list[str] = []
    name = upstream
    while name is not None:
        if name not in sections:
            raise ValueError(f"no duct section called {name!r}")
        if name in chain:
            raise ValueError("the duct sections loop back on themselves")
        chain.append(name)
        name = sections[name].get("upstream")
    return list(reversed(chain))


def _runs(
    pending: list[tuple[dict, str, int]],
    sections: dict[str, dict],
    warnings: list[str],
) -> list[Run]:
    """Each register's run: its shared sections from the plenum, then its branch.

    A shared section carries the airflow of every register behind it, so its
    loss and velocity are checked at that total. A register with no airflow
    adds nothing to its sections, which is said in the warnings.
    """
    paths = []
    for reg, room, index in pending:
        label = reg.get("title") or f"{room} register {index}"
        try:
            chain = _chain(reg.get("upstream"), sections)
        except ValueError as err:
            warnings.append(f"{label}: {err}. The register is not in the calculation.")
            continue
        if chain and not reg.get("flow_cfm"):
            warnings.append(
                f"{label}: no design airflow, so the shared ducts it runs through "
                "carry less than they will."
            )
        paths.append((reg, room, index, label, chain))
    carried: dict[str, float] = {}
    for reg, _, _, _, chain in paths:
        flow = reg["flow_cfm"] * CFM_TO_M3S if reg.get("flow_cfm") else 0.0
        for name in chain:
            carried[name] = carried.get(name, 0.0) + flow
    runs = []
    for reg, room, _, label, chain in paths:
        segments = [
            _segment(seg, carried[name] or None, trunk=True)
            for name in chain
            for seg in sections[name]["segments"]
        ]
        for seg in reg.get("duct") or ():
            flow = seg["flow_cfm"] * CFM_TO_M3S if seg.get("flow_cfm") else None
            segments.append(_segment(seg, flow, bool(seg.get("trunk"))))
        flow = reg["flow_cfm"] * CFM_TO_M3S if reg.get("flow_cfm") else None
        runs.append(
            Run(
                name=label,
                room=room,
                register_area_m2=reg["free_area_in2"] * IN2_TO_M2,
                segments=tuple(segments),
                flow_m3s=flow,
            )
        )
    return runs


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
        # The fit's rate covers the above-grade envelope (the ground has its own
        # term), so a basement's walls count only above the grade line.
        above = 1.0 - ground_fraction(summary)
        elements = []
        for kind, items in (
            ("wall", summary.get("walls", [])),
            ("roof", summary.get("roofs", [])),
        ):
            for i, item in enumerate(items, start=1):
                net = (item.get("area_m2") or 0.0) - (item.get("glass_m2") or 0.0)
                if kind == "wall":
                    net *= above
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


def fixed_conductances(room: Room, design: Design) -> tuple[float, float]:
    """A room's window conductance and its infiltration conductance, W/K."""
    windows = sum(s.conductance for s in room.surfaces if s.kind == "window")
    infiltration = (
        room.ach
        * room.volume
        / 3600.0
        * rho_cp(design.heat_indoor_c, design.altitude_m)
    )
    return windows, infiltration


def room_capacities(rooms: dict[str, dict]) -> dict[str, float]:
    """Each room's heat capacity (air only), J/K, by area id."""
    return {
        area_id: room_capacity(volume)
        for area_id, summary in rooms.items()
        if (volume := _volume(summary))
    }
