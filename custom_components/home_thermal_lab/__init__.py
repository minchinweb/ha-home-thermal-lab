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

DOMAIN = "home_thermal_lab"
PLATFORMS = ["sensor"]

# Sub-entry types: one per kind of sensor.
ZONE = "zone"
CALL_STATS = "call_stats"
ENERGY = "energy"
CONTRIBUTION = "contribution"
# A detached building (such as a garage): its own Manual J, S and D, apart from
# the house.
BUILDING = "building"


async def async_setup_entry(hass, entry) -> bool:
    """Create the sensors for a config entry and reload when it changes.

    It also reloads when House Structure's rooms change, since zones with an
    area take their windows, walls, thermostat and room sensor from there.
    """
    from homeassistant.core import callback

    from .options import STRUCTURE_EVENT

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))

    @callback  # runs in the event loop, as the reload needs
    def _rooms_changed(event) -> None:
        hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(hass.bus.async_listen(STRUCTURE_EVENT, _rooms_changed))
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Remove the sensors of a config entry, and the sidebar panel."""
    from .panel import async_remove_panel

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_remove_panel(hass)
    return unloaded


async def _reload(hass, entry) -> None:
    """Rebuild the sensors after a sub-entry is added, changed or removed."""
    await hass.config_entries.async_reload(entry.entry_id)
