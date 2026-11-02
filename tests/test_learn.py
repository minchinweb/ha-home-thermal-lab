"""Tests for learning a house's numbers from its history."""

from datetime import UTC, datetime, timedelta
import random

import pytest

from custom_components.home_thermal_lab.hvac import Run
from custom_components.home_thermal_lab.learn import (
    bin_fraction,
    bin_held,
    blower_kw,
    edge_steps,
    fit_no_heat,
    lag,
    least_squares,
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
    assert (fit.b, fit.w, fit.ground) == (0.0, 0.0, None)
