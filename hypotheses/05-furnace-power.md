# 5 Furnace heating power from room temperature gradient

**Status:** untested

**Claim:** Observing the temperature rise in a room while the furnace runs lets us estimate the furnace's effective heating power.

**Data:** Room temperature sensors, furnace/zone call states, outdoor temperature, electricity use.

**Our entities:** four zones (`z1` kitchen, `z2` basement, `z3` master bedroom, `z4` office). The call state is the `hvac_action` attribute of `climate.z1`..`z4` (`heating`, `cooling`, `fan`, `idle`); the `binary_sensor.zN_furnace_heating` sensors never turned on in the history we could read, so don't rely on them. Whole-house power is `sensor.eagle_00bb9c_power_demand`. Run `scripts/hvac_overview.py` for run counts and durations.

**Method:**
- Select clean windows: overnight, no solar gain, one zone calling.
- Fit `C * dT/dt = P_furnace*duty - UA*(T_in - T_out) + coupling terms`.
- Estimate effective power per zone, including spillover into non-calling zones.

**Caveats:** Zone valve leakage; unknown thermal mass C (fit jointly, or from cooldown periods).

**Zone board.** A zone board sits upstream of the thermostats, so a zone's call is a request, not proof its own air is running:
- With one heat call and one AC call at the same time, the board alternates between heat and AC.
- With several heat calls (or several AC calls), all zones become active, not just the ones calling.
- Fan calls only take effect when there is no heat or AC call, and then all zones are active.
So the furnace is on whenever any zone calls for heat, and a zone's temperature can rise because of another zone's call. Analyse heating as the union of all zones' heat calls, and treat a zone that is not itself calling as a measure of leakage and spillover.

## Results

First look (9 days, late October 2026; `scripts/hvac_overview.py`): z4 (office) heated 3.2 h/day in about 11 runs (median 9 min, longest 84 min) on every day. z2 (basement) heated 0.8 h/day in 6 runs (median 6 min). z1 and z3 never called for heat. No cooling. Every zone also shows long fan-only periods (5-14 h/day), including runs of 6-12 h, which will matter for 07 (fan flux).

First response look (10 days, late October 2026; `scripts/hvac_response.py`, thermostat `current_temperature`, episodes of 20 minutes or more, 25-29 per zone). Episodes are the union of all zones' heat calls. Medians:

| Zone | Own call | Episodes | Rise per episode | Rate while running | Keeps rising after end | Time to peak |
|---|---|---|---|---|---|---|
| z4 office | yes | 25 | 1.1 C | 1.5 C/h | 0.1 C | 3 min |
| z2 basement | yes | 7 | 0.2 C | 0.3 C/h | 0.2 C | 12 min |
| z2 basement | no | 18 | 0.7 C | 0.7 C/h | 0.6 C | 14 min |
| z1 kitchen | no (never calls) | 25 | 2.0 C | 2.6 C/h | 0.1 C | 3 min |
| z3 master | no (never calls) | 25 | 0.1 C | 0.1 C/h | 0.1 C | 9 min |

Cautions: short episodes (the median is 9 minutes, about 16 a day) are within the thermostat's resolution (about 0.1 C), so only the 20-minute-plus episodes are usable. The kitchen warms by 2 C during long episodes although its thermostat never calls for heat. That is either air arriving through the zone board (several zones calling) or daytime solar gain through the south and west windows, and this data cannot separate them yet; it needs the solar term from 10. The rate is the room's rise per hour, not power in watts; converting needs the thermal mass.

Crossover bleed (`scripts/hvac_bleed.py`, 10 days). A heat call in one zone also warms the others through the leaky zoning valves, and the kitchen most of all. Looking only at episodes where z4 alone called for at least 15 minutes, and subtracting each room's drift over an equal quiet stretch just before, the median extra warming rate (C per hour) was:

| Time of day | Episodes | z4 (calling) | z1 kitchen | z2 basement | z3 master |
|---|---|---|---|---|---|
| Night (sun below -6 degrees) | 20 | +1.66 | +3.06 | +0.55 | +0.33 |
| Day (sun above 5 degrees) | 6 | +1.66 | +3.08 | +0.86 | +0.07 |

At night, with no sun, the kitchen warms about twice as fast as the zone that is calling, and at the same rate as in the day. So the kitchen's rise is bleed from z4's call, and solar gain is not needed to explain it. This is the crossover flux between zones, and it can be measured per pair of zones. Only z4-alone episodes are well covered; z2-alone has a single episode, so the other direction is still open.

