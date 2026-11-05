"""Tests for the setup forms' text parsing."""

import pytest

from custom_components.home_thermal_lab.options import (
    FieldError,
    format_lights,
    kw_table,
    parse_lights,
    with_house,
)


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


def test_kw_table_converts_btu():
    table = kw_table({"heat_high": 80000, "fan": ""}, "BTU/h")
    assert table == {"heat_high": pytest.approx(23.4456)}


def test_with_house_fills_the_ground_wave_only():
    house = {"ground_mean": 6.0, "ground_swing": 5.0, "rotation": 10.4}
    out = with_house({"name": "Den", "ground_swing": 4.0}, house)
    assert out == {"name": "Den", "ground_mean": 6.0, "ground_swing": 4.0}
    assert with_house({}, {}) == {}
