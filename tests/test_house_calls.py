"""Tests for the cooling and fan terms: the simulation, and the fits that learn them."""

import random

import pytest

from custom_components.home_thermal_lab.learn import (
    ZoneData,
    cool_thermostat,
    fit_cool_rate,
    fit_no_heat,
)
from custom_components.home_thermal_lab.shadow import (
    HouseZone,
    Thermostat,
    ZoneModel,
    simulate_house,
    simulate_house_full,
    step,
)

STEPS = 96
STEP_H = 0.25


def _zone(model, room=21.0, **kwargs):
    return HouseZone(
        model,
        room,
        [0.0] * STEPS,
        Thermostat([-50.0] * STEPS, 0.5, False),
        **kwargs,
    )


def _end(zone, outdoor=21.0):
    return simulate_house([zone], [outdoor] * STEPS, STEP_H)[0][0][-1]


def test_a_cooling_call_cools_the_room():
    model = ZoneModel(a=0.02, c=0.0, e=-2.0)
    still = _end(_zone(model))
    cooled = _end(_zone(model, cool=[1.0] * STEPS))
    assert still == pytest.approx(21.0)
    assert cooled < still - 2.0


def test_the_fan_pulls_heat_from_the_room():
    model = ZoneModel(a=0.02, c=0.0, f=-0.5)
    still = _end(_zone(model))
    pulled = _end(_zone(model, fan=[1.0] * STEPS))
    assert pulled < still - 0.8


def test_another_zones_cooling_bleeds_in():
    cooler = _zone(ZoneModel(a=0.0, c=0.0, e=-2.0), cool=[1.0] * STEPS)
    bled = _zone(ZoneModel(a=0.0, c=0.0, y=-1.0), others=(0,))
    out = simulate_house([cooler, bled], [21.0] * STEPS, STEP_H)
    assert out[1][0][-1] < 21.0 - 1.0


def test_a_simulated_air_conditioner_stops_at_its_setpoint():
    model = ZoneModel(a=0.02, c=0.0, e=-2.0)
    zone = _zone(model, room=24.0, cool_setpoint=21.0, cool_band=0.5)
    path, _, cool = simulate_house_full([zone], [24.0] * STEPS, STEP_H)[0]
    assert sum(cool) > 0
    # once it has pulled the room down, it holds it within the band
    settled = path[16:]
    assert min(settled) >= 20.9
    assert max(settled) <= 21.6


def test_a_zone_without_a_cooling_rate_is_not_simulated_to_cool():
    zone = _zone(ZoneModel(a=0.02, c=0.0), room=24.0, cool_setpoint=21.0, cool_band=0.5)
    _, _, cool = simulate_house_full([zone], [24.0] * STEPS, STEP_H)[0]
    assert sum(cool) == 0


def test_fan_and_bleed_are_learned_as_negative_terms():
    rng = random.Random(3)
    n = 600
    hours = 0.25
    truth = ZoneModel(a=0.05, c=0.01, f=-0.3, y=-0.2)
    outdoor = [-5.0 + 8 * rng.random() for _ in range(n)]
    fan = [1.0 if rng.random() < 0.3 else 0.0 for _ in range(n)]
    other_cool = [1.0 if rng.random() < 0.2 else 0.0 for _ in range(n)]
    room = [20.0]
    for i in range(n - 1):
        rate = (
            truth.a * (outdoor[i] - room[i])
            + truth.c
            + truth.f * fan[i]
            + truth.y * other_cool[i]
        )
        room.append(room[i] + rate * hours)
    fit = fit_no_heat(
        room,
        outdoor,
        [0.0] * n,
        [0.0] * n,
        hours,
        other_cool=other_cool,
        fan=fan,
    )
    assert fit.a == pytest.approx(0.05, abs=1e-3)
    assert fit.f == pytest.approx(-0.3, abs=1e-3)
    assert fit.y == pytest.approx(-0.2, abs=1e-3)


def test_a_fan_that_warms_the_room_is_not_kept():
    rng = random.Random(4)
    n = 600
    hours = 0.25
    outdoor = [-5.0 + 8 * rng.random() for _ in range(n)]
    fan = [1.0 if rng.random() < 0.3 else 0.0 for _ in range(n)]
    room = [20.0]
    for i in range(n - 1):
        rate = 0.05 * (outdoor[i] - room[i]) + 0.3 * fan[i]
        room.append(room[i] + rate * hours)
    fit = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, hours, fan=fan)
    assert fit.f == 0.0


def test_the_cooling_rate_is_learned_from_its_own_calls():
    rng = random.Random(5)
    n = 400
    hours = 0.25
    outdoor = [-5.0 + 8 * rng.random() for _ in range(n)]
    cooling = [1.0 if (i % 24) < 6 else 0.0 for i in range(n)]
    truth = ZoneModel(a=0.05, c=0.0, e=-1.5)
    room = [22.0]
    for i in range(n - 1):
        room.append(step(room[i], outdoor[i], 0.0, truth, hours, cool=cooling[i]))
    data = ZoneData(room, outdoor, [0.0] * n, [0.0] * n, hours, cooling=cooling)
    rate = fit_cool_rate(ZoneModel(a=0.05, c=0.0), data)
    assert rate == pytest.approx(-1.5, abs=0.05)


def test_the_stop_and_start_temperatures_are_read_from_the_calls():
    n = 24 * 8
    cooling = [0.0] * n
    room = [22.0] * n
    for k in range(8):
        for i in range(24 * k + 4, 24 * k + 8):
            cooling[i] = 1.0
        room[24 * k + 4] = 23.0
        room[24 * k + 8] = 21.0
    assert cool_thermostat(room, cooling) == pytest.approx((21.0, 2.0))
    assert cool_thermostat(room, [0.0] * n) is None


def _supply_history(seed, own_share=0.5):
    """A zone warmed by its own supply air (s) and pulled by the house fan (f).

    The house fan runs 70% of the time; the zone's own call is a part of that.
    """
    rng = random.Random(seed)
    n = 600
    hours = 0.25
    outdoor = [-5.0 + 8 * rng.random() for _ in range(n)]
    fan = [1.0 if rng.random() < 0.7 else 0.0 for _ in range(n)]
    own = [f if rng.random() < own_share else 0.0 for f in fan]
    truth = ZoneModel(a=0.05, c=0.01, f=-0.1, s=0.4)
    room = [20.0]
    for i in range(n - 1):
        room.append(
            step(room[i], outdoor[i], 0.0, truth, hours, fan=fan[i], own_fan=own[i])
        )
    return room, outdoor, fan, own, hours


def test_a_zones_own_supply_air_is_learned_apart_from_the_house_fan():
    room, outdoor, fan, own, hours = _supply_history(6)
    n = len(room)
    fit = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, hours, fan=fan, own_fan=own)
    assert fit.s == pytest.approx(0.4, abs=0.02)
    assert fit.f == pytest.approx(-0.1, abs=0.02)


def test_the_supply_term_may_cool_a_warm_zone():
    rng = random.Random(7)
    n = 600
    hours = 0.25
    outdoor = [-5.0 + 8 * rng.random() for _ in range(n)]
    fan = [1.0 if rng.random() < 0.7 else 0.0 for _ in range(n)]
    own = [f if rng.random() < 0.5 else 0.0 for f in fan]
    truth = ZoneModel(a=0.05, c=0.2, s=-0.3)
    room = [22.0]
    for i in range(n - 1):
        room.append(step(room[i], outdoor[i], 0.0, truth, hours, own_fan=own[i]))
    fit = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, hours, fan=fan, own_fan=own)
    assert fit.s == pytest.approx(-0.3, abs=0.02)


def test_the_supply_term_is_left_out_when_it_is_the_house_fan():
    room, outdoor, fan, _, hours = _supply_history(8)
    n = len(room)
    fit = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, hours, fan=fan, own_fan=fan)
    assert fit.s == 0.0


def test_only_the_zone_calling_for_the_fan_gets_its_supply():
    model = ZoneModel(a=0.02, c=0.0, s=0.5)
    calling = _zone(model, fan=[1.0] * STEPS, own_fan=[1.0] * STEPS)
    not_calling = _zone(model, fan=[1.0] * STEPS)
    out = simulate_house([calling, not_calling], [21.0] * STEPS, STEP_H)
    assert out[0][0][-1] > 21.0 + 0.8
    assert out[1][0][-1] == pytest.approx(21.0)


def test_the_supply_term_acts_while_the_air_conditioner_is_simulated():
    model = ZoneModel(a=0.02, c=0.0, e=-2.0, s=-0.5)
    base = _zone(model, room=21.0, cool_setpoint=25.0, cool_band=0.5)
    supplied = _zone(
        model, room=21.0, cool_setpoint=25.0, cool_band=0.5, own_fan=[1.0] * STEPS
    )
    still = simulate_house_full([base], [21.0] * STEPS, STEP_H)[0][0][-1]
    fanned = simulate_house_full([supplied], [21.0] * STEPS, STEP_H)[0][0][-1]
    assert fanned < still - 0.8
