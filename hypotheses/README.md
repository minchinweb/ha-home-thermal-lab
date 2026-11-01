# Hypotheses

Each file states one claim, the data needed, the method, and a result log.
Status values: `untested`, `in progress`, `supported`, `refuted`, `revised`.

The experiments are meant to be run by the `house_thermal_lab` custom
component (`custom_components/house_thermal_lab/`), using data already in
Home Assistant, so they can be re-run later or by others.

| # | Hypothesis | Stage | Status |
|---|---|---|---|
| [01](01-sine-wave.md) | Daily temperature is roughly sinusoidal | A. Validate the wave | in progress |
| [02](02-solar-noon-peak.md) | Peak at solar noon, trough at solar midnight | A | in progress |
| [03](03-furnace-power.md) | Furnace heating power from room gradient | B. Characterise house | untested |
| [04](04-ac-power.md) | AC cooling power from room gradient | B | untested |
| [05](05-fan-flux.md) | Heat flux of running the furnace fan | B | untested |
| [06](06-door-state.md) | Door open/closed from inter-room gradients | B | untested |
| [07](07-static-flux.md) | Static heat flux between rooms/floors | B | untested |
| [08](08-solar-gain.md) | Predict room solar gain | C. Disturbances | untested |
| [09](09-wind-loss.md) | Predict heat loss from wind speed/direction | C | untested |
| [10](10-electrical-heat.md) | Electrical use becomes indoor heat | B | untested |
| [11](11-occupancy.md) | Occupancy from room temperature changes | B | untested |
| [12](12-predict-day.md) | Predict next-day house/room temperature | D. Predict and control | untested |
| [13](13-control.md) | Decide whether to run furnace/AC to avoid overshoot | D | untested |

## Dependency order

A (1, 2) feeds back into the wave component. B and C produce the parameters
for a grey-box RC thermal model. D (12, 13) uses that model plus a weather
forecast, and only makes sense once B and C hold up.

## Cross-cutting notes

- Home Assistant's recorder keeps about 10 days of detail; long-term
  statistics are hourly. Fitting at 5-minute resolution needs the component
  to snapshot its own data, or a longer `purge_keep_days`.
- Zoning valves leak into non-calling zones, so "off" is not zero flow.
  Model spillover as a fitted parameter.
- Furnace, fan, solar gain and occupants all act at once. Pick clean windows
  (e.g. overnight, one actor changing) to isolate effects.
- AC and oven are not individually metered, so they are unexplained terms
  in the electrical-to-heat balance (#10).
