# 10 Static heat flux between floors/rooms

**Status:** untested

**Claim:** When the furnace/AC and fans are off, the temperature gradient between rooms/floors gives a stable heat-flux coefficient (conductance) per pair.

**Data:** Multi-room temperatures during idle periods, outdoor temperature, door state (09).

**Method:** Fit the coupling terms `k_ij * (T_i - T_j)` in the RC model during idle windows. Expect stack effect (heat rising to upper floors) to make coupling asymmetric.

**Related:** the crossover bleed measured during a call (see 06) is the powered counterpart of this idle-state flux; the zoning valves leak both ways.

## Results

_none yet_

### First measurement (see 13)

Intercepts of the night cool-down fit (heat the room gains from elsewhere in the house, in C/h with the room at outdoor temperature): +0.06 to +0.25 C/h in every room, largest in the SE basement (+0.25) and basement (+0.20), smallest in the master (+0.07) and office (+0.06). Positive everywhere, as expected when the house is warmer than outdoors.
