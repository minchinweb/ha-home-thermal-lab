"""Tests for the shadow controller and forecast loader."""

from datetime import UTC, datetime

import pytest

from custom_components.home_thermal_lab.forecast import parse_forecast
from custom_components.home_thermal_lab.irradiance import (
    Irradiance,
    light_on_surfaces,
)
from custom_components.home_thermal_lab.shadow import ZoneModel, decide, simulate


def test_simulation_cools_toward_outdoors():
    model = ZoneModel(a=0.02, c=0.0)
    path = simulate(20.0, [0.0] * 4, [0.0] * 4, model, 1.0)
    assert len(path) == 5
    assert path[1] == pytest.approx(20.0 - 0.4)
    assert path == sorted(path, reverse=True)


def test_sun_can_keep_a_room_up():
    model = ZoneModel(a=0.02, c=0.0, g=0.002)
    shady = decide(20.0, 20.0, [0.0] * 12, [0.0] * 12, model, 0.25, 0.25, 0.1)
    sunny = decide(20.0, 20.0, [0.0] * 12, [400.0] * 12, model, 0.25, 0.25, 0.1)
    assert sunny.skip
    assert sunny.lowest >= -0.01
    assert shady.shortfall > sunny.shortfall


def test_decision_reports_the_dip():
    d = decide(19.0, 20.0, [-10.0] * 8, [0.0] * 8, ZoneModel(0.05, 0.0), 0.5, 0.5, 0.2)
    assert not d.skip
    assert d.lowest < -1.0
    assert d.steps == 8


def test_forecast_skips_incomplete_hours():
    body = {
        "hourly": {
            "time": ["2026-11-02T10:00", "2026-11-02T11:00"],
            "temperature_2m": [-3.0, None],
            "direct_normal_irradiance": [300.0, 100.0],
            "diffuse_radiation": [40.0, 30.0],
            "cloud_cover": [10, 20],
        }
    }
    hours = parse_forecast(body)
    assert len(hours) == 1
    assert hours[0].temperature == -3.0
    assert hours[0].light.direct_normal == 300.0


def test_light_on_surfaces_sums_walls_and_roofs():
    reading = Irradiance(datetime(2026, 11, 2, tzinfo=UTC), 400.0, 40.0)
    wall = light_on_surfaces(reading, 180.0, 20.0, ["S"], [])
    both = light_on_surfaces(reading, 180.0, 20.0, ["S"], [("S", 30.0)])
    assert both > wall > 0
    assert light_on_surfaces(reading, 180.0, 20.0, ["S"], [], shaded=True) == (
        pytest.approx(20.0)
    )


def test_ground_and_wall_terms_in_the_simulation():
    cold = simulate(20.0, [0.0] * 4, [0.0] * 4, ZoneModel(0.0, 0.0), 0.25)
    assert cold[-1] == 20.0
    buried = ZoneModel(0.0, 0.0, b=0.1)
    path = simulate(20.0, [0.0] * 4, [0.0] * 4, buried, 0.25, ground=10.0)
    assert path[-1] < 20.0
    assert path[-1] > 19.0
    walled = ZoneModel(0.0, 0.0, w=0.01)
    warm = simulate(20.0, [0.0] * 4, [0.0] * 4, walled, 0.25, wall=[100.0] * 4)
    assert warm[-1] == pytest.approx(21.0)
