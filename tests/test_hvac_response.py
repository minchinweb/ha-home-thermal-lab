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


def test_baseline_drift_and_excess_rate():
    # drifts down 0.2 C in the 10 minutes before a 10 minute run, then rises 0.5
    series = [(at(0), 20.2), (at(10), 20.0), (at(20), 20.5)]
    (r,) = analyse_responses([Run(at(10), at(20))], series)
    assert r.baseline_rate_per_h == pytest.approx(-1.2)
    assert r.rate_per_h == pytest.approx(3.0)
    assert r.excess_rate_per_h == pytest.approx(4.2)


def test_baseline_unknown_when_previous_episode_is_close():
    series = [(at(0), 20.0), (at(30), 20.5)]
    episodes = [Run(at(5), at(15)), Run(at(20), at(30))]
    out = analyse_responses(episodes, series)
    assert out[1].baseline_rate_per_h is None
    assert out[1].excess_rate_per_h is None


def test_solar_elevation():
    from custom_components.house_thermal_lab.solar import solar_elevation_degrees

    # Edmonton, summer solstice: about 60 degrees at noon, below -6 at midnight
    noon = datetime(2025, 6, 21, 19, 0, tzinfo=UTC)
    midnight = datetime(2025, 6, 21, 7, 0, tzinfo=UTC)
    assert solar_elevation_degrees(noon, 53.5, -113.5) == pytest.approx(60.0, abs=2.0)
    assert solar_elevation_degrees(midnight, 53.5, -113.5) < -6.0


def test_stale_readings_are_skipped():
    from custom_components.house_thermal_lab.hvac_response import reading_age_minutes

    # the room last reported 40 minutes before the run starts
    series = [(at(0), 20.0), (at(60), 21.0)]
    run = Run(at(40), at(55))
    assert reading_age_minutes(series, at(40)) == 40.0
    assert reading_age_minutes([], at(5)) is None
    assert analyse_responses([run], series, max_age_minutes=15) == []
    assert len(analyse_responses([run], series)) == 1
