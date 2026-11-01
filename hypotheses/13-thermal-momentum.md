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
