# 12 Predict next-day house/room temperature

**Status:** untested

**Claim:** With the fitted factors (B, C) and a weather forecast, we can predict each room's temperature for the coming day.

**Data:** Fitted thermal model, weather forecast (temperature, cloud, wind), planned furnace/AC schedule, expected electrical load.

**Method:** Simulate the RC model forward 24 h. Backtest on historical days using the forecasts that were available at the time. Report per-room error against a naive baseline (persistence, or the wave component alone).

## Results

_none yet_
