# 04 Heat flux through the envelope from inside and outside temperatures

**Status:** untested

**Claim:** We can measure the heat flux between the house and the outside from the inside and outside temperatures. For upper-level rooms the outside is the air; for basement rooms it is the ground (see 03).

**Method:**
- Model the flux as `q = UA * (T_in - T_out)` per room (or per level), with `T_out` the air temperature for upper rooms and the modelled ground temperature for basement rooms.
- Temperatures alone give the ratio `UA / C` (the cooling time constant), not `UA`. To get `UA` in watts per degree, add a heat input (furnace runtime, electrical use from 14) or a known thermal mass.
- Fit on clean windows: night, no furnace or AC running, doors closed, little wind, so only the envelope is acting. Then add the wind (12) and solar (11) corrections.
- Compare per-room and per-level `UA`, and see whether `UA` for upper rooms shifts with wind while the basement's does not.

**Caveats:** Neighbouring rooms exchange heat too (10), and zoning leakage keeps "off" zones from being isolated.

**Data:** Room and outdoor temperatures, ground model from 03, furnace/AC call states, electrical use.

**Feeds:** 05, 07, 13 (thermal momentum) and 16 (prediction).

## Results

_none yet_
