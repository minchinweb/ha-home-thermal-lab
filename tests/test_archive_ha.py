"""Tests of the archive wiring against real Home Assistant objects.

They need ``homeassistant`` and ``pytest-homeassistant-custom-component``,
which the project does not install (Home Assistant does not run on Windows), so
they are skipped without them. Run them where those are installed, for example
in WSL: ``pytest -o asyncio_mode=auto tests/test_archive_ha.py``.
"""

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from custom_components.home_thermal_lab import DOMAIN, archive, sensor
from custom_components.home_thermal_lab.archive_store import (
    ArchiveStore,
    get_store,
)
from custom_components.home_thermal_lab.forecast import ForecastHour
from custom_components.home_thermal_lab.house import ZoneAhead
from custom_components.home_thermal_lab.irradiance import Irradiance
from custom_components.home_thermal_lab.shadow import ZoneModel

WIDE = (datetime(2020, 1, 1, tzinfo=UTC), datetime(2030, 1, 1, tzinfo=UTC))
ENTITY = "sensor.forecast_a"
T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _custom(enable_custom_integrations):
    return


@pytest.fixture
def clock(monkeypatch):
    """Control ``datetime.now`` inside ``sensor``."""
    state = {"now": T0}

    class Fake(datetime):
        @classmethod
        def now(cls, tz=None):
            return state["now"]

    monkeypatch.setattr(sensor, "datetime", Fake)
    return state


@pytest.fixture
def store(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    return get_store(hass)


def make_sensor(hass, *, method="hybrid", d=True, model=True):
    zone = {
        "name": "A",
        "climate_entity": "climate.a",
        "room_entity": "sensor.room_a",
        "tolerance": 0.5,
        "deadband": 0.1,
    }
    temps = [20.0 + 0.01 * k for k in range(97)]
    ahead = ZoneAhead(temps, [0.0] * 96, method, None, None, [19.0] * 96 if d else None)
    got = SimpleNamespace(
        ahead=ahead, outdoor=[0.0] * 96, plan=[21.0] * 96, shift=0.5, neighbour=None
    )

    async def get_ahead(key, now):
        return got

    brain = SimpleNamespace(
        hass=hass,
        zone=zone,
        key="climate.a",
        model=ZoneModel(0.1, 0.0) if model else None,
        note="learned",
        wave=None,
        names=lambda keys: list(keys),
        neighbours=("Hall",),
        quality={"fitted_at": "2026-11-04T06:00:00+00:00"},
        forecast=SimpleNamespace(fetched=T0 - timedelta(minutes=20)),
        house=SimpleNamespace(ahead=get_ahead),
        entities={},
    )
    entity = sensor.ZoneForecastSensor(brain)
    entity.hass = hass
    entity.entity_id = ENTITY
    hass.states.async_set("climate.a", "heat", {"temperature": 21.0})
    hass.states.async_set("sensor.room_a", "20.0")
    return entity


async def test_refresh_archives_a_room_record(hass, store, clock):
    entity = make_sensor(hass)
    await entity._refresh(None)
    await hass.async_block_till_done()
    (record,) = await store.read("room", *WIDE)
    attrs = entity.extra_state_attributes
    assert record["zone"] == ENTITY
    assert record["at"] == attrs["issued"] == T0.isoformat()
    for name in ("start", "setpoint", "method", "neighbours"):
        assert record[name] == attrs[name]
    assert record["leads"]["1"] == attrs["predicted_1h"]
    assert record["leads"]["6"] == attrs["predicted_6h"]
    assert record["leads"]["3"] == entity.native_value
    assert record["leads_d"] == {"1": 19.0, "3": 19.0, "6": 19.0}
    assert record["fallback"] is None
    assert record["outdoor_shift"] == 0.5
    assert record["outdoor_at"] == (T0 - timedelta(minutes=20)).isoformat()
    assert record["params"]["a"] == 0.1
    assert record["path"][0] == [0, 20.0]
    assert len(record["path"]) == 97
    assert attrs["archive_errors"] == 0


async def test_path_only_on_the_first_issue_of_each_hour(hass, store, clock):
    entity = make_sensor(hass)
    for minutes in (0, 15, 45, 60):
        clock["now"] = T0 + timedelta(minutes=minutes)
        await entity._refresh(None)
        await hass.async_block_till_done()
    records = await store.read("room", *WIDE)
    assert ["path" in r for r in records] == [True, False, False, True]


async def test_profile_and_held_forecasts(hass, store, clock):
    profile = make_sensor(hass, method="profile", model=False)
    await profile._refresh(None)
    held = make_sensor(hass, method="held", model=False, d=False)
    clock["now"] = T0 + timedelta(minutes=15)
    await held._refresh(None)
    await hass.async_block_till_done()
    first, second = await store.read("room", *WIDE)
    assert first["fallback"] == "no usable fit"
    assert all(v is None for v in first["params"].values())
    assert second["leads"] == {"1": None, "3": None, "6": None}
    assert second["leads_d"] == {"1": None, "3": None, "6": None}
    assert held.native_value is None


async def test_archive_failure_is_counted_and_warned_hourly(
    hass, store, clock, monkeypatch, caplog
):
    async def broken(self, record):
        raise OSError("disk full")

    monkeypatch.setattr(ArchiveStore, "append", broken)
    entity = make_sensor(hass)
    with caplog.at_level(logging.WARNING):
        for minutes in (0, 15, 30, 60):
            clock["now"] = T0 + timedelta(minutes=minutes)
            await entity._refresh(None)
            await hass.async_block_till_done()
    assert entity._archive_errors == 4
    # the attribute is written before the append task runs, so it trails by one
    assert entity.extra_state_attributes["archive_errors"] == 3
    warned = [m for m in caplog.messages if "Could not archive the forecast" in m]
    assert len(warned) == 2  # at 0 and at 60 minutes
    assert entity.native_value is not None  # the sensor kept working


def stamp(t):
    return {"last_changed": t.isoformat(), "last_updated": t.isoformat()}


@pytest.fixture
def room_rows(monkeypatch):
    """A room that sits at 20.0 all week, and one old recorded forecast."""
    flat = [
        {"state": "20.0", "attributes": {}, **stamp(T0 - timedelta(hours=h))}
        for h in range(8 * 24, 0, -3)
    ]
    old_at = T0 - timedelta(days=6)
    old = {
        "state": "20.5",
        **stamp(old_at),
        "attributes": {
            "issued": old_at.isoformat(),
            "start": 20.0,
            "predicted_1h": 20.5,
            "predicted_6h": 20.5,
        },
    }

    async def fake(hass, ids, start, end):
        return {i: (flat if i == "sensor.room_a" else [old]) for i in ids}

    monkeypatch.setattr(sensor, "_recorded", fake)


def archived(at, h, d):
    return {
        "v": 1,
        "kind": "room",
        "at": at.isoformat(),
        "zone": ENTITY,
        "start": 20.0,
        "leads": {"1": h, "3": None, "6": None},
        "leads_d": {"1": d, "3": None, "6": None},
    }


async def test_score_sources(hass, store, clock, room_rows):
    entity = make_sensor(hass)
    await entity._score()  # nothing archived yet: the recorder alone
    assert entity._scores["scored_from"] == "recorder"
    assert entity._scores["error_1h"]["bias"] == 0.5

    # the archive began 3 days ago: it covers its part, the recorder the rest
    await store.append(archived(T0 - timedelta(days=3), 20.2, 19.0))
    await entity._score()
    assert entity._scores["scored_from"] == "both"
    assert entity._scores["error_1h"]["n"] == 2
    assert entity._scores["error_d_1h"]["bias"] == -1.0
    assert "error_d_3h" not in entity._scores  # null leads are not scored

    # an archive that covers the whole window needs no recorder
    await store.append(archived(T0 - timedelta(days=7), 20.4, 19.0))
    await entity._score()
    assert entity._scores["scored_from"] == "archive"
    assert entity._scores["error_1h"]["n"] == 2
    assert entity._scores["error_1h"]["bias"] == pytest.approx(0.3)


async def test_outdoor_forecast_is_archived_on_fetch(hass, store, monkeypatch):
    now = datetime.now(UTC).replace(microsecond=0)

    def hour(offset):
        end = now + timedelta(hours=offset)
        return ForecastHour(end, 1.0 + offset, Irradiance(end, 100.0, 50.0, 30.0))

    monkeypatch.setattr(sensor, "fetch_forecast", lambda *a, **k: [hour(-2), hour(1)])
    cache = sensor._Forecast(hass)
    cache.bias_of = lambda: (0.4, 12)
    assert cache.fetched is None
    await cache.hours()
    (record,) = await store.read("outdoor", *WIDE)
    assert record["at"] == cache.fetched.isoformat()
    assert record["model"] == "best_match"
    assert (record["bias"], record["bias_hours"]) == (0.4, 12)
    assert [h[0] for h in record["hours"]] == [hour(1).time.isoformat()]  # no past
    assert record["hours"][0][1:] == [2.0, 100.0, 50.0, 30.0]
    await cache.hours()  # cached: no second fetch, no second record
    assert len(await store.read("outdoor", *WIDE)) == 1


async def test_a_failed_archive_write_keeps_the_forecast(hass, store, monkeypatch):
    now = datetime.now(UTC)
    hours = [ForecastHour(now + timedelta(hours=1), 3.0, Irradiance(now, 0, 0, 0))]
    monkeypatch.setattr(sensor, "fetch_forecast", lambda *a, **k: hours)

    async def broken(self, record):
        raise OSError("read-only")

    monkeypatch.setattr(ArchiveStore, "append", broken)
    cache = sensor._Forecast(hass)
    assert await cache.hours() == hours
    assert cache.fetched is not None


async def test_options_flow_sets_the_retention(hass, store):
    from homeassistant.data_entry_flow import FlowResultType
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.home_thermal_lab.config_flow import ArchiveOptionsFlow

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    flow = ArchiveOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    form = await flow.async_step_init()
    assert form["type"] is FlowResultType.FORM
    assert form["data_schema"]({})["archive_keep_days"] == 0
    done = await flow.async_step_init({"archive_keep_days": 45.0})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["data"] == {"archive_keep_days": 45}


async def test_real_service_registration_and_clear(hass, store):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.home_thermal_lab import _register_services

    await store.append(archived(T0, 20.0, 19.0))
    _register_services(hass)
    assert hass.services.has_service(DOMAIN, "clear_archive")
    got = await hass.services.async_call(
        DOMAIN, "clear_archive", {}, blocking=True, return_response=True
    )
    assert got["dry_run"] is True
    assert got["lines"] == 1
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "clear_archive", {"zones": ["sensor.nope"]}, blocking=True
        )
    got = await hass.services.async_call(
        DOMAIN,
        "clear_archive",
        {"kinds": ["room"], "dry_run": False},
        blocking=True,
        return_response=True,
    )
    assert got["lines"] == 1
    assert archive.stats(store.directory) == {}
