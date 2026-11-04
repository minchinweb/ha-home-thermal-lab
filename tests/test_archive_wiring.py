"""Tests for the archive's Home Assistant wiring, with a fake ``hass``.

Home Assistant and voluptuous are not installed here, so the few modules the
wiring imports from them are stubbed in ``sys.modules``.
"""

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.home_thermal_lab import (
    DOMAIN,
    _register_services,
    archive,
    async_remove_entry,
)
from custom_components.home_thermal_lab.archive_store import KEEP_DAYS, get_store
from custom_components.home_thermal_lab.diagnostics import (
    async_get_config_entry_diagnostics,
)

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
WIDE = (datetime(2020, 1, 1, tzinfo=UTC), datetime(2030, 1, 1, tzinfo=UTC))


class FakeServices:
    def __init__(self):
        self.registered = {}

    def has_service(self, domain, name):
        return (domain, name) in self.registered

    def async_register(
        self, domain, name, handler, schema=None, supports_response=None
    ):
        self.registered[(domain, name)] = (handler, schema, supports_response)


class FakeHass:
    def __init__(self, tmp_path):
        self.data = {}
        self.services = FakeServices()
        self.config = SimpleNamespace(
            path=lambda *parts: str(tmp_path.joinpath(*parts))
        )

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class ServiceValidationError(Exception):
    pass


@pytest.fixture
def hass(tmp_path, monkeypatch):
    # the repository's own `homeassistant/` folder is a namespace package, so
    # look for a module that only the real Home Assistant has
    try:
        import homeassistant.exceptions as real
    except ImportError:
        real = None
    if real is not None:
        monkeypatch.setitem(
            globals(), "ServiceValidationError", real.ServiceValidationError
        )
        return FakeHass(tmp_path)
    core = ModuleType("homeassistant.core")
    core.SupportsResponse = SimpleNamespace(OPTIONAL="optional")
    exc = ModuleType("homeassistant.exceptions")
    exc.ServiceValidationError = ServiceValidationError
    vol = ModuleType("voluptuous")
    vol.Schema = lambda schema: schema
    vol.Optional = lambda key, default=None: key
    vol.Any = lambda *types: types
    for name, mod in (
        ("voluptuous", vol),
        ("homeassistant", ModuleType("homeassistant")),
        ("homeassistant.core", core),
        ("homeassistant.exceptions", exc),
    ):
        monkeypatch.setitem(__import__("sys").modules, name, mod)
    return FakeHass(tmp_path)


def room(at, zone="sensor.forecast_a"):
    return {"v": 1, "kind": "room", "at": at.isoformat(), "zone": zone}


def run(coro):
    return asyncio.run(coro)


def test_store_is_one_per_instance_in_the_config_directory(hass, tmp_path):
    store = get_store(hass)
    assert get_store(hass) is store
    assert store.directory == tmp_path / "home_thermal_lab" / "archive"


def test_store_append_read_and_first_at(hass):
    store = get_store(hass)

    async def go():
        assert await store.first_at("room") is None
        assert await store.append(room(NOW))
        assert not await store.append(room(NOW))  # a repeat
        await store.append(room(NOW + timedelta(minutes=15)))
        got = await store.read("room", *WIDE, zone="sensor.forecast_a")
        assert len(got) == 2
        assert await store.read("room", *WIDE, zone="sensor.other") == []
        assert await store.first_at("room") == NOW

    run(go())


def test_housekeeping_compresses_and_applies_retention(hass):
    store = get_store(hass)
    old = datetime(2026, 8, 1, tzinfo=UTC)

    async def go():
        for at in (old, NOW - timedelta(days=30), NOW):
            await store.append(room(at))
        await store.housekeeping(0, NOW)  # keep everything, but gzip August
        assert len(await store.read("room", *WIDE)) == 3
        assert (store.directory / "room-2026-08.jsonl.gz").exists()
        await store.housekeeping(10, NOW)
        left = await store.read("room", *WIDE)
        assert [r["at"] for r in left] == [NOW.isoformat()]

    run(go())


def test_diagnostics_lists_the_archive(hass):
    store = get_store(hass)
    entry = SimpleNamespace(options={KEEP_DAYS: 30})

    async def go():
        await store.append(room(NOW))
        return await async_get_config_entry_diagnostics(hass, entry)

    got = run(go())["archive"]
    assert got["keep_days"] == 30
    assert got["files"]["room"]["2026-11"]["lines"] == 1
    assert got["directory"] == str(store.directory)


def test_remove_entry_keeps_the_archive_and_says_where(hass, caplog):
    store = get_store(hass)
    run(store.append(room(NOW)))
    with caplog.at_level(logging.INFO):
        run(async_remove_entry(hass, SimpleNamespace()))
    assert any(str(store.directory) in m for m in caplog.messages)
    assert len(archive.stats(store.directory)["room"]) == 1


def call(hass, **data):
    handler = hass.services.registered[(DOMAIN, "clear_archive")][0]
    return run(handler(SimpleNamespace(data={"dry_run": True, **data})))


def test_service_is_registered_once_with_a_response(hass):
    _register_services(hass)
    _register_services(hass)
    assert list(hass.services.registered) == [(DOMAIN, "clear_archive")]
    assert hass.services.registered[(DOMAIN, "clear_archive")][2] == "optional"


def test_service_dry_run_then_real_clear(hass):
    store = get_store(hass)
    for zone in ("sensor.forecast_a", "sensor.forecast_b"):
        run(store.append(room(NOW, zone)))
    _register_services(hass)
    assert call(hass)["lines"] == 2
    assert len(run(store.read("room", *WIDE))) == 2
    got = call(hass, zones=["sensor.forecast_a"], dry_run=False)
    assert got["lines"] == 1
    left = run(store.read("room", *WIDE))
    assert [r["zone"] for r in left] == ["sensor.forecast_b"]


def test_service_rejects_bad_scopes_and_removes_nothing(hass):
    store = get_store(hass)
    run(store.append(room(NOW)))
    _register_services(hass)
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    for bad in (
        {"kinds": ["nope"]},
        {"kinds": []},
        {"zones": []},
        {"zones": ["sensor.unknown"]},
        {"before": tomorrow},
        {"before": "not a date"},
    ):
        with pytest.raises(ServiceValidationError):
            call(hass, dry_run=False, **bad)
    assert len(run(store.read("room", *WIDE))) == 1
