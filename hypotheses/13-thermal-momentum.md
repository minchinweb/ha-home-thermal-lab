# 13 Thermal momentum of the house

**Status:** untested

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
