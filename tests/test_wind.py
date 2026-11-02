"""Tests for the wind loader."""

from datetime import UTC, datetime

import pytest

from custom_components.home_thermal_lab.wind import build_url, parse_wind

BODY = {
    "hourly": {
        "time": ["2026-11-01T00:00", "2026-11-01T01:00", "2026-11-01T02:00"],
        "wind_speed_10m": [2.0, None, 5.0],
        "wind_direction_10m": [270, 90, 180],
    }
}


def test_parse_skips_missing_hours():
    readings = parse_wind(BODY)
    assert [r.speed for r in readings] == [2.0, 5.0]
    assert readings[0].time == datetime(2026, 11, 1, 0, tzinfo=UTC)


def test_face_component():
    west, south = parse_wind(BODY)
    assert west.face_component("W") == pytest.approx(2.0)
    assert west.face_component("E") == 0.0
    assert south.face_component("S") == pytest.approx(5.0)
    assert south.face_component("W") == pytest.approx(0.0, abs=1e-9)


def test_url_asks_for_ms_and_gmt():
    url = build_url(53.5, -113.5, 10)
    assert "past_days=10" in url
    assert "wind_speed_unit=ms" in url
    assert "timezone=GMT" in url
