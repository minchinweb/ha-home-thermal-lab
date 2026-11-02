# 12 Predict heat loss from wind speed and direction

**Status:** first test run; no wind effect detectable yet

**Claim:** Heat loss (and infiltration) of a room depends on wind speed and direction relative to its exposed faces.

**Data:** Wind speed/direction from weather, room temperatures, outdoor temperature.

**Method:** Fit `UA` as a function of wind on each face: `UA = UA0 + k * v^n * f(angle)`. Use night windows to avoid solar gain.

## Results

First test (`scripts/wind_loss.py`, 10 days to 2026-11-01; wind from Open-Meteo's forecast endpoint with `past_days`, because the archive lags several days):

- Data: 370 night bins (15 minutes) with no heating; wind there had a median of 2.8 m/s and a maximum of 7.0 m/s.
- Per room, `dT/dt = a * diff + b * wind * diff + c`: `a` is 0.014 to 0.024 per hour in most rooms (tau 42 to 72 h, as in 13), and `b` is between -0.0007 and +0.0006 per hour per m/s. No room's `b` is beyond two standard errors. For scale, `b` of +0.0003 means +1.7% heat loss per m/s, about +5% on a 3 m/s night.
- Pooled over all rooms with one wind term per face (N, E, S, W): no face is clearly different from zero (the north term is slightly negative and the others are about zero). R2 is 0.01, so wind explains almost none of the cooling variation.
- Reading: with these gentle nights, wind is not a detectable driver. A real effect of a few percent per m/s would be hidden by sensor resolution and the other flux terms. Retest after a windier cold spell (gusts above 10 m/s) and with the weather station when it is back, since 10 m forecast winds are not the wind at the house.
