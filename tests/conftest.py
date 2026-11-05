"""Shared fixtures for the tests against real Home Assistant."""

import pytest

# House Structure's summary (``hass.data["house_structure"]``) with one room
ROOMS = {
    "version": 1,
    "rooms": {
        "office": {
            "area_id": "office",
            "title": "Office",
            "volume_m3": 30.0,
            "temperature_entity": "sensor.room_a",
            "walls": [
                {
                    "face": "N",
                    "azimuth": 0.0,
                    "tilt": 90.0,
                    "area_m2": 6.0,
                    "glass_m2": 0.0,
                }
            ],
            "internal_walls": [],
            "neighbours": [],
            "windows": [],
            "roofs": [],
            "registers": [{"climate": "climate.a", "fan": None}],
        }
    },
}


@pytest.fixture
def house_structure(hass):
    """A stand-in House Structure, the lab's dependency, publishing ``ROOMS``."""
    from pytest_homeassistant_custom_component.common import (
        MockModule,
        mock_integration,
    )

    mock_integration(hass, MockModule("house_structure"))
    hass.data["house_structure"] = ROOMS
    return ROOMS
