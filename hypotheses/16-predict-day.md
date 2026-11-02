# 16 Predict next-day house/room temperature

**Status:** revised after reading ClimateAdvisor; zone model with a simulated thermostat built and backtested (does not yet beat the profile with offset); live forecasts now logged as issued

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


## Revised hypothesis (after ClimateAdvisor, 2 November 2026)

[ClimateAdvisor](https://github.com/gunkl/ClimateAdvisor) forecasts a whole house with one first-order model, `dT/dt = k (T - T_out) + Q_hvac + k_solar * solar_factor(hour)`, with the thermostat in the loop: the heater runs at a learned rate below the setpoint and the path is capped at it. Its physics is simpler than ours (one node, a clock-hour sine for the sun). What it adds is how the model is fitted, the thermostat inside the forecast, and logging forecasts as issued and scoring them. So the claim is now:

**Claim:** Each zone's next 24 hours are predicted by its own first-order model (envelope `a`, ground `b`, sun `g` and `w`, constant `c`), driven by the outdoor forecast as issued and the thermostat's program, with the thermostat simulated as an on/off heater (heating rate `h` learned from the calls; heat below the setpoint minus a deadband, off at the setpoint). It is fitted on rates over hour-long blocks, refined on 3 hour simulated paths, and scored live against its own logged forecasts at 1, 3 and 6 hours. **Target:** beat predictor D/E (0.47 C over hours 6 to 23), keeping hours 0 to 5 at 0.20 to 0.30 C.

**Built** (integration): exact exponential steps (`shadow.step`), the simulated thermostat (`shadow.simulate_heated`), block fits with sign and range checks, the multi-step refinement, the heating rate and the wall lag learned from history, and a grade per fit (`learn.py`); the outdoor forecast's bias against the sensor (`scoring.py`); a forecast sensor per zone whose recorded history is the archive of forecasts as issued and that scores itself every 6 hours; the target wave (`target.py`); and the Thermal Lab panel.

### First backtest (`scripts/predict_rc.py --days 14`)

Rolling origin at local midnight (America/Regina) of test days 4 to 13, 14 days to 2026-11-02, 15 minute bins from 5-minute statistics, fits on the 7 days before each midnight, deadband 0.1 C. Weather measured, standing in for a perfect forecast. RMSE (C) over the day, mean over zones (z1 to z4, the zone's room) and test days:

| Predictor | all | hours 0-5 | hours 6-23 | n |
|---|---|---|---|---|
| A persistence | 0.82 | 0.96 | 0.74 | 40 |
| C profile | 0.48 | 0.35 | 0.50 | 40 |
| D profile + offset | 0.47 | 0.30 | 0.50 | 40 |
| R1 zone model, one-step fit, thermostat | 0.83 | 0.70 | 0.84 | 39 |
| R4 same, hour-block fit | 0.92 | 0.74 | 0.95 | 39 |
| RM same, refined on 3 h paths | 0.93 | 0.74 | 0.95 | 39 |
| RM, setpoint at midnight held | 1.49 | 0.74 | 1.62 | 39 |
| RM, yesterday's setpoints repeated | 0.62 | 0.61 | 0.60 | 14 |

By zone (whole day): z4 office D 0.33, R1 0.44, R4 0.44, RM 0.46, RM with yesterday's program 0.47, RM held 2.93; z2 basement D 0.43, RM 0.84; z3 master D 0.52, RM 0.70; z1 kitchen D 0.59, RM 1.67.

- **Refuted for now:** the zone model with a simulated thermostat does not beat the profile with offset in any zone. Even in z4, the one zone whose fit is physical (a = 0.031 per hour, c 0.38 C/h, g 0.0027), it is 0.44 to 0.46 C against 0.33.
- z1, z2 and z3 fit with the wrong sign (a from -0.010 to -0.055): the room "warms toward a colder outdoors". Their thermostats are off (z1, z3) or their calls are short and few (z2), so they are driven by the rest of the house, which a one-zone model cannot see. The integration now refuses such fits (`problem: wrong sign`) instead of forecasting with them; the backtest still simulates them, which is why the R rows are so poor on average.
- Hour-long blocks and the multi-step refinement did not help here (0.83 to 0.93 on average; 0.44 to 0.46 in z4). With 7 training days there are only a few hundred idle hours, and the error is dominated by what the model lacks (other zones, people, the furnace's lag and overshoot) rather than by the thermostat's 0.1 C steps.
- **The program matters most.** Holding the midnight setpoint all day cost z4 2.9 C (it has a night setback). Repeating yesterday's setpoints came within 0.02 C of knowing the day's own (0.47 against 0.46), so the forecast sensor does that.
- Next: (1) the live scores (`error_1h`, `error_3h`, `error_6h` on the forecast sensor) over the coming weeks, which test forecasts as issued for the first time; (2) a coupled multi-zone model (the crossover terms of 06 and the room network of 10) so z1 to z3 get a physical fit; (3) the furnace's start lag and overshoot (13) in the simulated thermostat; (4) a hybrid that takes D's profile for the shape and the model only for the departures from it (weather, setpoint changes).
