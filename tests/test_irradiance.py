"""Tests for irradiance and sun azimuth."""

from datetime import UTC, datetime

import pytest

from custom_components.house_thermal_lab.irradiance import (
    Irradiance,
    parse_irradiance,
)
from custom_components.house_thermal_lab.solar import solar_azimuth_degrees

BODY = {
    "hourly": {
        "time": ["2026-11-01T18:00", "2026-11-01T19:00"],
        "direct_normal_irradiance": [400.0, None],
        "diffuse_radiation": [50.0, 10.0],
    }
}


def test_parse_skips_missing_hours():
    readings = parse_irradiance(BODY)
    assert len(readings) == 1
    assert readings[0].direct_normal == 400.0


def test_south_wall_gets_beam_from_the_south():
    hour = Irradiance(datetime(2026, 11, 1, tzinfo=UTC), 400.0, 40.0)
    assert hour.on_face("S", 180.0, 0.0001) == pytest.approx(400.0 + 20.0, rel=1e-3)
    assert hour.on_face("N", 180.0, 30.0) == pytest.approx(20.0)
    assert hour.on_face("S", 180.0, -5.0) == 0.0


def test_azimuth_is_south_at_solar_noon_and_east_in_the_morning():
    lon = -113.5
    # solar noon at this longitude is about 19:30 UTC
    solar_noon = datetime(2026, 3, 20, 19, 30, tzinfo=UTC)
    assert solar_azimuth_degrees(solar_noon, 53.5, lon) == pytest.approx(180.0, abs=5)
    morning = datetime(2026, 3, 20, 16, 0, tzinfo=UTC)
    assert 90 < solar_azimuth_degrees(morning, 53.5, lon) < 160
