# 13 Thermal momentum of the house

**Status:** in progress; cool-down tau, wave lag, furnace start lag and overshoot measured

**Claim:** The house's thermal momentum (inertia) can be measured: how long a room keeps changing temperature after the heat source stops, or how slowly it follows the outdoor wave.

**Data:** Room temperatures, furnace/AC/fan call states, outdoor temperature, solar data.

**Method:**
- Overshoot after the furnace stops: the extra rise and how long it lasts.
- Cool-down: after heating ends at night, fit the decay toward outdoor temperature to get a time constant `tau = C / UA`.
- Lag: the delay and damping of each room's daily wave compared with the outdoor wave (the phase lag and amplitude ratio of the fits from 01/02).
- Compare rooms and floors; a larger `tau` means more momentum.

**Feeds:** 16 (prediction) and 17 (control): the overshoot to avoid is this momentum. Shares parameters with 04, 05, 06, 10 and 12.

## Results

First look (see 05 for the table): after the furnace stops, the office (z4) stops rising almost at once (0.1 C more, peak 3 minutes later), while the basement (z2) keeps rising about 0.6 C for about 14 minutes. That suggests the basement has more momentum, or a slower air path, than the office. Thermostat resolution (about 0.1 C) limits this, and 10 days of data is only a start.

### First measurement (`scripts/thermal_momentum.py`, 10 days to 2026-11-01, 15-minute bins)

- Cool-down time constant, from sun-down bins with no heating: tau is roughly 47 to 76 hours across rooms, each with a wide margin (+-10 to 25 h). The master bedroom gave no usable slope. That is slow, as expected for a house that is only a few degrees from outdoors, but the rooms cannot be ranked yet: the margins overlap.
- Wave damping: rooms swing 0.1 to 0.5 times the outdoor amplitude (2.7 C; a mild stretch). The kitchen has the largest swing (0.53), which fits its big south and west windows; the upstairs bathroom the smallest (0.08).
- Wave lag: most rooms peak 2 to 3 hours before the outdoor wave, not after. So over these days the indoor wave is driven by the sun, thermostat schedules and heating rather than by outdoor air.
- Heat-up rates at night exist only for z4 (+1.7 to +3.4 C/h), because only z4 called for heat overnight.
- Watts: needs `--furnace-kw`; not run, as the furnace output is not yet recorded.

### First whole-house estimate (80,000 BTU/h input, 95% efficiency, low stage taken as half)

High stage output 22.3 kW; stage-weighted mean output over the 10 days 2.13 kW against a 21 C to -0.5 C difference gives UA of about 100 W/C (about 0.04 W/C per sq ft over roughly 2400 sq ft, four zones of about 600). With a median tau of 60 h, thermal mass C is about 6 kWh/C. Rough: it ignores sun, people and appliances, and the low-stage fraction is unconfirmed (see 05). Because UA scales with the low-stage fraction and C with UA, a 0.65 low stage would raise both by roughly 15%.

### Re-run with the low stage at 65% of high (working assumption until the nameplate is read; see 05)

Mean furnace output 2.63 kW; UA about 123 W/C (about 0.05 W/C per sq ft); median tau 54 h (the data window moved slightly); C about 6.7 kWh/C. `--low-fraction` now defaults to 0.65.

### Furnace start lag, and the dip and rebound after a call (`scripts/furnace_lag.py`, 11 days to 2026-11-02)

From the thermostat's own reading (about 0.06 C steps), per call; overshoot, dip and rebound only for calls with 30+ minutes before the next one, within 90 minutes of the end:

| Zone, calls | Lag to first rise | No rise at all | Rise during call | Overshoot after | Dip after (at) | Rebound |
|---|---|---|---|---|---|---|
| z2 low only (62, median 6 min) | 3 min | 0 | +0.3 C | +0.45 C | -0.2 C (47 min) | 0.0 |
| z4 low only (114, median 9 min) | 8 min | 17 | +0.1 C | +0.2 C | -0.2 C (48 min) | +0.1 |
| z4 stepped up (18, median 66 min) | 6 min | 0 | +1.7 C | +0.2 C | -0.1 C (33 min) | 0.0 |

- Lag: heat reaches the z4 thermostat about 6 to 12 minutes after a call starts, and the median z4 low-stage call lasts only 9 minutes. 17 of 114 z4 calls ended before the reading moved at all. Most short calls stop just as the warm air arrives, and the room keeps rising about 0.2 C after the furnace stops. z2's thermostat responds in 3 minutes.
- After a call: the overshoot (+0.2 to +0.45 C) comes first, then the reading falls back below the end value (-0.1 to -0.2 C) within 30 to 50 minutes. A rebound as surfaces give heat back is not visible at the thermostat's 0.06 C resolution (median 0 to +0.1 C). The dip may be ordinary cooling rather than the loss of forced warm air; separating them needs the room sensors at finer resolution or longer gaps between calls.
- For control (17): the 6 to 12 minute lag plus about 0.2 C of overshoot is the momentum to anticipate. A controller that stops calls about 0.2 C early would land near the setpoint.
