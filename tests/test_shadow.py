"""Tests for the shadow controller and forecast loader."""

from datetime import UTC, datetime
import math

import pytest

from custom_components.home_thermal_lab.forecast import parse_forecast
from custom_components.home_thermal_lab.irradiance import (
    Irradiance,
    light_on_surfaces,
)
from custom_components.home_thermal_lab.shadow import (
    Thermostat,
    ZoneModel,
    decide,
    simulate,
    simulate_heated,
    step,
)


def test_simulation_cools_toward_outdoors():
    model = ZoneModel(a=0.02, c=0.0)
    path = simulate(20.0, [0.0] * 4, [0.0] * 4, model, 1.0)
    assert len(path) == 5
    assert path[1] == pytest.approx(20.0 * math.exp(-0.02))
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


def test_exact_step_matches_fine_euler_and_ignores_step_size():
    model = ZoneModel(a=0.3, c=0.5, g=0.01, b=0.1)
    fine = 20.0
    for _ in range(10000):
        rate = 0.3 * (-5.0 - fine) + 0.5 + 0.01 * 100.0 + 0.1 * (8.0 - fine)
        fine += rate * 0.0004
    one = step(20.0, -5.0, 100.0, model, 4.0, ground=8.0)
    many = simulate(20.0, [-5.0] * 16, [100.0] * 16, model, 0.25, ground=8.0)[-1]
    assert one == pytest.approx(fine, abs=1e-3)
    assert many == pytest.approx(one)


def test_thermostat_heats_to_the_setpoint_and_stops_there():
    model = ZoneModel(a=0.02, c=0.0, h=2.0)
    stat = Thermostat([20.0] * 16, deadband=0.5)
    path, duty = simulate_heated(19.0, [0.0] * 16, [0.0] * 16, model, 0.25, stat)
    assert duty[0] == 1.0
    assert 19.9 < max(path) <= 20.0  # off at 20, then the rest of the step cools
    first_off = duty.index(next(d for d in duty if d < 1.0))
    assert 0.0 < duty[first_off] < 1.0
    assert path[first_off + 1] < 20.0
    assert sum(duty) < 16


def test_thermostat_waits_for_the_deadband():
    model = ZoneModel(a=0.02, c=0.0, h=2.0)
    stat = Thermostat([20.0] * 4, deadband=0.5)
    path, duty = simulate_heated(19.8, [0.0] * 4, [0.0] * 4, model, 0.25, stat)
    assert duty == [0.0] * 4
    assert path == pytest.approx(simulate(19.8, [0.0] * 4, [0.0] * 4, model, 0.25))


def test_thermostat_without_a_heating_rate_cannot_heat():
    model = ZoneModel(a=0.02, c=0.0)
    stat = Thermostat([22.0] * 4, heating=True)
    _, duty = simulate_heated(18.0, [0.0] * 4, [0.0] * 4, model, 0.25, stat)
    assert duty == [0.0] * 4


def test_thermostat_holds_the_setpoint_over_a_cold_day():
    model = ZoneModel(a=0.02, c=0.0, h=1.5)
    stat = Thermostat([21.0] * 96, deadband=0.3)
    path, duty = simulate_heated(21.0, [-20.0] * 96, [0.0] * 96, model, 0.25, stat)
    assert min(path) > 20.4  # the deadband, less one step of cooling
    assert max(path) <= 21.0 + 1e-9
    # long run duty matches the loss: a * (21 + 20) / h
    assert sum(duty[8:]) / len(duty[8:]) == pytest.approx(0.02 * 41 / 1.5, rel=0.1)
