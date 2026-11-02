"""Modelled energy of the furnace from the thermostats' state (05, 08, 14).

The furnace has no meter of its own. Its state comes from the zone thermostats
(the zone board runs it for every zone): heating on W2 if any zone is on
``auxHeat2``, on W1 if any zone is heating, cooling if any is cooling, the fan
if any reports ``fan`` running, else off. Each state has a power in kW, and the
meter adds ``power * time`` as the state changes.

Measured for this house (``scripts/blower_power.py``, whole-house power edges):
the fan-only blower at most about 0.04 kW (no clear step), and heating adds
about 0.2 kW (both stages alike). Gas input is 80,000 BTU/h (23.4 kW) on high
and about 65% of that on low (unconfirmed; see 05).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

MODES = ("off", "fan", "heat_low", "heat_high", "cool")


def furnace_mode(zones: list[dict]) -> str:
    """The equipment state from every zone thermostat's attributes."""
    equipment = set()
    actions = set()
    for attrs in zones:
        equipment.update((attrs.get("equipment_running") or "").split(","))
        actions.add(attrs.get("hvac_action"))
    if "auxHeat2" in equipment:
        return "heat_high"
    if "heating" in actions or "auxHeat1" in equipment:
        return "heat_low"
    if "cooling" in actions or "compCool1" in equipment:
        return "cool"
    if "fan" in equipment or "fan" in actions:
        return "fan"
    return "off"


@dataclass
class Meter:
    """Integrates power by state into kWh."""

    kw: dict[str, float]
    total: float = 0.0
    mode: str = "off"
    since: datetime | None = None
    seen: dict[str, float] = field(default_factory=dict)

    def advance(self, now: datetime, mode: str | None = None) -> float:
        """Add the energy since the last call; then switch to ``mode``."""
        if self.since is not None and now > self.since:
            hours = (now - self.since).total_seconds() / 3600.0
            added = self.kw.get(self.mode, 0.0) * hours
            self.total += added
            self.seen[self.mode] = self.seen.get(self.mode, 0.0) + hours
        self.since = now
        if mode is not None:
            self.mode = mode
        return self.total
