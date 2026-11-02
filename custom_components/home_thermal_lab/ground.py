"""Ground temperature at basement depth, as a damped and lagged annual wave.

Hypothesis 03: below about 1.5 m the soil follows the air's annual wave with a
smaller swing and a lag of months (Kusuda-Achenbach). Standard library only.
"""

from __future__ import annotations

from datetime import datetime
import math

# Regina, from hypothesis 03 at 1.78 m: air mean 4.2 C + 1.5 C (snow cover), swing
# 0.37 of the air's 15.2 C, coldest 74 days after the coldest air (day 21).
DEFAULT_MEAN = 5.7
DEFAULT_SWING = 5.6
DEFAULT_COLDEST_DAY = 95.0


def ground_temperature(
    when: datetime,
    mean: float = DEFAULT_MEAN,
    swing: float = DEFAULT_SWING,
    coldest_day: float = DEFAULT_COLDEST_DAY,
) -> float:
    """Ground temperature (C) at a moment.

    Args:
        when: The moment (its local day of the year is used).
        mean: Annual mean ground temperature.
        swing: Half the difference between the warmest and coldest ground.
        coldest_day: Day of the year (1 to 365) the ground is coldest.
    """
    day = when.timetuple().tm_yday + (when.hour + when.minute / 60.0) / 24.0
    return mean - swing * math.cos(2 * math.pi * (day - coldest_day) / 365.25)
