# 15 Occupancy from room temperature changes

**Status:** three test runs; the office signal is the computer's power, not body heat

**Claim:** Occupancy (people home, or in a given room) can be inferred from room temperature changes, because each person adds roughly 100 W of heat.

**Expectation:** A weak signal compared with solar gain, furnace and appliances. Likely works best at night (bedrooms, no sun, fewer other loads) and as a residual after the model from B and C is fitted.

**Data:** Model residuals per room; ground truth from presence detection (phone trackers, motion sensors, bed sensors) if available.

**Method:**
- After fitting the thermal model, look for a positive unexplained heat input that correlates with known presence.
- Evaluate as a detector (precision/recall), and check whether it adds information beyond existing sensors.
- Optionally add humidity and CO2 as stronger occupancy signals.

**Depends on:** 04, 05, 06, 10, 11, 12, 13 (thermal momentum), 14 (electrical heat).

## Results

First run (`scripts/occupancy.py --days 14`, 15 minute bins, quiet night bins only: 560 of 1344).

Ground truth available in Home Assistant: `binary_sensor.kitchen_occupancy`, `z2_occupancy`, `master_bedroom_occupancy`, `office_occupancy`; the office motion sensor `multisensor_6_motion_detection`; the office CO2 sensor; two phone `person` entities. Occupied share of bins: kitchen 48%, z2 38%, master bedroom 74%, office 35%; motion in 25%.

Fit `dT/dt = a * (outdoor - room) + c + b * occupied` per room:

- Extra warming when the zone is occupied, `b`: +0.01 to +0.11 C/h, positive for 10 of 12 rooms but only two beyond two standard errors (Z4 office +0.08, S basement +0.07), and the standard errors are understated because bins are not independent. One person adds about 0.1 kW; with about 1.7 kWh/C per zone that is up to about 0.06 C/h, so values near +0.05 are the right size but not distinguishable from zero.
- As a detector, the cooling residual separates occupied from empty bins only weakly: AUC 0.47 to 0.62 (office 0.60, S basement 0.59, office air-quality sensor 0.62; kitchen and basement thermostat about 0.5).
- Master bedroom, N bedroom and the upstairs bathroom cannot be tested: the master bedroom sensor reads occupied in 98% of the quiet night bins, which leaves no empty bins to compare.
- Office CO2 does not follow the occupancy sensor: median 1121 ppm when occupied and 1562 ppm when empty (AUC 0.40), and the rate of rise is the same (AUC 0.50). The CO2 sensor may sit somewhere else, or the occupancy sensor may be measuring something other than presence.
- Conclusion: night-time temperature changes give at most a weak hint of occupancy. Better routes are the daytime (needs the sun and furnace terms from 11 and 05), the door contact (09, open doors coincide with a warmer room), and checking what the occupancy sensors really measure.


### Second run: corrected ground truth, day and night, event study (`scripts/occupancy.py --days 14`)

Ground truth corrected: the master bedroom occupancy sensor is always on because of the spinning register fan, so z3 (master, N bedroom, upstairs bathroom) is out until it has another sensor. For the office there are three candidate signals; I used `binary_sensor.office_occupancy` (Z4). Compared with the Williams Office motion sensor, the occupancy sensor is on 35% of bins against 25% for motion, and motion fires only inside occupied periods (motion-only 1% of bins), so occupancy is the motion signal with a hold time. Office computer power is above 60 W in 75% of bins (it is mostly left on), so it is a weak truth: 99.6% when occupied, 62% when not. Occupancy also tracks the office-air-quality CO2 sensor (`sensor.office_office_air_quality_co2`: occupied 1120 ppm, empty 948, AUC 0.74), while `sensor.z4_office_carbon_dioxide` (the thermostat's) runs the wrong way (AUC 0.40, higher when empty) and is not used. The CO2 rise rate carries no signal (AUC 0.50).

Extra warming `b` in C/h (own zone not calling for heat; * = beyond two standard errors):

| Room | night | all day (sun term added) | event study (after minus before onset or departure) |
|---|---|---|---|
| Z4 office | +0.08* | +0.10* | +0.01 (25 events) |
| Office AQ | +0.07 | +0.10* | -0.05 |
| Office sensor | +0.01 | +0.07* | -0.01 |
| S basement | +0.07* | +0.03 | +0.13* (52 events) |
| NE / SE basement | +0.05 | +0.04 / +0.02 | +0.08 / +0.10 |
| Z2 basement | -0.03 | -0.01 | +0.15 |
| Kitchen | +0.02 | -0.17* | -0.06 |

- Office: a steady +0.08 to +0.10 C/h with the office occupied, day or night, close to what one person (about 100 W into about 1.7 kWh/C) would give, but the onset and departure events show nothing (+0.01 C/h, 25 events), so it may be a slow difference between occupied and empty periods (time of day, computer and lights) and not people.
- Basement rooms: events show +0.08 to +0.15 C/h, and the S basement bedroom is beyond two standard errors, but the all-day fit does not. The S basement bedroom is also the room with the door contact (09), where open (occupied) periods were warmer by 0.3 C.
- Kitchen: -0.17 C/h when occupied, the wrong sign. The kitchen is occupied at meals and in the evenings, when cooking, the dishwasher, doors and the range hood and the setback schedule change the heat balance, and the model has no term for them.
- As a detector it is still weak (night AUC 0.47 to 0.62).
- Conclusion: some sign of people warming small rooms (office, S basement), nothing reliable. The best next steps are the solar and furnace terms from 11 and 05 for daytime, the door contact (09) as a second label for the S basement bedroom, and a longer record (the recorder is already at 60 days).

Correction: the office sensor and the office air-quality sensor are one room. They are now averaged into one "Office (sensor+AQ)" row: night +0.06 C/h (not significant), all day +0.09 C/h*, events -0.03 C/h, AUC 0.61. The earlier table counted this room twice.

### Third run: appliance power as its own term (`scripts/occupancy.py --days 14`, to 2026-11-02)

The all-day fit now also includes each zone's metered plugs (z4: the office computer; z1: the fridge and kitchen computers), because 14 found the office computer's power acting like an occupancy signal.

| Room | b all day | b with plugs | plug term (C/h per kW) |
|---|---|---|---|
| Office (sensor+AQ) | +0.083* | +0.020 | office PC +1.62* |
| Z4 office | +0.096* | +0.054 | office PC +1.09* |
| W bedroom | +0.051 | +0.032 | office PC +0.50* |
| Kitchen | -0.183* | -0.160* | fridge +0.36, kitchen PCs -1.25 |

- The office "occupancy" warming mostly goes away (+0.08 to +0.02, not significant) once the computer's power is in. The computer's power carries the signal better than the occupancy sensor; the two are the same sessions.
- The basement rooms (no plugs) are unchanged: night +0.05 to +0.07, event study +0.08 to +0.12 (S basement +0.12*).
- The office CO2 sensor still follows occupancy (AUC 0.75).
- Answer to "can we test it now": yes, and the result is the same as before. Body heat is too small to see in the room temperature. Presence is better read from computer power and CO2 than from temperature.

With the office lights added as a third term (modelled power, see 14), the occupancy term for the office sensors turns negative (-0.25 C/h*, Z4 thermostat -0.13*) while lights (+3.6) and computer (+1.6) carry the warming. The three signals mark the same sessions and cannot be separated. Occupied hours with the lights off (daytime) are, if anything, cooler than the model expects.
