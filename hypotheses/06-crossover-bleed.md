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

Extended matrix (`scripts/hvac_bleed_matrix.py`, 10 days, 70 episodes of 10 minutes or more: z4 alone 50, z2 and z4 together 14, z2 alone 6; z1 and z3 never called). Median extra warming, C per hour above prior drift, skipping episodes where a room's last reading was more than 15 minutes old:

| Room | z4 alone | z2 + z4 | z2 alone |
|---|---|---|---|
| Z1 kitchen | +2.8 (44) | +2.4 (13) | +2.1 (6) |
| Z2 basement | -0.2 (45) | +0.6 (13) | +2.0 (6) |
| Z3 master | +0.2 (40) | -0.2 (13) | 0.0 (5) |
| Z4 office | +1.2 (44) | +1.5 (13) | +0.6 (6) |
| Office sensor | +2.9 (26) | +2.1 (13) | +0.3 (5) |
| Office air-quality | +3.5 (45) | +3.1 (13) | +0.2 (6) |
| N bedroom | +0.2 (13) | +0.3 (3) | +0.3 (1) |
| Upstairs bathroom | +0.3 (17) | +0.5 (2) | -0.1 (1) |
| NE / SE basement | 0.0 / +0.1 | +5.7 / +3.8 | +11.4 / +10.6 |

Episode counts are in brackets. The kitchen is warmed about as much by z2 as by z4, so it is the common sink for bleed from both. The upstairs rooms (master, N bedroom, bathroom) get almost nothing from any combination. The NE and SE basement bedrooms read 3-5 times higher than the 30-minute regression suggests for a z2 call; The owner confirms that the basement bedrooms heat very quickly (the NE bedroom is about 2 feet from the furnace), so these large values are probably real and not a sensor artefact. Several rooms (W bedroom, S basement) have too few episodes with fresh readings to say anything.

### Airflow measurements (owner's balancing check, December 2025)

Air speed was measured at every supply register with one zone calling at a time, before the registers were rebalanced on 23 December 2025. Flow is speed times register area. The furnace moves about 1,575 cfm. The kitchen has a different kind of zone damper from the others, and it does not close as tightly. A bypass returns air to the supply side when the pressure is too high.

Flow into each room, in cfm, by the zone calling (rooms by the names used in this repo):

| Room (zone) | Z1 only | Z2 only | Z3 only | Z4 only | Z2 after rebalancing |
|---|---|---|---|---|---|
| Kitchen + dining, 5 registers (Z1) | 485 | 427 | 388 | 330 | 349 |
| NE basement (Z2) | 0 | 153 | 0 | 0 | 137 |
| SE basement (Z2) | 0 | 16 | 0 | 0 | 142 |
| S basement (Z2) | 4 | 82 | 4 | 0 | 127 |
| Basement family room (Z2) | 0 | 38 | 0 | 0 | 126 |
| Laundry (Z2) | 0 | 0 | 0 | 0 | 376 |
| Entranceway, front room, two offices, W bedroom, main bathroom (Z4) | 47 | 52 | 20 | 705 | |
| N bedroom, master, upstairs bathroom (Z3) | 33 | 24 | 474 | 14 | |
| Total measured | 565 | 797 | 887 | 1,049 | 1,257 |
| Lost to the bypass and leaks | 64% | 49% | 44% | 33% | 20% |

- The kitchen gets 68 to 88% of its own-call flow whichever zone calls. Every other room gets 0 to 5% of its flow when its zone is not calling. In practice the kitchen is unzoned, and its thermostat has little say over it. This is the mechanism behind the kitchen's bleed above.
- Before rebalancing, a z2 call sent more air to the kitchen (427 cfm) than to the whole basement (289). After it, z2 and z4 calls send the kitchen about the same (349 and 330). The fitted bleed now agrees: kitchen +1.9 C/h for a z2 call and +2.1 for z4 (`scripts/horizon_profile.py`, 15 days to 2 November 2026; see 11).
- Air changes per hour on a room's own call: NE and SE basement 17 to 20, which is why they heat so fast. The master bedroom gets only 4.5, the fewest in the house, and is the coolest room.
- Over a day the kitchen's air is replaced about as often as the Z4 rooms' air. On 2 November 2026 (Z4 calling 3.8 h, Z2 1.3 h) both came to about 36 room volumes. Z4's calls end when its thermostat reaches the setpoint, and the kitchen gets the same air with no thermostat of its own to stop it. The kitchen ends up about 3 C warmer than the Z4 thermostat and 1 C warmer than the other two sensors in the same office (lux and presence, air quality). The thermostat reads about 2 C below those two, so where it sits in the office matters, and which of the three is the room temperature is not known. The kitchen's last degree over the office is its own heat: the fridge, cooking and the sun on the patio door.
- A small zone calling alone loses the most air to the bypass and leaks (64% for Z1, 33% for Z4).

### 3 November 2026: a new schedule, and the kitchen too warm to keep shut (times in UTC-6)

The owner changed the heating schedule the day before, so more zones now call: Z3 has a call at about 06:00, Z4 a noon boost to 22.5 C (12:30 to 13:30, against 21.3 the day before), and Z2 ramps from 16 to 21.5 C in half-degree steps every 30 minutes through the morning. Z1 was set to heat (17.2 C overnight, 20 to 21.1 C by day), but never called: the kitchen was above its setpoint all day. In the afternoon the owner opened the sink window and the patio door to cool the kitchen. The data is from Home Assistant's history. The windows have no contact sensors, and Home Performance's "kitchen window open" sensor did not fire.

| Local time | Kitchen | What drove it |
|---|---|---|
| 05:45 to 07:00 | 20.8 to 23.8 C | Z4 and Z3 calls, about 1.25 h of furnace (+2.4 C/h). The kitchen gained more than either zone that called (office +1.7, master about +1). |
| 07:00 to 11:45 | 23.8 to 22.3 | No calls; slow drift down. |
| 11:45 to 12:45 | 22.8 to 25.4 | Z4 called for 60 min from 11:50 (the thermostat started early for the 22.5 at 12:32), short Z2 calls, and the sun on the patio door from about 12:15. |
| 12:45 to 14:00 | 25.4 to 24.3 | No calls. Full sun on the patio door, but the windows were open (below). |
| 13:30 to 15:15 | about 24.4 | Cooking (whole-house power 2 to 4.3 kW) and Z2 calls, against the open windows. |

- The noon rise of 2.6 C splits, with the fitted bleed (Z4 +2.1, Z2 +1.9 C/h per call) and the sun gain measured on 2 November (11), into about 1.6 C from Z4's call, 0.5 C from Z2's, and 0.3 C of sun (it had only just reached the patio door). About 80% of the overheating was bleed. The cooking came after the peak.
- The schedule did not add heating hours. The furnace ran 3.4 h (to 17:00), against 3.6 to 5.1 h a day from 26 October to 2 November. It moved them: Z4's noon boost put a full hour of furnace on the kitchen just as the patio door's sun began. The kitchen's peak was 25.6 C, in the range of the week before (23.7 to 25.7 C).
- The morning calls start the kitchen's day near 24 C. Z1's own setpoint has no say in this, as the airflow measurements predict.

#### When the windows were opened, and what they removed

The owner did not note the time, so it was found by comparing the kitchen's rate in 15-minute bins with the same clock times on 2 November. That day was as clear (beam within about 5%), with the same sun path, and the windows were shut. The expected rate today is yesterday's, plus the difference in bleed (rates above, Z3 taken as 2.0 C/h like the others), plus 0.4 C/h per kW of whole-house power above 1.1 kW (cooking), minus the cooling law at 0.03/h on the difference in indoor-outdoor gap. The extra loss is the measured rate less the expected one.

| 15 min to | Kitchen | Rate today | Rate on 2 Nov | Extra loss C/h | W/K |
|---|---|---|---|---|---|
| 12:30 | 24.83 | +3.3 | +0.9 | +1.9 | |
| 12:45 | 25.39 | +2.2 | -0.2 | +0.6 | |
| 13:00 | 25.33 | -0.2 | +2.2 | -2.2 | 305 |
| 13:15 | 25.17 | -0.7 | +1.8 | -1.7 | 248 |
| 13:30 | 24.78 | -1.6 | +0.2 | -2.4 | 363 |
| 13:45 | 24.56 | -0.9 | +0.4 | -1.9 | 295 |
| 14:00 | 24.33 | -0.9 | +1.1 | -2.2 | 348 |

- The windows were opened at about 12:45 to 12:50, just after the 25.4 C peak and as Z4's call ended. They stayed open for the rest of the day.
- In the cleanest stretches (13:00 to 14:00 and, in 30-minute bins, 15:00 to 16:00) they took about 2 C/h off the kitchen: roughly 300 W/K with the kitchen's effective 7.9 MJ/K (13), or about 4 kW with the kitchen 14 C above outdoors. That is about 900 m3/h of outdoor air, and about the size of the sun through the glass (about 2 kW) and the cooking (2 to 3 kW) together, so the kitchen held near 24.3 C through the cooking.
- From 14:15 to 15:00 the comparison is unreliable: on 2 November the sun was behind the spruce then, and today's cooking overlaps it. The cooking factor (0.3 to 0.5 C/h per kW) moves the clean bins by less than 0.3 C/h.
- With the windows still open after sunset (about 17:00), the kitchen at 24.1 C and outdoors 13.5 C, the expected loss is about 1.5 C/h, reaching Z1's 21.1 C setpoint at about 19:00.

#### What would help

- On sunny days, skip or shrink Z4's noon boost: the office faces east, gets no afternoon sun, and rose only 1.3 C for the hour. That would take about 1.5 to 2 C off the kitchen's peak.
- Z2's half-degree steps make short calls around 11:00 to 12:15 and 14:00 to 15:15, each one also heating the kitchen.
- While the kitchen gets 68 to 88% of its flow on every call, no schedule on the other zones avoids heating it. A balancing damper on the kitchen's supply runs is the physical fix.
