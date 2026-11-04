"""Tests for the setup forms' text parsing."""

import pytest

from custom_components.home_thermal_lab.options import (
    FieldError,
    format_lights,
    format_roofs,
    kw_table,
    parse_blower,
    parse_lights,
    parse_roofs,
    resolve_sun,
    roof_label,
    roof_renames,
)


def test_roofs_round_trip():
    roofs = parse_roofs("s 30, W 22.5")
    assert roofs == [["South", "S", 30.0], ["West", "W", 22.5]]
    assert format_roofs(roofs) == "South=S 30, West=W 22.5"
    assert parse_roofs(format_roofs(roofs)) == roofs


def test_roofs_empty_and_separators():
    assert parse_roofs("") == []
    assert parse_roofs("N 10; E 12,") == [["North", "N", 10.0], ["East", "E", 12.0]]


def test_roofs_names_are_kept_when_a_pitch_changes():
    first = parse_roofs("W 4:12, W 8:12")
    assert [r[0] for r in first] == ["West", "West 2"]
    # the form shows the names; edit the second pitch and the names stay
    edited = format_roofs(first).replace("8:12", "9:12")
    again = parse_roofs(edited)
    assert [r[0] for r in again] == ["West", "West 2"]
    assert again[1][2] == pytest.approx(36.87, abs=0.01)


def test_roofs_explicit_names_and_duplicates():
    roofs = parse_roofs("Garage=W 8:12, W 4:12")
    assert [r[0] for r in roofs] == ["Garage", "West"]
    with pytest.raises(FieldError):
        parse_roofs("A=W 4:12, A=S 6:12")


@pytest.mark.parametrize("text", ["S", "Q 30", "S thirty", "S 30 40"])
def test_roofs_reject_bad_parts(text):
    with pytest.raises(FieldError) as err:
        parse_roofs(text)
    assert err.value.field == "roofs"


def test_lights_round_trip():
    lights = parse_lights("light.office_main_lights=105, light.hall = 40")
    assert lights == {"light.office_main_lights": 105.0, "light.hall": 40.0}
    assert parse_lights(format_lights(lights)) == lights


@pytest.mark.parametrize("text", ["light.a", "switch.a=10", "light.a=lots", "=5"])
def test_lights_reject_bad_parts(text):
    with pytest.raises(FieldError) as err:
        parse_lights(text)
    assert err.value.field == "lights"


def test_kw_table_keeps_filled_modes_only():
    form = {"name": "x", "fan": 0.04, "heat_low": 0.0, "heat_high": None, "cool": ""}
    assert kw_table(form) == {"fan": 0.04, "heat_low": 0.0}


def test_roof_ratio_pitch():
    roofs = parse_roofs("S 4:12, W 12:12, N 0:12")
    assert [r[2] for r in roofs] == pytest.approx([18.4349, 45.0, 0.0], abs=1e-3)
    assert format_roofs(roofs) == "South=S 4:12, West=W 12:12, North=N 0:12"
    assert format_roofs([["S", 30.0]]) == "South=S 30"  # a pair is named


@pytest.mark.parametrize("text", ["S 4:0", "S -1:12", "S a:12", "S 4:"])
def test_roof_ratio_rejects_bad_parts(text):
    with pytest.raises(FieldError):
        parse_roofs(text)


def test_kw_table_converts_tons():
    table = kw_table({"cool": 9, "cool_tons": 3})
    assert table == {"cool": pytest.approx(10.55052)}


def test_kw_table_converts_btu():
    table = kw_table({"heat_high": 80000, "fan": ""}, "BTU/h")
    assert table == {"heat_high": pytest.approx(23.4456)}


def test_resolve_sun_applies_house_settings():
    house = {
        "rotation": 10.4,
        "shade_below": 18,
        "roofs": [["Front", "S", 30.0], ["Back", "W", 20.0]],
    }
    out = resolve_sun({"windows": ["E"], "roofs": ["Back", "Gone"]}, house)
    assert out["roofs"] == [["W", 20.0]]
    assert out["rotation"] == 10.4
    assert out["shade_below"] == 18
    assert out["windows"] == ["E"]


def test_resolve_sun_room_shade_wins_and_old_data_works():
    house = {"rotation": 5.0, "shade_below": 18}
    out = resolve_sun({"shade_below": 10, "roofs": [["S", 30.0]]}, house)
    assert out["shade_below"] == 10
    assert out["roofs"] == [["S", 30.0]]
    assert resolve_sun({}, {}) == {"roofs": []}


def test_room_keeps_its_roof_when_the_pitch_is_edited():
    house = {"roofs": parse_roofs("Front=W 4:12, Back=W 8:12, S 12:12")}
    room = {"roofs": ["Back"]}
    assert resolve_sun(room, house)["roofs"] == [["W", pytest.approx(33.69, abs=0.01)]]
    # edit the Back pitch on the house; the room still points at it
    house = {
        "roofs": parse_roofs(format_roofs(house["roofs"]).replace("8:12", "10:12"))
    }
    out = resolve_sun(room, house)
    assert out["roofs"] == [["W", pytest.approx(39.81, abs=0.01)]]


def test_two_roofs_on_one_face_are_separate():
    house = {"roofs": parse_roofs("W 4:12, W 8:12, S 12:12")}
    assert [r[0] for r in resolve_sun({"roofs": ["West 2"]}, house)["roofs"]] == ["W"]
    out = resolve_sun({"roofs": ["West", "West 2", "South"]}, house)
    assert [r[0] for r in out["roofs"]] == ["W", "W", "S"]


def test_resolve_sun_reads_older_saved_roofs():
    house = {"roofs": [["W", 40.0], ["S", 45.0]]}  # pairs saved without names
    assert roof_label("W", 18.4349) == "W 4:12"
    assert resolve_sun({"roofs": ["W 4:12"]}, house)["roofs"] == [["W", 40.0]]
    assert resolve_sun({"roofs": ["S"]}, house)["roofs"] == [["S", 45.0]]
    assert resolve_sun({"roofs": ["N 3:12"]}, house)["roofs"] == []


def test_renamed_roof_is_followed():
    old = parse_roofs("Front=S 30, Back=W 4:12, Garage=W 8:12")
    new = parse_roofs("Front=S 30, Rear=W 4:12, Garage=W 8:12")
    assert roof_renames(old, new) == {"Back": "Rear"}


def test_two_renames_on_one_face_follow_in_order():
    old = parse_roofs("A=W 4:12, B=W 8:12")
    new = parse_roofs("Left=W 4:12, Right=W 8:12")
    assert roof_renames(old, new) == {"A": "Left", "B": "Right"}


def test_added_removed_or_changed_pitch_is_not_a_rename():
    old = parse_roofs("Front=S 30, Back=W 4:12")
    assert roof_renames(old, parse_roofs("Front=S 40, Back=W 5:12")) == {}  # pitches
    assert roof_renames(old, parse_roofs("Front=S 30, Back=W 4:12, Shed=N 6:12")) == {}
    assert roof_renames(old, parse_roofs("Front=S 30")) == {}  # Back removed
    # removed and a different face added: not the same roof
    assert roof_renames(old, parse_roofs("Front=S 30, Shed=N 6:12")) == {}
    assert roof_renames([], parse_roofs("W 4:12")) == {}


def test_blower_curve_units_on_first_point_carry_to_rest():
    points = parse_blower("400 cfm = 0.30 inWC, 800 = 0.20, 1200 = 0.05")
    assert len(points) == 3
    flow, static = points[0]
    assert flow == pytest.approx(400 * 0.000471947)
    assert static == pytest.approx(0.30 * 249.089)
    assert points[2][1] == pytest.approx(0.05 * 249.089)


def test_blower_curve_defaults_to_cfm_and_inwc():
    points = parse_blower("400 = 0.3, 800 = 0.2")
    assert points[1][0] == pytest.approx(800 * 0.000471947)


def test_blower_curve_metric_and_mixed_units():
    points = parse_blower("0.2 m3/s = 60 Pa, 0.1 l/s = 150 Pa")
    assert points[0] == pytest.approx((0.0001, 150.0))
    assert points[1] == pytest.approx((0.2, 60.0))


def test_blower_curve_errors():
    for bad in [
        "400 cfm = 0.3",
        "400 = 0.3, 400 = 0.2",
        "400 furlongs = 0.3, 800 = 0.2",
        "x = 1, 2 = 3",
    ]:
        with pytest.raises(FieldError):
            parse_blower(bad)
