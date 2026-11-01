# 12 Occupancy from room temperature changes

**Status:** untested

**Claim:** Occupancy (people home, or in a given room) can be inferred from room temperature changes, because each person adds roughly 100 W of heat.

**Expectation:** A weak signal compared with solar gain, furnace and appliances. Likely works best at night (bedrooms, no sun, fewer other loads) and as a residual after the model from B and C is fitted.

**Data:** Model residuals per room; ground truth from presence detection (phone trackers, motion sensors, bed sensors) if available.

**Method:**
- After fitting the thermal model, look for a positive unexplained heat input that correlates with known presence.
- Evaluate as a detector (precision/recall), and check whether it adds information beyond existing sensors.
- Optionally add humidity and CO2 as stronger occupancy signals.

**Depends on:** 03, 07, 08, 09, 10 (thermal momentum), 11 (electrical heat).

## Results

_none yet_
