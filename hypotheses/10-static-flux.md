# 10 Static heat flux between floors/rooms

**Status:** revised; no static (fan-off) periods in the data; fan-on network fit adds little

**Claim:** When the furnace/AC and fans are off, the temperature gradient between rooms/floors gives a stable heat-flux coefficient (conductance) per pair.

**Data:** Multi-room temperatures during idle periods, outdoor temperature, door state (09).

**Method:** Fit the coupling terms `k_ij * (T_i - T_j)` in the RC model during idle windows. Expect stack effect (heat rising to upper floors) to make coupling asymmetric.

**Related:** the crossover bleed measured during a call (see 06) is the powered counterpart of this idle-state flux; the zoning valves leak both ways.

## Results

_none yet_

### First measurement (see 13)

Intercepts of the night cool-down fit (heat the room gains from elsewhere in the house, in C/h with the room at outdoor temperature): +0.06 to +0.25 C/h in every room, largest in the SE basement (+0.25) and basement (+0.20), smallest in the master (+0.07) and office (+0.06). Positive everywhere, as expected when the house is warmer than outdoors.

### Review (2026-11-02)

The hypothesis asks for the coupling when the furnace, AC and fans are off. 08 found that the blower is never off for more than 12 minutes (the Ecobees' fan minimum on-times), so the recorded data has no static periods at all; every "idle" bin is fan-mixed. Better tests:

1. A network fit on the idle (no heating) bins, per room, with a pull from each zone (below). It measures fan-on coupling, not static.
2. Deliberate no-fan nights (fan minimum on-time 0, no heating calls), shared with the 08 test. That is the only way to get the static coupling the hypothesis is about.
3. Asymmetry (stack effect) needs the static data and the thermal masses from 13.

### Network fit (`scripts/room_network.py`, 11 days to 2026-11-02, 15-minute idle night bins)

`dT_i/dt = a (outdoor - T_i) + sum_z k_iz (mean of zone z's other rooms - T_i) + c`, compared with the single-room law by leave-one-day-out cross-validation:

- The network barely predicts better: CV RMSE changes by -0.013 to +0.007 C/h across rooms (night), and by up to -0.014 (all day, with a sun term). The zone terms are mostly small and some are non-physical (the office sensor -0.74/h toward its own zone).
- Consistent couplings: the master bedroom follows the rest of z3 (+0.57/h); the SE basement follows z2 (+0.37); most rooms are pulled toward z3 (upstairs), which may be the stack effect or simply that z3 never calls and so moves with the house.
- Conclusion: with the fan always on, the idle data cannot identify pairwise static coupling. The deliberate no-fan nights are the test.
