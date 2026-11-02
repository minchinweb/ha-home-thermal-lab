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
| [03](03-ground-temperature.md) | Ground temperature follows a damped, lagged wave of air temperature | B. Characterise house | untested |
| [04](04-envelope-flux.md) | Heat flux through the envelope from inside and outside (or ground) temperatures | B | untested |
| [05](05-furnace-power.md) | Furnace heating power from room gradient | B. Characterise house | untested |
| [06](06-crossover-bleed.md) | Heat crosses over between zones during a call (strongest into the kitchen) | B | in progress |
| [07](07-ac-power.md) | AC cooling power from room gradient | B | untested |
| [08](08-fan-flux.md) | Heat flux of running the furnace fan | B | untested |
| [09](09-door-state.md) | Door open/closed from inter-room gradients | B | untested |
| [10](10-static-flux.md) | Static heat flux between rooms/floors | B | untested |
| [11](11-solar-gain.md) | Predict room solar gain | C. Disturbances | untested |
| [12](12-wind-loss.md) | Predict heat loss from wind speed/direction | C | untested |
| [13](13-thermal-momentum.md) | Measure the house's thermal momentum (inertia, time constant) | B | untested |
| [14](14-electrical-heat.md) | Electrical use becomes indoor heat | B | untested |
| [15](15-occupancy.md) | Occupancy from room temperature changes | B | untested |
| [16](16-predict-day.md) | Predict next-day house/room temperature | D. Predict and control | untested |
| [17](17-control.md) | Decide whether to run furnace/AC to avoid overshoot | D | untested |

## Dependency order

A (1, 2) feeds back into the wave component. B and C produce the parameters
for a grey-box RC thermal model. D (16, 17) uses that model plus a weather
forecast, and only makes sense once B and C hold up.

## Cross-cutting notes

- Home Assistant's recorder keeps about 10 days of detail; long-term
  statistics are hourly. Fitting at 5-minute resolution needs the component
  to snapshot its own data, or a longer `purge_keep_days`.
- Zoning valves leak into non-calling zones, so "off" is not zero flow.
  Model spillover as a fitted parameter.
- Furnace, fan, solar gain and occupants all act at once. Pick clean windows
  (e.g. overnight, one actor changing) to isolate effects.
- The zone board upstream of the thermostats means a zone's call starts the equipment for every zone (see 05). Treat calls as whole-house events, and per-zone calls as requests.
- The "Home Performance" integration publishes its own per-room heating-active flags, window-open sensors and daily estimated energy. Use it as a cross-check on our results for 05, 10 and 13; it is not an input.
- AC and oven are not individually metered, so they are unexplained terms
  in the electrical-to-heat balance (#14).

## Zone map (this house)

Which room sensors belong to which zone (from the owner, checked against the first regression, where each room responds most to its own zone's calls):

| Zone | Rooms and sensors |
|---|---|
| z1 | Kitchen (`sensor.z1_temperature`) |
| z2 | Basement (`sensor.z2_temperature`), NE and SE basement bedrooms, the S basement bedroom |
| z3 | Master bedroom (`sensor.z3_temperature`), the N bedroom, upstairs bathroom |
| z4 | Office (`sensor.z4_temperature`), the office sensor, the office air-quality sensor, the W bedroom |

the W bedroom also has its own thermostat (`climate.w_bedroom_thermostat`), separate from the four-zone board.

