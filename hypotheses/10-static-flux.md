# 10 Static heat flux between floors/rooms

**Status:** testing; 8 no-fan nights (2-16 Nov 2026, ended): the basement-to-main coupling is mostly the fan (z2's supply); upstairs and the main floor cool the same with or without it; 618 still 5-minute bins are ready for the pairwise fit

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

The no-fan nights are now running (see 08, from 2 November 2026). Rerun `scripts/room_network.py` on those nights' still bins once a few have passed.

### First static data (no-fan night, 2 to 3 November 2026)

Six hours with the blower off and no calls (23:00 to 05:00 UTC-6; details in 08). Against the next night (fan on, no calls, outdoor about 3 C colder), the basement cooled 1.38 C instead of 0.85, while the main floor (-1.39 both nights) and upstairs (-0.58 and -0.62) did not change. So with the fan off the basement is held up much less by the floor above, and the fan-on coupling between the basement and the main floor is mostly the blower. The upstairs coupling is the same with or without the fan, so it is static (conduction and the stairwell). The room spread closed from 0.86 to 0.65 C in both cases. One night is too few for `room_network.py`; rerun it on the still bins once three or four nights have passed.

### All eight no-fan nights (2026-11-17)

The no-fan nights ended on 16 November (details and the table in 08). Over 8 nights each way, 23:00 to 05:00 local:

- The basement bedrooms cooled 1.27 C without the fan and 0.97 C with it (-11 against -8 per hour per K x1000). The main floor (-1.53 against -1.58) and upstairs (-0.80 against -0.78) were the same. This confirms the first night: the basement's link to the main floor is mostly the blower, and the upstairs and main-floor links are static (conduction, the stairwell, open doors).
- The blower link is z2's supply, not the fan as a whole. The zone board sends supply air only to the zones calling for the fan (corrected in 05), and on fan nights z2 called 63 to 71% of the night against about 25% for each other zone.
- There are now 618 still 5-minute bins with no heating (all on these nights), where before there were none. `scripts/room_network.py` does not yet select them; the pairwise static fit, and the stack-effect asymmetry, are the next step. Caution from 08: many still bins start just after a heat call, so leave out the first hour after a call.
- The Z2 thermostat (Theater) reads higher when the blower stops, so leave it out of the static fit or treat it as a sensor that depends on the fan.
