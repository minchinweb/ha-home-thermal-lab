"""Set up the whole integration against real Home Assistant and its recorder.

Skipped without ``homeassistant`` and ``pytest-homeassistant-custom-component``
(see ``test_archive_ha.py``).
"""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("homeassistant")
common = pytest.importorskip("pytest_homeassistant_custom_component.common")

from homeassistant.config_entries import ConfigSubentryData  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402

from custom_components.home_thermal_lab import DOMAIN, ZONE, archive, sensor  # noqa: E402
from custom_components.home_thermal_lab.archive_store import ArchiveStore, get_store  # noqa: E402
from custom_components.home_thermal_lab.forecast import ForecastHour  # noqa: E402
from custom_components.home_thermal_lab.irradiance import Irradiance  # noqa: E402

WIDE = (datetime(2020, 1, 1, tzinfo=UTC), datetime(2030, 1, 1, tzinfo=UTC))


@pytest.fixture
def offline(monkeypatch):
    """No network, no tab: Open-Meteo answers with a fixed forecast."""
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

    async def no_tab(hass):
        return

    monkeypatch.setattr(sensor, "_register_tab", no_tab)
    return hours


def make_entry(options=None):
    return common.MockConfigEntry(
        domain=DOMAIN,
        data={"outdoor_entity": "sensor.outdoor"},
        options=options or {},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=ZONE,
                title="A",
                unique_id=None,
                data={
                    "name": "A",
                    "area_id": "office",
                    "climate_entity": "climate.a",
                    "room_entity": "sensor.room_a",
                    "model": {"a": 0.1, "c": 0.0},
                },
            )
        ],
    )


async def test_setup_writes_archives_and_housekeeps(
    recorder_mock,
    hass,
    enable_custom_integrations,
    house_structure,
    offline,
    tmp_path,
):
    hass.config.config_dir = str(tmp_path)
    hass.states.async_set("sensor.outdoor", "-5.0")
    hass.states.async_set("sensor.room_a", "20.0")
    hass.states.async_set(
        "climate.a", "heat", {"temperature": 21.0, "hvac_action": "idle"}
    )
    store = get_store(hass)
    # a month long past, and records both old and recent, for the retention rule
    old = datetime.now(UTC) - timedelta(days=90)
    await store.append(
        {"v": 1, "kind": "room", "at": old.isoformat(), "zone": "sensor.x"}
    )
    entry = make_entry({"archive_keep_days": 30})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "clear_archive")
    forecast = hass.states.get("sensor.forecast_a")
    assert forecast is not None
    rooms = await store.read("room", *WIDE, zone="sensor.forecast_a")
    assert rooms
    assert rooms[0]["params"]["a"] == 0.1
    assert rooms[0]["path"]
    outdoor = await store.read("outdoor", *WIDE)
    assert outdoor
    assert all(
        datetime.fromisoformat(h[0]) > datetime.fromisoformat(outdoor[0]["at"])
        for h in outdoor[0]["hours"]
    )
    # the room records point at the outdoor fetch they used
    assert rooms[0]["outdoor_at"] == outdoor[0]["at"]
    # the retention rule ran at startup: the 90 day old record is gone
    assert await store.read("room", *WIDE, zone="sensor.x") == []


async def test_daily_housekeeping_timer_and_unload(
    recorder_mock,
    hass,
    enable_custom_integrations,
    house_structure,
    offline,
    tmp_path,
    monkeypatch,
):
    hass.config.config_dir = str(tmp_path)
    hass.states.async_set("sensor.outdoor", "-5.0")
    hass.states.async_set("sensor.room_a", "20.0")
    hass.states.async_set("climate.a", "heat", {"temperature": 21.0})
    calls = []
    original = ArchiveStore.housekeeping

    async def spy(self, keep_days=0, now=None):
        calls.append(keep_days)
        await original(self, keep_days, now)

    monkeypatch.setattr(ArchiveStore, "housekeeping", spy)
    entry = make_entry({"archive_keep_days": 10})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    store = get_store(hass)
    assert calls == [10]  # once at startup, with the option
    common.async_fire_time_changed(
        hass, datetime.now(UTC) + timedelta(days=1, minutes=1)
    )
    await hass.async_block_till_done()
    assert calls == [10, 10]  # and a day later

    # unloading stops the timer; removing the entry keeps the archive
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    common.async_fire_time_changed(hass, datetime.now(UTC) + timedelta(days=3))
    await hass.async_block_till_done()
    assert calls == [10, 10]
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert archive.stats(store.directory)["room"]  # still there
