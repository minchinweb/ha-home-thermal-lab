"""Tests for the modelled furnace energy."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.home_thermal_lab.energy import Meter, furnace_mode

T0 = datetime(2026, 11, 2, tzinfo=UTC)


def test_mode_from_zones():
    assert furnace_mode([{"equipment_running": "fan"}, {}]) == "fan"
    assert (
        furnace_mode(
            [
                {"equipment_running": "fan"},
                {"hvac_action": "heating", "equipment_running": "auxHeat1,fan"},
            ]
        )
        == "heat_low"
    )
    assert furnace_mode([{"equipment_running": "auxHeat2,fan"}]) == "heat_high"
    assert furnace_mode([{"hvac_action": "idle", "equipment_running": ""}]) == "off"


def test_meter_integrates_by_mode():
    m = Meter({"fan": 0.05, "heat_low": 0.25})
    m.advance(T0, "fan")
    m.advance(T0 + timedelta(hours=2), "heat_low")
    total = m.advance(T0 + timedelta(hours=2, minutes=30), "off")
    assert total == pytest.approx(0.1 + 0.125)
    assert m.advance(T0 + timedelta(hours=5)) == pytest.approx(total)
