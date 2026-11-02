# 09 Door open/closed from inter-room gradients

**Status:** first test run; the proposed features do not identify the door

**Claim:** The temperature difference between two connected rooms, and how fast it decays, indicates whether the door between them is open or closed.

**Data:** Paired room temperatures; ground truth from door contact sensors if any, otherwise manual logging for a labelled set.

**Method:**
- Classification problem. Features: gradient, decay rate of the gradient, rate-of-change correlation.
- Needs labelled examples; collect by logging door state for a few weeks.

**Feeds:** 10 (coupling depends on door state).

## Results

Ground truth exists: `binary_sensor.s_basement_bedroom_door` (100 open runs since 2026-10-22, 37 of 10+ minutes, 126 hours open in total). The front door contacts only open for seconds, and the S basement bedroom's closet door never opened. The `home_performance_*_window_open` sensors are computed estimates, not contacts.

First test (`scripts/door_state.py`, 14 days to 2026-11-01, 15-minute bins; 504 open bins, 449 closed): the S basement bedroom against the zone 2 thermostat, NE basement and SE basement.

- The hypothesis predicted a smaller gradient when the door is open. The opposite appears: S basement versus Z2 is 1.15 C apart open and 0.81 C closed (AUC 0.82 for 'open is larger'). the S basement bedroom is warmer than Z2 by that much with the door open.
- Confound: the door is open almost only 07:00 to 21:00 and shut overnight, so the daily cycle (sun, heating) is mixed in. Matched by hour of day, open is still +0.28 C warmer (median over 10 hours with enough bins of each kind). Part of the gap is real and likely means someone is in the room (heat from a person, computer or lights), so this points to 15 (occupancy) rather than a door-coupling signal.
- Quiet night bins (sun down, no heating) have only 83 open bins. Gradient AUC drops to 0.75 against Z2 and 0.48 and 0.45 against the NE and SE bedrooms; the rate mismatch feature is about 0.5 to 0.6 everywhere. Neither feature classifies the door.
- Gradient change across 90+ minute open stretches: +0.06 C (13 stretches) versus -0.16 C across closed ones against Z2, in line with the room being warmer when open rather than the rooms equalising.

Reading: this pair does not show the expected coupling. Next steps: use 5-minute bins with the door-open event times (open or close edges) to look for step changes in the rate of change; try a pair with more air flow, such as the upstairs hallway rooms if they get contact sensors; and treat the 'open means occupied' link as an input for 15.
