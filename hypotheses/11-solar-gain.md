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
- The W bedroom's west window is the one clear wall term in the upper floors (+0.84 mC/h per W/m2).
- The S basement bedroom's and the SE bedroom's south windows are positive (+0.39 significant, +0.35); the NE basement east window (low to the ground) is +0.33 but not significant.
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


### Horizon on the roof faces too (`scripts/horizon_profile.py`)

Same 14 days, roof 12:12 (kitchen 3:12). Three ways of treating the roof, scored by leave-one-day-out RMSE (C/h) for the three rooms that have roof faces: unshaded (the walls-only column above), sharing the window horizon, and its own horizon:

| Room | cooling law only | windows, no shading | horizon on walls, roof unshaded | roof shares the wall horizon | roof has its own horizon |
|---|---|---|---|---|---|
| N bedroom | 0.327 | 0.331 | 0.331 | 0.322 | 0.322 |
| Master | 0.382 | 0.368 | 0.357 | 0.351 | 0.353 |
| Kitchen | 1.068 | 1.025 | 0.985 | 0.973 | 0.977 |

- Shading the roof helps a little in all three rooms, and the N bedroom now beats the cooling law alone (0.322 against 0.327) for the first time. The gain is 0.006 to 0.009 C/h, about 2% of the error, much smaller than the day-to-day spread, so it is a hint, not a result.
- The N bedroom's own roof horizon is 21 degrees for sun from 120 to 180 and 24 degrees for 180 to 210, clear at 90 to 120 and about 9 degrees at 210 to 240. The master's own roof horizon (6, 21, 0, 21, 6, 6) varies sector to sector like its wall horizon and looks over-fitted. The kitchen's low roof is clear except at 120 to 150 (18) and 180 to 210 (27).
- Sharing one horizon between a room's walls and roof does as well as giving the roof its own, with fewer parameters, so the simpler model is the better choice for now. This agrees with the east roof being shaded by the same trees that block the east and south-east windows.


### Photos from each window (2 November 2026, 13:11 local, sun at azimuth 178.5, height 20.8 degrees)

One photo or more from every window except the upstairs master bedroom. Heights are read from the photos (24 mm equivalent lens, about 830 px focal length at 1200 px). Where the sun is in the frame it sets the scale and these readings are good to about 2 degrees. Elsewhere the camera is assumed level, good to about 5 degrees. The phone's compass tag is not reliable indoors (off by 90 degrees on most landscape shots and wrong in the basement), so directions come from the room layout and the sun.

| Room | Window | What is in the way |
|---|---|---|
| Kitchen (Z1) | S patio door | Neighbour's roof about 13 degrees from 165 to 187; a spruce to about 21 degrees from 190 to 213; apartment block about 8 degrees from 216 to 229. Fence below eye level. Sun clear at noon today. |
| Kitchen (Z1) | W big window and W sink window | Garage roof 13 to 16 degrees across the middle of the view, a spruce behind it to about 18; bare trees to about 25 to the south-west. |
| Kitchen (Z1) | small E window by the fridge | Narrow; street trees (spruce and bare deciduous) across the front. |
| Front room (no sensor) | big E window | Street trees: a large elm close by and a spruce to the north-east, canopy above the top of the window. Bare now, leafy in summer. |
| Front room (no sensor) | two small S glass-block windows | Glass block: diffuse light only, no view. Sunlit at noon today. |
| Office (Z4) | E window | The same street trees, close; bare branches fill the upper view. |
| Entranceway (heated by Z4, open to the kitchen, no sensor) | N sidelight | Frosted glass, diffuse only. |
| W bedroom | W window | Backyard, neighbouring garages and roofs at about 13 degrees, trees to about 20. |
| N bedroom | N gable window | Bare tree and a neighbour's house; north, so direct sun only on summer mornings and evenings. |
| S basement (south-west) | S window | Fence top at about 20 degrees due south; trees above it to about 26 (south-south-east) and a spruce to about 28 (south-south-west). The sun at 20.8 degrees was just clear and lit the north wall. |
| SE basement | S window in a window well | Fence top at about 20 degrees due south, trees above it to about 25. The sun was right on the fence line and put a stripe of light on the door. |
| NE basement | N window (small) | A white wall a short distance away fills the whole view, plus a birch. North, so no direct sun anyway. |
| NE basement | E window (large, in a window well, facing the street) | Trees above the well. |

- The south basement windows match the fit well. The fence blocks the sun below about 20 degrees, so these rooms get almost no direct sun from now to early February (noon height is 13 degrees at the winter solstice). The fitted SE basement horizon (21 to 27 degrees) agrees.
- The fit says the NE basement is "clear at the east". That matches the photos once their labels are corrected (below): the large window in the well faces east to the street, and the wall is outside the small north window.
- The kitchen's fitted 27 degrees at 150 to 180 is higher than the photo (about 13, the neighbour's roof). The patio door may be shaded by the house's own eave or by the walls next to the door, which a photo from the middle of the room does not show. Or the fit is taking up time-of-day effects.
- Correction: the kitchen's third window faces east, not north, so `scripts/solar_windows.py` now has the kitchen as S, W and E. The horizon and roof tables above used S, W and N and need rerunning.


### Horizon fit rerun with the photo corrections (`scripts/horizon_profile.py --days 14 --rotation 10.4`, 19 October to 2 November 2026)

Kitchen walls now S, W and E (the small window is east, not north). NE basement dropped from the window fit (a wall outside what was taken to be its east window; corrected below, it is the north window). Clear-sun height in degrees by sun azimuth, with the photo reading next to it where there is one:

| Room | 90-120 | 120-150 | 150-180 | 180-210 | 210-240 | 240-270 | Photo | CV RMSE: cooling law / no shading / walls only / roof shared / roof own |
|---|---|---|---|---|---|---|---|---|
| Kitchen | 6 | 21 | 18 | 18 | 0 | 0 | patio door: roof ~13 at 165-187, spruce ~21 at 190-213, ~8 at 216-229 | 1.083 / 1.040 / 0.987 / 0.972 / 0.972 |
| Master | 6 | 21 | 18 | 18 | 18 | 6 | (no photo) | 0.398 / 0.381 / 0.368 / 0.370 / 0.364 |
| S basement | 6 | 18 | 27 | 0 | 0 | . | fence ~20 due south, trees ~26 SSE, spruce ~28 SSW | 0.510 / 0.506 / 0.489 |
| SE basement | 0 | 21 | 21 | 27 | 21 | . | fence ~20 due south, trees to ~25 | 0.889 / 0.888 / 0.880 |
| N bedroom | 0 | 0 | 0 | 0 | 0 | . | north window | 0.329 / 0.330 / 0.330 / 0.329 / 0.329 |
| W bedroom | . | 0 | 0 | 18 | 9 | . | roofs ~13, trees ~20 | 0.302 / 0.310 / 0.326 |
| Office | . | 21 | 21 | 0 | 0 | 0 | bare street trees | 0.400 / 0.402 / 0.402 |
| NE basement | | | | | | | wall outside the window taken to be east (it is the north one) | not fitted; refitted below |

- Kitchen: with the east window in place of the north one, the fitted south-south-east height falls from 27 to 18 degrees, close to the photo (the neighbour's roof at about 13). The 18 for 180 to 210 matches the spruce (about 21). The cross-validated errors are almost the same as before (0.972 against 0.973), so the direction of the small window hardly matters to the fit.
- SE basement: 21 to 27 degrees across the south, as the photo shows (fence at 20, trees above). The shading is confirmed, but the window still adds almost nothing to the prediction (0.880 against 0.889). The room barely sees the sun at this time of year.
- S basement: 27 for 150 to 180 fits the trees above the fence. 0 for 180 to 210 does not fit the photo (fence at about 20, spruce at about 28). In this period the sun in that sector is only 18 to 26 degrees high, so the fit cannot tell 0 from 18. Using the photo's 20 would be more trustworthy. This room now improves under cross-validation (0.510 to 0.489), which the earlier run did not show.
- The shading is still learned from a narrow band of sun heights (3 to 26 degrees). The photo readings are the better values until spring data reaches higher sun.

### Kitchen on 2 November 2026: a clear day, and the bleed term

The kitchen rose from 21.4 C at 10:15 to 25.0 C at 14:07 (local) with its own zone off, on a clear day (700 to 770 W/m2 beam). The oven ran from about 12:15 to 13:00 (whole-house power up from about 1.1 to 4.0 kW).

- The committed window model (S, W, E and the low W roof, with the fitted horizon and no bleed) ran forward from 09:22 reached 23.2 C by 13:45, against 24.8 measured. Its south gain was negative, and the small east window carried most of the sun term.
- With the other zones' calls added as bleed terms (06), the model tracks the kitchen within 0.2 C until 12:30. The rise from 10:15 to 12:30 was Z4 and Z2 calls, at +1 to +3 C/h.
- After 12:30 the kitchen gained about 1 C more than the model by 13:45. In that time the sun was clear of the neighbour's roof from the patio door, and the oven was running. One day cannot separate the two. If it were all sun, the patio door's gain would be about 0.7 mC/h per W/m2.
- Photos at 14:08 (sun at 193 degrees, 20 high) show the sun shining through the spruce. A broad stripe of light with dappled branch shadows crosses the floor and the island. The spruce blocks only part of the light. The kitchen kept rising (24.84 to 25.03 C from 13:52 to 14:07) with the oven off and only a short Z2 call.

### Horizon fit with bleed and partial transmission (`scripts/horizon_profile.py --days 15`, 18 October to 2 November 2026)

Every model now has the other zones' calls as terms, the cooling law included. The kitchen roof is now 18.8 degrees (about 4:12), measured from the ceiling, which falls from 12.5 ft to 8 ft across the 13.25 ft east-west span, in place of the 3:12 (14 degrees) used before. The change moves the kitchen's numbers by less than 0.01 C/h. A new "partial" model lets a fitted share of blocked beam through (0 to 90% in steps of 10). The same terms were added to `scripts/solar_windows.py`.

| Room | 90-120 | 120-150 | 150-180 | 180-210 | 210-240 | 240-270 | Through blocked | Bleed C/h per call | Window gain mC/h per W/m2 | CV RMSE: cooling law / no shading / walls only / partial / roof shared / roof own |
|---|---|---|---|---|---|---|---|---|---|---|
| Kitchen | 6 | 18 | 0 | 27 | 0 | 0 | 0% | z2 +1.92, z4 +2.10 | S +0.79, W -1.57, E +0.33 | 0.716 / 0.703 / 0.712 / 0.712 / 0.694 / 0.718 |
| Master | 6 | 21 | 18 | 18 | 21 | 6 | 0% | z4 +0.13 | S +0.62 | 0.396 / 0.381 / 0.369 / 0.369 / 0.370 / 0.372 |
| S basement | 0 | 15 | 21 | 24 | 21 | . | 0% | z4 +0.70 | S +0.80 | 0.440 / 0.440 / 0.424 / 0.424 |
| SE basement | 0 | 9 | 21 | 27 | 21 | . | 0% | z4 +0.73 | S +0.62 | 0.850 / 0.851 / 0.858 / 0.858 |
| N bedroom | 0 | 0 | 0 | 0 | 0 | . | 0% | z4 +0.43 | N +0.09 | 0.305 / 0.309 / 0.309 / 0.309 / 0.308 / 0.308 |
| W bedroom | . | 0 | 0 | 18 | 9 | . | 40% | z2 +0.17 | W +0.91 | 0.292 / 0.307 / 0.323 / 0.323 |
| Office | . | 21 | 24 | 0 | 0 | 0 | 10% | z2 +0.41 | E -1.64 | 0.389 / 0.391 / 0.395 / 0.393 |

- The bleed term is what matters for the kitchen. Its error falls from 0.97 C/h (best model without bleed) to 0.69 to 0.72 with it, a 28% cut. That is far more than any window term has given. With bleed in, the windows add only 3% (0.716 to 0.694).
- The kitchen's south gain is now positive (+0.81 mC/h per W/m2, close to today's 0.7), and the east window drops to +0.31. The west term is still negative. West sun comes as the evening cool-down starts, so the two cannot be told apart yet.
- The fit lets no blocked light through for the kitchen. It puts 180 to 210 at 27 degrees, fully blocked, which is at odds with today's photos. In this period, sun from 180 to 210 was rare and low, and the sunny days often had calls around noon. Today's data is better evidence than the fit: the spruce passes a good share. Recheck after more clear days.
- Z1 and Z3 never called in this period, so their bleed terms are zero.
- The S, SE and NE basement rooms show +0.5 to +0.9 C/h per Z4 call, although the airflow check found no Z4 air reaching them. That heat comes another way, through the stairs, warm ducts or the furnace room, or Z4 calls happen at the same times as something else.

### Window sizes and apertures (`scripts/room_geometry.py`, `scripts/room_capacity.py`)

Window sizes are the owner's tape measurements, width x height in inches (the sink window is the glass alone; the others are the whole window or door):

| Room | Windows | Glass m2 |
|---|---|---|
| Kitchen | S patio door 70 x 80; W window 74 x 80; W sink window 45 x 32; E 12 x 60 | 3.6 S, 4.7 W, 0.5 E |
| Front room | E 77 x 54; S glass blocks 2 x (7.5 x 31) | 2.7 E, 0.3 S |
| Z4 office (main office) | E 73 x 54 | 2.5 |
| Small office | E 32 x 43 | 0.9 |
| Entranceway | N sidelight 14 x 80 (frosted) | 0.7 |
| W bedroom | W 34 x 52 | 1.1 |
| N bedroom | N 48 x 55 | 1.7 |
| Master | S 48 x 55 | 1.7 |
| S basement (south-west) | S 67 x 31 | 1.3 |
| SE basement | S 47 x 31 | 0.9 |
| NE basement | N 32 x 18; E 47 x 31 | 0.4 N, 0.9 E |

The photo estimates of area were mostly 20 to 45% low (the W bedroom only 8%) (kitchen west window 60 x 60 against 74 x 80; patio door 54 x 75 against 70 x 80).

The kitchen's west window is starting to catch its own light now that the afternoon sun swings far enough round to the south-west.

A window gain times the room's effective heat capacity (13) is watts per W/m2 of sun, an effective aperture. With a 25 K supply rise (35 K in brackets), unshaded light and the bleed terms in:

| Room | Window | Gain mC/h per W/m2 | Aperture m2 | Glass m2 | Share |
|---|---|---|---|---|---|
| W bedroom | W | +0.74 | 1.2 (1.6) | 1.1 | 110 to 145% |
| Kitchen | S patio door | +0.51 | 1.1 (1.6) | 3.6 | 30 to 45% |
| S basement | S | +0.17 | 0.2 (0.3) | 1.3 | 15 to 25% |
| SE basement | S | +0.13 | 0.1 (0.2) | 0.9 | 10 to 20% |
| NE basement | E | +0.20 | 0.2 (0.3) | 0.9 | 20 to 30% |
| Kitchen | W, E | negative | - | 4.7, 0.5 | - |
| Z4 office | E | negative | - | 2.5 | - |

- The patio door works like a third to under half of its area. That fits the frame, partly drawn curtains, double glazing (about 70% of the sun through) and the trees treated as clear in this fit. The fitted gain is the right order, so it is real sun, not a stand-in for time of day.
- The W bedroom's aperture is larger than its whole window, more than glass can pass. The supply rise may be under 25 K for that room (a longer duct run), or the room gets other heat that follows the west sun.
- The basement windows act like a tenth to a quarter of their area. That fits the window wells and the fence in the photos.
- The kitchen's large west window (4.7 m2 with the sink window) still fits as negative. West sun comes as the evening cool-down starts, and so far the west sun has been low and behind the garage and spruce. With the sun now reaching it, the next clear afternoons should settle it.
- A supply-air temperature at a register would turn the apertures from checks of order into calibrated numbers.

### NE basement: the photo labels were swapped

The owner confirms that the NE basement's large window, in a window well, faces east to the street, and the small one with a wall just outside faces north. The two photos were labelled the wrong way round. The east window is back in `scripts/solar_windows.py`, so the fit uses it again (15 days to 2 November 2026, with bleed):

- Horizon 6 degrees for sun from 90 to 120, clear from 120 to 150, 21 and 27 degrees from 150 to 210 (the house and trees to the south). That is the shape expected for an east window: the morning sun reaches it, and the sun to the south is behind the house.
- Window gain +0.42 mC/h per W/m2 with the horizon (+0.20 unshaded), an aperture of about 0.2 m2, a fifth to a third of its 0.9 m2. That is in line with the other basement windows in their wells.
- It still does not help prediction: cross-validated error 0.802 C/h for the cooling law and bleed alone, 0.811 with the window. The morning sun on it is small and low at this time of year.
