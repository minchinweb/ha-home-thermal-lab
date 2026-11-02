# 16 Predict next-day house/room temperature

**Status:** first backtest run; beats naive baselines by a small margin

**Claim:** With the fitted factors (B, C) and a weather forecast, we can predict each room's temperature for the coming day.

**Data:** Fitted thermal model, weather forecast (temperature, cloud, wind), planned furnace/AC schedule, expected electrical load.

**Method:** Simulate the RC model forward 24 h. Backtest on historical days using the forecasts that were available at the time. Report per-room error against a naive baseline (persistence, or the wave component alone).

## Results

First backtest (`scripts/predict_day.py --days 40`): rolling origin, at local midnight (America/Regina) of every test day predict the 24 hourly room temperatures of the day ahead from earlier data only. Hourly long-term statistics, 40 days to 2026-11-02, test days 10 to 39 (15 to 30 days per room: the Zigbee bedroom sensors have about 20 days of history). Outdoor temperature is the measured value, standing in for a perfect forecast. the office sensor and the office air-quality sensor are one room.

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
