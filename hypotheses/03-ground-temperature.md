# 03 Ground temperature follows a damped, lagged wave of air temperature

**Status:** first test run; the model fits the deep band roughly, with a warm offset

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

**Feeds:** 04, and the basement parts of 05-08, 10 and 13.

**From the prior-art review (4 November 2026; see `docs/prior-art-review.md`):**
- Manual J codes use one of two conventions for below-grade surfaces. Eldr uses an *effective* U, with the soil path included, at the full outdoor ΔT, and ignores the ground temperature in heating. Manual J (`ha-manual-j`, was `manual.py` here) uses a ground sink instead (`ground_c`, 5.6 °C, about the soil mean found below). A U-value only makes sense with its own convention, so record which one each surface uses.
- The design-day sink should come from this hypothesis, not the annual mean. With the fitted wave at 1.78 m (mean about 6 C, amplitude 0.37 × 15.2 ≈ 5.6 C, lag 74 days), the soil is coldest, about 0.4 C, in early April. Shallower wall is colder and earlier. So 5.6 °C understates late-winter loss through the basement walls. Test this when the basement fit in 04 is run.

## Results

First run (`scripts/ground_temperature.py --years 3`, ERA5-Land soil via Open-Meteo, 2023-10-27 to 2026-10-26, daily means):

- Air annual wave: mean 4.2 C, amplitude 15.2 C, coldest day 21 of the year.
- Soil bands' own annual waves: 0.04 m amplitude ratio 0.80 (lag -3 days); 0.17 m 0.74 (+3 d); 0.64 m 0.56 (+24 d); 1.78 m 0.37 (+74 d). Soil mean is 5.6 to 6.3 C, 1.4 to 2.1 C above the air mean (snow cover insulating the ground).
- Predicting each band from the air wave alone (Kusuda-Achenbach): at 1.78 m, the depth nearest a basement wall, the best diffusivity is about 0.020 m2/day, RMSE 2.1 C, or 1.5 C once a constant +1.5 C offset is allowed. That fits the damping (0.37 implies about 0.027) but under-predicts the lag (58 days against 74 observed).
- The fitted diffusivity changes with depth (0.002 at the surface to 0.020 at 1.8 m), so one constant-diffusivity soil does not describe all four bands: the shallow bands are dominated by snow and weather, not conduction.
- Not yet done: use the modelled 1.8 m soil as the basement's "outside" in 04 and see whether it fits the basement better than air; that needs a longer basement record than the 60 days in the recorder.
