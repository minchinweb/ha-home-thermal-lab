"""Tests for the setup forms' text parsing."""

import pytest

from custom_components.home_thermal_lab.options import (
    FieldError,
    format_lights,
    format_roofs,
    kw_table,
    parse_lights,
    parse_roofs,
)


def test_roofs_round_trip():
    roofs = parse_roofs("s 30, W 22.5")
    assert roofs == [["S", 30.0], ["W", 22.5]]
    assert parse_roofs(format_roofs(roofs)) == roofs


def test_roofs_empty_and_separators():
    assert parse_roofs("") == []
    assert parse_roofs("N 10; E 12,") == [["N", 10.0], ["E", 12.0]]


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
    assert [r[1] for r in roofs] == pytest.approx([18.4349, 45.0, 0.0], abs=1e-3)
    assert format_roofs(roofs) == "S 4:12, W 12:12, N 0:12"
    assert format_roofs([["S", 30.0]]) == "S 30"


@pytest.mark.parametrize("text", ["S 4:0", "S -1:12", "S a:12", "S 4:"])
def test_roof_ratio_rejects_bad_parts(text):
    with pytest.raises(FieldError):
        parse_roofs(text)


def test_kw_table_converts_btu():
    table = kw_table({"heat_high": 80000, "fan": ""}, "BTU/h")
    assert table == {"heat_high": pytest.approx(23.4456)}
