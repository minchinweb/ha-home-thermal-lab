"""Tests for whole-house power around events."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.home_thermal_lab.hvac import Run
from custom_components.home_thermal_lab.power import (
    power_series,
    steps_around,
    time_weighted_mean,
)


def at(minute):
    return datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)


def test_time_weighted_mean_holds_values():
    series = [(at(0), 1.0), (at(10), 3.0)]
    assert time_weighted_mean(series, at(0), at(20)) == pytest.approx(2.0)
    assert time_weighted_mean(series, at(5), at(15)) == pytest.approx(2.0)
    assert time_weighted_mean(series, at(12), at(18)) == pytest.approx(3.0)
    assert time_weighted_mean(series, at(-5), at(-1)) is None
    assert time_weighted_mean(series, at(5), at(5)) is None


def test_power_series_skips_bad_states():
    states = [
        {"state": "1.5", "last_changed": "2025-01-01T00:00:00+00:00"},
        {"state": "unavailable", "last_changed": "2025-01-01T00:01:00+00:00"},
    ]
    assert power_series(states) == [(at(0), 1.5)]


def test_steps_around_a_run():
    # 1 kW, then 2.5 kW while running 30-50, then back to 1 kW
    series = [(at(0), 1.0), (at(30), 2.5), (at(50), 1.0)]
    (step,) = steps_around([Run(at(30), at(50))], series)
    assert step.before == pytest.approx(1.0)
    assert step.during == pytest.approx(2.5)
    assert step.rise == pytest.approx(1.5)
    assert step.fall == pytest.approx(-1.5)


def test_short_runs_are_skipped():
    series = [(at(0), 1.0)]
    assert steps_around([Run(at(30), at(33))], series) == []
