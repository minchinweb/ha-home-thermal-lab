# 03 Ground temperature follows a damped, lagged wave of air temperature

**Status:** untested

**Claim:** For basement rooms the "outside" is the ground, which is not measured directly. Its temperature at basement depth can be modelled from above-ground air temperatures, as a seasonal wave that is smaller and later than the air's.

**Known model:** The classic Kusuda-Achenbach (1965) solution for soil temperature at depth `z` and day `t`:

`T(z, t) = T_mean - A * exp(-z / d) * cos(2*pi*(t - t0 - z/d * 365/(2*pi)) / 365)`

where `T_mean` is the mean annual air (surface) temperature, `A` is the annual air-temperature amplitude, `t0` is the day of the coldest surface temperature, and `d = sqrt(2*alpha/omega)` is the damping depth, with soil thermal diffusivity `alpha` (roughly 0.04-0.09 m2/day, depending on soil and moisture) and `omega = 2*pi/365`. Deeper means a smaller swing and a longer lag. At basement depth (about 1.5-3 m) the swing is a fraction of the air's and the minimum comes months after the coldest air.

**Complications:** Snow cover insulates the ground (important for Edmonton), soil moisture changes `alpha`, and the heated basement itself warms the nearby soil.

**Data:**
- Open-Meteo's historical API has modelled soil temperature at several depths (ERA5-Land, from the surface to about 2.5 m), which gives a check on the model without sensors in the ground.
- Basement room temperatures and the basement's heat balance, for an indirect check (see 04).

**Method:**
- Fit `T_mean`, `A`, `t0` and `alpha` to the modelled soil temperatures at each depth, from several years of air temperature.
- Test how well air temperature alone predicts them, and whether snow depth or soil moisture improves it.
- Use the fitted model as the "outside" temperature for basement rooms in 04, and check whether it makes the basement flux fit better than using air temperature.

**Feeds:** 04, and the basement parts of 05-07, 09 and 12.

## Results

_none yet_
