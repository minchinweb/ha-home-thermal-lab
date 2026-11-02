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

Live ground truth, 1 November 2026, 18:08 local: the owner turned a stove burner on and told us. Whole-house power (Eagle sensor, about 30-second readings) stepped from 1.16 to 2.30 kW at 18:08:01 (+1.1 kW), reached 4.2 kW at 18:14, then began cycling between about 1.1 kW and 3.0-3.3 kW every 30-60 seconds, the on/off cycling of an electric element holding temperature. The furnace was idle (only fan calls) so the kitchen was a clean test; it was cooling slowly (22.4 to 21.9 C over the previous 20 minutes). The bursts of +1.2 to +2.3 kW found in the history are consistent with this signature, which supports reading them as stove use.

