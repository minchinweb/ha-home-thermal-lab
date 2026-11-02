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


### Windows, roof and house rotation (`scripts/solar_windows.py --rotation 10.4`, same 14 days)

House rotation: the OpenStreetMap outline for the house (8 walls, all on one grid) has its walls 10.4 degrees clockwise of north (`scripts/house_orientation.py`). Rotating the model by 10.4 degrees changes the coefficients modestly (for example master east roof +0.82 against +0.94 at 0 degrees), so it is a refinement, not a big effect at this latitude and season.

Window and roof layout used (from the house): N bedroom north window + east and west roof faces (roof pitch assumed 25 degrees; 18 degrees changes little); master south window + east/west roof; W bedroom west; office east (limited winter light); kitchen south, west and a small north-east window + a low-slope (10 degree) west roof; S basement and the SE basement bedroom south windows; NE basement an east window low to the ground. The front room (large east window) has no sensor yet.

Milli-C/h per W/m2 (* = beyond two standard errors):

| Room | Walls | Roof | Clear sky at night (mC/h) |
|---|---|---|---|
| N bedroom | N +0.08 | E +0.25*, W +0.42 | -51 |
| Master | S -0.19 | E +0.82*, W +1.46* | -22 |
| W bedroom | W +0.84* | - | -74 |
| Office | E -0.17 | - | -61 |
| Kitchen | S -1.78*, W -1.33, E +1.82* | W (10 degrees) +5.39* | -125* |
| S basement | S +0.39* | - | -36 |
| SE basement | S +0.35 | - | +1 |
| NE basement | E +0.33 | - | +31 |

- The attic rooms respond to the roof, not the wall: the master bedroom has a significant gain on both roof faces (west +1.46, east +0.82, about +0.15 C/h per 100 W/m2 at the west face) while its south window term is zero or slightly negative; the N bedroom's east roof face is significant and her north window is nothing. This agrees with the roof deck heating the attic rooms.
- the W bedroom's west window is the one clear wall term in the upper floors (+0.84 mC/h per W/m2).
- the S basement bedroom's and the SE bedroom's south windows are positive (+0.39 significant, +0.35); the NE basement east window (low to the ground) is +0.33 but not significant.
- Windows lose heat to a clear sky: the clear-sky term is negative for the kitchen (-125 mC/h when the sky is clear compared with overcast, significant), and negative but within noise for N bedroom, W bedroom, the office, the master and S basement. The basement rooms with windows low to the ground (SE, NE) show none. That fits the user's suggestion that windows can show a negative effect: extra radiant loss on clear nights, which is part of why the daytime terms and the air-temperature term can disagree.
- Kitchen caution: the wall and roof terms are large and have opposite signs (S -1.78, E +1.82, west roof +5.4), which is collinearity between faces over a fortnight with the sun between 3 and 25 degrees, not independent window gains. The 10 degree roof is close to a horizontal surface, so it also picks up anything that follows the sun's height.
- Next: a horizon (shading) profile per window as described above, a longer and sunnier dataset, a front-room sensor, and fixing the roof pitch (a photo or the plans).


### Horizon-profile fit (`scripts/horizon_profile.py --rotation 10.4`, same 14 days; roof 12:12 = 45 degrees, kitchen roof 3:12 = 14 degrees, kitchen walls S, W and N)

Each room's window light is the beam (when the sun is above that sector's horizon) plus the diffuse sky, with a stepped horizon per 30 degree sector of sun azimuth chosen by coordinate descent; roof faces are unshaded. Scored by leave-one-day-out cross-validation (the horizon is re-fit with each day held out). Clear-sun height in degrees (0 clear, 27 to 30 blocked at every height seen, `.` = under 5 sunny bins):

| Room | 90-120 | 120-150 | 150-180 | 180-210 | 210-240 | 240-270 | CV RMSE, cooling law only | windows, no shading | with horizon |
|---|---|---|---|---|---|---|---|---|---|
| Kitchen | 0 | 15 | 27 | 18 | 0 | 0 | 1.068 | 1.025 | 0.985 |
| Master | 6 | 21 | 0 | 18 | 18 | 6 | 0.382 | 0.368 | 0.357 |
| S basement | 6 | 18 | 27 | 0 | 0 | . | 0.509 | 0.510 | 0.504 |
| SE basement | 0 | 21 | 21 | 27 | 21 | . | 0.882 | 0.881 | 0.881 |
| NE basement | 6 | 0 | 21 | 27 | 0 | . | 0.808 | 0.809 | 0.817 |
| N bedroom | 0 | 0 | 0 | 0 | 0 | . | 0.327 | 0.331 | 0.331 |
| W bedroom | . | 0 | 0 | 18 | 9 | . | 0.306 | 0.310 | 0.326 |
| Office | . | 21 | 21 | 0 | 0 | 0 | 0.396 | 0.398 | 0.401 |

- Only the kitchen and the master bedroom improve under cross-validation, and only by a little: the kitchen error falls 1.068 to 0.985 C/h (8%) with the horizon (4% without shading), the master 0.382 to 0.357 (7%). For every other room, adding the windows, with or without a horizon, does not predict held-out days better than the cooling law alone (W bedroom and the NE basement are worse).
- Kitchen: the fitted horizon is blocked at 27 degrees for sun from 150 to 180 (south-south-east), 18 degrees for 180 to 210 (south), and clear for south-west and west (210 to 270). That is the shape expected with trees and a low house to the south, a clear west, and sun that only reaches 25 degrees in the period, so south light gets through only in the last weeks of low sun. It is the best-supported result.
- Master bedroom: the south window shows 0 at 150 to 180 and 18 at 180 to 270, a pattern that varies sector to sector and is likely over-fitting; its gain comes mostly from the roof (see above).
- Basement bedrooms (S basement, SE): blocked to 21 to 27 degrees across the south-east to south, so effectively no direct light in this period, consistent with low windows behind a house and trees to the south. NE basement is blocked towards the south and clear at the east.
- N bedroom, W bedroom and the office have no useful window signal: the N bedroom's north window never sees direct sun; the office east window and the W bedroom's west window gain nothing beyond noise over these two weeks.
- The shading is a step (one height per 30 degree sector), is learned from about 300 sunny bins in 14 days, and is not validated against a photo of the tree line. A photo from each window, or a sun-path tool, would give the true profile to compare with these steps.
