"""Manual J (room loads), Manual S (equipment) and Manual D (ducts) for a house.

Standard library only, so the integration calls it directly and it is tested
without Home Assistant. SI units throughout: W, m, m², m³, m³/s, Pa and °C.
Inches are converted on the way in (``Segment.round_in`` and friends).

These are simplified steady-state calculations in the spirit of ACCA's Manual
J, S and D. They are not ACCA's tables. Cooling uses the design temperature
difference and a design-day solar gain per face rather than CLTD and SCL
tables, so cooling loads are approximate. The design values in ``Design`` are
starting points for Edmonton: check them against ASHRAE Fundamentals' climate
data for the site before relying on the results.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import pairwise
import math

R_DRY_AIR = 287.05  # J/(kg K)
CP_AIR = 1006.0  # J/(kg K)
H_FG = 2.45e6  # J/kg, latent heat of water near room temperature
MU_AIR = 1.8e-5  # Pa s, dynamic viscosity of air near 20 C
ROUGHNESS_M = 0.00015  # galvanised sheet metal
IN_TO_M = 0.0254
BTU_H_TO_W = 0.29307
PEOPLE_SENSIBLE_W = 70.0
PEOPLE_LATENT_W = 45.0
REGISTER_K = 1.5  # loss coefficient of a register's face, on its neck velocity
ROUND_SIZES_IN = (3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 24)
KINDS = ("wall", "roof", "floor", "window", "door")
# Design-day solar gain on each face, W/m² (N, E, S, W and H for horizontal).
# Approximate clear-summer values near 53 N; verify before relying on them.
SOLAR_W_M2 = {"N": 100.0, "E": 630.0, "S": 220.0, "W": 630.0, "H": 790.0}


# --- Air ----------------------------------------------------------------------


def inches(value: float) -> float:
    """Inches as metres."""
    return value * IN_TO_M


def btu_h(value: float) -> float:
    """BTU/h as watts."""
    return value * BTU_H_TO_W


def pressure_pa(altitude_m: float) -> float:
    """Standard-atmosphere pressure at an altitude (Edmonton is about 723 m)."""
    return 101325.0 * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588


def air_density(temp_c: float, altitude_m: float = 0.0) -> float:
    """Dry-air density, kg/m³."""
    return pressure_pa(altitude_m) / (R_DRY_AIR * (temp_c + 273.15))


def rho_cp(temp_c: float, altitude_m: float = 0.0) -> float:
    """Volumetric heat capacity of air, J/(m³ K): the watts per m³/s per kelvin."""
    return air_density(temp_c, altitude_m) * CP_AIR


# --- Building -----------------------------------------------------------------


@dataclass(frozen=True)
class Surface:
    """One part of a room's envelope.

    Attributes:
        name: Label, used as the key in the load breakdown.
        kind: ``wall``, ``roof``, ``floor``, ``window`` or ``door``.
        area: Area, m².
        u: Overall coefficient, W/(m² K). Used in preference to ``r``.
        r: Thermal resistance, m² K/W, when no ``u`` is given.
        shgc: Solar heat gain coefficient (windows only).
        face: Compass face for windows and roofs (N, E, S, W or H).
        ground: Whether the surface meets the ground (its sink is the ground).
    """

    name: str
    kind: str
    area: float
    u: float | None = None
    r: float | None = None
    shgc: float = 0.0
    face: str = ""
    ground: bool = False

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}")
        if self.area < 0:
            raise ValueError(f"{self.name}: negative area")
        if self.u is None and not self.r:
            raise ValueError(f"{self.name}: needs a U value or an R value")

    @property
    def conductance(self) -> float:
        """Conductance of the whole surface, W/K."""
        u = self.u if self.u is not None else 1.0 / self.r
        return u * self.area


@dataclass(frozen=True)
class Room:
    """A room: its volume, its envelope and its internal gains.

    Attributes:
        name: The room's name.
        volume: Air volume, m³.
        surfaces: The envelope (walls, roofs, floors, windows and doors).
        ach: Infiltration, air changes per hour.
        people: Occupants at design (cooling).
        gains_w: Sensible internal gains at design, W (appliances, lights).
    """

    name: str
    volume: float
    surfaces: tuple[Surface, ...]
    ach: float = 0.35
    people: int = 0
    gains_w: float = 0.0


@dataclass(frozen=True)
class Design:
    """Design conditions and air-side settings.

    The defaults are starting values for Edmonton, to confirm against ASHRAE
    climate data. Temperatures are °C; humidity ratios are kg water per kg dry
    air.
    """

    heat_outdoor_c: float = -27.0
    heat_indoor_c: float = 21.0
    cool_outdoor_c: float = 28.0
    cool_indoor_c: float = 24.0
    ground_c: float = 5.6  # design soil temperature for ground-coupled surfaces
    altitude_m: float = 723.0
    cool_outdoor_w: float = 0.0100
    cool_indoor_w: float = 0.0093
    solar_w_m2: Mapping[str, float] = field(default_factory=lambda: dict(SOLAR_W_M2))
    heat_rise_k: float = 20.0  # supply-air temperature rise in heating
    cool_rise_k: float = 11.0  # supply-air temperature drop in cooling
    duct_air_c: float = 20.0  # temperature used for duct friction


# --- Design temperatures from history -----------------------------------------

HOURS_PER_YEAR = 8760


def quantile(sorted_values: list[float], q: float) -> float:
    """The ``q`` quantile of sorted values, linearly interpolated (0 <= q <= 1)."""
    if not sorted_values:
        raise ValueError("no values")
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (pos - lo) * (sorted_values[hi] - sorted_values[lo])


def design_temperatures(
    hourly_c: list[float | None], min_hours: int = int(0.9 * HOURS_PER_YEAR)
) -> dict:
    """Design dry-bulb temperatures from a record of hourly outdoor temperatures.

    The ASHRAE convention, applied to the record: the heating design is the
    temperature exceeded in 99.6% of hours (the 0.4th percentile), and the
    cooling design the temperature exceeded in 0.4% of hours (the 99.6th
    percentile). The 99% and 1% values are returned as a cross-check.

    A year is a single sample of the weather. The 0.4% tail rests on about 35
    hours, so a second year, and a comparison with the station's ASHRAE values,
    should be used before trusting the result.

    Args:
        hourly_c: Hourly outdoor dry-bulb temperatures, °C; None for a missing hour.
        min_hours: Fewest valid hours to accept (default 90% of a year).

    Returns:
        ``heat_c`` and ``cool_c`` (the design values), ``heat_c_99`` and
        ``cool_c_1`` (the cross-checks), ``hours`` (valid hours used) and
        ``warnings``.
    """
    valid = sorted(t for t in hourly_c if t is not None and math.isfinite(t))
    n = len(valid)
    if n < min_hours:
        raise ValueError(
            f"only {n} valid hours; at least {min_hours} are needed for a design value"
        )
    warnings: list[str] = []
    if n < 2 * 0.9 * HOURS_PER_YEAR:
        warnings.append("Under two years of record: the 0.4% values rest on one year.")
    missing = len(hourly_c) - n
    if missing > 0.1 * len(hourly_c):
        warnings.append(f"{missing} of {len(hourly_c)} hours are missing.")
    return {
        "heat_c": quantile(valid, 0.004),
        "heat_c_99": quantile(valid, 0.010),
        "cool_c": quantile(valid, 0.996),
        "cool_c_1": quantile(valid, 0.990),
        "hours": n,
        "warnings": warnings,
    }


def humidity_ratio(dew_c: float, altitude_m: float = 0.0) -> float:
    """Humidity ratio (kg water per kg dry air) at a dew point."""
    e = 610.94 * math.exp(17.625 * dew_c / (dew_c + 243.04))  # Pa, over water
    p = pressure_pa(altitude_m)
    return 0.622 * e / (p - e)


def cooling_humidity(
    hours: list[tuple[float | None, float | None]],
    cool_c: float,
    altitude_m: float = 0.0,
) -> dict:
    """Design humidity ratio for cooling, from the hours as hot as the design.

    The design humidity is the average humidity ratio of the hours whose dry-bulb
    reaches the cooling design temperature, so it matches the design heat rather
    than an annual average.

    Args:
        hours: (dry-bulb, dew point) pairs in °C; either may be None.
        cool_c: The cooling design dry-bulb temperature.
        altitude_m: Site altitude.

    Returns:
        ``w`` (the humidity ratio), ``hours`` (hours used) and ``warnings``.
    """
    ws = [
        humidity_ratio(dew, altitude_m)
        for dry, dew in hours
        if dry is not None and dew is not None and dry >= cool_c
    ]
    warnings: list[str] = []
    if len(ws) < 5:
        warnings.append(
            "Fewer than 5 hot hours with a dew point: humidity is uncertain."
        )
    if not ws:
        raise ValueError("no hours with both a design-hot dry-bulb and a dew point")
    return {"w": sum(ws) / len(ws), "hours": len(ws), "warnings": warnings}


# --- Envelope from measurement -------------------------------------------------

CFM_TO_M3S = 0.000471947
M3H_PER_CFM = 1.69901
AIR_HEAT_CAPACITY_J_M3K = 1200.0 * 1005.0  # air at about 20 C
# Nominal whole-window U-values, W/(m² K), by glazing and frame. Typical
# catalogue values from memory: verify against the product before use.
NOMINAL_WINDOW_U = {
    ("double", "vinyl"): 1.4,
    ("double", "wood"): 1.6,
    ("double", "aluminium"): 2.8,
    ("triple", "vinyl"): 0.9,
    ("triple", "wood"): 1.0,
    ("triple", "aluminium"): 1.8,
}


def room_capacity(
    volume_m3: float, furnishing_kg: float = 0.0, furnishing_c: float = 1000.0
) -> float:
    """Heat capacity of a room's air and furnishings, J/K.

    The furnishings' mass is a guess unless it is measured, and it is the main
    uncertainty in turning a fitted rate into a conductance.
    """
    return volume_m3 * AIR_HEAT_CAPACITY_J_M3K + furnishing_kg * furnishing_c


def ua_from_rate(rate_per_h: float, capacity_j_k: float) -> float:
    """The conductance (W/K) behind a fitted rate (per hour): UA = rate * C / 3600."""
    return rate_per_h * capacity_j_k / 3600.0


def natural_ach(cfm50: float, volume_m3: float, n_factor: float = 20.0) -> float:
    """Natural air changes per hour from a blower-door test.

    Args:
        cfm50: Airflow at 50 Pa, CFM (the blower test's result).
        volume_m3: The house's volume, m³.
        n_factor: The leakage-to-natural ratio (about 20 for a typical house;
            it depends on height, exposure and climate).
    """
    ach50 = cfm50 * M3H_PER_CFM / volume_m3
    return ach50 / n_factor


def infiltration_ua(
    ach: float, volume_m3: float, indoor_c: float = 21.0, altitude_m: float = 0.0
) -> float:
    """Conductance of air leakage, W/K, at a given air-change rate."""
    return ach * volume_m3 / 3600.0 * rho_cp(indoor_c, altitude_m)


def window_u(glazing: str, frame: str) -> float:
    """Nominal window U-value from the glazing ("double" or "triple") and frame."""
    key = (glazing.lower(), frame.lower())
    if key not in NOMINAL_WINDOW_U:
        raise ValueError(f"no nominal U for {glazing!r} glazing in a {frame!r} frame")
    return NOMINAL_WINDOW_U[key]


@dataclass(frozen=True)
class Element:
    """A wall, roof or floor whose nominal R-value is known.

    Attributes:
        name: The element's name.
        area: Area, m².
        r_nominal: Nominal (as-built, from the construction) R-value, m² K/W.
    """

    name: str
    area: float
    r_nominal: float


def envelope_scale(
    elements: list[Element], fixed_ua: float, measured_ua: float
) -> dict:
    """Scale the nominal R-values so the elements' conductance matches a measurement.

    The measured conductance covers all of the envelope. Windows and anything
    else with a known U are taken out first (``fixed_ua``), and the rest is
    shared across the elements in proportion to their nominal conductances:
    each element's U is its nominal U times one factor, so the walls keep their
    relative differences.

    Args:
        elements: The elements to scale (walls, roofs).
        fixed_ua: Conductance of the parts not scaled (windows, doors), W/K.
        measured_ua: Conductance measured for the whole group, W/K, after the
            infiltration has been removed by the caller.

    Returns:
        ``scale`` (the factor), ``elements`` (each with its derived ``u`` and
        ``r``) and ``warnings``.
    """
    if not elements:
        raise ValueError("no elements to scale")
    nominal = sum(e.area / e.r_nominal for e in elements)
    target = measured_ua - fixed_ua
    if target <= 0:
        raise ValueError(
            "the measured conductance does not exceed the fixed parts (windows, "
            "infiltration): the blower test or the fit needs checking"
        )
    scale = target / nominal
    warnings: list[str] = []
    if not 0.5 <= scale <= 2.0:
        warnings.append(
            f"The scale factor is {scale:.2f}: the nominal R-values or the measured "
            "conductance are well off. Check the construction and the fit."
        )
    out = []
    for e in elements:
        u = scale / e.r_nominal
        out.append({"name": e.name, "area": e.area, "u": u, "r": 1.0 / u})
    return {"scale": scale, "elements": out, "warnings": warnings}


# --- Manual J -----------------------------------------------------------------


@dataclass(frozen=True)
class RoomLoad:
    """A room's design loads, with the parts that make them up."""

    room: str
    heating_w: float
    heating_parts: Mapping[str, float]
    cooling_sensible_w: float
    cooling_sensible_parts: Mapping[str, float]
    cooling_latent_w: float
    cooling_latent_parts: Mapping[str, float]
    airflow_m3s: float

    @property
    def cooling_total_w(self) -> float:
        return self.cooling_sensible_w + self.cooling_latent_w


def heating_load(room: Room, design: Design) -> tuple[float, dict[str, float]]:
    """Heat loss at the design winter temperature, W, and its parts.

    Conduction through each surface plus infiltration. Internal gains are not
    counted, as in Manual J.
    """
    parts: dict[str, float] = {}
    for s in room.surfaces:
        sink = design.ground_c if s.ground else design.heat_outdoor_c
        parts[s.name] = s.conductance * (design.heat_indoor_c - sink)
    air_flow = room.ach * room.volume / 3600.0
    parts["infiltration"] = (
        air_flow
        * rho_cp(design.heat_indoor_c, design.altitude_m)
        * (design.heat_indoor_c - design.heat_outdoor_c)
    )
    return sum(parts.values()), parts


def cooling_load(
    room: Room, design: Design
) -> tuple[dict[str, float], dict[str, float]]:
    """Sensible and latent gains at the design summer conditions, W.

    Each gain is clipped at zero, so a surface that would cool the room is not
    credited. Opaque surfaces take no solar gain in this simplified method.
    Returns the sensible parts and the latent parts.
    """
    sensible: dict[str, float] = {}
    for s in room.surfaces:
        sink = design.ground_c if s.ground else design.cool_outdoor_c
        gain = s.conductance * (sink - design.cool_indoor_c)
        if s.kind == "window":
            gain += s.area * s.shgc * design.solar_w_m2.get(s.face, 0.0)
        sensible[s.name] = max(gain, 0.0)
    air_flow = room.ach * room.volume / 3600.0
    sensible["infiltration"] = max(
        air_flow
        * rho_cp(design.cool_indoor_c, design.altitude_m)
        * (design.cool_outdoor_c - design.cool_indoor_c),
        0.0,
    )
    sensible["people"] = room.people * PEOPLE_SENSIBLE_W
    sensible["internal"] = room.gains_w
    latent = {
        "infiltration": air_flow
        * air_density(design.cool_indoor_c, design.altitude_m)
        * H_FG
        * max(design.cool_outdoor_w - design.cool_indoor_w, 0.0),
        "people": room.people * PEOPLE_LATENT_W,
    }
    return sensible, latent


def room_airflow(heating_w: float, cooling_sensible_w: float, design: Design) -> float:
    """Supply air a room needs, m³/s: the larger of its heating and cooling flows."""
    heat = heating_w / (
        rho_cp(design.heat_indoor_c, design.altitude_m) * design.heat_rise_k
    )
    cool = cooling_sensible_w / (
        rho_cp(design.cool_indoor_c, design.altitude_m) * design.cool_rise_k
    )
    return max(heat, cool, 0.0)


def room_load(room: Room, design: Design) -> RoomLoad:
    """Manual J for one room."""
    heat, heat_parts = heating_load(room, design)
    sens, lat = cooling_load(room, design)
    sensible = sum(sens.values())
    return RoomLoad(
        room=room.name,
        heating_w=heat,
        heating_parts=heat_parts,
        cooling_sensible_w=sensible,
        cooling_sensible_parts=sens,
        cooling_latent_w=sum(lat.values()),
        cooling_latent_parts=lat,
        airflow_m3s=room_airflow(heat, sensible, design),
    )


# --- Manual S -----------------------------------------------------------------


@dataclass(frozen=True)
class Furnace:
    """A furnace's nameplate data and blower curve.

    Attributes:
        stages_input_w: Input per stage in W (gas input, or electric draw). Keys
            are ``high`` and, if it has one, ``low``.
        efficiency: AFUE as a fraction (0.95 for a 95% furnace); 1.0 for electric.
        blower: The blower's (airflow m³/s, external static Pa) points, from its
            nameplate or data sheet. Needed for the duct check.
    """

    stages_input_w: Mapping[str, float]
    efficiency: float = 1.0
    blower: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        if "high" not in self.stages_input_w:
            raise ValueError("furnace needs a high-stage input")
        if not 0 < self.efficiency <= 1.0:
            raise ValueError("efficiency must be a fraction in (0, 1]")

    def output_w(self, stage: str = "high") -> float | None:
        """Heat output of a stage, W, or None if the furnace has no such stage."""
        if stage not in self.stages_input_w:
            return None
        return self.stages_input_w[stage] * self.efficiency


@dataclass(frozen=True)
class AirConditioner:
    """An air conditioner's rated capacity, corrected to the design temperature.

    Attributes:
        total_w: Total cooling capacity at the rated outdoor temperature, W.
        sensible_w: Sensible capacity at the rated outdoor temperature, W.
        rated_outdoor_c: The outdoor temperature the rating is for (35 C is
            the usual rating point).
        capacity_per_k: Fractional change in capacity per kelvin away from the
            rating point. A rough stand-in for the manufacturer's curves.
    """

    total_w: float
    sensible_w: float
    rated_outdoor_c: float = 35.0
    capacity_per_k: float = 0.0085

    def capacity_at(self, outdoor_c: float) -> tuple[float, float]:
        """Total and sensible capacity at an outdoor temperature, W."""
        factor = 1.0 + self.capacity_per_k * (self.rated_outdoor_c - outdoor_c)
        return self.total_w * factor, self.sensible_w * factor


def _verdict(ratio: float, max_ratio: float) -> str:
    if ratio < 1.0:
        return "undersized"
    if ratio > max_ratio:
        return "oversized"
    return "ok"


def check_heating(
    load_w: float, furnace: Furnace, design: Design, max_ratio: float = 1.4
) -> dict:
    """Manual S for heating: the high stage against the whole-house heat loss."""
    capacity = furnace.output_w("high")
    ratio = capacity / load_w if load_w > 0 else math.inf
    low = furnace.output_w("low")
    return {
        "load_w": load_w,
        "capacity_w": capacity,
        "ratio": ratio,
        "verdict": _verdict(ratio, max_ratio),
        "low_stage_w": low,
        "low_stage_ratio": low / load_w if low is not None and load_w > 0 else None,
        "airflow_m3s": capacity
        / (rho_cp(design.heat_indoor_c, design.altitude_m) * design.heat_rise_k),
    }


def check_cooling(
    total_w: float,
    sensible_w: float,
    ac: AirConditioner,
    design: Design,
    max_ratio: float = 1.15,
) -> dict:
    """Manual S for cooling: total and sensible capacity against the loads."""
    cap_total, cap_sensible = ac.capacity_at(design.cool_outdoor_c)
    ratio = cap_total / total_w if total_w > 0 else math.inf
    return {
        "load_total_w": total_w,
        "load_sensible_w": sensible_w,
        "capacity_total_w": cap_total,
        "capacity_sensible_w": cap_sensible,
        "ratio": ratio,
        "sensible_ratio": cap_sensible / sensible_w if sensible_w > 0 else math.inf,
        "verdict": _verdict(ratio, max_ratio),
        "airflow_m3s": cap_sensible
        / (rho_cp(design.cool_indoor_c, design.altitude_m) * design.cool_rise_k),
    }


# --- Manual D -----------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """A piece of duct between two points.

    Attributes:
        shape: ``round`` (``size_m`` is the diameter) or ``rect`` (width, height).
        size_m: Size in metres.
        length_m: Length, m.
        fittings_k: Sum of the loss coefficients of the fittings on it.
        flow_m3s: Air carried, m³/s. None means the run's own airflow; trunk
            segments give the total they carry.
        trunk: Whether the segment is trunk (higher velocity limit) or branch.
    """

    shape: str
    size_m: tuple[float, ...]
    length_m: float
    fittings_k: float = 0.0
    flow_m3s: float | None = None
    trunk: bool = False

    def __post_init__(self) -> None:
        if self.shape == "round" and len(self.size_m) != 1:
            raise ValueError("a round segment has one size (its diameter)")
        if self.shape == "rect" and len(self.size_m) != 2:
            raise ValueError("a rectangular segment has a width and a height")
        if self.shape not in ("round", "rect"):
            raise ValueError("shape must be 'round' or 'rect'")
        if any(x <= 0 for x in self.size_m) or self.length_m < 0:
            raise ValueError("sizes must be positive and lengths not negative")

    @classmethod
    def round_in(
        cls,
        diameter_in: float,
        length_m: float,
        fittings_k: float = 0.0,
        flow_m3s: float | None = None,
        trunk: bool = False,
    ) -> Segment:
        """A round duct given in inches (``4`` for 4" round)."""
        return cls(
            "round", (inches(diameter_in),), length_m, fittings_k, flow_m3s, trunk
        )

    @classmethod
    def rect_in(
        cls,
        width_in: float,
        height_in: float,
        length_m: float,
        fittings_k: float = 0.0,
        flow_m3s: float | None = None,
        trunk: bool = False,
    ) -> Segment:
        """A rectangular duct given in inches."""
        return cls(
            "rect",
            (inches(width_in), inches(height_in)),
            length_m,
            fittings_k,
            flow_m3s,
            trunk,
        )


@dataclass(frozen=True)
class Run:
    """A supply run: a register and the duct from the plenum to it.

    Attributes:
        name: The run's name.
        room: The room the register serves (a ``RoomLoad`` name).
        register_area_m2: Free area of the register, m².
        segments: The duct from the plenum to the register, in order.
        flow_m3s: Airflow to the register. None uses the room's design airflow.
        register_k: Loss coefficient of the register.
    """

    name: str
    room: str
    register_area_m2: float
    segments: tuple[Segment, ...]
    flow_m3s: float | None = None
    register_k: float = REGISTER_K

    def __post_init__(self) -> None:
        if self.register_area_m2 <= 0:
            raise ValueError(f"{self.name}: register area must be positive")


def _area_and_diameter(seg: Segment) -> tuple[float, float]:
    """Flow area and hydraulic diameter of a segment, m² and m."""
    if seg.shape == "round":
        d = seg.size_m[0]
        return math.pi * d * d / 4.0, d
    a, b = seg.size_m
    # Huebscher's equivalent round diameter for a rectangular duct.
    return a * b, 1.30 * (a * b) ** 0.625 / (a + b) ** 0.25


def _segment_drop(
    seg: Segment, flow: float, density: float
) -> tuple[float, float, float]:
    """Velocity (m/s), friction rate (Pa/m) and total loss (Pa) of a segment."""
    area, d = _area_and_diameter(seg)
    v = flow / area
    re = density * v * d / MU_AIR
    if re <= 0:
        f = 0.0
    elif re < 2300:
        f = 64.0 / re
    else:
        # Swamee-Jain, an explicit fit to the Colebrook equation.
        f = 0.25 / math.log10(ROUGHNESS_M / (3.7 * d) + 5.74 / re**0.9) ** 2
    pressure = density * v * v / 2.0
    rate = f / d * pressure
    loss = (f * seg.length_m / d + seg.fittings_k) * pressure
    return v, rate, loss


def round_size_for_friction(
    flow: float, target_pa_per_m: float, temp_c: float = 20.0, altitude_m: float = 0.0
) -> float:
    """The smallest standard round size (inches) with friction within target."""
    density = air_density(temp_c, altitude_m)
    for d_in in ROUND_SIZES_IN:
        _, rate, _ = _segment_drop(Segment.round_in(d_in, 1.0), flow, density)
        if rate <= target_pa_per_m:
            return float(d_in)
    return float(ROUND_SIZES_IN[-1])


def available_static(
    curve: tuple[tuple[float, float], ...], flow: float
) -> tuple[float, bool]:
    """The blower's external static (Pa) at an airflow, and whether it is on the curve.

    Linear between the curve's (flow, static) points. Outside the curve the
    nearest end is used and the flag is False.
    """
    if not curve:
        raise ValueError("the blower curve is empty")
    pts = sorted(curve)
    if flow <= pts[0][0]:
        return pts[0][1], True
    for (f0, s0), (f1, s1) in pairwise(pts):
        if flow <= f1:
            t = (flow - f0) / (f1 - f0)
            return s0 + t * (s1 - s0), True
    return pts[-1][1], False


def evaluate_run(
    run: Run, flow: float, design: Design, max_branch: float, max_trunk: float
) -> dict:
    """Pressure loss of one run at its airflow, with velocity checks."""
    density = air_density(design.duct_air_c, design.altitude_m)
    segments = []
    loss_total = 0.0
    for seg in run.segments:
        carried = seg.flow_m3s if seg.flow_m3s is not None else flow
        v, rate, loss = _segment_drop(seg, carried, density)
        limit = max_trunk if seg.trunk else max_branch
        loss_total += loss
        segments.append(
            {
                "shape": seg.shape,
                "size_in": [round(x / IN_TO_M, 2) for x in seg.size_m],
                "trunk": seg.trunk,
                "flow_m3s": carried,
                "velocity_mps": v,
                "friction_pa_per_m": rate,
                "loss_pa": loss,
                "velocity_ok": v <= limit,
            }
        )
    neck_velocity = flow / run.register_area_m2
    register_loss = run.register_k * density * neck_velocity**2 / 2.0
    loss_total += register_loss
    return {
        "name": run.name,
        "room": run.room,
        "flow_m3s": flow,
        "segments": segments,
        "register_loss_pa": register_loss,
        "loss_pa": loss_total,
    }


# --- The whole house ----------------------------------------------------------


@dataclass(frozen=True)
class Project:
    """Everything the three calculations need.

    Attributes:
        rooms: The rooms (Manual J).
        design: Design conditions and air settings.
        furnace: Furnace nameplate and blower curve (Manual S and D).
        ac: Air conditioner nameplate (Manual S).
        equipment_static_pa: Static used by the coil, filter and cabinet, Pa.
        runs: Supply runs (Manual D).
        friction_target_pa_m: Friction rate to size branches to, Pa/m.
        branch_max_mps: Velocity limit for branch duct, m/s.
        trunk_max_mps: Velocity limit for trunk duct, m/s.
        heating_max_ratio: Largest acceptable furnace-to-load ratio.
        cooling_max_ratio: Largest acceptable AC-to-load ratio.
    """

    rooms: tuple[Room, ...]
    design: Design = Design()
    furnace: Furnace | None = None
    ac: AirConditioner | None = None
    equipment_static_pa: float = 75.0
    runs: tuple[Run, ...] = ()
    friction_target_pa_m: float = 0.8
    branch_max_mps: float = 4.6  # 900 fpm
    trunk_max_mps: float = 6.1  # 1200 fpm
    heating_max_ratio: float = 1.4
    cooling_max_ratio: float = 1.15


def calculate(project: Project) -> dict:
    """Run Manual J, S and D for a project.

    Returns a plain dict (numbers, strings, lists and dicts only) so the
    integration can publish it as sensor attributes. Keys: ``rooms``,
    ``totals``, ``equipment``, ``airflow_m3s``, ``ducts`` and ``warnings``.
    """
    d = project.design
    warnings: list[str] = []

    loads = {room.name: room_load(room, d) for room in project.rooms}
    rooms_out = {
        name: {
            "heating_w": load.heating_w,
            "heating_parts": dict(load.heating_parts),
            "cooling_sensible_w": load.cooling_sensible_w,
            "cooling_sensible_parts": dict(load.cooling_sensible_parts),
            "cooling_latent_w": load.cooling_latent_w,
            "cooling_latent_parts": dict(load.cooling_latent_parts),
            "cooling_total_w": load.cooling_total_w,
            "airflow_m3s": load.airflow_m3s,
        }
        for name, load in loads.items()
    }

    heat_total = sum(load.heating_w for load in loads.values())
    sens_total = sum(load.cooling_sensible_w for load in loads.values())
    lat_total = sum(load.cooling_latent_w for load in loads.values())
    ua_total = 0.0
    for room in project.rooms:
        ua_total += sum(s.conductance for s in room.surfaces)
        ua_total += (
            room.ach * room.volume / 3600.0 * rho_cp(d.heat_indoor_c, d.altitude_m)
        )
    totals = {
        "heating_w": heat_total,
        "cooling_sensible_w": sens_total,
        "cooling_latent_w": lat_total,
        "cooling_total_w": sens_total + lat_total,
        "ua_w_per_k": ua_total,
    }

    equipment: dict = {"heating": None, "cooling": None}
    system_flow = 0.0
    if project.furnace is not None:
        heat_check = check_heating(
            heat_total, project.furnace, d, project.heating_max_ratio
        )
        equipment["heating"] = heat_check
        system_flow = max(system_flow, heat_check["airflow_m3s"])
    if project.ac is not None:
        cool_check = check_cooling(
            sens_total + lat_total, sens_total, project.ac, d, project.cooling_max_ratio
        )
        equipment["cooling"] = cool_check
        system_flow = max(system_flow, cool_check["airflow_m3s"])

    ducts: dict = {
        "runs": [],
        "airflow_m3s": 0.0,
        "blower_static_pa": None,
        "budget_pa": None,
    }
    if project.runs:
        run_flows = {}
        for run in project.runs:
            if run.room not in loads:
                raise ValueError(
                    f"run {run.name!r} serves an unknown room {run.room!r}"
                )
            run_flows[run.name] = (
                run.flow_m3s
                if run.flow_m3s is not None
                else loads[run.room].airflow_m3s
            )
        total_flow = sum(run_flows.values())
        ducts["airflow_m3s"] = total_flow
        if project.furnace is None or not project.furnace.blower:
            warnings.append(
                "Duct check skipped: the furnace's blower curve is not set."
            )
        else:
            static, in_range = available_static(project.furnace.blower, total_flow)
            if not in_range:
                warnings.append("The duct airflow is outside the blower curve.")
            budget = static - project.equipment_static_pa
            ducts["blower_static_pa"] = static
            ducts["budget_pa"] = budget
            for run in project.runs:
                flow = run_flows[run.name]
                result = evaluate_run(
                    run, flow, d, project.branch_max_mps, project.trunk_max_mps
                )
                result["margin_pa"] = budget - result["loss_pa"]
                result["branch_round_in"] = round_size_for_friction(
                    flow, project.friction_target_pa_m, d.duct_air_c, d.altitude_m
                )
                result["ok"] = result["margin_pa"] >= 0 and all(
                    s["velocity_ok"] for s in result["segments"]
                )
                ducts["runs"].append(result)
        if system_flow and total_flow > system_flow * 1.05:
            warnings.append(
                "The runs' total airflow is more than the equipment's airflow."
            )

    return {
        "rooms": rooms_out,
        "totals": totals,
        "equipment": equipment,
        "airflow_m3s": system_flow,
        "ducts": ducts,
        "warnings": warnings,
    }
