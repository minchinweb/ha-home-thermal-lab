# Hypotheses

Each file states one claim, the data needed, the method, and a result log.
Status values: `untested`, `in progress`, `supported`, `refuted`, `revised`.

The experiments are meant to be run by the `home_thermal_lab` custom
component (`custom_components/home_thermal_lab/`), using data already in
Home Assistant, so they can be re-run later or by others.

| # | Hypothesis | Stage | Status |
|---|---|---|---|
| [01](01-sine-wave.md) | Daily temperature is roughly sinusoidal | A. Validate the wave | in progress: fits within about 1 C; more locations being added |
| [02](02-solar-noon-peak.md) | Peak at solar noon, trough at solar midnight | A | in progress: the peak comes 1-3 h after solar noon |
| [03](03-ground-temperature.md) | Ground temperature follows a damped, lagged wave of air temperature | B. Characterise house | first run: fits the 1.8 m soil roughly (RMSE 1.5 C with an offset) |
| [04](04-envelope-flux.md) | Heat flux through the envelope from inside and outside (or ground) temperatures | B | untested on its own (envelope terms are in 13, 16 and 17) |
| [05](05-furnace-power.md) | Furnace heating power from room gradient | B. Characterise house | in progress: stages, call lengths and rise measured; call statistics sensor |
| [06](06-crossover-bleed.md) | Heat crosses over between zones during a call (strongest into the kitchen) | B | in progress: register airflow measured; the kitchen gets 68-88% of its own flow whichever zone calls, so it is in practice unzoned |
| [07](07-ac-power.md) | AC cooling power from room gradient | B | waiting for the cooling season |
| [08](08-fan-flux.md) | Heat flux of running the furnace fan | B | revised: the blower is never off long enough; no-fan nights running 2-16 Nov |
| [09](09-door-state.md) | Door open/closed from inter-room gradients | B | two runs: too few clean door edges |
| [10](10-static-flux.md) | Static heat flux between rooms/floors | B | revised: no fan-off data; no-fan nights running 2-16 Nov |
| [11](11-solar-gain.md) | Predict room solar gain | C. Disturbances | horizon fits checked against window photos and sizes; with the other zones' calls as terms the windows add little (3% in the kitchen); apertures a tenth to a half of the glass |
| [12](12-wind-loss.md) | Predict heat loss from wind speed/direction | C | first run: no wind effect detectable |
| [13](13-thermal-momentum.md) | Measure the house's thermal momentum (inertia, time constant) | B | in progress: tau about 54 h; furnace lag 6-12 min, overshoot 0.2 C; a delivery lag does not help the 15 min forecast; effective room capacity 80-230 times the air |
| [14](14-electrical-heat.md) | Electrical use becomes indoor heat | B | in progress: blower +0.2 kW when heating; small plug loads not resolvable |
| [15](15-occupancy.md) | Occupancy from room temperature changes | B | three runs: the office signal is the computer, not body heat |
| [16](16-predict-day.md) | Predict next-day house/room temperature | D. Predict and control | hybrid (profile plus the coupled zone model's departures) beats profile plus offset: 0.44 against 0.46 C over the day, 0.19 against 0.27 C over hours 0-5; live forecast uses it |
| [17](17-control.md) | Decide whether to run furnace/AC to avoid overshoot | D | shadow mode; sensors ready, not yet deployed |
| [18](18-shower-heat.md) | Showers from bathroom humidity, and their heat | C | first run: showers detected; heat into the house not measurable |

## Dependency order

A (1, 2) feeds back into the wave component. B and C produce the parameters
for a grey-box RC thermal model. D (16, 17) uses that model plus a weather
forecast, and only makes sense once B and C hold up.

## Cross-cutting notes

- Home Assistant's recorder keeps state history and 5-minute statistics for
  `purge_keep_days`: 10 days until 1 November 2026, now 60 (checked on 2
  November: nothing before 22 October was purged overnight, so the setting
  is live; the full 60 days will be there from about 21 December). Long-term
  statistics are hourly and kept indefinitely.
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

The W bedroom has a thermostat (`climate.w_bedroom_thermostat`), but it is non-functional and only used as a convenient way to measure the temperature there.

