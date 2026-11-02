"""House Structure: the rooms, walls, roofs, windows and registers of a house.

Each part is a sub-entry of the integration and a device in a Home Assistant
area, so the house's rooms are its areas. A room's own size (floor area,
ceiling height, volume) is a part too, as is each heating register, which ties
a thermostat (and the register's fan, if it has one) to the room it heats. The
devices carry sensors: the sun on each wall and roof, the solar heat through
each window (less what its blind keeps out) and through all of a room's
windows, the temperature difference across each internal wall, and whether
each register is heating. Other integrations, such as Home Thermal Lab, find a
room's parts by its area.

Set up from the web interface only (see ``config_flow.py``). Light comes from
Open-Meteo every 15 minutes for the home location.

The modules other than ``config_flow.py``, ``coordinator.py`` and ``sensor.py``
use only the standard library, so the tests can import them without Home
Assistant installed. That is why this file imports Home Assistant only inside
its functions.
"""

from __future__ import annotations

DOMAIN = "house_structure"
PLATFORMS = ["binary_sensor", "sensor"]

# Sub-entry types: one per kind of part.
WALL = "wall"
ROOF = "roof"
WINDOW = "window"
INTERNAL_WALL = "internal_wall"
ROOM = "room"
REGISTER = "register"


async def async_setup_entry(hass, entry) -> bool:
    """Fetch the sky, then create the devices and sensors."""
    from .coordinator import SkyCoordinator
    from .devices import HouseData, elements_of, register_devices

    coordinator = SkyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    elements = elements_of(entry)
    register_devices(hass, entry, elements)
    entry.runtime_data = HouseData(coordinator, elements)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Remove the sensors."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload(hass, entry) -> None:
    """Rebuild after a part is added, changed or removed."""
    await hass.config_entries.async_reload(entry.entry_id)
