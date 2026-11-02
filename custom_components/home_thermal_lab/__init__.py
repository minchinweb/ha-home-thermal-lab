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


async def async_setup_entry(hass, entry) -> bool:
    """Create the sensors for a config entry and reload when it changes."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Remove the sensors of a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload(hass, entry) -> None:
    """Rebuild the sensors after a sub-entry is added, changed or removed."""
    await hass.config_entries.async_reload(entry.entry_id)
