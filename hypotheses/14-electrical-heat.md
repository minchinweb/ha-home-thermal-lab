# 14 Electrical use becomes indoor heat

**Status:** untested

**Claim:** Apart from the AC (which moves heat outside), essentially all electricity used inside becomes heat inside the house.

**Data:** Whole-house power (HA energy), any per-circuit sensors, temperatures.

**Method:**
- Add measured electrical power as an input term in the RC model and fit its coefficient (expect about 1 for indoor loads).
- Treat the AC and the oven as unmetered terms: derive AC load from its call state, and expect the oven to appear as residual.

**Caveats:** Some load is outside the envelope (e.g. outdoor, garage); room allocation of heat is unknown.

## Results

Furnace blower and the stove (`scripts/power_check.py`, whole-house power at about 30-second resolution, 10 days from 23 October 2026).

- The furnace blower is visible. Across 122 whole-house heating episodes of 8 minutes or more, power rose a median 0.25 kW when heating started and fell 0.26 kW when it stopped, against -0.04 and +0.01 kW at 122 control times with no heating. So about 250 W of electrical draw goes with a furnace run, small beside the 1.1 kW base load.
- Larger events are far more obvious, as expected: 41 bursts lasting 10 minutes or more and at least 1 kW above the surrounding baseline, the biggest about 30-65 minutes at +2 to +2.5 kW on average (peaks of 3-4 kW), roughly ten times the blower step. They cluster around 12:00-15:00 and 17:00, with a few late evening. Without ground truth we cannot say which appliance each is (an oven or stove, a dryer, a dishwasher and the 3D printers are all candidates). The first regression found no electricity-to-room-heat effect (coefficients near zero), because 30-minute whole-house power is a poor proxy for heat landing in any one room.

Appliances and the stove proxy (`scripts/regress_power.py`, 15-minute bins, 10 days).

- Whole-house power regressed on the washer plug, the dryer status and the furnace: the washer plug comes out at 1.2 kW per kW (the plug is part of the whole house, as it should be), the furnace at +0.18 kW (agreeing with the 0.25 kW step above), and the dryer at only +0.31 kW while running, which is far below an electric dryer's several kilowatts. That fits a gas dryer, which the owner confirmed (it draws only a few hundred watts for the drum and controls); the dryer has no power sensor of its own (the entities named `dryer_plug_*` are actually the server's plug). The fit is poor (R2 = 0.11) because whole-house power is dominated by things we do not measure.
- After removing those, 15 unexplained bursts of 30-75 minutes at +1.2 to +2.3 kW remain in 10 days, starting around 12:00-15:00 (most), 17:00 and late evening. This is the stove proxy; it cannot be confirmed without a cooking log.
- Against room temperatures, the stove proxy has no detectable effect on the kitchen (+0.06 C/h per kW now, +0.08 the bin after; neither significant), nor on any other room. Either the bursts are not the stove, the range hood removes the heat, or 15 bursts is too few against the much larger furnace-bleed signal.

Live ground truth, 1 November 2026 (owner's account, power from the Eagle sensor at about 30-second readings). The electric kettle and the stove were started at about the same time, with the small front-right burner on high; the small rear-left burner was added at about 18:20.

- 18:08: power stepped from 1.1 to 2.3 kW (+1.2 kW) and stayed there for six minutes. That is the kettle, a typical 1.2-1.5 kW load.
- 18:14: it jumped to about 4.1 kW (kettle plus the burner at full power), then, as the kettle finished, fell to cycling between about 1.1 and 3.3 kW every 30-60 seconds: the burner on high is about +2.0 to +2.2 kW when on, switching on and off to hold its temperature.
- 18:21: back up to 3.9 kW as the second burner joined.
- The furnace was idle (only fan calls), so this is a clean test. Over the first 14 minutes of 2-3 kW extra electrical load the kitchen thermostat did not warm; it kept drifting down, 22.4 to 21.8 C since 17:58, in 0.06 C steps. Most of a stove's electrical power goes into the pot and its steam, and the range hood (if on) removes the rest, so the sensor may not see it quickly.

The burst signature (+1.2 to +2.3 kW, 30-75 minutes) in the history matches this, which supports reading those bursts as stove use, though the kettle alone is also a possibility for the shorter ones.

First reading of the cooking session (`scripts/event_response.py`, 18:14 to about 18:30, range hood off, front-right burner on high, rear-left added at about 18:20 and later turned down to 3): about 0.37 kWh above the 1.27 kW house level beforehand (2.71 kW during). The furnace was only calling for the fan. The kitchen thermostat was drifting down at -0.89 C/h in the half hour before and at -0.44 C/h during, so its cooling slowed by about +0.45 C/h, but it was still lower at the end (-0.11 C), and the change is about one 0.06 C reading step. Not a clear warming signal. Other rooms moved by similar small amounts in both directions, so none of this is distinguishable from noise yet.


### Cooking session, whole run (18:08 to 18:59 local, 2026-11-01; range hood off)

Note: Home Assistant's time zone is America/Regina (UTC-6 all year), which is what the scripts use as "local".

- Whole-house power: 1.08 kW before, 3.08 kW during; extra energy about 1.70 kWh over 51 minutes (kettle and burners together). Power fell from 3.9 to 2.1 kW at 18:59.
- Kitchen: net -0.11 C over the event (+0.11 C/h before, -0.13 during). No warming is visible.
- Other rooms: noisy and mixed. Master bedroom +0.5 C (fan-only calls, probably unrelated), the S basement bedroom -0.6 C, basement rooms cooling less than before.
- Scale check: with roughly 6 kWh/C for the whole house (13) and 1.5 kWh/C per zone, 1.7 kWh retained in the kitchen zone would give about +1 C; spread over the house about +0.3 C. Neither is seen, so most of the stove's heat is not showing up as warmer air at the sensors (heat in food and water, pans, vented moisture, fans mixing it through the house).
- Follow-up: re-run `event_response.py 18:08 18:59 --follow 60` after 20:00 to see any slow warming after the load stopped.
