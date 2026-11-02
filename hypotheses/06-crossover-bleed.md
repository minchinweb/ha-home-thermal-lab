# 06 Crossover bleed between zones during a call

**Status:** in progress

**Claim:** A call for heat (or cooling) in one zone also moves heat into the other zones, including zones that are not calling, because the zoning valves leak. This crossover flux can be measured for each pair of zones, and it is strongest into the kitchen because of how the zoning valves are set up.

**Data:** Whole-house heating episodes from the zone calls (see the zone-board note in 05), each room's temperature, sun height to separate day from night.

**Method:**
- Take episodes where a single zone called, so the source is known.
- For each other zone, take its warming rate during the episode minus its drift over an equal quiet stretch just before it.
- Compare night (sun below -6 degrees) with day, to rule out solar gain.
- Build a matrix of source zone against receiving zone. Repeat for cooling when the AC runs.
- Convert rates to watts later, using the thermal mass from 13.

**Feeds:** 05 (furnace power per zone, because bleed is part of what each zone gets), 10 (static flux), 16 (prediction) and 17 (control).

## Results

First look (`scripts/hvac_bleed.py`, 10 days). A heat call in one zone also warms the others through the leaky zoning valves, and the kitchen most of all. Looking only at episodes where z4 alone called for at least 15 minutes, and subtracting each room's drift over an equal quiet stretch just before, the median extra warming rate (C per hour) was:

| Time of day | Episodes | z4 (calling) | z1 kitchen | z2 basement | z3 master |
|---|---|---|---|---|---|
| Night (sun below -6 degrees) | 20 | +1.66 | +3.06 | +0.55 | +0.33 |
| Day (sun above 5 degrees) | 6 | +1.66 | +3.08 | +0.86 | +0.07 |

At night, with no sun, the kitchen warms about twice as fast as the zone that is calling, and at the same rate as in the day. So the kitchen's rise is bleed from z4's call, and solar gain is not needed to explain it. This is the crossover flux between zones, and it can be measured per pair of zones. Only z4-alone episodes are well covered; z2-alone has a single episode, so the other direction is still open.

Regression view (same run): each room's response to a z2 call and a z4 call, in C per hour per unit of the call, with the rest held fixed. z1 and z3 never called, so they have no coefficient. Strongest responses: kitchen 1.7 (z2) and 2.1 (z4), basement bedrooms NE 1.8 and SE 1.4 (z2) with 0.7 and 1.0 (z4), the office sensor 1.1 and 1.6, the office air-quality sensor 1.6 and 2.3, Z2 basement 1.3 and 1.3. The master bedroom and the N bedroom barely respond to either (0.0-0.4), and the upstairs bathroom only a little (0.2 and 0.4), consistent with them being at the far end of the supply runs. Zone membership of the other rooms can be read off these coefficients: the NE and SE basement bedrooms respond most to z2, the office sensor and the office air-quality sensor to z4.
