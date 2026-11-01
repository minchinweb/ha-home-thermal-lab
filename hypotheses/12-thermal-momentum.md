# 12 Thermal momentum of the house

**Status:** untested

**Claim:** The house's thermal momentum (inertia) can be measured: how long a room keeps changing temperature after the heat source stops, or how slowly it follows the outdoor wave.

**Data:** Room temperatures, furnace/AC/fan call states, outdoor temperature, solar data.

**Method:**
- Overshoot after the furnace stops: the extra rise and how long it lasts.
- Cool-down: after heating ends at night, fit the decay toward outdoor temperature to get a time constant `tau = C / UA`.
- Lag: the delay and damping of each room's daily wave compared with the outdoor wave (the phase lag and amplitude ratio of the fits from 01/02).
- Compare rooms and floors; a larger `tau` means more momentum.

**Feeds:** 15 (prediction) and 16 (control): the overshoot to avoid is this momentum. Shares parameters with 04, 05, 09 and 11.

## Results

_none yet_
