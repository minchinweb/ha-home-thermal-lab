# 08 Heat flux of running the furnace fan

**Status:** untested

**Claim:** Temperature gradients across several rooms while the fan runs (without heating/cooling) reveal the heat flux the fan moves between rooms.

**Data:** Multi-room temperatures, fan state per zone, furnace/AC call state.

**Method:**
- Isolate fan-only periods.
- Measure how quickly inter-room differences collapse versus the no-fan baseline (10).
- Estimate per-zone fan flux coefficients.

**Caveats:** Fan-only periods may be rare; may need to schedule deliberate experiments.

**Zone board:** fan-only calls only take effect when no zone calls for heat or AC, and then all zones are active, so fan periods are whole-house, not per zone. See the zone-board note in 05.

**The register fan:** `fan.master_bedroom_ad3958` produces no heat. It is tied to the master bedroom thermostat (z3) and is there to increase airflow into the master bedroom, which sits at the end of a very long supply run. It is mostly for cooling, so the heating-season data below is a weak test. The comparison room is the N bedroom, which has no register fan.

## Results

First look (10 days, late October 2026): the fan was on about 15 hours a day in long blocks (10-39 hours, often starting at 03:00 or 15:00), so there is little off-time to compare with. During whole-house heating episodes of 15 minutes or more (43, with the fan on for 28), the master bedroom warmed by about +0.2 C/h more than its prior drift with the fan on and +0.3 C/h with it off (thermostat), and the N bedroom by +0.1 C/h either way. No benefit of the fan is visible yet, but the master bedroom barely warms in either case, and the cooling season is the better test. Needs a deliberate on/off experiment.
