# 11 Predict room solar gain

**Status:** untested

**Claim:** A room's solar gain can be predicted from weather, luminosity and sun position.

**Data:** Sun azimuth/elevation, cloud cover or lux/irradiance sensor, room temperatures, window orientation. Kitchen (large south and west windows) is the strongest test case.

**Method:**
- Model gain as `sum over windows of area * g * irradiance_on_face(azimuth, elevation, cloud)`.
- Fit per-room effective window coefficients on daytime idle windows.
- Validate on held-out days.

## Results

Regression view (10 days from 23 October 2026): a sun term (sine of sun height, daytime only) was significant only for the master bedroom (+0.62 C/h per unit) and the N bedroom (+0.41), both upstairs bedrooms. It was not significant for the kitchen (+0.25) despite its large south and west windows, perhaps because the kitchen is dominated by furnace bleed (06) and late-October sun is low. A longer, sunnier dataset is needed.

Caveat on the kitchen: it has been cloudy for the last few days of this dataset, so the small kitchen sun term says little. The test needs sunny days; recheck once there are some.
