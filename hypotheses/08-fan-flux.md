# 08 Heat flux of running the furnace fan

**Status:** revised; the blower never stops for more than 12 minutes, so there is no fan-off baseline; needs a deliberate test

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

### Review (2026-11-02): the first look tested the wrong thing

The first look compared the master bedroom's warming during heating calls with the register fan on and off. During a heating call the zone board ignores fan-only requests, so that only tested the register fan, not the furnace blower moving heat between floors. The intended test is whole-house fan-only periods (blower on, no heat or cool call) against still periods (blower off): with the cold-air returns open in nearly every room, the fan should pull the basement up toward the rest of the house and, in summer, the master bedroom down toward it.

### Fan-only versus still (`scripts/fan_mixing.py`, 11 days from 2026-10-22, when the thermostat history starts)

- There are no still periods. Each Ecobee has a fan minimum on-time (z1, z3, z4: 15 min per hour; z2: 40 min per hour), and the zone board runs the blower for any of them. In 268 hours the blower was off for 40 hours in total, in 701 gaps with a median of 3 minutes and a maximum of 12. No 15-minute or even 5-minute bin without heating had the blower off.
- So the house is always fan-mixed, and there is no baseline to compare with. With the fan on (5-minute bins, no heating), each room's gap to the rest of the house closes at k = 0.15 to 1.2 per hour: fastest for the Z2 basement thermostat (1.2/h; it sits about 0.5 C below the house) and the office (0.8), slowest for the kitchen (0.15) and the S basement bedroom (0.05). The master bedroom stays 1.5 C below the rest despite the fan, closing at only 0.34/h. These rates include everything that closes the gap (walls, doors, air leaks), not only the fan.
- The blower's electrical draw at its short off-gaps (`scripts/blower_power.py`) shows no clear step (median +0.04 kW with 5-minute windows), so in fan-only mode it runs slowly.

**Next:** a deliberate test. For example, set all four thermostats' fan minimum on-time to 0 on alternate nights for two weeks (with a heat setpoint low enough that no zone calls), and rerun `fan_mixing.py`; the "still" column will then fill in. The same nights give 10 its no-fan data.
