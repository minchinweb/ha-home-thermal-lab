"""Home Thermal Lab: experiments on house thermal behaviour, run inside Home Assistant.

Set up from the web (Settings > Devices & services > Add integration; each
sensor is then added as a sub-entry, see ``config_flow.py``) or in YAML through
the ``sensor`` platform (see ``sensor.py`` and the README). See ``hypotheses/``
at the repository root for the experiments.

The modules other than ``sensor.py`` and ``config_flow.py`` use only the
standard library, so the scripts and tests can import them without Home
Assistant installed. That is why this file imports nothing from Home Assistant
and defines no ``async_setup``.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "home_thermal_lab"
PLATFORMS = ["sensor"]

# Sub-entry types: one per kind of sensor.
ZONE = "zone"
CALL_STATS = "call_stats"
ENERGY = "energy"
CONTRIBUTION = "contribution"


async def async_setup_entry(hass, entry) -> bool:
    """Create the sensors for a config entry and reload when it changes.

    It also reloads when House Structure's rooms change, since zones with an
    area take their windows, walls, thermostat and room sensor from there.
    """
    from datetime import timedelta

    from homeassistant.core import callback
    from homeassistant.helpers.event import async_track_time_interval

    from .archive_store import KEEP_DAYS, get_store
    from .options import STRUCTURE_EVENT

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    _register_services(hass)

    async def _housekeeping(_now=None) -> None:
        try:
            await get_store(hass).housekeeping(int(entry.options.get(KEEP_DAYS, 0)))
        except Exception:
            _LOGGER.warning("Archive housekeeping failed", exc_info=True)

    entry.async_on_unload(
        async_track_time_interval(hass, _housekeeping, timedelta(days=1))
    )
    hass.async_create_task(_housekeeping())

    @callback  # runs in the event loop, as the reload needs
    def _rooms_changed(event) -> None:
        hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(hass.bus.async_listen(STRUCTURE_EVENT, _rooms_changed))
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Remove the sensors of a config entry, the Zones tab and the overlay."""
    from .panel import async_remove_tab

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_remove_tab(hass)
    return unloaded


async def async_migrate_entry(hass, entry) -> bool:
    """Remove the settings that moved to House Structure and Manual J (``migrate``)."""
    from .migrate import (
        BUILDING,
        ENVELOPE_KEYS,
        MINOR_VERSION,
        NAMEPLATE_KEYS,
        moved,
        without,
    )

    if entry.version > 1:
        return False  # from a newer version of the lab
    if entry.minor_version >= MINOR_VERSION:
        return True
    gone = moved(entry.data, ENVELOPE_KEYS)
    if gone:
        _LOGGER.warning(
            "The envelope defaults (%s) moved to Manual J and were removed from "
            "Home Thermal Lab; set them in Manual J",
            ", ".join(gone),
        )
    for subentry in list(entry.subentries.values()):
        if subentry.subentry_type == BUILDING:
            _LOGGER.warning(
                "The building %r moved to House Structure (a Building part) and "
                "its setpoints to Manual J; it was removed from Home Thermal Lab",
                subentry.title,
            )
            hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
        elif subentry.subentry_type == ENERGY:
            nameplate = moved(subentry.data, NAMEPLATE_KEYS)
            if nameplate:
                _LOGGER.warning(
                    "%s: the furnace and air conditioner nameplate (%s) moved to "
                    "House Structure's Furnace and Air conditioner parts and was "
                    "removed from Home Thermal Lab",
                    subentry.title,
                    ", ".join(nameplate),
                )
                hass.config_entries.async_update_subentry(
                    entry, subentry, data=without(subentry.data, NAMEPLATE_KEYS)
                )
    hass.config_entries.async_update_entry(
        entry, data=without(entry.data, ENVELOPE_KEYS), minor_version=MINOR_VERSION
    )
    return True


async def _reload(hass, entry) -> None:
    """Rebuild the sensors after a sub-entry is added, changed or removed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass, entry) -> None:
    """Keep the archive: its forecasts cannot be rebuilt, so say where it is."""
    from .archive_store import get_store

    _LOGGER.info(
        "Home Thermal Lab was removed, but its forecast archive was kept in %s. "
        "Run the home_thermal_lab.clear_archive service before removing the "
        "integration, or delete that directory, to remove it.",
        get_store(hass).directory,
    )


def _register_services(hass) -> None:
    """Register ``clear_archive`` once per Home Assistant instance."""
    from datetime import UTC, date, datetime

    from homeassistant.core import SupportsResponse
    from homeassistant.exceptions import ServiceValidationError
    import voluptuous as vol

    from .archive import KINDS
    from .archive_store import get_store

    if hass.services.has_service(DOMAIN, "clear_archive"):
        return

    async def clear_archive(call):
        kinds = call.data.get("kinds")
        zones = call.data.get("zones")
        before = call.data.get("before")
        if kinds is not None and (not kinds or any(k not in KINDS for k in kinds)):
            raise ServiceValidationError(f"kinds must be some of {', '.join(KINDS)}")
        if before is not None:
            if isinstance(before, str):
                try:
                    before = date.fromisoformat(before)
                except ValueError as err:
                    raise ServiceValidationError("before must be a date") from err
            if before > datetime.now(UTC).date():
                raise ServiceValidationError("before is in the future")
        store = get_store(hass)
        if zones is not None:
            if not zones:
                raise ServiceValidationError("zones is empty; leave it out for all")
            known = {z for z in await _archived_zones(store) | _live_zones(hass)}
            unknown = sorted(set(zones) - known)
            if unknown:
                raise ServiceValidationError(f"unknown zones: {', '.join(unknown)}")
        return await store.clear(
            kinds=kinds, zones=zones, before=before, dry_run=call.data["dry_run"]
        )

    hass.services.async_register(
        DOMAIN,
        "clear_archive",
        clear_archive,
        schema=vol.Schema(
            {
                vol.Optional("kinds"): [str],
                vol.Optional("zones"): [str],
                vol.Optional("before"): vol.Any(date, str),
                vol.Optional("dry_run", default=True): bool,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )


async def _archived_zones(store) -> set[str]:
    found = set()
    for months in (await store.stats()).get("room", {}).values():
        found.update(months["zones"])
    return found


def _live_zones(hass) -> set[str]:
    return {
        b.entities["forecast"]
        for b in hass.data.get(DOMAIN, {}).get("zones", {}).values()
        if "forecast" in b.entities
    }
