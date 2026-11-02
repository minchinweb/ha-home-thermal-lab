"""Tests for the profile forecast (D) and the hybrid."""

import math

import pytest

from custom_components.home_thermal_lab.routine import (
    fill,
    fit_offset_tau,
    forecast_d,
    hybrid,
    offset_path,
    typical,
)

PER_DAY = 96


def _days(n: int, base: float = 20.0) -> list[float]:
    """A room with the same daily wave every day."""
    return [base + math.sin(2 * math.pi * (i % PER_DAY) / PER_DAY) for i in range(n)]


def test_typical_averages_the_same_time_on_earlier_days():
    values = _days(3 * PER_DAY)
    profile = typical(values, 2 * PER_DAY, PER_DAY)
    assert profile == pytest.approx(values[2 * PER_DAY : 3 * PER_DAY])


def test_typical_skips_unknown_and_future_bins():
    values = [None] * PER_DAY + [5.0] * PER_DAY
    assert typical(values, PER_DAY, 4) == [None] * 4
    assert typical(values, 2 * PER_DAY, 2) == [5.0, 5.0]


def test_offset_fades():
    path = offset_path([20.0] * 4, 21.0, 20.0, 1.0, 2.0)
    assert path[0] == pytest.approx(21.0)
    assert path[2] == pytest.approx(20.0 + math.exp(-1.0))


def test_forecast_d_is_exact_on_a_repeating_house():
    values = _days(4 * PER_DAY)
    pred = forecast_d(values, 3 * PER_DAY, PER_DAY, 0.25, 8.0)
    assert pred == pytest.approx(values[3 * PER_DAY :])


def test_offset_tau_picks_the_fading_that_happened():
    values = _days(10 * PER_DAY)
    # each day starts 1 C warm or cool in turn, and the gap fades over 4 hours
    for d in range(1, 10):
        sign = 1.0 if d % 2 else -1.0
        for k in range(PER_DAY):
            values[d * PER_DAY + k] += sign * math.exp(-k * 0.25 / 4.0)
        values[d * PER_DAY - 1] += sign
    origins = [d * PER_DAY for d in range(8, 10)]
    assert fit_offset_tau(values, origins, PER_DAY, 0.25) == 4.0


def test_hybrid_adds_the_model_departure():
    assert hybrid([20.0, 20.0], [19.0, 18.5, 18.0], [19.0, 19.0, 19.0]) == [
        19.5,
        19.0,
    ]
    assert hybrid([None, 20.0], [0.0, 1.0, 2.0], [0.0, 0.0, 0.0]) == [None, 22.0]


def test_fill_carries_the_last_value():
    assert fill([None, 1.0, None, 2.0], 0.5) == [0.5, 1.0, 1.0, 2.0]
