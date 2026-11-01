# 9 Static heat flux between floors/rooms

**Status:** untested

**Claim:** When the furnace/AC and fans are off, the temperature gradient between rooms/floors gives a stable heat-flux coefficient (conductance) per pair.

**Data:** Multi-room temperatures during idle periods, outdoor temperature, door state (08).

**Method:** Fit the coupling terms `k_ij * (T_i - T_j)` in the RC model during idle windows. Expect stack effect (heat rising to upper floors) to make coupling asymmetric.

**Related:** the crossover bleed measured during a call (see 05) is the powered counterpart of this idle-state flux; the zoning valves leak both ways.

## Results

_none yet_
