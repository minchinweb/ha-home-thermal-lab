# 12 Predict heat loss from wind speed and direction

**Status:** first test run; no wind effect detectable yet

**Claim:** Heat loss (and infiltration) of a room depends on wind speed and direction relative to its exposed faces.

**Data:** Wind speed/direction from weather, room temperatures, outdoor temperature.

**Method:** Fit `UA` as a function of wind on each face: `UA = UA0 + k * v^n * f(angle)`. Use night windows to avoid solar gain.

**From the literature review (4 November 2026):** ISO 13789 splits envelope loss into transmission (`H_tr`, fabric) and ventilation (`H_ve`). Wind should act on the ventilation part only, so the effect is a share of `UA`, not all of it: the `b * wind * diff` form in the first test below is right, and a tight house would show a small `b`. See 04 for the split. Heating Analytics notes wind and cloud are poor in standard weather feeds, which is another reason to retest with the weather station.

## Results

First test (`scripts/wind_loss.py`, 10 days to 2026-11-01; wind from Open-Meteo's forecast endpoint with `past_days`, because the archive lags several days):

- Data: 370 night bins (15 minutes) with no heating; wind there had a median of 2.8 m/s and a maximum of 7.0 m/s.
- Per room, `dT/dt = a * diff + b * wind * diff + c`: `a` is 0.014 to 0.024 per hour in most rooms (tau 42 to 72 h, as in 13), and `b` is between -0.0007 and +0.0006 per hour per m/s. No room's `b` is beyond two standard errors. For scale, `b` of +0.0003 means +1.7% heat loss per m/s, about +5% on a 3 m/s night.
- Pooled over all rooms with one wind term per face (N, E, S, W): no face is clearly different from zero (the north term is slightly negative and the others are about zero). R2 is 0.01, so wind explains almost none of the cooling variation.
- Reading: with these gentle nights, wind is not a detectable driver. A real effect of a few percent per m/s would be hidden by sensor resolution and the other flux terms. Retest after a windier cold spell (gusts above 10 m/s) and with the weather station when it is back, since 10 m forecast winds are not the wind at the house.

### Windy day review (2026-11-10; HA history, 2026-11-05 to 11-10)

A windy day about 4-5 days earlier (OpenWeatherMap and the Environment Canada station agree, km/h feeds) was checked against the night cooling of each room (k = -slope / (Tin - Tout) over 00-05 h) and a pooled fit `dT = a*diff + b*wind*diff` with room fixed effects on night hours 22-05.

- Windy nights cool faster once normalised by the inside-outside gap, but the pooled `b` is not robust: t = 2.5 with the OWM wind, 1.1 with the station wind, and lower again without 2026-11-09.
- The windy spell was a warm storm, so the inside-outside gap was small, which limits what can be resolved.
- Reading: a weak, unconfirmed hint, not a detection. Retest with a windy night that is also cold (gap above 15 C). Exclude 2026-11-09 about 17:26-17:42 (Zigbee sensors logged 0.0) and 19:10-19:45 (install window).
