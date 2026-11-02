"""Tests for the annual ground-temperature wave."""

from datetime import UTC, datetime

import pytest

from custom_components.home_thermal_lab.ground import ground_temperature


def test_ground_is_coldest_on_the_coldest_day():
    cold = ground_temperature(datetime(2026, 4, 5, 0, tzinfo=UTC), 6.0, 5.0, 95)
    assert cold == pytest.approx(1.0, abs=0.05)  # day 95 is 5 April
    warm = ground_temperature(datetime(2026, 10, 4, 12, tzinfo=UTC), 6.0, 5.0, 95)
    assert warm == pytest.approx(11.0, abs=0.1)


def test_ground_mean_half_way():
    day = datetime(2026, 7, 4, tzinfo=UTC)  # about a quarter year after day 95
    assert ground_temperature(day, 6.0, 5.0, 95) == pytest.approx(6.0, abs=0.5)
