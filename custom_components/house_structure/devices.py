"""One device per part of the house, kept in the part's area."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr

from . import DOMAIN, INTERNAL_WALL, REGISTER, ROOF, ROOM, WALL, WINDOW
from .coordinator import SkyCoordinator
from .model import Element, Raw, build

_LOGGER = logging.getLogger(__name__)

_MODELS = {
    ROOM: "Room",
    WALL: "Outside wall",
    ROOF: "Roof",
    WINDOW: "Window",
    INTERNAL_WALL: "Internal wall",
    REGISTER: "Heating register",
}


@dataclass
class HouseData:
    """What the platforms share: the sky and the parts of the house."""

    coordinator: SkyCoordinator
    elements: dict[str, Element]


def elements_of(entry) -> dict[str, Element]:
    """The parts of the house from the entry's sub-entries."""
    raws = [
        Raw(s.subentry_id, s.subentry_type, s.title, dict(s.data))
        for s in entry.subentries.values()
    ]
    elements, problems = build(dict(entry.data), raws)
    for problem in problems:
        _LOGGER.warning("Skipping %s", problem)
    return elements


def register_devices(hass, entry, elements: dict[str, Element]) -> None:
    """Make a device for each part and put it in the part's area.

    The part's settings choose its room; a device moved by hand goes back on
    the next reload.
    """
    devices = dr.async_get(hass)
    areas = ar.async_get(hass)
    for element in elements.values():
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=element.id,
            identifiers={(DOMAIN, element.id)},
            name=element.title,
            manufacturer="House Structure",
            model=_MODELS[element.kind],
        )
        if element.area_id and device.area_id != element.area_id:
            if areas.async_get_area(element.area_id) is None:
                _LOGGER.warning("%s: its area was deleted", element.title)
            else:
                devices.async_update_device(device.id, area_id=element.area_id)
