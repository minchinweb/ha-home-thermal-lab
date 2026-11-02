# 15 Occupancy from room temperature changes

**Status:** first test run; no temperature signal found yet

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
