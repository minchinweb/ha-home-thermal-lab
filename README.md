# ha-home-thermal-lab

Home Assistant custom components for modelling a target daily temperature
wave, and for testing hypotheses about how a house behaves thermally.

- `custom_components/home_thermal_lab/`: runs the experiments inside Home
  Assistant, using data already in its recorder.
- The house itself (rooms, walls, roofs, windows, internal walls, heating
  registers) is described once in
  [House Structure](https://github.com/minchinweb/ha-house-structure), a
  separate integration; the zones here read their room from it.
- `hypotheses/`: one file per hypothesis (claim, data, method, results).
- `scripts/`: command-line runners and reports. Copy `.env.example` to `.env` (git-ignored) and fill in your Home Assistant URL, token and sensor.

## Install with HACS

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=minchinweb&repository=ha-home-thermal-lab&category=integration)

The button adds this repository to HACS as a custom repository. By hand:

1. In HACS, open the menu (three dots) and choose **Custom repositories**. Add
   `https://github.com/minchinweb/ha-home-thermal-lab` with the type
   **Integration**.
2. Find **Home Thermal Lab** in HACS, download it, and restart Home Assistant.
3. Add the integration (**Settings > Devices & services > Add integration >
   Home Thermal Lab**), pick the outdoor temperature sensor, then add each
   sensor from the integration's page (below). Or use YAML instead.

Without HACS, copy `custom_components/home_thermal_lab/` into your Home
Assistant `custom_components/` folder.

The integration switches nothing. It needs Home Assistant 2025.3 or later, the
recorder (default), and fetches an hourly forecast from Open-Meteo for the home
location. The `.github/workflows/validate.yml` workflow runs the HACS and
`hassfest` checks on every push.

## Using House Structure

With [House Structure](https://github.com/minchinweb/ha-house-structure)
installed and the house's parts added there, a zone, contribution chart or
heating-call statistics sensor only needs its **Room (area)**. From that room
it takes:

- the thermostat, from the room's heating register;
- the room temperature sensor, from the area;
- the sun: the room's windows and roofs (the `g` term) and its windowless
  outside walls (the lagged `w` term), each at its own compass bearing, tilt
  and shading, in place of the window faces, roofs and sunlit walls typed on
  the zone;
- whether the room is below ground.

A thermostat, room sensor or below-ground setting typed on the zone wins over
the room's. The sensors reload when House Structure's rooms change. Without
House Structure, or for an area with no parts in it, the settings typed on the
zone are used as before. A pinned `g` or `w` was fitted to the old faces, so
leave them empty to have them learned again when a zone moves to a room.

## Sensors

### From the web interface

Add the integration and set the house once: the outdoor temperature sensor, the
house rotation (measured from the building outline on OpenStreetMap, which
needs one request to the Overpass service with your home position, and drawn on
the form so you can check it; tick **Redraw the map** and submit to see another
rotation without saving), and its roofs typed as `S 30, W 4:12` (face, then the pitch in
degrees or as rise:run; give each roof a name, such as
`Front=S 30, Back=W 4:12, Garage=W 8:12`, and two roofs on one face are fine). Renaming a roof
(on the same face) updates the rooms that use it; deleting one unlinks them. Rooms then only tick which of those
roofs they have windows in. Then add the sensors from the integration's page,
with the buttons in this order:

1. **Add heating-call statistics**: one per zone; only a thermostat is needed.
2. **Add furnace energy**: one for the blower and one for the gas.
   - Blower: pick your whole-house power sensor and the integration learns the
     fan and heating powers from the steps in it whenever the furnace changes
     state (`scripts/blower_power.py` shows the same steps). It needs several
     days of data and refreshes every 6 hours; the powers you type are used
     until then and for any state it cannot learn. The `learned_kw` and `edges`
     attributes show what it found. Fan-only draw is small, so it is the last
     to be clear; the fewer fan-only edges lost to heating calls, the better.
   - Gas: leave the power sensor empty, set the unit to **BTU/h** and type the
     furnace input (80,000 for the high stage, about 65% of that for low).
3. **Add shadow zone (with sun)**: one per zone. It makes three sensors (shadow,
   forecast and target, below) and puts the zone in the **Thermal Lab** panel.
   Leave **a** and **c** empty and the integration fits the zone's no-heat
   model on the last 14 days of idle history (the room temperature, the outdoor
   sensor and the sun on its windows), retries every 6 hours, and shows the
   result in the `a`, `c`, `g` and `model` attributes. Type them in to pin the
   numbers instead. The fit takes its rates over hour-long blocks (a thermostat
   that reports in 0.1 C steps hides a 15 minute change), drops a sun, wall or
   ground term that comes out negative, then refines the terms on 3 hour
   simulated paths. A fit with the wrong sign (the room warming toward a
   colder outdoors, as in a zone whose thermostat is off and that the rest of
   the house drives) or an implausible loss rate is not used: the `problem`
   attribute says why.
   - **Heating rate h** is learned from the zone's calls (what the room gained
     beyond the no-heat model, per hour of call) unless you type it in.
   - **Window faces** are the faces with glass (the `g` term). **Sunlit walls
     without windows** are faces of solid wall the sun hits; they get their own
     gain `w`, lagged because a wall soaks up the sun slowly (the lag, 1.5, 3
     or 6 hours, is chosen by the fit).
   - Tick **Below ground** for a basement room: the model adds `b`, how fast the
     room trades heat with the soil. The soil is not the air: at basement depth it
     follows the air's annual wave with a smaller swing and a lag of about 70 days
     (hypothesis 03). Give a ground temperature sensor if you have one; if not, the
     ground is the wave `mean - swing * cos(2 pi (day - coldest day) / 365)` with the
     house's **ground temperature** settings (defaults 5.7, 5.6 and day 95, from
     Regina at 1.8 m; refit with `scripts/ground_temperature.py` for your site).
4. **Add contribution chart**: one per zone. Its terms still come from
   `scripts/fit_contributions.py`. It has its own `walls` band for **sunlit walls**
   (fill in `w`); it does not use the ground yet.

Each is a sub-entry; the pencil icon edits it and the sensor reloads on save.
The forms take the same settings as the YAML below, with these differences:
the rotation and roofs are set once on the integration instead of per room, dimmed lights as `light.office_main_lights=105` (entity and watts at
full), and the furnace powers are one box per state, in kW or BTU/h (cooling can
also be given in tons, 12,000 BTU/h each: heat moved, not electricity). Change the
outdoor sensor, rotation or roofs with **Reconfigure** on the integration. Entities from the web
and from YAML can both exist; use one or the other so they do not duplicate.

### From YAML

All four kinds go under one platform entry. Every key is optional except
where noted; `sensor.py` documents each one.

```yaml
sensor:
  - platform: home_thermal_lab
    outdoor_entity: sensor.edmonton_temperature   # needed for zones and contributions

    # Shadow controller (hypothesis 17): `skip` or `heat` for a call starting now.
    # Fit `model` with scripts/shadow_control.py.
    zones:
      - name: Z4 office
        climate_entity: climate.z4
        room_entity: sensor.z4_temperature
        model: {a: 0.0106, c: 0.0032, g: 0.000229}   # leave out to learn it
        windows: [E]
        # sunlit_walls: [S]            # solid walls the sun hits (own gain w, lagged)
        # below_ground: true          # basement room; ground_entity: sensor.soil_temp (optional)
        rotation: 10.4
        shade_below: 18
        # The forecast's simulated thermostat: calls start this far below the
        # setpoint (default 0.1). Add h: to the model to pin the heating rate.
        deadband: 0.1
        # Target wave (target.py): leave target_mean out to target the setpoint.
        target_mean: 21.0
        target_swing: 0.5        # degrees either side of the mean
        target_peak_hour: 15     # local clock hour of the warmest target
        target_band: 0.5         # comfort band either side

    # Heating-call statistics per zone (05, 13): state = calls in `days`;
    # attributes `low` and `stepped` hold min / median / max minutes, rise,
    # lag to the first rise, overshoot, dip and rebound.
    call_stats:
      - name: Z4 heating calls
        climate_entity: climate.z4
        days: 7
      - name: Z2 heating calls
        climate_entity: climate.z2

    # Modelled energy (kWh, total_increasing) for the energy dashboard.
    # Powers in kW per state: off, fan, heat_low, heat_high, cool.
    energy:
      - name: Furnace blower energy
        climate_entities: [climate.z1, climate.z2, climate.z3, climate.z4]
        kw: {fan: 0.04, heat_low: 0.24, heat_high: 0.24}
        power_entity: sensor.whole_house_power   # optional: learn kw from it
        learn_days: 14
      - name: Furnace gas energy   # 80,000 BTU/h input; low stage taken as 65%
        climate_entities: [climate.z1, climate.z2, climate.z3, climate.z4]
        kw: {heat_low: 15.2, heat_high: 23.4}

    # What moved each zone's temperature (chart below). Fit `terms` with
    # scripts/fit_contributions.py.
    contributions:
      - name: Z4 office
        climate_entity: climate.z4
        room_entity: sensor.z4_temperature
        other_climate_entities: [climate.z1, climate.z2, climate.z3]
        plug_entities: [sensor.office_office_computer_plug_power]
        lights: {light.office_main_lights: 105}   # 7 x 15 W LEDs, scaled by the dimmer
        terms: {a: 0.0174, c: -0.069, g: 0.00005, h: 1.67, x: 0.31, p: 1.15}
        windows: [E]
        rotation: 10.4
        shade_below: 18
```

The blower figures come from `scripts/blower_power.py` (heating adds about
0.2 kW; the fan-only blower shows no clear step, at most about 0.04 kW). Add
the energy sensors under **Settings > Dashboards > Energy**: the blower as an
individual device, the gas one as gas consumption. Both are models, not meters.

After some days, `scripts/shadow_compare.py --zone z4=sensor.shadow_z4_office`
compares the shadow log with the calls the thermostat made.

## Zone sensors

Each shadow zone has three sensors:

- **Shadow** (`sensor.shadow_<zone>`): `skip` or `heat` for a call starting now
  (hypothesis 17). It also shows how far to trust the model, as
  ClimateAdvisor's calibration label does: `grade` (`none`, `low`, `medium`,
  `high`: whether the model beats simply holding the temperature 3 hours ahead
  on the idle history, and on how much data), `method`, `bins`, `r2`,
  `error_1h`/`error_3h` against `hold_1h`/`hold_3h`, the heating rate `h`, the
  furnace's delivery lag (`furnace_lag`), the wall lag, the zones coupled into
  the model (`neighbours`), the outdoor forecast's bias and any `problem`.
- **Forecast** (`sensor.forecast_<zone>`): the room temperature 3 hours ahead
  (hypothesis 16). All the zones run forward 24 hours together, with the
  outdoor forecast and the sun on each room, each zone's thermostat simulated
  as an on/off heater (heating rate `h`; heat below the setpoint minus the
  deadband, off at the setpoint), and each zone fed its neighbours' forecast
  temperature and calls. Where there is history, the forecast (`method:
  hybrid`) is the usual day (the mean of the last 7 days at each quarter-hour,
  plus today's gap fading away) plus what the model says differs today: the
  simulation with the day's forecast and setpoints minus the simulation with
  the usual day's. A zone with no usable model gets the usual day alone
  (`method: profile`). The thermostat's program is taken to repeat
  yesterday's: the current setpoint holds until yesterday's setpoints changed
  at that time of day. The outdoor forecast is shifted by its bias against
  your outdoor sensor over the last 48 hours (at least 0.3 C, at most 4 C).
  The sensor's history is the archive of forecasts as issued: `predicted_1h`,
  the state (3 h) and `predicted_6h`, with the `start` temperature. Every 6
  hours it scores its last 7 days against the room: `error_1h`, `error_3h` and
  `error_6h` hold the mean absolute error, RMSE, bias and the error in the
  predicted change (`change_mae`) with the count. `points` (not recorded) is
  the day ahead for charts: `temp`, `outdoor`, `heat` (furnace duty), and the
  target band `lower` and `upper`, every 30 minutes.

In an open house a zone whose thermostat rarely calls is warmed mostly by the
zones that do, and a model of the zone alone fits the wrong way round (its room
"warms toward a colder outdoors"). So every zone is also fitted with two more
terms: `n (neighbour - T)`, the pull toward its neighbours' temperature, and
`x other`, warming while their calls run; the fit with them is used when it is
physical and forecasts better. By default the zone that heats most is every
other zone's neighbour, and all the others are its; set `neighbours` (a list
of thermostats) on a zone to choose.

- **Target** (`sensor.target_<zone>`): where the zone should be now, with the
  band in `lower` and `upper`. With `target_mean` set it is the target wave
  `mean + swing * cos(2 pi (hour - peak_hour) / 24)`; otherwise the
  thermostat's setpoint with the tolerance below it.

## Thermal Lab panel

The integration adds **Thermal Lab** to the sidebar: a page per zone with
tiles for now (room, target, thermostat, the shadow decision, the forecast in
3 hours and its live error), a chart of the room, outdoor (on its own axis),
setpoint and target band over 6 hours to 30 days with the forecast for the
next day after "now", the forecast made 3 hours earlier laid over what
happened, a strip of heating calls and forecast furnace duty, and a card with
the model, its grade and how well it forecasts. It follows the Home Assistant
theme and works on a phone.

The page and Chart.js are served by Home Assistant from the integration's
`frontend/` folder, so opening the panel loads nothing from the internet;
the data comes over the page's own Home Assistant connection. Chart.js is
pinned (version and SHA-256) in `frontend/vendor.json` and committed;
`uv run invoke vendor` fetches it again and checks the hash (see Development).

## Dashboard cards

For a zone on your own dashboards, `homeassistant/thermal_lab_dashboard.yaml`
is a view built from standard cards and
[apexcharts-card](https://github.com/RomRider/apexcharts-card): the tiles, the
room and outdoor with the forecast and the target band (the forecast sensor
shifted back 3 hours lays each forecast on the time it was made for), the
forecast furnace duty, a history graph of the thermostat and the shadow
decision, and a markdown card with the model. Paste it into a dashboard's raw
configuration editor and replace the entity ids.

## Contribution chart

`sensor.contributions_<zone>` holds the zone's temperature now (the baseline).
Its `points` attribute has one entry per 30 minutes for the past and next
24 hours, with each effect's running total relative to the baseline: `outdoor`
(envelope loss), `house` (heat from the rest of the house), `sun`, `furnace`,
`crossover`, `appliances` and, for the past only, `unexplained` (what the model
misses, so the past stack adds up to what was measured). Points with
`forecast: 1` are the forecast, with the furnace run by a simple thermostat at
the current setpoint. The attribute is not written to the database.

With [apexcharts-card](https://github.com/RomRider/apexcharts-card) (from HACS),
stacked columns put the gains above the baseline and the losses below it:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Z4 office, change from now (C)
graph_span: 48h
span:
  offset: +24h
now:
  show: true
  label: now
stacked: true
yaxis:
  - decimals: 1
series:
  - &term
    entity: sensor.contributions_z4_office
    name: outdoor
    type: column
    data_generator: |
      return entity.attributes.points.map(p => [new Date(p.t).getTime(), p.outdoor]);
  - <<: *term
    name: house
    data_generator: |
      return entity.attributes.points.map(p => [new Date(p.t).getTime(), p.house]);
  - <<: *term
    name: sun
    data_generator: |
      return entity.attributes.points.map(p => [new Date(p.t).getTime(), p.sun]);
  - <<: *term
    name: furnace
    data_generator: |
      return entity.attributes.points.map(p => [new Date(p.t).getTime(), p.furnace]);
  - <<: *term
    name: crossover
    data_generator: |
      return entity.attributes.points.map(p => [new Date(p.t).getTime(), p.crossover]);
  - <<: *term
    name: appliances
    data_generator: |
      return entity.attributes.points.map(p => [new Date(p.t).getTime(), p.appliances]);
  - <<: *term
    name: unexplained
    data_generator: |
      return entity.attributes.points.map(p => [new Date(p.t).getTime(), p.unexplained ?? 0]);
```

For the temperature itself (measured, then forecast), add a second card with
one `line` series returning `[time, p.temp]`. Both cards are untested.

## Development

```
uv sync
uv run invoke check     # lint, formatting and tests
uv run invoke format    # apply fixes
uv run invoke vendor    # fetch the panel's pinned Chart.js and check its hash
```

To upgrade Chart.js, change the version and URL in
`custom_components/home_thermal_lab/frontend/vendor.json`, run `invoke vendor`
(it reports the new hash and refuses the file), check and pin the hash, run it
again, and commit the file. A test checks the committed file against the pin.

## Credits

- Several ideas come from [ClimateAdvisor](https://github.com/gunkl/ClimateAdvisor)
  (MIT): rates over hour-long blocks and rejecting unphysical fits, the heating
  rate learned from calls, a simulated thermostat in the forecast, logging
  forecasts as issued and scoring them, the outdoor forecast's bias, a
  calibration grade, and the layout of the panel. The code here is our own.
- [Chart.js](https://www.chartjs.org/) (MIT) draws the panel; it is vendored in
  `frontend/`.
