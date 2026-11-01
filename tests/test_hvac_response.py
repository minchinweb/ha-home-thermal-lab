"""Tests for heating-episode responses."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.house_thermal_lab.hvac import Run
from custom_components.house_thermal_lab.hvac_response import (
    analyse_responses,
    merge_runs,
    temperature_series,
    value_at,
)


def at(minute):
    return datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)


def test_episode_response_with_overshoot():
    series = [
        (at(0), 20.0),
        (at(10), 20.0),
        (at(20), 20.6),  # run ends here
        (at(30), 20.9),  # keeps rising
        (at(40), 20.7),
        (at(70), 20.2),
    ]
    run = Run(at(10), at(20))
    episodes = merge_runs([run, Run(at(12), at(14)), Run(at(22), at(25))], 5.0)
    assert len(episodes) == 1  # all joined into 10-25
    (r,) = analyse_responses(episodes, series, [run], window_minutes=30)
    assert r.own_call
    assert r.t_start == 20.0
    assert r.t_end == 20.6  # value held at minute 25
    assert r.overshoot == pytest.approx(0.3)
    assert r.minutes_to_peak == pytest.approx(5.0)


def test_other_zone_call_and_short_episodes():
    series = [(at(0), 20.0), (at(30), 20.5)]
    episodes = [Run(at(5), at(7)), Run(at(10), at(25))]
    out = analyse_responses(episodes, series, own_runs=[])
    assert len(out) == 1  # the 2 minute episode is skipped
    assert not out[0].own_call


def test_follow_up_window_stops_at_next_episode():
    series = [(at(0), 20.0), (at(20), 20.2), (at(35), 21.0), (at(50), 20.1)]
    episodes = [Run(at(10), at(20)), Run(at(30), at(40))]
    first = analyse_responses(episodes, series, window_minutes=60)[0]
    assert first.overshoot == 0.0  # the 21.0 reading falls inside episode two


def test_value_at_and_series():
    series = [(at(0), 1.0), (at(10), 2.0)]
    assert value_at(series, at(5)) == 1.0
    assert value_at(series, at(10)) == 2.0
    assert value_at([], at(5)) is None
    states = [
        {
            "attributes": {"current_temperature": 20.5},
            "last_updated": "2025-01-01T00:00:00+00:00",
        },
        {"attributes": {}, "last_updated": "2025-01-01T00:05:00+00:00"},
    ]
    assert len(temperature_series(states)) == 1
