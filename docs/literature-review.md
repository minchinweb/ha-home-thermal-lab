# Literature and project review: house thermal modelling

Survey of Home Assistant integrations and the scientific references behind them, done to see what others do for house thermal modelling and what we can learn from it. Written from web search, README and docs reading, and shallow clones of source repos. Where a claim was not checked against source, it says so.

Sources were read in a short session; figures and equations quoted from fetch-tool summaries are marked **(summary)** and should be checked against the source before reuse.

---

## Summary: what to copy and what to avoid (consolidated 4 November 2026)

This section condenses the sections below, mostly the Heating Analytics code review (about 250 passes). The detail and the line references are in the sections below and in [heating-analytics-review.md](heating-analytics-review.md).

**Scope.** Heating Analytics is an *energy* model. It predicts kWh from the weather, feeds forward only, and is tuned for heat pumps (COP, defrost, Track B/C smearing). It does not forecast room temperature. Its value to us is the machinery *around* the model: gates, scoring, replay and persistence. Its model core is not that useful to us. RoomMind is the closest reviewed project to our room-temperature forecast.

### Copy: modelling and learning

1. **Excitation gating** (RoomMind EKF). Update a term only when its input is non-zero in the data: sun terms from sunlit hours, heating rate from call hours. Our block fits already check sign and range (`learn.py`). Add a minimum count of *excited* hours for each term before it is fitted. Otherwise the term stays out of the fit (`None`, not 0).
2. **A scored readiness gate** (RoomMind: prediction std below 0.5 °C, and at least 60 idle and 20 heating updates). For us: issue the hybrid (H) for a zone and lead time only while its trailing scored error beats the profile-with-offset (D). Otherwise issue D. We already fall back to D when no fit is usable. This makes the fallback depend on the score as well.
3. **Censored solar.** Sun gain while the furnace runs is hidden (censored). Use Tobit or a one-sided inequality, keep the sun terms non-negative, and gate the censored fit against a plain least-squares fit with a cosine check and a step cap. Restart from least squares when the fit fails (Heating Analytics' live Tobit writer). This applies to hypothesis 11 when the sun is higher.
4. **State what a weighted fit converges to.** Heating Analytics weights each hour by its solar signal, so its base converges to dark-hour demand, not to the mean. Any weighting we add needs the same sentence in its docstring.
5. **Events are observed, not imputed.** Hot water is logged as zero, not skipped (Heating Analytics). Outliers are marked, not smoothed away (GivTCP lesson). For us this covers showers (18), cooking, open windows and guests.
6. **Lagged outdoor temperature** (Heating Analytics' inertia temperature). It is an exponential kernel over outdoor history with τ bounded to 1–24 h, and the history stops at the first gap longer than τ. This is our predictor E's accumulated outdoor term. Compare τ candidates **on the same hours**. Heating Analytics' sweep does not, and its candidates are scored on different samples.
7. **Season-transition test** (`DESIGN.md` §8). Bucket the residual by the trailing 48–72 h outdoor trend and look for a signed bias. It is cheap to run on our forecast scores once there are a few weeks of them.
8. **Replay through the live code.** A backtest that calls the same fit and step functions as the integration cannot drift from it. `scripts/predict_rc.py` imports part of the integration. Move the rest into it as the model settles.
9. **Suggest, don't auto-apply**, learned physical values the user sees (Heating Analytics #1020), and **version-tag learned state** so it can be reset after a physical change (RoomMind, Heating Analytics).

### Copy: forecasting and scoring

1. **Log forecasts as issued, with provenance.** Record which weather source and which model made each forecast. Clear or split the scores when the source changes (Heating Analytics filters history on the weather entity).
2. **Build bands from measured errors, and leave them out when the sample is thin.** Measure a multi-step horizon's error directly: independent errors grow as √n, not ×n (Heating Analytics fixed a ×7 week band). Take the band's centre and its width from the same basis.
3. **Key days by local date and hours by UTC instant**, never by hour number. Heating Analytics has several daylight-saving faults: hour-number maps, text-prefix dates and a 24-hour loop from local midnight. The house is in Edmonton. Alberta now stays on UTC-6 all year, but the time-zone database Home Assistant uses has not caught up, so Home Assistant is set to America/Regina, which is also UTC-6 all year (hypothesis 14). Those faults would not show today. The code should still not depend on that: other users' zones change clocks, and so would ours if the setting changed.
4. **Bias-correct the outdoor forecast against our own sensor.** We already do this (`scoring.py`, 48 h). Keep it.
5. **Fail closed.** An unknown source or a missing input gets the lowest reliability, not a default value.

### Avoid: pitfalls seen repeatedly in Heating Analytics

1. **Zero standing in for missing** (the most common class, about 20 instances). Patterns: `.get(key, 0.0)` on a measurement; `if temp:` on a temperature (0 °C is falsy); a missing forecast error read as 0, so the forecast looks perfect; a missing forecast filled with the live model, so the error is zero by construction. Rule: use `None` for no evidence, and count missing values apart from real zeros.
2. **One number kept in several places.** There are seven design-versus-code mismatches, docstrings that disagree with constants (decay 0.80 against 0.50, cap 20 against 10), and three thresholds for one idea (20, 22 and 24 h). Rule: use one named constant, import it, and put every clamp in the docstring.
3. **Two code paths for one job.** The 3D and 4D batches filter outliers differently, two global-base writers use different weights, the save and the backup write different key lists, and live and import de-duplicate on different keys. Rule: use one function, or write a test that proves the two agree.
4. **Silent fallbacks.** A broad `except` returns `None` and switches pipeline, setup errors show as "timeout", and services report success for a failed import. Rule: log, count and show every fallback in diagnostics.
5. **Persistence.** Debounced saves on unload and after user actions lose writes on restart. An import learns before it de-duplicates, so a re-import teaches the model twice. A backup misses keys that the restore reads.
6. **Signs and units missing from names.** `delta_t` is absolute in one place and signed in another, an "hourly" MAE is in kWh per day, and kWh thresholds depend on house size.
7. **Complexity without a held-out score.** The integration has 45,000 lines, 341 constants and several experimental flags that are off by default. Our hypothesis files and backtests are the guard against this. Keep a term only when it beats the simpler predictor out of sample.

### Not worth copying

- Heating Analytics' model core: temperature and wind buckets, 3D and 4D solar vectors, and Track B/C COP smearing. These attribute energy for heat pumps. We forecast room temperature with a gas furnace.
- RoomMind's optimiser as a reference for optimal control. It is a greedy search. A horizon-optimal plan is a MILP or dynamic-programming problem (EMHASS, Langer and Völling).
- Weather Fusion AI (obfuscated code) and EcoEdge's accuracy claims (no figures).

---

## a) Projects reviewed

| Project | Repo | What it does | Thermal model | Source read? |
|---|---|---|---|---|
| **RoomMind** | [snazzybean/roommind](https://github.com/snazzybean/roommind) | Per-room control (MPC, valve control) with learned thermal model | Single-node 1R1C RC model; EKF learns α = U/C, β_h, β_c, β_s (solar), β_o (occupancy), β_f (AC air/mass offset) | **Yes**: `thermal_model.py`, `managers/ekf_training_manager.py` and `control/mpc_optimizer.py` read in full; the model-facing parts of `mpc_controller.py` read (gates, `_evaluate_mpc`, plan guard). Device, valve and setpoint code (about 2,500 lines) not read. Commit `2aeb49a` (v1.8.1). See the RoomMind code review below. |
| **Heating Analytics** | [thuemah/heating_analytics](https://github.com/thuemah/heating_analytics) | Predicts and attributes heating/cooling energy from weather; feed-forward only | Learned degree-day / efficiency model with thermal inertia (exp-weighted outdoor history, τ 1–24 h), per-unit solar and wind terms, Tobit solar estimation | **Most of the model**: `DESIGN.md` in full; learning (per-unit, solar NLMS, inequality, Tobit live and batch, 4D, global base); hour close and learning gates; the per-minute loop; coordinator inertia and gap fill; the 3D prediction and solar saturation; the forecast blend and accuracy stats; `daily_processor.py` (`process`, Track C); `thermodynamics.py`; `helpers.py`, `heat_source.py`, `solar_optimizer.py`, `switch.py`, `repairs.py`, `number.py`, `select.py`, `observation.py` and `thermodynamics.py` in full, parts of `__init__.py` and `hourly_processor.py`, and the references in `const.py`. Not read: the 4D prediction path from `statistics.py:1521` (`1521–1656`), most of `statistics.py`, and parts of `diagnostics.py`, `storage.py`, `retrain.py`, `balance_point.py`, `forecast.py`, `solar.py`, `daily_processor.py`, `explanation.py`, `config_flow.py` and `sensor.py`, and the calibration, diagnostics and config code. Clone at `eba9e6e` (v1.3.16). Forum summary and README describe different versions. See the [Heating Analytics code review](heating-analytics-review.md). |
| **EcoEdge AI** | [ecoedge-dev/ha_ecoedge_ai_thermostat](https://github.com/ecoedge-dev/ha_ecoedge_ai_thermostat) (forum: [thread 998485](https://community.home-assistant.io/t/ecoedge-ai-predictive-heating-control-for-home-assistant/998485)) | Predictive setpoint advice from a 24 h weather forecast; shadow mode only | Per-room single-node RC / Newton cooling, k per hour (time constant 1/k); LightGBM "shadow" model in forum post only | **No**: forum summary and README only. Commercial hosted dashboard. |
| **Predheat** (merged into Predbat) | [springfall2008/predheat](https://github.com/springfall2008/predheat) (archived) | Predicts indoor temperature and heating for water-based central heating | Single lumped indoor node plus water-loop node; heat loss = P_loss·(T_in − T_out); radiator output via ΔT correction table; manual calibration | **Partly**: `predheat.py` read via fetch summary; not run. Delta-T table values not seen. |
| **Predbat** | [springfall2008/batpred](https://github.com/springfall2008/batpred) (URL in older docs is dead) | Battery, PV and load forecasting and charge scheduling; includes Predheat | Predheat as above; SoC balance per 5 min; ML load MLP (~889k parameters, autoregressive, 48 h) | **Partly**: cloned; `predheat.py`, `docs/predheat.md`, `docs/load-ml.md`, `docs/caution.md` read; `prediction.py` grepped only. |
| **EMHASS** | [davidusb-geek/emhass](https://github.com/davidusb-geek/emhass) | Energy management optimisation, MILP via CVXPY/HiGHS; includes a thermal battery model | Linear discrete recursion T[k+1] = T[k] + heating − γ_c·dt·(T − T_out); physics utilities for transmission, ventilation, solar, internal gains; degree-day demand; Carnot COP | **Partly**: docs plus about 3/5 of `optimization.py` and first 100 kB of `utils.py` (fetch summaries). |
| **Home Performance** | [Hugofromfrance/home_performance](https://github.com/Hugofromfrance/home_performance) (HACS, MIT, v1.4.2) | Estimates whole-house heat-loss coefficient K (W/°C) and rates insulation A+ to D | Steady-state K = E_thermal / (ΔT × duration), 7-day rolling window, fixed thresholds, no calibration | **Partly**: `models.py` and `const.py` read. **Confirmed as the installed version** (v1.4.2): Home Assistant entity names ("Home Performance - <room> Avg delta T 24h", "Window open") match this repo's source. |
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
| **Climate Advisor** | search result | [gunkl/SmartHVAC](https://github.com/gunkl/SmartHVAC) | Reportedly a two-parameter first-order model (unverified) |
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
| **Versatile Thermostat** | user request | not linked | Home Assistant thermostat integration; to review later |
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

### Heating Analytics code review

Moved to its own note: [heating-analytics-review.md](heating-analytics-review.md) (design document, where the design and the code disagree, and about 250 reading passes with line references at `eba9e6e`, v1.3.16). The Summary at the top of this review condenses it.

---

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

1. **Finish the source reading.** RoomMind's model-facing code and Heating Analytics' `DESIGN.md` are read (see the code reviews). Not read: the device, valve and setpoint code in RoomMind's `mpc_controller.py` (about 2,500 lines). Heating Analytics: every source file has had at least one pass (see [heating-analytics-review.md](heating-analytics-review.md)); its tests (about 63,000 lines) are not reviewed. Test the residual and rebound inconsistency in RoomMind's `mpc_optimizer.py` on a simulated room before relying on the closed-form power.
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
