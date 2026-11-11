# 08 Heat flux of running the furnace fan

**Status:** testing; no-fan nights 2-16 Nov 2026; the first night shows the fan keeps the basement warm and does little else

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

### No-fan nights set up (2026-11-02)

`homeassistant/no_fan_nights.yaml`, installed in Home Assistant as two automations ("No-fan night: start" and "No-fan night: end"): on even days of the year, 23:00 to 06:00 local, every thermostat's fan minimum on-time is set to 0 and the fan mode to auto; at 06:00 (or when Home Assistant starts during the day) they go back to 15 min/h (z2: 40). Heating is unchanged; a heat call still runs the blower and the analysis uses the time between calls. First night 2 November, last 16 November (8 nights, with 7 normal nights between them). `scripts/fan_mixing.py` finds these nights from the thermostats' `fan_min_on_time` attribute.

Owner's note: the blower probably does not stop when a zone goes from a fan-only call to a heating call. That fits the power data: the +0.2 kW "heat on" step in 14 was measured with the blower already running for the fan, so it is the extra draw of heating over fan-only, not the blower starting. It also means the 3-minute "off" gaps above may not be real stops (a furnace usually has a fan-off delay), which would explain why no step shows at them. The no-fan nights will give the first real off-to-on edges for the fan-only power.

### First no-fan night (2 to 3 November 2026, times in UTC-6)

The automations worked: all four thermostats went to a fan minimum of 0 at 23:00 and back at 06:00 (Z4 at 06:04). No zone called from 23:00 to 05:00, so the blower was off for 6 hours, the first fan-off stretch in the data. The night of 3 to 4 November (a normal fan night, as 3 November is an odd day of the year) also had no calls from 23:00 to 05:00, so it is the comparison. Floor means of 15-minute bins:

| 23:00 to 05:00 | No fan (2-3 Nov) | Fan on (3-4 Nov) |
|---|---|---|
| Outdoor | about 4.5 C | about 1.8 C |
| Basement (Z2, S, NE, SE) | 21.72 to 20.34 (-1.38) | 21.11 to 20.26 (-0.85) |
| Main floor (kitchen, Z4, W bedroom, office) | 21.82 to 20.43 (-1.39) | 21.95 to 20.56 (-1.39) |
| Upstairs (master, N bedroom, bath) | 20.39 to 19.81 (-0.58) | 20.99 to 20.37 (-0.62) |
| Spread of all rooms (std) | 0.86 to 0.65 | 0.81 to 0.63 |

- **The blower keeps the basement warm.** Without it the basement cooled about 60% faster, on a night about 3 C milder outside. The S and SE basement bedrooms fell 1.9 and 2.0 C from 23:00 to 06:00, against 1.3 and 0.8 C with the fan. With the fan on, the returns take main-floor air and the basement supplies push it down, so the fan minimum on-time works as a small basement heater fed by the main floor.
- **Otherwise the fan does little at night.** The main floor and upstairs cooled the same with or without it, and the spread between rooms closed the same way. In the heating season the fan does not help the master bedroom.
- **The fan-only blower is cheap.** `scripts/blower_power.py --days 3 --edge 5` found 18 clean fan switch-ons (the first real off-to-on edges) with a median step of -0.02 kW (quartiles -0.06 to +0.03), within the whole-house meter's noise: probably under about 50 W. The 7 "fan off" edges at +0.20 kW are most likely the fan flag dropping as a heat call starts (the +0.2 kW heat step in 14), not the blower.
- **Do not read `fan_mixing.py`'s k table yet.** With 4 days (`--days 4 --bin 5`), "still" has a larger k than "fan only" for most rooms (Z2 basement 2.75 against 1.05/h). All 78 still bins come from this one night, which began just after a Z3 + Z4 heat call (22:00 to 22:20), so the fit mostly measures the house settling after that call. It needs more nights.
- Caveats: one night. The basement started warmer than on 3 to 4 November (21.7 against 21.1 C) and so had more to lose. The upstairs bathroom rose 0.4 C overnight (probably a shower).
- Watch for: a colder basement on no-fan nights may make Z2 call overnight, which runs the blower and shortens the still stretch.

### No-fan nights seen from the basement bedrooms (2026-11-10; nights of 2, 4, 6 and 8 November)

The automations only started on 2 November, so 2, 4, 6 and 8 November are the real no-fan nights (labels from earlier even-day guesses for 29 and 31 October were wrong).

- The Z2 thermostat (in the Theater) warms about 0.5 C/h from 23:00, when the blower stops: +0.8 to +1.0 C by 00:00 on all four nights, and +0.3 to +0.8 C over 22:00 to 05:00, against -0.6 to -1.2 C on fan nights. NE, SE and Dan's rooms do not change at 23:00. So the Theater reading rises when the fan stops without the other basement rooms following; whether the room itself warms is open.
- Bedroom humidity climbs steadily on the no-fan nights (about +1 to +2 %/h in the first 3 hours, +4 to +9% overnight in NE and SE, less in Dan's) while the Theater reading falls; on fan nights it is flat.
- Result: the Theater is not a usable baseline on no-fan nights (see 15). It is a result for this hypothesis: the fan state changes the Theater thermostat reading and the bedroom humidity.
