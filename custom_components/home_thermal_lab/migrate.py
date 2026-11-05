"""Settings that moved to House Structure and Manual J, removed from old entries.

The split (``docs/split-spec.md``) moved the house's sizing out of the lab:

* the envelope defaults on the integration's settings went to Manual J;
* the furnace and air conditioner nameplates, and the furnace's room, on the
  energy sub-entry went to House Structure's Furnace and Air conditioner
  parts (the energy sensor keeps its per-state powers, ``kw``);
* the building sub-entry went to House Structure's Building part, and its
  setpoints to Manual J (minor version 2);
* the house's rotation, roofs and shading on the integration's settings, and
  each zone's and contribution's window faces, roofs, sunlit walls, shading
  and below-ground setting, are House Structure's: a zone is a room (area) in
  House Structure, and takes them from there (minor version 3).

The config entry's migration (``__init__.async_migrate_entry``) removes them.
Type them into House Structure and Manual J first: the lab's diagnostics from
before the upgrade keep a copy. Standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping

# the config entry's version once the moved settings are gone
MINOR_VERSION = 3
BUILDING = "building"  # the sub-entry type that went to House Structure
ENVELOPE_KEYS = ("infiltration_ach", "wall_r", "roof_r", "door_r", "basement_floor_r")
NAMEPLATE_KEYS = (
    "afue",
    "blower_curve",
    "blower",
    "ac_sensible_w",
    "ac_total_w",
    "cool_tons",
    "area_id",
)
# minor version 3: the house's sun settings, and a room's own
HOUSE_SUN_KEYS = ("rotation", "roofs", "shade_below")
ROOM_SUN_KEYS = (
    "windows",
    "sunlit_walls",
    "roofs",
    "rotation",
    "shade_below",
    "below_ground",
)


def without(data: Mapping, keys: tuple[str, ...]) -> dict:
    """``data`` without ``keys``."""
    return {k: v for k, v in data.items() if k not in keys}


def moved(data: Mapping, keys: tuple[str, ...]) -> list[str]:
    """Which of ``keys`` are in ``data``, in order."""
    return [k for k in keys if k in data]
