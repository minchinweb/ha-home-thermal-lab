# 17 Use the forecast to decide whether to run furnace/AC

**Status:** shadow mode started (`scripts/shadow_control.py`); nothing actuated

**Claim:** A forecast lets us decide to run or skip the furnace/AC now to avoid later overshoot (e.g. skip heating in the morning if afternoon sun will warm the kitchen).

**Method:**
- Rule or model-predictive controller on top of 16, minimising comfort deviation from the wave target and energy use.
- First run in shadow mode: log what it would have done and compare with what the thermostat did.
- Only then let it actuate.

**Depends on:** 16, and the wave component as the target.

## Results

First shadow run (`scripts/shadow_control.py --days 14`, 15 minute bins from 2026-10-19; nothing was switched). For every heating call, a per-zone no-heat forecast (`dT/dt = a * (outdoor - room) + c + g * light`, fitted on that zone's idle bins; weather measured, standing in for a forecast; sunlight on the room's windows and roof as in 11 and 16) asks whether the room would have stayed within a band below the thermostat's setpoint for the next few hours without the furnace. If it would (with at most 0.5 degree-hours below the band), the call is marked skippable. The thermostat setpoint is the current target; the wave target of the component will replace it.

Check of the forecast itself (RMSE C at 1, 2, 3 hours after any idle moment, against holding the temperature): z3 0.18, 0.28, 0.36 (hold 0.22, 0.36, 0.49); z4 0.22, 0.31, 0.36 (hold 0.30, 0.52, 0.72); z1 0.70, 1.07, 1.30 (hold 0.71, 1.09, 1.33); z2 0.41, 0.59, 0.69 (hold 0.41, 0.59, 0.68). The model beats holding the temperature in z3 and z4 (the rooms with windows and roof), and adds nothing in z1 and z2. Zone 1 (kitchen) and zone 3 (master) thermostats are in the off mode and recorded no heating calls in this period, so only z2 (63 calls, 480 minutes) and z4 (130 calls, 2269 minutes) have a decision to make.

Share of calls the rule would skip, by band below the setpoint (look-ahead 3 h; 6 h in brackets); furnace minutes in the skipped calls out of 2749 (the energy is an upper bound, since zone calls overlap):

| Band | Calls skipped (of 193) | Minutes skipped | kWh skipped (of 638) |
|---|---|---|---|
| 0.25 C | 115 (64 of 191) | 1942 (1325) | 444 (298) |
| 0.5 C | 184 (86) | 2626 (1566) | 609 (355) |
| 1.0 C | 191 (159) | 2725 (2355) | 632 (543) |

- The result depends almost entirely on how much comfort loss is allowed. Thermostat calls begin at the setpoint (the room is a median 0.05 to 0.07 C below it when the call starts), so a forecast showing a fall of 0.2 to 0.7 C over the next 3 hours counts as "within band" for a 0.5 C band, and nearly every call is skippable. At 0.25 C, 64% of the calls (3 h) and 34% (6 h) are.
- The forecast error at 3 hours (0.36 C in z4 and 0.69 C in z2) is as large as the band, so decisions near the band's edge are not trustworthy. The z2 basement cools and heats quickly (most of its 63 calls last under 10 minutes) and the model is no better than holding the temperature there.
- This is a shadow estimate only. It cannot observe what would have happened without the call, and the thermostat's own calls are what keep the room near the setpoint in the first place, so the "saving" is an upper bound on the energy and a lower bound on the comfort cost.
- Next: log real forecasts and the rule's decision live in Home Assistant (a sensor that says "would skip"), compare with what the thermostat actually did over a week, add the wave target instead of the thermostat setpoint, and only then consider letting it act, starting with the z4 office (the zone where the forecast beats holding).



### Live shadow sensors (built, not yet deployed)

`custom_components/home_thermal_lab/sensor.py` is a Home Assistant sensor platform: one `skip`/`heat` sensor per zone, refreshed every 15 minutes and whenever the thermostat's `hvac_action` changes. It reads the zone's thermostat and room temperature, takes the outdoor temperature now and the Open-Meteo forecast (temperature, direct and diffuse light, cached for an hour) for the next 3 hours, works out the sunlight on the zone's windows and roof, and calls the same decision function as the offline script (`shadow.py`, tested). Its attributes keep the room, setpoint, lowest forecast, shortfall and what the thermostat was doing, so the recorder history is the shadow-mode log. `scripts/shadow_compare.py` reads that log back and compares it with the thermostat's heating calls (how many the rule would have skipped, the minutes involved, and how far the room actually fell below the setpoint within 3 hours with the heating that did run). Nothing is switched.

- The decision, forecast, light and simulation code have unit tests (73 passing). The sensor platform itself needs Home Assistant, which is not installed in this development environment, so it has only been syntax-checked and linted; the first thing to do after copying it over is to watch the log for errors.
- The model coefficients come from `scripts/shadow_control.py` (it prints a `model:` line per zone) and should be re-fit as the history grows; z4 and z3 are the only zones where the model beats holding the temperature.
- Next: run it for a week, then `shadow_compare.py`; swap the thermostat setpoint for the wave target; then consider acting on `skip` in one zone (z4 first), with a manual override.
- Fitted models (14 days, per hour): z4 `a 0.0106, c 0.0032, g 0.000229` (a cooling time of about 94 h, a sensible value); z2 `a 0.0027, c 0.0018, g 0`; z3 `a -0.0038, c -0.148, g 0.000336` and z1 `a -0.0189, c -0.50, g 0.0004`. The z1 and z3 cooling rates are negative, which is not physical (their thermostats are off and the room is driven by other things), so only z4 should be configured for now.
