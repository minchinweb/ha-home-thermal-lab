# 09 Door open/closed from inter-room gradients

**Status:** two test runs (15 and 5 minute bins); too few clean door edges to decide

**Claim:** The temperature difference between two connected rooms, and how fast it decays, indicates whether the door between them is open or closed.

**Data:** Paired room temperatures; ground truth from door contact sensors if any, otherwise manual logging for a labelled set.

**Method:**
- Classification problem. Features: gradient, decay rate of the gradient, rate-of-change correlation.
- Needs labelled examples; collect by logging door state for a few weeks.

**Feeds:** 10 (coupling depends on door state).

**From the literature review (4 November 2026):**
- Versatile Thermostat detects open windows from the slope of a time-aware EMA (`alpha = 1 - 0.5^(dt / halflife)`, half-life 5 minutes), with guards: a physical bound on the slope, at least 4 points, and a reset after a 30-minute gap. That addresses the 5-minute rate feature being pure noise (one 0.1 C step is 1.2 C/h). The smoothed slope lags, so allow for it when timing edges.
- Climate Advisor uses contact sensors with a delay, not inference. Where a contact exists (the S basement bedroom), use it as an input, and keep inference for the doors without one.
- In ISO 13789 terms an open door changes the coupling between rooms (10), not the envelope; an open window or outside door adds to the ventilation part of the envelope (04).

## Results

Ground truth exists: `binary_sensor.s_basement_bedroom_door` (100 open runs since 2026-10-22, 37 of 10+ minutes, 126 hours open in total). The front door contacts only open for seconds, and the S basement bedroom's closet door never opened. The `home_performance_*_window_open` sensors are computed estimates, not contacts.

First test (`scripts/door_state.py`, 14 days to 2026-11-01, 15-minute bins; 504 open bins, 449 closed): the S basement bedroom against the zone 2 thermostat, NE basement and SE basement.

- The hypothesis predicted a smaller gradient when the door is open. The opposite appears: S basement versus Z2 is 1.15 C apart open and 0.81 C closed (AUC 0.82 for 'open is larger'). The S basement bedroom is warmer than Z2 by that much with the door open.
- Confound: the door is open almost only 07:00 to 21:00 and shut overnight, so the daily cycle (sun, heating) is mixed in. Matched by hour of day, open is still +0.28 C warmer (median over 10 hours with enough bins of each kind). Part of the gap is real and likely means someone is in the room (heat from a person, computer or lights), so this points to 15 (occupancy) rather than a door-coupling signal.
- Quiet night bins (sun down, no heating) have only 83 open bins. Gradient AUC drops to 0.75 against Z2 and 0.48 and 0.45 against the NE and SE bedrooms; the rate mismatch feature is about 0.5 to 0.6 everywhere. Neither feature classifies the door.
- Gradient change across 90+ minute open stretches: +0.06 C (13 stretches) versus -0.16 C across closed ones against Z2, in line with the room being warmer when open rather than the rooms equalising.

Reading: this pair does not show the expected coupling. Next steps: use 5-minute bins with the door-open event times (open or close edges) to look for step changes in the rate of change; try a pair with more air flow, such as the upstairs hallway rooms if they get contact sensors; and treat the 'open means occupied' link as an input for 15.

### 5-minute bins (`scripts/door_state.py --bin 5`, 11 days to 2026-11-02)

- Same picture as at 15 minutes: the S basement bedroom is warmer than Z2 with the door open (1.15 against 0.80 C, AUC 0.81). The rate mismatch becomes pure noise at 5 minutes (one 0.1 C step in 5 minutes is 1.2 C/h), AUC 0.45 to 0.58.
- New door-edge event study (`--edge`, rate of gap closing in the window before and after each edge, with at least 80% of the window in the old and new state): only 5 clean openings and 1 or 2 clean closings in 11 days, because the door flutters. After the door opens, the gap to the NE bedroom starts closing (-0.18 to +0.42 C/h, 4 of 5) but the gap to Z2 widens (-0.64 to -0.76). After the door closes, closing slows in every pair, as coupling would predict, but on one or two events.
- Reading: too few clean edges to decide. The door needs a longer record (the edge study can be rerun as data builds up), or a deliberate test (door shut for a night, open the next).
