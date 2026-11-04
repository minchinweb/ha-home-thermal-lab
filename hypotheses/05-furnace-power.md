# 05 Furnace heating power from room temperature gradient

**Status:** in progress; call lengths, stages and rise measured; live call statistics sensor

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

**From the literature review (4 November 2026; see `docs/literature-review.md`, Summary):**
- Fit the passive decay and the heated rise on separate windows, split at the call edges. A fit that spans the end of a call mixes the heating ramp into the decay rate (Climate Advisor, `compute_k_passive`).
- Cross-check each call with the heat balance Versatile Thermostat uses: heating rate = observed rise rate + decay rate at that indoor-outdoor difference. This is the same balance as the fit above, solved per call, so the two should agree.
- Gate the calls before pooling them: drop calls where the setpoint changed mid-call, remove outliers (IQR) before taking a percentile or mean of per-call rates, and cap the weight of old calls (Versatile Thermostat caps the count at 50).
- A single on/off heating rate misfits a two-stage furnace (Climate Advisor's `Q` is bang-bang). Keep a rate per stage.
- If this is reported as energy, CV(RMSE) and NMBE (ASHRAE Guideline 14) apply; for temperatures, use °C.

## Results

First look (9 days, late October 2026; `scripts/hvac_overview.py`): z4 (office) heated 3.2 h/day in about 11 runs (median 9 min, longest 84 min) on every day. z2 (basement) heated 0.8 h/day in 6 runs (median 6 min). z1 and z3 never called for heat. No cooling. Every zone also shows long fan-only periods (5-14 h/day), including runs of 6-12 h, which will matter for 08 (fan flux).

First response look (10 days, late October 2026; `scripts/hvac_response.py`, thermostat `current_temperature`, episodes of 20 minutes or more, 25-29 per zone). Episodes are the union of all zones' heat calls. Medians:

| Zone | Own call | Episodes | Rise per episode | Rate while running | Keeps rising after end | Time to peak |
|---|---|---|---|---|---|---|
| z4 office | yes | 25 | 1.1 C | 1.5 C/h | 0.1 C | 3 min |
| z2 basement | yes | 7 | 0.2 C | 0.3 C/h | 0.2 C | 12 min |
| z2 basement | no | 18 | 0.7 C | 0.7 C/h | 0.6 C | 14 min |
| z1 kitchen | no (never calls) | 25 | 2.0 C | 2.6 C/h | 0.1 C | 3 min |
| z3 master | no (never calls) | 25 | 0.1 C | 0.1 C/h | 0.1 C | 9 min |

Cautions: short episodes (the median is 9 minutes, about 16 a day) are within the thermostat's resolution (about 0.1 C), so only the 20-minute-plus episodes are usable. The kitchen warms by 2 C during long episodes although its thermostat never calls for heat. That is either air arriving through the zone board (several zones calling) or daytime solar gain through the south and west windows, and this data cannot separate them yet; it needs the solar term from 11. The rate is the room's rise per hour, not power in watts; converting needs the thermal mass.

Crossover bleed into the other zones during a call is its own hypothesis, 06.

### Heating stage from the Ecobees (`scripts/furnace_stages.py`, 10 days to 2026-11-01)

The Ecobee climate entities report `equipment_running` (`auxHeat1,fan` = W1, low stage; `auxHeat2,fan` = W2, high stage). Furnace: 80,000 BTU/h rated, roughly half at low stage (user's figures). Each zone is about 600 sq ft.

- Only z2 and z4 called for heat in this period. z2: 474 min low, 6 min high. z4: 1841 min low, 293 min high.
- Whole-house episodes (3+ min): 142 low only (median 9 min), 2 high only, 16 that stepped up (median 66 min long). The step to high came after a median 47 min (range 21 to 63 min), so the thermostat escalates only after a long, unsatisfied call; short calls stay on low, as expected.
- Whole-house power is the same in both stages (about 1.3 kW), so the blower does not change speed; the stage cannot be seen in electricity, only in the Ecobee state.

### Relative size of the two stages (`scripts/furnace_stage_ratio.py`, 10 days to 2026-11-01)

Only z4 has enough high-stage calls (z2 has one). Warming rate of the z4 rooms above their drift in the 30 minutes before the call began, in calls that stepped up (low stretch, then high) and in low-only calls:

- Low stage: +1.5 C/h (98 low-only calls), +2.2 C/h (16 calls before stepping up).
- High stage: +2.5 C/h (15 calls).
- High / low about 1.55 skipping the first 3 minutes of each stretch, and about 1.30 skipping 8. Read as low being roughly 65 to 77% of high, not 50%.
- Caveats: the ratio is biased toward 1 (a warmer room loses more heat, high calls come late in long calls, some heat leaks to other zones, the sensors step in 0.1 C). So the low stage is probably no larger than 77% of high, and a typical two-stage furnace (about 65%) fits better than a half. Check the nameplate.

### Call statistics and response (`scripts/furnace_lag.py`, 11 days to 2026-11-02; same code as the new `call_stats` sensor)

| Zone | Calls | Low only (min / median / max) | Stepped up (min / median / max) | Rise low / stepped |
|---|---|---|---|---|
| z2 | 63 | 62 calls: 3 / 6 / 15 min | 1 call: 6 min | +0.3 / +0.5 C |
| z4 | 132 | 114 calls: 3 / 9 / 36 min | 18 calls: 27 / 66 / 90 min | +0.1 / +1.7 C |

Lag, overshoot, dip and rebound are in 13. The `call_stats` sensor reports the same figures live (state: calls in the last `days`; attributes split by stage).

### First Z3 calls (2 and 3 November 2026, times in UTC-6)

After the owner changed the schedule, Z3 (master bedroom) called for the first time in the history: 22:10 to 22:28 on 2 November (18 min, setpoint 20.1) and 06:00 to 06:58 on 3 November (58 min; the thermostat started early for the 21.0 at 06:31). Both overlapped Z4 calls (to 22:13 and 06:46), so neither is a clean Z3-alone episode. Over the morning call:

| Room | Change |
|---|---|
| Master (the Z3 thermostat) | +0.7 C during the call, +1.2 C including the rise after it |
| N bedroom | +3.1 C, to 22.1 (1.1 C over the setpoint) |
| Upstairs bathroom | +2.4 C |
| Kitchen (with Z4 to 06:46) | +3.0 C |

- The room with the thermostat is the slowest of its zone, so a Z3 call runs until the master is warm and the N bedroom and bathroom overshoot. This fits the airflow (06): the master gets 4.5 air changes per hour on its own call, the fewest in the house, and its supply run is much longer than the straight runs up to the N bedroom and bathroom (owner). Both bedrooms have return grilles.
- Once warm air arrived the master rose at about 2 C/h (19.6 at 06:18 to 20.9 at 06:57). It lost about 0.3 C/h afterwards, against 0.9 for the N bedroom; the master's door is usually closed.
- The 18-minute call gave the master only about 0.5 C: most of it went on pushing the cold air out of the long duct (13). For Z3, fewer and longer calls are better value.
- The thermostat ended the call at 20.9 for a 21.0 setpoint, and the room rose to 21.4 after it.
- The dip at the start and the rise after the end are in 13.
