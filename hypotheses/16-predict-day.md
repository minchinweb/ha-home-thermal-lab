# 16 Predict next-day house/room temperature

**Status:** two backtests run; the profile with offset beats naive baselines; sun terms do not help yet

**Claim:** With the fitted factors (B, C) and a weather forecast, we can predict each room's temperature for the coming day.

**Data:** Fitted thermal model, weather forecast (temperature, cloud, wind), planned furnace/AC schedule, expected electrical load.

**Method:** Simulate the RC model forward 24 h. Backtest on historical days using the forecasts that were available at the time. Report per-room error against a naive baseline (persistence, or the wave component alone).

## Results

First backtest (`scripts/predict_day.py --days 40`): rolling origin, at local midnight (America/Regina) of every test day predict the 24 hourly room temperatures of the day ahead from earlier data only. Hourly long-term statistics, 40 days to 2026-11-02, test days 10 to 39 (15 to 30 days per room: the Zigbee bedroom sensors have about 20 days of history). Outdoor temperature is the measured value, standing in for a perfect forecast. The office sensor and the office air-quality sensor are one room.

Mean RMSE (C) over 24 h, averaged over rooms and test days:

| Predictor | RMSE |
|---|---|
| A persistence (hold the midnight value) | 0.75 |
| B yesterday | 0.47 |
| C mean of the last 7 days at each hour | 0.47 |
| D profile + offset decaying with a fitted time constant | 0.43 |
| E D + accumulated outdoor temperature difference | 0.42 |

By lead time: hours 0 to 5, A 0.77, B 0.35, C 0.39, D 0.22, E 0.20; hours 6 to 23, A 0.73, B 0.50, C 0.48, D 0.48, E 0.47.

- Everything beats persistence by a wide margin, and a simple recent-days profile (C) already reaches 0.47 C. Starting from the actual midnight temperature (D) takes the first six hours down to 0.22 C, with a fitted memory of 2 to 16 hours (median 4 to 8): in a thermostat-controlled house a deviation fades within hours.
- After the first six hours nothing improves on the profile (0.48 to 0.50 for B, C, D and E): that remainder is the furnace and setpoint cycle, people, and solar gain, none of which is in these predictors.
- Outdoor temperature adds little: 0.43 to 0.42 on average. It helps the master bedroom (0.40 to 0.35, k = 0.007 C per C-hour) and the upstairs bathroom (0.39 to 0.34), a little for N bedroom (0.39 to 0.37), and not at all for the kitchen and the basement rooms (k about 0.001 to 0.004), which is what a thermostat-held zone with a 50 h time constant should do.
- Kitchen (0.60) and office (0.52) are the least predictable; the Z2 basement (0.33) and S basement (0.28) the most.
- Not yet tried: the actual RC simulation with the fitted tau, UA and C; the furnace/setpoint schedule as an input; solar terms from 11; a real weather forecast (the Open-Meteo archive has no forecasts as issued, so a backtest against forecasts needs them recorded going forward); a longer record.


### Sun terms added (same backtest, `scripts/predict_day.py --days 40`)

Two more predictors: F adds the accumulated difference in sunlight (that day against the profile's) on each room's windows and roof faces (layout from `scripts/solar_windows.py`: 12:12 roof, house rotated 10.4 degrees); G does the same with a fixed horizon that cuts the beam below 18 degrees of sun height for sun between 120 and 210 degrees of azimuth (the south-east to south block from `scripts/horizon_profile.py`). Sunlight is the measured value standing in for a forecast, and the thermostat setpoint is deliberately not an input: it is what this prediction is meant to produce (17), and feeding it back in would make the prediction partly predict itself.

Mean RMSE (C), rooms with a window layout (kitchen, master, W bedroom, office thermostat, S basement, N bedroom, NE, SE basement and the office sensors):

| Predictor | all 11 rooms | hours 0-5 | hours 6-23 |
|---|---|---|---|
| D profile + offset | 0.425 | 0.218 | 0.475 |
| E + outdoor | 0.418 | 0.199 | 0.470 |
| F + sun, unshaded | 0.427 | 0.198 | 0.478 |
| G + sun, shaded | 0.424 | 0.199 | 0.472 |

- The sun terms do not improve the forecast on average (0.418 for E, 0.427 for F, 0.424 for G); shading recovers part of what the unshaded light loses but does not beat E.
- By room: the kitchen improves (0.60 to 0.58), the master slightly (0.35 to 0.34), and the Z4 office thermostat with the shaded light (0.42 to 0.40); the NE basement (0.51 to 0.57), S basement (0.28 to 0.32) and the office sensors (0.52 to 0.54-0.56) get worse. Two more regression coefficients fit on 3 to 30 earlier days overfit in the rooms with the least sun and the fewest days.
- The early test days have the fewest training days and the longest list of coefficients to fit; as in the solar test (11), 40 days in late October to early November, mostly cloudy and with the sun never above 25 degrees, is too little sun signal for the 6 to 23 hour range, where the error stays near 0.47 C.
- Next: pool the sun coefficient across rooms (one gain per unit of light and per room-size class) instead of fitting each room, re-run in spring when the sun is higher, and try the furnace duty cycle forecast as an input once the control hypothesis (17) can supply it.
