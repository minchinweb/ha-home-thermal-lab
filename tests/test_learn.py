"""Tests for learning a house's numbers from its history."""

from datetime import UTC, datetime, timedelta
import math
import random

import pytest

from custom_components.home_thermal_lab.hvac import Run
from custom_components.home_thermal_lab.learn import (
    NoHeatFit,
    Skill,
    ZoneData,
    bin_fraction,
    bin_held,
    blower_kw,
    edge_steps,
    fit_heat_rate,
    fit_no_heat,
    fit_with_wall_lag,
    grade,
    idle_starts,
    lag,
    least_squares,
    model_of,
    problem,
    refine_multistep,
    simulate_from,
    skill,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_least_squares_recovers_a_line():
    x = [float(i) for i in range(10)]
    beta = least_squares([x, [1.0] * 10], [2 * v + 3 for v in x])
    assert beta == pytest.approx([2.0, 3.0])
    assert least_squares([x, x], x) is None


def test_bin_held_fills_between_changes():
    series = [(T0, 10.0), (T0 + timedelta(minutes=30), 20.0)]
    out = bin_held(series, T0, 4, timedelta(minutes=15))
    assert out == [10.0, 10.0, 20.0, 20.0]


def test_bin_held_marks_gaps():
    out = bin_held([(T0 + timedelta(minutes=20), 5.0)], T0, 2, timedelta(minutes=15))
    assert out[0] is None
    assert out[1] == 5.0


def test_bin_fraction():
    runs = [Run(T0 + timedelta(minutes=10), T0 + timedelta(minutes=20))]
    out = bin_fraction(runs, T0, 2, timedelta(minutes=15))
    assert out == pytest.approx([5 / 15, 5 / 15])


def test_fit_no_heat_recovers_the_model():
    rng = random.Random(1)
    a, c, g = 0.05, 0.02, 0.004
    hours = 0.25
    n = 400
    outdoor = [-5.0 + 8 * rng.random() for _ in range(n)]
    light = [max(0.0, 200 * rng.random() - 100) for _ in range(n)]
    room = [20.0]
    for i in range(n - 1):
        rate = a * (outdoor[i] - room[i]) + c + g * light[i]
        room.append(room[i] + rate * hours)
    heating = [0.0] * n
    heating[100] = 1.0  # one heated bin is skipped
    fit = fit_no_heat(room, outdoor, light, heating, hours)
    assert fit is not None
    assert (fit.a, fit.c, fit.g) == pytest.approx((a, c, g), abs=1e-6)
    assert fit.bins < n - 1


def test_fit_no_heat_needs_enough_idle_bins():
    room = [20.0] * 30
    assert fit_no_heat(room, room, [0.0] * 30, [0.0] * 30, 0.25) is None


def test_fit_no_heat_without_light_gives_zero_g():
    rng = random.Random(2)
    n = 200
    outdoor = [rng.uniform(-10, 0) for _ in range(n)]
    room = [20.0]
    for i in range(n - 1):
        room.append(room[i] + (0.04 * (outdoor[i] - room[i]) + 0.01) * 0.25)
    fit = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, 0.25)
    assert fit is not None
    assert fit.g == 0.0
    assert fit.a == pytest.approx(0.04, abs=1e-6)


def _power(steps: list[tuple[float, float]]):
    """Readings every 30 s: (minute, kW) segments, each held for its length."""
    out = []
    for minute, kw in steps:
        out.append((T0 + timedelta(minutes=minute), kw))
    return out


def _series(changes: list[tuple[float, float]], total: float):
    """Expand (minute, kW) changes into a reading every 30 seconds."""
    out = []
    kw = 0.0
    j = 0
    m = 0.0
    while m < total:
        while j < len(changes) and changes[j][0] <= m:
            kw = changes[j][1]
            j += 1
        out.append((T0 + timedelta(minutes=m), 0.3 + kw))
        m += 0.5
    return out


def test_edge_steps_and_blower_kw():
    # the blower alone (0.06 kW) for 10 minutes, every hour; heating one hour
    # (adds 0.2 on top of the running blower) with a step to high of 0.01
    changes, fan, heat, high = [], [], [], []
    for hour in range(8):
        base = hour * 60.0
        changes += [(base + 10, 0.06), (base + 20, 0.0)]
        fan.append(
            Run(T0 + timedelta(minutes=base + 10), T0 + timedelta(minutes=base + 20))
        )
    # a heating call at 500 min, inside a fan run that began at 490
    changes += [(490, 0.06), (500, 0.26), (515, 0.27), (530, 0.06), (540, 0.0)]
    fan.append(Run(T0 + timedelta(minutes=490), T0 + timedelta(minutes=540)))
    heat.append(Run(T0 + timedelta(minutes=500), T0 + timedelta(minutes=530)))
    high.append(Run(T0 + timedelta(minutes=515), T0 + timedelta(minutes=530)))
    power = _series(sorted(changes), 600)
    steps = edge_steps(power, heat, fan, high, edge_minutes=2.0)
    # the long run (490 to 540) also starts and ends away from the heating call
    assert steps["fan on"] == pytest.approx([0.06] * 9, abs=1e-9)
    assert steps["fan off"] == pytest.approx([-0.06] * 9, abs=1e-9)
    assert steps["heat on"] == pytest.approx([0.2], abs=1e-9)
    kw, counts = blower_kw(steps, min_edges=5)
    assert kw == {"fan": pytest.approx(0.06)}
    assert counts["fan on"] == 9
    kw, _ = blower_kw(steps, min_edges=1)
    assert kw["heat_low"] == pytest.approx(0.265)  # on 0.20, off 0.21
    assert kw["heat_high"] == pytest.approx(0.275)


def test_blower_kw_needs_edges():
    assert blower_kw({"fan on": [0.05, 0.06]}, min_edges=5)[0] == {}


def test_lag_smooths_a_step():
    out = lag([0.0, 10.0, 10.0, 10.0], 1.0, 1.0)
    assert out[0] == 0.0
    assert out[1] == pytest.approx(10 * (1 - 2.718281828**-1))
    assert out[1] < out[2] < out[3] < 10.0
    assert lag([], 1.0, 1.0) == []
    assert lag([10.0], 1.0, 1.0, start=0.0)[0] == pytest.approx(
        10 * (1 - 2.718281828**-1)
    )
    assert lag([5.0, 5.0], 1.0, 3.0) == [5.0, 5.0]


def test_fit_no_heat_recovers_wall_and_ground_terms():
    rng = random.Random(2)
    a, b, c, g, w = 0.04, 0.03, 0.01, 0.003, 0.002
    hours = 0.25
    n = 600
    outdoor = [-10.0 + 20 * rng.random() for _ in range(n)]
    ground = [6.0 + 0.5 * rng.random() for _ in range(n)]
    light = [max(0.0, 300 * rng.random() - 150) for _ in range(n)]
    wall = [max(0.0, 200 * rng.random() - 80) for _ in range(n)]
    room = [18.0]
    for i in range(n - 1):
        rate = (
            a * (outdoor[i] - room[i])
            + b * (ground[i] - room[i])
            + c
            + g * light[i]
            + w * wall[i]
        )
        room.append(room[i] + rate * hours)
    fit = fit_no_heat(room, outdoor, light, [0.0] * n, hours, wall=wall, ground=ground)
    assert fit is not None
    assert (fit.a, fit.b, fit.c, fit.g, fit.w) == pytest.approx(
        (a, b, c, g, w), abs=1e-6
    )


def test_fit_no_heat_without_wall_or_ground_leaves_them_zero():
    room = [20.0 + 0.01 * i for i in range(100)]
    outdoor = [float(i % 7) for i in range(100)]
    fit = fit_no_heat(room, outdoor, [0.0] * 100, [0.0] * 100, 0.25)
    assert fit is not None
    assert (fit.b, fit.w) == (0.0, 0.0)


def _quantised_day(seed: int, n: int = 960, quantum: float = 0.1):
    """A room that cools toward a swinging outdoors, read in ``quantum`` steps."""
    from custom_components.home_thermal_lab.shadow import ZoneModel, step

    rng = random.Random(seed)
    model = ZoneModel(a=0.02, c=0.15)
    outdoor = [-5.0 + 6 * math.sin(i / 96 * 2 * math.pi) for i in range(n)]
    true = [21.0]
    for i in range(n - 1):
        true.append(step(true[i], outdoor[i], 0.0, model, 0.25))
    room = [round((t + rng.gauss(0, 0.02)) / quantum) * quantum for t in true]
    return model, room, outdoor


def test_block_rates_beat_quantisation():
    model, room, outdoor = _quantised_day(3)
    n = len(room)
    one = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, 0.25)
    block = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, 0.25, block=4)
    assert one is not None
    assert block is not None
    assert block.method == "block"
    assert abs(block.a - model.a) <= abs(one.a - model.a) + 1e-4
    assert block.r2 > one.r2


def test_negative_sun_term_is_dropped():
    rng = random.Random(4)
    n = 300
    outdoor = [rng.uniform(-10, 0) for _ in range(n)]
    light = [max(0.0, rng.uniform(-100, 200)) for _ in range(n)]
    room = [20.0]
    for i in range(n - 1):
        rate = 0.04 * (outdoor[i] - room[i]) + 0.3 - 0.002 * light[i]
        room.append(room[i] + rate * 0.25)
    fit = fit_no_heat(room, outdoor, light, [0.0] * n, 0.25)
    assert fit is not None
    assert fit.g == 0.0


def test_problem_flags_unphysical_fits():
    assert problem(None) == "too little idle data"
    assert problem(NoHeatFit(-0.01, 0.1, 0.0, 100)) == "wrong sign"
    assert problem(NoHeatFit(0.9, 0.1, 0.0, 100)) == "out of range"
    assert problem(NoHeatFit(0.02, 0.1, 0.0, 100)) is None


def test_wall_lag_is_chosen_by_the_fit():
    rng = random.Random(5)
    n = 800
    hours = 0.25
    outdoor = [rng.uniform(-10, 0) for _ in range(n)]
    raw = [max(0.0, 400 * math.sin((i % 96) / 96 * 2 * math.pi)) for i in range(n)]
    lagged = lag(raw, hours, 6.0)
    room = [20.0]
    for i in range(n - 1):
        rate = 0.03 * (outdoor[i] - room[i]) + 0.1 + 0.002 * lagged[i]
        room.append(room[i] + rate * hours)
    fit, tau = fit_with_wall_lag(room, outdoor, [0.0] * n, [0.0] * n, hours, raw)
    assert tau == 6.0
    assert fit is not None
    assert fit.w == pytest.approx(0.002, rel=1e-3)


def _path_error(fit, data, steps=12, every=4):
    total = 0.0
    for i in idle_starts(data, steps, every):
        path = simulate_from(model_of(fit), data, i, steps)
        total += sum((path[k] - data.room[i + k]) ** 2 for k in range(1, steps + 1))
    return total


def test_skill_and_multistep_refinement():
    # the true house has a slow mass behind the air, which the one-node model
    # lacks: the rate fit is then a poor guide to the hours ahead
    rng = random.Random(6)
    n = 1344
    outdoor = [-5.0 + 6 * math.sin(i / 96 * 2 * math.pi) for i in range(n)]
    air, mass = [21.0], 21.0
    for i in range(n - 1):
        t = air[i]
        air.append(t + 0.25 * (0.03 * (outdoor[i] - t) + 0.4 * (mass - t) + 0.2))
        mass += 0.25 * 0.05 * (t - mass)
    room = [round((t + rng.gauss(0, 0.02)) / 0.1) * 0.1 for t in air]
    data = ZoneData(room, outdoor, [0.0] * n, [0.0] * n, 0.25)
    first = fit_no_heat(room, outdoor, [0.0] * n, [0.0] * n, 0.25, block=4)
    refined = refine_multistep(first, data)
    assert refined.method == "multi-step"
    assert _path_error(refined, data) < _path_error(first, data)
    after = skill(model_of(refined), data)
    assert after[12].model < after[12].hold
    assert after[12].n > 100
    assert set(after) == {4, 12}


def test_refinement_leaves_unphysical_fits_alone():
    _, room, outdoor = _quantised_day(7)
    n = len(room)
    data = ZoneData(room, outdoor, [0.0] * n, [0.0] * n, 0.25)
    bad = NoHeatFit(-0.01, 0.1, 0.0, 500)
    assert refine_multistep(bad, data) is bad


def test_heat_rate_is_recovered_from_calls():
    from custom_components.home_thermal_lab.shadow import ZoneModel, step

    model = ZoneModel(a=0.02, c=0.0, h=2.0)
    n = 400
    outdoor = [-10.0] * n
    heating = [1.0 if i % 20 in (0, 1) else 0.0 for i in range(n)]
    room = [20.0]
    for i in range(n - 1):
        room.append(step(room[i], outdoor[i], 0.0, model, 0.25, heat=heating[i]))
    data = ZoneData(room, outdoor, [0.0] * n, heating, 0.25)
    h = fit_heat_rate(ZoneModel(a=0.02, c=0.0), data)
    assert h == pytest.approx(2.0, rel=0.02)
    assert fit_heat_rate(ZoneModel(a=0.02, c=0.0), data, min_calls=1000) == 0.0


def test_grade_follows_skill_and_data():
    good = NoHeatFit(0.02, 0.1, 0.0, 500)
    assert grade(None, {}) == "none"
    assert grade(NoHeatFit(-0.02, 0.1, 0.0, 500), {}) == "none"
    assert grade(good, {}) == "none"
    assert grade(good, {12: Skill(0.5, 0.4, 50)}) == "low"
    assert grade(good, {12: Skill(0.2, 0.4, 50)}) == "high"
    assert grade(NoHeatFit(0.02, 0.1, 0.0, 200), {12: Skill(0.2, 0.4, 50)}) == "medium"
