"""The target wave: where a zone should be at each hour of the day.

Standard library only. The project's aim is a room temperature that follows a
daily wave rather than a flat setpoint (hypotheses 01 and 02 measure the
outdoor wave it is modelled on: roughly a 24 h sinusoid peaking 1 to 3 hours
after solar noon)::

    centre(hour) = mean + swing * cos(2 pi (hour - peak_hour) / 24)

with a comfort band of ``band`` either side. Without a configured mean the
target is the thermostat's own setpoint, flat, with the band below it (the
shadow controller's tolerance), so the charts still show something to aim at.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class TargetWave:
    """A zone's target wave.

    Attributes:
        mean: Daily mean, C.
        swing: Half the daily range, C.
        peak_hour: Local clock hour of the warmest target.
        band: Comfort band either side of the centre, C.
    """

    mean: float
    swing: float = 0.0
    peak_hour: float = 15.0
    band: float = 0.5


@dataclass(frozen=True)
class Band:
    """The target at one moment."""

    lower: float
    centre: float
    upper: float


def target_at(wave: TargetWave, hour: float) -> Band:
    """The band at a local clock hour (fractions allowed)."""
    centre = wave.mean + wave.swing * math.cos(
        2 * math.pi * (hour - wave.peak_hour) / 24.0
    )
    return Band(centre - wave.band, centre, centre + wave.band)


def setpoint_band(setpoint: float, tolerance: float) -> Band:
    """The fallback target: the setpoint, with the tolerance below it."""
    return Band(setpoint - tolerance, setpoint, setpoint)
