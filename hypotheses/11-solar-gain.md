# 11 Predict room solar gain

**Status:** untested

**Claim:** A room's solar gain can be predicted from weather, luminosity and sun position.

**Data:** Sun azimuth/elevation, cloud cover or lux/irradiance sensor, room temperatures, window orientation. Kitchen (large south and west windows) is the strongest test case.

**Method:**
- Model gain as `sum over windows of area * g * irradiance_on_face(azimuth, elevation, cloud)`.
- Fit per-room effective window coefficients on daytime idle windows.
- Validate on held-out days.

## Results

_none yet_
