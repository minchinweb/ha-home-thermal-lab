"""Tests for the Manual J, S and D calculations (standard library only)."""

import math

import pytest

from custom_components.home_thermal_lab.manual import (
    ROUND_SIZES_IN,
    AirConditioner,
    Design,
    Element,
    Furnace,
    Project,
    Room,
    Run,
    Segment,
    Surface,
    _area_and_diameter,
    _segment_drop,
    air_density,
    available_static,
    btu_h,
    calculate,
    check_cooling,
    check_heating,
    cooling_humidity,
    cooling_load,
    design_temperatures,
    envelope_scale,
    heating_load,
    humidity_ratio,
    inches,
    infiltration_ua,
    natural_ach,
    room_capacity,
    round_size_for_friction,
    ua_from_rate,
    window_u,
)


def _wall(area=10.0, u=0.3, **kw):
    return Surface("wall", "wall", area, u=u, **kw)


def test_surface_needs_u_or_r():
    with pytest.raises(ValueError):
        Surface("x", "wall", 10.0)


def test_r_value_gives_u_value():
    s = Surface("wall", "wall", 10.0, r=3.5)
    assert s.conductance == pytest.approx(10.0 / 3.5)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        Surface("x", "ceiling", 10.0, u=0.2)


def test_heating_conduction_without_infiltration():
    room = Room("r", volume=30.0, surfaces=(_wall(),), ach=0.0)
    design = Design(heat_outdoor_c=-27.0, heat_indoor_c=21.0)
    total, parts = heating_load(room, design)
    # 10 m² at 0.3 W/m²K across a 48 K difference
    assert total == pytest.approx(144.0)
    assert parts["infiltration"] == 0.0


def test_ground_surface_uses_ground_temperature():
    floor = Surface("slab", "floor", 10.0, u=0.5, ground=True)
    room = Room("r", volume=30.0, surfaces=(floor,), ach=0.0)
    design = Design(ground_c=5.6, heat_indoor_c=21.0)
    total, _ = heating_load(room, design)
    assert total == pytest.approx(10.0 * 0.5 * (21.0 - 5.6))


def test_infiltration_scales_with_volume_and_air_change():
    room = Room("r", volume=36.0, surfaces=(), ach=1.0)  # 36 m³/h = 0.01 m³/s
    design = Design(heat_outdoor_c=-27.0, heat_indoor_c=21.0, altitude_m=0.0)
    total, _ = heating_load(room, design)
    expected = 0.01 * air_density(21.0) * 1006.0 * 48.0
    assert total == pytest.approx(expected, rel=1e-3)


def test_window_solar_gain_on_its_face():
    win = Surface("window", "window", 2.0, u=0.0, shgc=0.5, face="S")
    room = Room("r", volume=30.0, surfaces=(win,), ach=0.0)
    design = Design(solar_w_m2={"S": 220.0})
    sens, _ = cooling_load(room, design)
    assert sens["window"] == pytest.approx(2.0 * 0.5 * 220.0)


def test_people_and_internal_gains_are_cooling_only():
    room = Room("r", volume=30.0, surfaces=(), ach=0.0, people=2, gains_w=300.0)
    sens, lat = cooling_load(room, Design())
    assert sens["people"] == pytest.approx(140.0)
    assert sens["internal"] == pytest.approx(300.0)
    assert lat["people"] == pytest.approx(90.0)
    assert "people" not in heating_load(room, Design())[1]


def test_air_density_at_edmonton_is_thinner_than_sea_level():
    sea = air_density(20.0, 0.0)
    edmonton = air_density(20.0, 723.0)
    assert sea == pytest.approx(1.204, abs=0.005)
    assert edmonton == pytest.approx(1.10, abs=0.01)


def test_unit_helpers():
    assert inches(4) == pytest.approx(0.1016)
    assert btu_h(80000) == pytest.approx(23446, rel=1e-3)


def test_furnace_output_applies_efficiency():
    f = Furnace({"high": 20000.0, "low": 13000.0}, efficiency=0.95)
    assert f.output_w("high") == pytest.approx(19000.0)
    assert f.output_w("low") == pytest.approx(12350.0)
    assert f.output_w("missing") is None


def test_furnace_needs_high_stage():
    with pytest.raises(ValueError):
        Furnace({"low": 10000.0})


def test_heating_check_oversized_and_undersized():
    f = Furnace({"high": 30000.0}, efficiency=1.0)
    design = Design()
    assert check_heating(10000.0, f, design)["verdict"] == "oversized"
    assert check_heating(40000.0, f, design)["verdict"] == "undersized"
    assert check_heating(25000.0, f, design)["verdict"] == "ok"


def test_cooling_capacity_falls_with_hotter_outdoors():
    ac = AirConditioner(total_w=10000.0, sensible_w=7500.0, rated_outdoor_c=35.0)
    at_rating, _ = ac.capacity_at(35.0)
    hotter, _ = ac.capacity_at(40.0)
    milder, _ = ac.capacity_at(28.0)
    assert at_rating == pytest.approx(10000.0)
    assert hotter < at_rating < milder


def test_cooling_check_uses_design_temperature():
    ac = AirConditioner(total_w=10000.0, sensible_w=7500.0)
    check = check_cooling(9000.0, 6000.0, ac, Design(cool_outdoor_c=35.0))
    assert check["capacity_total_w"] == pytest.approx(10000.0)
    assert check["verdict"] == "ok"
    assert check["ratio"] == pytest.approx(10000.0 / 9000.0)


def test_round_duct_velocity_from_flow_and_area():
    seg = Segment.round_in(4, 1.0)
    v, rate, loss = _segment_drop(seg, 0.05, 1.2)
    area = math.pi * 0.1016**2 / 4
    assert v == pytest.approx(0.05 / area)
    assert rate > 0 and loss > 0


def test_bigger_duct_loses_less():
    small = Segment.round_in(4, 10.0)
    big = Segment.round_in(8, 10.0)
    _, rate_small, _ = _segment_drop(small, 0.05, 1.2)
    _, rate_big, _ = _segment_drop(big, 0.05, 1.2)
    assert rate_big < rate_small


def test_round_size_meets_target_and_next_smaller_does_not():
    flow, target = 0.06, 0.8
    size = round_size_for_friction(flow, target, 20.0, 723.0)
    density = air_density(20.0, 723.0)
    _, rate, _ = _segment_drop(Segment.round_in(size, 1.0), flow, density)
    assert rate <= target
    index = ROUND_SIZES_IN.index(int(size))
    if index > 0:
        _, smaller, _ = _segment_drop(
            Segment.round_in(ROUND_SIZES_IN[index - 1], 1.0), flow, density
        )
        assert smaller > target


def test_rectangular_duct_is_loss_equal_to_a_similar_round_one():
    area, d = _area_and_diameter(Segment.rect_in(10, 10, 1.0))
    # Huebscher: a square duct's equivalent round is about 1.09 times its side
    assert area == pytest.approx(inches(10) ** 2)
    assert d == pytest.approx(
        1.30 * (inches(10) ** 2) ** 0.625 / (2 * inches(10)) ** 0.25
    )
    assert d == pytest.approx(1.09 * inches(10), rel=0.01)


def test_blower_curve_interpolation():
    curve = ((0.0, 200.0), (0.1, 150.0), (0.2, 50.0))
    static, ok = available_static(curve, 0.05)
    assert static == pytest.approx(175.0)
    assert ok
    static, ok = available_static(curve, 0.3)
    assert static == pytest.approx(50.0)
    assert not ok


def test_full_calculation_returns_consistent_totals():
    wall = _wall(area=20.0, u=0.3)
    window = Surface("window", "window", 3.0, u=1.8, shgc=0.6, face="S")
    rooms = (
        Room("Office", 50.0, (wall, window), ach=0.5, people=1),
        Room("Bedroom", 40.0, (wall,), ach=0.5),
    )
    furnace = Furnace(
        {"high": 25000.0, "low": 16000.0},
        efficiency=0.95,
        blower=((0.0, 250.0), (0.1, 150.0), (0.2, 60.0)),
    )
    ac = AirConditioner(total_w=12000.0, sensible_w=9000.0)
    runs = (
        Run(
            "Office supply",
            "Office",
            register_area_m2=0.02,
            segments=(
                Segment.round_in(8, 4.0, trunk=True, flow_m3s=0.08),
                Segment.round_in(4, 3.0, fittings_k=0.5),
            ),
        ),
        Run(
            "Bedroom supply",
            "Bedroom",
            register_area_m2=0.02,
            segments=(Segment.round_in(4, 5.0, fittings_k=0.9),),
        ),
    )
    result = calculate(Project(rooms=rooms, furnace=furnace, ac=ac, runs=runs))

    rooms_out = result["rooms"]
    assert result["totals"]["heating_w"] == pytest.approx(
        rooms_out["Office"]["heating_w"] + rooms_out["Bedroom"]["heating_w"]
    )
    assert result["totals"]["cooling_total_w"] == pytest.approx(
        result["totals"]["cooling_sensible_w"] + result["totals"]["cooling_latent_w"]
    )
    assert result["equipment"]["heating"]["verdict"] in (
        "ok",
        "oversized",
        "undersized",
    )
    assert len(result["ducts"]["runs"]) == 2
    assert result["ducts"]["budget_pa"] is not None
    for run in result["ducts"]["runs"]:
        assert run["loss_pa"] > 0
        assert run["branch_round_in"] in ROUND_SIZES_IN


def test_calculation_without_furnace_still_gives_loads():
    room = Room("Office", 50.0, (_wall(),), ach=0.5)
    result = calculate(Project(rooms=(room,)))
    assert result["equipment"]["heating"] is None
    assert result["rooms"]["Office"]["heating_w"] > 0
    assert result["ducts"]["runs"] == []


def test_run_in_unknown_room_is_an_error():
    room = Room("Office", 50.0, (_wall(),))
    run = Run("x", "Nowhere", 0.02, (Segment.round_in(4, 1.0),))
    furnace = Furnace({"high": 20000.0}, blower=((0.0, 200.0), (0.2, 50.0)))
    with pytest.raises(ValueError):
        calculate(Project(rooms=(room,), furnace=furnace, runs=(run,)))


def test_design_temperatures_from_a_year_of_hours():
    # A year of hours spanning -30 to +30 C, evenly spread.
    hours = [-30.0 + 60.0 * i / (8760 - 1) for i in range(8760)]
    result = design_temperatures(hours)
    # 0.4% of 8760 hours is about 35 hours: the coldest value is near -30.
    assert result["heat_c"] == pytest.approx(-30.0 + 60.0 * 35 / 8759, abs=0.1)
    assert result["cool_c"] == pytest.approx(30.0 - 60.0 * 35 / 8759, abs=0.1)
    assert (
        result["heat_c"] < result["heat_c_99"] < result["cool_c_1"] < result["cool_c"]
    )
    assert result["hours"] == 8760
    assert any("one year" in w for w in result["warnings"])


def test_design_temperatures_skip_missing_hours():
    hours = [10.0] * 8000 + [None] * 500 + [-20.0] * 300
    result = design_temperatures(hours, min_hours=8000)
    assert result["hours"] == 8300
    assert result["heat_c"] == pytest.approx(-20.0)


def test_design_temperatures_need_enough_hours():
    with pytest.raises(ValueError):
        design_temperatures([0.0] * 100)


def test_two_years_drop_the_single_year_warning():
    hours = [float(i % 40 - 20) for i in range(2 * 8760)]
    result = design_temperatures(hours)
    assert not any("one year" in w for w in result["warnings"])


def test_humidity_ratio_at_a_known_dew_point():
    # 20 C dew point at sea level: about 0.0147 kg/kg
    assert humidity_ratio(20.0, 0.0) == pytest.approx(0.0147, abs=0.0002)


def test_cooling_humidity_uses_only_hot_hours():
    hours = [(30.0, 18.0)] * 6 + [(20.0, 5.0)] * 100 + [(30.0, None)]
    result = cooling_humidity(hours, cool_c=28.0)
    assert result["hours"] == 6
    assert result["w"] == pytest.approx(humidity_ratio(18.0))
    assert result["warnings"] == []


def test_few_hot_hours_warn():
    result = cooling_humidity([(30.0, 18.0)] * 2, cool_c=28.0)
    assert result["warnings"]


def test_cooling_humidity_needs_hot_hours():
    with pytest.raises(ValueError):
        cooling_humidity([(10.0, 5.0)], cool_c=28.0)


def test_capacity_and_rate_to_conductance():
    cap = room_capacity(50.0)  # air only
    assert cap == pytest.approx(50.0 * 1200.0 * 1005.0)
    # a rate of 0.01 per hour on that room is about 16.7 W/K
    assert ua_from_rate(0.01, cap) == pytest.approx(0.01 * cap / 3600.0)
    assert room_capacity(50.0, furnishing_kg=1000.0) > cap


def test_blower_door_to_natural_ach():
    # 2000 CFM50 on 400 m³ is about 8.5 ACH50, so about 0.42 natural at N = 20
    ach = natural_ach(2000.0, 400.0, n_factor=20.0)
    assert ach == pytest.approx(2000.0 * 1.69901 / 400.0 / 20.0)
    assert infiltration_ua(ach, 400.0) > 0


def test_window_u_lookup_is_case_insensitive():
    assert window_u("Double", "Vinyl") == 1.4
    with pytest.raises(ValueError):
        window_u("single", "vinyl")


def test_envelope_scale_recovers_a_known_factor():
    elements = [Element("wall", 40.0, 3.5), Element("roof", 20.0, 6.0)]
    # Build the measured conductance from a scale of 1.5 on the nominal U values
    nominal = 40.0 / 3.5 + 20.0 / 6.0
    fixed = 5.0
    measured = fixed + 1.5 * nominal
    result = envelope_scale(elements, fixed_ua=fixed, measured_ua=measured)
    assert result["scale"] == pytest.approx(1.5)
    wall = result["elements"][0]
    assert wall["u"] == pytest.approx(1.5 / 3.5)
    assert wall["r"] == pytest.approx(3.5 / 1.5)
    assert result["warnings"] == []


def test_envelope_scale_warns_on_implausible_factor():
    elements = [Element("wall", 40.0, 3.5)]
    result = envelope_scale(elements, fixed_ua=0.0, measured_ua=40.0 / 3.5 * 3.0)
    assert result["warnings"]


def test_envelope_scale_rejects_measurement_below_fixed_parts():
    with pytest.raises(ValueError):
        envelope_scale([Element("wall", 40.0, 3.5)], fixed_ua=50.0, measured_ua=10.0)
