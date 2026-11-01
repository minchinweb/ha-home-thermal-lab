"""Tests for weather classes, groups, ranges, bands and Home Assistant history."""

from datetime import UTC, date, datetime
import math

import pytest

from custom_components.house_thermal_lab import experiments, ha_history, stats, weather
from custom_components.house_thermal_lab.locations import Location
from custom_components.house_thermal_lab.readings import Reading, SolarReading

HERE = Location("Here", 50.0, 0.0, "home")


def _day(day, mean=10.0, amp=5.0, peak=15.0, code=None, cloud=None):
    """24 hourly solar readings of a clean sinusoid."""
    return [
        SolarReading(
            float(h),
            mean + amp * math.cos(2 * math.pi * (h - peak) / 24),
            code,
            cloud,
        )
        for h in range(24)
    ]


def test_percentile_interpolates():
    assert stats.percentile([1, 2, 3, 4], 0) == 1
    assert stats.percentile([1, 2, 3, 4], 100) == 4
    assert stats.percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert stats.percentile([5], 90) == 5


def test_percentile_rejects_bad_input():
    with pytest.raises(ValueError, match="no values"):
        stats.percentile([], 50)
    with pytest.raises(ValueError, match="between"):
        stats.percentile([1], 101)


@pytest.mark.parametrize(
    ("day", "latitude", "expected"),
    [
        (date(2025, 1, 15), 53.0, "winter"),
        (date(2025, 12, 1), 53.0, "winter"),
        (date(2025, 4, 15), 53.0, "spring"),
        (date(2025, 7, 15), 53.0, "summer"),
        (date(2025, 10, 15), 53.0, "autumn"),
        (date(2025, 7, 15), -17.0, "winter"),
        (date(2025, 1, 15), -17.0, "summer"),
    ],
)
def test_season(day, latitude, expected):
    assert weather.season(day, latitude) == expected


def test_classify_weather():
    snow = [SolarReading(h, 0.0, 73) for h in range(4)]
    rain = [SolarReading(h, 5.0, 61) for h in range(4)]
    storm = [SolarReading(0, 5.0, 95)]
    sunny = [SolarReading(h, 5.0, 0, 5.0) for h in range(24)]
    partly = [SolarReading(h, 5.0, 2, 50.0) for h in range(24)]
    cloudy = [SolarReading(h, 5.0, 3, 95.0) for h in range(24)]
    assert weather.classify_weather(snow) == "snow"
    assert weather.classify_weather(rain) == "rain"
    assert weather.classify_weather(storm) == "storm"
    assert weather.classify_weather(sunny) == "sunny"
    assert weather.classify_weather(partly) == "partly cloudy"
    assert weather.classify_weather(cloudy) == "cloudy"
    assert weather.classify_weather([SolarReading(0, 1.0)]) == "unknown"


def test_range_and_peak_to_trough():
    results = experiments.analyse_days({date(2025, 6, 1): _day(None)}, 50.0)
    (r,) = results
    assert r.observed_range == pytest.approx(10.0)
    assert r.fitted_range == pytest.approx(10.0)
    # peak at 15 h, trough at 3 h: 12 h from peak forward to trough
    assert r.peak_to_trough_h == pytest.approx(12.0)


def test_groups_by_season_and_weather():
    days = {
        date(2025, 1, 10): _day(None, code=73),
        date(2025, 1, 11): _day(None, code=73),
        date(2025, 7, 10): _day(None, cloud=5.0),
    }
    results = experiments.analyse_days(days, 50.0)
    assert list(experiments.group_results(results, "season")) == ["winter", "summer"]
    assert list(experiments.group_results(results, "all")) == ["all"]
    weather_groups = experiments.group_results(results, "weather")
    assert list(weather_groups) == ["sunny", "snow"]
    assert len(weather_groups["snow"]) == 2
    with pytest.raises(ValueError, match="group by"):
        experiments.group_results(results, "colour")


def test_weather_by_day_overrides():
    day = date(2025, 6, 1)
    (r,) = experiments.analyse_days({day: _day(None)}, 50.0, {day: "rain"})
    assert r.weather == "rain"


def test_average_fit_recovers_common_wave():
    days = {date(2025, 6, d): _day(None, amp=4.0, peak=14.0) for d in range(1, 6)}
    results = experiments.analyse_days(days, 50.0)
    amp, peak = experiments.average_fit(results)
    assert amp == pytest.approx(4.0)
    assert peak == pytest.approx(14.0)


def test_bands_are_ordered():
    days = {date(2025, 6, d): _day(None, amp=float(d)) for d in range(1, 11)}
    bands = experiments.profile_bands(experiments.analyse_days(days, 50.0))
    for hour in bands[50]:
        values = [bands[q][hour] for q in (10, 25, 50, 75, 90)]
        assert values == sorted(values)


def test_external_weather_is_used():
    sensor = [Reading(datetime(2025, 6, 1, h), 10 + h % 5 * 1.0) for h in range(24)]
    wx = [Reading(datetime(2025, 6, 1, h), 0.0, 3, 95.0) for h in range(24)]
    (r,) = experiments.analyse_with_external_weather(sensor, wx, HERE)
    assert r.weather == "cloudy"


def test_hourly_means_skips_bad_states_and_averages():
    states = [
        {"state": "10", "last_changed": "2025-06-01T00:10:00+00:00"},
        {"state": "12", "last_changed": "2025-06-01T00:40:00+00:00"},
        {"state": "unavailable", "last_changed": "2025-06-01T01:00:00+00:00"},
        {"state": "oops", "last_changed": "2025-06-01T01:30:00+00:00"},
        {"state": "20", "last_changed": "2025-06-01T02:00:00-06:00"},
    ]
    out = ha_history.hourly_means(states)
    assert out == [
        Reading(datetime(2025, 6, 1, 0), 11.0),
        Reading(datetime(2025, 6, 1, 8), 20.0),
    ]


def test_fetch_sensor_history_builds_request():
    seen = []

    def fake(url, token):
        seen.append((url, token))
        return [[{"state": "5", "last_changed": "2025-06-01T00:00:00+00:00"}]]

    start = datetime(2025, 6, 1, tzinfo=UTC)
    out = ha_history.fetch_sensor_history(
        "http://ha:8123/", "tok", "sensor.out", start, start, fake
    )
    url, token = seen[0]
    assert token == "tok"
    assert "/api/history/period/" in url
    assert "filter_entity_id=sensor.out" in url
    assert out[0].temperature == 5.0


def test_fetch_home_position():
    pos = ha_history.fetch_home_position(
        "http://ha:8123", "t", lambda _u, _t: {"latitude": 53.5, "longitude": -113.5}
    )
    assert pos == (53.5, -113.5)
