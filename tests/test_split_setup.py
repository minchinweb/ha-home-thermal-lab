"""After the split: the Zones tab, Heat flow overlay, fitted rates and migration.

Against real Home Assistant; skipped without ``homeassistant`` and
``pytest-homeassistant-custom-component`` (see ``test_archive_ha.py``).
"""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("homeassistant")
common = pytest.importorskip("pytest_homeassistant_custom_component.common")

from homeassistant.config_entries import ConfigSubentryData  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402

from custom_components.home_thermal_lab import DOMAIN, ENERGY, ZONE, sensor  # noqa: E402
from custom_components.home_thermal_lab.forecast import ForecastHour  # noqa: E402
from custom_components.home_thermal_lab.irradiance import Irradiance  # noqa: E402
from custom_components.home_thermal_lab.migrate import MINOR_VERSION  # noqa: E402
from custom_components.home_thermal_lab.panel import (  # noqa: E402
    FITTED,
    FITTED_EVENT,
    OVERLAYS,
    TABS,
)

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
            "registers": [],
        }
    },
}


@pytest.fixture
def offline(monkeypatch):
    """No network: Open-Meteo answers with a fixed forecast."""
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    hours = [
        ForecastHour(
            now + timedelta(hours=k),
            -5.0,
            Irradiance(now + timedelta(hours=k), 0.0, 0.0, 50.0),
        )
        for k in range(-48, 72)
    ]
    monkeypatch.setattr(sensor, "fetch_forecast", lambda *a, **k: hours)
    monkeypatch.setattr(sensor, "fetch_irradiance", lambda *a, **k: [])
    return hours


def zone(**extra):
    return ConfigSubentryData(
        subentry_type=ZONE,
        title="A",
        unique_id=None,
        data={
            "name": "A",
            "area_id": "office",
            "climate_entity": "climate.a",
            "room_entity": "sensor.room_a",
            "model": {"a": 0.1, "c": 0.0},
            **extra,
        },
    )


def states(hass):
    hass.states.async_set("sensor.outdoor", "-5.0")
    hass.states.async_set("sensor.room_a", "20.0")
    hass.states.async_set(
        "climate.a", "heat", {"temperature": 21.0, "hvac_action": "idle"}
    )


async def test_tab_overlay_and_fitted_rates(
    recorder_mock, hass, enable_custom_integrations, offline, tmp_path, hass_ws_client
):
    hass.config.config_dir = str(tmp_path)
    hass.data["house_structure"] = ROOMS
    states(hass)
    fitted_events = common.async_capture_events(hass, FITTED_EVENT)
    entry = common.MockConfigEntry(
        domain=DOMAIN,
        data={"outdoor_entity": "sensor.outdoor"},
        version=1,
        minor_version=MINOR_VERSION,
        subentries_data=[zone()],
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    tab = hass.data[TABS]["zones"]
    assert tab["title"] == "Zones"
    assert tab["order"] == 30
    assert tab["url"].startswith("/home_thermal_lab_static/index.html?v=")
    assert hass.data[OVERLAYS]["heat_flow"]["command"] == "home_thermal_lab/heat_flow"
    # the given model's cooling rate, for Manual J
    assert hass.data[FITTED] == {"office": {"a": 0.1}}
    assert fitted_events

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "home_thermal_lab/heat_flow"})
    answer = await client.receive_json()
    assert answer["success"], answer
    result = answer["result"]
    assert result["as_of"]
    # 0.1 per hour over 30 m3 of air, 25 C colder outside, all through the N wall
    (outside,) = result["outside"]
    assert outside["room"] == "office"
    assert outside["face"] == "N"
    assert outside["w"] == pytest.approx(-0.1 * 25 * 30 * 1200 * 1005 / 3600, abs=0.5)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "zones" not in hass.data[TABS]
    assert "heat_flow" not in hass.data[OVERLAYS]
    assert FITTED not in hass.data


async def test_old_entries_lose_the_moved_settings(
    recorder_mock, hass, enable_custom_integrations, offline, tmp_path
):
    hass.config.config_dir = str(tmp_path)
    states(hass)
    entry = common.MockConfigEntry(
        domain=DOMAIN,
        data={"outdoor_entity": "sensor.outdoor", "wall_r": 20.0, "rotation": 10.0},
        version=1,
        minor_version=1,
        subentries_data=[
            zone(),
            ConfigSubentryData(
                subentry_type=ENERGY,
                title="Furnace",
                unique_id=None,
                data={
                    "name": "Furnace",
                    "climate_entities": ["climate.a"],
                    "kw": {"fan": 0.04},
                    "afue": 0.95,
                    "blower_curve": "400 = 0.3, 800 = 0.2",
                    "blower": [[0.19, 75.0], [0.38, 50.0]],
                    "ac_total_w": 8800.0,
                    "area_id": "basement",
                },
            ),
            ConfigSubentryData(
                subentry_type="building",
                title="Garage",
                unique_id=None,
                data={"name": "Garage", "areas": ["garage"], "indoor_heat_c": 10.0},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert entry.minor_version == MINOR_VERSION
    assert entry.data == {"outdoor_entity": "sensor.outdoor", "rotation": 10.0}
    kinds = sorted(s.subentry_type for s in entry.subentries.values())
    assert kinds == [ENERGY, ZONE]
    (energy,) = [s for s in entry.subentries.values() if s.subentry_type == ENERGY]
    assert dict(energy.data) == {
        "name": "Furnace",
        "climate_entities": ["climate.a"],
        "kw": {"fan": 0.04},
    }
