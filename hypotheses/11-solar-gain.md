# 11 Predict room solar gain

**Status:** second test run (shading by sun direction); not validated

**Claim:** A room's solar gain can be predicted from weather, luminosity and sun position.

**Data:** Sun azimuth/elevation, cloud cover or lux/irradiance sensor, room temperatures, window orientation. Kitchen (large south and west windows) is the strongest test case.

**Method:**
- Model gain as `sum over windows of area * g * irradiance_on_face(azimuth, elevation, cloud)`.
- Fit per-room effective window coefficients on daytime idle windows.
- Validate on held-out days.

## Results

Regression view (10 days from 23 October 2026): a sun term (sine of sun height, daytime only) was significant only for the master bedroom (+0.62 C/h per unit) and the N bedroom (+0.41), both upstairs bedrooms. It was not significant for the kitchen (+0.25) despite its large south and west windows, perhaps because the kitchen is dominated by furnace bleed (06) and late-October sun is low. A longer, sunnier dataset is needed.

Caveat on the kitchen: it has been cloudy for the last few days of this dataset, so the small kitchen sun term says little. The test needs sunny days; recheck once there are some.


### Window-face model (`scripts/solar_gain.py --days 14`, 15 minute bins from 2026-10-19)

Irradiance from Open-Meteo (`direct_normal_irradiance` and `diffuse_radiation`, mean of the preceding hour), turned into light on a vertical wall facing N, E, S and W using the sun's azimuth and elevation (new `irradiance.py` and `solar_azimuth_degrees`). Fit per room on 491 daytime bins when its own zone was not heating: `dT/dt = a * (outdoor - room) + c + sum g_face * I_face`. Peak on a wall in this period: S 836, E 585, W 577, N 114 W/m2.

- South face: positive and beyond two standard errors in 7 of 12 sensors. Per 100 W/m2 on the south wall: kitchen +0.10 C/h, master +0.08, W bedroom +0.05, S basement +0.06, SE basement +0.06, N bedroom +0.03. At the 836 W/m2 peak that is up to about +0.8 C/h for the kitchen, the right order for large south windows.
- West face: mostly negative (kitchen -0.23 C/h per 100 W/m2, S basement, SE basement), which cannot be a real cooling by sunshine. South and west are correlated through the afternoon and the evening cool-down begins as the west sun peaks, so the two terms trade off. The basement rooms showing "solar gain" at all (S basement +0.06, SE +0.06) points the same way: this fit is picking up a daytime pattern, not just window light.
- East face: nothing clear (the morning is also when furnace set-points change).
- Held-out check (fit on the first two thirds of the days, scored on the last third, only a few days): the solar terms barely help (kitchen 1.08 to 1.05 C/h RMSE, master 0.40 to 0.39, S basement 0.46 to 0.46) and make four rooms worse (office 0.37 to 0.44, Office sensor 0.41 to 0.49, office air quality 0.42 to 0.49, W bedroom 0.34 to 0.36). The noise floor is high: one thermostat step of 0.06 C in 15 minutes is already 0.24 C/h.
- Conclusion: the kitchen and master bedroom show a plausible south-window gain, but this is not a validated prediction. Needs a sunnier and longer dataset (this fortnight was mostly cloudy, peak beam 886 W/m2 on only a few days), the furnace and fan terms from 05 and 08 so that the daytime cycle is not leaking into the sun terms, and probably a per-window area fit with non-negative constraints so the west term cannot go negative.


### Correction and shading view (`scripts/solar_gain.py`, same 14 days)

Corrections from the house: the office sensor and the office air-quality sensor are one room, so they are now averaged into a single "Office" series (this removes a double count in the table above: the office has no usable gain, with the south term -0.5 mC/h). Solar gain also needs an unshaded window: there are trees to the south and east and a low house immediately to the south, so what counts is the sun's compass direction together with its height, not only the wall it faces.

Second view: the cooling-law residual in sunny bins (316 of 491 daytime bins with beam above 100 W/m2; the sun was only 3 to 25 degrees high and 116 to 246 degrees round the compass), summed per direction and height cell and divided by the beam light, C/h per 100 W/m2 of beam (bins in brackets):

| Sun azimuth, elevation | Kitchen | Master | N bedroom | W bedroom | Office |
|---|---|---|---|---|---|
| 90-135, 0-14 (low, east to south-east) | 0.00 (32) | 0.00 | 0.00 | - | -0.04 |
| 135-170, 8-14 | +0.09 (7) | +0.01 | +0.01 | - | - |
| 135-170, over 14 | +0.16 (53) | +0.04 | +0.02 | +0.01 | 0.00 |
| 170-205 (due south), over 14 | -0.03 (62) | +0.07 | +0.01 | +0.02 | -0.04 |
| 205-250, 0-14 (low, south-west) | -0.18 and -0.10 | 0.00 and +0.03 | -0.03 and +0.03 | +0.01 and +0.07 | +0.06 and +0.01 |
| 205-250, over 14 | +0.08 (26) | +0.01 | +0.02 | +0.02 | -0.03 |

- Low sun to the east and south-east (under 14 degrees): no gain in any room, as expected with trees to the east and south-east and a house to the south.
- Kitchen: the gain is concentrated where the sun is south-east and above about 14 degrees (+0.16 C/h per 100 W/m2, 53 bins) and again at south-west above 14 degrees (+0.08). With the sun due south at the same height the kitchen shows nothing (-0.03, 62 bins), which would mean the south window is blocked even at that height, or the two are confounded by the time of day (late morning against noon). The data cannot separate them yet.
- Low sun to the south-west: negative or zero, so the evening sun reaches nothing at that height (or the west gain is being masked by the evening cool-down).
- Master bedroom: a small gain only with the sun due south and high (+0.07). N bedroom, W bedroom and the office: nothing above noise.
- Conclusion: the shading is real and strong in this part of the year (the sun never gets above 25 degrees), and most of the apparent south gain in the first table is from a narrow window of sun positions. A usable model must be a horizon profile per window (the lowest elevation at which the sun is clear, for each azimuth), not a wall-normal cosine. Better data: spring and autumn weeks with high sun, clear skies, and a noted tree-line from the kitchen window (a photo from each window would give the profile directly).
