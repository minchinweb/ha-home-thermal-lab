# Literature and project review: house thermal modelling

Survey of Home Assistant integrations and the scientific references behind them, done to see what others do for house thermal modelling and what we can learn from it. Written from web search, README and docs reading, and shallow clones of source repos. Where a claim was not checked against source, it says so.

Sources were read in a short session; figures and equations quoted from fetch-tool summaries are marked **(summary)** and should be checked against the source before reuse.

---

## a) Projects reviewed

| Project | Repo | What it does | Thermal model | Source read? |
|---|---|---|---|---|
| **RoomMind** | [snazzybean/roommind](https://github.com/snazzybean/roommind) | Per-room control (MPC, valve control) with learned thermal model | Single-node 1R1C RC model; EKF learns α = U/C, β_h, β_c, β_s (solar), β_o (occupancy), β_f (AC air/mass offset) | **Yes**, `custom_components/roommind/control/thermal_model.py`, cloned to scratchpad. Rest of the controller (`mpc_controller.py`, `mpc_optimizer.py`) not read. |
| **Heating Analytics** | [thuemah/heating_analytics](https://github.com/thuemah/heating_analytics) | Predicts and attributes heating/cooling energy from weather; feed-forward only | Learned degree-day / efficiency model with thermal inertia (exp-weighted outdoor history, τ 1–24 h), per-unit solar and wind terms, Tobit solar estimation | **Partly**: README, file list and `const.py` read; `DESIGN.md` and the core learning code not read. Forum summary and README describe different versions. |
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

- **RoomMind**: the README-based summary said "EKF per room"; the source confirms a **single-node** model, not multi-node.
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

### Validation and tests
- **Hold out data**, and compare predicted with measured temperatures. EcoEdge published no such validation; we should.
- **Shadow mode** gives a free counterfactual: predicted against actual, run standing alongside decisions (Heating Analytics, EcoEdge).
- **Test sensitivity to any confidence weighting** under several settings (GivTCP PALM, P10/P50/P90).
- **Treat warm-up as a known period.** Heating Analytics needs 7–14 days; Track B (daily learning) months. Report predictions as unreliable until then.
- **Version-tag learned parameters** so they can be reset after physical changes (RoomMind's "Reset Thermal Data", Heating Analytics' solar reset).

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

1. **Confirm the source of each model we might adopt.** RoomMind's MPC and EKF parameter update code (`mpc_controller.py`, `mpc_optimizer.py`, `thermal_model.py` beyond the first 300 lines) should be read in full. Heating Analytics `DESIGN.md` and its learning code were not read.
2. **Home Performance K method.** The installed integration is confirmed as `Hugofromfrance/home_performance` v1.4.2. Next, check the installed config options (not visible through the MCP) and whether the K sensor is exposed, before relying on its K method.
3. **Test steady-state K against our data.** Home Performance warns that stable temperatures bias K upward. Check against the Kitchen and other rooms.
4. **Identifiability at recorder resolution.** Determine whether 30-minute recorder data can separate C from UA per room. Simulate first.
5. **Solar gain under heating.** Heating Analytics' Tobit approach handles censoring. Our solar hypothesis (11) needs a method that works when the heating is on.
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

---

*Verification status: most claims about other projects are from README/docs and fetch summaries, not full code reading. Items marked "not opened" or "not read" were only seen in search results.*
