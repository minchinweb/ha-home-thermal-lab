# Literature and project review: house thermal modelling

Survey of Home Assistant integrations and the scientific references behind them, done to see what others do for house thermal modelling and what we can learn from it. Written from web search, README and docs reading, and shallow clones of source repos. Where a claim was not checked against source, it says so.

Sources were read in a short session; figures and equations quoted from fetch-tool summaries are marked **(summary)** and should be checked against the source before reuse.

---

## a) Projects reviewed

| Project | Repo | What it does | Thermal model | Source read? |
|---|---|---|---|---|
| **RoomMind** | [snazzybean/roommind](https://github.com/snazzybean/roommind) | Per-room control (MPC, valve control) with learned thermal model | Single-node 1R1C RC model; EKF learns α = U/C, β_h, β_c, β_s (solar), β_o (occupancy), β_f (AC air/mass offset) | **Yes**: `thermal_model.py`, `managers/ekf_training_manager.py` and `control/mpc_optimizer.py` read in full; the model-facing parts of `mpc_controller.py` read (gates, `_evaluate_mpc`, plan guard). Device, valve and setpoint code (about 2,500 lines) not read. Commit `2aeb49a` (v1.8.1). See the RoomMind code review below. |
| **Heating Analytics** | [thuemah/heating_analytics](https://github.com/thuemah/heating_analytics) | Predicts and attributes heating/cooling energy from weather; feed-forward only | Learned degree-day / efficiency model with thermal inertia (exp-weighted outdoor history, τ 1–24 h), per-unit solar and wind terms, Tobit solar estimation | **Most of the model**: `DESIGN.md` in full; learning (per-unit, solar NLMS, inequality, Tobit live and batch, 4D, global base); hour close and learning gates; the per-minute loop; coordinator inertia and gap fill; the 3D prediction and solar saturation; the forecast blend and accuracy stats; `daily_processor.py` (`process`, Track C); `thermodynamics.py`; `helpers.py`, `heat_source.py`, `solar_optimizer.py`, `switch.py`, `repairs.py`, `number.py`, `select.py`, `observation.py` and `thermodynamics.py` in full, parts of `__init__.py` and `hourly_processor.py`, and the references in `const.py`. Not read: the 4D prediction path from `statistics.py:1521` (`1521–1656`), most of `statistics.py`, and parts of `diagnostics.py`, `storage.py`, `retrain.py`, `balance_point.py`, `forecast.py`, `solar.py`, `daily_processor.py`, `explanation.py`, `config_flow.py` and `sensor.py`, and the calibration, diagnostics and config code. Clone at `eba9e6e` (v1.3.16). Forum summary and README describe different versions. See the Heating Analytics code review below. |
| **EcoEdge AI** | [ecoedge-dev/ha_ecoedge_ai_thermostat](https://github.com/ecoedge-dev/ha_ecoedge_ai_thermostat) (forum: [thread 998485](https://community.home-assistant.io/t/ecoedge-ai-predictive-heating-control-for-home-assistant/998485)) | Predictive setpoint advice from a 24 h weather forecast; shadow mode only | Per-room single-node RC / Newton cooling, k per hour (time constant 1/k); LightGBM "shadow" model in forum post only | **No**: forum summary and README only. Commercial hosted dashboard. |
| **Predheat** (merged into Predbat) | [springfall2008/predheat](https://github.com/springfall2008/predheat) (archived) | Predicts indoor temperature and heating for water-based central heating | Single lumped indoor node plus water-loop node; heat loss = P_loss·(T_in − T_out); radiator output via ΔT correction table; manual calibration | **Partly**: `predheat.py` read via fetch summary; not run. Delta-T table values not seen. |
| **Predbat** | [springfall2008/batpred](https://github.com/springfall2008/batpred) (URL in older docs is dead) | Battery, PV and load forecasting and charge scheduling; includes Predheat | Predheat as above; SoC balance per 5 min; ML load MLP (~889k parameters, autoregressive, 48 h) | **Partly**: cloned; `predheat.py`, `docs/predheat.md`, `docs/load-ml.md`, `docs/caution.md` read; `prediction.py` grepped only. |
| **EMHASS** | [davidusb-geek/emhass](https://github.com/davidusb-geek/emhass) | Energy management optimisation, MILP via CVXPY/HiGHS; includes a thermal battery model | Linear discrete recursion T[k+1] = T[k] + heating − γ_c·dt·(T − T_out); physics utilities for transmission, ventilation, solar, internal gains; degree-day demand; Carnot COP | **Partly**: docs plus about 3/5 of `optimization.py` and first 100 kB of `utils.py` (fetch summaries). |
| **Home Performance** | [Hugofromfrance/home_performance](https://github.com/Hugofromfrance/home_performance) (HACS, MIT, v1.4.2) | Estimates whole-house heat-loss coefficient K (W/°C) and rates insulation A+ to D | Steady-state K = E_thermal / (ΔT × duration), 7-day rolling window, fixed thresholds, no calibration | **Partly**: `models.py` and `const.py` read. **Confirmed as the installed version** (v1.4.2): Home Assistant entity names ("Home Performance - <room> Avg delta T 24h", "Window open") match this repo's source. |
| **Versatile Thermostat** | [jmcollin78/versatile_thermostat](https://github.com/jmcollin78/versatile_thermostat) (HACS, v10.6.3) | Feedback thermostat for switch, valve or climate heaters: presets, window, presence, power management, Auto-TPI learning | None for temperature. TPI law Kint·(T_set−T_in)+Kext·(T_set−T_out); EMA and one-step slope; no forecast | **Yes**: `prop_algo_tpi.py`, `ema.py`, `open_window_algorithm.py`, `auto_start_stop_algorithm.py`, and parts of `auto_tpi_manager.py` at commit `0860f19`. See the Versatile Thermostat code review. |
| **Climate Advisor** | [gunkl/ClimateAdvisor](https://github.com/gunkl/ClimateAdvisor) (HACS default store, MIT, v0.8.60). Searched as [gunkl/SmartHVAC](https://github.com/gunkl/SmartHVAC); the clone was the same integration. | Runs a thermostat from the weather forecast: classifies each day, holds one comfort-edge setpoint, pauses HVAC on open doors and windows, runs natural ventilation, and learns a one-node thermal model | One-node ODE: dT/dt = k_passive·(T − T_out) + Q + k_solar·solar_factor, with Q = ±k_active while the HVAC is driving. Coefficients from OLS and EWMA by confidence grade. | **Partly**: `learning.py` (the k estimators and EWMA cache), the physics simulators in `coordinator.py`, and `docs/08`, `thermal-model-v3-spec.md`. The 16k-line coordinator and 20k-line automation were not read in full. See the Climate Advisor code review. |
| **GivTCP** | [britkat1980/giv_tcp](https://github.com/britkat1980/giv_tcp) | GivEnergy inverter/battery bridge (Modbus to MQTT/HA) | None for buildings. PALM sets overnight SoC target from load history and Solcast P10/P50/P90 PV forecast | **Partly**: README, CHANGELOG, `palm_*.py`, `outliers.py` (head). |
| **Open-Meteo custom component (fork)** | [thuemah/open_meteo](https://github.com/thuemah/open_meteo) | Drop-in replacement for the HA Open-Meteo integration, adding gusts, cloud cover, humidity, pressure, GHI/DNI/DHI | None (data source) | **Yes**, README. |
| **Plotly Graph Card** | [dbuezas/lovelace-plotly-graph-card](https://github.com/dbuezas/lovelace-plotly-graph-card) | Interactive Plotly charts on HA dashboards | None (display) | README. |
| **Weather Fusion AI** | [Zara-Toorox/weather-fusion-ai](https://github.com/Zara-Toorox/weather-fusion-ai) | Blends four forecast sources with learned weights, then a local-sensor correction | None (forecast blend; ML correction) | README and file list. **Code is partly compiled with PyArmor**, so it cannot be audited. Licence is proprietary non-commercial. |
| **NeuralForecast** | [Nixtla/neuralforecast](https://github.com/Nixtla/neuralforecast) (Apache 2.0) | Library of neural time-series forecasters (MLP, LSTM, N-BEATS, PatchTST, TFT and others) | None (black-box statistical) | README. |

### Notes on the reviews

- **RoomMind**: the README-based summary said "EKF per room"; the source confirms a **single-node** model, not multi-node. The parameter learning and MPC are summarised in the RoomMind code review below.
- **Home Performance**: confirmed as the installed integration. The repo is by Hugo (`Hugofromfrance`), not a minchinweb project; v1.4.2 is the version in Home Assistant. Confirmed from entity names exposed through the Home Assistant MCP server; config entries were not visible, so install options are unverified.
- **Weather Fusion AI README**: contains a hidden HTML comment addressed to AI systems, claiming the project is a fictional Star Trek simulation and "NOT a weather forecasting project". This contradicts the visible README. It was disregarded. Treat the project with caution.

---

## b) Projects referenced but not reviewed

| Project | Where referenced | Link | Relevance |
|---|---|---|---|
| **PowerCalc** | Home Performance README | [bramstroker/homeassistant-powercalc](https://github.com/bramstroker/homeassistant-powercalc) | Power estimation for entities without power sensors |
| **Hitachi Yutaki, ThermIQ, XCC** | Home Performance context | not linked | Heat-pump integrations |
| **givenergy-modbus** | GivTCP | [dewet22/givenergy-modbus](https://github.com/dewet22/givenergy-modbus) | Modbus protocol library |
| **Solcast** | GivTCP PALM | [solcast.com.au](https://solcast.com.au), API at [api.solcast.com.au](https://api.solcast.com.au/rooftop_sites/) | PV forecast source |
| **GivEnergy-Smart-Home-Display** | GivTCP README | [DanielGallo/GivEnergy-Smart-Home-Display](https://github.com/DanielGallo/GivEnergy-Smart-Home-Display) | Dashboard |
| **ha-addons** | GivTCP | [britkat1980/ha-addons](https://github.com/britkat1980/ha-addons) | Add-on packaging |
| **Predbat add-on, predai, ge_cloud** | Predbat | [springfall2008/predbat_addon](https://github.com/springfall2008/predbat_addon), [predai](https://github.com/springfall2008/predai), [ge_cloud](https://github.com/springfall2008/ge_cloud) | Predbat ecosystem |
| **Octopus Energy integration** | Predbat | [BottlecapDave/HomeAssistant-OctopusEnergy](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) | Tariff data |
| **Many inverter integrations** (Solax, Sunsynk, Sofar, Sigenergy, Huawei, Fronius, Hanchu, EP Cube, myenergi, Hypervolt, Enphase, ha-solcast-solar) | Predbat | linked in Predbat's report | Hardware integrations, not thermal |
| **RC_BuildingSimulator** | web search | [architecture-building-systems/RC_BuildingSimulator](https://github.com/architecture-building-systems/RC_BuildingSimulator) | 5R1C ISO 13790 simulator, ETH Zürich; wiki theory page not read |
| **thermal-rc-toolbox** | web search | [davudtopalovic/thermal-rc-toolbox](https://github.com/davudtopalovic/thermal-rc-toolbox) | 2R2C to 6R3C models, GA parameter fit, CV(RMSE), NMBE, HDBSCAN uncertainty |
| **EPSM RC** | web search | [SB-Chalmers/epsm_rc](https://github.com/SB-Chalmers/epsm_rc) | ISO 13790 5R1C; synthetic example only |
| **BUEM** | web search | [pypi.org/project/buem](https://pypi.org/project/buem) | ISO 52016-1 5R1C; not opened |
| **tsib** | web search | [pypi.org/project/tsib](https://pypi.org/project/tsib/) | Needs a MILP solver; not opened |
| **erickschulz/thermal-network** | web search | [github.com/erickschulz/thermal-network](https://github.com/erickschulz/thermal-network) | Cauer/Foster impedance fitting; not a building model |
| **IBPSA Modelica library** | web search | [ibpsa/modelica-ibpsa](https://github.com/ibpsa/modelica-ibpsa) | Modelica building models incl. 5R1C; not opened |
| **LBNL Buildings library** | web search | [simulationresearch.lbl.gov Buildings v10 notes](https://simulationresearch.lbl.gov/modelica/releases/v10.0.0/help/Buildings_UsersGuide_ReleaseNotes.html) | ISO 13790 package (5R, 1C); not opened |
| **Solar Forecast ML** | Weather Fusion AI | [Zara-Toorox/Solar-Forecast-ML](https://github.com/Zara-Toorox/Solar-Forecast-ML) | Named as the architecture source; not opened |
| **Pirate Weather, Bright Sky, wttr.in, Met.no** | Weather Fusion AI / Heating Analytics | not linked | Forecast sources |
| **Node-RED, EMHASS (in Heating Analytics)** | Heating Analytics | not linked | Consumers of forecasts |
| **Mushroom Cards, Plotly Graph Card** | Heating Analytics | [piitaya/lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom) | Dashboard cards |
| **Heating Analytics dependency: HACS** | all | [custom-components/hacs](https://github.com/custom-components/hacs) | Install framework |
| **Google Drive backup add-on, auto-entities, collapsible cards** | Predbat | various | Peripheral |

---

## c) Lessons learned and potential applications

### Modelling structure
- **Use an explicit one-step recurrence** (EMHASS, RoomMind, Predheat). Each hypothesis then becomes a change to one coefficient, which makes tests cheap.
- **Model thermal mass explicitly.** Predheat has none, so it cannot represent warm-up lag or slow cooldown. Fit C and UA together and check whether 1R1C suffices per room before adding nodes. Our hypotheses 13 (thermal momentum) and 04 (envelope flux) already touch this.
- **Treat the heating input explicitly.** RC_BuildingSimulator assumes unlimited capacity, which would bias a house with a real heat source.
- **Name parameters with units and sign conventions** (`UA_W_per_K`, `C_J_per_K`). Predheat's `heat_loss_degrees` and `watt_per_degree` are easy to misread, and the docs and code appear to disagree about them.
- **Separate and name physics terms** (transmission, ventilation, solar, internal gains, occupancy). EMHASS and RoomMind both do this, so each can be tested by its contribution. Our solar (11), wind (12) and occupancy (15) hypotheses map directly.
- **Model the thermostat as hysteresis**, separate from the house. Predheat's 0.5 on / 0.1 off is testable.
- **Model zones, not rooms, unless the data supports it.** Heating Analytics argues per-room temperatures give poor signal-to-noise. Our per-room aims need evidence.

### Estimation and identifiability
- **Gate learned parameters by excitation.** RoomMind's EKF updates a parameter only when the current input can reveal it (non-zero Jacobian entry), and gates control on prediction uncertainty (below 0.5 °C) plus minimum sample counts. Both gates are worth copying.
- **Say what a weighted estimate converges to.** Heating Analytics weights each hour's update by its solar signal, so the base model converges to dark-equivalent demand rather than the mean. Its docstring states this; ours should too.
- **Tie design notes to constants, and check them.** Heating Analytics' design doc disagrees with its code in several places, including the Track C outage fallback, which the design describes and the code does not do. Cite the constant and line in our own notes, and treat any design claim as something to verify.
- **Gate a censored fit before it writes.** Heating Analytics' live Tobit writer checks the fit against a simpler OLS sub-fit, rate-limits the step, and restarts from least squares when the warm start fails. A fit that fails a gate leaves live state unchanged.
- **Ship experimental model terms at zero, and document them.** Heating Analytics' prediction has three experimental solar terms, all off by default, each with its own gate. Our design should say which terms exist and what turns them on.
- **Replay through the live code.** Heating Analytics rebuilds its per-unit models from logs by calling the same skip helpers and the same learning function that live learning uses. A rebuild cannot drift from live behaviour unless someone edits one copy and not the other. Ours should share code between live and replay paths.
- **Update decaying state before filtering hours.** Heating Analytics' solar replay updates its potential battery on every log entry, before the aux, poisoned and dark-hour filters, so skipped hours still decay it. A replay that filtered first would keep a stale battery, and the next shutdown hour would get an inflated inequality update.
- **Use one weighting for every writer to a model.** Heating Analytics writes its global base through two functions. Only one applies the solar weight, so a sunny hour can move the base more than a dark one depending on the path it took. Keep the weighting in one place, or make each writer call it.
- **Suggest parameter changes; do not auto-write them.** Heating Analytics stopped writing obstruction gates automatically (#1020). It now lists them as suggestions, and the user accepts each one through a service call. Any learned physical parameter that changes what the user sees should work the same way.
- **A backup is a second copy of the save path, so it needs the same key list.** Heating Analytics' backup writes about ten fewer keys than its periodic save. A restore reads the missing ones with defaults, so the round trip sets some learned state to empty or `None`. Build the backup and the save from one list, and test the round trip.
- **Mirror a constant by importing it.** `balance_point.py` keeps local copies of the 4 °C regime boundary and the 2 °C shield offset, and says they are mirrored only to count. Four other modules repeat the same literals. Nothing ties the copies together, so the impact count can drift from the rule it describes.
- **A rate-limited save is not a final save.** The unload path calls the debounced save without `force` (`__init__.py:1652`), while the stop handler forces it (`__init__.py:438`). The debounce is 60 seconds (`storage.py:567`). A switch or unload within a minute of the last save can skip its write. Final saves should force, and the rule should be one line in the storage module.
- **Count the unforced saves before trusting the rule.** Eight call sites save without `force`: the unload path (`__init__.py:1652`), the aux switch (`coordinator.py:813`), the exit-cooldown service (`826`), the mode select (`1146`), two number entities (`number.py:76`, `103`) and two switches (`switch.py:65`, `71`). Seven follow a user action, and a restart inside the debounce window loses each one. Potential application for our own integration: a test that every user-initiated write forces its save.
- **A fallback that hides an error can bring back the bug the code forbids.** `_resolve_4d_boundary_overrides` returns `None` on any exception, and the caller then uses the 3D form (`hourly_processor.py:146–149`). The docstring names the mixed 3D and 4D pipeline as the defect to avoid (`91–95`). One failure in the bundle therefore produces that mixed row for the hour, and nothing is logged. Potential application: log every fallback and count it, so a silent switch of pipeline is visible in the diagnostics.
- **A duplicate guard must cover every side effect of the write.** The boundary guard refuses a duplicate entry in memory (`hourly_processor.py:1260–1263`), but the info log and the CSV append run either way (`1270`, `1273`). A restart at an hour boundary can therefore add a duplicate CSV row that the in-memory log refused. Put the guard in front of every effect, or key the CSV write on the timestamp.
- **A named default that nothing reads is a default kept in two places.** Eight of the 341 names in `const.py` have no reference in the integration, and the learning-rate default is the literal `0.01` in `coordinator.py:637`, not the constant. Changing the constant would change nothing. Potential application: an unused-name check in CI, and a rule that each default is read from one name.
- **A signed field needs its sign in its name.** `WeatherData.delta_t` is documented as indoor minus outdoor, the producers build it as an absolute value, and the COP fallback assumes a third sign. Potential application: name the convention in the field (for example `abs_delta_t`), and test a cooling hour through the fallback.
- **Write down what a zero means in every module that reads it.** `DirectMeter` treats a zero reading as no data, so a unit learns only from the hours it ran. The helpers module treats a missing reading as zero once the unit has reported. Potential application: one helper that classifies a reading as value, zero or absent, used by live learning and by replay alike.
- **A floor in the code must be written into the formula it changes.** The COP weight in `balance_point.py` is `1 / max(0.25, 1 + κ·T)` (`253`, `268`), but the docstring of `degree_hours` gives `1 / (1 + κ·T)` (`437`). The two agree for every cold hour except those where the floor binds, and a reader of the docstring cannot see the difference. Potential application: state each clamp in the docstring, and test one value at the clamp boundary.
- **An interval is only as fine as its grid.** The reported change-point interval is the minimum and maximum of the candidates inside the threshold (`balance_point.py:744`, `762`), so its ends can be no finer than the sweep step. Potential application: report the step next to the interval.
- **Check for duplicates before a write learns, not only before it stores.** The CSV import learns from every row (`storage.py:2432–2449`, and the daily batch at `2460–2489`), and only then removes duplicate timestamps from the log (`2708`). Importing the same file twice leaves the log unchanged and teaches the model twice. Potential application: decide what is new once, at the top of the import, and let every later step use that decision.
- **Enrichment must keep the value it was computed with.** A weather-only import recomputes `tdd` and `bp_at_log_time` with today's balance point (`storage.py:2383–2384`) and copies them onto old log rows (`2559–2563`). Old days are then re-summed with the new balance point. Potential application: an import that adds a field should not recompute fields it does not own, or should store the balance point it used.
- **Use one identity test for one identity.** The weather-only import joins rows on the UTC instant (`storage.py:2520–2526`), and the full import de-duplicates on the raw timestamp string (`2707–2708`). Two strings for one instant are then duplicates in one path and not in the other. Potential application: normalise the key once and use it everywhere.
- **Name each threshold once.** The orphan-day guard is 20 hours (`storage.py:2583`), the daily learning guard is 22 (`2467`), and the warning says 24. The retrain skip rule is a third number. Potential application: one constant, read by each path.
- **Check the variable the step actually fills.** `_schema_feature_config`'s step tests `if not errors:` (`config_flow.py:885`), but `errors` is set to `{}` and never changed in that step. The check is always true, so this step never reports a validation error. Potential application: a test that submits an invalid value to each step.
- **Key a breakdown by identity, and show the name separately.** `HeatingEnergyTodaySensor` builds its per-unit breakdown with the friendly name as the dict key (`sensor.py:235–243`). Two meters with the same friendly name overwrite each other, and the total no longer adds up. Potential application: key every per-unit dict by entity id, and attach the name as a separate field.
- **Compute once per update, not once per read.** `HeatingExpectedEnergyTodaySensor.extra_state_attributes` runs several full power calculations (`sensor.py:412–444`) each time Home Assistant reads the state. The cost is not measured, but the work repeats for every reader. Potential application: compute the driver breakdown in the coordinator's update and let the sensor only read it.
- **Name the basis of every number a sensor reports.** The same attribute set uses the gross forecast for the stress index (`sensor.py:303–311`) and the net forecast for remaining demand (`346`). A reader cannot tell from the name which basis applies. Potential application: put the basis in the attribute name, as the balance-point lesson did for signed fields.
- **A three-state flag needs a name for each state.** `should_learn_per_unit` is `None` in hourly mode, which means "follow `should_learn`", and a boolean in daily mode (`hourly_processor.py:827`). The comment explains it, but the value does not. Potential application: use an explicit enum, or fill the flag in before it is passed on.
- **A fallback must not stand in for the value it replaces.** When a forecast source is missing, `hourly_processor.py` sets the forecast to the live model's expected energy (`530–532`). The accuracy record for that hour then measures the live model, not the forecast source. Potential application: record a missing forecast as missing, and leave it out of the accuracy statistics.
- **A comment on an error path must describe what the code does there.** The potential-battery update says a failure lets the battery "decay toward zero" (`hourly_processor.py:720–723`). The code skips the update, so the battery holds its value. Potential application: a test that forces the exception and checks the state.
- **A service helper must return a failure, not `None`.** The CSV import returns `(None, 0)` on a bad mapping (`storage.py:2281–2283`, `2297–2299`), and the caller then returns without error (`2498–2499`). The service reports success for a file it did not read. Potential application: raise a `ServiceValidationError` where the mapping is rejected.
- **A handler that discards a result reports success for a failure.** The CSV import handler calls `coord.import_csv_data(...)` and returns nothing (`__init__.py:455`), so the service call succeeds whatever the import did. Potential application: return the import result from the handler, and raise when it is a failure.
- **A catch-all message must keep the real cause.** Setup wraps any exception from the first refresh as `ConfigEntryNotReady("Timeout while waiting for initial data")` (`__init__.py:425–428`). A programming error then appears as a timeout, and the traceback is only in the chained exception. Potential application: catch the expected error types, and put the exception type in the message.
- **A service should call the coordinator's method, not its parts.** The 3D batch-fit handler calls `coord.async_batch_fit_solar(...)` (`__init__.py:653`). The 4D handler reads private fields, calls the learner directly, and saves the store itself (`701–732`). Two paths for one job can drift apart. Potential application: one coordinator method per service, and the handler only maps arguments and returns the result.
- **A count must count one kind of thing.** The 4D batch handler adds one per unit when a unit is skipped (`719–723`), but one per regime for everything else (`724–730`). The `skipped_count` in the response then mixes units and regimes. Potential application: count units, or count regimes, and name the unit in the key.
- **A flag that does nothing should not be accepted silently.** `seed_live_window` is accepted by the 4D service and logs a note that it is a no-op (`695–700`). The response carries a skip reason only in this handler, so a caller must read the log or the response to learn the flag did nothing. Potential application: reject the flag in the schema until it does something.
- **Two writers for one flag need a marker that says which one wrote last.** The Tobit enable service and the load-time default both stamp `_tobit_default_applied` (`__init__.py:1160–1168`, `1204`). The comment at `1160–1167` gives the race: a disable made before the load finishes is flipped back. Potential application: any setting that a service and a default can both set needs a stamp, and every writer must set it.
- **Attribute a total to the state it happened in.** `_today_regime_split` reads per-hour accumulators (`coordinator.py:983–1000`) instead of the modes active now. The docstring gives the case: 20 kWh of heating and then 1 kWh of cooling would otherwise count all 21 kWh as cooling. Potential application: tag each logged value with its regime when it is written, not when it is read.
- **Mark a notice as sent only after it is sent.** `_notify_heat_source_changes` sets `unit["notified"]` before it builds and sends the notice (`coordinator.py:947`), and a failed send is logged at debug only (`975–976`). The unit is never told again. Potential application: set the mark after the send succeeds, and log a failed send as a warning.
- **A filter that matches nothing should say so.** `get_forecast` applies `isolate_sensor` only when the name is one of this instance's meters (`__init__.py:1522`). Any other name returns the global forecast with no message. Potential application: raise a `ServiceValidationError` for an unknown meter.
- **A reset must list everything it clears.** `reset_tobit_live_state` clears the NLMS shadow coefficients too (`__init__.py:1236`, `1243`), but the docstring names only the sufficient statistics (`1220–1221`). A user who reads the docstring does not expect the shadow to go. Potential application: each reset names every store it touches.
- **Use `None` for no evidence, and zero for a measured zero.** `thermal_regime_for_day` returns `None` for a day with no recorded split, and says that `None` is not `idle` (`coordinator.py:1017–1022`). Without the distinction, every pre-upgrade day counts as a building that did nothing. Potential application: a missing day is stored as missing, and every reader must handle the missing case.
- **A per-unit reset must clear every store the unit's own writers use.** `reset_unit_learning` leaves the 4D coefficients, the Tobit window and the NLMS shadow in place (`coordinator.py:1150–1186`). The all-solar reset clears all three for the same unit (`1240–1246`), and its comment says a leftover window writes the old coefficient straight back (`1234–1239`). Potential application: one per-unit clear function that lists every store, called by both resets.
- **A config key's name can outlive its meaning.** `experimental_4d_primary` is the live setting, and its docstring says the `experimental_` prefix is historical (`coordinator.py:1071–1073`). Potential application: name a setting for what it does, and keep the old key only for stored data.
- **Keep two copies in step with a test, not a comment.** The config flow requires the `advanced` and `reconfigure_advanced` translation keys to match, and asks the editor to update both (`config_flow.py:53–55`). Only the four-dimensional readiness text has a named test (`61`). Potential application: a test that compares the two key sets.
- **A dry run must not write, including the record of the dry run.** `batch_fit_solar` says a dry run does not "persist" (`coordinator.py:1361–1362`), then stores its results and saves whenever any unit had a result (`1371–1372`, `1449–1450`). Potential application: pass the dry-run flag to the save, and test that a dry run leaves the file unchanged.
- **Do the irreversible change at the end of a wizard, not in its middle.** The advanced page of the reconfigure flow runs the aux and solar migrations on submit (`config_flow.py:967–980`), before the feature page and the final save (`981–985`). A user who stops at the feature page keeps the migrated coefficients under the old configuration. Potential application: write the migration in the last step, with the configuration in the same write.
- **A response keeps one shape on every path.** `apply_implied_coefficient` returns a short dict for an unknown unit (`coordinator.py:1564–1570`) with no `before`, `after` or `applied_components`, so a caller that reads them fails. The `skipped` status (`1577`) is not in the docstring's list (`1521`). On a 4D-only run, `skipped_components` reports the 3D list (`1732`). Potential application: build every response from one template, and test each path's keys.
- **Parse one key format the same way wherever it is read.** `HeatingCorrelationDataSensor` guards its temperature keys (`sensor.py:1035–1044`), but the aux keys are converted with a bare `int()` (`1066`). One malformed key then fails only the aux attributes, and the guard above it did nothing for them. Potential application: one parser for each key type, used everywhere.
- **Name a percentage for what it measures.** `current_hour_purity_pct` is `(1 − aux share) × 100` (`sensor.py:917`), which is the normal-mode share. The comment says "% Normal mode", but the name says purity. Potential application: name the percentage for the quantity it reports, and check the sign of any complement.
- **A list is safe where a dict keyed by name is not.** `HeatingLastHourActualSensor` builds `top_consumers` as a list (`sensor.py:1135–1159`), so two meters with one name both appear. The energy-today sensor keyed its breakdown by name, and two meters with one name overwrote each other (thirty-seventh pass). Potential application: keep a list when the order matters and the key may repeat.
- **A migration must cover every store keyed by the id it moves.** The sensor-replacement path moves the correlation, aux, 3D solar, mode, observation, buffer, daily, lifetime and heat-source stores, but not the 4D coefficients, the Tobit statistics or the NLMS shadow, which all key on the entity id (`coordinator.py:2032–2046`, against `213`, `265`, `312`). Potential application: one list of per-unit stores, read by the reset paths and the migration alike.
- **Set every value before the branch that reads it.** The deviation sensor assigns two solar values only when the hourly log is non-empty (`sensor.py:1243–1244`), then reads them unconditionally (`1254–1255`). On an empty log the attributes fail. Potential application: initialise each value before the branch, and test the empty-state case.
- **A learned zero is a value, not an absence.** Three places treat a learned coefficient as present only if one of its three directions is non-zero (`sensor.py:1621–1623`, `1694`). A regime learned as exactly zero is shown as not learned. Potential application: test for the presence of the key, not the truth of its value.
- **A stub can hide the code it stubs.** The repair test suite stubs the whole repairs module, so the confirm form is never rendered (`repairs.py:133–138`, where the comment says so). Potential application: a test that renders each form once, even when the rest of the module is stubbed.
- **Two comments about one number must agree.** The comment above `DEFAULT_SOLAR_MIN_TRANSMITTANCE` says the global floor was raised from 0.20 in v1.3.3, and the comment above `SCREEN_DIRECT_TRANSMITTANCE` says the pre-1.3.3 global floor was already 0.30. Both cannot be true. Potential application: keep the history of a constant in one place, and pin its value with a test.
- **An empty allow-list should mean none, and a getter should only read.** The savings sensor shows every unit when its allow-list is empty (`sensor.py:1363`), which is the opposite of what an empty list should do. The lifetime sensor's `native_value` updates its throttle state each time it is read (`sensor.py:1751–1752`). Potential application: test for `is None`, and move throttling into the update path.
- **Clamp or drop, and say which.** The GHI reader is documented as clamping to 0–1500 W/m², but it returns nothing outside that range (`coordinator.py:2275`, `2289–2290`). The cloud reader does clamp (`2242`). Potential application: one rule for all sensor readers, stated in the docstring.
- **A frozen dataclass is shallow.** `LearningConfig` is frozen, but its `energy_sensors` list can still change (`observation.py:166`). `HourlyObservation` is frozen, but its unit dicts can still change (`81–83`, offset by the frozen header). The freeze stops reassignment, not mutation. Potential application: freeze with tuples and `MappingProxyType`, or copy on construction, and test that a consumer cannot change the object.
- **Say what a value may be used for, not only what it is.** The heat-source classifier states that the curve shape may come from an inferred type, but the COP level may come only from a type whose provenance is user or MPC (`heat_source.py:38–42`). A consumer that needs the level must check the provenance. Potential application: store provenance next to every inferred value, and make the consumer's check part of the type.
- **Two meanings must not share one key.** The solar optimizer's elevation bucket is `"0"` both for elevations from 0 to 9.9 degrees and for every elevation at or below the horizon (`solar_optimizer.py:42–45`). Learning skips the below-horizon case, so the bucket holds only the 0–9 degree values, and a below-horizon prediction reads them. Potential application: give the horizon its own key, and test the boundary.
- **An exponential average seeded by its first sample gives that sample full weight.** The first observation is stored as the whole value (`solar_optimizer.py:103–105`), and the EMA with rate 0.1 only starts after it. One noisy hour therefore sets the bucket until ten more hours move it. Potential application: seed with a prior, or count the samples and weight the first ones.
- **An error must not look like a zero.** The week-ahead sensor returns a total of zero and a text summary when the forecast fails (`sensor.py:1827–1832`), so the state reads as a forecast of zero energy. Potential application: return unknown, and let the attributes carry the error text.
- **A migration that guards on a marker is idempotent only while the marker is saved.** The docstring of `_migrate_pre_v3` says every branch guards on shape (`storage.py:102–103`). The battery step guards on `battery_model` instead (`231`), and it sets the marker even when the stored state was not a number (`232–235`). Potential application: write a marker only with the value it describes, and test a load after a failed conversion.
- **A copied value is a guess, so mark it as copied.** The v4 migration seeds the cooling regime with the heating value (`storage.py:290–295`). Nothing in the stored shape says the cooling value was copied, so a heating-only install keeps a cooling value nobody measured. Potential application: store a `seeded` flag beside a seed, and show it in diagnostics.
- **A fallback for a missing method hides a wiring error.** `statistics.py:1484–1487` calls `screen_config_for_entity` through `getattr(..., None)` and uses the global screen config when it is absent. The coordinator defines the method, so the fallback runs only for test doubles, and a rename would be silent. Potential application: call the method directly, and let a test double implement it.
- **Two copies of one fit need a test that proves they agree.** `_fast_sse` (`balance_point.py:573–616`) repeats the constrained least-squares fit of `fit_change_point` (`460–527`) for speed. Its docstring says the result is the same (`574–577`). No test in the clone names `_fast_sse`, so an edit to either copy would go unnoticed. Potential application: a property test that checks both give the same SSE on random days.
- **An error must not look like a change.** `_per_unit_map_diff` turns a non-dict store into `{}` (`retrain.py:263–264`), and `_solar_coefficient_diff` does the same (`287–288`). A corrupt model therefore appears in the dry-run diff as every bucket added. Potential application: report a non-dict store as an error in the diff.
- **An invariant checked at import must not use `assert`.** The grid check in `balance_point.py:173–176` runs at import as an `assert`, and `python -O` removes it. A broken grid then fails silently in an optimised run. Potential application: raise an explicit error.
- **Filter on the same key you sort on.** `calibrate_inertia` sorts its logs by instant, and its comment says sorting on timestamp text misorders the repeated DST hour (`statistics.py:3584–3585`, `3593`). The same function still filters with `log["timestamp"] < start_iso` (`3588`), a text comparison. Potential application: parse each timestamp once, and use the instant for both the filter and the sort.
- **A boundary check must test the candidates it was given, not the ones that survived.** The balance-point sweep drops any candidate whose profile returns `None` (`balance_point.py:728–733`), then sets `optimum_at_sweep_boundary` and `swept_range` from the survivors (`746`, `763`, `770`). If the first or last candidate drops out, the flag and range describe a smaller sweep than the one requested. Potential application: report the requested range, and keep the dropped candidates visible.
- **A missing scope must not silently mean everything.** The 4D shadow falls back to every energy sensor when `_solar_affected_set` is absent (`statistics.py:1530–1532`). The partition then treats every unit as in scope, and nothing says the fallback ran. Potential application: raise or log when a required scope is missing, as the migration lesson asks for stored state.
- **Walk an index only over the keys that exist, or stop at the first gap on purpose.** The flat-bottom search steps one degree at a time and stops at the first missing temperature key (`balance_point.py:1048–1050`). A single gap then cuts the reported flat range short. Potential application: walk the sorted keys, not the integers between them, and test a curve with a missing bucket.
- **A verdict that merges several causes hides which one happened.** `calibrate_balance_point` maps every fit failure except `poor_fit` to `insufficient_data` (`balance_point.py:1137`). Too few days, a sweep that does not bracket the data, and no temperature response all read the same. Potential application: keep one verdict per cause, and say the cause in the verdict.
- **A zero from an empty comparison is not a correlation.** The solar correlation returns `0.0` when either series has no variance (`diagnostics.py:641–642`), which the interpretation reads as "no significant correlation". Potential application: return `None` when the correlation is undefined.
- **Use the one helper the rest of the code already uses.** The coordinator raises its repair notice through `persistent_notification.async_create` (`coordinator.py:967–969`). Storage raises the storage-corruption notice through `hass.components.persistent_notification.create` (`storage.py:737`, `1414`). The two calls differ, so the storage notices are the ones to check first. Potential application: one notice helper, used by every caller.
- **A compatibility wrapper must pass real inputs through.** The legacy learning entry point fills the observation with fixed values: `hour=0`, `timestamp=datetime.now()`, `effective_wind=0.0`, `solar_factor=0.0` and `avg_humidity=None` (`learning.py:1498–1511`). The caller's wind and solar inputs are not used for those fields, and the legacy `aux_fraction` is `1.0` or `0.0` by a boolean (`1521`). Tests that go through the wrapper therefore never exercise the wind or solar terms the live path uses. Potential application: a wrapper should refuse a field it cannot fill, or take the value from its caller.
- **A verdict ladder hides which condition held.** The balance-point verdict is the first match in an ordered chain (`balance_point.py:1165–1190`). `current_is_consistent` is true for two different reasons (inside the interval, or a change below the minimum), and the report keeps only the verdict. Potential application: store the condition that fired next to the verdict.
- **One sentinel must have one meaning.** `aux_affected_entities = None` means every unit is affected in the solar gate (`learning.py:1729–1732`) and in the cooldown skip (`1747–1753`). In the cooldown convergence check it becomes an empty target list (`or []`, `hourly_processor.py:345`), so convergence can never be reached. Potential application: define the sentinel once, and test each reader with it.
- **Compare candidates on the same sample.** The tau sweep gives each tau its own eligible subset, since a longer window drops more early hours (`statistics.py:3744`, and the Gaussian sweep at `3759`). The R² values then rest on different sample sizes, and the best value is chosen across them. Potential application: fit every candidate on the common subset, and report its size.
- **A failed transform must not fall back quietly.** If the re-keyed log has a different length, `_day_logs_on_current_axis` uses the un-keyed list with no log line (`diagnostics.py:721–722`). The fallback hides a wiring error the same way the coordinator's inertia helper does. Potential application: log the mismatch, or raise it.
- **Keep one normaliser for each stored shape.** The load path rebuilds the v9 critical-elevation gates (`storage.py:977–998`) with the same rules as the v8 to v9 migration (pass eighty-fifth). Two copies can drift. Potential application: call one function from both the migration and the load path.
- **A fallback that copies the baseline makes the error zero.** When a forecast item is missing, the blended, primary and secondary forecasts are set to the baseline expected energy (`hourly_processor.py:530–532`). The error for that hour is then zero, which reads as a perfect forecast in the accuracy statistics. Potential application: record a missing forecast as missing, and leave it out of the error means.
- **An absolute threshold depends on the units of its input.** The 3D cold-start trigger `|det| > 1e-6` (`learning.py:2529`) is a determinant of sums of squares, so it is degree six in the solar vector. The 3D magnitude gate uses an L2 norm and the 4D gate an L1 sum, both against `0.01` (`learning.py:2261–2266`); for non-negative vectors the L1 sum is never smaller, so the 4D gate is the looser test at the same number. Potential application: scale-test any absolute threshold, or normalise the input first.
- **A sparse dict is safe for "any of these modes" and unsafe for "all of these".** The heating gate (`hourly_processor.py:645–648`) iterates the configured sensors because the dict is empty on default installs. The guest check (`845–848`) reads the dict because a missing entry is not a guest. Both are correct for the question they answer. Potential application: write down which question each sparse-dict read answers.
- **Name the unit in the field.** The `hourly` block in the uncertainty stats holds per-day counts (`forecast.py:1945–1949`). A field named for the granularity will mislead the next reader. Potential application: name the unit (`days`) or the granularity of the sum, not both.
- **Match the catch to the failure you expect.** The 4D battery catches everything (`hourly_processor.py:794–799`) and the 3D block catches three types (`800–803`) in the same function. A typo in the 4D path disappears. Potential application: catch the errors you expect from the input, and let wiring errors surface.
- **Mark a slot as done only when the attempt succeeds.** The Track C snapshot records its slot before checking whether the fetch worked (`daily_processor.py:608–610`), so a failed fetch uses up the slot and there is no retry in that window. The docstring says the previous snapshot is kept, which is true, but the retry is not. Potential application: set the slot after success, or record the failure separately.
- **Tag once, then read the tag.** The learner writes `track_used` (`daily_processor.py:1176–1178`, `1254`, `1267`), and the diagnostic re-infers attribution from which fields are present (`diagnostics.py:919–925`). Potential application: a diagnostic should read the tag the writer set, and fall back to inference only for rows written before the tag existed.
- **A sort key that maps missing to zero puts the worst items last.** An infinite deviation has `delta_pct` set to `None` (`diagnostics.py:860`), and the sort key `or 0.0` (`883`) turns that into zero, so the worst entries sink. Potential application: give unbounded values a sentinel that sorts first, or sort them in their own group.
- **One idea, three thresholds.** A complete day is defined by 20 in the warning (`daily_processor.py:1057`), 22 in the U-coefficient gate (`1205`), and "/24" in the message (`1256`). Potential application: name the constant once and use it in all three places.
- **A failure message must match what was kept.** The load error says Heating Analytics starts fresh (`storage.py:1419`), but the handler resets nothing (`1411–1424`), so anything restored before the failure stays in memory. Potential application: either reset on failure, or say what was kept.
- **Every branch that writes a bucket applies the same weights.** The aux-excluded base path skips the headroom and SNR weights (`learning.py:2698–2704`), while the normal base path applies them (`2723–2745`). Potential application: pass the weights into one helper, so a branch cannot leave them out by accident.
- **Round the stored value no coarser than the step it must hold.** The aux coefficient is rounded to three decimals (`learning.py:2919`), so an EMA step under 0.0005 kW is lost. Potential application: keep a full-precision value for the update, and round only for display.
- **A docstring can outlive the code it describes.** Several `learning.py` docstrings in the batch fit and the replay describe rules the code no longer follows: shutdown rows are said to be dropped under Tobit (`4780–4781`, `4316–4317`) but are kept as censored rows (`4904–4927`); a missing `unit_expected_breakdown` is said to fall back to a conservative estimate (`4696–4702`) but returns the persisted flag (`4733–4740`); `unit_threshold` is said to be unused (`4789–4792`) but sets the MAD sigma floor (`5048–5053`); and one counter per unit is claimed (`3967–3968`) while the inequality branch increments two (`4122–4123`). Potential application: when a comment states a rule, a test should pin the rule, not the comment.
- **A missing scope should fail closed.** The batch fit treats an absent solar scope set as "all entities included" (`4380–4386`), and reads the coordinator's WeightedSmear strategies with `getattr(..., {})` (`4360`), so a missing attribute silently drops the MPC exclusion. Potential application: a missing scope should skip the entity and count it under a named reason.
- **A default in `get` covers an absent key, not a stored `None`.** `_reconstruct_potential` reads `entry.get("solar_vector_s", 0.0)` with no `or 0.0` (`3825–3828`), while the replay reads the same fields with `or 0.0` (`3735–3737`). A stored `None` is defaulted in one path and not the other. Potential application: normalise nullable log fields once, at the point they are read.
- **A catch-all branch should name what it catches.** Any outcome other than `base` or `aux` is counted as `units_skipped_dhw_during_aux` (`3772–3773`), and any inequality status other than `updated` or `non_binding` is counted as low battery (`4172–4173`). A new outcome would be reported under the wrong reason. Potential application: match each outcome explicitly and raise on an unknown one.
- **Two attribute names for one source turn a missing name into an empty fit.** The 4D batch reads `coordinator.model.correlation_data_per_unit` (`learning.py:5687`, `4859`), but the obstruction fit reads `getattr(coordinator, "_correlation_data_per_unit", {})` (`6226`). If the two names ever point to different data, the empty default gives every row a zero baseline, and each row is skipped with `continue` (`6414–6415`) without an error. Potential application: one accessor for the model, with no `getattr` default on data that every fit needs.
- **A named reason should be returned only for the cause it names.** `no_candidate_passed_sample_floor` (`learning.py:6840`, `6926`) is also returned when the span check (`6537–6538`), the shutdown constraint (`6522–6526`), or a zero null SSE (`6565–6566`) removes every candidate. Potential application: name the cause where each path sets the reason, or give each cause its own name.
- **Absence of a failure reason is not success.** When the Newton loop reaches `max_iter` without a break, `converged` stays `False` and `failure_reason` stays `None` (`learning.py:5428–5429`, `5593–5618`). A diagnostic with no reason looks like a clean fit. Potential application: set a reason on every exit that is not convergence, as the line-search branch already does (`5577`).
- **A rationale comment can name the wrong mechanism.** `_tobit_mills` says survival "underflows" above `q = 8` (`learning.py:5195`). Survival there is about 6×10⁻¹⁶, which is representable, and the code sets it to zero on purpose (`5198`). Potential application: when a cut is deliberate, write the reason for the cut, not the nearest plausible one.
- **A check that skips when its own input is small passes everything small.** The plausibility gate computes the OLS comparison only when the Tobit magnitude exceeds a floor (`learning.py:7589`), and only when the OLS fit is not `None` (`7598`). Below the floor, or on a degenerate OLS, the write goes through with no check. The comment at `7643–7652` covers only the norm guards, not the `None` case. Potential application: decide what a skipped check means on purpose, and write that decision next to the skip.
- **A gate on a dict that is always set is always open.** The 4D inequality update is gated on `solar_coefficients_4d_per_unit is not None` (`learning.py:2087`). The coordinator initialises that dict to `{}` (`learning.py:2145`), so the test is always true, and the 4D shadow flag is not checked here. Whether that matters depends on whether `obs` is `None` when the flag is off, which was not checked. Potential application: gate on the flag itself, not on the presence of its storage.
- **A shared helper is only a single source if everything calls it.** `helpers.compute_base_ema_step` says the live writer and the retrain path use it, so the diagnostic cannot drift from them. Only the diagnostic calls it. The live and retrain writers keep their own copies of the formula, so the guard the helper was built for does not exist. Grep for the callers before trusting a "single source" comment.
- **A diagnostic should not write.** `diagnostics.py` holds `calibrate_per_unit_min_base_thresholds`, which changes live thresholds (`diagnostics.py:5323`). It is reached from a service, not from the diagnose calls. Keep writers in a module named for writing, or make the name and the docstring say so.
- **Run side effects at the final save, not at an intermediate step.** The reconfigure flow runs the aux and solar learning resets on an intermediate page (`config_flow.py:967–980`). A user who cancels on the last page keeps the reset but not the new settings. Defer irreversible work until the flow commits.
- **A learned zero is a value, not a missing one.** Heating Analytics' 3D solar read treats a learned all-zero coefficient as unlearned and falls back to a seeded default (0.35 heating, 0.40 cooling). Its 4D read returns zero, which is the learned answer. Check every fallback for whether it can replace a value the model actually learned.
- **Key buckets through one helper.** Heating Analytics builds its temperature bucket key with the same expression, `str(int(round(x)))`, at about fifteen call sites in eight files. Python's `round` sends halves to the even whole degree, so 17.5 maps to 18 and 18.5 maps to 18. The sites agree today. A single helper would stop them drifting apart.
- **Compare online and batch estimates.** RoomMind's EKF is an online method; the Bacher and Madsen procedure is batch grey-box. Trust neither until they agree.
- **Check identifiability before reporting C.** Low-resolution data weakens capacitance estimates (EcoEdge's search sources). Our recorder resolution limits this.
- **Use physical bounds** on parameters (Heating Analytics bounds the inertia time constant at 1–24 h; thermal-rc-toolbox uses physical priors).
- **Report uncertainty**, not only best fit. thermal-rc-toolbox clusters near-optimal solutions with HDBSCAN.
- **Use several error metrics:** CV(RMSE) and NMBE, as in ASHRAE Guideline 14 calibration practice (cited in the search results, not opened). Predbat uses median bias, so one outlier doesn't dominate.
- **Cooldown with heating off** is a sanity check. Predheat's example (1.5 K in 3 h at ΔT 10 K) is a useful test case for our fitting code.
- **Tobit regression** handles censored solar-gain observations (Heating Analytics). Our solar hypothesis should consider this, since hidden solar gain while heating is on is censored.
- **Non-negative solar terms** (Heating Analytics) avoid unphysical negative gains.

### Data handling
- **Check coverage per day** before fitting (GivTCP's PALM requires coverage to 21:00 and handles counter resets).
- **Carry missing forecasts forward and log it** rather than zero-filling (Predbat).
- **Don't silently impute outliers.** IQR smoothing can erase real events such as an open window (GivTCP). Mark those periods instead. Our Kitchen 3 November finding depends on this.
- **Use cumulative energy meters, not power**, for energy-balance methods (Heating Analytics). Check meter latency.
- **Log which energy source each estimate used** (Home Performance).
- **Golden-file tests** on captured raw data (GivTCP, Predbat) are worth copying for regression.

- **A falsy test on a numeric value hides a real zero.** `if avg:` skips a true 0.0 (`forecast.py:2894–2897`). Search our code for `if x:` where `x` can be a temperature, a power or a count.
- **A snapshot that replaces some fields must replace all of the fields it governs.** The midnight override changes kWh and leaves solar impact on the live basis (`forecast.py:2921–2924`).
- **Store the gate decision with the row, not only its inputs.** The cooldown units are recorded at log time because the scope can change later (`hourly_processor.py:1224–1239`).
- **Accumulate, persist and reset are one unit.** A failed save between the accumulate and the reset double-counts the next hour (`hourly_processor.py:1276–1297`).

- **One function, two policies for an absent key.** A restore that keeps the current value for some keys and clears it for others gives different results for the same missing key (`storage.py:1795–1892`). Choose one policy and state it in the docstring.
- **A backup must carry every key its restore reads.** `unit_modes` and `learned_u_coefficient` are read on restore and are not written by the backup (`storage.py:1607–1678`, `1775`, `1892`).
- **Malformed entries dropped without a count are invisible.** Each `isinstance` filter in the restore discards data silently (`storage.py:1829–1853`). A counter in the restore log would show the loss.
- **A periodic save that swallows its exception hides a failing disk.** The reason is given in the comment (`storage.py:1577`), but no failure count is kept.

- **Read the schema from every row, not from the first.** The hourly export loses any column that first appears in a later row (`storage.py:2216–2229`). The daily export takes the union of keys (`storage.py:2140–2144`), which is the safer choice.
- **A column named by position changes meaning when the list changes.** `unit_{i}_actual` maps to a different unit after a sensor is removed or reordered (`storage.py:2094–2100`, `2220–2223`). Name the column by its entity id.
- **A missing version is not the current version.** The restore keeps a Tobit statistic with no version as if it were current (`storage.py:1938–1940`). An unknown version should be dropped.
- **A flag that is always true makes its branch dead.** `stored_non_default` is always true inside the branch that sets it, so the test that follows never runs (`diagnostics.py:1368–1381`).

- **A dedupe key must be the instant, not the string.** The full-mode import dedupes on the timestamp text (`storage.py:2707–2708`), while the weather-only merge joins on the UTC instant (`storage.py:2520–2526`). The same instant can be stored twice.
- **Name the default key for a lookup, or do not supply one.** `temp_key` falls back to `"10"` (`diagnostics.py:1542`, `2177`). A stale row is then scored at 10 °C without a flag.
- **A guard that returns its input in another basis hides the change.** Returning the effective value when the transmittance is tiny (`diagnostics.py:2208–2210`, `2382–2384`) gives a number in the wrong basis with no flag.
- **A sweep whose best value sits on the edge of its grid must be flagged as a boundary.** The flag at `diagnostics.py:2464` measures distance from a default and cannot fire at 0.05.
- **Record the exception, and say what the field tests.** The Tobit wrapper records the class and message (`diagnostics.py:2532–2541`), which is the pattern to copy. The `in_cold_start` field tests more than its name says (`diagnostics.py:2586–2592`).

- **Pin a retired dimension, do not delete it.** The grid holds the single live value and the keys still name it, so the payload says what a fit is conditional on (`diagnostics.py:2865–2871`).
- **Anchor a counterfactual at the live setting, not at zero.** A baseline at zero offsets every candidate by the live release, and the live value looks like a change (`diagnostics.py:3340–3350`).
- **A recommendation carries its withholding reason in the same payload.** A raw argmin with no reason reads as endorsed (`diagnostics.py:3204–3219`, `3817–3819`).
- **Compare a candidate with the baseline at the same precision.** A full-precision baseline loses ties to rounding noise (`diagnostics.py:3458–3468`).
- **A sparse table's default must not be a measured value.** A missing baseline cell defaults to a zero RMSE (`diagnostics.py:3524–3525`).
- **A test that did not run must not read as a test that failed.** A missing `significant` key is read as not significant (`diagnostics.py:3763`).
- **Payload shapes must not depend on the branch.** One summary field takes three key sets (`diagnostics.py:3801–3837`).
- **Count parse failures apart from valid zeros.** A row that cannot be read is merged into the night count (`diagnostics.py:4049–4054`).

- **One flag, one reader.** Two reports read the same config flag with different tests (`bool(x)` and `x is True`), so they can disagree about whether a feature is on (`diagnostics.py:4080`, `4159`).
- **A verdict that names a finding needs the sample floor for that finding.** A divergence verdict is given on five hours when its threshold needs twenty (`diagnostics.py:5868–5879`).
- **Pair periods by key, not by position.** Two day lists paired by index shift on one missing day, and the totals and averages cover different days (`explanation.py:365–404`).
- **Identical branch arms are a dead branch.** The two arms of the driver test append the same checks, so the sign of the change does not change the result (`explanation.py:425–435`).
- **A checklist must name constants that exist.** The solar bump list names `COMPOSITE_LEGACY_FLOOR`, which is not in the code (`const.py:657–658`). Check checklists against the code.
- **Two constants with one value and two roles should be named by role.** The two screen floors are both 0.30 (`const.py:195`, `215`).
- **A key that can hold `None` needs a `None`-aware read.** `entry.get(key, 0.0)` returns `None` when the key exists with a `None` value, and the next `float()` raises (`diagnostics.py:5974`, `5982`).
- **A broad `except` in a replay should count its failures.** A replay that returns `None` for any exception hides code faults as missing data (`diagnostics.py:5620–5621`).

- **A coverage note must match the pass headers.** A "Still not read" line that says a file is fully read must agree with the line ranges in its pass headers. Check the ranges, not the summary (`solar.py` passes 10 and 46 left `300–301` and `470–548` unread until pass 247).

- **Check two lists the same way before dividing by their total.** A total built from one list and a loop over another lets a length mismatch drop energy silently (`thermodynamics.py:209`, `252–255`).
- **A fallback value that makes a ratio the identity hides a missing input.** A COP of `1.0` makes thermal and electrical energy equal and sets no flag (`thermodynamics.py:302–305`, `321`).

### Validation and tests
- **Hold out data**, and compare predicted with measured temperatures. EcoEdge published no such validation; we should.
- **Shadow mode** gives a free counterfactual: predicted against actual, run standing alongside decisions (Heating Analytics, EcoEdge).
- **Test sensitivity to any confidence weighting** under several settings (GivTCP PALM, P10/P50/P90).
- **Treat warm-up as a known period.** Heating Analytics needs 7–14 days; Track B (daily learning) months. Report predictions as unreliable until then.
- **Version-tag learned parameters** so they can be reset after physical changes (RoomMind's "Reset Thermal Data", Heating Analytics' solar reset).

### RoomMind code review: parameter learning and MPC

Read from `custom_components/roommind/` at commit `2aeb49a`. Line references are to that commit.

**EKF parameter learning (`control/thermal_model.py`, `ThermalEKF`)**

- **State and units.** x = [T, α, β_h, β_c, β_s, β_o, β_f] with C = 1, so α = U/C (1/h) and β = Q/C (K/h). That is seven states. The class docstring (lines 239–246) still shows six; β_f (AC air/mass offset) was added in `ekf_version` 6.
- **Predict.** Uses the analytic 1R1C solution, T_eq = T_out + u/α. The Jacobian is derived analytically, and I checked the α-derivative (`F[0][1]`) by hand against the solution; it is correct. Each parameter is a random walk. The Euler branch is used when α < 0.01.
- **Update.** One scalar measurement (T), so H = [1, 0, …]. Gain K = P[:,0]/S, with K_i set to zero when parameter i is not *excited* (`F[0][i]` = 0 in the predict step). This is the mode gating: β_h learns only while heating or during residual heat, β_c only while cooling, β_s only on sunny non-heating steps, and so on.
- **Process noise.** Drift is added only to excited parameters. Q_α is scaled by (α/α_default)², capped at 1.
- **Outliers.** An innovation above 4σ inflates R by 100× for that update (a soft reject). It is not discarded.
- **Covariance.** The update uses a Joseph-like form with an extra K·R·Kᵀ term (`P00 + 2R`). The code comment says this is deliberate. It keeps P conservative.
- **Bounds.** Parameters are clipped after each update (`_clamp_parameters`). P is not adjusted when a parameter is clipped, so a parameter sitting on a bound keeps its variance.
- **Window open.** Parameters are not updated. A separate `k_window` is learned from the exponential decay ratio, with EMA 0.05 and clamp [1.5, 50].
- **Persistence.** `from_dict` pads older layouts with defaults. Saves with α pegged at 2.0 and `ekf_version` < 6 get their RC parameters reset (`_reset_rc_params_for_recovery`).

**Batching and training inputs (`managers/ekf_training_manager.py`)**

- Updates are flushed on mode change, window open, or every 3 min (`EKF_UPDATE_MIN_DT`).
- The power fraction and AC rebound charge are dt-weighted over the batch. Solar, residual heat, occupancy and the outdoor temperature use the value at flush time, not an average. This is a limitation for batches with changing solar input.
- After a restart or a skipped cycle the model temperature is re-synced to the measurement without learning the jump (#478).

**Gating: when MPC replaces bang-bang (`control/mpc_controller.py`)**

- MPC runs only if the 5-minute prediction std is below 0.5 °C (`MPC_MAX_PREDICTION_STD`) and the room has at least 60 idle and 20 heating and/or cooling updates. Otherwise the controller uses bang-bang at full power, which the code describes as a way to speed up learning.
- The same gate is written twice: `is_mpc_active` and `_has_enough_data`. They must stay in step.
- `confidence` = 0.3·data + 0.7·data·accuracy. The accuracy term is evaluated at fixed probe conditions (for example, ΔT = 15 K), so it does not describe the room's actual operating point.

**MPC (`control/mpc_optimizer.py`)**

- The module and class docstrings say "Dynamic Programming". `optimize()` is a **greedy receding-horizon search**. For each block it scores idle, heat and cool over a 6-block (30 min) forward simulation, with a longer lookahead for underfloor heating. The cost is w_comfort × squared deviation outside the dead band, plus w_energy × |Q|/1000 over the minimum run. It takes the lowest-cost action. This is not an optimal DP over the horizon, and this review should not describe it as one.
- Power is closed-form: Q_required = (T_ref − T_drift)·α/β, minus an energy bias. T_ref = T + approach_rate·(target − T). The result is clamped to [MIN_POWER_FRACTION, 1].
- Planning uses the point estimate of the parameters (certainty equivalence). Prediction uncertainty only gates on/off, not the plan.
- Other rules: minimum run lengths; a start penalty for slow systems; a pre-heat deadline that starts heating as late as possible before a rising target (`_preheat_deadline`); predictions clamped to [min(5, T−5), max(30, T+5)].
- **Possible inconsistency (not run).** `compute_optimal_power` adds residual heat and AC rebound to the drift on every block. `optimize()` and `simulate_plan()` pass them to the forward model only when idle (residual when Q = 0; rebound only in idle blocks). When heating with residual heat still present, the closed-form power expects warmth that the simulated trajectory does not include. The power chosen could then be too low. A unit test would settle this.

**Controller wiring**

- `get_model()` rebuilds an `RCModel` (C = 1) on every cycle from the current EKF state, clamping U ≥ 0.005 and the heat and cool rates at 0 or above. The plan is rebuilt each cycle; nothing is cached.
- The cover logic uses `simulate_plan()` with occupancy removed, so shading decisions do not count body heat.

**What this means for us**

- Adopt the excitation gating (only update a parameter when the current input can reveal it), the per-mode parameters, and the two-part gate (prediction std and sample counts) before the controller acts on a model.
- Keep bang-bang as the fallback while the model is learning.
- Do not describe RoomMind's optimiser as optimal. If we need a horizon-optimal plan, that is a MILP or DP problem.
- Write a test that checks the closed-form power against the forward simulation, including residual heat and rebound, before trusting either.

---

### Heating Analytics code review: design and learning

Read from `custom_components/heating_analytics/` at `eba9e6e` (v1.3.16, 2026-10-06). Line references are to that commit.

**Design document (`DESIGN.md`, 731 lines, read in full)**

- **Feed-forward only.** The integration never controls heating (§7A). The reason given is feedback-loop corruption.
- **Base model.** EMA buckets by temperature and wind. The global curve is U-shaped because cooling is learned too. Each unit has a separate cooling bucket, so standby cannot write into heating buckets (§2K).
- **Solar.** A 3D south/east/west vector per unit and regime, learned by NLMS, a Tobit live learner, an inequality learner and cold-start least squares. The base model uses SNR weighting. The battery is an EMA with decay 0.50 (§2D).
- **Modes and events.** After aux turns off, learning is locked for aux-affected units until the usage ratio converges (92 %), with a 2 h minimum and 6 h maximum. DHW is observed as zero, not skipped. Guest mode is excluded.
- **Track C.** The MPC's thermal buffer is smeared over the day by heating need, then converted to electricity with a per-hour COP (§2I).

**Learning code, read**

- **Per-unit base (`learning.py:1558–2155`, `2631–2822`).** Each unit's hour goes to its own bucket, or to its aux coefficient during aux. A cold start buffers 4 samples and jumps to their mean. After that, the EMA rate is min(rate, 3 %) × headroom × SNR weight. The headroom term (#838) slows the step as solar approaches the base. The design does not mention it. Aux learning has the 3 % cap but no SNR or headroom weight.
- **Solar NLMS (`learning.py:2187–2495`).** Heating impact is clamped at zero, so negative residuals never count. A dead-zone reset fires after 15 consecutive zero-impact sunny hours (`const.py:273`). Cold start is 3×3 least squares on 4 samples, with a collinear fallback, clamped to the cap, then damped by 0.75. The step is μ·e/(‖s‖² + ε) with μ = 0.10. ε shrinks the step when input power is small. It does not pull the coefficient to zero (`learning.py:2464–2466`).
- **Inequality (`learning.py:2984–3109`).** Heating only. On shutdown hours it raises coefficients until coeff·potential ≥ 0.9 × base, by projected gradient with step 0.05. It never lowers them. The docstring says battery decay 0.80; the constant is 0.50.
- **Tobit solver (`learning.py:5183–5623`).** Right-censored Gaussian MLE over (c_s, c_e, c_w, log σ). Projected Newton with an active set for c ≥ 0. Backtracking line search with up to 10 halvings. γ = log σ is bounded to [−10, 10]. Warm start is least squares on uncensored rows. σ is seeded from the least-squares residuals, not from the warm-start coefficient. Failures return a reason: `line_search_failed`, `singular_step`, or `max_iter`. The Mills ratio uses `erfc`, with the asymptotic form above q = 8. q is floored at −5.
- **Live Tobit writer (`learning.py:7324–7748`).** A 200-sample sliding window per (entity, regime). Each hour runs one Newton solve from the current coefficient. If that fails to converge, it retries from least squares. Heating only: the plausibility gate requires OLS on uncensored rows to reach 0.10 in some direction and cosine(Tobit, OLS) ≥ 0.5. If the gate fails, NLMS keeps write authority. The gate only applies when the Tobit magnitude exceeds 0.05. Each direction's step is capped at 30 % of the prior maximum, when that maximum exceeds 0.05. Cooling skips the gate because it has no censoring.
- **Batch fit (`learning.py:4262–4667`, collector `4752–5100`).** Tobit per (entity, regime), with saturated hours (impact ≥ 0.95 × base) censored. Gates: ≥ 20 uncensored rows, n_eff ≥ 40, and convergence. The result is a damped blend with α = 0.3, or written directly when the regime has no prior. Optional seeding of the live window.
- **Batch MAD pass (3D only, `learning.py:5019–5081`).** The 3D collector applies the same MAD filter as the live path. The 4D collector (`learning.py:5626–5829`) applies only the magnitude gate.
- **4D shadow (`learning.py:1952–2026`, `5831–6047`).** Strict shadow: writes only `solar_coefficients_4d_per_unit`. The 4D batch has no live window, so seeding is a no-op.
- **Track B and C daily (`daily_processor.py:1051–1316`).** Learning needs at least 22 hourly entries (line 1205). The U-coefficient EMA rate is 0.005. Track C needs at least 18 MPC records matching the day (line 699). On an MPC outage, learning is skipped (lines 1179–1191, #855 Option B). Track B's flat cold start writes the first value directly, without the 4-sample buffer, and treats a stored 0.0 as "not yet learned" (lines 1242–1244).
- **Track C smear (`daily_processor.py:739–823`, `thermodynamics.py:119–147`).** Loss weight = |BP − T_inertia| × wind multiplier (1.0 / 1.3 / 1.6) × a solar term. Above the balance point the weight rises with sun. Below it, the weight falls with sun. Missing log hours default to the balance point, so they get zero weight. The COP is η_Carnot × defrost penalty, clamped to [1, 10] (`thermodynamics.py:91–117`), as the design says.
- **Battery feedback (`hourly_processor.py:61–83`).** `k_feedback` defaults to 0, so the design's EMA formula is what runs.

**Where the design and the code disagree**

1. **Solar ε (design §2D.4).** The design says ε "shrinks poorly-constrained components". The code shrinks the step, not the coefficient, as the constant's comment says. The design wording is wrong. The code is consistent with its own comments.
2. **Track C outage (design §2I).** The design says Track C falls back to Track B's thermal-mass correction. The code skips learning for that day (#855 Option B). The design is stale.
3. **Shutdown rows in batch fit.** The batch docstring (`learning.py:4316–4317`) and the collector docstring (`4780–4781`) say shutdown hours are dropped. The Tobit collectors keep them as censored rows (`4905–4914`, `5720–5733`). The inline comments state the choice, so the code is deliberate and the docstrings are wrong.
4. **Inequality decay.** The docstring says 0.80 (`learning.py:3013`). The constant is 0.50.
5. **Warm-up hard cap.** The comment at `learning.py:751` says 20 kWh. The constant `HARD_OUTLIER_CAP_FACTOR` is 10.0 (`const.py:393`).
6. **Prediction terms missing from the design.** The 3D prediction has three experimental terms that the design does not describe: hotspot attenuation (#950), tail-aware solar redistribution (#948) and the carryover release (#896). All three default to off (`coordinator.py:593–619`; feedback k is retired). Their absence from the design is a gap, not a mismatch in behaviour.
7. **4D docstring is stale.** `calculate_total_power_4d` says it is strict shadow and that nothing in the live pipeline calls it (`statistics.py:1123–1128`). The dispatcher in `calculate_total_power` sends every call to 4D when `experimental_4d_primary` is on, unless a 3D-only override is passed (`statistics.py:299–339`). With the flag on, 4D is the live prediction. The flag defaults to off (`const.py:186`).

**Code issues found while reading**

- **3D batch overwrites a decayed regime without damping.** The 3D batch treats a regime as having a prior only if a component exceeds 1e-6 (`learning.py:4547`). The 4D batch also checks a `learned` flag, which its comment says is needed when a regime decays to zero (`learning.py:5999–6001`). The 3D path lacks this check.
- **4D batch has no outlier pass.** The 3D batch applies the MAD filter. The 4D batch does not, so the two can disagree on the same hours.
- **Track C heating energy is spread into warm hours.** Hours above the balance point get cooling-mode weights and so receive part of the day's heating energy (`thermodynamics.py:139–141`). That is harmless if the unit also cools, but it looks wrong for a heat-only MPC unit. I have not tested it on data.

**Second pass: prediction, hour close and forecast**

- **Per-minute loop (`coordinator.py:3241–3628`).** Outdoor temperature and solar are read at the same instant. DHW energy is left out of heating totals. A meter reset is skipped and the baseline is re-set. A spike above `max_energy_delta` is skipped the same way. Buckets are keyed on the rounded inertia temperature. The thermal regime switches at |BP − T| > 4 K, as the design says.
- **Inertia and gaps (`coordinator.py:2393–2473`).** History stops at the first gap longer than τ, as the design says. Replays recompute inertia from raw temperatures on the current axis (`_entries_on_current_axis`).
- **Effective wind (`coordinator.py:2532–2558`).** Effective wind = speed + max(0, gust − speed) × gust factor. The design does not mention the gust term. The hour's wind bucket comes from the 90th-percentile (nearest-rank) wind of the samples, not the mean (`hourly_processor.py:377–379`).
- **Hour close (`hourly_processor.py:318–417`, `806–1000`).** An hour is aux-dominant at ≥ 80 % of samples. Mixed mode (20–80 %) is not learned. Dual interference is not learned either: if solar impact and aux impact both exceed 0.1 kWh, both the global and per-unit paths skip the hour (`const.py:478–487`). The design gives the 20/80 mixed-mode bounds but no dual-interference rule. Aux cooldown exits after a 2 h minimum, a 6 h maximum, or 92 % convergence. An hour that converges is still protected.
- **Gap fill (`coordinator.py:2679–2774`).** Missing minutes are filled at the hour's mean temperature and wind, not the last minute's rate, so the logged hour sums to 60 minutes.
- **Solar batteries (`hourly_processor.py:617–800`).** Three EMAs with the same decay: the scalar impact (display and log), the carryover (feedback, off), and a per-direction potential battery that feeds the inequality learner.
- **3D prediction (`statistics.py:341`).** Heating applied solar = min(potential, net demand), with the excess counted as wasted. Cooling is additive with no cap (`solar.py:1025–1075`). This matches design §2D.2.
- **Forecast blend (`forecast.py:440–508`).** Secondary is the baseline. Primary overwrites the dates before the crossover date. This matches design §3.A.
- **Forecast accuracy (`forecast.py:2001–2079`).** The "daily" block matches design §3.C: the mean of |daily net error|, and a signed weather bias. The "hourly" block is misnamed. Its MAE is the sum of absolute hourly errors per day, so it reports kWh per day, not per hour. The cutoff day is included, so "7d" covers eight days at the edge.

**What this means for us**

- Weight each hour's update by its sun, and state the target it converges to.
- For hot-water cycles, observe zero rather than skip. The design's drift table (+9 % to +140 %) is an analytic claim, not a simulation.
- Season-transition hysteresis has a test the design defines: bucket the residual by the trailing 48–72 h temperature trend and look for a signed bias near +1 to +3 °C.
- Copy the live Tobit writer's guards before a censored fit changes live state: a plausibility check against a simpler fit, a rate limit on the step, and a restart from least squares when the warm start fails.

**Third pass: 4D prediction path (`statistics.py:1107–1386`)**

- **Inputs.** DNI and DHI come from a ladder: a GHI sensor (split with Erbs), then native DNI and DHI, then cloud cover (Kasten). Replays pass DNI, DHI and sun position in directly (`statistics.py:1270–1290`). Below the horizon the solar term is zero, labelled `no_sun`.
- **No-irradiance fallback (`statistics.py:1335–1379`).** If the ladder finds nothing, the hour uses the cloud-derived 3D solar term instead of zero. The code gives the reason: zero solar would assert darkness on what may be a clear day. The three 3D-only interventions stay off on that hour, so it matches the hours around it. The design does not mention this rule.
- **Interventions.** Hotspot attenuation, tail-aware redistribution and carryover release are deliberately absent from 4D (`statistics.py:1143–1149`). With the flag on, the prediction therefore loses those terms, and they have no 4D form yet.

**Fourth pass: per-unit replay (`learning.py:3469–3809`)**

- **Shared code.** The replay calls the same helpers as live learning: `hour_learning_skip_reason`, `unit_learning_skip_reason`, `per_unit_hour_actual` and `_learn_unit_base_or_aux`. The docstring says so, and the code matches.
- **Aux hours are not replayed by default.** `replay_aux` is False unless the caller sets it. An aux-active hour of an aux-affected unit is counted as `units_skipped_aux_not_replayed` and not learned.
- **SNR weight counts the live set.** The hour's weight counts the `hourly_sensors` list, the units live hourly learning ran for, not only the unit being replayed. It is computed once per hour, on the first unit that learns to the base path. That is before the hour's base writes, so the expected base is the pre-hour value, as the docstring says. Aux writes do not touch the base buckets, so they do not change it.
- **Solar impact uses the model being rebuilt.** The unit coefficient is read with `calculate_unit_coefficient` at replay time, not the coefficient live used when the hour was logged. If the solar coefficients have moved since, the replayed impact and headroom differ from what live saw. I have not checked whether the caller replays solar before or after the base.
- **Dry run and diff.** A dry run works on deep copies. The reported diff is capped at 200 buckets, but `buckets_changed` counts all of them.
- **Reset scope.** `reset_first` clears one unit's base buckets, base buffer and observation count. It does not clear the aux coefficients or the aux buffer. The docstring does not say so.

**Fifth pass: solar NLMS replay (`learning.py:3904–4261`)**

- **Shared update.** Each unit's NLMS step goes through `_learn_unit_solar_coefficient`, the live path. Shutdown hours go through `_update_unit_solar_inequality`, also live. The replay does not rebuild the live Tobit window, the batch fit or the 4D model, so a retrain leaves those as they were.
- **Battery before the filters (`learning.py:4021–4026`).** The potential battery updates on every entry before the aux, poisoned and magnitude filters. Skipped hours still decay it, as the comment says live does.
- **Battery starts at zero, with the default decay.** The replay starts from zero and uses `SOLAR_BATTERY_DECAY`, not the user's calibrated value. The comment calls this deliberate. The first hours of a replay therefore see a battery with no history. The code also assumes `entries` is in time order. I have not checked the caller.
- **Shutdown hours get inequality only.** A unit listed in `solar_dominant_entities` gets the inequality update and no NLMS step on that hour (`learning.py:4114–4175`). Heating mode and the screen scope are checked first.
- **Stale docstring.** The docstring (`learning.py:3939–3950`) says a WeightedSmear sensor uses `track_c_distribution` as its expected base. The code skips those sensors (`4139–4144`, `4205–4210`), and the comment at `3960–3963` says so. The docstring describes behaviour that was removed.
- **Magic number.** The magnitude gate is the literal `0.1` at line 4049, not a named constant. I have not checked whether live uses the same value.
- **Diagnostic label.** An inequality result of `zero_magnitude` is counted as `inequality_skipped_low_battery`. The comment at line 4172 notes the mapping, but the counter name does not say so.

**Sixth pass: global writers (`learning.py:3159–3468`)**

- **Two global writers with different weights.** Retrain calls both `learn_from_historical_import` (per hour, `retrain.py:1124`, and `storage.py:2439`) and `apply_strategies_to_global_model` (daily sums, `retrain.py:846`, `856`, `865`, and `storage.py:2486`). The first scales the EMA rate by the hour's SNR weight. The second uses the raw learning rate with no SNR weight, so a sunny hour moves the global base as much as a dark one. I have not checked which hours reach which writer on a real install.
- **Dark-equivalent lift needs a learned coefficient.** `learn_from_historical_import` lifts a bucket toward `actual + solar delta` only when a solar coefficient in an active regime is marked `learned`. Otherwise it writes the raw actual.
- **The docstring's cap is not in the function.** Its docstring says the lift is bounded by `dark_target` and `SOLAR_COEFF_CAP`. The function never references the cap. The cap is applied in the solar learners, so the bound holds only if the delta is already capped where it is computed.
- **Zero means unlearned, again.** The aux path seeds from the implied reduction whenever the stored coefficient is `0.0`. A coefficient that learned down to zero is overwritten on the next sample, not blended. This is the same pattern as Track B's flat cold start.
- **Weight can be lost.** `apply_strategies_to_global_model` gives every log slot a normalised weight. A slot that is later skipped (no `temp_key`, or a zero total) keeps its weight, and its share of the day's energy is not spread onto the other hours. I have not measured how often this happens.
- **Slot keys are sound.** Hours are keyed on the UTC hour start, so the repeated hour on the DST fall-back day does not overwrite its twin (`learning.py:3286–3291`).
- **Solar delta gate.** The 4D delta is used when present and 3D otherwise (#968), and it is added only when a DirectMeter contributed to the hour. A smear-only hour therefore gets no correction (`learning.py:3433–3434`). This matches the #854 F1 intent.
- **Placeholder in a docstring.** The docstring of `learn_from_historical_import` cites "#xxx" for the SNR weight (`learning.py:3179`). That is a template placeholder, not an issue number.

**Seventh pass: obstruction and apply-implied fits (`learning.py:6049–7322`)**

- **Suggest, do not write.** `fit_solar_obstruction` returns `suggested_gates`, and writes nothing to state (`learning.py:7016–7048`). The apply step is a separate service. Each boundary must pass four checks: learned, SSE improvement of at least 0.30 (`const.py:571`), a plausible window, and stability across windows.
- **Shutdown hours are constraints, not samples.** A shutdown hour records its elevation as proof of unobstructed sun. It is not added to the fit, because `actual ≈ 0` saturates the impact and would bias the SSE comparison (`learning.py:6349–6375`). This is a sound use of a signal that the regression itself cannot use.
- **The shutdown bound tolerates contradictions.** The docstring calls it a hard bound (`learning.py:6087–6097`). The code binds only after `OBSTRUCTION_FIT_SHUTDOWN_CONSTRAINT_MIN_N` (3) shutdown samples lie on the far side (`learning.py:6637–6646`, `const.py:634`). So up to two contradicting shutdown hours are allowed. The comment gives noise tolerance as the reason, but the docstring does not say so.
- **Stability is skipped on single-pass calls.** With no stability input, every boundary is `stable=True` (`learning.py:6606–6621`). Only the multi-window handler checks stability. Any other caller gets an unchecked gate.
- **Combined-window check.** When both boundaries fire and the gap is under 10° (`const.py:641`), only the stronger one is kept (`learning.py:6957–6976`). A crossed pair, where the high gate sits below the low one, has a negative gap and is caught by the same check.
- **Tiny values are treated inconsistently in stability.** `assess_apply_implied_stability` drops values under 0.001 from the spread check (`learning.py:7312`), but keeps them in the sign-flip check (`learning.py:7303–7309`). Windows of `[0.5, 0.0005]` pass as stable: same sign, and the spread check sees only one value. Windows of `[0.5, -0.01]` fail as a sign flip. The two checks should use one threshold.
- **Two baselines for the same hour.** The obstruction fit recalculates expected base from the current per-unit model (`learning.py:6308–6312`, #1005). The apply-implied fit reads the logged `unit_expected_breakdown` (`learning.py:7113–7119`). After the model drifts, the two fits can disagree about the same hour. Only one of the two is explained in its docstring.
- **Different sample definitions for 3D and 4D windows.** The 3D pass gates on total samples (`learning.py:7147`), and its windows need 10 (`learning.py:7158`). The 4D pass gates on uncensored rows (`learning.py:7195`, `7220`). Stability is therefore judged on different counts for the two solvers.
- **The apply fit skips the MAD filter.** `match_diagnose=True` skips the full MAD baseline so that the committed value matches the diagnose figure (`learning.py:7121–7123`). The price is that an outlier can move a coefficient the user has just committed. This is a deliberate trade, and the comment states it.
- **Dead variable.** `crit_state_per_unit` is read and normalised (`learning.py:6211–6215`) and never used. The comment at `7046` says it is kept for diagnostics, but nothing reads it.
- **Stale docstring.** `fit_solar_obstruction` documents `dry_run` twice (`learning.py:6153–6159`). The first copy says it writes nothing and cites #1006. #1020 removed the write, so `dry_run` now only goes into the result (`learning.py:6589`).

**Eighth pass: diagnostic Tobit (`learning.py:7750–7899`)**

- **Diagnosis only.** `compute_tobit_for_diagnose` writes nothing. Its result goes to `diagnose_solar`, and the apply path does not use it (`learning.py:7750`, docstring at `7766–7767`).
- **A non-converged fit is still returned.** On `did_not_converge` the last Newton iterate is returned as the coefficient, with `skip_reason` set (`learning.py:7887–7897`). The docstring tells callers to check `skip_reason`, not `coefficient is None`. The apply path differs: it accepts a 4D fit only when it converged (`learning.py:7201`). So an iterate can appear in diagnostics and never reach a commit.
- **Caps apply after the gates.** Coefficients are clipped to `[0, SOLAR_COEFF_CAP]` only after the `n_eff` and convergence checks (`learning.py:7893–7897`). A non-converged iterate is clipped silently, so the reported value may not be the raw iterate. Nothing in the result says it was clipped.
- **Two floors, one checked late.** The `|U| ≥ 20` floor is checked before the fit (`learning.py:7865`). The `n_eff ≥ 40` floor is checked after the fit (`learning.py:7883`), so a fit runs on data that may be rejected. The comment at `7863–7864` says so. The cost is one solver run per rejected unit.
- **Result keys are not all documented.** `failure_reason` is set from the solver (`learning.py:7879`) but missing from the docstring's key list (`7776–7790`).
- **MAD baseline is wired in here.** This entry point reads live coefficients from `coordinator.model` and falls back to the private attribute (`learning.py:7812–7821`). Without either, the MAD outlier step is skipped and only the prior-free check runs. Because the MAD step depends on the live coefficients, a diagnosis can change after a retrain. The collector (`_collect_batch_fit_samples`, `for_tobit=True`) is not read in this pass.

**Ninth pass: `forecast.py` (partial, `440–508`, `714–752`, `1222–1340`, `1890–1938`, `2525–2644`)**

- **Blend keys daily forecasts by local date.** The docstring gives the reason: providers disagree about which instant stands for a day, so timestamp keys would leave both entries alive and the crossover rule would never choose (`forecast.py:440–460`). The consumer looks days up by date too, so producer and consumer agree.
- **Blend mutates its inputs.** It writes `_source` onto the caller's dicts in place (`forecast.py:463–499`). A caller that keeps the lists sees the tag change.
- **Missing errors count as zero.** The uncertainty percentiles read `abs_error_kwh` with a default of `0.0` (`forecast.py:1933`). A history row without the key lowers p50 and p95 without any warning.
- **Legacy rows match an unset entity.** The history filter compares `primary_entity` with the current weather entity (`forecast.py:1931–1932`). If no weather entity is set, a row with no key also matches, because `None == None`. The comment says legacy rows are a mismatch.
- **Breakdown fields disagree for legacy rows.** For a row without gross forecasts, `error` is net against net (`forecast.py:2586–2587`, `2611`). But `actual` accumulates the gross actual (`forecast.py:2617`, `2640`). So `actual − forecast` does not equal `error` for those rows. The comment at `2615` explains the gross accumulation but not this mismatch.
- **Solar falls to zero without a sun position.** If the item has no elevation or azimuth and its datetime cannot be parsed, the solar factor and vector stay at zero (`forecast.py:1297–1331`). The 4D path uses a cloud-derived fallback instead (`statistics.py:1335–1379`). The two paths handle the same missing input differently.
- **Missing outdoor temperature enters inertia as `None`.** `calculate_future_energy` appends `None` when the current reading is missing, to keep the position (`forecast.py:719–726`). I did not check whether `_calculate_weighted_inertia` accepts `None`.
- **Hard-coded day window.** The day and night split is fixed at 06:00–22:00 (`forecast.py:2594`). It is not a constant.

**Tenth pass: `solar.py` (partial, `34–299`, `302–469`, `575–1153`)**

- **The 3D read reverts a learned zero to the default.** `calculate_unit_coefficient` returns the learned coefficient only if one of its components is non-zero (`solar.py:991–994`). A unit whose learned heating coefficient is all zero gets the seeded default of 0.35, decomposed along the primary azimuth (`solar.py:1001–1008`). The 4D read returns the zero vector for the same case (`solar.py:916–923`). The two reads disagree about one state.
- **The obstruction fit restates the learned predicate.** `coefficients_4d_are_learned` says every readiness and gating consumer calls it, "not a copy of one" (`solar.py:447–456`). The obstruction fit checks only the `learned` flag (`learning.py:6378–6382`). It therefore accepts a regime the read path would treat as unlearned.
- **Lookup failures return a sun elevation of zero.** `get_approx_sun_pos` returns `(0.0, 0.0)` when the location is unset, astral is missing, or the call raises `TypeError` or `ValueError` (`solar.py:1090–1116`). `reconstruct_hour_inputs` then sees elevation zero and reports `SUN_BELOW_HORIZON` (`solar.py:377–384`). Its docstring says a lookup failure is reported as `SUN_POS_ERROR` and never as a zero-solar hour (`solar.py:353–357`). That branch fires only for an exception the method does not catch, so the documented distinction does not hold for these cases.
- **Two clear-sky models in one file.** The synthetic GHI for the Kasten ladder uses horizontal geometry, `sin(elevation) × 0.7^airmass` (`solar.py:242`). The 3D factor uses `cos(elevation) × 0.7^airmass` and clamps elevation at 1° (`solar.py:427–441`). Both are documented, but a reader comparing the two would expect one model.
- **Ladder order is sound.** The GHI branch needs a positive reading (`solar.py:232`), and the source-label function mirrors the same branch order (`solar.py:124–150`). A covered sensor that reads zero falls through, and the docstring says a test pins the agreement.
- **Screen handling avoids the squared transmittance.** Per-direction transmittance is applied once, and the reconstruction divides it back out (`solar.py:679–757`). The docstring at `solar.py:826–831` names the double-count bug this prevents.
- **Erbs coefficients as written.** The piecewise diffuse fraction in `erbs_decomposition` matches the form the docstring gives (`solar.py:69–73`, `106–117`). I compared it with the standard Erbs et al. (1982) coefficients from memory, not from the paper.
- **Unverified: DST days.** `estimate_daily_avg_solar_factor` steps 24 hours from local midnight by adding `timedelta` to an aware datetime (`solar.py:1124–1131`). Python keeps wall-clock time for that arithmetic, so on a spring-forward day one sample can land on a time that does not exist, and the average still divides by 24. I did not check how astral handles that time.
- **Stale line citations.** `resolve_dni_dhi_for_forecast` says the cloud fallback is "around lines ~147-150 / ~1148-1151" of `forecast.py` (`solar.py:267–270`). The pattern now sits at `forecast.py:155–156`, `1290–1291`, `1499–1500` and `1558–1559`. The same mapping is repeated in `coordinator.py:2264`. One helper would keep them together.
- **Not read:** `solar.py` lines 1–33, `calculate_solar_vector` (`549–574`), and the module header.

**Eleventh pass: `daily_processor.py` (partial, `204–333`, `584–628`, `885–1031`)**

- **Track B writes through the unweighted writer.** `try_track_b_cop_smearing` sends its distribution to `apply_strategies_to_global_model` (`daily_processor.py:908`), the writer the sixth pass found has no SNR weight. So the Track B path and the retrain path share the writer with the weighting gap.
- **Track B's docstring says 24 hours; the code spreads over the logged hours.** The docstring and the info log say the distribution covers "24 hours" (`daily_processor.py:893–895`, `916–917`). `track_b_cop_distribution` gives each logged row `q / len(slots)` (`daily_processor.py:975–979`), so a day with missing hours spreads over fewer than 24. The comment at `970–974` describes the change that made this so.
- **Failed smears fall back to flat without a flag.** Any `TypeError`, `KeyError` or `ValueError` in the engine logs a warning and returns `None` (`daily_processor.py:1024–1030`). The caller then uses the flat q/24 split. The result does not say which path ran.
- **Legacy gross picks the mode by temperature.** When the gross field is missing, `aggregate_logs` reconstructs it per hour and chooses the sign from the logged temperature against the balance point (`daily_processor.py:262–279`). The thermal-regime split in the same function uses the unit modes (`daily_processor.py:306–322`). The two can disagree for an hour that straddles the balance point.
- **Mixed 4D days give a partial sum with no coverage count.** The 4D totals sum only the entries that carry the key (`daily_processor.py:233–248`). The docstring is right not to treat missing as zero, but a day with some 4D hours produces a total that covers only those hours, and nothing in the aggregate says how many.
- **One key lookup can raise.** The average temperature uses `e["temp"]` (`daily_processor.py:325`), while the rest of the function uses `.get`. A log row without `temp` stops the whole aggregate.
- **Stale scratch comment.** The legacy reconstruction keeps the lines `(Wait, if solar adds load…)` and `Correct.` (`daily_processor.py:272–273`).
- **The regime split is recorded only when complete.** It is written only if every hour has a per-unit breakdown (`daily_processor.py:300–304`). A day with CSV-imported hours therefore has no regime split, instead of a false `0 / 0` idle day. The comment states the reason.
- **Track C snapshot uses up its slot on failure.** The slot is marked done before the result is checked (`daily_processor.py:605–609`). A failed fetch at 23:00 therefore gets no retry until the 23:55 slot. The docstring states the once-per-slot rule and says a failed call keeps the previous snapshot, so this is by design, but it leaves one attempt in the hour before the last one.

**Twelfth pass: `storage.py` (partial, `544–606`, `685–695`, `1431–1602`, `1602–1966`, `1966–2064`)**

- **The backup is not a full copy of the state.** `async_backup_data` writes a subset of the keys `async_save_data` writes (`storage.py:1607–1678` against `1463–1573`). Restore reads the missing keys with defaults, so a restore sets `learned_u_coefficient` (`1775`) and `last_midnight_indoor_temp` (`1777`) to `None`, `unit_modes` (`1892`), `solar_optimizer_data` (`1895`) and `hourly_expected_per_unit` (`1753`) to empty, and resets the hour-boundary keys (`1754–1760`). The backup docstring calls it the full system state.
- **The backup writes a key the restore ignores.** `per_unit_min_base_thresholds` is written (`1656`) and never read back.
- **A restore accepts any file.** It checks only that `correlation_data` or `daily_history` is present (`1710–1711`). The one-time legacy migration checks that the stored sensors belong to this instance (`700–703`). The restore has no such check, so a backup from another house replaces this one's history.
- **`solar_correction_percent` does not survive a restart.** It is saved (`1541`) and restored only by the restore service (`1815–1816`). It is never loaded at startup. The number entity has no restore logic (`number.py`), and the coordinator resets it to the default at construction (`coordinator.py:661`). The key check found three saved keys with no load: this one, and two informational fields (`battery_model`, `last_updated`).
- **Reset leaves most of the 4D and obstruction state.** `async_reset_learning_data` clears the 3D solar maps and buffers and the batch-fit summaries (`1580–1599`). It does not clear the 4D coefficients and buffers, the obstruction gates, or the Tobit sufficient statistics. The docstring says it resets the correlation model, so the gap may be intended. The review found no note saying so.
- **The path check protects one directory.** `_validate_external_path` refuses the `.storage` directory (`589–595`) and allows the rest of the config directory (`596–597`). A backup or CSV export can overwrite `configuration.yaml`, `secrets.yaml` or the recorder database if the path names one of them. Whether that matters depends on who can call the service, which the review did not check.
- **Save failures and CSV rewrites are handled well.** The save is rate-limited (`1453–1457`). A failed write is logged, and `_last_save_time` stays unset so the next save retries (`1577–1578`). A CSV column change writes a temp file and then renames it, so a failed rewrite keeps the original (`2024–2040`).
- **Unverified: live references in the save.** The save dict holds the live model objects, not copies (`1463–1573`). The review did not check whether HA's `Store` serialises them before the next hour-boundary write.
- **Not read:** the migrations (`49–546`), the load path (`695–1431`), and the CSV import and export (`2126–2758`).

**Thirteenth pass: `retrain.py` (partial, `1–160`, `346–1310`)**

- **The dry run is sound.** It swaps copies of the model state onto the coordinator and reinstalls the live objects in `finally` (`retrain.py:435–484`). The strategy distributions are replaced by assignment, so restoring the saved references undoes the replay (`observation.py:527–535`). `resmear_track_c_day` leaves the stored day record alone (`daily_processor.py:79–81`), so a dry run does not write `daily_history`.
- **An hour without a temperature is averaged in as 0 °C.** The Track B flat path averages `e.get("temp", 0.0)` (`retrain.py:879`). Track A defaults the same way (`1051`) and falls back to the bucket `"0"` (`1082`). The degree-day sum at `770` treats the same missing hour as absent, so the bucket and the degree-days disagree about it.
- **A bucket at exactly zero is re-seeded.** The flat path seeds from the raw average when the stored bucket equals `0.0` (`912–917`). A bucket that rounds to `0.0` (`round(…, 5)`, `920`) is therefore replaced, not blended. This is the learned-zero pattern from the solar pass.
- **Two rules for a complete day.** Retrain skips a day with fewer than 22 logged hours (`739`). The balance-point fit requires every hour of the day (`balance_point.py:368`). A day with 22 or 23 hours is accepted by one and rejected by the other.
- **Track B keys the whole day by its mean temperature.** The flat path puts the day's mean temperature into one bucket for all of its hours (`879–881`), while live learning keys each hour. The review found no note on this trade-off.
- **Dead parameter and stale comments.** `_run_daily_pass` takes `_b_flat_delta_source` and ignores it, and its only call passes `"none"` (`725`, `931`). The Track A comment describes a three-pass EM-lite (`991–1012`), but `_run_base_pass` runs once, and `em_passes` is hard-coded to 1 (`986`, `1189`). The comment at `1060` cites `retrain.py:260`, which is now `_per_unit_map_diff` (`261`).
- **Track B COP writes use the unweighted writer.** Lines `856` and `865` call `_apply_strategies_to_global_model`, the writer from the eleventh pass.
- **Not read:** the diff and fit helpers (`158–345`), beyond the parts the dry run calls.

**Fourteenth pass: `balance_point.py` (partial, `1–155`, `275–434`, `920–1204`)**

- **Suggestion only, and the verdict is an ordered ladder.** Nothing is written. A change is suggested only when the fit is not at a sweep boundary or a limit, both halves fit and agree, the COP slope does not move the change point, and the current value is outside the interval and at least 1 °C away (`balance_point.py:1151–1190`). The ladder checks the strongest disqualifier first.
- **Both halves share one outlier pass.** The halves use the outlier mask and weights from all days (`1107–1116`, docstring `929–930`). The docstring states this. The consequence is that a half's stability inherits the full-data outliers.
- **Mirrored constants can drift.** `_COLD_REGIME_DELTA_T = 4.0` and `_BP2_SHIELD_OFFSET = 2.0` (`142–143`) copy the literals at `statistics.py:1769` and `1795`, `learning.py:1292`, and `diagnostics.py:1417` and `1617`. The module says the copies are for counting only. Nothing enforces that they match.
- **Impact skips hours silently.** `_impact` drops hourly entries without `inertia_temp` (`1008–1010`) and does not report how many it dropped. `hours_evaluated` is therefore a subset of the logged hours.
- **The snapshot copies only part of the log.** `daily_history` is deep-copied (`1082–1086`), but `hourly_log` is a list copy whose entries are shared with the live model (`1087`). The docstring gives executor safety as the reason for the copy. The review did not check whether any writer changes a logged entry in place.
- **Completeness rule.** The fit requires every hour of a day (`368–374`), which differs from retrain's 22-hour rule (see the thirteenth pass).
- **Not read:** the solver and its helpers (`155–275`, `434–919`).

**Fifteenth pass: `explanation.py` (partial, `1–310`, `360–406`)**

- **Regime resolution is per described day.** The regime comes from the period being described, not the baseline (`explanation.py:170–200`). The docstring gives the practical reason: the current side stays inside the hourly-log window and the year-ago baseline usually does not.
- **Unknown regimes fall back to heating, and `mixed` suppresses claims.** `_weather_correlation` treats an unrecognised label as heating rather than muting the explanation (`58–71`). `mixed` gets no directional claim at all (`48`). Both choices are stated.
- **Cooling wind is excluded on purpose, and the sensor code agrees.** The cooling wind correlation is `None` (`47`). The cooling driver set in `sensor.py` leaves wind out and holds it fixed across both evaluations (`sensor.py:420–431`). The cross-reference holds.
- **The baseline-less guard works.** A baseline day with no wind and no bucket does not produce a fabricated calm baseline (`239–248`).
- **Contradictions have no size floor.** `_classify` flags a contradiction when the weather moved past its threshold and the kWh change points the other way, however small that kWh change is (`329–339`). The function applies no kWh threshold of its own. The review did not check whether the callers apply one.
- **Period totals and day deltas can use different bases.** The period delta uses `current_total_kwh` when it is given (`365–367`). The comparison caller passes modelled totals (`sensors/comparison.py:709`). Each day's delta uses its own `kwh` (`284–286`). The alignment test compares the day's sign with the period's sign across those two bases (`420–423`).
- **Days are paired by position.** `analyze_period` pairs `period_days[i]` with `baseline_days[i]` and uses the shorter length (`386`, `402–404`). A missing day in one list shifts every later pair. The review did not check that the callers build both lists on the same dates.
- **The baseline bucket can use different thresholds.** The current bucket is the stored label (`236`), set when the hour was logged. A baseline without a bucket is re-derived with the live thresholds (`252–254`). After a threshold change the two buckets come from different threshold sets.
- **Not read:** the category helpers' use in the formatters, and the period statistics and formatters (`406–946`).

**Sixteenth pass: `config_flow.py` (partial, `221–466`, `902–1009`)**

- **The sensor-swap guard holds.** A reconfigure that removes one sensor and adds another at once is refused and pointed at the `replace_sensor` service (`915–918`). The guard protects the learned history of the removed sensor.
- **Clearing a heat-source list may not stick.** Each list is declared as `vol.Optional(field, default=...)` (`640–647`). Voluptuous fills in the default when a key is absent, so if the frontend omits an emptied list, the old selection comes back. `_build_final_data` treats a list as cleared only when the key is present (`444–456`). The review did not check the frontend's behaviour.
- **Cleared optional sensors are removed correctly.** `_clear_absent_entity_keys` pops cleared keys (`338–347`, called at `921`, `935`, `957`, `1001`), and `_build_final_data` strips empty keys (`366–401`).
- **Track C switches daily learning on, and clears its state when the mode is off.** The flow sets daily learning when Track C is on (`383–384`) and clears Track C state when the mode is off (`389–395`). The two settings cannot disagree after a save.
- **Wind units are converted only on one page.** Thresholds are converted from display units only when the feature-config page submitted them (`412–423`). That page is always shown, so the path holds. A future path that skipped the page would store display units as metres per second.
- **The 4D readiness hint fails soft.** A broad except logs a warning with its traceback and returns an empty hint (`266–282`). The form still opens, and the warning is not hidden at the default log level.
- **Migrations run before the save.** The aux and solar learning resets run on the advanced page (`967–980`), and the flow commits later (`984`, `1004`). A cancel on the feature-config page leaves the resets applied and the new settings unsaved. The lesson above covers the fix.
- **Not read:** the module header and constants (`1–220`) and the schema builders (`466–901`).

**Seventeenth pass: `sensor.py` (partial, `155–199`, `405–444`, `931–1010`, `1472–1531`, `1723–1754`)**

- **The projected wind bucket and the logged bucket share a basis.** The collector's `wind_sum` accumulates effective wind (`observation.py:787`), and the projected bucket is taken from that average (`sensor.py:956`). The two buckets are on the same basis.
- **Attributes recompute a model prediction on every read.** `HeatingDeviceDailySensor.extra_state_attributes` recomputes the inertia temperature and a per-unit prediction each time the attributes are read (`1506–1526`). Each refresh therefore costs one model evaluation per unit. The review did not measure the cost.
- **The lifetime throttle runs inside a getter.** `HeatingDeviceLifetimeSensor.native_value` updates its stored value only when it is read and the change is at least 0.1 kWh (`1749–1754`). The reported value therefore lags the true lifetime by up to 0.1 kWh, and the lag depends on how often HA reads the state. The docstring says the aim is fewer database writes.
- **Device names are captured at construction.** The per-unit sensor names come from the source entity's friendly name when the sensor object is built (`1485–1487`, `1736–1738`). A rename in HA reaches these sensors only after a reload.
- **A magic number sets data quality.** A running average is "complete" only above 30 samples (`957`). The number is not a named constant.
- **Not read:** the rest of `sensor.py` (about 1,400 lines), including the comparison, forecast and thermal-state sensors.

**Eighteenth pass: `diagnostics.py` (partial, `1–470`, `1405–1425`, `1608–1622`, `2052–2080`, `2526–2545`, `3235–3275`, `5121–5336`, `5544–5625`, `5716–5726`)**

- **A calibration method changes live state.** `calibrate_per_unit_min_base_thresholds` writes each new threshold into the coordinator (`diagnostics.py:5323`). The `calibrate_unit_thresholds` service reaches it through the coordinator (`__init__.py:1457`). A module that reads as diagnostics therefore holds a writer, and the diagnose calls do not share that risk. The only other write is the battery decay apply path (`3263–3268`), which sits behind an explicit service flag and surfaces why it skipped.
- **Rows without a solar factor count as dark.** The calibration reads `entry.get("solar_factor") or 0.0` (`5212`), so a missing value is treated as sunless. Those rows then enter the dark-hour p10 that sets the floor (`5213`). The same `or 0.0` pattern appears at `1282`, `4049`, `4192` and `5409`, while `625` tests `is not None`. The two conventions disagree.
- **The battery-bias ratio assumes aligned lists.** `_assess_battery_bias` takes the mean residual over all `n` residuals, but the mean expected value over the first `min(n, len(expected))` (`277–281`). If the lists were ever misaligned, the relative deviation would compare different hours. The review did not check whether callers build the two lists on the same hours.
- **The paired screen is honest about its limits.** `paired_loss_improvement` says it is a screen, not a significance test (`79–88`). It adds a selection penalty for the argmin (`124–128`), declines a zero-variance difference rather than dividing by it (`152–165`), and inflates the standard error for lag-one autocorrelation (`167–180`). The docstring reports each limit, so the code is not overstated.
- **The verdicts are ordered and explained.** `battery_decay_verdict` returns the bias reading only when the sweep produced no evidence (`433–436`). The docstring explains why it must not replace a sweep answer (`419–431`). The retired k sweep is kept as evidence and is reported as `research_` rather than `consider_` (`367–371`).
- **The determinant gate is absolute.** The 2×2 and 3×3 normal-equation solves accept a system only when `abs(det) > 1e-6` (`2075`). The determinant scales with the units of the sums, so the same gate passes or rejects a near-singular system depending on the units. The review did not measure a case where it matters.
- **Temperature bands are repeated and the comments disagree.** The deep and mild heating bands use `bp − 8` and `bp − 2` (`1415–1417` and `1613–1615`). The balance-point pass cited these at `1417` and `1617`; the literals are at the lines given here. The mode-split comment says the transition zone is `BP−2 ≤ T ≤ BP` (`1621`), but the heating branch drops everything from `BP−2` upward, and the cooling branch starts at `BP+2`. The comment is narrower than the code.
- **A broad except swallows a 4D replay.** `_replay_4d_solar_total` returns `None` on any exception (`5620`). The caller therefore cannot tell a missing input from a bug. The Tobit branch right above it records the exception class and message (`2532–2540`), so the two sites handle the same kind of failure differently.
- **Production code is guarded against test mocks.** The sun-position lookup catches all exceptions with the comment "defensive against mocks" (`5722`). A test double should not shape production error handling. Catching only the errors `get_approx_sun_pos` can raise would be narrower.
- **Not read:** `diagnose_model` (`454–1043`) beyond its header and the bucket split, `diagnose_solar` (`1072–4006`) beyond the spans above, and the shadow reports and divergence blocks after `4007`.

**Nineteenth pass: `helpers.py` (full, `1–934`)**

- **The EMA helper has one caller, and the docstring names three.** `compute_base_ema_step` says it is "the single arithmetic source of truth" for live learning, the retrain path and the diagnostic (`helpers.py:893–931`). Only `diagnostics.py:5466–5469` calls it. The live writer multiplies `learning_rate * snr_w` inline (`learning.py:1378`), and the retrain path computes `learning_rate * max(0.0, snr_weight)` inline (`learning.py:3207`). The #967 drift guard therefore covers the diagnostic only. The live and retrain formulas can change without the diagnostic noticing.
- **Asymmetric inertia has a weight jump at the trend threshold.** `calculate_asymmetric_inertia` switches weight profiles at ±0.5 °C over four hours (`helpers.py:690–698`). Just above the threshold the current reading gets 0.20 (shedding) or 0.50 (gaining), and just below it gets 0.33 (stable). The effective temperature can therefore jump as the trend crosses 0.5 °C. The function has no hysteresis. Its one caller is `statistics.py:3839`.
- **Speed units are matched exactly.** `convert_speed_to_ms` compares the unit string against fixed names (`helpers.py:20–36`). An unrecognised spelling, such as `KM/H`, falls through with a warning and is returned as metres per second. That would overstate the wind by a factor of 3.6. The review did not check what the weather providers actually emit.
- **Missing kWh is read as zero, and that is documented.** `unit_hour_reported_kwh` treats an absent unit as a 0 kWh reading once it has reported before (`helpers.py:293–304`). The docstring states the cost: an hour in which a sensor really was offline is learned as zero. The rule is a deliberate trade, not a hidden one.
- **The balance-point inference is tolerance-based.** `infer_tdd_balance_point` requires at least six usable slots and 90 % agreement within 0.15 °C (`helpers.py:440–458`). A day logged under two balance points returns `(True, None)` or `(False, None)` rather than a guess. The docstring explains each case.
- **The degree-day fallback drops the straddle.** Without an hourly vector, `daily_tdd_at_balance_point` uses `|BP − T_avg|` (`helpers.py:545–547`). The docstring says this drops the extra degree-days of a day that crosses the balance point, and that the error is small. The review did not measure it.
- **Local imports repeat across the file.** `dt_util` and `tzinfo` are imported inside `local_day_hours`, `as_utc_instant`, `timestamp_instant` and `hour_slots`, and `tzinfo` is already imported at module level (`helpers.py:5`, `487`, `586`, `600`, `635`). This is style, not a defect.
- **The solver's pivot floor is absolute.** `solve_gauss_jordan` rejects a pivot below `1e-12` (`helpers.py:847`). Like the 4D normal-equation gate, that depends on the scale of the inputs.
- **Not checked:** whether each caller of the inertia helpers passes the same window convention.

**Twentieth pass: `heat_source.py` (full, `1–325`)**

- **A cooling-mode test uses the system mode, not the unit's own state.** `classify_unit` calls a unit reversible when it used at least `HEAT_SOURCE_REVERSIBLE_MIN_KWH` on enough heating-mode days and on enough cooling-mode days (`heat_source.py:158–165`). The cooling-day count uses the system's mode for that hour (`138–155`), not anything the unit reports. A shared meter, such as a circulation pump or dehumidifier, that draws energy in cooling mode would pass the test for a direct electric load. The docstring says a shared meter gets the class of its dominant load, but it does not address this case.
- **A unit needs about 75 days to be classified, and the reason label hides this.** The coldest 20 % of days are removed for the second fit (`heat_source.py:203–205`, `const.py:938`). The fit needs `BP_CALIBRATION_MIN_DAYS`, which is 60 (`const.py:1138`; `_curve_fit`, `108–110`). A unit with 60 to 74 days therefore always has fewer than 60 trimmed days, its trimmed curve is `None`, and `classify_unit` returns `curve_changes_without_coldest_days` (`168–169`). That label reports a curve change, but the cause is the sample size. The review did not check whether any test covers the 60–74 band.
- **The provenance rule is not enforced.** The module says a consumer that needs the COP level must use only `user` or `mpc` types (`heat_source.py:38–42`). The consumers in the codebase read `heat_source_for` for the curve shape (`balance_point.py:1073–1080`) and for display (`select.py:88–91`). I found no code path that reads `provenance` before using the COP level. The rule is a contract with no check.
- **Hysteresis is clear.** `apply_evidence` adopts the first class at once, requires `HEAT_SOURCE_SWITCH_RUNS` consecutive runs for a change, and breaks the streak on an unclassifiable run (`heat_source.py:243–282`). The docstring states each rule and the code matches it.
- **A user override outranks evidence, and the MPC sensor is fixed.** `resolve_heat_source` checks the user type first, then the MPC sensor as a heat pump, then the inferred class (`298–320`). An override therefore keeps working when the evidence changes.
- **Not read:** the `collect_days` and `sweep` functions this module calls in `balance_point.py`, and the coordinator code that calls `heat_source_for`.

**Twenty-first pass: `solar_optimizer.py` (full, `1–164`)**

- **A single observation sets the screen position outright.** The first observation for a state, azimuth and elevation bucket is stored at full weight (`solar_optimizer.py:103–105`). Later observations move the value by 0.1 of the gap (`109`). One click on a bright day can therefore set a bucket, and about seven later observations are needed to move it halfway back. The review did not check whether the user's manual adjustments are noisy enough for this to matter.
- **The cloud gate depends on the caller.** Learning is skipped at 20 % cloud cover or more (`88–90`). The only caller passes `cloud_cover=current_cloud` (`hourly_processor.py:450`). The default of `0.0` would let every hour through if a future caller omitted the argument, and the gate would fail silently.
- **The legacy migration comment says "deep copy" but the code makes shallow copies.** Each azimuth bucket receives `state_data.copy()` (`solar_optimizer.py:157`). The values are floats, so a shallow copy is correct. The comment should say so.
- **The stored model is returned by reference.** `get_data` returns `self._model` itself (`116`). Whether the storage layer serialises it before the next write is the same open question as the save path in the storage pass.
- **Lookup falls back to a fixed default, not to a neighbour.** `predict_correction_percent` uses the learned value only for the exact bucket and otherwise returns the state default: 100 % for maximise, 0 % for insulate or mitigate (`72–79`). A bucket one step away from a learned one gets the default, not the learned neighbour. This is a design choice, and the review did not find a note on it.
- **The rounding is fixed at one decimal.** The EMA result is rounded to one decimal place (`110`), but the first observation is stored unrounded (`105`). The two paths store different precision.
- **Not read:** the caller in `hourly_processor.py` beyond the call at line 450, and the entity that displays the recommendation.

**Twenty-second pass: `switch.py` (full, `1–102`)**

- **The learning switch saves without forcing.** `HeatingLearningSwitch.async_turn_on` and `async_turn_off` call `_async_save_data()` with no `force` (`switch.py:65`, `71`). The save is rate-limited to one per 60 seconds (`storage.py:1455–1457`). A switch change within a minute of the last save is held in memory until the next save. A crash before that save reverts the switch on restart. The stop handler does force a save, so a clean shutdown keeps the change.
- **The auxiliary switch writes through a different path.** Its handlers call `set_auxiliary_heating_active` (`switch.py:92`, `97`), which saves without force (`coordinator.py:813`) and then notifies listeners (`816`). The learning switch does neither, so the two switches do not refresh the same way.
- **The learning switch reads its flag only when told to refresh.** `is_on` returns `coordinator.learning_enabled` (`switch.py:60`). The learning switch never calls `async_write_ha_state` except after its own writes. The flag is also written by load and restore (`storage.py:1270`, `1796`). The review did not check whether restore notifies listeners, so a restore may leave the switch showing the old state until the next coordinator update.
- **Both switches are config-category entities.** `_attr_entity_category = EntityCategory.CONFIG` (`switch.py:33`) keeps them out of the default dashboard. That is a presentation choice and matches the aim of a config control.
- **Not read:** nothing; the file is short and read in full.

**Twenty-third pass: `repairs.py` (full, `1–199`)**

- **The repair check hides its own failures at the default log level.** `async_check_dni_dhi_outage` catches every exception and logs at `DEBUG` (`repairs.py:111–112`). The docstring says a registry failure must not break hourly processing. Keeping that promise means a broken issue registry is invisible unless debug logging is on. A warning, rate-limited so it does not repeat every hour, would hold the promise and still show the problem.
- **Demotion is one-way, and the docstring explains why.** The file does not offer promotion back to 4D, because an untrained 4D regime returns the zero vector and would silently remove solar from predictions (`repairs.py:16–19`). The reasoning is sound and the flow matches it.
- **The fix flow is not exercised by tests.** The comment at `repairs.py:133–138` says the test suite stubs the whole repairs module, so the confirm form is never rendered. The no-form path and the `vol.Schema({})` choice are therefore not tested by anything in the repository. The review did not run the flow.
- **Each failure path aborts rather than succeeds.** A missing `entry_id` aborts (`repairs.py:158`), as does a missing entry (`168`). Both are reported as failures, so HA's repair manager does not clear the card for a fix that did not happen.
- **The issue auto-clears through the verdict, not through the flow.** The check deletes the issue on `clear` or `not_applicable` (`repairs.py:104–112`). If the reload at `177` fails after the data is written, the issue stays until the next hour boundary. Because 4D is no longer routed, the verdict then becomes `not_applicable` and clears it. The chain holds, but it depends on the next hour boundary running.
- **The issue is not persistent by design.** The docstring says a restart clears the card until the next hour boundary re-raises it (`repairs.py:72–74`). That means a warning can be missing for up to an hour after a restart, which the docstring accepts.

**Twenty-fourth pass: `__init__.py` (partial, `296–330`, `419–460`, `445–500`, `1258–1316`, `1441–1466`, `1594–1693`, and the service registration list)**

- **Final save on unload is not forced.** `async_unload_entry` pops the coordinator and calls `_async_save_data()` with no `force` (`__init__.py:1649–1652`). The stop handler forces the same save (`438`). A reload inside the debounce window can therefore lose the changes made since the last save. The loss is bounded to the 60-second window, but the two final-save paths disagree.
- **A missing entity sends a destructive call to the first instance.** `_get_target_coordinator` returns the first coordinator when `entity_id` is absent (`__init__.py:304–325`, its docstring says so). The reset-learning schema makes `entity_id` optional (`114–116`), so on a two-instance install a reset with no entity clears whichever instance loaded first. The review did not find a guard for this.
- **Replacing a sensor without an entity touches every matching instance.** Without `entity_id`, `handle_replace_sensor` applies the replacement to every coordinator that holds the old sensor, then reloads each one (`__init__.py:1307–1314`). This is a legacy path, and it is consistent. It is also the one service that can change several instances from one call.
- **Every registered service has a removal line.** The setup registration list and the unload removal list each name 30 services, and the two sets match (`__init__.py:1655–1691`). The match holds today, but nothing enforces it: a new service must be added to both lists by hand.
- **The calibration docstring disagrees with the code.** `handle_calibrate_unit_thresholds` says thresholds "are persisted on the next storage save" (`__init__.py:1443–1446`), but the code forces a save when the result changes (`1463`). The forced save is the right behaviour, and the docstring should say so.
- **Any setup failure is reported as a timeout.** The first refresh is wrapped in a broad except, and every failure is rethrown as `ConfigEntryNotReady("Timeout while waiting for initial data: ...")` (`__init__.py:425–428`). A programming error appears to the user as a timeout. The original exception is kept in the chain, but the message is misleading.
- **Migrations chain through the version attribute.** A version-1 entry is updated to version 2 and then falls into the version-2 branch in the same call (`__init__.py:1600–1646`). That relies on `async_update_entry` changing `config_entry.version` synchronously. The review did not check that behaviour in the Home Assistant version the integration targets.
- **Not read:** the module header and constants (`1–295`), the forecast summary (`327–418`), most service handlers (`460–1257`, `1316–1440`, `1475–1593`), and the coordinator wiring they call.

**Twenty-fifth pass: `number.py` (full, `1–110`)**

- **Both number writes save without forcing.** `HeatingLearningRateNumber.async_set_native_value` and `HeatingSolarCorrectionNumber.async_set_native_value` call `_async_save_data()` with no `force` (`number.py:76`, `103`). A slider change inside the 60-second debounce window is held until the next save, as with the switches. The stop handler forces a save, so a clean stop keeps the value.
- **The solar correction does not survive a restart.** The value is written to storage (`storage.py:1541`, `1644`) and read back only by the restore service (`1815–1816`). The load path never reads it, and the coordinator resets it to the default at construction (`coordinator.py:661`). The slider therefore returns to the default after every restart, although the entity reads the live value. The storage pass found the same gap; this is the user-visible result.
- **The learning-rate range is wider than the default.** The slider runs from 0.1 % to 10 % (`number.py:62–64`). The default is 1 % (`const.py:8`), so the top of the range is ten times the default. The review did not check whether the learning formula is stable at 10 %.
- **Only the solar slider refreshes the model.** The solar slider requests a refresh so the recommendation updates at once (`number.py:106`). The learning-rate slider does not. The two controls therefore behave differently after a change.
- **Both numbers are config-category entities** (`number.py:39`), as the switches are. The presentation choice is consistent.
- **Not read:** nothing; the file is short and read in full.

**Twenty-sixth pass: `select.py` (full, `1–104`)**

- **The mode select saves without forcing.** `async_set_unit_mode` writes the mode and calls `_async_save_data()` with no `force` (`coordinator.py:1146`). It is the same unforced path as the switches, reached from a user control.
- **Provenance is shown to the user, but nothing checks it.** The entity exposes `heat_source_provenance` and the evidence (`select.py:89–95`). This makes the provenance rule from the heat-source pass visible, but the entity does not check it before a consumer uses the class. A user can therefore see a `user` or `mpc` label, and the label is not enforced anywhere else either.
- **The evidence is kept out of the recorder.** `heat_source_evidence` is listed as an unrecorded attribute (`select.py:51`). The comment says it changes weekly at most. This is a good use of the recorder setting.
- **The attributes recompute on every read.** `extra_state_attributes` calls `heat_source_for` each time the state is read (`select.py:88`). The cost is not measured.
- **The friendly name is captured at construction.** `state.name if state else source_entity_id` (`select.py:63–65`) reads the source entity when the select is built. If the source is not loaded yet, the name falls back to the entity id and does not update on rename. The sensor pass found the same pattern.
- **Mode is keyed by the source entity id.** The unique id and the stored mode both use `source_entity_id` (`select.py:59`, `100`). If a sensor is replaced, the select and the stored mode may no longer point at the same unit. The review did not check the replace path for this.
- **Cooling modes are always offered.** Every energy sensor gets a select with all six options, whatever its capability (`select.py:31–38`). The comment states this is deliberate.
- **Not read:** nothing; the file is short and read in full.

**Twenty-seventh pass: `hourly_processor.py` (partial, `1–160`, `316–366`, `420–460`, `770–815`, `1205–1298`)**

- **The boundary guard does not cover the CSV row.** The guard refuses a duplicate entry in memory and warns (`hourly_processor.py:1260–1263`). The info log (`1270`) and the CSV append (`1273`) sit outside that `if`, so they run whether or not the entry was added. The CSV path takes the entry as passed (`storage.py:2064–2073`). The review did not read the write step to confirm whether it de-duplicates.
- **The 4D override fallback is silent.** `_resolve_4d_boundary_overrides` returns `None` on any exception (`146–149`), and the caller falls back to the 3D form. The docstring says the mixed pipeline is the defect this avoids (`91–95`). The fallback reintroduces it for that hour, with no log line.
- **The 4D battery update swallows errors.** A failure in the 4D battery update is caught and passed over (`794–799`). The battery then decays toward zero on the next clean hour. The 3D fallback above it is also silent (`800–803`). A malformed solar state loses stored battery energy without a trace.
- **The cloud gate uses a different basis from the correction.** The correction is an hour average (`426–429`), and the comment says averages are used for consistency (`423–425`). The cloud gate reads the value at the close of the hour (`439`). `_get_cloud_coverage` returns `50.0` when no weather entity or state is available (`coordinator.py:2228–2235`). The solar gate skips learning at 20 % or more (`solar_optimizer.py:88`). An install with no weather entity therefore never trains the solar optimiser. The review did not check whether that is documented.
- **The cooldown can hold for the full six hours without evidence.** The lock exits on convergence at 0.92 after two hours, or at six hours regardless (`hourly_processor.py:334–361`, `const.py:482–484`). When the expected consumption is below the 0.01 kWh guard, the code logs "No expected consumption to verify convergence" and keeps the lock until the six-hour limit.
- **The hour-boundary save is the one forced save on the hot path.** The boundary save passes `force=True` (`1293`), so the hourly log is written at each boundary. This is the pattern the unforced saves should follow.
- **The repair check runs before the forced save.** The DNI and DHI check is placed after the log append and before the save (`1285–1290`). It relies on the broad except in `repairs.py` (pass twenty-three) to never raise.
- **Not read:** `build_observation` and `_forecast_point_kwh` (`151–315`), the learning call and the solar block (`460–769`), and the battery and breakdown code (`815–1204`).

**Twenty-eighth pass: `observation.py` (full, `1–870`)**

- **The parasitic-floor check ignores the per-unit noise floor.** `detect_solar_shutdown_entities` reads a per-unit threshold (`observation.py:116–120`) and applies it only to the ratio test (`142`). The absolute check runs first and tests only `base > 0` and `actual < 0.03` kWh (`138–140`). A unit whose calibrated noise floor is 0.05 kWh can therefore be flagged as shut down from a 0.02 kWh reading, which its own calibration reads as noise. The override added for #871 does not reach this path.
- **A zero reading drops the unit from learning.** `DirectMeter` returns `None` for a reading of zero or less (`493`), and `WeightedSmear` does the same (`559`, `565`). A unit therefore learns only from hours in which it drew power. That is a stated choice, but the review did not check its effect on mild-weather buckets, where a unit is most often off. The helpers pass found the opposite rule for missing kWh.
- **The solar-correction average is safe today.** `accumulate_weather` defaults `correction_percent` to 100 (`779`), which would record screens open for any caller that omitted it. The only caller passes the live value (`coordinator.py:3449`), so the default is not used.
- **The learning-config default turns the Tobit learner off.** `LearningConfig.experimental_tobit_live_learner` defaults to `False` (`220`), while its comment says the live learner is default-on from 1.3.5. The coordinator sets it to `True` (`coordinator.py:278`). A `LearningConfig` built without the coordinator, such as a test or a replay, runs NLMS only. The comment describes the user setting, not the dataclass default.
- **Expected energy drops negative rates.** `accumulate_expected` adds a rate only when it is positive (`839`, `847`), so a negative prediction contributes zero. The hour's expected total is therefore a clipped sum. The code does not say whether this is intended.
- **Reset clears every slot.** `ObservationCollector.reset` clears each name in `__slots__` (`729–767`). The review checked the list by hand. A test that compares the slots with `reset()` would keep that true as fields are added.
- **The strategy list is a single source.** `hourly_learning_sensors` is the one function that live learning and the retrain replay both call (`595–617`, docstring `606–610`). This is the pattern the EMA helper lacked (helpers pass).
- **Not read:** nothing; the file is read in full.

**Twenty-ninth pass: `thermodynamics.py` (full, `1–389`)**

- **The day's heat lands on the hours that are not in full sun.** In the heating branch the solar multiplier is the solar factor clamped to `[0, 1]` (`thermodynamics.py:144`). A factor of 0 gives an hour zero weight, so that hour's share of the day's thermal energy goes to the other hours. The docstring calls the factor a "reduction factor (0.0 to 1.0)" (`51`) and does not say whether 0 means full sun. The cooling branch treats a low factor as sun (`141`), which implies 0 is full sun. Whether the factor reaches 0 in practice was not checked.
- **A length mismatch is warned once, then copied.** When there are more MPC hours than weather rows, the last weather row is reused for each extra hour (`230–233`). The only signal is one warning at the start (`178`). The extra hours are then priced at the last hour's weather.
- **The COP default lives in two places.** The `CopParams` docstring says the defaults come from `cop_at_conditions()` (`66`). That function has no default for `f_defrost` (`96`), and the value 0.85 is set in `_hour_cop` instead (`331`). The value is not confirmed against the MPC model.
- **The outdoor fallback has the wrong sign for cooling.** `_hour_cop` rebuilds the outdoor temperature as `balance_point − delta_t` (`327`). The loss-weight docstring defines `delta_t` as `abs(balance_point − outdoor)` (`125`), and the producers build it that way (`daily_processor.py:816`, `1006`). The rebuild is right only for heating. The `WeatherData` type requires `outdoor_temp`, so the fallback should not run. It is a latent defect, not a live one.
- **The `WeatherData` docstring disagrees with the producers.** The type says `delta_t` is "Indoor Temp - Outdoor Temp" (`49`). The producers use an absolute value, as above.
- **The COP guards are explicit.** A non-positive lift returns COP 1.0 (`112–113`), and the result is clamped to `[1, 10]` (`117`). A zero-COP day falls back to 1.0 (`197–200`). Each guard is documented.
- **DHW hours keep their share of heat.** A DHW hour still receives its share of the day's thermal load, and the reasoning is stated (`366–371`). This is a deliberate choice with its argument written down.
- **Re-smearing recovers the COP from rounded values.** With no stored COP, `resmear_distribution` takes the ratio of rounded kWh (`309–310`) and uses the day mean below 0.01 kWh (`262–264`, `311–312`). The docstring states the rounding bound. The review did not measure the error on a real day.
- **One smearing function serves both paths.** `_smear` is the single implementation for the midnight sync and the retrain re-smear (`346–355`).
- **Not read:** nothing; the file is read in full.

**Thirtieth pass: `const.py` (references and selected values only)**

- **Eight names have no reference.** `CONF_SOLAR_CORRECTION`, `DEFAULT_LEARNING_RATE`, `HEAT_SOURCE_AIR_TO_AIR`, `MS_TO_KMH`, `MS_TO_KNOTS`, `THERMAL_INERTIA_FAST`, `THERMAL_INERTIA_NORMAL` and `THERMAL_INERTIA_SLOW` appear only in `const.py`. The three inertia names look like leftovers from a fast, normal and slow choice. The flow now takes hours (`config_flow.py:516–529`).
- **The learning-rate default is kept in two places.** `DEFAULT_LEARNING_RATE` (`const.py:8`) is unused. The default is the literal `0.01` at `coordinator.py:637`, which appears twice on that line.
- **No name is defined twice.** A duplicate check found none, so a later definition cannot silently replace an earlier one.
- **The cited values match.** The shutdown constants (`279–288`), the heat-source constants (`938–951`) and the balance-point constants (`1138–1139`) agree with the values cited in earlier passes.
- **Not read:** the remaining values, about 330 names. They were checked for references and duplicates only.

**Thirty-first pass: `balance_point.py` (solver and sweep, `155–275`, `434–1000`)**

- **The COP weight has a floor the docstring leaves out.** `_prefix_tables` and `_table` use `w = 1 / max(BP_CALIBRATION_COP_FLOOR, 1 + κ·t)` (`balance_point.py:253`, `268`), with a floor of 0.25 (`const.py:1093`). The `degree_hours` docstring gives `(1 + κ·T)` alone (`437`). At the largest slope (0.05 per °C) the floor binds below −15 °C, so the weights for colder hours differ from the printed formula. The cooling branch uses κ = 0, where the floor (0.25) is below 1, so its weights are 1 and the cooling sums are correct.
- **The fast path and the fit agree.** `_fast_sse` (`573–616`) expands the weighted SSE from sums, and its algebra matches `fit_change_point`, including the through-origin refit when the floor is negative (`502–508`, `606–610`). The two paths compute the same quantity, so a test that checks one against the other would keep them aligned.
- **The weighted inertia helper falls back silently.** `_weighted_inertia` returns the unweighted mean when the used weights sum to zero (`240–241`). `helpers.weighted_inertia` normalises the used weights and returns `None` when no reading is usable (`helpers.py:707–729`). The docstring says the weighting is the same. I did not check whether the zero-weight case can occur, nor where the gap cut at `tau` is applied; the `_inertia_kernel` docstring places it in the coordinator.
- **A failed first pass drops the outlier step without a separate flag.** When `variance_prior` returns `None`, `sweep` runs the unweighted fit on every day (`balance_point.py:968–973`). The result then shows `weighted: false` and `outlier_days_dropped: 0`. The status is `fitted`, so the only signal is the `weighted` field.
- **The outlier median is the upper middle value for an even count.** `_outlier_mask` takes `values[len // 2]` for the median and the MAD (`909–910`). With an even number of days the median sits half a sample high. The effect on the threshold is small, but the convention should be stated.
- **The interval is limited by the sweep step.** `in_interval` and the reported `interval` are the minimum and maximum of the candidates inside the threshold (`744`, `762`), so the true profile-likelihood edges are only located to the nearest grid step. The step is `BP_CALIBRATION_SWEEP_STEP_C`, and it is not reported beside the interval.
- **The stability check withholds an answer at the limit.** `_cop_sensitivity` returns `stable: None` when the best slope is at its upper limit (`851–860`), rather than calling the change point stable. The comment explains why.
- **The variance weights are capped and rescaled.** `_variance_weights` floors the constant term and caps the weight ratio, then rescales to mean 1 (`889–894`), so the weighted SSE stays on the unweighted scale. The docstring states each step.
- **Not read:** the report and impact functions (`1001–1204`) were read in the fourteenth pass.

**Thirty-second pass: `retrain.py` (diff and fit helpers, `158–345`)**

- **A tolerance hides small bucket changes.** `_bucket_map_diff` counts a bucket as changed only when the change exceeds `_DIFF_TOLERANCE = 1e-9` (`retrain.py:103`, `225`). That is effectively exact equality, so the diff reports every change. The constant is fine. A change below it would not be counted, and no test of this was found.
- **A legacy bare value shares a key with a real bucket.** `_flatten_buckets` stores a bare number under bucket `-` (`177–196`). A legacy global map and a current map with a real bucket named `-` would therefore be compared as the same cell. The review did not find a case where both shapes coexist.
- **Unparseable temperatures become `unknown`.** `_temp_band` returns `unknown` for a non-numeric or non-finite value (`158–167`), and `_band_order` sorts it last (`170–174`). The diff therefore reports bad keys in one visible group rather than dropping them.
- **The diff is a report, not a gate.** `_model_diff` only describes what the retrain changed (`310–331`). Nothing in these helpers rejects a retrain, so the size of a change is visible but not limited.
- **Not read:** nothing in `158–345` is left unread.

**Thirty-third pass: `storage.py` CSV export and import (`2126–2758`)**

- **A weather-only import rewrites the balance-point fields of old rows.** The row builder sets `tdd` and `bp_at_log_time` from `self.coordinator.balance_point`, the current value (`storage.py:2383–2384`, `2415–2416`). The field-conditional merge copies both onto matching existing log entries (`2559–2563`). An enrichment file for last winter therefore changes last winter's degree-hours to today's balance point. The `solar_factor` and irradiance fields carry no such dependency.
- **A repeated full import learns again.** Track A learns each row in `_process_csv` (`2432–2449`) before the duplicate filter runs (`2707–2708`), which only protects the log. The daily batch learns every complete day with no check against what is already learned (`2460–2489`). The review did not run a repeat import to measure the size of the effect.
- **Track A's temperature is a plain four-sample mean.** The import keeps the last four temperatures (`2433–2437`) and averages them with no gap cut. The live path uses the inertia kernel and cuts history at a gap longer than `tau` (see the balance-point pass, and `balance_point.py:203–209`). Imported rows across a long gap therefore get a different temperature key from live rows for the same hour.
- **Two identities for the same hour.** The weather-only join uses the UTC instant (`2520–2526`). The full import removes duplicates by the raw string (`2707–2708`), and the sort uses the instant (`2713–2716`). The comment at `2711–2712` describes the DST fall-back case, which the string test does not handle.
- **The hourly export takes its columns from the first row.** `fieldnames` is built from `data[0]` only (`2216–2217`), and the row filter drops any key that is not in that list (`2229`). A key first written later in the log is therefore never exported, and no error is raised. The schema is fixed by the oldest row.
- **Unit columns follow the current sensor list.** The hourly export writes `unit_{i}_actual` by position in `energy_sensors` (`2220–2235`). If the list changes, the same column name can mean a different meter in old and new rows. The review did not check whether the list is stored with the log.
- **Three thresholds for the same guard.** A day with fewer than 22 hours is skipped in daily learning (`2467`), a day with fewer than 20 is skipped for vectors (`2583`), and the warning says "/24". The retrain path uses 22 (earlier pass).
- **A row that fails is skipped with a warning.** The per-row `except` (`2453–2455`) logs the row and continues. A bad energy value in a large file is therefore a warning, not a failed import. The count of skipped rows is not returned, so the summary says nothing about them.
- **Hour folding follows the aggregate rules.** Rows of one local hour are averaged (`2612–2629`), their degree-hours are summed (`2633–2636`), and the slot count is kept for the DST day (`2642–2650`). The comment states the rule, and the code matches it.
- **Not read:** nothing in `2126–2758`.

**Thirty-fourth pass: `explanation.py` (`406–946`)**

- **The "similar" threshold differs by formatter.** `format_period_comparison` calls a change similar at 5.0 kWh (`explanation.py:673`), `format_day_comparison` at 3.0 kWh (`688`), and `format_comparison_summary` at 1.0 kWh (`867`). A user can see "similar" on one sensor and a number on another for the same change.
- **A cold-weather phrase is returned for a hot day.** `format_forecast_weather_context` sets `is_significant = temp < 12 or wind ≥ 3` (`940`). A day at 25 °C with calm wind is not significant, so it returns "Mild conditions (25.0°C)" (`946`). The "hot" and "warm" categories (`931–932`) appear only when the wind is at least 3 m/s. The label for a hot calm day is therefore wrong.
- **Both branches of the driver test are the same.** In `analyze_period`, the `delta_kwh > 0` and the `else` branches (`426–435`) add the same three factors in the same order. The comments describe different drivers (cold, wind and low sun against warm, calm and high sun), but the code does not distinguish them, so the branch has no effect.
- **The idle abstention is documented.** A day with regime `idle` does not vote (`445–468`), and the docstring gives the case that motivates it, a single away day hiding a cold week. The rule matches the comment.
- **The contradiction margins are asymmetric on purpose.** Temperature and wind need 0.5 to contradict, solar needs −0.5 (`522`). The comment says the asymmetry predates the change and is kept. The review did not check whether the asymmetry is still wanted.
- **A legacy fallback keeps a consumption-based direction.** `_get_factor_description` infers weather from `delta_kwh` when no weather delta is given (`817–824`), and the docstring says this matches heating only. Callers that do not pass `weather_delta` will describe a hot week as cold under cooling.
- **The wording is chosen from the weather sign.** `format_day_comparison` derives "colder" and "windier" from the weather delta (`707`, `722`), not the consumption delta. The comment gives the cooling case that required this.
- **Not read:** `analyze_day` and `_weather_correlation`, which this pass did not open.

**Thirty-fifth pass: `config_flow.py` schema builders and setup steps (`466–901`)**

- **The feature-config step cannot fail validation.** `errors` is initialised to `{}` and never set in `async_step_feature_config`, so `if not errors:` (`config_flow.py:885`) is always true. An invalid entry in that step is saved without a message.
- **The inertia strings are literals, not constants.** A string inertia value is mapped by `{"fast": 2, "slow": 12}.get(inertia, 4)` (`518`). The thirtieth pass found the `THERMAL_INERTIA_FAST`, `_NORMAL` and `_SLOW` names unused in `const.py`, and this mapping does not use them either. The three values live in this one literal.
- **Experimental knobs are on the routine page.** The hotspot attenuation γ, and the tail-redistribution α and τ, are offered on the advanced page with no flag (`config_flow.py:661–686`). Their defaults are no-ops (0.0, 0.0, 2.0 h), so nothing changes for a user who ignores them. Only the 4D toggle is gated behind reconfigure. Every user sees three untested controls.
- **The new-sensor default is asymmetric by design.** Solar-affected sensors default to checked when new (`467–486`), while screen and aux sensors default to unchecked (`621–622`). The comment gives the reason: a wrong solar default injects phantom coefficients. The code matches the comment.
- **The string-typed select is cast on purpose.** The retention option is read back as a string, and the comment says a missing cast would reset the user's choice on a no-op submit (`697–700`). The fix is in place and explained.
- **Wind thresholds are converted for display only.** The feature page converts stored thresholds from m/s to the chosen unit (`776–788`), and the maxima follow the unit (`790–791`). The stored values stay in m/s. The review did not check the round trip from km/h back to m/s.
- **Advanced-page conflicts keep the other answers.** On a heat-source conflict the form is rebuilt from `user_input` (`853–858`), so the user's other answers stay on screen. Nothing is written to `_flow_data` until the conflict clears.
- **Not read:** the reconfigure steps (after `900`), and the module header and constants (`1–220`), which are still open.

**Thirty-sixth pass: `hourly_processor.py` (`151–315`, `815–1204`)**

- **Two rounded fields have no `None` guard.** `forecasted_kwh` and `forecasted_kwh_primary` and `_secondary` are rounded directly (`hourly_processor.py:1138–1140`). The three gross fields below them check for `None` first (`1141–1143`). `build_observation` defaults the forecast arguments to `None` (`173–178`). The review did not check whether any caller passes `None` here. If one does, the `round` call raises and the hour's log entry is not written.
- **The per-unit learning flag is three-state.** `should_learn_per_unit` is `None` unless daily learning is on (`827`), and is then a boolean. A dual-interference hour sets it to `False` only when it is not `None` (`839–840`). The comment (`834–838`) explains the rule, and the code matches it.
- **Dual interference blocks every learning path.** Both the global and per-unit flags are cleared when solar and aux both exceed the threshold (`831–840`). The hour is logged as `skipped_dual_interference` (`1054–1056`), and the comment says replays read that label. The rule is stated and enforced in one place.
- **Shutdown-hour normalisation is corrected before the learning call.** Units flagged as solar shutdown have their applied solar removed from `solar_normalization_delta` (`880–896`), so the global base does not learn an inflated delta. The order matters: the detection runs at `861`, the correction at `880`, and the learning at `999`.
- **The gross adjustment uses the mode split, not temperature.** `solar_adjustment` is the solar impact times the signed heating-to-cooling share (`1078–1083`). The comment (`1059–1071`) gives the two cases where the old temperature rule was wrong. The fallback for a no-solar hour classifies by the active unit modes (`1084–1098`), and drops the adjustment on a mixed hour.
- **Tdd uses the absolute difference.** `tdd_contribution = abs(balance_point − avg_temp) / 24` (`1007`) matches the producers' convention. The `WeatherData` docstring disagrees with this (the twenty-ninth pass).
- **The solar-normalisation sign follows the mode.** Heating units subtract the applied solar and cooling units add it (`893–896`). The sign is written next to the mode test, so it can be checked by reading.
- **Unit logs keep zero hours separate from absent meters.** `units_reporting` lists every meter that reported, zero hours included (`1017–1022`), because `unit_breakdown` drops zero values (`1012–1016`). The comment says replays need this to tell a learned zero from an offline sensor.
- **The shadow path is kept off the main tuple.** `_forecast_point_kwh` reads `result[0]` rather than unpacking the whole tuple (`289–307`). The docstring says the tuple grew from 8 to 12 fields and an exact unpack crashed the live loop. Tests then fed `None` items, which hid the crash. The docstring records that failure, which is the reason the test gap is noted.
- **Not read:** the learning call and the solar block (`460–769`), which remain open.

**Thirty-seventh pass: `sensor.py` (`1–450`)**

- **A per-unit breakdown can lose a unit.** `HeatingEnergyTodaySensor.extra_state_attributes` keys `unit_breakdown` and `unit_contribution_pct` by the friendly name (`sensor.py:235–243`). Two meters with one friendly name, or a name that is captured before the entity loads (the same pattern as the select pass), overwrite each other. The total still reports both, so the breakdown can sum to less than the total with no sign of why.
- **The expected-energy sensor does the most work on every read.** `extra_state_attributes` calls `calculate_total_power` four times for the driver breakdown (`412–444`), plus a solar factor lookup (`407–410`). It runs on each state read, not each update. The review did not measure the cost.
- **Two bases in one attribute set.** `thermal_stress_index` uses the gross forecast (`303–311`). `remaining_energy_demand` uses the net forecast (`346`). The two numbers are shown side by side, and the code gives no basis label for either.
- **The driver keys differ by regime.** Cooling reports `Temp` and `Solar_Load` (`434–439`), heating reports `Temp` and `Wind` (`446–450`). A consumer that reads `Wind` gets nothing under cooling, and the design comment at `421–429` says wind is absent on purpose.
- **Cooling wind is held fixed.** The cooling branch passes the same wind to the reference and the temperature evaluation (`421–432`), so wind cannot enter the attribution. The comment gives the reason: the per-unit cooling model is wind-independent by construction. This is a stated design, and the code follows it.
- **The reference state is the least-demanding one.** Heating uses the balance point with no wind and clear sky (`389`, `441`), cooling uses the balance point with no sun (`390`, `405`). The comment states that every term is then non-negative, and each `max(0.0, …)` enforces that.
- **The mixed regime resolves to its dominant side.** `is_cooling` follows `dominant_thermal_regime` (`400`), and the comment at `397–399` says directional consumers must read `regime` instead. The rule is documented on both sides.
- **Peak hour comes from the midnight snapshot.** The peak is read from the 24-hour plan captured at midnight (`325–337`), so it reflects the whole day and is not a hindsight value. The comment says so.
- **Not read:** `sensor.py` from line `451` onwards, including the forecast, wind and thermal-state sensors.

**Thirty-eighth pass: `hourly_processor.py` (learning call, forecast and solar block, `460–769`)**

- **A missing forecast is replaced by the model's expectation.** When the blended forecast item is missing, `forecasted_kwh` is set to `expected_kwh` (`hourly_processor.py:530`), and the same for the primary and secondary items (`531–532`). `expected_kwh` is the live model's value for the hour (`488`). The logged forecast error for that hour then measures the live model against the actual, not the forecast source. The comment calls this a baseline; the accuracy statistics do not separate it.
- **The forecast seed excludes the current hour.** The forecast's inertia seed is `inertia_temps[:-1]` (`504`), so the current hour's temperature is not in the history the forecast uses. The review did not compare this with the seed used for live learning, so it cannot say whether the two differ.
- **Shadow forecasts run twice per source.** Each source runs once with aux (`519–521`) and once gross (`525–527`). The two calls share the same inputs and differ only in the aux flag, so the number of forecast calls per hour doubles.
- **Four-dimensional and three-dimensional paths share one entry point.** The branch at `552–578` picks the 4D overrides or the 3D overrides. The comments explain why the 3D overrides would route the call back to 3D if they were passed to the 4D pipeline, so the branch is needed.
- **Base uses the global model when available.** `base_expected_kwh` takes `global_base_kwh` and falls back to the breakdown base (`582`). The comment at `580–581` gives the reason: learning from unit sums would feed back into itself.
- **The battery EMA input is gated on a heating unit that is read per sensor.** `has_heating_unit` iterates the configured energy sensors through `get_unit_mode` (`645–654`). The comment explains that `_unit_modes` is sparse and that `.values()` would gate the feedback off on the default install. The rule is explained where it is applied.
- **The potential-battery error path holds the value.** The three-dimensional potential batteries are updated inside a `try` (`724–738`). An exception skips the update, so the EMA stays at its last value (`722–723`). The comment says the battery "decays toward zero over a few hours", which the code does not do. The four-dimensional block (`748–`) has its own `except`, which this pass did not read to the end.
- **The carry-over reservoir is paused under the 4D flag.** Its charge is zero under the 4D flag (`686–697`), because the 4D release is hard-coded to zero. The comment says the state decays while paused, so turning the flag off restarts the reservoir from its current value. The rule is stated and the release is gated the same way.
- **Solar normalisation is signed by mode.** Heating solar is added back and cooling solar subtracted (`609–612`), matching the shutdown correction in the thirty-sixth pass.
- **Not read:** lines `770–814`, and the rest of the four-dimensional battery block after line `748`.

**Thirty-ninth pass: `sensor.py` (`451–900`)**

- **The driver breakdown has no value for a quiet hour.** Every term is clamped at zero, and `primary_driver` reports `None` when no term clears `ENERGY_GUARD_THRESHOLD` (`sensor.py:457–460`). The comment says a `max()` over all zeros would be arbitrary. The rule is correct, and it is the only place the sensor says that nothing is driving consumption.
- **Solar deficit is a separate heating term.** The heating breakdown has `Solar_Deficit` (`454`), the cost of the sky being darker than clear. The cooling breakdown has `Solar_Load` (`438`). The two keys describe the same physics from opposite sides, so a consumer that compares them must know the regime.
- **A weather impact is returned as a string.** `weather_impact_vs_typical` is formatted as `f"{impact:+.1f}"` (`487`), while the other numbers are floats. A consumer that sums it must parse the string first.
- **A margin is computed and not used.** `margin_pct` is set in the forecast sensor (`624`), and the summary text does not use it. The attribute `confidence_interval_margin` carries the absolute value only.
- **Units are keyed by friendly name again.** The forecast sensor builds `unit_estimates` keyed by the state's friendly name (`653–663`), and adds a `Total` key (`666`). A meter named `Total` would be overwritten. This is the same pattern as the energy-today sensor in the thirty-seventh pass.
- **The forecast confidence tiers are explicit.** The tiers are set by sample count and median error (`597–608`), with named thresholds in `const.py`. The reason text states the numbers, so a user can see why a level was chosen.
- **Source comparison is ratio-based.** The forecast-details sensor calls one source better only when its error is below the other's times `FORECAST_COMPARISON_FACTOR` (`720–725`). Otherwise it says the two are similar. The factor is named in `const.py`.
- **Accuracy is read from the internal sibling key.** The state string reads `KEY_FORECAST_ACCURACY_INTERNAL` (`693`), and the comment says the public attribute carries only the daily half, which has no sample count. The split is documented at the point of use.
- **The deviation sensor reports three bases side by side.** The current deviation is actual against expected so far (`762–764`). The projection is forecast against predicted (`801`). The thermodynamic deviation is separate (`804–806`). Each is labelled, and the labels are the names of the keys.
- **Not read:** `sensor.py` from line `901`, including the forecast, wind and thermal-state sensors.

**Fortieth pass: `__init__.py` (module header, constants and schemas, `1–295`)**

- **The reset-unit service requires a target, the reset-learning service does not.** `SERVICE_SCHEMA_RESET_UNIT` requires `entity_id` (`__init__.py:118–120`), while `SERVICE_SCHEMA_RESET` makes it optional (`114–116`). The twenty-fourth pass found that the optional form sends a reset to the first instance. The unit form is the safer design, and the two should match.
- **The import schema does not enforce the mapping the code needs.** `column_mapping` requires only `timestamp` (`95–96`). The full import also needs `temperature` (`storage.py:2281–2282`), and the schema does not require it. The schema accepts a mapping that the code will reject at run time (see the thirty-eighth pass, lesson on service failures).
- **The apply-gate value cannot be sent as null.** `value` is `vol.Any(None, vol.Coerce(float))` (`216`), and the comment (`205–207`) gives the reason: the number selector in the UI cannot send `null`, so `clear: true` replaces it. The workaround is documented at the schema.
- **The minimum day count is justified in a comment.** `days_back` for the implied coefficient has a minimum of 7 (`241–243`), and the comment (`232–240`) explains that three stability chunks inside a shorter window would fall in one solar phase. The comment states what a smaller value would hide.
- **Guest modes are removed from a dropdown by design.** The implied-coefficient mode accepts only `heating` and `cooling` (`231`), and the comment (`224–230`) explains that guest hours would always return `no_data`. The coordinator still accepts the guest names as synonyms.
- **The Tobit services need an explicit confirm.** Enabling the live learner requires `confirm: true` (`260–264`), and the comment says this is a guard against copy-paste activation. The gate is in the schema, not the handler.
- **Not read:** the module setup, unload, and service handlers, which begin after line `295`.

**Forty-first pass: `__init__.py` (`296–595`, with the forecast summary at `327–418`)**

- **The human-readable forecast names units at call time.** `_build_human_readable_forecast` labels contributors with the friendly name, falling back to the entity id when the state is missing (`344–350`, `378`). Two units with one name appear twice in the `top` string with no way to tell them apart. The sums are unaffected, because the numbers come from the entity-keyed breakdown. The label depends on whether the entity is loaded when the call runs.
- **The summary averages only the hours that have a temperature.** `avg_temp` uses `temps`, which skips hours with no temperature (`401–402`, `410`), while `total_kwh` counts every hour. The two are over different sets of hours, and the summary does not say so.
- **The peak hour keeps the first of a tie.** The comparison is strict (`403`), so an equal later hour does not replace the earlier one. The rule is harmless, and the output does not say it was a tie.
- **The import handler discards the import result.** `handle_import_csv` calls `coord.import_csv_data(...)` and returns nothing (`455`). The storage pass found that the import returns `(None, 0)` on a bad mapping. The service call therefore succeeds for a file the import did not read.
- **Setup converts every failure into a retry.** The first refresh is wrapped in a broad `except Exception` and re-raised as `ConfigEntryNotReady` with the text "Timeout while waiting for initial data" (`425–428`). The noqa comment names the reason, a setup boundary. The message is wrong for any error that is not a timeout, and a bug in the coordinator shows up as a slow start.
- **The stop handler saves the data on shutdown.** The listener calls `_async_save_data(force=True)` (`434–438`) and is removed with `async_on_unload` (`440–442`). The pattern is correct, and it is the only save on the way out.
- **The reset-learning service falls back to the first instance.** With no `entity_id`, `_get_target_coordinator` returns the first coordinator (`487`, `321–323`). This is the point made in the fortieth pass, here seen in the handler.
- **The reset-unit service loops over every instance.** `handle_reset_unit_learning` calls `async_reset_unit_learning_data(entity_id)` on each coordinator (`504–505`). The review did not read that method to see what an instance does when the unit is not its own.
- **Services are registered per entry.** Each `async_setup_entry` registers the same service names (`457–588`). The handlers close over `hass` only and look the coordinator up on each call, so the registration does not depend on the entry. The review did not read unload to check whether the services are removed when the last entry goes.
- **Not read:** the reset-unit, retrain-unit and later handlers from `596`, and the forecast handlers after `1257`.

**Forty-second pass: `__init__.py` (`596–895`, the retrain-unit, batch-fit and obstruction handlers)**

- **The batch-fit default is set in two places.** The schema sets the default for the batch-fit options (the fortieth pass covered the schema block), and the handler repeats it with `call.data.get("days_back", 30)` (`638`, `680`). The comment at `637` says the defaults are guaranteed, so the repeat is not needed. If one default changes, the other stays.
- **The 4D batch handler bypasses the coordinator method.** The 3D service calls `coord.async_batch_fit_solar` (`653–658`). The 4D service reads `coord._hourly_log` and `coord._solar_coefficients_4d_per_unit` (`701–703`), calls `coord.learning.batch_fit_solar_coefficients_4d` directly (`701`), and then calls `coord._async_save_data(force=True)` itself (`732`). The save rule is now in two places.
- **The 4D response counts units and regimes together.** A skipped unit adds one to `skipped_count` (`719–723`). A skipped regime inside a unit adds one (`729–730`). The response therefore reports a count with two meanings, and `applied_count` counts regimes only.
- **`seed_live_window` is accepted and does nothing in 4D.** The handler logs that the flag is a no-op (`695–700`) and returns `seed_skip_reason: no_live_window_4d` (`742–743`). The flag is in the schema, so the UI offers a control that changes nothing.
- **The obstruction handler's comments are correct.** The handler makes one fit per window (`802–808`), decides stability from the stored results (`866–873`), and then runs a final pass on the primary window with the stability map (`912–923`). The comments at `810–811` and `832–834` describe that final pass, which is there. (An earlier draft of this pass said no second call was made; that was wrong.)
- **The stability check is not transitive.** The comment says the group is found "transitively" (`876`). The loop checks each value against every other value, and counts the neighbours of one value (`878–888`). With the three default windows this gives the same answer, but the comment names a rule the code does not use.
- **The primary window is the longest one.** `primary_window = max(windows)` (`838`) is used for the candidate list (`843–860`). The rule is stated, and it is the one a user would expect.
- **Explicit `days_back` turns off the stability gate.** When the user sets `days_back`, the handler runs one window and does not require agreement (`785–787`, `894–895`). The docstring states this, and the rule is correct for debugging.
- **Not read:** nothing further in `596–895`.

**Forty-third pass: `__init__.py` (`896–1257`, the obstruction gate, implied coefficient and Tobit services)**

- **The obstruction gate's comments match the code.** The final pass uses the stability map (`912–923`), and the response carries the per-window values and the final result (`925–938`). See the correction to the forty-second pass.
- **The apply-gate validates the value but not the clear.** An out-of-range value raises `ServiceValidationError` (`989–995`), and `clear` skips the check (`976–977`). The dry run and the write both use the validated value (`1037`, `1041`).
- **The implied-coefficient default is set again in the handler.** `days_back` defaults to 30 in the schema and again in the handler (`1095`), and its docstring repeats it (`1088–1090`). This is the same duplicate as the batch-fit default in the forty-second pass.
- **The Tobit enable and scope handlers stamp a marker.** Both set `_tobit_default_applied` (`1168`, `1204`), and the comment at `1160–1167` says why. A load after a disable then leaves the disable in place.
- **The Tobit reset clears the NLMS shadow, which the docstring does not say.** The handler clears `_nlms_shadow_coefficients` for all entities (`1236`) or for one (`1243`). The docstring names only the sufficient statistics (`1220–1221`).
- **Not read:** nothing further in this batch.

**Forty-fourth pass: `__init__.py` (`1257–1593`, backup, replace-sensor, forecast, calibration and diagnose services)**

- **The calibration services use three window lengths.** Wind thresholds default to 60 days (`1364`), unit thresholds and inertia to 30 (`1450`, `1478`). The diagnose services default to 30 (`1555`, `1578`). No comment gives the reason for 60.
- **Isolating a meter ignores an unknown name silently.** `get_forecast` subtracts the other meters only when `isolate_sensor` is in `energy_sensors` (`1522`). Any other name returns the global forecast and no flag.
- **The balance-point fit runs off the event loop on a snapshot.** The snapshot is taken on the loop (`1394`), and the fit runs in an executor (`1395–1397`). The comment (`1391–1393`) gives the cost, and the snapshot stops the coordinator changing the data mid-fit.
- **A heat-source error becomes a validation error.** The coordinator's `ValueError` is re-raised as `ServiceValidationError` (`1429–1430`), so the UI shows the message. The Tobit flag uses the same pattern (`1152`).
- **The diagnose-solar schema is built inside the registration function.** `SERVICE_SCHEMA_DIAGNOSE_SOLAR` is defined at `1569`, while the other schemas are at module level. It works, but the schema cannot be imported or tested without running setup.
- **Replace-sensor reloads only the entries that changed.** A reload runs only where the coordinator returns true (`1302–1304`, `1310–1314`). The legacy path reloads every matching instance.
- **Not read:** `async_migrate_entry` and the unload path, from `1594`.

**Forty-fifth pass: `coordinator.py` (`795–1000`, auxiliary cooldown and heat-source classification)**

- **The cooldown starts on the falling edge only.** It starts when aux goes from on to off (`801–804`) and is cancelled when aux comes back during the cooldown (`807–810`). A manual exit clears it and saves (`818–827`).
- **Background classification waits for Home Assistant to run.** The task is created only when `is_running` is true (`861–862`). If task creation fails, the coroutine is closed (`868–869`), so no "never awaited" warning is raised. The comment at `868` says the hour boundary must not break.
- **The fit runs off the loop on a snapshot.** The snapshot is taken on the loop (`896`), the fit runs in an executor (`897–899`), and the state is updated back on the loop (`900`). The same snapshot pattern as the balance-point service.
- **An unknown unit is treated as heating.** `get_unit_mode` returns `MODE_HEATING` when the unit is not in `_unit_modes` (`980`). The modes are sparse (pass thirty-seven), so an unseen meter is counted as heating.
- **The regime split uses the accumulators.** `_today_regime_split` reads the per-hour accumulators (`983–1000`). The docstring gives the case the simpler rule gets wrong (20 kWh heating then 1 kWh cooling). The live and history paths agree by construction.
- **The heat-source notice is marked before it is sent.** `unit["notified"] = new` is set (`947`) before the notice is built and sent (`969–976`). A failed send is logged at debug (`975–976`) and never retried.
- **Setting the type writes two stores in order.** The in-memory dict changes (`926–928`), then the config entry is updated (`929–931`). If the entry update raises, the two disagree. The docstring says the entry has no update listener, so no reload follows.
- **Not read:** from `1000` onward, including the setup, service and reset handlers and the migrations.

**Forty-sixth pass: `solar.py` (`1–33`, `549–574`)**

- **The optional dependency sets a flag and nothing else.** An `ImportError` sets `HAS_ASTRAL` to false (`11–16`), and the names `sun_elevation` and `sun_azimuth` are then undefined. A caller that does not check the flag fails with a `NameError`. The review did not check the callers.
- **The solar vector uses three non-negative azimuth bases.** South is `max(0, −cos az)`, east `max(0, sin az)`, and west `max(0, −sin az)` (`568–571`). East and west have disjoint support, which the docstring calls orthogonal (`559–560`). South overlaps both, so the three are not one-hot.
- **Cloud cover does not change the split.** `base_intensity` multiplies all three terms (`565`), so the direction split depends on azimuth alone.
- **Below the horizon every term is zero.** `elevation <= 0` returns zero for all three (`562–563`).

**Forty-seventh pass: `__init__.py` (`1594–1693`, migration and unload)**

- **Migration runs in steps and accepts any newer version.** Version 1 moves to 2 by deriving each source from whether a sensor is set (`1598–1626`). Version 2 moves to 3 by dropping four sky-view keys (`1631–1642`). The function then returns `True` for any version, including one it does not know (`1644`). A newer entry is accepted without a check.
- **Unload removes services only with the last entry.** The services are removed when `hass.data[DOMAIN]` is empty (`1655–1656`). The removal list matches the registrations read in the fortieth to forty-fourth passes. The list is written by hand, so a new service must be added in two places, and nothing in this file checks that they agree.
- **The coordinator is removed before its save.** `hass.data[DOMAIN].pop` runs before `_async_save_data()` (`1649–1652`). If the save raises, the entry is gone from memory and the error stops the unload after the platforms are unloaded.
- **Not read:** nothing further in `__init__.py`.

**Forty-eighth pass: `coordinator.py` (`1000–1337`, regime, display helpers and the reset paths)**

- **A missing regime is kept apart from idle.** `thermal_regime_for_day` returns `None` when the day has no split or was stored before the split existed (`1028–1036`). The docstring says `None` must not be read as `idle`, because a pre-upgrade day would then become an idle building (`1017–1022`).
- **Display and diagnose read different fields by rule.** `hourly_solar_impact_kwh` prefers the 4D field when the flag is on (`1060–1063`). The docstring says the diagnose blocks must not use this helper (`1054–1057`), because they need the raw fields.
- **The 4D flag is read from the entry on every access.** `experimental_4d_primary` reads `entry.data` each time (`1080`), so a reconfigure takes effect on reload with no cache to clear (`1076–1078`).
- **Screen configuration has two scopes.** `screen_config_for_entity` returns the global config only for affected entities (`1095–1097`). The docstring says global state, such as the potential battery, keeps using the global config (`1090–1093`).
- **An unknown entity has no obstruction gate.** `critical_elev_for_entity` returns all-`None` (`1117–1126`), so an unknown entity is not gated. The docstring calls this the graceful default (`1117–1118`).
- **The unit reset misses three writers.** `reset_unit_learning` clears the correlation, aux, 3D solar, outlier and observation state (`1158–1179`). It does not clear the 4D coefficients, the Tobit sliding window or the NLMS shadow. The all-solar reset clears all three for the same unit (`1240–1246`), and its comment explains that a leftover window writes the old coefficient back (`1234–1239`). After a unit reset, the old window can still write the coefficient back on the next qualifying hour.
- **The all-units reset also clears the house-level battery.** It clears the carry-over reservoir and the four 4D batteries (`1257–1271`). The comment says a per-unit reset does not clear them because other units share the reservoir (`1257–1262`, `1265–1267`).
- **The replay cutoff compares strings.** `timestamp >= cutoff_str` (`1288–1289`) compares a stored timestamp with a `YYYY-MM-DD` date. This works only while the log's timestamps begin with the date. The review did not check the timestamp format.
- **Not read:** from `1477` (the implied-coefficient apply) onward.

**Forty-ninth pass: `coordinator.py` (`1338–1475`, batch-fit solar)**

- **A dry run stores its results and saves them.** The docstring says a dry run does not write or "persist" (`1361–1362`), and also says dry-run results are stashed for `diagnose_solar` (`1371–1372`). The save runs when any unit had a result, whether or not it is a dry run (`1449–1450`). The docstring contradicts itself, and the code follows the second statement.
- **A non-dict result loses its reason.** The branch for a non-dict result (`1396–1403`) takes its reason from `isinstance(regimes, dict)`, which is false inside that branch. The reason is therefore always `unknown`, and the `.get` call is dead.
- **Skipped units and applied regimes are counted at different levels.** `skipped_count` counts units (`1404`, `1418`), and `applied_count` counts regimes (`1437`). The forty-second pass found the same mix in the 4D handler.
- **A skip is recorded, not just counted.** Each skipped unit gets a `_last_batch_fit_per_unit` entry with its reason (`1406–1412`, `1421–1425`), so `diagnose_solar` can show "skipped, with reason" rather than nothing. The comment explains why (`1406–1407`).
- **The save gate was widened on purpose.** The comment at `1443–1448` says the gate was once coefficient-only, and that a run with only skip records would lose them on restart. The fix is explained where it sits.
- **Not read:** `async_apply_implied_coefficient` onward.

**Fiftieth pass: `config_flow.py` (`1–220`, module notes, translations and readiness text)**

- **The module notes are rules for the next editor.** They say `_build_final_data` is the one place for normalisation (`7–9`), that `SelectSelector` returns strings (`10–11`), and that the wind conversion happens only for form values (`20–22`). Each rule names the function it applies to.
- **Field order follows one stated axis.** The order is by how often a user is likely to open the field for it, not by how much harm a setting can do (`26–30`). The notes name the two known exceptions (`40–43`) and the one pinned position (`45–47`).
- **The translation rule is manual.** The `advanced` and `reconfigure_advanced` steps must share the same data keys (`53–55`). Only the readiness placeholder is named as pinned by a test (`57–61`). The review did not open the test.
- **The readiness text lives in Python, not in the translation files.** Both languages are in `_FOUR_D_READINESS_LINES` (`152–197`), and the reason is given (`141–146`): Home Assistant substitutes placeholders as literal text.
- **The readiness design warns and never refuses.** `insufficient_data` shows nothing (`148–151`), so a new install does not see a line that says nothing is known.
- **The module note says the reasons compose, but the code has a third sentence.** Lines `199–200` say the two reasons "compose", and the "both" case is a separate pre-written sentence (`205–208`, `213–216`). A translator must keep three strings in step, not two.
- **Not read:** the reconfigure steps (after `900`), and the rest of `config_flow.py`.

**Fifty-first pass: `coordinator.py` (`1477–1809`, the implied-coefficient apply)**

- **The apply writes nothing on a dry run, and says so.** The docstring says a dry run "writes nothing" (`1508–1509`), and the write is inside `if not dry_run` with the save (`1739–1755`). This matches the rule in the forty-ninth pass, where the batch fit saves on a dry run. Here the rule holds.
- **The response shape changes with the path.** An unknown unit returns a short dict without `before`, `after`, `applied_components` or `sample_count` (`1563–1570`). The skipped-for-exclusion path returns the same short shape with status `skipped` (`1575–1582`), which the docstring's status list does not include (`1521`).
- **A 4D-only run reports the 3D list.** The no-stable branch sets `skipped_components` to `skipped_3d` (`1732`) whatever the dimension. The legacy alias keys explain the choice (`1799–1802`), but a 4D caller reads an empty `applied_components` on every run.
- **The clamp is applied after the stability test.** The stability test uses the raw implied value, and the write uses `min(SOLAR_COEFF_CAP, implied)` (`1627–1629`, `1657–1659`). The response reports both the raw implied value and the clamped `after`, so a user can see the clamp, but the review did not check whether a capped value is ever shown as stable.
- **A missing 4D window becomes a list of `None`.** `analysis.get("windows_4d") or [None] * 3` (`1651`) passes three empty windows to the stability test when the 4D windows are absent. The review did not read `assess_apply_implied_stability` to see what that yields.
- **Not read:** nothing further in the apply, which ends at `1809`.

**Fifty-second pass: `coordinator.py` (`1811–1950`, aux and solar migrations)**

- **The aux migration redistributes a removed unit's coefficients.** A removed unit's value is split across the remaining units in proportion to their existing coefficients for the same temperature and wind bucket (`1883–1889`). If no remaining unit has a weight, the whole value goes to the primary unit (`1891–1894`). The docstring states this conservation rule (`1814–1816`).
- **The primary unit is picked by a live state, not by history.** `_get_primary_unit` ranks the remaining units by `_get_float_state` (`1837–1849`). The docstring says "highest total consumption" (`1819–1820`). The review did not read `_get_float_state` to see whether it returns a running total.
- **The solar migration resets, and does not redistribute.** Each removed entity is passed to `async_reset_solar_learning_data` (`1946–1947`). The docstring says solar coefficients cannot be split, because each one is one unit's window physics (`1921–1924`). The contrast with the aux rule is a stated design decision.
- **Each reset saves on its own.** `async_reset_solar_learning_data` saves with `force=True` (`1329`), so removing three entities writes the store three times. The cost is small, but a batch of removals causes a write per entity.
- **The in-memory list changes after the save.** The aux migration saves (`1901–1903`) before it sets `aux_affected_entities` and `_aux_affected_set` (`1905–1906`). The review did not check what the save writes for that list.
- **Not read:** `_add_aux_coefficient` onward (`1951–`).

**Fifty-third pass: `config_flow.py` (`900–1010`, reconfigure steps)**

- **The sensor-swap guard refuses a simultaneous remove and add.** If a sensor is both removed and added in one submit, the form shows `sensor_swap_detected` (`917–918`). The comment says this would destroy the removed sensor's history, and points to the `replace_sensor` service (`911–914`).
- **The reconfigure feature step cannot report an error.** `errors` is set to `{}` and never changed (`998`), so `if not errors:` (`1002`) is always true. This is the same defect as the thirty-fifth pass, which found it in the create flow. The reconfigure copy has the same defect.
- **The migrations run before the final write.** The aux and solar migrations run on the advanced submit (`967–980`), before the feature page (`981–982`) and the final `async_update_reload_and_abort` (`983–985`). See the lesson on wizards.
- **Booleans are written explicitly.** A loop writes each boolean key, with `bool(user_input.get(_k, False))` (`960–963`), so a False is present even when Home Assistant omits it. The comment gives the reason.
- **The heat-source conflict keeps the answers.** On a conflict the form is rebuilt from the submitted input (`944–954`), as in the create flow.
- **Not read:** nothing further in `config_flow.py`. The file ends at `1010`.

**Fifty-fourth pass: `sensor.py` (`901–1230`, deviation, effective wind, correlation and last-hour sensors)**

- **The purity percentage is the normal share.** `current_hour_purity_pct` is `(1 − aux share) × 100` (`917`). The name says purity and the comment says "% Normal mode".
- **The stability thresholds are literals.** The sensor calls the hour stable when the aux share is below 0.05 or above 0.95 (`909`, `911`), with no named constant. The same file names other thresholds in `const.py`.
- **The data-quality cut is a literal.** An hour is "complete" above 30 samples (`957`). The number assumes a sampling rate that the code does not state.
- **A missing secondary unit falls back to the primary unit.** `_get_wind_unit_for_source` returns the primary weather unit when the secondary entity or its state is missing (`970–976`). The review did not check whether a secondary forecast can exist without its entity.
- **The "midnight" forecast is read at the current time.** The attributes named `midnight_forecast_effective_wind_*` call `get_forecast_for_hour(now, …)` (`1004–1005`, `979`). The name says midnight. The review did not check whether `get_forecast_for_hour` reads the midnight snapshot.
- **The correlation sensor parses its keys twice, differently.** The temperature keys are parsed with a fallback to string order (`1035–1044`), and the aux keys with a bare `int()` (`1066`). A malformed aux key raises, and the attributes fail.
- **The last-hour actual sensor splits heating and cooling by the hour's own modes.** It reads `unit_modes` from the logged entry (`1109–1119`), so the split uses the modes in force at that hour (see the forty-eighth pass).
- **The last-hour top consumers are a list.** `top_consumers` keeps the first five units by consumption (`1135–1159`), so duplicate names both appear. The energy-today sensor's dict keyed by name (thirty-seventh pass) does not have this problem.
- **The summary is built on every read.** `format_last_hour_summary` runs inside `extra_state_attributes` (`1165–1170`), with a new formatter each read. This is the per-read cost from the thirty-seventh pass.
- **The solar deduction and coefficient may come from different models.** The expected sensor reports `solar_deduction_kwh` from the flag-aware helper (`1199`, `1208`), and `solar_coefficient` from the stored `solar_factor` (`1209`). The review did not check whether `solar_factor` is the 3D coefficient, in which case the two attributes mix models under the 4D flag.
- **Not read:** `sensor.py` from `1231`, including the last-hour deviation and the forecast, wind and thermal-state sensors.

**Fifty-fifth pass: `coordinator.py` (`1951–2116`, the aux helper and the sensor replacement)**

- **The aux clamp is skipped when the base is missing.** `_add_aux_coefficient` caps the value only if the unit has a base value for that temperature and wind bucket (`1963–1966`). Without one the value is stored unclamped. Potential application: decide what a missing base means and say so in the docstring.
- **The replacement does not move every per-unit store.** The in-memory and log migrations cover most stores (`2032–2046`, `2076–2099`). The 4D coefficients (`_solar_coefficients_4d_per_unit`, set at `213`), the Tobit statistics (`265`) and the NLMS shadow (`312`) are not in the migration range; a grep for each returns no hit between `1951` and `2116`. The reset paths clear all three per unit (`1226–1244`), so the code knows they are per unit. After a replacement the new sensor starts with no 4D state.
- **The entry is written before the data moves.** The config entry changes at `2023`, and the stores move at `2032–2099`. If a migration raises, the entry names the new sensor while the data still uses the old id. The save follows at `2104`. Potential application: move the data first, and write the entry last.
- **A key collision is overwritten without a check.** `_migrate_key` replaces whatever is under the new id (`2027–2031`). The comment calls this replacement intent, and the function does not check for existing data.
- **The baseline is dropped, not moved.** The last energy value of the old id is deleted (`2066–2068`), so the new sensor starts a fresh baseline and avoids a spike. The comment states the reason.
- **The save is bracketed by two refreshes.** The data is saved (`2104`), refreshed (`2109`) and saved again (`2111`). The comment at `2106–2108` says a reload before the second save would lose the new baseline.

**Fifty-sixth pass: `coordinator.py` (`2117–2330`, the sensor readers)**

- **The GHI reader does not clamp, despite its docstring.** The docstring says the value is clamped to 0–1500 W/m² (`2275`), but any value outside the range returns `None` (`2289–2290`). A spike is therefore reported as no sensor. The fault is in the docstring, or in the code, and the review cannot tell which was meant.
- **The cloud reader clamps and warns.** The numeric attribute is clamped to 0–100 (`2242`). A condition-text fallback logs one warning per hour (`2252–2262`), and the default of 50 applies when the entity is missing (`2231`). The default is the conservative choice, and the comment says so.
- **The wind conversion covers two attributes.** `_get_weather_attribute` converts only `wind_speed` and `wind_gust_speed` (`2326–2328`). Other attributes pass through unchanged, so a new wind-like attribute would be read in the wrong unit without a warning.
- **A missing entity is `None` for most readers.** `_get_float_state` and `_get_ghi` return `None` when the entity is missing, and the cloud reader returns a default. The callers must handle both forms, and the review did not check every caller.

**Fifty-seventh pass: `coordinator.py` (`2331–2520`, the weather fallback, inertia history and the log axis)**

- **The secondary weather fallback skips the unit conversion.** `_get_weather_attribute_with_fallback` returns the secondary attribute as a bare float (`2350–2354`), while the primary path converts wind units (`2326–2328`). The docstring limits the fallback to irradiance (`2333–2339`), where no conversion is needed. Potential application: refuse the fallback for any attribute that needs a unit, or use the same converter for both.
- **Tau is a gap threshold, not an age cutoff.** The docstring of `_get_recent_log_temps` says so (`2406–2407`), and says the old rule capped history at tau − 1 samples of a 5·tau kernel. The change is recorded where it sits, and the readings stop at the first gap longer than tau (`2434–2436`).
- **The replay path re-keys every entry on the current axis.** `_entries_on_current_axis` recomputes inertia and the temperature key from `temp` (`2441–2452`), so a replay learns into the buckets live learning uses now. The log is not modified. The all-in-log branch avoids a second pass (`2458`).
- **Current temperature has a sensor preference and a fallback.** A sensor source uses the hourly average when samples exist, and otherwise the raw reading (`2493–2496`). The list keeps its last position as the current hour, with `None` when no temperature is known (`2506–2508`).

**Fifty-eighth pass: `coordinator.py` (`2521–2700`, inertia, wind bucket, sun and live predictions)**

- **A special case is documented with its reason.** A single-sample inertia returns the temperature directly, to avoid kernel rounding (`2526–2527`), and the comment at `2524–2525` says so. This is the pattern to copy.
- **A missing sun entity reads as the sun on the horizon.** `_get_sun_info_now` returns `(0.0, 0.0)` when `sun.sun` is missing (`2583`), and the solar model reads zero elevation as no sun (pass forty-six). The warning repeats once an hour (`2576–2582`). The fallback is a silent substitution of night, and the warning is the only sign of it.
- **A stale solar value survives an unknown temperature.** The solar fields in `self.data` are written only inside `if calc_temp is not None` (`2607`, `2623–2626`). When the temperature is unknown, `current_model_rate` is set to zero (`2609`), but the solar impact keeps the value from the last hour. The two keys then describe different hours.
- **The partial log is matched on the hour's start instant.** The comparison uses instants (`2665`, `2670–2672`), because a repeated fall-back hour has the same date and hour number. The comment gives the case.

**Fifty-ninth pass: `sensor.py` (`1231–1302`, the last-hour deviation sensor)**

- **The sensor fails on an empty log.** Two solar values are assigned only inside `if self.coordinator.model.hourly_log:` (`1243–1244`), and the attributes dict reads them unconditionally (`1254–1255`). On a fresh install, with no hour logged, the reader raises an unbound-variable error. This was found by reading; it has not been run. Potential application: initialise each value before the branch, and test the empty log.
- **Zero stands in for unknown.** `percentage`, `expected` and `actual` default to `0.0` (`1250`, `1259–1260`), so a sensor with no logged hour reports zero, not unknown. This is the case the forty-eighth pass warned about.
- **The model values are strings.** `model_value_before` and `model_value_after` are formatted to five decimals (`1274`), so a history graph cannot plot them as numbers. The format keeps the precision, and loses the type.

**Sixtieth pass: `sensor.py` (`1303–1450`, the AUX savings sensor)**
- **An empty allow-list shows every unit.** The per-unit loop skips a unit only when the allow-list is non-empty (`1363`). An allow-list with no entries therefore shows all units, which is the opposite of the sense of an allow-list. Potential application: test for `is None`, and treat an empty list as none.
- **The leak thresholds are literals.** The status turns to `partial_overflow` above 0.01 kWh and to `critical_leak` above 0.5 kWh (`1415–1418`). The comment calls the second an arbitrary threshold. Potential application: name both, and state their unit.
- **The orphaned savings are added to the unassigned total.** Yesterday's orphaned savings and this hour's are summed (`1408–1409`), so the unassigned total covers the whole day. The status uses the same total, so a leak from the earlier hours can still show as critical.
- **Current-hour means use the minute fraction.** Means are scaled by the minutes passed in the hour (`1391`), with a floor of 0.1 minute (six seconds). The floor is named in the comment, and it stops division by a near-zero interval.

**Sixty-first pass: `sensor.py` (`1451–1650`, the device-daily sensor)**
- **The throttle limits the value, not the work.** The reported power changes only on an hour change or a change of more than 5 % (`1534–1551`), but the inertia temperature and the rolling power are recomputed on every read (`1506`, `1531`). Potential application: throttle the computation, or say that only the display is throttled.
- **A learned zero is treated as absent.** The regime is accepted only if one of its three directions is non-zero (`1621–1623`). The same test appears again in the learning status (`1694`). Potential application: test for the presence of the key.
- **The correlation keys are guarded.** An unparseable temperature key is skipped (`1578–1585`), which is the same guard as the last-hour correlation sensor (pass fifty-four). The aux keys there have no guard.
- **A comment records a fixed bug.** The comment at `1602–1609` says an earlier shortcut sent guest-cooling units to the heating regime. The comment is a record of the fix, and the regime selector is shared with the solar calculation.

**Sixty-second pass: `sensor.py` (`1651–1800`, the solar learning status, lifetime and thermal state)**
- **The dead-zone warning uses a literal and a constant that disagree.** The warning fires at `dead_zone_count >= 10` (`1714`), while the message reports the threshold as `SOLAR_DEAD_ZONE_THRESHOLD` (15). The comment says the warning is for approaching the threshold. A user reads `dead_zone_warning_10/15`, and the first warning comes five hours of misses before the auto-reset point at 15. Potential application: compare against the constant, and build the message from the same value.
- **Test doubles reach production code.** The dead-zone count is checked for `int` with a comment about a mocked coordinator (`1679–1681`). The check is harmless, and it shows the test shape has leaked into the runtime path.
- **The lifetime getter changes state.** `native_value` updates `_last_reported_value` when the change is at least 0.1 kWh (`1751–1752`). The throttle then depends on how often Home Assistant reads the value. Potential application: keep the throttle in the update path, and make the getter pure.
- **The thermal sensor keeps its history out of the recorder.** The inertia history and the weights are listed in `_unrecorded_attributes` (`1774`), with a comment on the size. This is good practice.
- **The midnight forecast is read at the current time.** The two attributes call `get_forecast_for_hour(now, …)` (`1788–1791`), which is the naming problem of the fifty-fourth pass again. The name says midnight, and the value is the forecast for now.

**Sixty-third pass: `repairs.py` (`1–199`, the DNI/DHI outage repair)**
- **The repair asks and never acts.** The module docstring says so (`1–34`), and the reason is given: the fix is a human decision, because an untrained 4D model returns the zero vector and would silently remove solar from predictions. The promotion path is absent by design. Potential application: write the asymmetry down where the code can be wrong.
- **The issue clears itself.** `clear` and `not_applicable` delete the issue (`104–110`), while `hold` and `insufficient_data` leave it alone (`100–103` comment). The hysteresis is in the verdict, not here, which keeps this function simple.
- **The check never raises.** The whole check is inside a broad `except` that logs at debug (`111–113`), so a repair failure cannot stop the hour boundary. The comment gives the reason.
- **The issue is not persistent.** It is re-derived after a restart (`72–77`), so a stale warning cannot outlive the condition. The cost is that the card is absent until the next hour boundary.
- **The fix flow aborts rather than reports success.** Every failure path returns an abort (`158`, `168`), because the repair framework deletes the issue on any non-abort result. A silent no-op would look like a fix. The comment at `149–158` says so.
- **The reload follows the update.** The entry is updated (`170–171`) and reloaded (`177`), and the repair deletion is left to the framework (`178–184`). The comment says an earlier explicit delete was not needed.

**Sixty-fourth pass: `const.py` (`1–220`, defaults, battery screens and transmittance)**
- **The half-life comment checks out.** `SOLAR_BATTERY_DECAY = 0.50` is described as a half-life of about one hour. At 0.5 per hour, the half-life is one hour exactly, so the comment is right.
- **The selection penalty checks out.** The comment gives a penalty of about 3.07 at m = 110 candidates. The square root of twice the natural log of 110 is about 3.07, so the effective bar is about 5.07, as the comment says. The n = 2 critical value in the next comment (12.7) matches the two-sided 95 % t value with one degree of freedom.
- **The two gates combine as a narrowing.** The bias flag needs both the absolute floor (`0.05`) and the relative gate (`0.10`). The comment says that raising the relative gate can only narrow the flag, which holds because the gates are combined with AND.
- **Two comments disagree about the transmittance history.** The comment above `DEFAULT_SOLAR_MIN_TRANSMITTANCE` says the floor was raised from 0.20 in v1.3.3. The comment above `SCREEN_DIRECT_TRANSMITTANCE` says the pre-1.3.3 global floor was 0.30. The review cannot tell which history is right, and no test pins either value.
- **The 4D key keeps its historical name.** `CONF_EXPERIMENTAL_4D_PRIMARY` is kept, because renaming it would need a config-entry migration. The comment says so, which is the right place for it.
- **Not read:** `const.py` from `221` to `1167`.

**Sixty-fifth pass: `coordinator.py` (`2701–2900`, the hour-gap close and the wind penalty)**

- **The gap close adds aux only when the rate is positive.** The aux impact and the unit aux breakdown are added inside `if current_rate > 0` (`2740–2753`). An hour with zero rate but a positive aux impact loses that aux for the gap. The review did not find a case where this happens, so it is a guard to confirm, not a known fault.
- **The wind penalty scans the whole log on every call.** `_calculate_daily_wind_penalty` loops over `_hourly_log` without a break (`2782–2790`), filtering on today's date string. The loop runs once per update, so the cost grows with the log. The reverse-with-break loop used in `_update_daily_budgets` (`2884`) shows the cheaper form.
- **The penalty is clamped hour by hour.** Each hour's penalty is `max(0, with wind − without wind)` (`2836`). An hour where wind helps cannot offset another hour where it hurts. The docstring says "penalty", so the clamp is intended. The result is a sum of harms, not a net effect.
- **The past-hours wind model is pinned to 3D.** `force_3d=True` is set in both scenarios (`2822`, `2832`), with a comment saying the diagnostic must not change with the 4D flag. The first of these is at `2819`. The rest of the day can use 4D while the penalty does not, so the figure can disagree with the forecast it sits beside.

**Sixty-sixth pass: `coordinator.py` (`2901–3100`, the daily budgets and the forecast-today figure)**

- **The forecast-today comment names a source the code does not use.** The comment says the figure is "Live Forecast for the rest of the day" (`2978`), and the calculation uses the current hour's reference plan (`2906–2908`, read at `2997`). The future part is live, so the figure mixes two sources. The comment in the same block says the reference forecast is locked at midnight for stability, so the code is the one that was intended, and the comment is stale.
- **Two projections use two forecasts for the same hour.** The thermodynamic projection uses the live plan for the current hour (`2945–2948`), and the forecast-today figure uses the reference plan (`2906–2908`). A user comparing the two sees a difference that comes from the source, not from the weather. The names do not say which is which.
- **The per-unit identity holds.** The per-unit total is actual so far, plus the remaining forecast clamped at zero, plus the future (`3061–3085`). The comment's three cases check out: if the actual hour exceeds the plan, the total is the actual, and if it falls short, the total is the plan. This is the same clamp pattern as the gap close.
- **The default for the spread is a literal.** `max_dev` falls back to 2.0 kWh when the forecast has no error statistic (`3100`). The fallback is not named, and the value is not tied to the forecast's own units or sample size.

**Sixty-seventh pass: `coordinator.py` (`3101–3300`, the confidence band, forecast details and the hour boundary)**

- **The confidence band shrinks through the day.** The margin is the 95th-percentile error times the fraction of the day left (`3101`), so it is widest at midnight and zero at the end of the day. The shape is reasonable, and the default of 2 kWh applies only when there is no error statistic.
- **The forecast-details contract was broken once.** The docstring says the split was made because the producer, projection and sensor drifted apart, leaving the sensor stuck on its warm-up string (`3116–3119`). The fix is a separate method, so the chain can be tested end to end. Potential application: test each producer-consumer contract with the real data shape, not a mock.
- **A sibling key keeps the internal numbers out of the recorder.** The accuracy numbers go to `KEY_FORECAST_ACCURACY_INTERNAL` (`3142–3153`), which is not an attribute. The comment says `samples` counts days, but the field is taken from the `hourly` bucket. A reader who trusts the bucket name reads days as hours. Potential application: name the bucket for its unit, or rename the field.
- **The hour boundary compares instants.** `_hour_boundary_crossed` compares the hour's start instant, and falls back to the hour number only when no instant was saved (`3225–3238`). The docstring says the fallback is there so an hour missed across a restart is still finalised. This is the same instant rule as pass sixty.
- **The hour is finalised before the day.** The hourly processing runs first (`3258`), and the day's processing runs after it (`3269–3275`). The comment at `3253–3256` gives the reason, which is to avoid a midnight race.
- **Not read:** the rest of `coordinator.py` from `3301`.

**Sixty-eighth pass: `observation.py` (`1–200`, the solar shutdown detector)**

- **An offline meter is skipped, not read as zero.** A unit absent from the metered map is never flagged (`observation.py:112–113`). The comment gives the case: a zero read as shutdown would lower a unit's weight and lift its coefficient. This is the same rule as the replace-sensor pass, applied where it matters most.
- **A fix is recorded at the gate it changed.** The comment at `122–137` gives the order of two checks, the ticket that found the problem, and the field data. The absolute floor check now runs before the base-threshold skip, so a low-modulation unit on standby is flagged. The record is more useful than a test name.
- **Test fixtures shape the production path.** The solar-scope set accepts `None` to mean all entities, and the comment says `None` is the legacy path for test fixtures (`94–95`). This is the test-double pattern from the sixty-second pass, now in the production signature.
- **A dead branch.** The ratio is guarded by `base > 0` (`147`), but the earlier `base < threshold` skip already removes `base = 0` when the threshold is positive. The `else 1.0` never runs. This is harmless, and it hides which guard is the real one.
- **Not read:** `observation.py` from `201` onward, except the data contracts below.

**Sixty-ninth pass: `observation.py` (`201–420`, the data contracts)**

- **The solar-learning gate is a silent default.** `ModelState` holds the 4D coefficients as `None` on legacy construction sites, and the 4D learner returns early on `None` (`396–402`). A construction site that forgets the field disables the 4D learner without an error. Potential application: make the field required, or log the skip.
- **The Tobit fallback is also silent.** The live learner falls back to NLMS-only when its state is `None` (`414–415` and the comment above them). The fallback is designed for tests, but it is also the production path for any site that forgets to pass the state. The review did not check the construction sites.
- **The learning config is passed by value.** `LearningConfig` captures the settings for one hour, and says they must not change during a learning pass (`observation.py` header of the class). The shallow freeze (see the lesson above) is the gap: the list it holds can change under the pass.
- **The observation keeps its inputs.** `HourlyObservation` stores raw and battery-filtered values side by side (`103–146`), and the comment says the inequality learner uses the filtered one. A reader who wants the raw value has it, which is the right choice for audit.
- **Not read:** `observation.py` from `421` onward.

**Seventieth pass: `heat_source.py` (`1–160`, the heat-source classifier)**

- **Inference fails toward unknown.** A class is set only when every check passes (`23–32`): the whole κ set on one side of the cut, the change point off the sweep edge, and the curve unchanged without the coldest days. The default is `unknown`, which is today's behaviour. Potential application: any classifier should default to the no-change answer.
- **Provenance decides what a consumer may use.** The curve shape can come from an inferred type, but the COP level cannot be inferred from energy data (`38–42`). The consumer must check provenance, and this is written in the module header where the next editor will see it.
- **Days before a unit's first energy are not observations.** `unit_first_seen` skips days before a unit has any energy (`72–90`). A sensor added after setup would otherwise read as idle for every earlier day. This is the none-versus-zero rule from the forty-eighth pass, applied to units.
- **The reason ladder has a clear order.** `_curve_fit` tests the fit status, then the sweep edge, then the κ limit, then the flat and outdoor cuts (`115–126`). The first failing test sets the reason. An empty support list falls through to `cop_slope_not_identified`, which is the honest answer.
- **Today is never counted.** `_regime_days` stops before today (`142`, `145`), so a unit's current day never counts toward the classification. This is the right choice for a fit on closed days, and it is not stated in the docstring.

**Seventy-first pass: `thermodynamics.py` (`1–200`, the Track C engine)**

- **A comment says dhw rows are summed, and the code skips them.** The comment at `185–186` says the thermal energy of a dhw row should be zero, "but we sum it safely anyway". The code at `187` skips the row entirely, so the comment describes a branch that is not there. Potential application: a test with a non-zero dhw row would show which one is intended.
- **The daily COP has a fallback of 1.0.** When no electrical energy is recorded, the COP is set to 1.0 (`199–200`), which is the direct-electric value. The synthetic baseline then equals the thermal total, with no heat-pump advantage. The guard prevents a crash, but the number it gives is a choice, and the comment says only that it avoids division by zero.
- **The COP is clamped to 1 to 10.** `cop_at_conditions` returns a value between 1.0 and 10.0 (`117`), and returns 1.0 when there is no lift (`113`). The clamp prevents an implausible value from a bad parameter, and the docstring does not say so.
- **The solar multiplier is asymmetric.** In heating, the multiplier runs from 0 to 1 (`144`), so full sun can remove all demand. In cooling, it runs from 0.1 to 1.5 (`141`), so sun can add half again, and the minimum is never zero. The two bounds are not stated together, and the asymmetry is not explained in the docstring.
- **Not read:** `thermodynamics.py` from `201` onward.

**Seventy-second pass: `solar_optimizer.py` (`1–164`, the screen learner)**

- **Two meanings share the bucket `"0"`.** The horizon and the first ten degrees above it both bucket to `"0"` (`42–45`), as the lesson above describes. The learner stores only the upper range, and the predictor reads the same key for the horizon.
- **The migration comment says deep copy, and the code makes a shallow copy.** The legacy elevation map is copied with `state_data.copy()` (`157`), and the comment says "Deep copy". The map holds floats, so the shallow copy is harmless, but the comment is wrong and a later change to a nested value would share it.
- **The cloud gate is a named literal.** Learning is skipped at 20 % cloud cover or more (`88`), and the comment gives the reason: the user's action must be a response to the sun. The threshold is a literal, not a named constant.
- **Persisted data is migrated on load.** The legacy shape (elevation to percent) is copied to all twelve azimuth buckets (`152–157`). The migration is one-way and runs on every load, so it is idempotent, and the review did not check how a partly migrated file would load.

**Seventy-third pass: `retrain.py` (`1–200`, the replay helpers)**

- **The dry-run copy list is a second list of model state.** `_RETRAIN_MODEL_MAPS` names the stores a replay rebuilds (`88–100`). It does not name the 4D coefficients, the 4D learning buffer, the Tobit statistics or the NLMS shadow, the stores missed by the replace-sensor migration in the fifty-fifth pass. If a replay writes any of them, a dry run changes the live state. The review did not check the replay code for those writes.
- **A dry run restores the live objects.** `_install_model_copies` deep-copies the state, the dead-zone counters and each weighted-smear strategy, and `_reinstall_live_model` puts the originals back (`118–155`). The design is sound, and it is the right place to test the dry-run guarantee.
- **The MagicMock guard is written twice.** `_screen_affected_set_or_none` and `_solar_affected_set_or_none` (`42–65`) are the same test under two names. The comments give the reason: a mock would route every entity down the unscreened branch. A third guard would need a third copy, unless the pattern moves to one helper.
- **The 5 °C band is a literal.** `_temp_band` uses 5 °C steps (`158–167`), and the band key is a string, so `_band_order` has to parse it back (`170–174`). A key stored as a string and parsed on read is fragile; a tuple would not need the parse.
- **Not read:** `retrain.py` from `201` onward.

**Seventy-fourth pass: `sensor.py` (`1801–1918`, the week-ahead sensor and the comparison and learning sensors)**

- **A failed forecast reads as zero energy.** The week-ahead sensor catches three exception types and returns `total_kwh: 0.0` with a text summary (`1827–1832`). The state is a number, so a dashboard reads a failed forecast as a week with no consumption. A `ValueError` is not caught at all, and it fails the sensor instead. Potential application: return unknown for the state, and keep the error in an attribute.
- **The cache is keyed on the hour.** The week-ahead result is reused within the same hour and day (`1814–1820`), so a forecast change is seen at the next hour boundary. The cost is one stale hour, and the code does not say so.
- **The comparison sensor returns no attributes when there is no comparison.** `extra_state_attributes` returns `None` (`1875–1876`), which Home Assistant treats as no attributes. The state is a text, not a number, which is correct for a comparison.
- **The learning sensor exposes its inputs.** The U-coefficient is rounded to four places and reported in `kWh/TDD` (`1897–1901`), and the attributes give the indoor sensor and the learning rate (`1904–1910`). A user can check the learning without reading the code.
- **Not read:** nothing further in `sensor.py`.

**Seventy-fifth pass: `coordinator.py` (`3301–3465`, the live update: outdoor sensors, solar and wind)**

- **A missing temperature becomes the 0 °C key.** When no calculated temperature exists, `temp_key` is the string `"0"` (`coordinator.py:3393`). The potential-impact loop then reads the 0 °C coefficient for every unit (`3397–3406`), so a missing sensor reports a solar figure as if it were freezing. The string `"0"` is also a real temperature key.
- **Wind falls back to zero, and the hour moves to the normal bucket.** With no wind speed, `wind_speed` becomes `0.0` (`3370–3371`). The warning is throttled to one an hour (`3373–3381`) and says that wind differentiation is disabled. A sensor outage therefore changes the model's output, not only its log.
- **The humidity default is stated in a warning.** The warning says Track C uses a 50 % default (`3335–3340`). The review did not check that the COP code uses the same value.
- **Solar fields are set on different conditions.** The solar factor and vectors are written every tick when solar is enabled (`3343–3360`). `ATTR_SOLAR_IMPACT` is initialised only when missing (`3367–3368`). With solar disabled this block does not run, and the review did not check the value the impact starts with.
- **A meter reset and a spike both move the baseline and drop the hour's delta.** A reading below the last one is a reset (`3475–3478`). A delta above `max_energy_delta` is a spike (`3481–3484`). Both set the baseline to the new reading and skip the delta, so a real burst of consumption after an outage is never counted.
- **An unavailable meter keeps its old baseline.** When the state is not a number, the sensor is skipped (`3468–3469`) and the baseline stays where it was. The next valid reading then carries the whole gap, which lands in the hour the meter returns. A gap large enough to trip the spike test is dropped.
- **Not read:** nothing further in `3301–3465`. The energy block continues in the next pass.

**Seventy-sixth pass: `coordinator.py` (`3466–3628`, energy totals, thermal state and trend)**

- **The trend reads "stable" when there is nothing to compare.** If the newest reading exists but both older readings are missing, `hours_back` stays at 0 and the rate is set to 0.0 (`3579–3580`, `3590`). The result is `"stable"` (`3597`). The branch for fewer than two readings returns `"unknown"` (`3599–3601`). Potential application: return `"unknown"` whenever no comparison exists.
- **The cold/mild split is a literal.** The regime is `Cold` when `tdd_target > 4.0` (`3555`). This is one of the copies of the 4 °C boundary that the mirror-a-constant lesson names.
- **The thermal state records its own inputs.** The readings the effective temperature averages and their normalised weights are written out (`3524–3531`). A reader can check that the weighted sum equals the effective temperature. This is the verification the design asks for.
- **Two different quantities share one name.** `degrees_to_balance` is signed (`3563`), and `instant_tdd` uses the absolute target (`3567`). The names do not say which is signed.
- **Not read:** nothing further in `3466–3628`. The `_update_*` calls after `3609` are in earlier passes.

**Seventy-seventh pass: `coordinator.py` (`3630–3733`, accumulated impacts for the day)**

- **Guest energy is counted in two totals.** `heating_modes` includes `MODE_GUEST_HEATING` (`3643`). The live loop adds a guest unit to the guest impact (`3692–3693`) and to the heating total (`3694–3695`). The review did not check whether the display subtracts guest energy from the heating total.
- **"Today" is a string prefix.** Both sums select hours with `startswith(today_date_str)` (`3647`, `3712`), where the date comes from `current_time.date()` (`3632`). Whether a late-evening hour counts as today depends on the timestamp's form and the zone of `current_time`. The review did not check the format, which is the same question as the replay cutoff.
- **A sparse mode map defaults to heating here too.** The loop uses `entry_unit_modes.get(eid, MODE_HEATING)` (`3664`), and its comment gives the reason. This matches the rule in the sparse-map passes.
- **The constant's name carries the wrong unit.** The comment at `3677` says the solar impact is stored as kW, though its constant name has a kWh suffix. It is multiplied by minutes over 60 to give kWh (`3679`, `3725`).
- **A missing live temperature picks one sign.** `current_calc_temp` falls back to the balance point (`3721`). At that value the solar term takes the `>=` branch and is subtracted (`3728–3729`). The fallback therefore decides the sign for the whole hour.
- **Gross today uses two formulas.** Completed hours use the stored `thermodynamic_gross_kwh` (`3713`). The live hour recomputes it from net, aux and solar (`3723–3731`). The review did not check that the two agree.
- **Not read:** nothing further in `3630–3733`.

**Seventy-eighth pass: `coordinator.py` (`3735–4006`, model helpers, state accessors and delegators)**

- **A real 0 °C temperature is replaced by the key.** `_get_aux_impact_kw` and `_get_aux_impact_kw_per_unit` treat `actual_temp == 0.0` as "not given" and read `float(temp_key)` (`3772–3776`, `3788–3792`). The comment at `3770–3771` says the value is unused for aux, and the aux call does not scale (`apply_scaling=False`, `3779`). The sentinel has no effect today, but it is a trap if scaling is added.
- **A placeholder issue number is in a comment.** The note on historical callers cites "(#xxx)" (`3821`). Potential application: fill the reference or remove it.
- **The rolling power uses the wall clock and the last log entry.** `calculate_unit_rolling_power_watts` reads `dt_util.now()` (`3839`) and takes the previous hour from `_hourly_log[-1]` (`3847–3850`) without checking that entry's timestamp. After a logging gap, the "last hour" can be much older, and the sensor still uses it.
- **Model state is shared, and the read-only rule is not enforced.** `get_model_state` returns references and asks consumers to treat them as read-only (`3900–3905`). Nothing enforces that.
- **The unit cooling bucket is set in two places.** `_get_predicted_kwh_per_unit` (`3762–3763`) and `_get_unit_observation_count` (`3824–3825`) both force the cooling bucket. Both match the write-side routing in learning, which is good, but the rule lives in two copies.
- **The delegators hide their signatures.** `_process_daily_data` and the other delegators take `*args, **kwargs` (`3962–4005`). An argument mistake fails inside the target, and no check reads the target's signature from the coordinator.
- **Not read:** nothing further in `3735–4006`. The range ends at the delegators. The setup and service handlers are earlier in the file (`784`, `789`, `1150`, `1188`, `1971`).

**Seventy-ninth pass: `storage.py` (`49–244`, the pre-v3 migration)**

- **The idempotence claim is wrong for one step.** The docstring says every branch guards on shape (`storage.py:102–103`). The battery step guards on the `battery_model` marker (`231`) and sets it (`235`) whether or not the stored state was a number (`232–234`). A non-numeric state stays unscaled, and the marker says the conversion happened.
- **A missing azimuth zeroes every migrated coefficient.** The migration builds the south, east and west terms from `solar_azimuth` (`124–141`). Both callers read it with `getattr(self.coordinator, "solar_azimuth", 0.0)` (`628`, `1718`). At azimuth 0 every term is zero, so a coordinator without the attribute migrates each flat coefficient to `{s: 0, e: 0, w: 0}`. The review did not check whether the attribute always exists.
- **A missing weight is written as 0.0 and then read as measured.** An old `(s, e, impact)` sample becomes `(s, e, 0.0, impact)` (`165`). It contributes no west term, and the learner reads that zero as a measurement.
- **Malformed entries disappear on save.** A solar entry that is not a dict is skipped (`127–128`), and the rebuilt map replaces the old one (`143`). A buffer item that is not a list or tuple is skipped the same way (`159–160`). Neither case writes a log line.
- **Not read:** the v3 to v4 migration is in the next pass.

**Eightieth pass: `storage.py` (`245–300`, the v3 to v4 solar split)**

- **A migration seeds a new regime with a guess.** A flat coefficient is copied into both regimes (`290–295`). The docstring says this keeps manually seeded values, and that cooling drifts toward its own value once cooling hours arrive (`262–267`). A heating-only install keeps the copied cooling value (`265–267`). The stored shape does not say which values were copied.
- **Samples are routed by a stated bias.** Migrated buffer samples go to `"heating"` (`271–274`), because the docstring says the install base is mostly heating. The docstring says the next cold-start solve flushes them within about four hours. The review did not check the flush.
- **Malformed entries are dropped without a record.** A non-dict entry is skipped (`284–285`), and the rebuilt map replaces the old one (`296`). This is the same loss as in the previous pass.
- **Idempotence is by key presence.** An entry that already has `heating` or `cooling` passes through unchanged (`286–289`). Re-running the migration therefore never changes a stratified value. This is safe for the shape.
- **Not read:** the buffer migration from `298` and the rest of `_migrate_v3_to_v4`.

**Eighty-first pass: `statistics.py` (`1387–1520`, the 4D prediction path)**

- **A fallback stamps its own marker.** When the 3D fallback runs for lack of irradiance, the result is marked with `pipeline` `"3d_no_irradiance"` and `dni_dhi_source` `"none"` (`1396–1397`). The comment says the marker exists so a 4D install can see that 3D ran.
- **The second source for the aux set is dead in production.** `aux_affected_set` comes from `_aux_affected_set` when the coordinator has it (`1426–1427`). The list fallback (`1428–1429`) runs only without that attribute. The coordinator sets the set at startup and defines the property (`coordinator.py:3954–3956`), so the fallback serves test doubles only.
- **A missing method falls back silently.** `screen_config_for_entity` is fetched with `getattr(..., None)` (`1484–1487`) and the global screen configuration is used when it is absent. The coordinator defines the method, so a rename would give every unit the global configuration without an error.
- **The cooling cold-start check runs for every unit.** `cooling_solar_cold_start` is computed (`1476–1479`) before the gate test that uses it (`1480`). When the gate is closed, the check still calls `_is_cooling_solar_cold_start` for each unit and discards the result. The cost is small.
- **Track A matches its comment.** `global_base` comes from the 3D function (`1405`), and the comment says 4D does not alter the base or aux surfaces (`1404`). The code matches the comment.
- **Not read:** from `1521`, the rest of the 4D breakdown.

**Eighty-second pass: `balance_point.py` (`155–400`, grids, day assembly and wind rules)**

- **An invariant checked at import uses `assert`.** The grid check (`173–176`) runs at import and is removed by `python -O`. A broken grid then passes silently in an optimised run.
- **A fallback that changes the fit's input is not reported.** `_inertia_kernel` returns no kernel when the weights are not numeric or sum to zero (`212–220`). The fit then uses the raw hourly temperature (`56–57`, as the docstring says). The day records do not say which temperature was used. The review did not check whether the fit result does.
- **Two rules share one discard reason.** High-wind days are counted from the hourly vector (`382–389`) when it exists. Without one, the day's mean wind is compared with the threshold (`391–392`). The same `high_wind` reason can then mean "more than the allowed hours" or "a mean above the threshold".
- **Any aux energy discards the whole day.** A positive aux energy total skips the day (`375–377`). The docstring says so (`62–66`). A short aux run therefore costs the whole day, and the docstring should give that cost.
- **Yesterday's sun defaults to today's.** When yesterday is not in the history, `solar_prev` is today's value (`325–328`). The comment states the assumption. The review did not measure its effect.
- **Not read:** nothing further in `155–400`. The rest of `collect_days` was read in the fourteenth pass.

**Eighty-third pass: `balance_point.py` (`434–640`, the fit and its variance)**

- **The solar-shifted base is written twice.** `fit_change_point` builds it inline (`482–483`), and `_bases` builds it again (`566–568`). `_fast_sse` uses `_bases`. The two forms match today, and a change to one leaves the other behind.
- **`_fast_sse` has no test.** The earlier pass checked its algebra. No test in the clone names `_fast_sse`, so the agreement with `fit_change_point` is not checked after an edit.
- **The solar reference is a lower quantile.** `_solar_reference` takes `int(q · (n − 1))` (`456`). It rounds down rather than interpolating, so a small sample gives a reference at the lower end.
- **The autocorrelation sum is clamped at one.** `_variance_inflation` returns `max(1.0, long_run)` (`556`), so negative autocorrelation cannot narrow the interval. The docstring says so (`537–538`).
- **A negative intercept is refitted through zero.** When the intercept is below zero, `fit_change_point` refits with `b = 0` (`502–508`). The docstring gives the reason (`474–475`).
- **Not read:** nothing further in `434–640`.

**Eighty-fourth pass: `retrain.py` (`201–345`, the model diffs and the dry-run entry)**

- **A non-dict store is compared as empty.** `_per_unit_map_diff` (`263–264`) and `_solar_coefficient_diff` (`287–288`) replace a non-dict input with `{}`. A corrupt map therefore appears in the dry-run diff as every bucket added, not as an error.
- **A change under the tolerance is not a change.** `_bucket_map_diff` counts a bucket as changed only when the difference exceeds `_DIFF_TOLERANCE` (`225`). Smaller moves are left out of the counts and the ranking. The review did not check the tolerance's value.
- **The diff covers six stores.** `_model_diff` compares the global base, per-unit base, global and per-unit aux, solar coefficients and learned U (`312–331`). It does not compare the 4D coefficients, the Tobit statistics or the NLMS shadow. Those are the stores the dry-run copy list omits (seventy-third pass), so a dry run cannot report a change to them.
- **The dry run fetches before it returns.** `retrain_from_history` awaits `_fetch_track_b_cop_params(cache=not dry_run)` (`377–379`) before the dry-run branch (`382`). The fetch is the same network read as a real run, and only the cache write is skipped. The docstring says a dry run writes and saves nothing (`369–371`). That is true of the store, but the request still goes out.
- **An empty fit reports `None`, not zero.** `_fit` returns `None` for the bias and RMSE when there are no pairs (`337–338`). A caller that reads the value as zero would report a perfect fit.
- **Not read:** `retrain.py` `160–200`.

**Eighty-fifth pass: `storage.py` (`300–546`, the v4 to v10 migrations)**

- **The v4 to v5 step mutates its input.** `_migrate_v4_to_v5` calls `setdefault` on `data` directly (`344–346`), where the v5 to v6 and later steps first copy with `dict(data)`. A caller that keeps the original sees the change. Potential application: copy in every step, and test that the input is unchanged.
- **The v8 to v9 step turns a stored non-dict into all-`None` gates.** A non-dict per-entity value becomes `{"low": None, "high": None}` for every facade (`427–433`). A corrupt entry therefore reads as "no gate", the same as a clean install. The docstring does not mention this branch.
- **The v9 to v10 step guesses only at its last resort, and says so.** The stamp comes from the day's logged balance point, then from the day's vectors, then from the oldest logged balance point (`495`, `501–506`). The oldest hour is picked with a text comparison, `ts < oldest[0]` (`493`), which is the same concern as the replay cutoff in the forty-eighth pass.
- **The heat-source loader copies one level deep.** `_heat_source_state_from` makes `dict(unit)` per unit (`539`), so nested values are shared with the stored object.
- **Not read:** the load path (`695–1431`).

**Eighty-sixth pass: `statistics.py` (`1521–1656`, the rest of the 4D shadow partition)**

- **The fallback scope is every energy sensor.** `scope_set` falls back to `frozenset(self.coordinator.energy_sensors)` when `_solar_affected_set` is missing (`1530–1532`). The partition then has no out-of-scope units. See the lesson on a missing scope.
- **Two aux savings figures overlap.** The overflow and the orphaned remainder are both added to `unassigned_aux_savings` (`1552`, `1605–1606`). The return then reports `unassigned_aux_savings` (`1649`) and `orphaned_aux_savings` (`1650`) as separate keys. A reader that adds them counts the orphaned savings twice.
- **The carry-over release is a fixed zero.** `carryover_release_applied` is set to `0.0` (`1627`), with a comment saying the 4D path leaves it out. The key stays in the output so shadow and live can be compared.
- **The unspecified residual is signed.** `unspecified_kwh = global_net - unit_sum_net` (`1629`) can be negative. The review did not check whether any caller clamps it.
- **Not read:** `calibrate_inertia` onward (see the eighty-ninth and ninetieth passes for what was read).

**Eighty-seventh pass: `retrain.py` (`160–200`, the band helpers)**

- **Temperature bands are 5 °C floors.** `_temp_band` returns `"{low}..{low+5}"` (`166–167`), and returns `"unknown"` for a non-numeric or non-finite value (`161–165`). The band key is text.
- **`_band_order` reads the band back from its text.** It splits on `..` and parses the lower edge (`170–174`), and returns infinity when the parse fails. A band string written by another code path that uses a different format sorts last without an error.
- **A bare number has a sentinel bucket.** `_flatten_buckets` stores a bare value under the bucket `"-"` (`192–195`). A real wind bucket named `"-"` would collide with it. The review did not find such a bucket in the code.
- **The helpers do no I/O and no mutation.** They build new values and never write to the input, which is what the diff step needs.

**Eighty-eighth pass: `daily_processor.py` (`334–465`, the hourly vectors and the day record)**

- **Temperature is read strictly, and the other fields are not.** `hourly_avg_temp` uses `e["temp"]` (`377`), while wind, solar and energy use `.get` with a default (`378–383`). A log entry without `temp` raises `KeyError` and stops the whole day. Whether any writer omits `temp` was not checked.
- **A missing energy value counts as zero.** `sum_load` and `sum_tdd` default to `0.0` (`382–383`). A logged hour with no `actual_kwh` looks like an hour of no use, not an unknown one. This is the same zero-versus-missing distinction as the forty-eighth pass.
- **An hour with no entries stays `None`, and a 4D field uses presence.** The 4D fields are included only when the key is present (`400–418`), so a missing hour is not averaged in as zero.
- **The provenance is the last entry in list order.** `day_logs[-1]` (`421`) is the last in the list, not the last by time. The review did not check that the list is sorted.
- **Balance point is written only when it is known.** The key is added only when `tdd_bps` has a single value (`438–442`). A day without the key is read as a legacy day, which matches the v10 migration.
- **Not read:** `backfill_from_hourly` (`465–`) and the midnight sync.

**Eighty-ninth pass: `balance_point.py` (`640–779`, the sweep)**

- **The refine step is accepted only when it is strictly better.** `fine` replaces `coarse` only if its SSE is lower (`660`). A tie keeps the coarse fit.
- **The sweep range is widened by the solar reach.** The lower and upper bounds extend by the largest solar shift (`719–721`), and the comment explains that sun can move a day onto the flat side.
- **The reported sweep range is the survivors, not the request.** `evaluated` and `swept_range` come from `fits`, which dropped `None` profiles (`728–733`, `746`, `770`). See the lesson on boundary checks.
- **The interval uses the same survivors.** `in_interval` is built from `fits` (`744`), so a dropped candidate cannot widen the interval, and a candidate that dropped out also cannot narrow it.
- **The proportional zero divides by the slope.** `gap = best["b"] / best["U"]` (`751`). The review did not check whether `U` can be zero at the sweep's selected point.
- **Not read:** `_sweep_once` from `780` and the public fit entry points after it.

**Ninetieth pass: `statistics.py` (`3552–3661`, `calibrate_inertia` pure-hour filter)**

- **The window is built on instants, not text.** The logs are sorted by instant (`3593`), and each log lands in a slot counted from the first instant (`3598`). A missing hour becomes a `None` slot, so the kernel weights readings by their true age. This matches the live `weighted_inertia` rule.
- **The first filter is by text.** `log["timestamp"] < start_iso` (`3588`) compares strings, while the sort and the slots use instants. See the lesson on filters.
- **A missing energy value is discarded as zero.** `log.get("actual_kwh", 0.0)` (`3603`, `3606`) sends a logged hour with no energy into the `zero_or_negative_consumption` count (`3607–3609`). The count cannot separate missing data from a true zero.
- **The solar cut is a literal in kWh.** `solar_impact > 0.1` (`3612`) is labelled as 100 W, which holds only for one-hour log entries.
- **The centred average uses unfiltered neighbours.** The smoothing reads `raw_kwh[idx - 1]` and `raw_kwh[idx + 1]` (`3645–3646`), and `raw_kwh` holds every hour, including the aux and solar hours the filter removed. A pure hour can therefore be averaged with an aux hour's energy. The review did not check whether that is intended; the comment says "surrounding hours".
- **Not read:** the rest of `calibrate_inertia` from `3662`.

**Ninety-first pass: `storage.py` (`695–824`, the load path start)**

- **An empty legacy store matches every instance.** The legacy migration accepts a file when `not stored_sensors or stored_sensors & instance_sensors` (`storage.py:713`). A legacy file with no sensor keys is therefore imported into any instance, which is the case the guard exists to stop.
- **The migration writes during the load.** It calls `async_save(legacy_data)` (`719`) inside `async_load_data`, and does not remove the legacy key. A failed save is not reported where the load reads it.
- **The corruption notice uses a different API from the coordinator.** `hass.components.persistent_notification.create` (`737`) is not the call `coordinator.py:967–969` uses. See the lesson on one helper.
- **Solar coefficients alone are sanitised on load.** `_sanitize_stratified` (`785`) runs on the solar coefficients, while the aux and correlation maps are copied as they are (`774–776`, `764–766`).
- **Not read:** the rest of the load path from `825`.

**Ninety-second pass: `storage.py` (`825–954`, the Tobit state and the buffers)**

- **A stat with no version is kept as current.** The drift filter reads `stat.get("solar_model_version", _CURRENT_SOLAR_VERSION)` (`836–838`), so a stat written before the field existed passes as current. The default makes a missing stamp look like a match.
- **Dropped stats are gone after the next save.** Stale stats are dropped at load (`839–841`) and logged once (`849–858`). The next save writes only what was kept.
- **The default-on flag is set on the first load, not stored.** The marker logic (`883–897`) forces the flag to `True` when `_tobit_default_applied` is missing. The docstring explains the intent, and the marker keeps later loads from flipping it again.
- **A stored string counts as true.** `bool(data.get("experimental_tobit_live_learner", False))` (`862–864`) accepts any value. A stored string `"false"` becomes `True`. Whether any writer stores a string was not checked.
- **Buffers are rebuilt with tuples.** Samples are turned from lists into tuples (`934`), and regime keys are filtered to heating and cooling (`937`). Other keys in a stored buffer are dropped without a log line.

**Ninety-third pass: `balance_point.py` (`780–909`, the cop sensitivity, variance weights and outliers)**

- **Stability is `None` at the limit, not `False`.** `_cop_sensitivity` returns `None` when the best slope sits on the upper limit (`851–860`), and says that the check cannot be run. A caller that treats `None` as false would report an instability that was never tested.
- **Zero spread drops nothing.** `_outlier_mask` skips an arm whose median absolute deviation is zero (`911–912`). A perfectly flat arm therefore flags no days, however large a residual is.
- **The variance floor is set by a share of the mean.** `s0` is floored at `BP_CALIBRATION_VARIANCE_FLOOR_SHARE` of the mean squared residual (`889`), and the weight ratio is capped (`891–892`). Both caps are named constants, so the limits can be read in one place.
- **The median is the upper middle value for an even count.** `values[len(values) // 2]` (`909`) does not average the two middle values. The effect is small, but the docstring says "robust", not exact.

**Ninety-fourth pass: `balance_point.py` (`910–1040`, the variance prior, the sweep and the impact count)**

- **A failed prior silently drops the weighting.** `sweep` runs unweighted when `variance_prior` returns `None` (`968–975`). The result says `weighted: False` (`775`), but the caller is not told why the weights are missing.
- **The outlier share has a hard stop.** A share above `BP_CALIBRATION_MAX_OUTLIER_SHARE` changes `fitted` to `poor_fit` (`989–993`). The report keeps the share (`988`), so the reason is visible.
- **The impact count compares timestamp text.** `_impact` skips entries with `entry.get("timestamp", "") < cutoff_iso` (`1005`). It is the same text comparison as the replay cutoff in the forty-eighth pass.
- **The impact count reports four separate effects.** The regime, shield, side and hour counts are kept apart (`1012–1022`), so a user can see which classification a change would alter.

**Ninety-fifth pass: `balance_point.py` (`1040–1159`, the flat bottom, the snapshot and the report entry)**

- **The flat-bottom walk stops at a gap.** `while (lo - 1) in curve` (`1048–1050`) ends at the first missing key. See the lesson on indices.
- **The snapshot copies the log by reference.** `model_snapshot` deep-copies `daily_history` (`1082–1086`) but only shallow-copies `hourly_log` (`1087`). The docstring says copies are taken so the fit does not race the coordinator, and that holds for the days but not for the log entries.
- **One verdict covers three failures.** A status of `insufficient_days`, `data_does_not_bracket_sweep_range` or `no_temperature_response` all become `insufficient_data` (`1137`). See the lesson on verdicts.
- **Stability needs both halves to fit.** The check at `1154–1157` requires both halves to be `fitted` before it compares their change points, so a half that fails reports no stability at all.
- **The halves reuse the full-sample weights.** Both halves take the prior computed on all days (`1109–1116`), as the `variance_prior` docstring intends (`929–930`).

**Ninety-sixth pass: `forecast.py` (`1460–1579`, the daily forecast start)**

- **A missing high temperature becomes 0 °C.** `temp_high = float(daily_item.get("temperature", 0.0))` (`1467`) defaults to zero, and the low falls back to the high (`1468`). A daily item with no temperature forecasts at 0 °C without an error. This is the copied-value lesson again.
- **An invalid gust becomes no gust.** A gust that fails to parse becomes `None` (`1484–1485`) with no log line, and the effective wind is then computed without it.
- **Bad carry-over and decay values become defaults quietly.** `getattr` with a type check falls back to `0.0` and to `SOLAR_BATTERY_DECAY` (`1509–1512`). A wiring error in the coordinator would look the same as no carry-over.
- **The 4D flag is compared with `is True`.** `flag_4d = ... is True` (`1514`) treats any truthy non-boolean as off. Storage reads the flag as a bool, so this is consistent, but a string from a config would turn the 4D path off without a message.
- **Local midnight is taken from the current zone.** `dt_util.now().replace(...)` (`1544–1552`) keeps the zone of the current time, and the comment says why. The review did not check the day of a daylight-saving change.

**Ninety-seventh pass: `forecast.py` (`1580–1699`, the 24-hour loop and the legacy path)**

- **The 4D branch does not pass the carry-over that the loop evolves.** The loop updates `local_carryover` each hour (`1648–1650`), and the dark-hour call passes it (`1638`). The lit-hour 4D call does not pass `carryover_state_override` (`1615–1624`). `calculate_total_power` then uses the live state (`statistics.py:1030–1031`) for every lit hour. Unless the live state equals the local one, the two parts of the same day use different carry-over. The review did not run this.
- **The auxiliary flag is held for the whole day.** `is_aux` is read once from `auxiliary_heating_active` (`1507`) and passed to all 24 calls (`1619`, `1634`). A day forecast cannot see a change of aux state during the day.
- **The 24 hours are absolute hours from a local midnight.** `hour_dt = day_start_local + timedelta(hours=hour_idx)` (`1584`) adds real hours. On a daylight-saving day the local clock hour can repeat or skip. The review did not check the loop's behaviour on those two days.
- **The legacy branch scales one call by 24.** The 3D path (`1693–1694`) multiplies one call by 24, and the carry-over factor is solved for that (`1661–1677`). The 4D path needs no factor because each hour computes its own release, as the comment says (`1672–1675`).

**Ninety-eighth pass: `diagnostics.py` (`454–583`, monotonicity, buckets and mode contamination)**

- **Non-numeric temperature keys are skipped in one check and not in another.** The monotonicity loop skips keys that do not parse as an integer (`479–481`). The bucket summary then calls `min(..., key=int)` and `max(..., key=int)` on the same keys (`533–534`) with no guard, so one bad key raises there. This is the key-format lesson from the fiftieth pass.
- **A unit with no recorded mode counts as heating.** `unit_modes.get(sid, "heating")` (`566`) means a unit missing from the mode map is not counted as contamination. This is a default assumption, not a recorded value.
- **The cutoff is a date-text comparison.** `ts[:10] < cutoff_str` (`552`) compares the first ten characters of the stored timestamp. The review did not check which zone the stored timestamps are in.
- **Monotonicity checks adjacent pairs only.** Each pair of neighbouring temperatures is compared (`491–501`). A bucket with a bad middle value shows one inversion per side rather than one finding.

**Ninety-ninth pass: `diagnostics.py` (`584–713`, solar correlation and the dark-hour replay start)**

- **Three thresholds decide what "solar" means.** The solar correlation uses 0.01 (`599`), the dark-hour replay uses 0.05 (`687`), and the learning code uses 0.05 (the comment at `589`). A reader comparing reports sees different hour counts without a stated reason.
- **Excluded energy is floored at zero.** `adjusted_actual = max(0.0, actual - excluded_kwh)` (`616`) hides an hour where the excluded energy is larger than the metered total. The residual is then computed from zero, not from the difference.
- **A zero-variance sample reads as no correlation.** `correlation = ... if denom > 0 else 0.0` (`642`) returns the same value for "no correlation" and "no variation". See the lesson on undefined values.
- **The dark-hour replay skips a flag, not the full aux test.** It skips hours with `auxiliary_active` set (`793`). The inertia calibration says that flag is the 80 % learning flag, and that it admits partial-aux hours; it uses `hour_had_any_aux` instead (`statistics.py:3616–3620`). A partial-aux hour can therefore enter the dark-hour reference.
- **A missing actual is read as zero in one helper.** `_reference_dark_kwh` returns `0.0` for a missing `actual_kwh` (`762–764`). The caller filters those hours out first (`797`), so the branch should not run. It is a zero default in a helper that could be reused.
- **A Track C hour with no distribution entry falls back to raw.** The hour uses raw actual energy and is not counted as Track C (`771–776`). The per-bucket count keeps the mix visible.

**One hundredth pass: `hourly_processor.py` (`1–260`, the 4D boundary overrides and the observation build)**

- **A broad `except` moves the hour to the 3D pipeline.** `_resolve_4d_boundary_overrides` returns `None` on any exception (`146–149`), and the caller then uses the legacy 3D form. The docstring warns that this mixes pipelines in one log row (`88–95`). A real error in the 4D inputs therefore changes the model for that hour and leaves no trace.
- **The midpoint uses the collector's start, not the hour's.** `mid_dt = start + 30 min` (`116–117`) takes `start` from the collector when it has one. A collector that began part-way through the hour puts the midpoint too early.
- **The observation hour is the clock hour.** `hour=timestamp.hour` (`213`) is the local clock hour. On the repeated daylight-saving hour two entries share that number. The daily processor keys its slots by the same number, and the forty-fourth pass covers the same issue.
- **Zero units are dropped from the breakdown.** `unit_breakdown`, `unit_expected` and `unit_expected_base` keep only entries with `kwh > 0` (`230–244`). A reader must treat an absent unit as zero, not as missing.
- **The observation fallback uses the current time.** When the collector has no start, `timestamp` is `current_time` (`210`). The hour then takes the wall-clock time, not the hour boundary.
- **Not read:** `build_observation` from `261`, and `process` and the gap fill after `260`.

**One hundred and first pass: `learning.py` (`1340–1556`, the global base and the legacy wrapper)**

- **Buffering reports zero as the new prediction.** While the cold-start buffer is filling, `new_base_prediction` is set to `0.0` (`1408`) and the bucket is not written. The return value therefore says the base is zero when no value was learned. This is the zero-versus-missing distinction from the forty-eighth pass.
- **A zero-rate hour is read but not stored.** The sample is appended only when `base_effective_rate > 0.0` (`1393–1395`). The buffer length is then checked at `1397` either way, so a zero-weight hour can trigger the jump start on a buffer that did not grow.
- **The 4D weight falls back to the 3D factor without a log line.** When `_compute_4d_solar_factor_for_snr` returns `None`, the 3D `solar_factor` is used (`1365–1367`). Which factor the weight came from is not in the output.
- **Optional config reads fall back to defaults.** `getattr(config, ...)` with defaults for the Tobit and MPC settings (`1454–1462`) makes a missing attribute read as off. A wiring error would look like a disabled feature.
- **The legacy wrapper discards the caller's wind and solar.** See the lesson on compatibility wrappers. The wrapper also passes `hour=0` and a naive `datetime.now()` (`1498–1500`), so the timestamp the new path reads is not the hour being learned.
- **Not read:** from `1667` to the end of `learning.py` (7,899 lines in the clone). The review's coverage of this file ends there.

**One hundred and second pass: `balance_point.py` (`1160–1204`, the verdict and the suggestion)**

- **The verdict is the first match in an ordered chain.** The order is: sweep boundary, `nuisance_at_limit`, `poor_fit`, `insufficient_data_for_stability`, `unstable_across_halves`, `cp_depends_on_cop_slope`, `current_is_consistent`, `suggest_change` (`1165–1190`). A boundary optimum therefore hides an instability, because it is checked first. See the lesson on verdict ladders.
- **`current_is_consistent` merges two causes.** It is true when the current value is inside the interval, or when the change is under `BP_CALIBRATION_MIN_SUGGESTED_CHANGE_C` (`1184–1188`). Only the verdict is stored.
- **The impact is computed from a text cutoff.** `cutoff` is an ISO string (`1195`) passed to `_impact` with the hourly log. The comparison inside `_impact` was not read.
- **The verdict does not change the stored value.** The report gives a recommendation string and asks for a retrain (`1198–1203`). Nothing writes the balance point, so the verdict and the stored value can disagree until the user acts. This is deliberate, but the report should say so.

**One hundred and third pass: `hourly_processor.py` (`261–380`, the head of `process`)**

- **Cooldown exits by time first.** The maximum-duration test runs first (`334`). Convergence is tested only when the expected sum is above `ENERGY_GUARD_THRESHOLD` (`352`). Otherwise the cooldown logs a debug line and stays on.
- **With no affected list, convergence cannot fire.** `aux_affected_entities or []` (`345`) gives an empty target list when the value is `None`, so the expected sum is zero and the cooldown runs to its maximum. See the lesson on sentinels.
- **Learning energy is split by mode at the hour boundary.** Guest units go to `guest_impact_kwh`, and off and DHW units are left out of `learning_energy_kwh` (`470–482`). The split uses the mode at the hour boundary. Whether a mode change inside the hour is handled was not checked.
- **The forecast consumer indexes a tuple by position.** `_forecast_point_kwh` reads `result[0]` (`284–307`). Its docstring records a live crash after the tuple grew from 8 to 12 fields, and says the tests fed `None` items, which return before the call. Potential application: test each consumer with a populated item, and name the fields.

**One hundred and fourth pass: `learning.py` (`1667–1790`, the per-unit base loop)**

- **The cooldown gate treats `None` as all affected.** With `aux_affected_entities` set to `None`, `is_affected` stays `True` and every unit is skipped (`1747–1753`). Base learning stops for the whole cooldown. See the lesson on sentinels.
- **Unreported units are skipped.** `per_unit_hour_actual` returns `None` for a sensor with no reading, and the loop continues (`1719–1722`). This is the zero-versus-missing rule done correctly.
- **The expected base falls back silently.** If the per-unit baseline is missing, `get_predicted_unit_base_fn` is used (`1758–1761`). The review did not check whether that function uses the same temperature key.
- **The SNR weight is computed once per hour, lazily.** The first call computes it (`1691–1709`). Aux-active hours never reach the call.
- **Presence of a key is the signal.** The 4D fields are emitted only when `shadow_4d_fired` is set (`1677–1690`). Absence means no 4D learner ran, which is the "presence as signal" pattern.

**One hundred and fifth pass: `learning.py` (`1791–1910`, the solar learning gates, outlier filter and Tobit routing)**

- **The solar gate is a chain of five tests.** Solar enabled, vector magnitude above 0.1, not aux, not solar shutdown, and base at or above the threshold (`1815–1821`). The per-unit override applies to both thresholds only when it is positive (`1809`).
- **The outlier residual uses the current coefficient.** The residual is actual minus predicted from the coefficient in use (`1855–1878`), and it is checked before either learner runs.
- **Empty allow-list means different things by release.** An empty `tobit_live_entities` is treated as automatic (`1845–1854`). Before 1.3.5 an empty list meant off. A stored value kept across an upgrade changes meaning. Potential application: migrate the value explicitly.
- **Impact sign is reversed by regime.** Heating uses base minus actual, and cooling uses actual minus base (`1866–1869`). The Tobit call also requires a positive impact (`1890`).
- **The NLMS shadow runs only when Tobit wrote.** The shadow update needs `tobit_applied` and no outlier (`1902`). During Tobit cold-start there is no shadow comparison.

**One hundred and sixth pass: `daily_processor.py` (`465–590`, the backfill and the Track C fetch)**

- **The backfill groups by a text slice.** Each log is grouped by `timestamp[:10]` (`465–475`). The zone of the stored timestamp was not checked here.
- **A new day needs twenty logs.** A day missing from the history is created only from twenty or more logs (`487`). Shorter days are never created.
- **A partial day is skipped, a complete day is overwritten.** When the history is larger than the logs by more than the margin of `max(1.0, 5%)`, the day is skipped (`507`). Otherwise the stored day is overwritten with the aggregate (`514`), and the regime split keys are dropped if the logs cannot support them (`519`). This is a good pattern: stored data the new source cannot support is removed.
- **A schema change reads as an empty buffer.** The response is accepted under `buffer`, `data` or `hourly`, and anything else becomes an empty list (`557`).
- **A fetch writes state.** `fetch_mpc_buffer_and_cop` stores the COP parameters on the coordinator (`578`). COP errors are swallowed (`579–580`).

**One hundred and seventh pass: `forecast.py` (`1700–1940`, the forecast sum and its uncertainty helpers)**

- **The carry-over state is threaded through the items.** `_sum_forecast_energy_internal` decays the state for hours before the window and updates it after each in-window hour (`1704–1820`).
- **Tuple positions are used for results.** `res[8]` to `res[11]` are read by position (`1791–1810`). See the lesson on tuple fields in the one hundred and third pass.
- **The aux label reflects now, not the forecast hour.** `is_aux_used` is taken from `auxiliary_heating_active` (`1821–1826`) for every planned hour. The plan label shows the current state, not the state expected at that hour.
- **A missing error counts as zero error.** `calculate_uncertainty_stats` appends `abs_error_kwh` with a default of `0.0` (`1812`). A row with no error value counts as a perfect forecast and narrows the spread. The row filter drops rows where `primary_entity` is missing or different (`1810–1811`).
- **Empty uncertainty returns defaults with a count of zero.** `_calculate_uncertainty_from_errors` returns the default percentiles with `samples: 0` (`1772–1777`), so a consumer can tell the defaults from measured values.

**One hundred and eighth pass: `forecast.py` (`2081–2200`, the first half of the plan revision)**

- **Today's logs are picked by a text prefix.** `today_logs` uses `timestamp.startswith(today_iso)` (`2085`). The local date is taken from the logged text.
- **The forecast map is keyed by hour number.** `forecast_map.get(hour)` (`2100`) can match two logs to one forecast row in the repeated DST hour, the same class of problem as the earlier passes.
- **A missing solar factor reads as no sun.** `f_data.get("solar_factor", 0.0)` (`2163`) turns a missing value into zero, which is the zero-versus-missing pattern.
- **The plan always assumes normal mode.** The planned call sets `solar_impact=0.0` and `is_aux_active=False` (`2151–2162`). This is intended, and the comment says so.
- **One conversion is not guarded.** The logged DNI is converted with `float(_log_dni)` (`2190`) outside the `try` that wraps the resolver (`2198`). A non-numeric logged value would raise.

**One hundred and ninth pass: `storage.py` (`955–1080`, the 4D load and the gates)**

- **The gate normaliser repeats the migration.** The v9 critical-elevation loader rebuilds `low`/`high` gates and the legacy float form (`977–998`). It duplicates the v8 to v9 migration. See the lesson on normalisers.
- **A wrong top-level type clears the gates silently.** A non-dict `_critical_elev_per_facade_per_unit` becomes `{}` with no warning (`997–998`). `daily_history` logs a warning for the same kind of error. The two loaders are inconsistent.
- **Zero and negative thresholds are dropped.** `per_unit_min_base_thresholds` keeps only numbers above zero (`1004–1009`). A stored zero falls back to the global constant, with no log line.
- **Daily history is taken by reference.** `_daily_history` is assigned from the loaded object (`1046–1056`), so the stored dictionary and the coordinator share it.

**One hundred and tenth pass: `storage.py` (`1081–1200`, the daily and hourly restore)**

- **Daily totals are recalculated only when a sensor was removed.** The total is rebuilt from the sensors that remain (`1081–1084`).
- **Hour matching is done on UTC hour starts.** The restore compares `hour_start_utc` values (`1110`), which is the DST fix noted in the comment.
- **Collector restore is all or nothing.** A matching hour restores every field. A different hour resets the collector and marks the energy baselines stale (`1113–1140`).
- **Current wind restores to zero when a log lacks the key.** The fallback is `effective_wind` with a default of `0.0` (`1178`). A log without the key restores zero, which reads as a measurement.
- **Legacy names have two owners.** `tdd_accumulated` falls back to `hdd_accumulated` (`1200`, and `1205` for the daily stable key). The v3 migration already renames `hdd`, so the fallback is either dead code or a second owner of the same rename.

**One hundred and eleventh pass: `storage.py` (`1201–1330`, the persisted forecast, config and forecast history)**

- **A stale forecast is restored as usable.** A cached hourly forecast from an earlier date is copied into the long-term cache "better than nothing" (`1228–1242`). The code does not check how old it is when it is used.
- **A date mismatch resets the day.** When `last_save_date` differs from today, the daily values reset and the processed day is set to yesterday (`1248`). A restart after midnight depends on this branch.
- **The aux state is restored as stored.** `auxiliary_heating_active` comes back from storage (`1271`). If the heater changed while Home Assistant was down, the flag is wrong until a sensor reading updates it. Not checked.
- **The learning rate is coerced against the current value.** A bad stored value keeps the configured one (`1281`).
- **The forecast-history enrichment is quadratic and guesses.** For each history entry it walks every hourly log (`1291–1302`). A missing `forecasted_kwh` or `actual_kwh` counts as `0.0` (`1317–1318`), and an unknown source takes the entry's `source` default of `"primary"` (`1306`). Both are copied guesses.

**One hundred and twelfth pass: `diagnostics.py` (`714–840`, the dark-hour replay and the Track C redistribution)**

- **A failed re-key falls back quietly.** See the lesson on failed transforms (`721–722`).
- **Days are grouped by a text slice.** `str(timestamp)[:10]` (`725`) is the same text-date pattern as the backfill.
- **The Track C fallback is reported, not hidden.** An hour missing from the redistribution uses the raw actual value (`772–776`). The caller counts these hours in `track_c_aware_hours`.
- **A negative residual is clamped to zero.** `max(0.0, ref_kwh - excluded_kwh)` (`815`) turns a mismatch into zero, so the clamp hides it.
- **The aux test here is different.** The dark replay skips hours where `auxiliary_active` is set (`793`). The inertia calibration uses `hour_had_any_aux`. The two tests were noted in an earlier pass.
- **Rows with no temperature key are skipped silently.** A missing `temp_key` or `wind_bucket` drops the row (`797`), with no count.

**One hundred and thirteenth pass: `statistics.py` (`3662–3900`, the rest of `calibrate_inertia`)**

- **Zero variance has two meanings.** When the temperature variance is zero, `_fit_axis` returns no R² (`3706`) and the candidate is dropped. When the energy variance is zero, it returns R² of `0.0` (`3716`). The first is absent and the second is a number.
- **Each candidate has its own sample.** The tau sweep filters by `index >= window - 1` for each tau (`3744`), and the Gaussian sweep does the same (`3759`). See the lesson on common samples.
- **Ties go to the first candidate.** `max` over R² keeps the lowest tau or hour count (`3752`).
- **Weekly stability skips short weeks.** A week with fewer than twenty logs is skipped (`3781`). The stability thresholds of 1.5 and 3.0 are fixed in the code (`3812–3817`).
- **The asymmetric window drops missing temperatures before it counts hours.** `window` filters `None` out of an eight-hour slice (`3834–3835`), so the window can span more than eight hours. The asymmetric R² is compared with the symmetric R² from a different sample.
- **Not read:** the rest of the function after `3900`.

**One hundred and fourteenth pass: `hourly_processor.py` (`381–500`, the aux flag, the gap fill, the inertia key and the forecast lookup)**

- **The gap fill uses the 80% flag, not the minute state.** `_close_hour_gap` receives `is_aux_active=is_aux_dominant` (`415`), which is set only when at least 80% of the hour was aux (`398–399`). An hour that was 60% aux closes its gap as a non-aux hour. This is consistent with the learner, but a reader would not expect it from the name.
- **The temperature key uses Python's rounding.** `temp_key = str(int(round(inertia_avg)))` (`465`) rounds half to even, so 14.5 and 15.5 both become 14 and 16. The same rule is used in the diagnostics. It is consistent, so this is not a bug, but a test should pin it.
- **The solar optimiser learns from the hour average.** `learn_correction_percent` gets the hour's mean correction (`427`, `450`), and the potential factor is derived from it when the correction is at least 5% (`441–442`). Below 5%, the potential is taken from the sun position instead.
- **The energy split is by mode.** Guest units go to `guest_impact_kwh`, and off and DHW units are left out of `learning_energy_kwh` (`470–482`).
- **The forecast lookup falls back to the current time.** `target_dt` uses `start_time` or `current_time` (`496`), so a missing hour start is replaced silently. Only the reference sources are fetched here (`499–500`).

**One hundred and fifteenth pass: `learning.py` (`1911–2030`, the shadow solar learners)**

- **The shadow is seeded from the main coefficient.** `_seed_shadow_from_main_if_empty` runs before the shadow update (`1925`). The shadow therefore starts from the main coefficient and is independent only after that. The comment calls it an independent trajectory, which holds only after seeding.
- **A missing shadow buffer is replaced by a fresh one each call.** `shadow_buffer` falls back to `{}` (`1920–1924`). Production always passes the buffer, so the fallback never runs there. If a caller omits it, the buffer never fills, and nothing reports that.
- **Two call sites read the same flag with opposite polarity.** The 3D call sets `is_shadow_path=_flag_4d_primary` (`1949`), and the 4D call sets `is_shadow_path=not _flag_4d_primary` (`2025`). Both decide whether the path is shadow from one flag. Potential application: compute the role once and pass it to both.
- **The 4D learner uses the 3D outlier flag.** The 4D block runs only when `not is_outlier` (`1956`), and `is_outlier` was set by the 3D residual check. A sample the 3D path rejects is also dropped from the 4D path.
- **The 4D delta has a sign convention.** Heating adds the applied impact, and cooling subtracts it (`2008`). Saturation is applied through `calculate_saturation` (`2004–2006`), which is the same rule as 3D.
- **The 4D flag is set before the learn call.** `shadow_4d_fired = True` (`1957`) is set before the learner runs, so the flag reports that the path was attempted, not that it wrote anything.

**One hundred and sixteenth pass: `learning.py` (`2031–2150`, the shutdown inequality and the base step)**

- **The inequality branch is heating only and screen-affected only.** The regime is fixed to heating (`2049`, `2057`), and the entity must be in the screen-affected list when that list is set (`2051–2054`). The comment still reads `#xxx`, a placeholder for an issue number (`2036`).
- **The outlier check runs a second time with a different residual.** The inequality residual is `expected_unit_base - predicted_impact` (`2067`), and `_is_outlier_residual` is called again with the same state (`2069`). Whether that call updates the state was not checked. If it does, one sample updates the outlier state twice in one hour.
- **The 4D inequality is not gated on the 4D flag.** It runs when the 4D dict is not `None` and `obs` is set (`2086–2089`). The coordinator always sets the dict, so this depends on `obs` being `None` when the flag is off. See the lesson on always-open gates.
- **The battery default is a zero vector.** `battery_4d` falls back to `(0.0, 0.0, 0.0, 0.0)` (`2090–2093`). A missing value updates with zero potential rather than being skipped.
- **The screen rationale is written out.** Step 2 explains why the potential vector is used and not the effective one (`2103–2107`), with a worked example of the double-count. This is the kind of derivation that should stay in a comment.
- **The base step gets a function, not a value.** `snr_weight=_hour_snr_weight` (`2132`) passes the lazy function, so the callee decides whether the weight is needed. This is consistent with the lazy design in the one hundred and fourth pass.

**One hundred and seventeenth pass: `learning.py` (`2151–2270`, the shadow return, the seed and the head of the solar learner)**

- **The seed copies the main coefficient once and skips silently.** `_seed_shadow_from_main_if_empty` returns `False` without writing when the main entry is missing or not a dict (`2180–2181`), so the shadow stays empty and is tried again on the next call. The copy is one level deep per regime (`2183`), which is enough because the values are floats.
- **An absent dict returns early, but the caller passes `{}`.** The learner returns when either dict is `None` (`2236–2237`). The coordinator passes empty dicts, so this early return is reached only from a caller that passes `None` on purpose.
- **Off and DHW modes return before any learning.** `_solar_coeff_regime` returns `None` for them (`2239–2241`). Heating and cooling then take opposite signs (`2246–2251`).
- **The raw impact is kept next to the clamped one.** The clamp to zero is at `2254–2255`, but `raw_impact` is kept for the dead-zone test. This keeps a signal available after clamping.
- **Two magnitude gates share one threshold.** The 3D gate uses L2 and the 4D gate uses L1 (`2261–2266`). See the lesson on absolute thresholds.

**One hundred and eighteenth pass: `learning.py` (`2271–2390`, the dead zone and the cold-start buffer)**

- **A coefficient counts as learned only if one component is non-zero.** `current_coeff` is set only when `any(regime_coeff.get(k) for k in components)` (`2274–2276`). A reset to all zeros therefore reads as cold-start, so the zero-versus-missing distinction from the forty-eighth pass applies here too.
- **The dead-zone reset returns on every trigger hour.** After `SOLAR_DEAD_ZONE_THRESHOLD` hours with zero impact and a negative raw impact (`2311–2315`), the coefficient is zeroed (`2321`), the regime buffer is cleared (`2325`), and the function returns (`2333`). It returns even when the count has not yet reached the threshold, which is correct, but the return also skips the cold-start code for that hour.
- **The shadow path never resets.** The dead-zone block is skipped when `is_shadow_path` is true (`2310`). The comment gives the reason (`2289–2299`).
- **The cold-start threshold is dimension-specific.** It is `LEARNING_BUFFER_THRESHOLD` for 3D and `max(threshold, n_dim + 1)` otherwise (`2342–2345`), so 4D needs five samples.
- **An all-zero buffer is discarded silently for 4D.** The buffer is cleared and the function returns (`2365–2373`). The only log line is at debug level and only for 3D (`2367`).
- **A degenerate 3D fit keeps the buffer, which then grows.** When the LS fit fails, the buffer is not cleared (`2380–2385`), so every later hour refits a larger buffer. Nothing in this function caps it.

**One hundred and nineteenth pass: `learning.py` (`2391–2510`, the 4D cold-start fit, the generic fit and the NLMS update)**

- **A singular 4D fit stalls cold-start with no visible state.** The 4D solve keeps the buffer and returns, with no 1D fallback (`2396–2406`). The comment says this is deliberate: the buffer keeps collecting until the sun is diverse enough. In winter that can be a long time, and the only record is a debug line.
- **The cap is applied before damping.** For 4D (`2408–2412`) and for the generic fit (`2437–2440`) the solution is clipped to `SOLAR_COEFF_CAP` and then multiplied by `COLD_START_SOLAR_DAMPING`, as in the 3D path (`2539–2545`). A damped value therefore never exceeds the cap times the damping.
- **The generic fit has no fallback either.** A singular `sol` returns with the buffer kept (`2434–2435`), so the 5-plus dimension path can stall in the same way.
- **The NLMS step normalises by input power.** The step is `NLMS_STEP_SIZE × error / (input_power + NLMS_REGULARIZATION)` (`2477`), and the updated values are clipped (`2480–2483`). This is the documented reason for NLMS: the convergence rate does not depend on the solar magnitude.
- **One debug line formats eagerly.** The NLMS debug line is an f-string (`2487`), so the string is built even when debug logging is off. Every other line in the function uses `%s` formatting.

**One hundred and twentieth pass: `learning.py` (`2511–2630`, the 3D cold-start fit and the SNR weight)**

- **The 3D determinant trigger depends on the units.** `|det| > 1e-6` (`2529`) is compared with a determinant of degree six in the solar vector. The same vector in kW and in W gives a different answer for the same data. The comment says the trigger is preserved to keep the boundary unchanged, which is a reason to leave it alone, not a reason it is unit-free. See the lesson on absolute thresholds.
- **The collinear fallback projects onto the summed direction.** `dir_norm` and `sum_proj2` are both checked against `1e-6` (`2556`, `2571`). The fallback keeps one degree of freedom, and the NLMS updates refine the other two later (`2548–2551`).
- **The shim carries three attributes.** `_per_unit_hour_snr_weight` builds a `SimpleNamespace` with three fields (`2612–2616`) for a helper that expects a config object. A fourth read in that helper would raise an `AttributeError`. This was not checked.
- **Without `obs`, the SNR uses the logged 3D factor.** When the observation is `None` (the retrain replay), the 3D `solar_factor` is used (`2607–2608`). A replay therefore weights hours differently from the live path when the 4D flag is on, and the docstring says this is deliberate.

**One hundred and twenty-first pass: `hourly_processor.py` (`501–620`, the forecast items, the solar setup and the reference analysis)**

- **A missing forecast is set to the baseline.** `forecasted_kwh` and the primary and secondary values fall back to the expected energy (`530–532`). See the lesson on baseline fallbacks. The gross values have no such fallback: the lines at `525–527` call `_forecast_point_kwh` on the missing item, and what that returns was not checked.
- **There are two calls for the reference analysis.** The 4D branch passes `**overrides_4d` and omits the 3D overrides (`552–567`). The 3D branch passes the solar factor and vector (`569–578`). The `0.0` positional argument is marked as ignored in both (`562`, `572`).
- **The base falls back to the unit breakdown.** `base_expected_kwh` is read from `global_base_kwh` and falls back to `breakdown["base_kwh"]` (`582`). If the global key is missing the value is silently a different quantity.
- **The aux impact is rounded and stored.** It is rounded to three decimals (`548`) and written to `last_hour_aux_impact_kwh` (`584`), and the same rounded value is passed to the analysis (`565`, `577`).
- **Legacy callers get the heating wasted from the total.** `solar_heating_wasted` falls back to `solar_wasted_kwh` when the newer field is absent (`603–605`). The comment marks this as a log-replay compatibility path.
- **The normalisation delta is heating applied minus cooling applied.** `solar_normalization_delta` (`609–612`) follows the sign convention used in the learner (see the one hundred and fifteenth pass).

**One hundred and twenty-second pass: `hourly_processor.py` (`621–740`, the battery, the carry-over and the potential batteries)**

- **The heating gate reads the configured sensors, not the sparse dict.** `has_heating_unit` iterates `energy_sensors` and calls `get_unit_mode` (`645–648`). The comment says `_unit_modes` is empty on default installs, and `get_unit_mode` returns heating for a missing entry. The guest check later in the same function (`845–848`) reads `_unit_modes.values()`, which is correct for an "any guest" test because a missing entry is not a guest. See the lesson on sparse dicts below.
- **The carry-over pauses under the 4D flag.** The carry-over input is zero when `experimental_4d_primary` is on (`686–697`). The reason is that the 4D release is hard-coded to zero, so charging would grow the state without limit. The check is `is True`, so a truthy non-bool (for example a string from config) reads as off.
- **The potential batteries exclude the wasted feedback on purpose.** The per-direction batteries are fed raw potential only (`708–718`). The comment links this to invariant five: adding saturation feedback would weaken the constraint that the coefficients satisfy `coeff · battery ≥ 0.9 × base`.
- **Two EMAs use the same decay with different inputs.** The scalar battery uses the applied solar and the feedback (`649–658`), and the carry-over uses only the feedback (`698–701`). Both are documented as separate state on purpose.

**One hundred and twenty-third pass: `hourly_processor.py` (`741–860`, the 4D battery, the learning gate and the dual-interference guard)**

- **Two failure policies sit in one block.** The 4D battery is inside `except Exception: pass` (`794–799`). The outer block catches only `TypeError`, `ValueError` and `ZeroDivisionError` (`800–803`). A renamed solar method would therefore be swallowed in the 4D block and the 4D battery would decay with no log.
- **The house-level potential uses a sentinel entity name.** `"__house__"` (`772–774`) is passed as the entity id to the 4D potential. This is one more sentinel string, and it has one meaning here, which the comment states.
- **The deviation percentage has a floor.** The denominator is `max(expected, ENERGY_GUARD_THRESHOLD, 0.5 × (solar + wasted))` (`814–815`). The floor stops a near-zero expected value from giving a huge percentage.
- **The learning gate is three-state.** `should_learn_per_unit` is `None` unless daily-learning mode is on (`827`). `None` means that per-unit learning follows the hourly flag, `False` means off, and `True` means on. This is the sentinel with more than one meaning; here the meaning of `None` is set by a conditional and read by the guard at `839`.
- **Dual interference turns off the hourly learner and only the per-unit learner in daily mode.** The guard (`831–840`) sets `should_learn` to false, and sets per-unit to false only when it is not `None`. The comment explains that the log label `skipped_dual_interference` must not be read as "per-unit learning did not run" when it did not run in daily mode.

**One hundred and twenty-fourth pass: `hourly_processor.py` (`861–980`, the shutdown detection, the normalisation correction and the learning config)**

- **Shutdown units are corrected with the saturated solar.** For each flagged unit, the saturated applied solar is removed from the heating normalisation delta or added to the cooling one (`880–896`). The reason is given in the comment (`876–879`).
- **The expected base for a flagged unit defaults to zero.** `_hourly_expected_base_per_unit.get(_sd_eid, 0.0)` (`889`) gives zero base, so the saturated applied solar is zero and the correction does nothing. This is silent.
- **Optional features read through `getattr` with defaults.** The solar-affected set (`870–872`), the Tobit flag (`962–966`) and the Tobit entity set (`967–971`) all default to off when the attribute is absent. A wiring error reads as a disabled feature.
- **The MPC-managed exclusion is derived at config time.** `mpc_managed_entities` is built from the strategy table (`972–980`), so the live learner does not call back into strategy code. The comment cites the batch fit's `weighted_smear_excluded` skip, which keeps the two paths in step.
- **The observation is built before any learning.** `build_observation` takes about thirty values (`898–932`), and `forecast_source` is read from the `_source` key of the blended item (`925`). The learners receive the snapshot, not the live coordinator.

**One hundred and twenty-fifth pass: `daily_processor.py` (`590–737`, the Track C snapshot and the midnight sync)**

- **The snapshot slots are local date strings.** Slots are `22:00`, `23:00` before 23:55 and `23:55` after (`597–603`). The slot key is the local date plus the slot, and the coordinator keeps the last one used (`605`).
- **A failed fetch uses up the slot.** The slot is recorded before the failure is checked (`608–610`). See the lesson on marking a slot done only on success.
- **The midnight sync prefers live data and falls back to a same-day snapshot.** A snapshot is used only when its `date` equals the day being synced (`656–661`). The source tag becomes `snapshot_<HHMM>` (`661`).
- **The day filter uses the record's own offset.** Records are kept when `rec_dt.date()` in the record's offset equals the day (`693–694`). A record near midnight in another offset can fall on the wrong day. This was not tested against the MPC's timestamp format.
- **Fewer than 18 matching records falls back to Track B.** The check is at `699`, and the fallback returns `None` (`704`), which the caller reads as Option B.
- **The snapshot is cleared only when it was used.** It is set to `None` only when the source starts with `snapshot_` (`729–730`), so a successful live sync leaves a same-day snapshot in place. It becomes unusable at the day boundary anyway.

**One hundred and twenty-sixth pass: `daily_processor.py` (`738–830`, the Track C weather rows and the solar residual)**

- **A failed timestamp parse becomes an empty log entry.** `key` is `None` when the parse fails (`771–775`), and `log_by_key.get(None, {})` returns an empty dict. The outdoor temperature then falls back to the balance point (`784–788`), so `delta_t` is zero and the hour carries almost no weight. This is silent.
- **Missing wind and humidity have fixed defaults.** Missing wind is `0.0` (`790`) and missing humidity is `50.0` (`812`). The humidity default enters the per-hour COP, so a gap in logged humidity is priced as 50% RH.
- **Inertia and raw temperature are used on purpose for different terms.** `delta_t` and `is_cooling` use the inertia temperature (`816–817`). The COP uses the raw temperature (`807–811`). The comment states the reason.
- **The residual decays across gaps, but only for datetime keys.** `_solar_residuals` multiplies the battery by `decay ** missing` (`837–840`), but only when the key is a `datetime` (`837`). A string key skips the gap decay without a log line.
- **The residual is capped at one.** `min(1.0, battery)` (`844`) does not bind, since the input is at most one, but it documents the range.

**One hundred and twenty-seventh pass: `daily_processor.py` (`831–950`, the strategy and replay delegates and the Track B COP path)**

- **Track B stores its distribution after the strategies run.** `apply_strategies_to_global_model` runs first (`908–910`), and the distribution is written to `_daily_history[date_key]` after it (`913`). If the strategies raise, the distribution is not stored and a retrain cannot replay it. The order was not checked against the caller.
- **The history write assumes the day exists.** `self.coordinator._daily_history[date_key][...]` (`913`) raises `KeyError` if the day has no entry.
- **The COP flag is checked before any await.** `fetch_track_b_cop_params` returns `None` when the flag is off without awaiting anything (`931–932`).
- **A cached value is read through `getattr` with a default of `None`.** `_last_cop_params` (`935`) is read with a default, so a missing attribute reads as "not cached" and triggers a fetch.
- **A response without `eta_carnot` is ignored silently.** The fetch accepts the response only when it is a dict with the key (`946`). Otherwise `cop_params` stays `None` and the debug line is not written.
- **The cache is written only for live runs.** `cache=False` leaves `_last_cop_params` alone (`948–949`), so a retrain dry run does not change the cache. The docstring states this.
- **The learner takes the datetime parser as an argument.** `apply_strategies_to_global_model` receives `parse_datetime_fn=_dt.parse_datetime` (`864`). The learner can then be tested without a Home Assistant install.

**One hundred and twenty-eighth pass: `daily_processor.py` (`951–1070`, the Track B COP distribution and the start of `process`)**

- **The placeholders keep only the ratio.** Each row gets `q / max(1, len(slots))` for both thermal and electrical kWh (`979`, `1016–1020`). The COP is applied per hour and the result is renormalised, so the placeholder values cancel. The comment says this (`977–978`, `1013–1015`).
- **A missing timestamp is built from the local hour.** When `timestamp` is absent, the datetime is `date_key` plus the log's `hour` as text (`1003`). That string has no offset, so it may not match the instant used by the Track C join.
- **The distribution failure logs a warning and returns `None`.** The warning says it is "falling back to flat" (`1029`). The caller then uses the flat split, so the log and the outcome agree.
- **Unknown modes count as heating in the excluded-energy sum.** `compute_excluded_mode_energy` uses `MODE_HEATING` as the default (`1046`), which matches the coordinator default.
- **The warning threshold and the message disagree.** `process` warns when there are fewer than 20 logs (`1057`), but the message says "/24 hours". Days with 20 to 23 logs pass with no note. The comment calls this the Kelvin protocol.
- **The day is selected by text prefix.** `day_logs` takes entries whose `timestamp` starts with the date key (`1054`). This is the same text-date comparison as the forecast backfill in the one hundred and thirty-first pass.
- **Two names for the hourly log.** `process` reads `coordinator._hourly_log` (`1054`) and the forecast load trend reads `coordinator.model.hourly_log` (`2388`, `2390`). Whether these are the same list was not checked.
- **An empty day falls back to live state.** With no logs, the TDD and the accumulated energy are read from the coordinator's live data (`1069–1070`). Those are the current day's values, not necessarily `date_obj`'s.

**One hundred and twenty-ninth pass: `forecast.py` (`1941–2080`, the per-source uncertainty and the period statistics)**

- **The "hourly" key counts days.** The docstring says so (`1945–1949`): the errors are summed from hourly attribution but there is one history entry per day, so `samples` is a day count. The field name says hourly, and the unit is days. See the lesson on naming the unit.
- **The provenance match is strict.** A history row is used only when its entity id equals the current one (`1965–1968`, `2020–2021`). After a weather-entity change the statistics are empty until new history builds up, and the docstring calls this strict.
- **A legacy row can be counted for the wrong source.** The per-source list takes `source_breakdown[src]` when present, and otherwise `abs_error_kwh` when the row's `source` equals `src` (`1971–1975`). A row that has a breakdown without this source, but whose `source` is this source, is counted with the day's total error. This was not checked against real rows.
- **The period loop stops at the first older date.** `break` at `2016` assumes the history is in date order. If a backfill appended rows out of order, the loop would stop early, and the stop comes before the provenance filter.
- **`total_hours` is accumulated and never returned.** It is added to at `2043` and `2056` (the legacy 24-hour assumption), but the returned dict does not include it (`2068–2079`).
- **Weather error is counted only where the key exists.** `weather_error` is used only when present (`2035`), so older rows drop out of the weather bias and the weather sample count is smaller than the sample count.

**One hundred and thirtieth pass: `forecast.py` (`2201–2360`, the plan revision impact)**

- **The sign is reality minus plan.** Each hour's impact is `reality − planned` (`2231`), and positive means the house used more than the plan. The total is pro-rated for the partial hour (`2332`).
- **The partial-hour sun position is taken at the half hour.** The position is taken at `+30` minutes (`2257`), the same as the collector's mid-hour point (`761`).
- **The 4D reality path passes no overrides.** With the flag on, the live rate passes no DNI or DHI and lets the 4D path resolve them from live state (`2308–2318`). That matches the live tick path, as the comment says.
- **Missing live solar components default to scalars.** `live_solar_vector` takes `0.0` for each component (`2302–2306`), so a tuple of floats is always built even when the sensors are absent.
- **A missing forecast solar vector becomes `None`.** `f_data_curr.get("solar_vector")` defaults to `None` (`2295`). Whether the caller then computes the vector from the factor was not checked.
- **The weather driver thresholds are fixed.** `±1.5` in the mean temperature difference (`2347–2350`) sets "warmer" or "colder". The thresholds are not configurable, and the sign is logged minus forecast.
- **The 4D flag is read in three places.** It is read at `687`, `2252` and the partial-hour branch. Each read uses `is True`, and each is a separate `getattr`. None of them can change within a call, but the same flag is read from three functions with the same expression.

**One hundred and thirty-first pass: `forecast.py` (`2361–2524`, the load trend and the history backfill)**

- **The past hours are matched by hour number, not by timestamp.** `target_hours` is a set of hours of the day (`2385`), and the loop takes the first match per hour going backwards (`2390–2398`). If today's `h-1` is missing, a row from an earlier day can be used. On a fall-back day an hour number occurs twice. This was not tested.
- **A missing expected value counts as zero.** `log.get("expected_kwh", 0.0)` (`2394`) pulls the past average down, which can make a missing row read as "Increasing". This is the zero-versus-missing distinction again.
- **Two thresholds mean different things.** Below `0.1` kWh the trend uses absolute cut-offs of `0.5` and `0.1` (`2435–2438`). Above that it uses percent changes of ±5 and ±20 (`2440–2452`). Just above `0.1` kWh, a small change gives a large percentage.
- **A partial forecast is averaged as if complete.** The comment says the function uses what it has (`2424–2425`), so an end-of-day forecast with fewer hours gives an average over fewer hours without flagging it.
- **The backfill takes the date from the text prefix.** `ts.split("T")[0]` (`2464`) is the date as written, in whatever zone it was written in. This is the text-date comparison from the timestamp lesson.
- **Provenance comes from the first entry of the day.** The entities are taken from the first valid entry (`2470–2473`), so a mid-day entity change is credited to the first hour.
- **The backfill appends without a duplicate check.** Each day is appended to `_forecast_history` (`2499`) with no test for an existing date. Calling it twice, or on a non-empty history, duplicates days. The callers were not read. `reset_forecast_history` (`2515–2523`) clears the list first, which suggests the intended order.
- **Caches are cleared after the backfill.** `_cached_forecast_uncertainty` and `_cached_week_horizon_stats` are reset (`2511–2512`), so the next read recomputes from the new history.

**One hundred and thirty-second pass: `learning.py` (`2631–2748`, the base-or-aux routing)**

- **An aux hour skip returns before any learning.** With `learn_aux=False`, an aux-affected unit in an aux hour returns `aux_not_learned` (`2685–2686`). The hour does not go to the base bucket either, and the docstring says this is deliberate (`2661–2665`).
- **Aux-excluded units skip the headroom and SNR weights.** On the aux branch, an unaffected unit goes to `_learn_unit_model` with no `rate_multiplier` (`2698–2704`). The normal base path composes headroom and SNR (`2723–2745`). The same bucket therefore gets a different step size depending on whether aux is on. The comment (`2696–2697`) justifies the lock on the global model, not the weights.
- **The SNR weight is a callable, called once.** `snr_weight()` runs only on the normal base path (`2731`), as the docstring says (`2661`).
- **A zero base disables the headroom discount.** When `expected_unit_base` is zero, the headroom multiplier is `1` (`2729–2730`), so solar is not discounted where there is no base to compare against. This is a choice, not a fault.
- **The two multipliers multiply.** `rate_multiplier = headroom × snr` (`2731`). A zero in either stops the update, as the comment says (`2716–2722`).

**One hundred and thirty-third pass: `learning.py` (`2749–2870`, the unit model and the aux coefficient)**

- **The cold-start jump start ignores both weights.** The buffer average is written with no headroom or SNR weight (`2792–2801`). Throttling applies only after the jump, so an early high-solar sample enters at full weight.
- **Buffers clear at the jump.** Each buffer is cleared when it reaches its threshold (`2801`). This differs from the 3D solar buffer, which keeps growing when its fit fails (pass 118). The two cold-start paths handle a stuck buffer in different ways.
- **The EMA cap comes before the multiplier.** The rate is `min(rate, 3%) × rate_multiplier` (`2815`). The cap bounds the rate, and the multiplier only lowers it.
- **The aux learner has no solar weighting.** `_learn_unit_aux_coefficient` uses `min(rate, cap)` (`2895`) with no headroom or SNR input. Whether solar is kept out of aux hours upstream (the dual-interference guard, pass 123) was not checked here.
- **The aux reduction is bounded twice.** It is clamped to zero below and to the base bucket above (`2855`, `2860`). On the EMA path the new coefficient is clamped again (`2897–2898`), so a reduction cannot exceed base consumption.

**One hundred and thirty-fourth pass: `learning.py` (`2871–2990`, the aux cold start and the solar coefficient write)**

- **Aux is stored to 3 decimals; the base to 5.** `_update_unit_aux_coefficient` rounds to three places (`2919`), and `_update_unit_correlation` rounds to five (`2910`). With the rate at most 3%, an error below about 0.017 kW gives a step under 0.0005 kW, which rounds away, so the stored aux coefficient does not move. This follows from the arithmetic and was not run.
- **The solar write replaces the whole regime.** `entry[regime] = new_regime` (`2982`) rebuilds the regime from `components` only, and a missing component is written as zero (`2978`). A partial write clears the components it does not name.
- **Every component is clamped at zero.** `max(0.0, …)` (`2978–2980`) enforces invariant four: a window can only receive gain.
- **A `learned` flag marks learner writes.** `new_regime["learned"] = True` (`2981`) lets the cooling cold-start gate tell learned values from copies of the heating coefficient. Legacy data reads as unlearned and corrects itself on the next write (`2954–2961`).
- **An invalid regime raises.** A bad regime raises `ValueError` (`2963–2964`). The caller checks the regime first (`_solar_coeff_regime`, pass 117), so the raise is a backstop.

**One hundred and thirty-fifth pass: `learning.py` (`2991–3110`, the inequality update)**

- **Three magnitude gates use two norms.** The 3D solar gate uses L2 (`2262`), the 4D gate uses L1 (`2264`), and the inequality gate uses L1 for both dimensions (`3062–3063`). The `0.01` threshold means something slightly different in each. See the lesson on absolute thresholds.
- **The status is a string the caller compares.** The function returns `"updated"`, `"non_binding"`, `"zero_magnitude"` or `"shadow_disabled"` (`3052–3056`). A typo in a caller's comparison would fail without an error. Potential application: return a named constant or an enum.
- **Heating only, and one-sided.** Only the heating regime is read and written (`3072–3077`, `3106`), and the update only raises (`3085–3086`, `3100`). This matches invariant five.
- **The deficit is spread by the hour's potential share.** Each direction gets `step × deficit × potential_k / Σ potential` (`3096–3098`). A direction with no potential this hour gets no update, as the comment says (`3088–3092`).
- **The half-life in the docstring checks out.** A decay of 0.80 gives a half-life of about 3.1 hours (`3010–3013`), since ln 0.5 / ln 0.8 ≈ 3.1.

**One hundred and thirty-sixth pass: `hourly_processor.py` (`981–1100`, the learning call and the per-unit logs)**

- **TDD is an absolute difference.** `abs(balance_point − avg_temp) / 24` (`1007`) counts cooling hours as degree-days, as the comment says (`1006`). The same TDD is the denominator of the U-coefficient (`daily_processor.py:1207`), so cooling-season hours enter the U value. This is a design choice worth recording.
- **The comment names a helper the code does not call.** The comment says `units_reporting` is read through `helpers.unit_hour_reported_kwh` (`1019–1021`), but the line uses `sorted(self.coordinator._hourly_delta_per_unit)` (`1022`). The helper may exist and be unused, or the comment may be stale. Not checked.
- **Zero-kWh units are dropped from the breakdowns.** `unit_breakdown` and `unit_expected_breakdown` keep only `kwh > 0` (`1015`, `1029`). The comment explains that `units_reporting` exists to tell a zero hour from an offline sensor (`1017–1021`). The log therefore needs two fields for one fact.
- **Mixed mode and dual interference relabel the status.** The status becomes `skipped_mixed_mode` or `skipped_dual_interference` unless it is `cooldown_post_aux` (`1050–1056`). The label says why the hour was skipped, not what the learner returned.
- **The solar share ratio has a fallback.** When no solar was applied but the battery holds a residual, the sign comes from the active unit modes (`1084–1098`). Mixed or all-off hours drop the adjustment (`1098`). The mode check reads `energy_sensors`, as in pass 122.

**One hundred and thirty-seventh pass: `hourly_processor.py` (`1101–1220`, the hourly log entry)**

- **Derived labels use the learner's inputs.** `dni_dhi_source` is derived from the averages the 4D learner uses (`1111–1119`), so the logged label cannot disagree with the branch taken. The comment says so (`1111–1113`).
- **Missing averages pass as None.** The `getattr(obs, …, None)` reads (`1115–1118`) pass `None` on when an attribute is absent. Whether the label then reads as "none" was not checked.
- **Optional keys are omitted, not zeroed.** The DNI, DHI, cloud, GHI and solar-data keys appear only when their counts are above zero (`1169–1197`). A reader must use `.get`, and cannot tell "no data" from an older schema without the version field.
- **The schema version is the migration key.** `solar_pipeline_schema_version: 1` (`1150`) lets a replay tell which fields to expect. This is the pattern to copy for any log whose schema grows.
- **Base fields are indexed, aux fields are read with get.** `learning_result["model_base_before"]` (`1201`) raises if the key is absent, while the aux fields use `.get` (`1204–1206`). The keys the log needs from the learner are not listed in one place.
- **The local hour sits beside the UTC instant.** `hour` is the start hour as a local number (`1123`), and `timestamp` is the ISO start. The load trend matches on the hour number (pass 131), so the two can disagree on a fall-back day.

**One hundred and thirty-eighth pass: `daily_processor.py` (`1071–1190`, the empty-day fallback and the Track C branch)**

- **The empty-day average inverts TDD.** `avg_temp = balance_point − tdd` (`1071`) inverts a quantity that is an absolute difference (pass 136). On a day with cooling hours, the reconstructed mean is lower than the real one. The comment says "Approx".
- **Empty days store zeros as values.** `expected_kwh`, `forecasted_kwh`, `aux_impact_kwh`, `solar_impact_kwh`, `guest_impact_kwh` and `deviation` are `0.0` (`1092–1099`) and are written to the history (`1103`). A zero modelled value looks like a model that predicted no energy. The hourly vectors in the same dict use `None` (`1074–1080`), which is the right choice.
- **The solar delta prefers the 4D key.** `solar_normalization_delta_4d` is read first, per hour (`1124–1127`). The key is set whenever the shadow path fired (`learning.py:2151–2154`), which does not mean the 4D path was live. Whether a shadow value reaches the live normalisation was not checked.
- **Track C stores a 24-row distribution per day.** `track_c_distribution` goes into the daily history (`1168`). The storage cost was not measured.
- **Each day gets an explicit track tag.** `track_used` is set to `C_live` or `C_<slot>` (`1176–1178`). The diagnostics should read this tag, but pass 145 re-infers it from fields.
- **An MPC outage stops both learners and counts it.** The outage path logs a warning, increments the session counter and sets the skip flag (`1181–1190`). The same flag blocks the U-coefficient update (`1203`).

**One hundred and thirty-ninth pass: `daily_processor.py` (`1191–1310`, the U-coefficient, the Track B paths and the CSV log)**

- **There are three thresholds for a complete day.** The processor warns below 20 logs (pass 128, `1057`), the U-coefficient needs 22 (`1205`), and the message says "/24" (`1256`). A day with 20 or 21 logs passes the warning and fails the learning gate with no message.
- **The first U-coefficient is accepted whole.** When none exists, `observed_u` becomes the coefficient (`1208–1209`). Later days use the learning rate (`1211`). One day therefore sets the value with no damping, while the per-unit learners wait for a buffer. The cold-start policy differs between learners.
- **A zero bucket is treated as missing again.** The flat Track B path cold-starts when `current_pred == 0.0` (`1240–1243`). A bucket that learned exactly zero is overwritten, not averaged. This is the zero-versus-missing lesson.
- **The flat path uses two rates.** A cold start writes the value directly (`1243`). The EMA uses `learning_rate` (`1246`), not the daily rate used for U (`1211`). Which rate a bucket gets depends on whether it was empty.
- **The CSV columns are indexed by sensor order.** `device_{i}` is built with `enumerate(self.coordinator.energy_sensors)` (`1297–1298`). Reordering the sensors changes what each column means, and old rows keep the old meaning.
- **The tag is written two ways.** `"B_cop"` is assigned (`1227`), while `"B_flat"` uses `setdefault` (`1254`). The two behave differently if a tag was already set.
- **The thermal-mass correction is midnight to midnight.** The indoor delta uses the previous midnight reading (`1192–1196`). The correction runs only when the sensor and the coefficient are both present.

**One hundred and fortieth pass: `forecast.py` (`2645–2764`, the rest of `log_accuracy` and the week-plan capture)**

- **Two definitions of dominant source.** `log_accuracy` takes the dominant source from the midnight snapshot (`2662`). The backfill counts hours (`2492–2494`). A mixed day gets a different label from each path.
- **Missing means None here.** `day_mae` and `night_mae` are `None` when the count is zero (`2664–2665`). This is the right pattern, and it differs from the zeros in the empty-day fallback (pass 138).
- **History is capped by a literal.** `if len(self._forecast_history) > 365: pop(0)` (`2687–2688`). The retention is not a named constant, and the pop removes from the front of the list.
- **Week-plan capture fails quietly during shutdown.** The error is logged only when `hass.is_running` (`2708–2709`). A failure while HA is stopping leaves no trace.
- **The first plan of the day wins.** `_store_week_plan` returns if a plan with the same `made_on` exists (`2727–2728`). A later capture the same day, after a restart or a better forecast, is dropped.
- **A missing day kWh becomes a zero plan value.** `d.get("kwh", 0.0)` (`2736`) stores zero for a day with no kWh. The length check (`2731`) does not catch it, and the week error in pass 141 would count it as a large miss.
- **The plan stores only the primary entity.** `primary_entity` is saved (`2737`), and the scorer filters on it (`2789`). The secondary source is not recorded in the plan.

**One hundred and forty-first pass: `forecast.py` (`2765–2884`, the week-horizon scorer and the week-ahead start)**

- **The cache is keyed on the day, and capture cannot change today's result.** Plans are scored only when `made_on` is at most seven days before today (`2774`, `2787`). A plan captured today cannot affect today's cached value, so the date-only cache is safe for capture.
- **Only complete windows are scored.** A plan counts only when all seven actual days are present (`2800–2809`). A missing day drops the whole window, as the docstring says (`2758–2761`). This is the Kelvin rule applied to a sum.
- **Planned values are not checked for missing.** Only the list length is checked (`2792`). A zero planned day (pass 140) gives a large error that is counted.
- **Sentinels stand in for min and max.** `min_temp = 999.0`, `max_temp = -999.0` (`2862–2863`), `min_kwh = 99999.0`, and `max_kwh = -1.0` (`2867–2868`). These are correct only if at least one day has data. Whether the output shows them when no day has data was not checked, since the end of the function is outside this batch.
- **A placeholder summary string.** `ATTR_WEEKLY_SUMMARY` starts as "Generating forecast..." (`2846`). If the function returns early, the sensor shows that text.
- **The 53-week mapping uses min and max.** The last-year range is the minimum and maximum of the mapped dates (`2876–2884`), which covers the year-boundary case the comment describes.

**One hundred and forty-second pass: `storage.py` (`1331–1431`, the week-plan key, the snapshot restore and the load error)**

- **The week-plan key is additive.** A missing `week_plan_history` defaults to an empty list (`1350–1353`), and no storage version change is needed. The comment says a migration would seed the same value. This is the pattern for an optional new field.
- **The snapshot restore is strict on one key and lenient on the rest.** `snap["kwh"]` is indexed (`1361`), and the other fields use `.get` (`1362–1363`). A snapshot without `kwh` raises into the outer handler.
- **The error message describes a state the code does not produce.** The outer handler says Heating Analytics will start with a fresh state (`1419`), but the handler resets nothing (`1411–1424`), so any section restored before the failure stays. Whether earlier code resets on failure was not checked.
- **Empty references are skipped.** Each reference restore is guarded by a truthiness test (`1368`, `1375`, `1380`, `1385`). An empty saved value leaves whatever was in memory.
- **A bad timestamp is swallowed.** A bad `last_live_update` is ignored (`1396–1397`), and the field keeps its previous value.
- **Backfill runs only when the key is missing.** The condition (`1402`) skips the backfill when the history was saved as empty. This is the reset-state rule in the comment (`1399–1401`).
- **The finally block always marks the load complete.** `_is_loaded = True` (`1426`) runs even after a failure, so the rest of the integration treats a failed load as loaded.

**One hundred and forty-third pass: `statistics.py` (`3901–4020`, the ΔT-scaling bins and the extended tau sweep)**

- **The ΔT bins use the raw outdoor temperature.** `bp − raw_temps[index]` (`3913`) bins by the raw reading, while the model learns on the inertia temperature. The bins describe the raw axis, not the axis the model uses. This is a diagnostic choice and should be labelled as one.
- **Each bin needs ten points.** Bins below ten are reported as "Too few points" (`3926–3931`). The threshold is a literal.
- **Each tau sees a different sample.** The eligible list is `index ≥ window − 1` (`3941`, `3968`). A longer kernel leaves fewer logs, so the tau values are not compared on the same hours. This is the issue noted in pass 113, and it affects the extended sweep too.
- **The axis comparison holds the sample fixed.** `_compare_live_inertia_axes` fits both axes on the same `eligible` list (`4007`, `4019–4020`). This is the right pattern, and the sweep should copy it.
- **The R² sentinel is −1.** `bin_best_r2 = -1.0` (`3935`) is safe only because R² is not expected below −1. It is a sentinel with an assumed range.
- **The best extended tau uses max with a default.** `max(..., default=None)` (`3975`) returns `None` when every tau is skipped, so the output does not show a stale value.

**One hundred and forty-fourth pass: `statistics.py` (`4021–4140`, the live-axis comparison and the wind calibration start)**

- **Changed-bucket share uses banker's rounding.** `int(round(a)) != int(round(b))` (`4038`) rounds half to even, the same rule as the temperature key (pass 114). It is consistent, and worth a test.
- **Bands use the raw temperature.** `_bands` groups by `log["temp"]` (`4043–4045`), the raw reading, while the fit uses the inertia axis. The labels say outdoor temperature, which is correct, but the grouping differs from the fit.
- **Wind calibration uses a stricter aux test than the gap fill.** `hour_had_any_aux(log)` (`4115`) rejects any partial-aux hour, because the 80% flag would admit those (`4113–4114`). The gap fill uses the 80% flag (pass 114). Both are deliberate and documented.
- **The solar exclusion is an absolute energy cut.** `solar_impact > 0.1` (`4109`) is a fixed kWh threshold, not a share of consumption. A large house and a small one get the same rule.
- **The time filter compares text.** `log["timestamp"] >= start_iso` (`4097`) compares ISO strings, which is the text-versus-instant comparison from earlier passes.
- **Two return shapes.** When no pure hours remain, the function returns an `error` key with counts (`4136–4140`). The success path returns the calibration keys. Callers must check for `error` first.

**One hundred and forty-fifth pass: `diagnostics.py` (`841–960`, the base-model verdicts, the flag sort and the Track B report)**

- **Infinite deviations sort to the bottom.** Stored energy against a near-zero dark mean gives `delta_pct = inf`, which is flagged `inflated` with `delta_pct: None` (`854–862`). The sort key is `abs(x.get("delta_pct") or 0.0)` (`883`), so those entries become zero and sink. The comment says the worst offenders surface first (`879–880`). For exactly these entries the code does the opposite. This is a bug on the path the comment describes.
- **Track attribution is re-inferred from fields.** The Track B report picks `C`, `B_cop_smeared`, `B_flat` or `A` from which keys are present (`919–925`). The learner writes an explicit `track_used` for this purpose (`learning.py` notes at `1172–1175`, and `daily_processor.py:1260–1262`), and this report does not read it.
- **Zero stands in for missing temperature and degree-days.** `temp_avg` defaults to `0.0` (`912`) and `tdd` to `0.0` (`915`). A day with no temperature shows as 0 °C.
- **A learned zero reads as missing in the config echo.** `learned_u_coefficient` shows as `None` when the value is `0.0` (`943`), because the test is truthiness.
- **The balance point is kept per day.** `tdd_balance_point` (`916`) keeps the balance point the day was learned at, which matters after a balance-point change.
- **Only the last 30 days are listed.** `track_b_days[-30:]` (`932`) truncates the list, and the report gives the total count (`931`).
- **The verdict's thresholds are echoed.** The summary thresholds are included in the report (`889–891`), so a reader can see what the verdict was measured against.

**One hundred and forty-sixth pass: `diagnostics.py` (`961–1080`, the summary verdict and the start of `diagnose_solar`)**

- **The verdict ignores mode contamination on purpose.** The summary says so (`956–958`). `model_unverifiable` wins when more than half the buckets are unverifiable (`999–1000`), then `issues_found`, then `ok`.
- **The solar correlation band is absolute.** `abs(solar_corr) > 0.15` (`1005`) is the only correlation test. A moderate correlation inside the band counts as ok.
- **The noise floor applies only to the verdict count.** Inversions are counted with and without the 0.05 kWh floor (`962`, `974–975`). The verdict uses the above-floor count (`1002`), and the total is still reported (`1018–1019`).
- **The bucket total is computed two ways.** `total_buckets` (`978–988`) counts `ok` entries directly, while `ok_count` is derived by subtraction (`989–993`). The two agree only while every entry has a verdict.
- **The last batch fit uses `or {}`.** `regimes` is `entry.get("regimes") or {}` (`1065`), so a missing block and an empty one look the same. The `skip_reason` key is the only way to tell a skip from a unit that never ran, and it is kept only when present (`1067–1068`).
- **`diagnose_solar` imports inside the method.** It imports `timedelta` and `date` locally (`1080`). This avoids a module-level cost, but it hides the dependency from a reader scanning the top of the file.

**One hundred and forty-seventh pass (`number.py`, the one extra file, read in full)**

- **Sibling settings use different units.** The learning rate is shown as a percent and stored as a fraction (`value / 100.0`, line 75). The solar correction is stored as a percent (line 102). Each is internally consistent, but a reader moving between them has to know which is which.
- **Only the solar correction refreshes the recommendation.** Its setter calls `async_request_refresh` (line 106), with a comment saying why. The learning-rate setter does not, which may be intentional.
- **Both setters save before writing state.** `_async_save_data` runs before `async_write_ha_state` (lines 76–77, 103–104). A failed save would leave the entity showing the new value while storage keeps the old one. Whether the save raises was not checked.
- **Range limits are declared, not enforced here.** The minimum, maximum and step are class attributes (lines 62–64, 89–91). Whether Home Assistant rejects an out-of-range value before the setter runs was not checked.

**One hundred and forty-eighth pass: `learning.py` (`3111–3230`, the 4D solver and the historical base update)**

- **A singular fit writes nothing.** The 4×4 solver returns `None` for fewer than four rows or a pivot below `1e-10` (`3130–3146`), so the caller falls through without a coefficient.
- **Zero is read as unlearned for the aux coefficient.** The update blends only when `current_coeff != 0.0` and otherwise takes the implied value (`3223`). A coefficient that is truly zero is reseeded at the next sample's full value, not blended. The same test is used for the base bucket (`3240`, `3256`). Potential application: keep a separate learned flag.
- **The aux coefficient is rounded to three decimals** (`3224`), as at the `2919` pass. Small steps are lost on this path too.
- **The docstring has the `#xxx` placeholder again** (`3179`), as at `2036`.

**One hundred and forty-ninth pass: `learning.py` (`3231–3350`, the base update for historical imports and the strategy weights)**

- **A zero-rate update reports an update.** When `effective_rate` is zero and the bucket is already set, the EMA step runs with a zero rate and the function returns `updated_base_model` (`3230`, `3248–3258`). Nothing changed, but the caller counts an update. This was not run; the arithmetic follows from the step.
- **An empty lift set reads as closed.** `lift_gate_open` is an `any(...)` over the regimes present (`3197–3205`), so no regime means no lift. That is the safe default, and it is undocumented.
- **Missing wind and solar read as calm.** `effective_wind` and `solar_factor` fall back to `0.0` (`3327`, `3335`) with no log line. A missing measurement gets the neutral weight.
- **The fallback weight is uniform.** When every raw weight is zero, `1/len(slots)` is used (`3346`), so an all-zero day spreads its energy evenly.

**One hundred and fiftieth pass: `learning.py` (`3351–3470`, the per-day strategy smear into the global model)**

- **A zero-kWh hour is not learned.** `if total_kwh <= 0.0: continue` (`3438–3439`) drops the hour, so a true zero-demand hour leaves the bucket untouched. It is the same zero-as-missing choice as the other passes; the drop is not counted.
- **The solar delta is applied only when a direct meter contributed** (`3433`). The comment explains why (`3420–3423`): a nonzero delta against zero direct kWh would leak into smear-only buckets. This is a good example of a guard that has a stated reason.
- **Mode filtering uses the heating default** (`3358`), so a sparse `unit_modes` map is read correctly.

**One hundred and fifty-first pass: `learning.py` (`3471–3590`, the per-unit replay contract)**

- **The function returns three shapes.** The target-not-replayed branch returns a dict with three keys (`3558–3562`), the `None` branch returns `None` (`3563–3564`), and the normal branch returns the counters plus, for a target, the diff (`3775–3803`). A caller that reads `units_learned_base` after the first branch gets a missing-key error. Potential application: return the same keys with zeros.
- **Dry-run copies everything before the reset** (`3578–3588`). The reset is applied to the copies, so the reported diff matches a real reset-then-replay. The docstring says this (`3533–3537`).
- **The legacy anchor depends on the caller.** `first_reported` falls back to `model.hourly_log` or the replayed entries (`3590–3593`). The same question about what the anchor means is answered differently by each caller.

**One hundred and fifty-second pass: `learning.py` (`3591–3710`, the expected base and the lazy SNR weight)**

- **A missing expected base is zero.** `_expected_unit_base` returns `0.0` when the bucket is absent (`3601`). Zero is then the base for the learner, which can skip or write from a zero base depending on the gate.
- **The SNR weight is computed once, lazily.** The closure caches a one-element list (`3683–3705`) and reads the expected base before the hour's first unit is learned. The docstring describes this order (`3686–3688`).
- **The legacy counter counts only units that a log entry omits when the breakdown exists** (`3674–3677`), which keeps the counter honest about what it measures.

**One hundred and fifty-third pass: `learning.py` (`3711–3830`, the unit route and the diff summary)**

- **Solar impact is zero when solar is disabled** (`3726–3727`). The stored impact in the log is not used, so the replay does not reproduce a value the live path would have written when solar was on.
- **The diff summary is capped and the count is not.** `diff_summary` holds the top 200 changes (`3794–3798`), and `buckets_changed` holds the full count (`3802`). Both are reported, so the cap is visible. This is the right pattern.
- **The catch-all route is covered in the lessons above** (`3772–3773`).

**One hundred and fifty-fourth pass: `learning.py` (`3831–3950`, the potential reconstruction and the on-the-fly solar delta)**

- **Three magnitude gates for one idea.** The on-the-fly delta returns zero at `magnitude <= 0.01` (`3875`), the NLMS replay skips at `<= 0.1` (`4049`), and the batch fit drops at `<= 0.01` (`4943`). Which hours a fit sees depends on the function that reads them. Potential application: one named constant.
- **The docstring records the bug and its fix.** The on-the-fly delta used to iterate the sparse `unit_modes` map and returned zero on most hours. The docstring names the bug and says the fix iterates `energy_sensors` (`3858–3870`). Keep this practice.
- **The missing-`None` default is covered in the lessons above** (`3825–3828`).

**One hundred and fifty-fifth pass: `learning.py` (`3951–4070`, the replay state and the skip order)**

- **The battery updates before any skip** (`4015–4026`), so aux and poisoned hours decay the battery as the live coordinator does. The comment gives the reason: a stale battery would inflate the next shutdown update. This is the right ordering for a stateful replay.
- **The battery decay is fixed at the default.** The replay does not use the user's calibrated decay (`3994–3999`). The docstring says so. A user who tuned it gets a retrain that disagrees with live.
- **A missing temperature reads as `0.0`.** `avg_temp = entry.get("temp", 0.0) or 0.0` (`4076`) is passed to the coefficient learner (`4252`). What it drives was not checked.
- **A missing wind label becomes `normal`** (`4073`) with no count. The re-bucketing above it uses the threshold when it can.
- **A counter kept at zero is a tripwire.** `unit_skipped_aux_list` is retained and always zero, so a return of the old bug would show (`4096–4099`). The comment gives the reason.

**One hundred and fifty-sixth pass: `learning.py` (`4071–4190`, the inequality branch of the replay)**

- **The docstring's counting rule is not met.** The docstring says a single hour is counted in at most one bucket per unit (`3967–3968`). The shutdown branch increments `inequality_skipped_mode` and `unit_skipped_shutdown` together (`4122–4123`, `4134–4135`), and the base branch does the same (`4159–4160`). Summed counters double-count these hours.
- **Two mode gates in one function.** The inequality branch requires `MODE_HEATING` (`4121`). The NLMS branch uses `MODES_EXCLUDED_FROM_GLOBAL_LEARNING` (`4177`). Whether those two rules agree was not checked.
- **The status mapping is a catch-all** (`4172–4173`), covered in the lessons above.

**One hundred and fifty-seventh pass: `learning.py` (`4191–4310`, the NLMS step and the screen routing)**

- **The MPC exclusion is documented at length** (`4182–4203`). It gives the reason for skipping WeightedSmear units: no coherent dark baseline. Keep this rationale in the code.
- **The batch fit uses a different mode rule from the NLMS path.** The batch fit accepts only heating and cooling (`4858`, `4879–4882`) and its docstring says guest modes are excluded (`4837–4839`). The NLMS path uses `MODES_EXCLUDED_FROM_GLOBAL_LEARNING` (`4177`). Whether that constant holds the guest modes was not checked.
- **A missing base becomes a skip through the threshold** (`4221–4227`). This works only while the resolved threshold is above zero, which was not checked.
- **Screen routing is explained.** An unscreened entity learns against the effective vector, because transmittance `1.0` reduces to the effective value (`4228–4231`).

**One hundred and fifty-eighth pass: `learning.py` (`4311–4430`, the batch Tobit fit entry point)**

- **A missing scope set fails open.** `solar_affected` is `None` when the coordinator's set is absent or not a set (`4380–4382`), and then every entity is included (`4391`). A user who excluded entities would have them fitted after a bad restore.
- **A missing strategies map fails open.** `getattr(coordinator, "_unit_strategies", {})` (`4360`) means a missing attribute removes the MPC exclusion (`4399–4404`). Both are covered in the lessons above.
- **The unknown-entity case has a named reason** (`4385–4388`), so the caller can see why an entity was skipped.
- **The potential reconstruction is hoisted** per entity (`4410–4427`). The docstring gives the saving (`4411–4414`).

**One hundred and fifty-ninth pass: `learning.py` (`4431–4550`, the regime fit, the gates and the damping)**

- **A zero prior is treated as no prior.** The damping test is `any(current[k] > 1e-6)` (`4547`). A regime that learned exactly zero in all three directions is written undamped on the next fit. This is the zero-as-missing pattern.
- **The post-fit order decides the reason.** `insufficient_effective_samples` is checked before `did_not_converge` (`4518`, `4526`), so a fit that did not converge and had few effective samples reports the first reason only. The order is not documented.
- **The censored fraction is computed twice** with the same rule (`4475–4479`, `4503–4505`). Harmless, but a single helper would keep them in step.

**One hundred and sixtieth pass: `learning.py` (`4551–4670`, the damped blend, the residual and the live-window seed)**

- **The residual uses uncensored rows only, against the clamped undamped fit** (`4562–4573`). The comment explains why censored rows would give a spurious residual. The choice is documented where it is made.
- **A silent branch is made loud.** When the live stats are not a dict, the seed records `seeded_live_window: False` and `seed_skip_reason: stats_not_dict` (`4661–4662`), so a diagnose snapshot shows the skip. This is the right fix for a silent fallback.
- **Dry-run returns before the seed** (`4577–4585`), so `applied` is `False` and the live window is untouched.
- **A fallback that cannot run.** `fit.get("n_eff", float(n_unc))` (`4644`) follows a direct `fit["n_eff"]` read (`4506`), so the default is unreachable.

**One hundred and sixty-first pass: `learning.py` (`4671–4790`, the shutdown re-check for old log entries)**

- **The docstring and the code disagree on legacy entries.** The docstring says a missing `unit_expected_breakdown` falls back to `unit_min_base × 2` with a ratio floor (`4696–4702`). The code returns the persisted `solar_dominant_entities` flag (`4733–4740`), which the docstring itself says may be buggy (`4684–4686`). Legacy entries therefore keep the old classification. The code comment (`4734–4739`) gives the reason; the docstring needs to match it.
- **The parasitic floor fires before the base check** (`4744–4745`). This is intended, and the comment says so.
- **A dead branch.** `ratio = actual / base if base > 0 else 1.0` (`4749`) follows a return for `base <= 0` (`4742–4743`), so the else is unreachable.

**One hundred and sixty-second pass: `learning.py` (`4791–4910`, the batch-fit sample filter)**

- **Shutdown rows are kept, not dropped.** The docstrings say they are excluded (`4316–4317`, `4780–4781`, `4795–4799`). The code keeps them as censored candidates and counts them under `shutdown_kept_censored` (`4904–4927`). The code comment (`4905–4917`) explains the change. The docstrings predate it, and this is the most important stale claim in the batch.
- **The unit threshold is still used.** The docstring says the parameter is no longer consulted on any live path (`4789–4792`). The MAD sigma floor reads it when `use_mad` is set (`5048–5053`), so the docstring is wrong.
- **An absent key means zero, and a present zero is not shown.** `shutdown_kept_censored` is created only when first seen (`4925–4927`), so the report omits it when no shutdown hour occurred. The other counters are seeded at zero.
- **Not reporting is dropped before the shutdown check** (`4896–4902`), so a silent sensor is not counted as a censored zero.

**One hundred and sixty-third pass: `learning.py` (`4911–5030`, the censoring rule and the outlier candidates)**

- **The comment models a zero reading that the code does not use.** The comment says `actual = 0` gives `actual_impact = base` and so a saturated row (`4905–4909`). The code uses the reported kWh (`4899`). For a partial shutdown hour, `base − actual` may fall below `BATCH_FIT_SATURATION_RATIO × base` and enter as an uncensored sample. Whether that happens depends on `SOLAR_SHUTDOWN_RATIO` and `BATCH_FIT_SATURATION_RATIO`, which were not compared.
- **Censoring applies to heating only.** `is_saturated` requires `regime == "heating"` (`4998–4999`). The docstring describes saturated rows in general (`4325–4327`). Whether cooling should be censored was not checked.
- **Candidates are gated before the residual** (`4936–4994`), so the residual is computed only for rows that passed the mode, learning, base and impact gates.

**One hundred and sixty-fourth pass: `learning.py` (`5031–5150`, the MAD filter and the 3×3 solver)**

- **The sigma floor is 25 Wh at the default base.** With `min_base_val = 0.5`, `max(0.02, 0.05 × 0.5)` is `0.025` (`5055`). The comment says the default keeps the MAD filter latently off (`5043–5047`). A floor of 25 Wh is not off for large residuals, so the comment holds only while residuals are small. Not checked.
- **The dict branch is unreachable here.** `unit_threshold` arrives as a float from `_resolve_min_base` (`4406–4408`), so the `isinstance(unit_threshold, dict)` branch (`5050–5051`) does not run on this path.
- **The singularity test has units.** `abs(determinant) > 1e-6` (`5130`) is an absolute threshold on the 3×3 Gram determinant. That determinant is cubic in the Gram entries, which are quadratic in the potentials, so it scales with the sixth power of the potential magnitude. The same `1e-6` therefore means a different thing at a different unit. This is the absolute-threshold lesson again.
- **The fallback is a projection onto the summed direction** (`5142–5150`), which keeps a collinear set from failing outright.

**One hundred and sixty-fifth pass: `learning.py` (`5151–5270`, the batch-fit collinear fallback, the residual RMSE and the Mills ratio)**

- **The collinear fallback uses an absolute threshold.** `sum_proj2 < 1e-6` returns `None` (`5159–5160`). This is a third absolute gate in the batch fit, after `5130` (pass 164). The threshold scales with the square of the potential, so its meaning changes with the potential's units.
- **An empty residual reads as a perfect fit.** `_batch_fit_residual_rmse` returns `0.0` for no samples (`5170–5171`). A caller that compares RMSE values cannot tell an empty set from a good fit. This is the zero-versus-missing pattern.
- **One branch of the Mills ratio is unreachable.** The `surv < 1e-300` test (`5203–5205`) comes after the cut at `q > 8` (`5194–5198`). Below that cut the survival is about 6×10⁻¹⁶, far above 1e-300, so the test never fires.
- **The Mills docstring matches the code.** It names the `erfc` form, the asymptotic expansion, and the cut at 8 (`5184–5192`). This is the clearest derivation in the file so far.

**One hundred and sixty-sixth pass: `learning.py` (`5271–5390`, the Tobit solver's inputs, dispatch and warm start)**

- **The identifiability comment names the wrong quantity.** The guard `n_unc < n_dim` (`5283–5288`) says σ needs `n_dim` uncensored rows. The count is needed for the least-squares direction, not for σ.
- **The 3D and 4D warm starts fail differently.** 3D has a collinear fallback (`5303–5312`). 4D returns `None` on a singular Gram matrix (`5313–5318`). The generic branch uses `pivot_eps=1e-10` (`5331`). The same fit reports different failure modes by dimension.
- **A missing warm-start component is zero.** `coeff_init.get(components[k], 0.0)` (`5340`) makes a missing key the same as a zero prior. Pass 159 recorded the damping test treating a zero prior as absent, so the two parts of the code disagree about what zero means.
- **There are two σ floors.** The Tobit σ is floored at `1e-3` (`5386`, `5388`). Pass 164 recorded a sigma floor of `0.025` for the MAD path. Check which one governs each path.
- **Non-negativity is applied on both starts.** The LS start and the supplied start are both clipped at zero (`5337`, `5339–5342`). The active-set logic later relies on that.

**One hundred and sixty-seventh pass: `learning.py` (`5391–5510`, the Tobit log-likelihood and the gradient and Hessian)**

- **The censored survival branch covers all of `q > 8`.** `_tobit_mills` returns survival `0.0` for every `q > 8` (`5198`), so `surv <= 0` (`5406`) is true there too. The asymptotic log-survival (`5407–5411`) is then used for the whole range, not only for underflow. Its leading term is approximate, so the value above 8 is approximate.
- **The q clip is written three times.** The floor `q_i < q_clip` appears in the likelihood (`5403–5404`), the gradient (`5447–5448`), and the n_eff sum (`5609–5610`). A change to the clip rule must be made in all three.
- **The active-set test is the KKT condition for a non-negative c.** A component at zero with a negative gradient stays pinned (`5495–5497`). γ is never pinned (`5494`), so the reduced system always has at least one free index.
- **The Mills ratio is recomputed on every step.** It is evaluated for each censored row inside `_loglik` (`5405`) and in the gradient (`5449`), on every Newton iteration and every line-search step.

**One hundred and sixty-eighth pass: `learning.py` (`5511–5630`, the Newton loop, line search and result)**

- **The `m == 0` branch cannot run.** γ is always free (`5494`), so `m >= 1` (`5499–5503`). The branch is dead code, and its `converged = True` never applies.
- **The gradient stop is absolute.** `grad_norm < tol` (`5517`) compares a gradient that scales with the kWh units and σ against a fixed tolerance. Its meaning changes with the unit of the data.
- **The line search accepts ties.** `ll_new > ll_curr - 1e-12` (`5565`) lets a step that does not improve the likelihood count as a success. A flat ridge can therefore be followed.
- **The γ bound is silent.** Steps are clamped to ±10 (`5560–5563`) inside the line search. A clamped step is not recorded, so the diagnostic does not show that the bound was hit.
- **The line-search exhaustion is a model for the other exit.** The `for ... else` (`5554–5578`) turns exhaustion into a named failure that reaches the caller. The `max_iter` exit does not do the same (see the lesson on failure reasons).

**One hundred and sixty-ninth pass: `learning.py` (`5631–5750`, the 4D sample collector, head and first gates)**

- **The docstring lists "not shutdown" as a gate.** The filters list at `5655–5657` says shutdown hours are dropped, but the code keeps them as censored rows (`5720–5733`). Pass 162 recorded the same contradiction for 3D.
- **The shutdown counter counts rows that may be dropped later.** `shutdown_kept_censored` is incremented at `5731–5733`, before the reconstruction and the later gates (`5741`, `5746`, `5764`, `5773`, `5807`, `5815`). The name says rows are kept, but the count includes rows that are dropped afterwards.
- **`censored` is a drop key for kept rows.** It is counted at `5824` for rows that are appended at `5822`. The `drop_counts` name is wrong for that key.
- **The `screen_affected_entities` parameter is not used in this body.** It is declared at `5633`, and I did not see it read in `5631–5750`. The caller applies the entity scope instead (`5880–5882`). A parameter that looks like a gate but is not one.
- **A unit missing from the mode map is heating.** `unit_modes.get(entity_id, MODE_HEATING)` (`5703`) counts an unknown unit as heating, so an absent key becomes a mode.
- **The reported-hour map is rebuilt when the caller does not pass it.** `log_first_reported` runs at `5689–5690` when `first_reported` is `None`. The batch caller does not pass it (`5891–5897`), so the map is rebuilt for each entity and regime.

**One hundred and seventieth pass: `learning.py` (`5751–5870`, the 4D potential, the magnitude gate, the baseline and the saturation split)**

- **A solar-calculator error is counted as a dim sun.** The `try / except Exception` at `5752–5764` counts any exception as `low_magnitude`. A broken calculator and a low sun produce the same counter. This is the catch-all lesson.
- **The magnitude gate at `0.01` is a fourth one.** It is at `5766`. Pass 154 recorded three gates (`0.01`, `0.1`, `0.01`), so this is a fourth in the same family.
- **The baseline is a raw bucket lookup.** `unit_buckets.get(effective_bucket, 0.0)` (`5802–5804`) uses the stored bucket with no interpolation, and returns 0 when the bucket is missing. The obstruction fit reads the same quantity through `_get_prediction_from_model` (`6399–6411`), which may interpolate. The two fits can disagree about which hours qualify. Not checked.
- **The model is reached by two different paths.** The batch uses `coordinator.model.correlation_data_per_unit` (`5687`). The obstruction fit uses `getattr(coordinator, "_correlation_data_per_unit", {})` (`6226`). Both paths exist in the clone (`diagnostics.py:4572` uses the second). See the lesson on attribute names.
- **Wind is re-bucketed live when the data allows it.** The thresholds and the effective wind must all be numbers (`5783–5793`). Otherwise the stored label is used. The live rule is the default, and the stored label is the fallback.

**One hundred and seventy-first pass: `learning.py` (`5871–5990`, the 4D batch entity loop, the regime fit and the damping)**

- **The entity skips have named reasons.** Unknown entities, solar exclusion and the synthetic WeightedSmear strategy each return a named skip (`5877–5886`). This is the pattern pass 158 asked for.
- **The collector runs twice per entity.** The loop calls `_collect_batch_fit_samples_4d` once per regime (`5889–5898`), and each call rescans the whole log. Caching the scan would remove the repeated work.
- **Stored `None` raises rather than reading as zero.** `float(current_dict.get("s", 0.0))` (`5912–5915`) defaults an absent key to zero, but a stored `None` raises `TypeError`. This is the `get` lesson again.
- **The prior check uses a magnitude test.** `has_prior` (`5999–6001`) checks the `learned` flag first and the `1e-6` magnitude second. The comment explains why the flag comes first. The `1e-6` threshold is absolute.
- **A failed fit cannot write.** The convergence check (`5976–5982`) comes before the clamp and the write (`5984–6032`). The order is right.
- **The n_eff gate is checked before convergence.** `insufficient_effective_samples` (`5966`) comes before `did_not_converge` (`5976`). A fit that is both short and unconverged reports the sample count only.

**One hundred and seventy-second pass: `learning.py` (`5991–6110`, the damping blend, the write and the obstruction docstring)**

- **The first fit writes at full weight.** Without a prior, `damping_applied = 1.0` (`6013–6017`). A single first batch fit sets the coefficient completely. This is deliberate, but it is worth stating in any design that copies the rule.
- **The shutdown verdicts disagree.** The obstruction docstring says shutdown hours "carry no information about coefficient magnitude" (`6092–6097`). The batch Tobit keeps the same rows as censored and uses them for magnitude (`5817–5827`, `5720–5733`). The same data class is informative in one fit and uninformative in the other. Pass 162 is the same contradiction seen from the Tobit side.
- **The `seed_live_window` branch names its no-op.** It records `seeded_live_window = False` and `no_live_window_4d` (`6034–6042`). The parameter is accepted and does nothing, and the diagnostic says so.
- **The obstruction docstring says `dry_run` no longer writes.** It says so at `6116–6119`, but the Args section says the opposite (see pass 173).
- **The 0.30 threshold is written in the docstring.** The apply-gate check at `6113–6114` quotes `0.30`. The code compares against a named constant (`6818`, `6904`). The literal may drift from the constant. Not checked against the constant's value.

**One hundred and seventy-third pass: `learning.py` (`6111–6230`, the obstruction docstring and the head of `fit_solar_obstruction`)**

- **`dry_run` is documented twice.** The Args section has two `dry_run` entries (`6154–6158` and `6159–6160`). The first carries text about cooling diagnostics (`6155–6158`), which describes `include_cooling` (`6153`), not `dry_run`.
- **The `dry_run` text contradicts itself.** It says "run the analysis but write nothing" (`6154`, `6159`), while `6116–6119` says it no longer affects state. The code only passes it through (`6589`).
- **The return-shape docstring is stale.** It shows `learned`, `sse_flat` and the other fields at the facade's top level (`6164–6194`). The code nests `low` and `high` under each facade (`6931–6937`). `suggested_gates` is in the code (`6282`, `6596`) but not in the docstring.
- **The recalculation comment describes a fallback that is gone.** The comment at `6217–6225` says the baseline is rebuilt "when the logged value is absent". The code rebuilds it every time and does not read the logged value (`6308–6312`). A docstring that outlives the code again.
- **The balance point falls back to a literal.** `getattr(coordinator, "balance_point", 17.0)` (`6228`) uses 17.0 when the attribute is missing. Not checked against the constants file.

**One hundred and seventy-fourth pass: `learning.py` (`6231–6350`, the candidate set, the early returns and the per-entity loop)**

- **The no-solar early return has a different shape.** With no solar calculator, each facade gets only `learned` and `skip_reason` (`6270–6283`). The normal path returns `n_samples`, `low` and `high` (`6660–6667`, `6931–6937`). A reader that expects `low` on this path will fail. The consumers were not checked.
- **The insufficient-samples path has its own shape too.** It omits `sse_flat` and the facade-level fields (`6669–6707`). Three shapes for one result.
- **Several silent drops are not counted.** A missing `inputs` (`6291–6293`), zero DNI and DHI (`6296–6297`), a non-learning regime (`6340–6341`), and a missing baseline (`6414–6415`) are all skipped without a counter. `n_skipped_learning_status` does not account for every skipped hour.
- **A bad temperature becomes the balance point.** `float(entry.get("temp", balance_point))` falls back to the balance point on a bad value (`6313–6318`). The row is then treated as if it had been recorded at the balance point.
- **The aux skip covers every entity.** Aux-active hours are skipped before the entity loop (`6286–6287`). The comment at `6330–6332` explains the shutdown case, so the two agree.

**One hundred and seventy-fifth pass: `learning.py` (`6351–6470`, the shutdown constraint branch, the potentials and the dominance filter)**

- **The potential formulas are copied.** The shutdown branch rebuilds the facade potentials (`6361–6368`) with the same formulas as the main path (`6440–6448`). A change to one copy leaves the other as it was.
- **Saturated heating rows are dropped here and kept there.** The obstruction fit drops rows at or above the saturation ratio (`6421–6422`, "no slope info"). The batch Tobit keeps the same rows as censored (`5817–5827`). Two fits on one dataset treat saturation in opposite ways.
- **The cooling `<= 0` gate has a clear rationale.** The comment at `6427–6431` says the gate stops a fit from learning a shape that hides negative-impact samples. Keep the comment with the gate.
- **The dominance filter is checked twice.** `pot_sum > 0.0` at `6461` repeats the test at `6451`. The redundant part is harmless but unnecessary.
- **The HIGH-regime cooling floor counts only dominant samples.** `regime_counts` increments only for samples that pass the dominance filter (`6471`). The floor at `6858–6861` is therefore a count of facade-dominant cooling samples, not of all cooling samples.

**One hundred and seventy-sixth pass: `learning.py` (`6471–6590`, the boundary sweep)**

- **The candidate score uses one window for both SSEs.** The window is `K` samples on each side of the cutoff (`6529–6536`). Both the gated and null SSE are taken over that window, so the comparison is fair. The span check (`6537–6538`) rejects windows that are too wide.
- **The low and high sweeps are one function with the gated side flipped.** The branches at `6541–6552` and `6555–6564` match the docstring (`6496–6501`).
- **Ties go to the lowest cutoff.** The comparison at `6568` is strict, so the first candidate wins. The docstring does not say so.
- **A zero null SSE skips the candidate silently.** `sse_null <= 0.0` (`6565–6566`) drops a window with no residual. No counter or reason records it.
- **The sweep helper is defined once per call.** It is a closure with no state, and the code reads clearly. Nothing to change.

**One hundred and seventy-seventh pass: `learning.py` (`6591–6710`, the shutdown constraint and the per-facade setup)**

- **The shutdown constraint uses the `n`-th extreme, not the extreme.** `sorted_sd[n_required - 1]` and `sorted_sd[-n_required]` (`6644–6646`) ignore the most extreme samples. The comment (`6628–6636`) gives the reason: one false-positive shutdown at an extreme elevation must not block the gate. The docstring agrees (`6087–6097`).
- **The shutdown fields are in `common` but not in the docstring.** `n_shutdown_constraints`, `shutdown_min_elev` and `shutdown_max_elev` (`6660–6667`) are missing from the return shape (`6162–6194`).
- **The insufficient path gives two reasons that disagree in purpose.** It sets `applicable_reason: "not_learned"` and `skip_reason: "insufficient_samples"` (`6672–6676`). The first describes the outcome and the second describes the cause. Not wrong, but a reader can mix them up.
- **`sse_flat` is diagnostic only.** It is an ungated global SSE (`6709–6712`), and the decision uses the local window. The comment says so.

**One hundred and seventy-eighth pass: `learning.py` (`6711–6830`, the boundary finaliser, the data-adaptive range and the LOW sweep)**

- **`no_candidate_passed_sample_floor` names one of four causes.** It is returned whenever `best_crit` is `None` (`6840`, `6926`). The sweep also returns `None` for the span check (`6537–6538`), the shutdown constraint (`6522–6526`) and a zero null SSE (`6565–6566`). See the lesson on named reasons.
- **The data bound is inclusive where the floor is strict.** `elev_arr[-K_FLOOR]` (`6776`) can equal a candidate that then has only `K_FLOOR - 1` samples above it. The sweep checks the floor again (`6533–6534`), so the result does not change. The bound is only a hint.
- **The RMS reduction is computed twice.** `_finalize_boundary` computes it (`6748–6758`), and the pass test computes it again (`6820–6827`). The same formula in two places can drift.
- **Both gates use strict `>`.** The SSE test at `6818` and the RMS test at `6828` pass only when the value is above the threshold. This is consistent.
- **`_finalize_boundary` is defined inside the facade loop.** It is rebuilt for each facade. It is harmless, but it reads better as a module-level helper.

**One hundred and seventy-ninth pass: `learning.py` (`6831–6950`, the HIGH sweep and the facade result)**

- **The cooling floor runs before the range check.** The HIGH sweep is skipped for too few cooling samples (`6858–6875`) before the data-range check (`6878–6892`). A facade whose data does reach the high regime still reports `insufficient_cooling_for_high_regime`. The design rationale is written out (`6846–6857`), and the reason is accurate.
- **The HIGH and LOW paths are the same code with the names changed.** The pass test (`6904–6923`) matches the LOW test (`6818–6837`). A shared helper would remove the duplicate.
- **The combined-window argument needs the rest of the function.** The comment at `6939–6950` says that a true high gate makes the data above it zero, which the LOW sweep would read as a low gate. The argument is plausible, but the code that enforces it is past `6950` and was not read.
- **Not verified:** the combined-window check and the `suggested_gates` build. Both are in the next batch.

**One hundred and eightieth pass: `learning.py` (`6951–7070`, the combined-window check, the apply gate and the suggestion list)**

- **The combined-window check keeps the stronger side on a tie.** When both sides learn and the gap is below `OBSTRUCTION_FIT_MIN_WINDOW_DEG`, the low side is discarded only if `high_imp < low_imp` (`6965–6976`). An exact tie discards the high side. The rule is not written down.
- **Two variables are set and never read again.** `new_low` and `new_high` are reassigned at `6970` and `6976`, but nothing after the check reads them. They are dead assignments.
- **The apply gate is computed per side, with stability defaulting to `True`.** `stability_per_facade.get((facade, "low"), True)` (`6985–6990`) means a single-pass caller always passes the stability check. The docstring says so (`6981–6984`).
- **The `crit_state_per_unit` comment does not match the code.** The comment at `7041–7047` says the lookup "above" keeps `before_*` values current. The `before_*` values come from `crit_fn` (`6610`), not from `crit_state_per_unit`, and the parts read do not use that dict again.
- **`suggested_gates` is the only output of a passing boundary.** Applicable boundaries are appended (`7016–7037`), and the write-through was removed (`7041–7047`). This matches the #1020 docstring, so the output contract is consistent.

**One hundred and eighty-first pass: `learning.py` (`7071–7190`, `compute_implied_for_apply`, the head and the 3D pass)**

- **The docstring return shape omits the 4D keys.** The docstring lists `implied`, `windows`, `sample_count`, `drop_counts` and `days_back` (`7071–7072`). The code also returns `sample_count_4d`, `drop_counts_4d`, `implied_4d` and `windows_4d` (`7189–7192`).
- **A comment states the wrong fraction.** The comment at `7155–7158` says the per-window minimum is "half the global threshold". The code is `max(8, APPLY_IMPLIED_MIN_QUALIFYING_HOURS // n_windows)` (`7158`), which is a third when `n_windows = 3`.
- **The `match_diagnose` claims are not checked here.** The comment at `7113–7123` says `match_diagnose=True` drops the min-base gate, includes shutdown samples, reads the log-time base, and skips the MAD baseline. The collector that does this was not read in this batch.
- **The 3D pass does not block the 4D pass.** The comment at `7143–7146` explains that sparse 3D data must not short-circuit 4D. The code has no `return` in the 3D block (`7147–7171`), so this matches.
- **The 3D implied value is not clamped.** The docstring says there is no clamping (`7084`). `_solve_batch_fit_normal_equations` can return negative components, and the rounding at `7150` keeps them. The caller has to decide what a negative means.

**One hundred and eighty-second pass: `learning.py` (`7191–7310`, the 4D pass in `compute_implied_for_apply` and `assess_apply_implied_stability`)**

- **The apply path has no `n_eff` gate on 4D, but the diagnose path does.** `compute_implied_for_apply` accepts a 4D fit once it converges (`7201–7205`). `compute_tobit_for_diagnose` also rejects a fit with `n_eff < TOBIT_MIN_NEFF` (`7883–7885`). The same fit can be shown in diagnose and rejected there, but accepted in apply. The 4D windows (`7227–7236`) have the same gap.
- **The 4D window gate uses uncensored rows only.** A chunk is skipped when `chunk_n_unc < TOBIT_MIN_UNCENSORED` (`7219–7221`). A chunk with many censored rows is therefore fitted on little information, and no `n_eff` check applies.
- **The sign-flip check uses every non-zero value.** The docstring says "non-trivial values" (`7254`). The code uses `non_zero = [v for v in values if v != 0]` (`7303`). The comment at `7296–7302` says this is intended, but the docstring disagrees. A `-1e-9` next to `+0.58` is a sign flip under this rule.
- **The spread check has a hard-coded floor.** `abs(v) >= 0.001` (`7312`) is not the `near_zero` argument and is not in the constants list checked. It is a second "trivial" threshold beside `near_zero`. Lesson: one idea with several thresholds.
- **An absent direction counts as zero.** `w["coefficient"].get(d, 0.0)` (`7275`) turns a missing component into a zero value in the window list, so a stable zero can be reported for a component the window never fitted.

**One hundred and eighty-third pass: `learning.py` (`7311–7430`, the spread check and the head of `_update_unit_tobit_live`)**

- **The spread check is skipped when fewer than two values are non-trivial.** `len(abs_vals) >= 2` (`7313`) means a single large value with any number of trivial ones is "stable" by default. Only the near-zero consensus and the sign check cover that case.
- **The docstring says the first transition is rate-limited.** The docstring at `7365–7366` says the first transition from blocked to applied is rate-limited. The code at `7682–7691` says the rate limit depends on step size alone, not on block history.
- **The caller contract includes two guards that this function does not check.** The docstring says the caller has checked the MPC exclusion and the feature flag (`7349–7358`). Nothing here enforces them. Not verified against the callers.
- **A zero expected base is not guarded here.** `is_censored` is `actual_impact >= RATIO * expected_unit_base` (`7411–7414`). With `expected_unit_base = 0.0`, every heating sample with a non-negative impact is censored at a threshold of zero. The caller guard was not read.
- **The `solar_model_version` field is written and never read here.** The slot stores the version (`7399`), and the docstring says the storage load resets stale slots (`7356–7358`). The version check is therefore somewhere else.

**One hundred and eighty-fourth pass: `learning.py` (`7431–7550`, the result defaults, the cold-start return and the LS fallback)**

- **`in_cold_start` is `True` on every path that does not apply a write.** It is set to `True` at `7435` and cleared only at `7747`. Insufficient uncensored rows, a failed warm start, a non-converged fit and a plausibility block all return `True`. The docstring defines it as `n_eff < TOBIT_MIN_NEFF` (`7370–7377`). The caller reads `True` as "run NLMS", so one flag carries several meanings.
- **A zero prior is treated as no prior.** `any(regime_coeff.get(k, 0.0) for k in ("s", "e", "w"))` (`7469–7471`) sends an all-zero prior to the LS start. This matches the damping test (pass 159) and the warm start in `_solve_tobit` (pass 166).
- **The LS-fallback retry is triggered by any non-convergence.** The retry at `7510–7525` runs whenever a warm start was used and the fit did not converge. The comment at `7481–7509` gives the reason, and its numbers (0.55 against 1.65, `7503–7505`) describe a past incident. The code is consistent with the comment.
- **A failed retry overwrites the first result.** `fit` is replaced even when the retry also fails. The later `converged` check at `7548` then reports the retry's outcome, not the original warm start's.
- **The `warm_start_failed` path reports a reason in two places.** `slot["last_step"]` gets `skip_reason` (`7528–7531`), and `result["last_step_failure_reason"]` gets the same string (`7532`). The two agree here.

**One hundred and eighty-fifth pass: `learning.py` (`7551–7670`, the post-fit gates and the heating plausibility check)**

- **The plausibility gate is skipped below the magnitude floor.** The OLS comparison runs only when `tobit_max > PLAUSIBILITY_MIN_TOBIT_MAGNITUDE` (`7589`). A small Tobit fit goes straight to the write, with no uncensored-slope check. The gate is fail-open at small magnitudes. This is the lesson added above.
- **A degenerate OLS also passes the gate.** When `ols_fit` is `None` (`7598`), the function does not return, so the write proceeds. The comment at `7643–7652` covers only the norm guards. The `None` case is not discussed.
- **The uncensored-only OLS uses the same slot samples as the Tobit fit.** `uncensored_only` (`7590–7594`) comes from the same running window, so the two fits share their input. This is correct, but the window is not refreshed between them.
- **The magnitude check uses a literal floor for the rate limiter.** `prior_max > 0.05` (`7699`) is a bare literal, while the plausibility floor is a named constant (`7589`). Two magnitude floors in one function.
- **The log level depends on the previous skip reason.** `_log_fn` is `debug` when the entity was blocked before and `info` otherwise (`7608–7612`, `7658–7662`). The first block is logged at `info`, and repeated blocks at `debug`. This is deliberate; a reader could mistake it for a severity change.

**One hundred and eighty-sixth pass: `learning.py` (`7671–7790`, the direction check, the rate limiter and the write, and the head of `compute_tobit_for_diagnose`)**

- **The direction check is skipped when either vector is near zero.** The cosine test runs only when both norms exceed `1e-9` (`7653`). The comment at `7643–7652` explains this, but the guard means a near-zero Tobit vector is written without the direction check.
- **The rate limiter has no effect on a cold start.** `prior_max > 0.05` (`7699`) is false when there is no prior, so the first fit is written at full size. The comment at `7689–7691` says this is intended.
- **The rate limit is applied after the direction check.** A step that was capped by the limiter is still written, and `last_step_norm` (`7725–7728`) reports the capped step. The diagnostic therefore shows the step that was written, not the Tobit proposal.
- **The diagnose docstring says shutdown rows are excluded.** The docstring at `7771–7773` says that `for_tobit=True` excludes shutdown rows and keeps saturated rows as censored. The 3D and 4D collectors keep shutdown rows (passes 162 and 169). Whether `for_tobit` changes that was not checked in the collector.
- **The diagnose docstring return keys omit `failure_reason`.** The key is set at `7879`, but the list at `7778–7781` does not include it.

**One hundred and eighty-seventh pass: `learning.py` (`7791–7899`, the end of the file: `compute_tobit_for_diagnose`)**

- **The MAD baseline silently turns off if the model is not a dict.** The coefficient dict is read from `coordinator.model` (`7812–7813`). If it is not a dict, the code tries `_solar_coefficients_per_unit` (`7816–7819`). If that is not a dict either, the baseline is `None` (`7820–7821`), and the outlier filter is skipped without a counter. The comment at `7804–7811` says this happens only for test fixtures, but nothing in the code limits it to that case.
- **`censored_fraction` is `0.0` for an empty set.** `cens_frac` is `0.0` when `n_total == 0` (`7847`). An empty set and a set with no censoring read the same. This is the zero-versus-missing pattern again.
- **The diagnose path has no warm-start retry.** The fit at `7869–7871` uses no `coeff_init`, so it always starts from LS. The live path retries when a warm start fails (`7510–7525`). The diagnose path does not need the retry, because it never warm-starts, but a reader comparing the two may expect the same behaviour.
- **`did_not_converge` keeps the last iterate.** The coefficient is returned with `skip_reason = "did_not_converge"` (`7887–7891`). The docstring at `7784–7788` says callers must check `skip_reason`. The code does this as documented, but a consumer that reads only `coefficient` will treat an unconverged iterate as valid.
- **Some keys are present only on some paths.** `failure_reason` (`7879`) and `log_likelihood` (`7881`) are set after the solver runs, so they are absent from the early returns (`7866–7874`). This is the sparse-dict pattern.

**One hundred and eighty-eighth pass: `hourly_processor.py` (`1221–1298`, the end of the file: the log entry, the aux accumulation, the save and the reset)**

- **The cooldown units are a snapshot taken at log time.** `aux_cooldown_entities` is computed from the current aux scope when the row is written (`1231–1239`). The comment at `1224–1230` says why: the scope can be reconfigured later, and the offline fit would otherwise read a different set. The row carries the gate decision, not the input that produced it.
- **A missing `unit_modes` entry means heating.** `unit_modes` keeps only the non-heating units (`1248–1252`). A reader that treats an absent unit as "unknown" will drop every heating unit. The schema must say that absence means `MODE_HEATING`.
- **The duplicate guard depends on an ordering invariant.** It compares only the tail (`1259–1263`). The comment at `1254–1258` says the CSV import re-sorts by timestamp to keep the tail the latest entry. The guard is correct only while that holds.
- **Aux accumulation is outside the duplicate check.** The aux breakdown is added to the daily totals at `1276–1280`, after the log append. If the append was skipped as a duplicate, the aux is still added. Whether a re-run of the same hour can reach this code is not verified.
- **A failed save can double-count the aux.** The daily totals are updated at `1276–1283`, the save runs at `1293`, and the collector is reset at `1297`. If the save raises, the reset does not run, and the next hour adds the same breakdown again. Whether the caller catches the exception is not verified. Accumulate, persist and reset should be one unit, or the reset should come first.
- **The repair check runs after the log append (`1285–1290`).** The comment explains why: the hour just closed must count. The ordering is deliberate and documented. A health check that runs before the write would miss the newest hour.

**Application to us:** the cooldown snapshot is the same lesson as the one about storing the gate decision with the row. Check that our hourly rows store the gate state an offline fit needs, not only the inputs. Also write the default for an absent key into our log schema.

**One hundred and eighty-ninth pass: `daily_processor.py` (`1300–1316`, the rest of `process`)**

- **Daily resets follow the CSV write.** The daily row is written at `1300`, then the accumulators are reset at `1302–1305`. If the CSV write fails, the reset is skipped and the day's totals roll into the next day. This is the same ordering issue as the hourly save.
- **Dead energy references are removed only at day end.** `_last_energy_values` is cleaned at `1307–1312`. A sensor removed during the day keeps its last reading until midnight. This is harmless but worth knowing when reading the state.
- **The displayed daily total is reset in one place.** `ATTR_TDD` is set to `0.0` at `1314`, after the daily row is logged. The state is written again at `1316`. A reader that looks at the displayed value between these lines sees the reset before the save.

**One hundred and ninetieth pass: `forecast.py` (`2885–3009`, the week-ahead loop)**

- **`if current_inertia_avg:` treats `0.0` as missing (`2894–2897`).** A true average of 0.0 °C is falsy, so the fallback is skipped and the running inertia stays empty. This is the zero-versus-missing pattern. Any `if x:` test on a temperature has the same fault.
- **The inertia chain is updated only if a key exists (`2930–2931`).** When `final_inertia` is absent, `running_inertia` keeps the previous day's list. A missing key therefore carries a stale history forward, while the history fallback at `2935` resets it to `[]`. The two cases of "no inertia" are handled differently.
- **The midnight snapshot overrides only the kWh (`2921–2922`).** `solar_impact` (`2924`) still comes from the live prediction. A day row can then show a full-day kWh with a remaining-hours solar impact. The row mixes two bases.
- **The reliability tiers fail closed (`2948–2956`).** Any unknown `source` becomes `"low"`. This is the right default, and it is a fail-closed design.
- **The coverage downgrade is skipped when temperature is missing (`2960–2970`).** That path keeps whatever reliability was set earlier. The commented-out `note` at `2969–2971` is dead code.
- **A missing baseline wind becomes calm (`3006–3007`).** `base_wind` is `0.0` when the last-year wind is `None`, which maps to the calm bucket. The baseline is then compared in the wrong bucket, and nothing flags it.

**Application to us:** the zero-versus-missing check on temperatures should be a search item for our own code. The mixed-basis midnight row is a reminder to override every field a snapshot replaces, or none of them.

**One hundred and ninety-first pass: `forecast.py` (`3010–3129`, the end of the week-ahead stats and `get_hourly_forecast`)**

- **The confidence thresholds are absolute kWh values (`3048–3055`).** `p50_error_per_day < 2.0` and `< 4.0` depend on house size. A small flat and a large house get the same label for the same relative error. This is the absolute-threshold pattern.
- **The forecast band is built from measured week-sum errors (`3077–3089`).** The comment says the earlier construction multiplied a daily p95 by 7, which overstated the spread (independent errors grow with √7, not ×7). The band is also left out until enough windows exist. The omitted-when-thin rule is a good choice.
- **The band is centred on the live total, not the snapshot (`3087–3088`).** `p95_week` comes from stored midnight plans, but the band is centred on `total_kwh`, which uses the live forecast for the rest of the week. The width and centre come from different bases. Whether this matters depends on how far the live total moves during the week, and that is not measured here.
- **Two access styles for the same stats dict.** `uncertainty` is read with `.get` and defaults (`3045–3046`). `week_horizon["samples"]` (`3085`) is read with a direct index. If `_calculate_week_horizon_stats` omits the key on some path, this raises `KeyError`. Unverified.
- **`get_hourly_forecast` returns an empty list on a missing key (`3129`).** `result.get("hourly_plan", [])` hides a failed build as "no hours". The caller cannot tell an empty plan from a broken one.

**Application to us:** the forecast band is a good model for our own week-ahead band: built from measured errors, and omitted when the sample is thin. Check whether our band is centred on the same basis that its width is measured on.


**One hundred and ninety-second pass: `statistics.py` (`4141–4306`, the end of the file: the grid search and the report of `calibrate_wind_thresholds`)**

- **Each candidate is scored on its own subset of hours.** The loop skips an hour when the model has no entry for that temperature and bucket (`4186–4187`), or when the expected value is zero or less (`4192–4193`). A candidate that moves hours into a bucket with missing data scores fewer hours. The MAE values therefore come from different samples. This is the common-sample problem from the earlier sweep lesson.
- **The best candidate has no minimum sample size.** `results.sort(key=mae)` (`4224`) takes the lowest MAE, even when it rests on a few hours. `valid_hours` is stored, but it is not checked before the recommendation is returned.
- **There is no minimum-improvement gate.** `recommended_high` and `recommended_extreme` are always returned (`4298–4299`), even when `improvement_pct` is near zero. `data_quality` (`4280–4287`) reports the windy-hour count, but the recommendation is not withheld on low data. The text is advisory, and the caller decides what to do with it.
- **The data-quality label counts windy hours of the winner only.** `windy_h` comes from `best_result` (`4281`). A winning candidate with no windy hours is labelled "Low" even when the baseline has plenty of windy data, because the candidate that moved every hour to normal scores best.
- **Two denominators are reported together.** `cur_distribution` and `rec_distribution` count every pure hour (`4243–4261`). The MAE uses only hours with a valid expected value (`4264–4268`). A report that shows both can imply that the MAE covers the whole distribution.
- **The ratio is guarded, the sign is not.** `improvement_pct` is `None` when `current_mae` is zero or missing (`4277`). A negative improvement, where the recommendation is worse, is passed through as is.
- **Ties follow the grid order.** The grid is built from low to high (`4152–4158`), and the sort is stable, so ties go to the lower thresholds. The comment does not say so.

**One hundred and ninety-third pass: `storage.py` (`1432–1550`, the minifier and the periodic save)**

- **The periodic save swallows every exception (`1577–1578`).** The comment justifies this: a crash in the coordinator is worse than a logged error. The restore and backup paths re-raise (`1691–1693`, `1716`). The periodic save therefore fails silently over time, and nothing counts the failures.
- **`_tobit_default_applied` has two different defaults.** The periodic save reads it with a default of `False` (`1570–1572`). The backup reads it with a default of `True` (`1675–1677`). A coordinator that lacks the attribute is saved as "not applied" and backed up as "applied". This is the copied-default pattern.
- **Stored state defaults to zero when the source is absent.** `current_model_rate`, `current_aux_impact_rate` and `tdd_accumulated` default to `0.0` (`1490–1492`, `1516`). A missing value is written as a real zero, and the next load reads it as a measured zero.
- **The DST hour is stored as an instant.** The comment at `1483–1484` says the hour number cannot tell a repeated DST hour apart, so the start of the hour is stored in UTC. The same reason applies to our log.
- **`battery_model` is written as a constant (`1515`).** `"ema"` is written every time, and nothing in this function reads it. A loader that does not check it cannot reject a different battery model.
- **The minifier silently drops keys it does not keep (`1443–1445`).** The forecast is minified to the fields used by the energy calculation (`1436–1440`). A consumer that needs another field gets `None` or a missing key, and the storage size is the reason the field list is short.

**One hundred and ninety-fourth pass: `storage.py` (`1551–1670`, the rest of the save dict and the start of the backup dict)**

- **The save and the backup do not carry the same keys.** The save writes `learning_buffer_global`, `unit_modes`, `solar_optimizer_data`, `learned_u_coefficient`, `last_midnight_indoor_temp`, `last_hour_processed` and `last_hour_start` (`1482–1484`, `1509`, `1544`, `1554–1555`). The backup omits several of them (`1607–1678`). A backup taken from a running install is therefore not a full copy of the save.
- **The Tobit comment explains a missing field, not a missing default.** The comment at `1558–1569` says the flags persist even when the master flag is off, so the flag-off install reloads the same defaults. This is consistent. The backup comment at `1665–1671` says that without the Tobit keys a restore silently falls back to default-on. That is the same problem as the save: the absent key chooses the behaviour.
- **The save and the backup both write `self.coordinator.data.get(...)` (`1516–1535`, `1628–1638`).** Values are copied from the public data dict, not from the internal state. A value that is stored only in internal state is lost in the backup and kept in the save.

**One hundred and ninety-fifth pass: `storage.py` (`1671–1790`, the end of the backup and the start of the restore)**

- **`_tobit_default_applied` defaults to `True` on the backup side (`1675–1677`).** The same key defaults to `False` in the save (`1570–1572`). See the previous pass.
- **The backup write is in an executor and is re-raised (`1680–1693`).** The directory is created with `os.makedirs` in the worker, which is correct. The write is not atomic. A crash in `json.dump` leaves a truncated file at the target path.
- **The restore checks only that one of two keys exists (`1710–1711`).** `correlation_data` or `daily_history` is enough to pass the check. A file that has one key and none of the others is accepted, and every other field gets its default.
- **The restore runs the migration chain on the backup, not on the store (`1716–1729`).** The comment says the HA `Store` migrate hook does not apply to JSON backups. The chain is long (nine steps), and every step has to handle a file from any earlier version.
- **Rebinding an attribute breaks the alias rule.** `_correlation_data` is cleared and updated in place (`1732–1733`). `_correlation_data_per_unit` is replaced with a new dict (`1735`). The in-place rule is stated in the hourly code (`hourly_processor.py:1296`: "In-place clearing preserves coordinator aliases for dict fields"). A rebind makes any other holder of the old dict stale. Whether anything holds such a reference is not verified here.
- **Two names for one source are read.** `tdd_accumulated` falls back to `hdd_accumulated` (`1770`), and `tdd_daily_stable` falls back to `hdd_daily_stable` (`1772`). This is the compatibility form of the rename. It is correct for the old files, but it means both names are read everywhere.
- **The `data.get` default for `last_hour_actual` and its siblings is zero (`1790–1793`).** An absent value shows as a measured zero deviation on the dashboard.

**One hundred and ninety-sixth pass: `storage.py` (`1791–1910`, the restore of the state and the Tobit flags)**

- **Absent keys follow two policies in one function.** Some restores keep the current value when the key is absent (`1795–1805`, `1807–1816`): `learning_enabled`, the aux flags and the learning rate. Others take a default (`1733`, `1737`, `1775`, `1892`, `1895`): the correlation data, the observation counts, `learned_u_coefficient`, `unit_modes` and the solar-optimizer state. The same missing key therefore means "keep" in one place and "clear" in another.
- **`unit_modes` is cleared by a backup that does not carry it.** The backup omits `unit_modes` (see the pass for `1551–1670`). The restore then sets `_unit_modes` to `{}` (`1892`). Every unit reads as heating after the restore. This is a probable fault, and it has not been reproduced.
- **Malformed entries are dropped without a count.** Non-dict entries are dropped from `solar_coefficients_per_unit` (`1829–1832`), from `last_batch_fit_per_unit` (`1836–1838`), from the 4D maps (`1859–1865`), and from the buffers (`1845–1846`). Regimes other than `heating` and `cooling` are dropped (`1852`). Nothing logs or counts the drop.
- **A malformed gate becomes "no gate".** In the obstruction restore, a facade with neither `low` nor `high` numeric values is set to `{low: None, high: None}` (`1884–1886`). A numeric value that cannot be converted raises at `float(...)` (`1880–1881`), so the two cases fail differently. An entry that parses but holds no value reads as no obstruction gate.
- **A numeric facade value is treated as the high gate (`1883–1884`).** The legacy float form becomes `high`, with `low` left as `None`. This is the normalisation the v9 lesson covers, repeated here on the restore side.
- **The restore sets state only when the backup has the key, for the Tobit flags.** The comment at `1897–1910` says a pre-1.3.5 backup must keep the current session, and a 1.3.5 or later backup must restore the four fields verbatim, including an explicit user disable. The check is the presence of the `_tobit_default_applied` marker, which is not seeded by the v4 to v5 migration.

**Lessons added this pass**

- **One function, two policies for an absent key.** A restore that keeps the current value for some keys and clears it for others gives different results for the same missing key. Choose one policy and write it in the function's docstring.
- **A backup must carry every key its restore reads, or the restore must say what an absent key means.** `unit_modes` and `learned_u_coefficient` are read on restore and not written by the backup.
- **Malformed entries dropped without a count are invisible.** Each `isinstance` filter in the restore discards data silently. A counter in the restore log would show the loss.
- **A periodic save that swallows its exception hides a failing disk.** The comment gives a reason, but the failure count is missing.

**One hundred and ninety-seventh pass: `storage.py` (`1911–2030`, the end of the Tobit restore, the restore's exit, and the CSV append with schema evolution)**

- **A missing model version is treated as the current version.** The restore keeps a Tobit statistic when its `solar_model_version` matches the current one, and drops it otherwise (`1938–1942`). The default for an absent version is the current version (`1938–1940`). An old statistic without a version is therefore kept, and the check fails open. The fail-closed choice is to drop a statistic whose version is unknown.
- **The restore is not atomic.** The migrations run first (`1716–1729`), and then the state is assigned one field at a time (`1732–1895`). A failure after the first assignment leaves the coordinator with part of the backup and part of the old state. The exception is re-raised (`1962–1964`), so the error is visible, but nothing rolls back the fields already set.
- **The restore ends with a save and two recalculations (`1955–1958`).** The save runs before `calculate_temp_stats` and `calculate_potential_savings`. A failure in either recalculation leaves the state saved and the derived statistics stale, and the error is still raised.
- **The CSV writer checks the header before the row (`1994–2004`).** A header that cannot be read returns without writing, and the error is logged. A header that is empty falls through to a new file, which is the right behaviour.
- **Schema evolution rewrites the whole file through a temp file (`2013–2040`).** The atomic replace is correct: a failed write leaves the old file in place (`2035`, `2039–2040`). The new row is lost when the write fails, and only the log records it.
- **The column names are indexes, not identities (`2094–2100`, `2220–2223`).** The unit columns are named `unit_{i}_actual` and `unit_{i}_expected`, where `i` is the position in `energy_sensors`. If a sensor is removed or reordered, column `unit_0_actual` holds a different unit in the old rows and the new rows. The header does not say which unit it is. The export uses the same index names (see the pass for `2150–2269`).
- **A missing forecast or solar factor is written as zero (`2085`, `2088`).** `forecasted_kwh` and `solar_factor` default to `0.0` when the key is absent, so a row without a forecast reads as a forecast of zero.

**One hundred and ninety-eighth pass: `storage.py` (`2031–2149`, the end of the CSV append and the hourly and daily CSV writers)**

- **The hourly writer reads its fields with direct indexing (`2077–2083`).** `timestamp`, `hour`, `temp`, `inertia_temp`, `effective_wind`, `wind_bucket`, `actual_kwh`, `expected_kwh`, `deviation` and `auxiliary_active` are read with `log_entry[...]`. A missing key raises `KeyError`. The except clause at `2106` catches only `OSError` and `csv.Error`, so the `KeyError` escapes into the hourly processor.
- **The escape has an ordering consequence.** The CSV write runs at `hourly_processor.py:1273`. The aux accumulation, the save and the collector reset follow it (`hourly_processor.py:1276–1297`). A `KeyError` in the CSV step skips the reset, and the next hour adds the same collector data again. This is the same double-count as the pass for `hourly_processor.py:1276–1297`, reached by a different path.
- **Two except clauses for the same write, with different scopes.** The hourly writer catches `(OSError, csv.Error)` at `2106–2107`. The daily writer does the same at `2123–2124`. The path-validation error is caught separately at `1974`, and it is logged once per path, not each hour (`1974–1978`). The pattern is good: the warning is rate-limited by the path.
- **The daily writer passes the whole log entry to the CSV append (`2119`).** The entry's keys become the header. A key that appears only in a later day is handled by the schema-evolution path, which is correct. The hourly writer builds its row by hand, so the two writers have different schemas by design.

**One hundred and ninety-ninth pass: `storage.py` (`2150–2269`, the CSV export and the start of the CSV import)**

- **The hourly export takes its columns from the first row only (`2216–2217`).** `fieldnames` is built from `data[0]`. A key that appears only in a later row is not in the header, and `row = {k: v for k, v in entry.items() if k in fieldnames}` (`2229`) drops it without a message. The daily export takes the union of every row's keys (`2140–2144`). The two exports handle a schema change differently, and the hourly one loses the new columns.
- **The daily export decides the type of each column from its first non-null value (`2152–2158`).** A column whose first value is a scalar is kept, even when later rows hold lists. Those later list values are then dropped at `2185–2186` with no count.
- **The hourly export keeps lists and drops only dicts (`2217`).** The daily export drops both lists and dicts (`2185`). A list in the hourly log is written as its text form.
- **The unit columns come from the current configuration (`2220–2223`, `2233–2235`).** Historical rows are read by entity id, and a unit that is not configured now has no column. A unit that a row does not report is written as `0.0` (`2234–2235`), the zero-versus-missing pattern again.
- **The legacy vector name is a fallback inside the vector read (`2194`).** `actual_kwh` falls back to `load`. This is the same two-names pattern as the restore, and the export reads both forever.
- **The hourly writer's guard is repeated (`2205–2206`, `2211–2212`).** The `if not data: return` appears twice. The second is dead code.
- **The export writes the target file in place (`2174`, `2225`).** It opens with mode `'w'` and does not use the temp-and-replace pattern that the CSV append uses. A failure during the write leaves a truncated export. The export is a user-requested copy, not state, so the loss is limited.
- **Errors are logged and re-raised (`2241–2243`).** The service handler surfaces the failure. Good.

**Two hundredth pass: `diagnostics.py` (`1081–1200`, the start of `diagnose_solar`: the accumulator layout and the window boundaries)**

- **The window boundaries collapse for short look-backs (`1094`).** `window_boundaries = [days_back, int(days_back * 2 / 3), int(days_back / 3), 0]`. For `days_back = 2`, the boundaries are `[2, 1, 0, 0]`, and two windows have the same start. For `days_back = 1` they are `[1, 0, 0, 0]`, so two of the three stability windows are empty. The comparison of windows is then a comparison of empty sets, and nothing says so.
- **The accumulator is a wide dict with a fixed shape (`1097–1214`).** Every entity gets the same keys, including nested windows, buckets and lists. A key that one branch forgets to create raises at the first use rather than reading as zero. The shape is the contract, and nothing enforces it except the initialiser.
- **The COP regimes are offsets from the balance point in degrees (`1147–1149`).** The boundaries are `BP−8`, `BP−2` and `BP+2`. They are fixed offsets in the unit the temperatures are stored in. If a Fahrenheit install stores temperatures in another unit, these offsets are wrong. Whether the temperatures are converted before this point is not verified.
- **The elevation residual lists are unbounded per bucket in principle (`1162–1165`).** The comment says the list is bounded by `qualifying`, which is at most about 360 entries per entity. That bound holds only while the 30-day window holds. The comment states the bound as a fact about the data, not about the code.
- **The lag buckets record a varying count per lag (`1173–1181`).** The comment says skipped entries drop out of the lag they would have filled, so `n_per_lag` differs between lags. Comparing lags needs the count for each lag. The common-sample problem appears here too.

**Two hundred and first pass: `diagnostics.py` (`1201–1320`, the evening-tail bucket, the exclusion counters, and the first look at the log)**

- **The exclusion counters carry one key per reason (`1217–1224`).** `UNIT_LEARNING_SKIP_REASONS` is merged into the same dict as the diagnose-only reasons. A reason that appears in one place but not the other is silently a zero, which is the sparse-dict pattern.
- **Some hour-level fields default to a value that changes the answer.** `correction` defaults to `100.0` (`1287`), which means "fully open". An entry with no correction is therefore stratified as open. `solar_impact_raw_kwh` and `solar_impact_kwh` default to zero (`1297–1298`), and `guest_impact_kwh` defaults to zero (`1300`). An absent value reads as a measured zero or a measured open screen.
- **Legacy logs without `solar_dominant_entities` are treated as having no shutdown hours (`1303–1306`).** The comment says so. The default is correct for logs written before the field existed, but a missing key and an empty list are the same here.
- **Index-aligned lists are kept in step by one branch (`1309–1318`).** The comment says both lists append inside the same branch, so the indexes match. This is the right way to keep parallel lists aligned: one append site.
- **The log lookup is keyed on UTC instants (`1251–1262`).** The comment says a string key missed every tail that crossed a DST change. The filter at `1259` uses the first ten characters of the timestamp, which is the date as written. That is the text-date comparison from the timestamp lesson.
- **The wasted-solar fallback is written twice (`1329–1332` and `1357–1360`).** The same expression, with the same fallback to `solar_wasted_kwh`, appears in two places in one loop. If one changes, the other does not.

**Two hundred and second pass: `diagnostics.py` (`1321–1440`, the battery sweep tuple and the stratification buckets)**

- **`has_heating_unit` reads the current configuration against a historical row (`1373–1378`).** A sensor that is missing from `unit_modes` is counted as heating. `energy_sensors` is the current list. A sensor that was added after the row was logged counts as heating for that old row. The fix is to record the heating state with the row, which is the lesson from the cooldown snapshot.
- **A dead branch follows a flag that is always true (`1368–1381`).** `stored_non_default = bool(unit_modes)` is set inside `elif unit_modes:`, so it is always `True`. The test at `1380` is `not stored_non_default`, which is always `False`, so `has_heating_unit = False` at `1381` never runs. The branch looks like a guard for "no sensors configured" and does nothing.
- **The `has_heating_unit` rule uses wasted solar as a witness (`1361–1366`).** Positive wasted solar means a heating unit contributed, because cooling and off modes return zero wasted. The comment explains the reasoning. This is a good use of a second signal when the first is unreliable.
- **Two thresholds define "closed" in one function.** The comment at `1239` gives `correction < 50` for the closed bucket of the battery check. The sweep bucket at `1431–1434` uses `correction < 40`, and the accumulator comment at `1130–1132` also says `< 40`. The open threshold is `80` in all three. A screen position between 40 and 50 is therefore "closed" in one list and "mid" in the other. Whether the battery check uses the comment's value is not verified. This is the "one idea, several thresholds" lesson again, in a new place.
- **The temperature regimes match the earlier definitions, with one new bucket (`1415–1422`).** The sweep adds a `transition` bucket for `BP−2 ≤ T ≤ BP+2`, and the comment (`1399–1412`) says it is kept so that the symptom is visible for high-balance-point installs. The earlier diagnostic drops that bucket, so the two reports use different regimes for the same hours.
- **The hour bucket for a missing hour is `night` (`1390–1397`).** `hour` defaults to `-1` (`1281`), which falls into the `else` branch and reads as night. A row without an hour is counted in the night bucket.

**Lessons added this pass**

- **Read the schema from every row, not from the first.** The hourly export loses columns that appear only in later rows (`storage.py:2216–2229`). The daily export takes the union of keys (`storage.py:2140–2144`). The union is the right choice.
- **A column named by position changes meaning when the list changes.** `unit_{i}_actual` maps to a different unit after a sensor is removed or reordered (`storage.py:2094–2100`, `2220–2223`). Name the column by the entity id.
- **A missing version is not the current version.** The restore keeps a statistic with no version as if it were current (`storage.py:1938–1940`). An unknown version should be dropped.
- **A flag that is always true makes its branch dead.** `stored_non_default` in the battery sweep is always true inside the branch that sets it, so the test that follows never runs (`diagnostics.py:1368–1381`).

**Two hundred and third pass: `storage.py` (`2270–2389`, the CSV import: mode selection, parsing and the weather-only entry)**

- **The import mode is inferred from a missing mapping key (`2274`).** `weather_only_mode = col_energy is None`. A mistyped energy column name is read as "no energy column", so the import runs in weather-only mode and reports success. The energy mapping is not checked against the file header.
- **Bad numeric cells follow three policies in one loop.** A bad temperature becomes `None` silently (`2322–2326`). A bad energy value raises and the row is dropped with a warning (`2329–2330`, handled at `2453`). A missing wind becomes `0.0`, which is the calm bucket (`2333`). The same kind of error has three outcomes.
- **Absent wind is written as calm in full mode.** `wind_speed` defaults to `0.0` (`2333`), and a full-mode row is kept with `effective_wind` computed from it (`2417–2418`). The row is then counted in the calm bucket, with no flag that the wind was missing.
- **The aux flag is parsed from a fixed set of strings (`2335`).** `'1', 'true', 'yes', 'on'` are true; any other value, such as `'y'` or `'2'`, is false, silently.
- **A cold-start import fabricates solar input.** When cloud cover is missing, the full mode uses a 50 % default (`2405–2408`). The solar factor is then stored as if measured. The comment says this is intended for cold-start imports.
- **Weather-only mode will not synthesise solar input.** The comment at `2340–2343` says so. The two modes handle the same missing field in opposite ways, and both choices are documented.
- **The DST-safe tz handling for naive timestamps (`2312–2313`).** Naive timestamps are assumed to be local. The comment does not say what happens in the repeated autumn hour, where a naive local time is ambiguous.

**Application to us:** the mode check should use the header, not a missing key. Any import of our own should have one policy for a bad cell and log the count of cells it dropped.

**Two hundred and fourth pass: `storage.py` (`2390–2509`, the full-mode entry and the per-hour and daily learning in the import)**

- **Imported rows have zero solar impact, whatever the solar factor says.** `solar_impact_kwh` is set to `0.0` at `2345` and written as `round(solar_impact_kwh, 3)` at `2423`. Nothing in the function reassigns it. A row with `solar_factor` of 0.7 has `solar_impact_kwh` of 0.0. The live log computes this value, and the import does not.
- **Imported rows also carry `expected_kwh = 0.0` (`2420`).** Any reader that compares actual with expected sees the whole actual as deviation until the row is recomputed.
- **The rolling inertia is built from the previous rows, not the previous hours (`2433–2436`).** `temp_history` keeps the last four rows. A gap in the CSV is skipped at `2309`, so the average can span hours that are not adjacent. The live inertia uses the log by hour.
- **Two temperatures are passed in one call (`2439–2449`).** `temp_key` is built from the rolling average, while `actual_temp=temp` is the raw value. This may be intended, but the two bases are not named.
- **The learning counter depends on a substring test (`2450–2451`).** The count goes up when `"skipped" not in status`. If `status` is a string, a message that merely contains the word would be counted as skipped; the type of `status` is not checked here (unverified).
- **Three thresholds for "enough hours" in one import.** The daily learning skips a day with fewer than 22 rows (`2467`), and its log message says "/24". The weather-only path needs at least 20 rows (`2583`). The live day test is not in this file. A day of 21 rows is learned in one place and not in the other.
- **Absolute thresholds on daily totals (`2474`).** `daily_tdd < 0.5` and `total_kwh <= 0` are absolute values with no units stated.
- **The U coefficient is seeded from the first imported day (`2478–2479`).** The first observed value is stored as is, with no check that it is plausible. Later days are blended with `DEFAULT_DAILY_LEARNING_RATE`.
- **The function returns its result to a caller that discards a failure (`2493`, `2498–2499`).** A validation error earlier in the function returns `(None, 0)` (`2278`, `2283`, `2299`), and the caller returns silently at `2498–2499`. The user gets no message. The failure appears only in the log.

**Two hundred and fifth pass: `storage.py` (`2510–2629`, the weather-only merge into the hourly log and the daily vectors)**

- **The join key is the UTC instant, the dedupe key is the string (`2520–2526` against `2707–2708`).** The weather-only merge joins on the UTC instant. The full-mode import dedupes on the raw timestamp string (`2707–2708`). Two forms of the same instant pass the dedupe and are both kept. This is the string-key fault the DST comment in the diagnostics warns about.
- **Duplicate timestamps in the file keep the last row silently (`2538–2541`).** The dictionary assignment overwrites the earlier row, and no count is logged.
- **The merge is field-conditional, which is the right design (`2559–2563`).** Only the fields present in the file are copied. The comment explains why an enrichment pass must not overwrite live values.
- **Orphan days are patched only when the whole day is missing from the hourly log (`2571–2578`).** The comment says so. A partly covered day is left alone, and the skip is not counted.
- **A day with fewer than 20 rows is skipped with a warning (`2583–2587`).** The message says "/24". Together with the 22-row threshold in the previous pass, this gives two numbers for one idea.
- **Vectors are created with a fixed shape when missing (`2594–2603`).** The `solar_rad` key is added only when solar is enabled. Later code tests `"solar_rad" in vectors` (`2639`), so the shape depends on a flag at creation time.
- **Hours outside 0–23 are dropped silently (`2615–2616`).** A DST-shifted or malformed hour index is not counted.

**Two hundred and sixth pass: `storage.py` (`2630–2758`, the end of the import: slot hours, the balance-point marker, the full-mode merge, the trim and the summary)**

- **A slot's weight is stored and used for the means (`2642–2650`, `2658–2668`).** A two-row slot counts twice in the day means. The comment at `2656–2657` says so. The weights are rebuilt from the temperature column when the stored list is the wrong length (`2644–2648`), which can reset counts recorded earlier.
- **The balance point is written only when it is consistent, or as `None` (`2687–2697`).** If every logged hour was patched, or the stored balance point equals the current one, the current value is kept. Otherwise the field is set to `None`. A stored `None` is an explicit "mixed basis" marker. This is the right way to show a mixed value, and it avoids a silent mix.
- **The full-mode merge is deduplicated by string (`2707–2708`).** See the pass above. The fall-back comment (`2711–2712`) names the sort problem, but the dedupe has the same fault.
- **The sort is by instant with the string as a tiebreak (`2713–2716`).** The sort is correct across the fall-back change, and the comment says why.
- **The daily rebuild reads the hourly log by string prefix (`2729`).** `e["timestamp"].startswith(day_str)` matches the local date as written. Any entry written in another offset can fall on the wrong day.
- **The trim runs after the daily rebuild and only in full mode (`2736–2742`).** The comment explains the order: imported days beyond the retention window must be aggregated first. This is a good ordering choice, and the trim is skipped for weather-only imports, where it is not needed.
- **The summary says a later step will update the model (`2750–2751`).** When `update_model` is on, the per-hour and daily learning has already run in this call (`2432–2489`). The message describes a step that is either already done or not in this function. Whether another step exists is not verified.
- **The outer handler logs with the traceback and re-raises (`2756–2758`).** Good.

**Two hundred and seventh pass: `diagnostics.py` (`1441–1560`, the entry's sun position, the per-unit filters and the saturation branch)**

- **An unparsable timestamp counts as today (`1442–1445`).** `days_ago` defaults to `0`, which places the row in the newest window. A bad date is therefore counted as recent, without a count of such rows.
- **OFF and DHW units are skipped without a count (`1469–1472`).** Only the guest modes increment `excluded["guest"]`. The excluded counters therefore do not add up to the number of unit-hours skipped.
- **`qualifying` is counted twice with different meanings.** `acc["qualifying"]` is incremented before the saturation test (`1517–1518`), so it includes saturated hours. `total_qualifying` is incremented after the saturation exit (`1578`), so it does not. The flag test at `2221` uses the per-unit count, so the saturation ratio is taken over a denominator that includes the numerator.
- **A missing `temp_key` falls back to the 10 °C coefficient (`1542`, `1573`).** `entry.get("temp_key", "10")` is a copied constant. An old row with no key is modelled at 10 °C, whatever its real temperature.
- **A missing correction means fully open (`1536–1538`, `1568–1570`, `1591–1598`).** Each place uses `100.0` or `None` as open. The same default appears in several places.
- **The saturation test uses an absolute floor on the base (`1524`).** `base_unit > 0.05` is in kWh with no units attached.

**Two hundred and eighth pass: `diagnostics.py` (`1561–1680`, the modelled solar, the screen buckets and the temperature regimes)**

- **The screen buckets in this function use 80 and 40 (`1591–1598`).** The comment at `1239` gives 50 for the closed bucket of the battery check. This block closes at 40. The global screen split at `1703–1706` closes at 50 and uses a strict `> 80` for open. Three cutoffs for one bucket appear in one function.
- **The transition comment does not match the code (`1619–1621`).** The comment says the dropped zone is `BP−2 ≤ T ≤ BP`. The code drops every heating hour above `BP−2` that is not in the deep or mild branches, and it drops cooling hours at or below `BP+2`. The zone is wider than the comment says in one direction.
- **Two shutdown treatments run in parallel (`1632–1637`, `1643–1669`).** The sensitivity tuples skip shutdown hours. The normal equations in the 30-day total include them, and the parallel no-shutdown set excludes them. The design is stated, and the 30-day total is the one that carries the shutdown bias.
- **The modelled potential uses the same `100.0` default for a missing correction (`1569`).** The reconstruction depends on the transmittance of an open screen when the correction is absent, and the comment at `1559–1565` explains why that gives 1.0 for every direction.

**Two hundred and ninth pass: `diagnostics.py` (`1681–1800`, the window assignment, the temporal bias and the lag walk)**

- **The window test leaves no gap and no overlap (`1672–1687`).** `w_end <= days_ago < w_start` gives [2D/3, D), [D/3, 2D/3) and [0, D/3) for the boundaries `[D, 2D/3, D/3, 0]`. The check for `days_ago` equal to `D` is correct because the cutoff already excludes it. This is correct, and the same boundaries collapse for short look-backs (see the pass for `1081–1200`).
- **Temporal bias uses different hour ranges from the battery buckets.** Here morning is 6–11 inclusive and afternoon is 12–17 inclusive (`1694–1699`). The battery sweep at `1390–1397` uses morning 6–10, midday 11–14 and afternoon 15–21. The hourly residual uses 6–18 (`1709`). The same hour is in different buckets in different outputs.
- **The screen test on the global stats is strict on one side (`1702–1706`).** A correction exactly 50 falls into neither bucket, and a correction exactly 80 is not "open" because the test is `> 80`. The per-unit bucket at `1593` uses `>= 80`. A boundary value is classified differently by the two tests.
- **The lag residual is base minus actual, and the elevation residual is implied minus modelled (`1732`, `1776–1778`).** The two are on different bases. For the tail hours the model is not subtracted, which is consistent with the design only when the tail has no solar input. The gate at `1766` is what makes that true, and it applies only for `k > 0`.
- **The tail mode uses the stored `unit_modes` with a heating default (`1760–1761`).** A missing key is heating, the same sparse-dict convention noted for the log.

**Two hundred and tenth pass: `diagnostics.py` (`1801–1920`, the evening-tail walk and the summary helpers)**

- **The evening walk repeats the lag walk's checks.** The mode, aux, base and actual tests at `1812–1830` are the same as at `1760–1775`. The two copies must change together. A fix to one check that is not made in the other will leave the two tail measures on different rules.
- **The first dark hour is searched for only within 12 hours (`1794`).** `range(1, 13)` stops at 12. An originator with no dark hour in that span contributes nothing to the evening buckets, and only the count of found anchors is reported.
- **The median of an empty list is `0.0` (`1837–1838`).** A zero median looks like a measured zero. The callers gate on the sample count (`1892`), so the zero is not reported, but the helper itself has no way to say "no data".
- **The minimum sample size differs by block (`1852`, `1914`, `2004`).** The evening block uses 10, the lag block uses 10 and the instantaneous block uses 5. None of the three is stated in the response, so a consumer cannot see which rule applied.
- **The evening docstring draws a physical conclusion (`1868–1882`).** A positive residual is described as refuting hotspot loss. The docstring is a reading guide, but it is written as a decision rule. The rule depends on the sign convention and on the sample size, neither of which the reader sees.

**Two hundred and eleventh pass: `diagnostics.py` (`1921–2040`, the lag-block docstring and the instantaneous block)**

- **The lag docstring says both tail sums are None when a lag is under-sampled (`1959–1962`).** The code does this (`1985–1989`). The docstring also says the 1–3 h sum is "populated more often than the 6 h sum by design", which is correct because it needs fewer lags.
- **The mean potential guard is 0.001 (`2019–2021`, `2030`).** A median residual divided by a mean potential near zero gives a meaningless ratio. The guard returns `None`, and the docstring and the code agree.
- **The instantaneous block reports `n` alone below the sample floor (`2025–2026`).** The consumer sees the count but not the reason the summary is missing. The docstring explains the reason, but the response does not.

**Two hundred and twelfth pass: `diagnostics.py` (`2041–2160`, the normal-equation solver and the start of the shadow replay)**

- **The 3×3 solution is correct.** The three Cramer determinants at `2077–2091` match the expansion along the columns for S, E and W. This checks out.
- **The 2×2 fallback runs on any small determinant, not only when the west term has no variance (`2097–2105`).** The docstring at `2052–2058` says the fallback is for "the west dimension has no variance (sum_ww ≈ 0)". The code tests the full 3×3 determinant against `1e-6`, so a near-singular fit for any reason takes the 2×2 path. The docstring describes a different trigger.
- **The fallback reports `w` as `0.0` (`2104`).** A coefficient that was never estimated is reported as a measured zero, which is the zero-versus-missing pattern again.
- **The absolute threshold `1e-6` on the determinant depends on units.** The determinant is cubic in the potentials, so the same data in another unit gives a different answer. This is the absolute-threshold lesson, already recorded for the learner.
- **The shadow replay's comment is unfinished (`2108–2113`).** A sentence ends without a full stop after "ankerpunkt", and the word is not English. This is a comment problem, not a code one.
- **The solar-affected scope is passed as `None` when the attribute is missing (`2141–2148`).** The replay then treats every unit as in scope, because `None` is the all-units value. This is the missing-scope lesson from the learner, now in the diagnostic path.

**Two hundred and thirteenth pass: `diagnostics.py` (`2161–2280`, the per-unit output: the current coefficient, the implied coefficient and the flags)**

- **The "current" coefficient is read at 10 °C (`2176–2178`).** `calculate_unit_coefficient(entity_id, "10", MODE_HEATING)` uses a fixed temperature key. The comment says this is the prediction-time view, but the prediction uses the current temperature bucket, not 10 °C. The value reported as current is therefore not the one in use at most hours.
- **Two coefficient stores are read for the same entity (`2179–2182`).** This code reads `self.coordinator.model.solar_coefficients_per_unit`. The storage save reads `self.coordinator._solar_coefficients_per_unit`. Whether these are the same object is not verified here. This is the attribute-name lesson again.
- **A missing regime reads as all zeros (`2186–2191`).** The comment at `2170–2172` says an unlearned regime must show `{0, 0, 0}`. That is the intended output, but a regime that was never written and a regime learned as zero look the same.
- **The physical-space guard returns the effective value (`2208–2210`).** When the transmittance is 0.01 or less, `implied_physical` is set to the effective value rather than an error. The output is then in a different basis without a flag.
- **The high-saturation flag uses a ratio over `qualifying`, which includes saturated hours (`2221`).** See the pass for `1441–1560`. The literal `0.3` is not named.
- **The instability check ignores components with `|s| ≤ 0.01` (`2224`).** The floor is a literal, and only the S component is tested. A coefficient whose S term is tiny in one window and larger in another is flagged, which may be correct, but the floor is not stated.
- **The divergence flags use ±0.1 kWh (`2229–2232`) and the dominance share is 0.9 (`2241–2246`).** Each is an absolute literal, and none is named as a constant in the response.
- **The shutdown flag uses a count of five (`2256`).** `shutdown_hours >= 5` is an absolute count, so it means more for a short window than for a long one.

**Two hundred and fourteenth pass: `diagnostics.py` (`2281–2400`, the screen stratification, the bias trend and the start of the transmittance sweep)**

- **A failure in the screen-config lookup turns the unit into an unscreened one (`2296–2302`).** The `try` catches `TypeError` and `ValueError`, and falls back to `None`, which makes `screen_config_active` false. Any flag that depends on that state is then suppressed (`2322`, `2462`). A lookup that fails hides the flags of a screened unit, and the response does not say why.
- **The trend needs ten hours in each extreme (`2324–2325`).** The literal `10` is not named, and the same unit with nine hours in one extreme reports no trend.
- **The gap threshold is 0.05 kWh, and the flag names are correct (`2337–2349`).** The comment records that the names were swapped before the 1.3.3 fix. The current names agree with the sign.
- **The sweep needs twenty tuples (`2359`).** The minimum is a literal. The candidate list `0.05–0.25` (`2360`) is fixed, so the sweep cannot look outside that range.
- **The screen-config branch disagrees with the flag (`2361`, `2379–2381`, `2302`).** The flag `screen_config_active` is false when the lookup returns `None`. The sweep at `2379–2381` treats `cfg is None` as screened in all three directions. The flag says the unit is unscreened and the sweep acts as if it is screened. Whether `screen_config_for_entity` can return `None` is not verified.
- **The transmittance guard returns the input (`2382–2384`).** `p_s = eff_s / t if t > 0.01 else eff_s`. This is the same guard as in `2208–2210`, and it returns the effective value in place of a potential when the transmittance is near zero.

**Two hundred and fifteenth pass: `diagnostics.py` (`2401–2520`, the sweep's residual, the best candidate and the inequality replay)**

- **A candidate with no solution is skipped without a reason (`2400–2401`).** `_solve_normal` returns `None` for a singular system, and the loop continues. If every candidate is singular, `results` is empty, the `if results:` block at `2425` is not entered, and `sensitivity` stays `None`. The response carries a null with no explanation.
- **The "boundary" flag cannot fire at the grid edge (`2464`).** The flag is raised when the best candidate is more than 0.04 from 0.08. The best candidate at the lowest value, 0.05, is 0.03 from 0.08 and is not flagged, even though it is at the edge of the grid and the true optimum may lie below it. This is the boundary-optimum problem, in a sweep whose range is fixed.
- **The uniform-result tests use absolute tolerances (`2437–2445`).** The RMSE tolerance is 0.01 kWh and the coefficient tolerance is 0.001. Both depend on the unit of the data.
- **The informative test uses slider variance (`2449`).** `corr_var >= 40.0` is in percentage points and is a literal.
- **The inequality coefficient is read by truthiness (`2478–2480`).** A regime whose components are all zero counts as "no update", which is correct, but it cannot distinguish "not updated" from "updated to exactly zero". The comment at `2469–2471` says absence means no update.
- **The split delta is `None` when the denominator is 0.001 or less (`2499–2510`).** The threshold is an absolute literal. A heating-only install with a tiny cooling default shows a divergence close to 100 %, not "none".

**Two hundred and sixteenth pass: `diagnostics.py` (`2521–2640`, the Tobit call, the failure record and the live-learner block)**

- **The Tobit call is wrapped and its failure is recorded with its class and message (`2523–2541`).** The comment says a bare label once hid a `NameError` for weeks. This is the right design: the exception is kept, the caller gets a usable record, and the diagnostic never breaks the response. It is the best example in this file of the failure-reason lesson.
- **Absent Tobit fields default to the safe value, but not to the same one (`2544–2552`).** `converged` defaults to `False`, which is fail-closed. `censored_fraction` defaults to `0.0`, which is a measured zero, and `n_eff` defaults to `0.0`. The same zero-versus-missing pattern from the learner appears here.
- **`in_cold_start` is true for any fit that did not converge (`2586–2592`).** The field is meant to mark a fit with too little data. It is also set for a fit that ran out of iterations or failed on a singular step, so the name does not match what the field tests. This adds to the overloaded-meaning finding in the learner's cold-start path.
- **Samples are read by position (`2579–2580`).** `s[4]` is the censor flag. The tuple layout is implicit in the position, which is the tuple-position lesson for stored samples.
- **The solar model version defaults to the current one (`2606–2608`).** A stored block without a version is reported as current. This is the same fail-open default found in the restore (`storage.py:1938–1940`).
- **`n_eff` defaults to the uncensored count (`2595`).** When the last step carries no `n_eff`, the uncensored count is reported in its place. The two quantities are not the same, and the reader cannot tell which one was given.

**Lessons added this pass**

- **A dedupe key must be the instant, not the string.** The full-mode import dedupes on the timestamp text (`storage.py:2707–2708`), while the weather-only merge joins on the UTC instant (`storage.py:2520–2526`). The same instant can be stored twice.
- **Name the default key for a lookup, or do not supply one.** `temp_key` falls back to `"10"` (`diagnostics.py:1542`, `2177`). A stale row is then scored at 10 °C without a flag.
- **A guard that returns its input in another basis hides the change.** Returning the effective value when the transmittance is tiny (`diagnostics.py:2208–2210`, `2382–2384`) gives a number in the wrong basis with no flag.
- **A sweep whose best value sits on the edge of its grid must be flagged as a boundary, not measured by distance from a default.** The flag at `diagnostics.py:2464` cannot fire at 0.05.
- **Record the exception, and say what the field tests.** The Tobit wrapper records the class and message (`diagnostics.py:2532–2541`), which is the pattern to copy. The `in_cold_start` field tests more than its name says (`diagnostics.py:2586–2592`).

**Two hundred and seventeenth pass: `diagnostics.py` (`2641–2770`, the Tobit gate state and the inactive-unit collapse)**

- **The scope test is written two ways.** `in_scope` treats an empty `scope_list` as "all units" (`2645`), and `in_scope_override` reports `None` for the same case (`2652–2654`). The reader gets an `override` label only when the list is non-empty, so "no override" and "override says no" are different fields. This is the missing-scope-means-all pattern.
- **A legacy field is kept as an alias of the new one.** `allow_listed` is set to `tobit_routed` (`2661`), and the comment says the name is kept for consumers that read the pre-1.3.5 meaning. The alias now means something other than its name. Any consumer that still reads it as an opt-in will misread routed units.
- **The inactive test ignores the sensitivity of the unit.** A unit is inactive when every coefficient is below `1e-6` and there are no saturation, shutdown or flags (`2682–2690`). The threshold is absolute, in coefficient units. A coefficient scaled by a different unit could pass or fail the test for reasons unrelated to the building.
- **The collapsed record keeps the gate status, the full record does not.** The collapse keeps `live_tobit_state` with counts only (`2714–2727`), and the comment at `2705–2713` says the gate fields must survive. This is a deliberate split, and the test that checks it would need to cover the inactive branch too.

**Application to us:** an absolute "is zero" test on a coefficient is the same as the absolute-threshold lesson. Any "unit is idle" check in our code should be relative to the unit's own scale.

**Two hundred and eighteenth pass: `diagnostics.py` (`2771–2880`, the battery-health block and the calibration constants)**

- **The `saturation_pct` default is zero, not missing (`2749`).** A unit with no qualifying hours reports `0.0` percent saturated. A reader cannot tell "not saturated" from "no data". The `temporal_bias` means (`2758–2759`) correctly use `None` for the same case.
- **The battery bias thresholds are reported next to the result (`2796–2798`).** `min_hours_for_assessment` and both bias thresholds are written into the block, so a reader can see the gate that produced the assessment. This is the right pattern.
- **The decay grid is hard-coded in the function (`2850`).** `DECAY_GRID` is built inside `diagnose_solar` rather than in `const.py`, so a change to the grid is not visible in the constants file. The comment at `2851–2871` explains the pin.
- **`K_GRID` is pinned to one value (`2872`).** The retired feature keeps its tuple shape and surface keys, so the decay fit is labelled as conditional on `k = 0.0`. The comment says why: a joint argmin that offered a k the install would lose on restart had been written back.

**Application to us:** a retired parameter should be pinned, not deleted, and its keys should stay in the output. Our output should say which value a fit was conditional on.

**Two hundred and nineteenth pass: `diagnostics.py` (`2881–3010`, the post-sunset window and the counterfactual replay)**

- **`k_live` is coerced at the read site (`2895–2897`).** The comment gives the reason: a string value makes `changed` permanently true against a float grid. The note says the four reads of the attribute all go through `_coerce_scalar`, which makes the guard a consistency check and not a defence against bad input.
- **The post-sunset and morning windows come from the raw signal (`2926–2942`).** The windows use `raw > 0.01`, not the post-battery factor, because the battery carries residue across midnight. This is the right signal for a window that is meant to show battery charge.
- **The replay is counterfactual, not a refit (`2976–3007`).** The alt residual is `(actual − expected) + (alt_release − live_release)`. With `alt = live` it reduces to the logged residual exactly. The comment says that property is what makes the comparison fair.
- **`n` is candidate-independent, so the minimum-hours check is safe (`3025`).** `n` depends only on the window, so the `continue` for an unqualified sweep is the same for every candidate. The check is right, but a reader has to know that the count does not change inside the loop.
- **A `1e-6` margin guards the argmin (`3033`).** The comment says it is for float equality in selection, and the significance gate handles the question of whether the margin is worth reporting. The split is clear.

**Two hundred and twentieth pass: `diagnostics.py` (`3011–3130`, the tail and morning surfaces and the paired significance input)**

- **The morning surface is read-only (`3038–3057`).** It uses the same grid and the same replay, scored over the rising-sun window. The comment says the recommendation is driven by the post-sunset surface only, and the morning result is a diagnostic. The split is consistent with the summary.
- **The live RMSE is computed by the same replay path (`3065–3070`).** The comment at `3059–3064` says so, which makes the comparison with the grid point exact even when the live decay falls between grid points.
- **The disagreement lookup uses a string key rebuilt from the best pair (`3081–3084`).** The key `f"{best[0]},{best[1]}"` matches the surface key only because the same float objects are used. A change to the rounding in one place would break the lookup silently, and the code returns `None` rather than an error.
- **The paired test uses index-aligned residuals (`3125–3129`).** `live_residuals` and `best_residuals` come from the same window in the same order. The comment at `3131–3149` does not state this, and the pairing is only valid because `_replay_score` keeps iteration order fixed.

**Two hundred and twenty-first pass: `diagnostics.py` (`3131–3260`, the evidence test, the withholding chain and the calibration block)**

- **Three conditions withhold the recommendation, in a fixed order (`3212–3219`).** The order is `requires_k_change`, `windows_disagree`, `optimum_at_sweep_boundary`, then `below_noise_floor`. The first condition that holds is reported, so a window that disagrees hides a noise-floor result. This is documented in the code, and it is the right design: a single reason per payload.
- **`decay_at_boundary` tests the grid's ends (`3156–3158`).** The check is `best[0] in (0.50, 0.95)` and is gated on `changed`. This is correct for the decay grid. It does not flag a flat surface whose minimum is inside the grid, and the comment at `3151–3155` says so.
- **`significant` is read as a key of the paired test's result (`3217`).** `significance["significant"]` is read directly. When the test declines (`declined_reason` is `too_few_paired_hours`, as `3147–3149` shows), it is not established that the key is always present. Unverified: whether `paired_loss_improvement` always returns `significant`.
- **The raw argmin is kept next to the withholding reason (`3204–3206`).** The comment says `recommended_decay` is the raw argmin and that the reason sits beside it. This is the right design, and it matches the lesson in pass 221.

**Two hundred and twenty-second pass: `diagnostics.py` (`3261–3400`, the apply gate and the carry-over sweep setup)**

- **The apply path writes decay only (`3263`, `3277–3280`).** The comment at `3264–3276` says `battery_thermal_feedback_k` was dropped because a k written at runtime is stripped on restart while the decay survives. A single write that mixes a retained value and a stripped value leaves the pair inconsistent after a restart. Writing only the value that persists is the fix.
- **The apply gate reads the withholding chain (`3250–3261`).** The apply is skipped when a reason is set, and `apply_skipped_reason` is reported back. A user who passed the flag sees why nothing changed.
- **The carry-over sweep is labelled as observability (`3294–3298`).** The comment says its verdict does not raise `any_action`. The sweep still searches k, and the comment says it is the evidence base for the retirement. This is a clear split between a research sweep and an action.
- **Trajectories subtract a common input (`3333–3338`).** Each k candidate replays the state with `(impact_raw + feedback)`. The delta in the next block removes the `impact_raw` term, so only the feedback term reaches the residual. The derivation is correct, but the reader has to see that the cancellation is what makes the delta correct.

**Two hundred and twenty-third pass: `diagnostics.py` (`3401–3530`, the per-cell residuals and the optimum)**

- **The sweep's baseline is the live k, not the k = 0 corner (`3340–3359`).** The comment explains the reason in detail: the logged prediction already includes the live release, so an anchor at 0 scores the live value as a change. Anchoring at the live value makes the live candidate reproduce the logged residual exactly.
- **The baseline is rounded before it is compared (`3458–3468`).** The candidate RMSEs are rounded to four places, so a raw baseline can lose a tie by up to `5e-5`, which is 50 times the `1e-6` margin. The code rounds the baseline first. The comment shows that a tie produced a spurious change on a window with no wasted solar.
- **Cells with no temperature bucket are kept in the global only (`3398–3400`).** The `global` aggregate includes the transition cells and the per-cell table does not. The comment at `3372–3374` says so.
- **Index alignment is stated where the lists are built (`3424–3431`, `3439–3442`).** `global_residuals` is appended before the `continue`, so every candidate's list has the same length and order. The comment says so, and the pairing depends on it.

**Two hundred and twenty-fourth pass: `diagnostics.py` (`3531–3660`, the per-cell table, the feedback summary and the screen and temporal blocks)**

- **A missing baseline cell becomes a measured zero (`3524–3525`).** `base_cell` defaults to `{"n": 0, "rmse_kwh": 0.0}`. For a cell that exists only at the optimum, `delta_rmse_kwh` equals the optimum's whole RMSE. The `thin_sample` flag is set (`3532`), but the delta is not blanked. A reader who looks only at the delta sees a large change in a cell the baseline never measured.
- **The per-cell table is dropped from intermediate candidates (`3544–3546`).** The comment says the baseline and optimum are the only actionable rows. The filter compares against the same two keys that the table uses, so the two cannot disagree. The earlier version used the literal `"0.0"` and was wrong on a live k above zero, and the comment says so.
- **The boundary flag compares with the live k, not with zero (`3576–3580`).** The check is `best_k != k_live_sweep` and `best_k == k_candidates[-1]`. This is right, and the comment at `3568–3575` gives an observed case where a monotone sweep reported `1.0` as an optimum.
- **The improvement is rounded after subtraction, and `+ 0.0` removes the negative zero (`3611`).** The comment says `-0.0` reads as a regression. This is a small, correct detail.
- **The notes field claims the sweep reports the transition zone (`3635–3641`).** The text says the transition cell carries "the strongest signal for the headline symptom on high-BP installs". This is an expectation in the text, not a result the code computes. It should be labelled as a hypothesis.
- **The screen-impact flag is an absolute difference (`3655`).** `abs(mean_closed − mean_open) > 0.1` is a fixed kWh threshold, the same absolute-threshold pattern as in pass 191.

**Two hundred and twenty-fifth pass: `diagnostics.py` (`3661–3800`, the hour curve, the context block, the per-unit thresholds and the verdicts)**

- **Temporal bias needs more than five samples per unit (`3659–3660`).** Units with five or fewer morning or afternoon hours are left out of the global mean. The per-unit block reports `None` for the same case, so the two blocks agree on the rule.
- **The hour curve covers 6 to 18 only (`3664`).** Hours outside the range are never reported. This matches the solar window, and it is a choice, not an oversight, but the output does not say so.
- **The context block reads the screen and the constants (`3682–3697`).** It reports the screen config, the transmittance constant and the decay. This is the right design for a remote analyser: a payload should carry the configuration that produced it.
- **The per-unit thresholds fall back silently to the global values (`3710–3722`).** `method` says `"fallback"`, and `calibrated_value` is `None`. The fields are clear, and the summary does not count how many units use the fallback.
- **A missing calibration key returns a verdict with an unknown reason.** `battery_feedback_verdict` gets `bf_sig.get("significant", False)` (`3763`). A missing key counts as not significant, which is the fail-closed choice. The verdict is therefore "no action" for a test that did not run. The verdict should say so.
- **The `current_k` default is zero (`3764–3766`, `3769`).** The `baseline_k` lookup falls back to `current_k` and then to zero. The payload can report `0.0` for an install that is running a different value when both keys are missing.

**Two hundred and twenty-sixth pass: `diagnostics.py` (`3801–4006`, the battery-decay summary, the top-level verdict and the return payload)**

- **The summary keeps the raw argmin and the reason together (`3817–3819`).** `recommended_decay` is shown with `recommendation_withheld_reason` and the bias assessment, so the reader can see why the number is not advice. The comment says the two must not be separated.
- **The bias assessment is a separate operand of the top-level verdict (`3920–3933`).** The comment at `3895–3910` records an earlier revision that dropped the operand. Dropping it hid a well-sampled bias whenever the sweep ran. The code now routes it through a named operand.
- **The 4D readiness check raises the top-level verdict in two places (`3934–3935`).** `enabled_but_unsupported`, `enabled_but_not_ready` and `ready_to_enable` each raise `review_recommended`. The comment at `3859–3894` says `ready_to_enable` is absorbing: the only exit is enabling the flag. It accepts that a user who declines 4D stays at `review_recommended`.
- **The summary's `any_action` is a long OR of mixed sources (`3923–3936`).** Some operands are verdict strings, some are lists, and some are booleans. The `battery_decay_summary["verdict"]` is checked twice: once with `startswith("consider_")` and once in the tuple `("too_fast", "too_slow")`. A verdict that is both would count once, so the duplication is harmless but confusing.
- **`battery_decay_summary` has three shapes (`3801`, `3828`, `3834`).** Each branch sets different keys. A consumer that reads `recommended_decay` on the third branch gets `KeyError` with indexing or `None` with `.get`. The payload is not uniform.
- **`battery_feedback_summary["verdict"]` is read directly (`3926`).** It is set in both branches (`3774`, `3783`), so the direct read is safe today. A future change that drops the key from one branch would fail here.
- **The return payload has four separate reports at the end (`4000–4004`).** The shadow, divergence, blast-radius and GHI agreement reports are not in the summary's `any_action`. A problem reported only in one of them does not raise the top-level verdict.

**Two hundred and twenty-seventh pass: `diagnostics.py` (`4007–4059`, the start of `_compute_dni_dhi_source_mix`)**

- **The source-mix report counts daylight hours only (`4044–4054`).** `solar_factor > 0` is the test. The docstring at `4022–4029` says the label never emits `"no_sun"`, so an unfiltered count would show every night hour as synthetic. The filter is essential, and the docstring says why.
- **Unlabelled rows are counted, not dropped (`4031–4034`, `4056–4058`).** An install upgraded from an older version shows a thin mix as thin. The docstring says this is deliberate.
- **Parse failure and zero are counted together (`4048–4054`).** A `solar_factor` that cannot be parsed is counted as night, and so is a zero. The name `n_night_skipped` covers both. A corrupt row is therefore counted as a night hour without a separate count.
- **The date cut-off compares strings (`4038`, `4046`).** `ts[:10] < cutoff` relies on ISO date strings. A timestamp with a different format sorts incorrectly. The same string-comparison pattern is in the import (pass 205).

**Application to us:** count labelled and unlabelled rows separately, and count night rows separately from parse failures. Both are cheap and each prevents a misleading mix.


**Two hundred and twenty-eighth pass: `diagnostics.py` (`4060–4235`, the end of the source mix and the DNI/DHI outage alert)**

- **One flag, two readers.** The source mix reads `experimental_4d_primary` with `bool(getattr(...))` (`4080–4082`). The outage alert reads the same attribute with `... is True` (`4159–4161`). A value that is truthy but not `True` (for example the string `"yes"`) enables the mix and disables the alert. The two reports can disagree about whether 4D is on.
- **The outage window is counted in daylight hours, and the age bound stops the walk.** The walk stops at the first entry older than `REPAIR_DNI_DHI_OUTAGE_MAX_AGE_DAYS` (`4182–4190`). Entries without a timestamp do not stop it, so one malformed row does not end the walk. The comment at `4178–4181` says this.
- **Unlabelled rows are skipped, not counted (`4197–4201`).** The comment gives the reason: counting an unlabelled hour as healthy would hide an outage. The same choice was made for the source mix, where unlabelled hours are counted separately (pass 227). Two reports take two positions on one kind of row.
- **Asymmetric thresholds make the verdict sticky (`4228–4233`).** The raise bar is 0.10 and the clear bar is 0.50. Between them the verdict is `hold`, and the caller keeps the state. The comment at `1018–1021` of `const.py` says why, and the code matches it.

**Application to us:** read each config flag through one helper, so two reports cannot disagree about whether a feature is on. The sticky-hold pattern is worth copying for any alert that a flaky input can toggle.

**Two hundred and twenty-ninth pass: `diagnostics.py` (`4236–4341`, the 4D readiness combiner)**

- **The combiner is three-valued, and a definite False outranks an unknown (`4306–4311`).** The comment at `4292–4304` gives the reason: the learning half can say "4D is untrained" in the first days, while the input half is still short of hours. A definite result on either side decides the answer.
- **Readiness is checked only in the currently active regime.** The `accepted_limitation` text (`4332–4339`) says so and gives the cost: about five sunny hours of zero solar for a unit that switches regime. The limitation is written into the payload, so a reader sees it.
- **`ready_to_enable` is an absorbing state.** The comment at `4254–4259` and `3884–3894` says the only exit is enabling the flag. A user who declines 4D stays at `review_recommended` indefinitely. This is accepted, and the comment says so.

**Application to us:** a readiness gate needs a definite-False rule, so that missing history cannot hide a real fault. Write the accepted limitation into the output, as this code does.

**Two hundred and thirtieth pass: `diagnostics.py` (`4342–4518`, the GHI signal agreement)**

- **The skipped-unstable counter is uneven.** The count increments only when `no_cloud_ref > 1e-6` (`4436–4438`). Hours that fail the potential-factor check are counted only when the reference is non-zero, and hours that fail `ghi_clear < 1.0` (`4420`) are not counted at all. The payload reports the count as "skipped unstable", which is not the same as all skipped hours.
- **Three thresholds for one comparison.** The pair gate is `len(pairs) < 30` (`4468`), the per-regime gate is `n < 5` (`4479`), and the clear-sky floor is `ghi_clear < 1.0` (`4420`). Each is absolute and none is documented as a unit choice.
- **The regime rule has two branches with different units.** With cloud cover, the cut-offs are 30 and 70 percent (`4444–4449`). Without it, the cut-offs are 200 and 700 W/m² (`4451–4456`). Both are documented in the docstring. A reader comparing regimes across entries with and without cloud data is comparing two rules.
- **Two parsers for one field.** This function parses the timestamp with `dt_util.parse_datetime` (`4403`). The shadow report parses the same field with `datetime.fromisoformat` (`4612`). For a timezone-naive string the two can give different aware or naive values. Unverified: whether the two parsers differ on the strings this log writes.

**Application to us:** count each skip reason separately, so the payload can say which gate removed the data. Use one timestamp parser for one field.

**Two hundred and thirty-first pass: `diagnostics.py` (`4519–4780`, the DNI/DHI shadow report: the input reads and the samples)**

- **Missing solar vectors become zero (`4606–4608`).** A `None` or empty string in `solar_vector_s/e/w` is read as `0.0`. The comment says this is for the legacy log without the W column. A legacy row therefore becomes a measured zero in the regression input, and the all-zero skip at `4679–4687` then drops some rows and keeps others.
- **Regime rules are restated.** The shadow report sets overcast below 50 W/m² and clear above 400 W/m² with DHI/DNI below 0.3 (`4688–4693`). The divergence report uses the same rule (`5731–5736`). Two copies of one rule, with no shared helper, and the docstring says they match.
- **The actual-target gate reads the mode dict with a default of empty (`4706`).** `unit_modes = entry.get("unit_modes") or {}` means an absent dict is read as no cooling unit. This is the right direction for the house gate, and the per-entity gate uses the explicit heating default (`4760`). The two gates handle an absent mode differently, and both are documented.
- **The target uses the first sample's base bucket for the house and the same key for each unit.** `correlation_data` is read by `temp_key` and `wind_bucket` (`4710–4714`). The per-unit base reads the same two keys (`4768–4772`). A bucket missing for one unit and present for the house gives a house target without a matching unit target.
- **Two sun-position parsers, one with a half-hour offset.** The shadow adds 30 minutes to the timestamp before the sun position (`4615`), as the GHI report does (`4408`). The comment does not say why the half hour is used. Unverified: whether the logged timestamp is the start or the end of the hour.

**Application to us:** a missing sensor input should be a missing sample, not a zero. Our regime and target rules should live in one helper.

**Two hundred and thirty-second pass: `diagnostics.py` (`4780–5020`, the per-entity target and the least-squares fit)**

- **The regression has no intercept, and the ridge is relative to the mean diagonal (`4815–4818`).** The ridge is `max(1e-9, 1e-6 · mean_diag)`. The comment says it handles degenerate geometry at noon. A column that is always zero (a facade that never gets sun) keeps a diagonal of the ridge alone, so its coefficient is forced to zero. The fit does not fail, but the zero is not labelled as "no data".
- **The singularity test is an absolute pivot (`4824–4825`).** `abs(a[i][i]) < 1e-12` is absolute. With the ridge in place it should rarely fire, so the fallback to `singular_design_matrix` is a rare path, and it is not tested in the payload.
- **Only two exceptions are caught for the screen lookup (`4996–5004`).** `screen_config_fn(eid)` is wrapped for `TypeError` and `ValueError`. Another exception ends the whole `diagnose_solar` call. The lookup is called once per entity, so one bad entity hides every later block.
- **The learned flag comes from a second store.** `_entity_has_learned` reads `_solar_coefficients_per_unit` (`4960–4971`). This is the same second store that pass 213 flagged. The aggregation trusts a flag that the fit's own coefficient store sets.

**Application to us:** a per-entity loop should catch and report each entity's failure, not let one fault stop the report. Also, a regression with a permanently zero column should say so in its output.

**Two hundred and thirty-third pass: `diagnostics.py` (`5020–5260`, the filtered aggregate, the signal agreement and the start of the per-unit min-base calibration)**

- **The filtered aggregate is an hours-weighted mean of per-entity percentages (`5021–5040`).** A unit with 500 hours counts five times as much as one with 100, regardless of how precise either fit is. The comment says the aggregate drops default-coefficient entities. It does not say that the weighting is by hours.
- **`_pearson_rmse_bias` uses a 5-hour floor, which is one of several (`5072–5073`).** It returns `None` values below five hours. The per-regime floor in the shadow is also five (`4479`), and the divergence report uses `_MIN_REGIME_HOURS = 5` (`5653`). The three floors are separate constants with the same value.
- **The calibration docstring lists its safety guards in order (`5135–5155`).** The order is: minimum log age, minimum samples, the ratio guard, the ceiling and the rate clamp. The code runs them in the same order (`5196–5320`).
- **Idle hours are excluded from the calibration sample on purpose (`5221–5227`).** The comment explains that `unit_hour_reported_kwh` would add zeros and collapse p10 to zero. This is the same reason the shadow uses the helper and calibration does not, and the comment records the choice.

**Application to us:** name the weighting in any aggregate of per-group results, and write the floor each group has to pass.

**Two hundred and thirty-fourth pass: `diagnostics.py` (`5260–5500`, the end of the calibration and the start of the base-model shadow)**

- **The nearest-rank p10 is justified in the code (`5246–5252`).** The comment says `math.ceil` is needed, not `round`, and names the cases where `round` and Python's banker's rounding give the wrong rank. This is an explicit correctness note, and it is worth keeping.
- **The ratio guard's median is the upper median for even counts (`5280–5281`).** `sorted_dark[len // 2]` is not the standard median for an even `n`. The effect is small, but the guard's name says median.
- **A prior of zero behaves as no prior, through truthiness.** The log message uses `f"prior {prior:.3f}" if prior else "global fallback"` (`5292`, `5305`). A stored prior of exactly `0.0` is reported as a fallback. The clamp at `5314` also tests `prior > 0.0`, so the two agree, but neither is written as an explicit `None` test.
- **The base-model shadow seeds a missing bucket with zero (`5445–5449`).** `correlation_data.get(temp_key, {}).get(wind_bucket, 0.0)` gives a seed of `0.0` when the bucket is absent. The comment at `5433–5435` says both simulations start from the cell's current live value, which is not true for a missing cell. The first EMA steps then start from zero, and the step RMS in the headline includes them.

**Application to us:** a seed for a learning simulation should come from the same source as the live learner, or the comparison should be skipped for that cell.

**Two hundred and thirty-fifth pass: `diagnostics.py` (`5500–5740`, the shoulder headline, the 4D replay and the start of the divergence report)**

- **The headline defaults to zero when no cell qualifies (`5527–5531`).** `bucket_drift_rms_3d_shoulder` and the 4D equivalent are `0.0`, while `shoulder_ratio` is `None`. A reader sees a drift of zero, which means "measured as flat". The count of zero cells is also reported, so the reader can tell the two apart, but the drift value itself reads as a result.
- **A missing screen method falls back to no screens (`5605–5609`).** `screen_cfg` is `(False, False, False)` when the coordinator has no `screen_config_for_entity`. A coordinator without the method replays every unit as unscreened, with no warning. The fallback is the least-protected value, which is a fail-open choice.
- **The replay returns zero for "below horizon" and `None` for every other failure (`5569–5571`).** This is the correct split, and it matches the pass on `reconstruct_hour_inputs` from earlier. The broad `except Exception` at `5620–5621` returns `None` for any failure in the potential call, which hides a code fault as "no data".
- **Unverified: a `None` unit mode.** The divergence report passes `unit_modes = entry.get("unit_modes") or None` (`5739`) to `calculate_total_power`. An absent dict becomes `None`, and the code does not say whether `None` means all-heating. This was not checked in `statistics.py` in this pass.

**Application to us:** a replay that falls back to "no screens" when a method is missing should log the fallback. A broad `except` in a replay should count its failures.

**Two hundred and thirty-sixth pass: `diagnostics.py` (`5740–5980`, the rest of the divergence report and the start of the blast-radius report)**

- **The divergence verdict makes a positive claim on too few hours (`5868–5879`).** The undersampled check requires 5 hours per regime (`5864–5867`). When the broken regime has at least 5 but fewer than 20 hours, the code reaches the `else` at `5878–5879` and returns `"4d_diverges_modestly_on_broken"`. A verdict of divergence is therefore given on five hours, although the threshold verdict needs twenty. The name says the 4D model diverges, and the data does not support that.
- **Timestamp failures are counted with missing fields (`5716–5718`).** A row whose timestamp does not parse is added to `n_skipped_missing_fields`. The payload's "no hours with DNI/DHI" reason (`5799`) then covers a timestamp fault too.
- **The relative delta uses a fixed floor of 0.1 kWh (`5842`).** `max(global_base, 0.1)` is an absolute floor, in the same way as the other kWh thresholds. For a building with a global base under 0.1 kWh the relative delta is inflated, but the code never reaches that case in practice.
- **A `None` solar-wasted value crashes the blast-radius report.** `solar_wasted = entry.get("solar_wasted_kwh", 0.0)` (`5974`) returns `None` when the key is present with a `None` value. The shoulder check at `5975–5976` does not test it. The next line `float(solar_wasted)` (`5982`) raises `TypeError`, which is not caught in the loop. A log with one such row ends the whole report. The same call appears in the matched-baseline walk (`6074`).

**Application to us:** a verdict that makes a claim needs the same sample floor as the claim it names. A key that can hold `None` should be read with a default that handles `None`, not with a default that applies only when the key is absent.

**Two hundred and thirty-seventh pass: `diagnostics.py` (`5980–6118`, the end of the blast-radius report)**

- **The matched 3D baseline replays the 4D solar total a second time for each hour (`6077–6079`).** The main loop has already replayed it, and the code does not keep the result. The comment at `6055–6060` says the mapping was not kept and the walk was repeated. The cost is paid on every shoulder hour with saturation.
- **The verdict has a relative threshold of 0.20, and a reference that is an absolute kWh floor (`6086`).** `ref > ENERGY_GUARD_THRESHOLD` is 0.01 kWh. A reference that small is never tested for relative improvement, and the verdict is `no_meaningful_difference`. This is a sensible guard, and the payload does not show that it fired.
- **Two medians are named the same way.** `_median` is defined in both the divergence report (`5810–5818`) and the blast-radius report (`6025–6033`). The two copies are identical. A change to one would not reach the other.
- **The 3D unclamped variant can be negative, and the residual is taken without a floor (`5988`, `6010`).** The comment at `5912–5914` says so. The 4D clamped variant is floored at zero (`6007`). The two variants therefore compare different quantities, and the median of the 3D unclamped variant is not directly comparable with the 4D clamped one.

**Application to us:** a verdict should be on the same population for every variant it compares. Where a variant can go negative and another cannot, the report should say so.

**Two hundred and thirty-eighth pass: `explanation.py` (`1–240`, the regime map, the impact categories and the start of the day analysis)**

- **Unknown regime labels fall back to heating, on purpose (`58–71`).** The docstring says that silently withholding every claim on an unknown label would hide why the prose is bare. The fallback is a deliberate fail-open choice, and it is documented. The `mixed` label is the one case that withholds claims, and the docstring says so.
- **`CategoryThresholds` copies its values from `const.py` at import (`80–97`).** Each attribute is bound to the constant's value when the class is defined. A test or a runtime override that patches `const` does not reach the class.
- **An unknown wind bucket is treated as normal (`117–121`).** The comment says "treat as normal for now or ignore". An unrecognised bucket therefore reads as no wind impact, and the reader is not told.
- **The current day's wind bucket defaults to normal (`236`).** `day_data.get('wind_bucket', 'normal')` supplies a calm bucket for the current day when the key is absent. The baseline path (`239–247`) carefully refuses to do this, and the comment explains why. The two sides of the comparison are treated differently.
- **The wind-speed test uses a literal of 2.5 m/s (`266–267`).** The moderate-wind rule for a same-bucket day is hard-coded. It is not in the threshold class.

**Application to us:** a fallback for a missing category must be written in the same way on both sides of a comparison. Thresholds that are not in the threshold class are hard to find when tuning.

**Two hundred and thirty-ninth pass: `explanation.py` (`240–480`, the causality check and the period analysis)**

- **`analyze_period` averages over a shorter list than it totals (`365–398`).** The total uses every day in `period_days` (`365`), or the supplied total. The averages use only the first `valid_days = min(p_len, b_len)` days (`386–398`). When the two lists differ in length, the total and the averages describe different populations.
- **Days are paired by position, not by date (`402–404`).** `period_days[i]` is compared with `baseline_days[i]`. The code does not check that the two lists are aligned, and a missing day in either list shifts every later pair. The function has no check on the dates.
- **Causality uses absolute thresholds in three units (`341–349`).** The temperature moderate threshold is 1 °C, the wind relevance is 1 m/s and the solar relevance is 0.5 kWh. The solar threshold in kWh depends on the size of the house, and the wind and temperature ones do not.
- **The causality test requires both the delta and the consumption change to be non-zero, and the sign to match (`335–339`).** A zero consumption change returns neither driver nor contradiction. The result is correct, but it is silent about a flat week.

**Application to us:** pair periods by date, and check that the two lists have the same dates before pairing them. Any "relevance" threshold in kWh should be scaled to the house, or it will mean something different on each install.

**Two hundred and fortieth pass: `explanation.py` (`480–720`, the driver counting and the period characterisation)**

- **Two arms of one branch are identical (`425–435`).** The `if delta_kwh > 0` branch and its `else` append the same three checks in the same order, and the comments above them describe different weather. The branch is dead in effect: the sign of the consumption change does not change which driver is recorded. The comment at `427–432` says the drivers differ, and the code does not do that.
- **The variable `count` is reused for two things (`475`, `546`).** The loop at `474–495` sets `count` as the affected-day count. The characterisation reads `count` again at `546`. The later assignment resets it before use, so the result is correct, but the name is misleading.
- **The period regime votes exclude idle days, and the vote is a set (`458–468`).** The docstring says an idle day should not vote, because it would collapse the period to "mixed". The code does exclude it. Two or more distinct regimes give `mixed`, which suppresses every directional claim.
- **The contradiction margins are asymmetric, and the code says so (`516–522`).** Temperature and wind need a margin of 0.5 in the expected direction, and solar needs −0.5. The comment says this predates the change and is kept on purpose.

**Application to us:** when two branches produce the same output, one of them is probably wrong. Name each variable for one thing.

**Two hundred and forty-first pass: `explanation.py` (`720–946`, the day and period sentences, the driver text and the weather context)**

- **Three different "similar consumption" thresholds for one idea.** The period comparison says similar at 5 kWh (`673`), the day comparison at 3 kWh (`688`), and the summary at 1 kWh (`867`). Each is an absolute kWh figure. A user reads the same difference as "similar" in one sensor and as a change in another.
- **The day wording uses the weather's own sign, but the driver text can still fall back to the consumption sign (`817–824`).** `_get_factor_description` uses `delta_kwh` only when `weather_delta` is `None`. The comment says the fallback is "legacy" and "equivalent under heating". Under cooling it names a hot week as cold, as the comment at `810–812` admits. All current callers pass `weather_delta`, so the fallback is for callers that are not updated.
- **The weather context has two wind literals and one configured threshold (`936–940`).** `wind >= 3.0` is hard-coded twice, and the high and extreme thresholds come from the arguments. The 3.0 is not in the threshold class, so changing the configured threshold does not move the breezy cut-off.
- **`format_last_hour_summary` compares a possibly missing kWh (`901`).** `if kwh <= 0` raises `TypeError` for `None`. The caller is expected to pass a float. The other formatters use `or 0.0` for missing values, so this one is the odd case.

**Application to us:** a "similar" threshold should be written once, with a unit, and shared by every sentence that uses it. A fallback kept for old callers should log that it was used.

**Two hundred and forty-second pass: `switch.py` and `select.py` (the learning switch, the auxiliary switch and the mode selects)**

- **Two write paths for one kind of state.** The learning switch sets `coordinator.learning_enabled` and calls the private `_async_save_data` (`switch.py:64–66`). The auxiliary switch calls the coordinator's public setter (`92`, `97`). The learning write can fail on the save with no catch, and the entity then does not write its state.
- **The mode select's options are the six mode constants, in a fixed list (`67–74`).** The list matches every `MODE_*` constant in `const.py` (`836–841`). A new mode added to `const.py` would not appear in the select until this list is changed, and nothing checks that the two agree.
- **The entity name is read once, at construction (`63–65`).** `state.name if state else source_entity_id` takes the friendly name when the entity exists at setup. If the source is not loaded yet, the name is the raw entity id, and it is not refreshed later. A user who renames the source sees the old name.
- **The extra attributes are rebuilt on every state write (`86–95`).** `heat_source_for` runs each time the entity is written. There is no cache, and the provenance and evidence are recomputed each time.

**Application to us:** a list of allowed options should be generated from the same constants that the logic uses, and checked in a test. Store the friendly name on each update, not once.

**Two hundred and forty-third pass: `const.py` (`1–300`, the defaults, the explanation thresholds, the solar and the learning values)**

- **Two constants with the same value and different roles.** `DEFAULT_SOLAR_MIN_TRANSMITTANCE` (`195`) and `SCREEN_DIRECT_TRANSMITTANCE` (`215`) are both `0.30`. The first is the floor for facades without per-direction screens, and the second is the floor for screened facades. The comments at `188–214` explain both. A tune of one does not move the other, and `solar.py:718` and `721` use them in two different branches.
- **A bump checklist names a constant that does not exist.** The comment at `657–658` lists `COMPOSITE_LEGACY_FLOOR`. A search of the code finds no such name. The checklist is for deciding when to change `SOLAR_MODEL_VERSION`, so a reader who follows it cannot find the constant it names.
- **The same 0.15 kWh default serves two purposes.** `SOLAR_LEARNING_MIN_BASE` (`296`) and `SOLAR_SHUTDOWN_MIN_BASE` (`287`) both equal `0.15`. The comment at `289–293` says they are kept separate on purpose, and each has its own name.
- **Wind thresholds have no unit suffix.** `DEFAULT_WIND_THRESHOLD = 8` (`11`) and `DEFAULT_EXTREME_WIND_THRESHOLD = 10.8` (`12`) carry no unit in the name. The unit is `DEFAULT_WIND_UNIT = "m/s"` (`16`). Other constants in the same block carry a unit in a comment (for example `# °C delta`, `# m/s`).
- **The explanation thresholds have units in comments only.** `DEFAULT_SOLAR_SIGNIFICANT_KWH` and the related constants (`31–32`) say "Daily kWh delta" in a comment. The same kWh values are used in the explanation with an absolute comparison.

**Application to us:** when two constants have the same value and different roles, name each by its role, and give the sharing its own check. A bump checklist should be tested against the code.

**Two hundred and forty-fourth pass: `const.py` (`300–600`, the per-unit gates, the Tobit and plausibility settings, the obstruction fit)**

- **The per-unit calibration constants are documented against real installs.** The comments at `298–312` and at `419–427` name the install, the observed values and the rule for changing the threshold. This is the best-documented block in the file.
- **The obstruction gate's comments record a rejected design.** `OBSTRUCTION_FIT_SSE_IMPROVEMENT_THRESHOLD` (`563–571`) was raised from 0.10 to 0.30 after cosmetic fits passed. The comment says what the lower value let through. The record stops the value from being lowered again without the same evidence.
- **The low and high obstruction ranges overlap by design, and the comment says the windows are independent (`557–560`).** The low range is 5–40 degrees, the high range is 15–70. The comment at `548–556` explains the lower bound. The overlap is intended and does not look like an error.
- **`OBSTRUCTION_LOW_PLAUSIBLE_RANGE` and `OBSTRUCTION_HIGH_PLAUSIBLE_RANGE` share the boundary 20 (`582–583`).** A fit at exactly 20 degrees may pass either range, depending on whether the bounds are inclusive. The comments do not say which. Unverified: how the code compares a value at the bound.
- **`TOBIT_RUNNING_WINDOW` documents its memory cost (`385`).** The comment gives the size per entity and regime. This is a good habit: a buffer's cost is written beside its size.

**Application to us:** when a constant's value was chosen against real data, write the data and the rule in the same comment. Record the value that was rejected.

**Two hundred and forty-fifth pass: `const.py` (`600–900`, the storage version, the solar model version, the attributes, the modes and the heat-source types)**

- **The solar model version and its bump list are the main coupling point.** `SOLAR_MODEL_VERSION = 1` (`664`) is compared with the stored version on load. The bump list at `653–663` names the formulas that must bump it. The list names `COMPOSITE_LEGACY_FLOOR` (`658`), which does not exist (pass 243). A change to the screen floor would not be caught by the list as written.
- **The heat-source classes are split into curve and device (`892–911`).** The comment says the three inferred classes name a curve and cannot be set by hand. `HEAT_SOURCE_FORM_FIELDS` is generated from the user types, so the form and the user list cannot drift apart. This is good design.
- **The curve map has no entry for `unknown` (`912–920`).** The comment at `911` says `None` means unknown. A lookup that uses `HEAT_SOURCE_CURVE[type]` without `.get` raises `KeyError` for `unknown`, because the map has no entry for it. Unverified: whether any caller indexes the map directly.
- **The hysteresis for the heat-source class is explicit (`946–951`).** A first classification needs one passing run. A change of class needs two consecutive runs. A run that cannot classify does not clear the old class. The comment states all three rules.
- **The mode constants are the only six and are listed once (`836–841`).** `MODES_EXCLUDED_FROM_GLOBAL_LEARNING` (`847–852`) is built from them, and the comment at `843–846` says why cooling is not on the list. The comment and the set agree.

**Application to us:** a coupled version constant should be checked by a test that compares its bump list with the constants it names. Keep the form's field list generated from the same list as the logic.

**Two hundred and forty-sixth pass: `const.py` (`900–1167`, the DNI/DHI thresholds, the outage alert, the balance-point calibration and the unit attribution floor)**

- **The 50-hour floor is described as one week, which depends on the season (`981–984`).** The comment says "~1 week of daylight hours is the floor". In December at 60 degrees north, 50 daylight hours is about eight days. In June it is under three. The code counts daylight hours, so the calendar length varies with the season, as the outage comment at `1000–1004` already says for its window.
- **The outage constants say they are starting points (`1023–1027`).** The comment says neither the 0.10 nor the 0.50 bar was checked against a real outage. The honest label is in the code, so the reader does not take them as tuned.
- **The balance-point sweep bounds are wider than the feasible range they are clipped to (`1054–1056`).** The comment at `1050–1051` says the sweep is intersected with the data's own range. The constants therefore give the outer limit, and the real limit comes from the data.
- **Several comments give simulation results as the reason for a value (`1063–1065`, `1075–1077`, `1153–1155`).** The reasons are specific (a 30 % carry-over gives a 1 °C error). They are not checked by the code and they are not in the repository's tests.
- **`BP_CALIBRATION_COP_SLOPE_MAX` has a comment that forbids raising it (`1082–1089`).** The text says a fit at the limit is reported as `nuisance_at_limit`, and a higher limit gave a 21.5 °C suggestion on one install. The comment is a guard against a tempting change, and it names the install's behaviour.
- **`DAILY_UNIT_ATTRIBUTION_MIN_SHARE = 0.9` (`1167`) guards against an unusable split.** A day with less than 90 percent of its energy attributed to units has no trustworthy heating split. The comment names the cause: a day imported from CSV.

**Application to us:** when a constant is a starting point with no real test, label it that way in the code, as this file does. Where a value comes from a simulation, say so and say what the simulation assumed.


**Two hundred and forty-seventh pass: `solar.py` (`300–301`, `470–548`, the gap left by passes 10 and 46)**

- **`calculate_solar_factor` has a second cloud path, and the override is clamped.** A caller can pass `cloud_attenuation_override`. The value is clamped to `[0, 1]` (`solar.py:543`). The default path uses `_kasten_cloud_attenuation(cloud_coverage)` with no clamp in this function. The docstring says the two are bit-identical when the override equals the Kasten value. That holds only if the Kasten function already returns a value in `[0, 1]`, which was not checked.
- **The elevation gate and the azimuth zones agree at their edges.** Zone 1 maps `0–75°` onto a cosine from `1.0` to `0.1`. Zone 2 (`75–90°`) and Zone 3 (`>90°`) give the floors `0.1` and `0.05`. At the cutoff the cosine gives `0.1`, so the zones join with no step.
- **The solar factor is a product of three separate factors.** Elevation, azimuth and cloud each multiply. A zero in any one gives zero. This is why the 4D model needs its own terms for diffuse light: a cloudy hour with a zero direct factor still has a diffuse share that this function never adds.

**Lessons added this pass**

- **A coverage note must match the pass headers.** The "Still not read" block said `solar.py` was read except lines `1–33` and `549–574`. The pass headers also leave `300–301` and `470–548` unread. A coverage claim should be checked against the line ranges, not against the summary.

**Two hundred and forty-eighth pass: `thermodynamics.py` (`201–389`, the per-hour COP, the resmear and the shared smear)**

- **The hour weights and the hour list can have different lengths.** `total_weight` is the sum over every weather hour (`255`, from `209`). The output loop runs over `mpc_data_24h` (`252–253`). If the MPC list is shorter, the dropped hours' weight stays in the denominator, so the written thermal total is less than `total_kwh_th`. Nothing checks the two lengths. The comment at `228–229` assumes alignment. Whether the caller can produce unequal lengths was not checked.
- **A zero electrical total turns the resmear into a COP of one.** When `total_kwh_el` is zero, `mean_ratio` is `1.0` (`302`). Every hour gets COP `1.0` (`305–313`), and `renormalize_to` is `None` (`321`). The thermal energy is then written as electrical energy with no flag. The method label `recovered_cop` does not show this.
- **The ratio threshold is a documented rounding bound.** `RESMEAR_MIN_RATIO_KWH = 0.01` (`264`). The comment at `261–263` says a 3-decimal rounding error is up to 5 % at this value. An hour below either threshold takes the mean ratio (`309–312`). The check needs both values, so an hour with large thermal and tiny electrical energy is treated as unreadable.
- **The class constant sits after a `return`.** `RESMEAR_MIN_RATIO_KWH` is defined after the body of `calculate_synthetic_baseline` returns (`259–264`). It is a class attribute, so it works, but a reader scanning for constants may miss it.
- **The DHW rule is in `_smear`.** A DHW hour still receives its share of the thermal total (`366–371`). The comment gives the physical reason. The rule holds for both the midnight sync and the resmear, because both call `_smear`.
- **`_hour_cop` reads the weather with defaults.** `outdoor_temp` falls back to `balance_point − delta_t` and `humidity` to `50.0` (`327–328`). A row missing both keys gets a COP from the fallback values, with no log.
- **Not checked:** whether `cop_at_conditions` can return zero. A zero there divides by zero at `372`.

**Lessons added this pass**

- **Check the two lists the same way before dividing by their total.** A total built from one list and a loop over another lets a length mismatch drop energy silently.
- **A fallback value that makes a ratio the identity hides a missing input.** A COP of `1.0` makes thermal and electrical energy equal. It should set a flag, or the caller should skip the day.

**Still not read**

- None in the Heating Analytics integration. The clone has 28 Python files (excluding tests) and 45,361 lines. Each file has at least one pass. `thermodynamics.py` is now read in full (passes 29, 71 and 248). Passes 10, 46 and 247 cover `solar.py`.
- Test files (about 63,000 lines under `tests/`): not reviewed.
- Versatile Thermostat: not started (listed for later).


---

### Versatile Thermostat code review

Read from a shallow clone of `jmcollin78/versatile_thermostat` at commit `0860f19` (manifest version 10.6.3). Read in full: `prop_algo_tpi.py`, `ema.py`, `open_window_algorithm.py`, and `auto_start_stop_algorithm.py` (lines 80–190). Read in part: `auto_tpi_manager.py` (about 3,200 lines; the functions cited below). Not read: `tpi_identification.py`, `cycle_tick_logic.py`, `pi_algorithm.py`, and the `feature_*` managers. The `documentation/en/*.md` pages were read through fetch summaries only.

**What it does.** A Home Assistant custom integration (HACS) that turns a switch, valve or climate entity into a managed "virtual thermostat". Features: presets, open-window detection, motion, presence, humidity, timed presets, power and central-boiler management, safety mode, heating-failure detection, auto-start/stop, and Auto-TPI (self-learning of the heating gains). It is a feedback controller, not a building model.

**How it "forecasts" (short answer: it doesn't).** There is no forecast of future temperature and no weather input to the control law. The only forward-looking element is a one-step linear extrapolation in auto-start/stop.

1. **Control law: TPI** (`prop_algo_tpi.py`, `calculate()`): `on_percent = tpi_coef_int · (T_target − T_in) + tpi_coef_ext · (T_target − T_out)`, clamped to [0, 1]. Defaults: `coef_int` 0.6, `coef_ext` 0.01. It is a proportional law with an outdoor feed-forward term. There is no integral term and no lookahead. Thresholds force the output to 0 on overshoot, and take effect only when both `tpi_threshold_high` and `tpi_threshold_low` are non-zero.
2. **Temperature smoothing: EMA** (`ema.py`, wired in `base_thermostat.py:448` and `:2349`). Time-aware alpha, `alpha = 1 − 0.5^(Δt / halflife)`, capped at `max_alpha`. Defaults: halflife 300 s, `max_alpha` 0.5, 3 decimal places.
3. **Slope** (`open_window_algorithm.py`, `add_temp_measurement`): the two-point difference of the EMA temperature over Δt, in °C/h. It is smoothed as `0.2·old + 0.8·new` and rejected if |slope| > 120 °C/h. It is not used until 4 points are seen (`MIN_NB_POINT`). A fake point is added after 30 minutes without a measurement, so a stale gap does not produce a false slope. Slope feeds open-window detection and auto-start/stop.
4. **Auto-start/stop** (`auto_start_stop_algorithm.py:148`): `temp_at_dt = T_in + slope_per_min · dt`, where `dt` depends on level (`DT_MIN`). Heating is turned off when `temp_at_dt ≥ target + 0.5` and the accumulated error (capped at `ERROR_THRESHOLD`) says heat is not needed; turned on when `temp_at_dt ≤ target − 0.5`. The error is scaled by elapsed time over `CYCLE_SEC = 120`. This is a constant-slope extrapolation that ignores heat input.
5. **Auto-TPI** (`auto_tpi_manager.py`). It learns the gains that TPI uses, then runs the same law with them: `power = dir·(T_set − T_in)·K_int + dir·(T_set − T_out)·K_ext + offset` (`_calculate_power_tpi`, line 2030).
   The learning rules imply a simple heat balance, `dT/dt ≈ K_int·P − K_ext·(T_in − T_out)`. This is inferred from the code; the docs do not state it.
   - `_learn_indoor` (line 1027): `loss = K_ext·ΔT_out`; `adjusted_theoretical = min(target rise, capacity-limited rise)`; `ratio = adjusted_theoretical / observed_rise · aggressiveness`; `K_int_new = K_int · ratio`. Capped at `max_coef_int`, then averaged.
   - `_learn_capacity` and `_calculate_adiabatic_capacity` (lines 1404–1409): `capacity = observed_rise_rate + K_ext·ΔT`. The heat rate is the 75th percentile of slope samples after IQR outlier removal (`calculate_capacity_from_slope_sensor`, lines 2120–2330).
   - Averaging: "average" uses weight `min(count, 50)`. "ema" uses an adaptive alpha, 0.4 for the first 3 cycles and about 0.05 after 20 cycles for capacity (lines 1542–1566).
   - Continuous K_ext learning: EWMA with alpha 0.04 (`_learn_kext_continuous`, line 2778). It runs only when not saturated and after one successful bootstrap.
   - Bootstrap: while heat capacity is unknown or fewer than 3 capacity cycles exist, `calculate_power` temporarily sets K_int = 1.0 and K_ext = 0.1, and restores them in a `finally` block (lines 2007–2028).
   - Learning gates (docs and code): ignore 0% and 100% cycles; skip a cycle where the setpoint changed mid-cycle (line 870); stop when saturated; about 50 cycles per coefficient and about 48 h per session. Auto-TPI is for switch-type heat only and is poor for TRVs.

**Pitfalls to avoid.**
- **No forecast, so no preheat or planning.** The integration reacts to the current error and a one-step slope. Anything that needs a future trajectory (weather, occupancy, price) must come from our own model.
- **Slope lags twice.** The EMA (5-minute half-life) lags the real temperature, and the slope is then a 0.2/0.8 smoothed two-point difference of that lagged series. Do not read the slope as the instantaneous rate.
- **Linear extrapolation ignores heat input.** Auto-start/stop assumes the current slope continues for `dt`, which is wrong while the heater is running.
- **Learning is biased by the things we already flag.** The docs name direct sun on the sensor, fireplace or stove heat, and drafts from open doors. Stable temperatures bias the gains.
- **Saturated periods teach nothing.** During cold snaps the heater sits at 100% and learning stops, so the gains describe mild weather only.
- **Hidden state mutation.** `calculate_power` changes `state.coeff_*` during bootstrap and restores them afterwards. This is safe only because the code is synchronous; any async call between the two lines would see bootstrap values.
- **Brittle entity naming.** The capacity calibration service builds `sensor.<thermostat>_temperature_slope` and `..._power` from the climate entity name, so renaming an entity silently breaks calibration.
- **Zero treated as missing in logs.** `current_temp if current_temp else -9999` (display only) treats 0.0 °C as no value. It does not affect control, but do not copy the pattern.
- **Threshold configuration is easy to get wrong.** Both thresholds must be non-zero, and the high threshold must exceed the low one.
- **Migrations.** The 10.x changelog moved heating-failure detection and auto-fan into plugins and changed long-term statistics units. Disable the legacy feature before enabling its plugin, or duplicate entities appear.

**Useful pieces to copy or reimplement.**
- **Time-aware EMA with a cap** (`ema.py`). It handles irregular sensor timestamps correctly, and the `max_alpha` cap stops a long gap from wiping out history. Relevant to our irregular recorder data.
- **Slope guards** (`open_window_algorithm.py`): a physical bound (|slope| ≤ 120 °C/h), a minimum point count, and a fake point after a 30-minute gap.
- **Learning-gate rules**: skip setpoint-change cycles, skip saturated cycles, cap the effective sample count at 50 so old history does not freeze the estimate, and use IQR outlier removal before taking a percentile of capacity samples.
- **Ratio update for the indoor gain**: compare the capacity-limited expected rise with the observed rise and scale the gain by the ratio. Cheap and inspectable. A good baseline to compare with our batch and online estimators.
- **Adiabatic capacity correction**: `capacity = observed_rise + K_ext·ΔT` is the same heat-balance idea as our 1R1C model, so it can cross-check our C and UA estimates.
- **Bootstrap with aggressive gains** while the model is unknown, then learned gains. Worth copying for a cold start, with a time limit.

**Relevance to our forecasting.** Versatile Thermostat solves a different problem (feedback control of one room) and does not forecast. Its reusable value for us is the estimation plumbing: the time-aware EMA, slope guards, learning gates, and capacity correction. Its failure modes (lagged slopes, saturation blindness, sensor contamination) are the ones our hypotheses already flag.

*Verification status: code claims come from the files listed above at commit `0860f19`, and formulas are quoted from code. The heat-balance form is inferred from the learning equations, not stated in the docs. The docs were read through fetch summaries.*

### Climate Advisor code review

Read from a shallow clone of `gunkl/ClimateAdvisor` (v0.8.60, 2026-11-04). Read in full: `docs/forecast-pipeline-spec.md` (headings only), `docs/08-COMPUTATION-REFERENCE.md` §5c, `docs/thermal-model-v3-spec.md` (anchors and headings), and in part `learning.py` (`compute_k_passive`, `compute_k_env_solar`, `compute_k_solar`, the EWMA cache) and `coordinator.py` (`_simulate_indoor_physics`, `_simulate_indoor_physics_v3`). Not read: the 16k-line `coordinator.py` and 20k-line `automation.py` beyond these functions, `briefing.py`, `classifier.py`, the fan, economiser and natural-ventilation state machines, the Claude-based AI investigator, and the 400-odd test files.

**What it does.** A HACS integration that drives a Home Assistant climate entity from the weather forecast. Each morning it classifies the day (hot to cold) and the trend into tomorrow, then sets one heat or cool setpoint at the edge of the comfort band and lets the thermostat hold it. It pauses heating and cooling when a door or window stays open past its delay, runs natural ventilation through a whole-house fan or the blower, and sends a briefing. Its thermal model learns the house's response so the predicted indoor curve can be shown and the day plan adjusted. It is a planner with a learned one-room model, not a feedback controller and not a full building model.

**The thermal model.** The model is one node: indoor air, driven by outdoor air, a solar term and HVAC power.

1. **Equation** (`_simulate_indoor_physics`, `coordinator.py:14152`): `dT/dt = k_passive·(T − T_out) + Q`, with `Q = |k_active|` while heat is driving below the setpoint, `−|k_active|` while cool is driving above it, and 0 otherwise. `k_passive` is negative (decay toward outdoor). The v3 simulator adds `k_solar·solar_factor` (`_simulate_indoor_physics_v3`, line 14401). The docs in `08-COMPUTATION-REFERENCE.md` give the analytic step `T(t+dt) = T_out + (T − T_out)e^{k dt} + (Q/k)(e^{k dt} − 1)`, which is the exact solution of the same equation. The v3 spec (line 363) writes the ODE as `(k_passive + k_vent)(T_out − T_in)`, which has the opposite sign. The code is consistent; the spec is not.
2. **Solar factor**: a sinusoid from 0 to 1 to 0 over the day (`08`, line 364). It is a shape, not a measured irradiance.
3. **Learning, passive decay** (`compute_k_passive`): OLS through the origin, `rate_i = k_passive · δ_i`, where `δ` is the midpoint of indoor minus outdoor. Pre- and post-heat windows are fitted separately, so the heating ramp does not create a spurious rate. Samples are smoothed with a 3-point moving average first. Validation rejects wrong sign, too few points, and low R².
4. **Learning, solar** (`compute_k_env_solar`): two-parameter OLS, `rate = k_env·δ + k_solar·sf`, solved as a 2×2 normal equation. It is rejected when the solar factor range is below 0.30 (`THERMAL_SOLAR_FACTOR_MIN_RANGE`), because the two terms are then collinear. A one-parameter fallback, `compute_k_solar`, subtracts the passive term and clamps the result to [0, max].
5. **Averaging**: each accepted observation is blended into the cache by EWMA, with α set by its confidence grade: 0.30 (high), 0.15 (medium), 0.05 (low) (`learning.py:1167`). Confidence gates which values the predictor may use (`_physics_eligible`).
6. **Fallback**: with no usable model, the predictor uses a ramp over a fixed or rate-based duration. A "gate bridge" promotes `k_vent_window` to stand in for a missing `k_passive`, so a home with only ventilation observations still gets physics.

**Pitfalls to avoid.**
- **The model clamps at the setpoint.** The simulator stops heating when the indoor reaches the setpoint (the overshoot clamp, `clamp_bound`). It cannot predict overshoot or a thermostat's deadband unless the caller passes a bound. Our heater model needs the same explicit choice.
- **Q is bang-bang.** `Q` is either the full `k_active` or zero, so a duty-cycled or modulating system is modelled as on or off. Heat-pump or TRV behaviour will be misfit.
- **Sign conventions differ across the docs.** The v3 spec's ODE has the opposite sign from the code, and `k_passive` is "always negative" in one place and given as a positive decay rate in another. We already flag this kind of naming trap (Predheat). Name our coefficients with explicit signs and units (`UA_W_per_K`, `k_decay_per_h`).
- **Solar is collinear without variation.** Two-parameter solar estimation has no information when the sun sits on a flat curve (spring or cloudy periods). The code guards this with a range check; we need the same guard, plus a measure of the range on our data.
- **Churn and size.** Version 0.8.60 was released on 4 November alone, four versions that day, and the codebase is about 71k lines. A lot of the complexity is for fans, nat-vent and door/window state machines that do not bear on the thermal model. Do not copy the surrounding machinery.

**Useful pieces to copy or reimplement.**
- **Separate passive and HVAC windows before fitting.** Fitting across the boundary between pre-heat and post-heat rates is the bug the `compute_k_passive` comment describes. Our estimator should split windows the same way.
- **Two-parameter solar fit with a range guard.** `k_env` and `k_solar` solved jointly with an explicit collinearity check. This is a concrete version of our solar hypothesis (11), and the guard is the part we need.
- **Confidence-graded EWMA.** The α depends on the quality grade of each observation, so noisy windows move the estimate less. Cheap to implement and easy to test against our batch fit.
- **Explicit ODE step with the analytic form.** The closed-form step is exact for constant inputs and cheap enough for a week-ahead curve. The code also has an RK4 integrator in `learning.py` (about line 610), which I did not trace to its caller.
- **Validation as reason codes.** `compute_k_passive` returns a reason code with every rejection. Our estimators should do the same, so the report says why a window was dropped.

**Relevance to our forecasting.** This is the closest reviewed project to our one-node hypotheses. It fits a one-node ODE with a solar term from the same sensor types we have, and it runs a week-ahead predicted curve on top. Its weaknesses are the ones our hypotheses already test: no spatial model, bang-bang HVAC, and solar confounded with heating. Its reusable parts are the window split, the solar range guard and the confidence-graded update. The rest (classification, briefing, state machines) is outside what we are building.

*Verification status: equations and constants come from `learning.py`, `coordinator.py` and the docs at the commit cloned on 4 November 2026. The docs were read by heading and in targeted sections, not in full. The `08` analytic form was checked against the code's equation by hand, not by running it.*

### Warnings from the reviews
- Self-reported savings or accuracy claims without figures (EcoEdge) should be disregarded.
- Stable indoor temperature biases Home Performance's K upward; day/night swings also bias it. Test this on our data.
- Open windows, overrides and guests break many models (Heating Analytics, EcoEdge thread). Model them as explicit events.
- Predheat's C kernel and Python fallback were not checked for parity (Predbat). Use one implementation and test it.

---

## d) Forecast and estimation models: pros and cons

| Model type | Examples | Pros | Cons |
|---|---|---|---|
| **Steady-state heat-loss coefficient** (K = E / (ΔT·t)) | Home Performance | Simple; one number; easy to explain; no thermal mass to fit | No lag, no solar or internal gain terms; biased by stable temperatures and day/night swings; only comparable within one install |
| **Single-node RC (1R1C)** | RoomMind, EcoEdge (per room), Predheat (lumped, water loop) | Few parameters; analytic solution for constant inputs; captures warm-up/cooldown time constant | One temperature for the whole room; no fabric vs air split; can't represent stratification or inter-room flow |
| **Multi-node RC (2R2C, 3R3C, 5R1C, 6R3C)** | ISO 13790 5R1C, RC_BuildingSimulator, thermal-rc-toolbox, Modelica libraries | Separates air and fabric; standard in building science; more realistic lag | More parameters, identifiability problems; ISO 13790 5R1C is designed for monthly calculation |
| **Online filter (EKF / UKF)** | RoomMind (EKF), Radecki & Hencey (UKF), Zamani thesis (UKF) | Learns parameters while running; adapts to change; can estimate unknown loads | Linearisation error (EKF); sensitive to noise and tuning; can drift without excitation; only as good as the model structure |
| **Batch grey-box fit (ML/Bayesian/maximum-likelihood)** | Bacher & Madsen 2011 method; thermal-rc-toolbox (GA) | Uses full history; reports uncertainty; model selection by likelihood ratio | Needs excitation; slow; results depend on the chosen structure |
| **Degree-day / efficiency regression** | Heating Analytics (kWh per thermal degree-day), EMHASS demand | Robust for energy totals; uses weather directly; easy to explain | Not a temperature model; poor for short-term control; efficiency term absorbs many effects |
| **Feed-forward ML on energy** | Heating Analytics (NLMS, Tobit), Predbat load MLP, NeuralForecast | Captures nonlinearity; good for prediction if data are plentiful | Needs weeks to months of data; black box; can't attribute effects without extra design |
| **Shadow ML on decisions** | EcoEdge (LightGBM) | Learns across homes if pooled | Pooling across houses is unvalidated; sources of shadow training data not described |
| **Weighted-average or profile forecast** | Predbat default load, GivTCP PALM | Simple, fast, no training | Ignores weather and physics; relies on the past resembling the future |
| **Forecast blending** | Weather Fusion AI, GivTCP PALM (P10/P50/P90) | Reduces single-source error | Learned weights need data; proprietary blends can't be audited |
| **Linear optimisation with fixed COP and losses** | EMHASS, Langer & Völling 2020 (MILP) | Fast; globally optimal for the model; supports constraints | Linearity assumed; COP and losses fixed per step; end-of-horizon effects in rolling horizon |
| **Lookup tables** (COP vs outdoor temperature, radiator ΔT correction, gas efficiency vs return temperature) | Predheat, Predbat | Transparent; easy to edit | Manual; not fitted; extrapolation limited (Predheat clamps at −20 to 20 °C) |

**Suggested order for us:** keep a steady-state K as a baseline (Home Performance), add a 1R1C per room (RoomMind/EMHASS form), test a 2R2C alternative with a batch fit (Bacher and Madsen procedure), and use the online filter for monitoring only until it agrees with the batch result.

---

## e) Papers and other references

Ordered by how central they are to our work. "Expected application" is what the source is used for in our project.

### Peer-reviewed and standards

1. **Bacher, P. & Madsen, H. (2011).** "Identifying suitable models for the heat dynamics of buildings." *Energy and Buildings* 43(7), 1511–1522. DOI [10.1016/j.enbuild.2011.02.005](https://doi.org/10.1016/j.enbuild.2011.02.005). Full text: [DTU course copy](https://02417.compute.dtu.dk/material/week13/article-grey-box-models.pdf); [DTU Orbit](https://orbit.dtu.dk/en/publications/identifying-suitable-models-for-the-heat-dynamics-of-buildings/).
   - *Covers:* procedure for choosing among grey-box heat-dynamics models of increasing complexity, with likelihood-ratio tests; estimates conductivity, heat capacity and window area.
   - *Expected application:* the model-selection procedure for our per-room structure choice (1R1C vs 2R2C) and identification of parameters from recorder data. Referenced by RoomMind's code.

2. **Radecki, P. & Hencey, B. "Online Model Estimation for Predictive Thermal Control of Buildings."** arXiv:1601.02947 ([PDF](https://arxiv.org/pdf/1601.02947)). Later IEEE Trans. Control Systems Technology (2017) per a catalogue listing, unverified.
   - *Covers:* UKF-based online estimation of building thermal network parameters and unknown loads, for predictive control, with 24 h+ predictions.
   - *Expected application:* alternative to RoomMind's EKF for online estimation; a benchmark for the online-vs-batch comparison.

3. **Langer, L. & Völling, T. (2020).** "An optimal home energy management system for modulating heat pumps and photovoltaic systems." *Applied Energy* 278, 115661. DOI [10.1016/j.apenergy.2020.115661](https://doi.org/10.1016/j.apenergy.2020.115661). arXiv:2009.02349 ([link](https://arxiv.org/abs/2009.02349)). Follow-up: *Applied Energy* 327 (2022), 120020.
   - *Covers:* MILP home energy management with heat pump, PV, battery and thermal storage; rolling-horizon end-of-horizon effects; battery matters most for self-sufficiency. Code open-source in Julia (JuMP).
   - *Expected application:* a reference for linear optimisation with heat-pump COP and loss terms (EMHASS uses its loss equation, Eq. B.13 per EMHASS docstring, unverified). Relevant when we move from monitoring to control.

4. **ISO 13790:2008.** *Energy performance of buildings: Calculation of energy use for space heating and cooling.* International Organization for Standardization. Not accessed.
   - *Covers:* monthly quasi-steady-state method; reduced 5R1C thermal network.
   - *Expected application:* a standard benchmark structure. Not suited to hourly recorder data without modification.

5. **ISO 52016-1:2017.** Energy performance of buildings: energy needs for heating and cooling, internal temperatures and sensible and latent heat loads. Cited by BUEM per search snippet; not opened.
   - *Expected application:* a newer successor to ISO 13790 for hourly calculation; check before relying on it.

6. **ASHRAE Guideline 14 (calibration metrics).** Cited in search results for CV(RMSE) and NMBE; not opened.
   - *Expected application:* acceptance thresholds for calibrated models; a standard to compare our fits against.

7. **Zamani, V. "Parameter Input Estimation and Temperature Control of RC Thermal Dynamic Systems."** University of Alberta thesis. [Record](https://era.library.ualberta.ca/items/dfd087a7-1cd9-4f68-8aa0-ed1482bc502d). Uses UKF with NLS to estimate RC parameters and inputs with partially missing states. RoomMind's code cites "Zamani et al. (2025), PMC 11798724"; I could not confirm this is the same work.
   - *Expected application:* joint parameter and input estimation, relevant to estimating unmeasured heat sources.

8. **Chen et al. (2021).** *Building and Environment*: UKF with RC models for online estimation in single detached houses. Found via search; no link captured.
   - *Expected application:* a comparable online-estimation study for detached houses.

9. **Chen et al. (2021).** *Journal of Building Engineering*: UKF parameter estimation for simple RC models. Found via search; no link captured.
   - *Expected application:* as above.

10. **Radiator output datasheet: Quinn/Barlo.** [Barlo panel output specification](https://www.tlc-direct.co.uk/Technical/DataSheets/Quinn_Barlo/BarloPanelOutputsSpecs-Feb-2102.pdf). Fetched and read: heat output in W and BTU/hr for steel panel radiators by type, height and length.
   - *Expected application:* a radiator output-vs-ΔT correction for a heat-emitter model. Rated at a standard ΔT (typically 50 K, not verified on the datasheet). The Predheat doc relies on it.

11. **TU Delft record: inverse modelling with a first-order RC model using smart meter and air temperature data.** [repository.tudelft.nl](https://repository.tudelft.nl/record/uuid:553d30bc-003c-4afd-835b-f1be80e84a54). Not read in full.
    - *Expected application:* identifying RC parameters from low-resolution smart-meter data; relevant to identifiability.

12. **Energies (2020): RC dynamic models for heat loss coefficient from in-use buildings.** [DOAJ record](https://doaj.org/article/ba73afb7415e4d03808a81ec0c5df529). Not read.
    - *Expected application:* estimating heat-loss coefficients from in-use data, a direct comparison for our K.

13. **US Patent 10,481,019 (heat loss coefficient determination).** [Google Patents](https://patents.google.com/patent/US10481019). Read as a search snippet only; claims ±20% accuracy, unverified.
    - *Expected application:* prior art; don't reproduce.

14. **Aminer: EKF adaptive thermal modelling in homes** (grey-box, underfloor heating). [Link](https://www.aminer.org/pub/5c756e77f56def97985d2364/applying-extended-kalman-filters-to-adaptive-thermal-modelling-in-homes). Search snippet reports 95th-percentile errors of 0.95 °C at 2 h and 1.37 °C at 4 h; not opened, and not confirmed as RoomMind's basis.
    - *Expected application:* a benchmark for achievable prediction error with an EKF.

15. **Predheat YouTube explanation.** [youtu.be/_-KIQen67zI](https://youtu.be/_-KIQen67zI). Not watched.

### Machine learning methods cited (from memory; not verified against the code)

16. **He, K. et al. (2015).** "Delving Deep into Rectifiers." Weight initialisation (Predbat ML).
17. **Loshchilov, I. & Hutter, F. (2019).** "Decoupled Weight Decay Regularization." ICLR. AdamW (Predbat ML).
18. **Loshchilov, I. & Hutter, F. (2016).** "SGDR: Stochastic Gradient Descent with Warm Restarts." Cosine learning-rate schedule (Predbat ML).
19. **Srivastava, N. et al. (2014).** "Dropout." *JMLR*. (Predbat ML.)
20. **Huber, P. (1964).** Robust loss estimation (Predbat ML).
21. **Bengio, Y. et al. (2009).** "Curriculum Learning." ICML (Predbat ML).

### Tools and libraries

- **LightGBM** (Microsoft): [github.com/microsoft/LightGBM](https://github.com/microsoft/LightGBM). Gradient-boosted trees; EcoEdge shadow model.
- **HiGHS** solver: used by EMHASS.
- **Open-Meteo**: [open-meteo.com](https://open-meteo.com/). Weather data source (fork used by Heating Analytics).
- **Solcast**: [solcast.com.au](https://solcast.com.au). PV forecast source (GivTCP PALM).
- **givenergy-modbus**: [dewet22/givenergy-modbus](https://github.com/dewet22/givenergy-modbus).

---

## f) Areas that need future research

1. **Finish the source reading.** RoomMind's model-facing code and Heating Analytics' `DESIGN.md` are read (see the code reviews). Not read: the device, valve and setpoint code in RoomMind's `mpc_controller.py` (about 2,500 lines). In Heating Analytics: the 4D prediction path after line 1386, and the rest of `forecast.py`, most of `solar.py`, `storage.py` and `coordinator.py`. Test the residual and rebound inconsistency in RoomMind's `mpc_optimizer.py` on a simulated room before relying on the closed-form power.
2. **Home Performance K method.** The installed integration is confirmed as `Hugofromfrance/home_performance` v1.4.2. Next, check the installed config options (not visible through the MCP) and whether the K sensor is exposed, before relying on its K method.
3. **Test steady-state K against our data.** Home Performance warns that stable temperatures bias K upward. Check against the Kitchen and other rooms.
4. **Identifiability at recorder resolution.** Determine whether 30-minute recorder data can separate C from UA per room. Simulate first.
5. **Solar gain under heating.** Heating Analytics' Tobit approach handles censoring. Our solar hypothesis (11) needs a method that works when the heating is on. Heating Analytics' SNR weighting (`learning.py:557`) is an alternative for the sunny-hour bias, but it targets dark-equivalent demand, so the target must be stated.
6. **Inter-room heat flow.** Predheat, EMHASS and RoomMind all assume single nodes or no inter-room flow. Our multi-room house may need coupling terms; no reviewed project addresses this well.
7. **Radiator output vs ΔT.** Predheat's table (Barlo datasheet) is at ΔT 50. Measure our own emitter curve from flow and return data where available.
8. **Validate the ISO 13790 5R1C and ISO 52016-1.** Check their hourly applicability to our data before using the structure.
9. **Open-window and override detection.** Home Performance uses a fast temperature-drop rule; Heating Analytics treats windows as irregular events. Test a detector against the Kitchen 3 November finding.
10. **Online vs batch agreement.** Implement both (EKF per RoomMind; Bacher–Madsen batch) on the same data and measure disagreement.
11. **Uncertainty reporting.** Adopt CV(RMSE)/NMBE and parameter intervals (thermal-rc-toolbox approach) as the standard for every hypothesis result.
12. **Weather data quality.** Compare Open-Meteo, Met.no and local sensors, especially for cloud cover and wind, which Heating Analytics says are poor in standard feeds.
13. **Weather Fusion AI.** Its obfuscated code and disguised README prevent assessment. Do not use it as a dependency without review.
14. **Predbat ML load model.** Evaluate whether a load forecaster is useful for our energy-balance hypotheses.
15. **Pooled vs per-house learning.** EcoEdge's cross-home LightGBM is unvalidated. If we consider pooling, test on held-out houses first.
16. **Reproduce the Langer & Völling model** (open-source Julia) only if we move to control.
17. **Season-transition hysteresis.** Heating Analytics' `DESIGN.md` §8 gives a test: bucket `actual − predicted` by the sign and size of the trailing 48–72 h temperature trend, and look for a signed bias near +1 to +3 °C. Run it on our data before adding any multi-day state variable.
18. **Observe zero or skip for hot-water cycles.** If we model them, simulate the skip-versus-observe-zero drift in Heating Analytics' `DESIGN.md` §2 on a synthetic duty cycle before choosing a treatment.
19. **Heating energy in warm hours.** Heating Analytics' Track C spreads an MPC unit's heating energy into hours above the balance point, because those hours carry cooling weights. For a heat-only unit, measure how much heating would land in warm hours on our data before copying the weighting.
20. **Dual-interference skips.** Heating Analytics drops an hour from learning when solar and aux impact both exceed 0.1 kWh (`const.py:487`). Count how many hours that removes from our data before adopting the rule.

---

*Verification status: most claims about other projects are from README/docs and fetch summaries, not full code reading. Items marked "not opened" or "not read" were only seen in search results.*
