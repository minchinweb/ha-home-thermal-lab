"""Room sizes, supply airflow and window sizes (the owner's measurements).

Floor sizes and ceiling heights are from the owner's HVAC balancing check
(December 2025). Volume is floor area times the mean of the lowest and highest
ceiling, which is right for a ceiling that slopes evenly. A room whose ceiling is
the underside of the roof has a ``roof_pitch``, and its roof area is the floor
area over the cosine of the pitch. The kitchen is 13.25 ft east to west and
22 ft north to south; its ceiling slopes down to the west across the short span
(12.5 ft at the east side, 8 ft at the west).

Airflow is the cfm into each room for each zone calling on its own (register air
speed times register area), with the basement registers as rebalanced on
23 December 2025. The furnace moves about 1,575 cfm, and a bypass returns air to
the supply side when the pressure is too high. The kitchen's zone damper is a
different type and does not close tightly (hypothesis 06).

Window sizes are the owner's tape measurements (2 November 2026), width by
height in inches. The sink window is the glass alone; the others are the window
or door. The front room's two south windows are glass block, and the
entranceway's sidelight is frosted. The master's south window is the same size
as the N bedroom's. The main bathroom, the upstairs bathroom and the basement
family room and laundry have no window listed.

Rooms with a temperature sensor use the names in ``scripts/regress_rooms.py``.
The main office holds the Z4 thermostat ("Z4 office") and also the "Office
sensor" (lux and presence) and the "Office AQ" (air quality) sensors. The small
office has no sensor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

FT = 0.3048  # m
INCH = 0.0254  # m
CFM = 0.000471947  # m3/s
AIR_HEAT = 1.2 * 1005.0  # J per m3 per K, near room temperature
# kitchen ceiling: 12.5 ft down to 8 ft across the 13.25 ft east-west span
KITCHEN_ROOF_PITCH = math.degrees(math.atan2(12.5 - 8.0, 13.25))  # about 18.8


@dataclass(frozen=True)
class Room:
    """One room's size, supply air and windows.

    Attributes:
        floor_ft2: Floor area in square feet.
        ceiling_ft: Lowest and highest ceiling height in feet.
        zone: The zone the room's registers belong to.
        airflow_cfm: Supply air into the room per zone calling alone.
        roof_pitch: Pitch in degrees when the ceiling is the underside of the
            roof, else ``None``.
        windows: ``(face, width_in, height_in)`` per window; ``None`` when the
            sizes are not known.
    """

    floor_ft2: float
    ceiling_ft: tuple[float, float]
    zone: str
    airflow_cfm: dict[str, float] = field(default_factory=dict)
    roof_pitch: float | None = None
    windows: tuple[tuple[str, float, float], ...] | None = ()

    @property
    def floor_m2(self) -> float:
        """Floor area in square metres."""
        return self.floor_ft2 * FT * FT

    @property
    def volume_m3(self) -> float:
        """Air volume in cubic metres."""
        return self.floor_m2 * sum(self.ceiling_ft) / 2 * FT

    @property
    def roof_m2(self) -> float:
        """Area of roof that is the room's ceiling (0 with a floor above)."""
        if self.roof_pitch is None:
            return 0.0
        return self.floor_m2 / math.cos(math.radians(self.roof_pitch))

    @property
    def air_heat(self) -> float:
        """Heat capacity of the room's air alone, J/K."""
        return self.volume_m3 * AIR_HEAT

    def glass_m2(self, face: str | None = None) -> float | None:
        """Window area facing ``face`` (all faces when ``None``), m2."""
        if self.windows is None:
            return None
        return sum(w * h * INCH * INCH for f, w, h in self.windows if face in (None, f))

    def supply_w_per_k(self, zone: str) -> float:
        """Heat carried in per kelvin of supply-air rise when ``zone`` calls, W/K."""
        return self.airflow_cfm.get(zone, 0.0) * CFM * AIR_HEAT


BASEMENT = (7.25, 7.25)
MAIN = (8.0, 8.0)
UPSTAIRS = (4.5, 11.5)  # knee wall to the peak, under the 12:12 roof

ROOM_GEOMETRY: dict[str, Room] = {
    "Z1 kitchen": Room(
        291.5,
        (8.0, 12.5),
        "z1",
        {"z1": 485, "z2": 349, "z3": 388, "z4": 330},
        roof_pitch=KITCHEN_ROOF_PITCH,
        windows=(("S", 70, 80), ("W", 74, 80), ("W", 45, 32), ("E", 12, 60)),
    ),
    "Front room": Room(
        200.0,
        MAIN,
        "z4",
        {"z1": 27, "z2": 41, "z3": 20, "z4": 156},
        windows=(("E", 77, 54), ("S", 7.5, 31), ("S", 7.5, 31)),
    ),
    "Z4 office": Room(
        108.0, MAIN, "z4", {"z1": 4, "z2": 4, "z4": 107}, windows=(("E", 73, 54),)
    ),
    "Small office": Room(
        60.0, MAIN, "z4", {"z1": 4, "z2": 4, "z4": 107}, windows=(("E", 32, 43),)
    ),
    "W bedroom": Room(95.0, MAIN, "z4", {"z2": 4, "z4": 119}, windows=(("W", 34, 52),)),
    "Entranceway": Room(
        57.1, MAIN, "z4", {"z1": 4, "z2": 4, "z4": 107}, windows=(("N", 14, 80),)
    ),
    "Main bathroom": Room(42.5, MAIN, "z4", {"z1": 4, "z4": 111}),
    "Z3 master": Room(
        178.75,
        UPSTAIRS,
        "z3",
        {"z1": 25, "z2": 20, "z3": 108, "z4": 10},
        roof_pitch=45.0,
        windows=(("S", 48, 55),),
    ),
    "N bedroom": Room(
        110.4, UPSTAIRS, "z3", {"z3": 342}, roof_pitch=45.0, windows=(("N", 48, 55),)
    ),
    "Upstairs bath": Room(
        35.0,
        UPSTAIRS,
        "z3",
        {"z1": 8, "z2": 4, "z3": 25, "z4": 4},
        roof_pitch=45.0,
    ),
    "S basement": Room(
        99.0,
        BASEMENT,
        "z2",
        {"z1": 4, "z2": 127, "z3": 4},
        windows=(("S", 67, 31),),
    ),
    "SE basement": Room(57.5, BASEMENT, "z2", {"z2": 142}, windows=(("S", 47, 31),)),
    "NE basement": Room(
        66.25,
        BASEMENT,
        "z2",
        {"z2": 137},
        windows=(("N", 32, 18), ("E", 47, 31)),
    ),
    "Basement family room": Room(282.3, BASEMENT, "z2", {"z2": 126}),
    "Laundry": Room(87.75, BASEMENT, "z2", {"z2": 376}),
}
