# 04 Heat flux through the envelope from inside and outside temperatures

**Status:** untested

**Claim:** We can measure the heat flux between the house and the outside from the inside and outside temperatures. For upper-level rooms the outside is the air; for basement rooms it is the ground (see 03).

**Method:**
- Model the flux as `q = UA * (T_in - T_out)` per room (or per level), with `T_out` the air temperature for upper rooms and the modelled ground temperature for basement rooms.
- Temperatures alone give the ratio `UA / C` (the cooling time constant), not `UA`. To get `UA` in watts per degree, add a heat input (furnace runtime, electrical use from 14) or a known thermal mass.
- Fit on clean windows: night, no furnace or AC running, doors closed, little wind, so only the envelope is acting. Then add the wind (12) and solar (11) corrections.
- Compare per-room and per-level `UA`, and see whether `UA` for upper rooms shifts with wind while the basement's does not.
- Split the fitted envelope coefficient into fabric and ventilation, as ISO 13789 does with `H_tr` and `H_ve` (formulas not checked against the standard). The temperatures give only the total. Ventilation should rise with wind (12) and with open windows or doors (09), so those terms separate the two. Without heat flux sensors the split is a model assumption, not a measurement.

**Caveats:** Neighbouring rooms exchange heat too (10), and zoning leakage keeps "off" zones from being isolated.

**Data:** Room and outdoor temperatures, ground model from 03, furnace/AC call states, electrical use.

**Feeds:** 05, 07, 13 (thermal momentum) and 16 (prediction).

## Results

First regression (`scripts/regress_rooms.py`, 10 days from 23 October 2026, 30-minute bins, 12 room sensors; each room's rate of temperature change against outdoor minus indoor temperature, each zone's heat call, a sun term and whole-house power). The outdoor coupling `k` (per hour, so the time constant `tau` is 1/k) came out between 0.01 and 0.06 per hour, i.e. time constants of roughly 20 to 160 hours, shortest for the kitchen (about 23 h) and the office (about 18-45 h), longest for the upstairs rooms (Z3 master 121 h, N bedroom 161 h, but not significant for N bedroom). These are weakly determined: ten days of mild weather barely moves the outdoor term and it is correlated with the other terms, so treat them as a rough scale, not a result. The fits explain 10-63% of the variance (W bedroom 0.63, Z4 office 0.61, Z2 basement 0.53; upstairs bathroom 0.10).
