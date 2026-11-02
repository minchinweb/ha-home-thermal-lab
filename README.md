# ha-home-thermal-lab

Home Assistant custom components for modelling a target daily temperature
wave, and for testing hypotheses about how a house behaves thermally.

- `custom_components/home_thermal_lab/`: runs the experiments inside Home
  Assistant, using data already in its recorder.
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

## Sensors

### From the web interface

Add the integration, choose the outdoor temperature sensor, then use **Add
shadow zone**, **Add heating-call statistics**, **Add furnace energy** or **Add
contribution chart** on the integration's page. Each is a sub-entry; the pencil
icon edits it and the sensor reloads on save. The forms take the same settings
as the YAML below, with these differences: roofs are typed as `S 30, W 30`
(face and pitch), dimmed lights as `light.office_main_lights=105` (entity and
watts at full), and the furnace powers are one box per state. Change the
outdoor sensor with **Reconfigure** on the integration. Entities from the web
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
        model: {a: 0.0106, c: 0.0032, g: 0.000229}
        walls: [E]
        rotation: 10.4
        shade_below: 18

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
        walls: [E]
        rotation: 10.4
        shade_below: 18
```

The blower figures come from `scripts/blower_power.py` (heating adds about
0.2 kW; the fan-only blower shows no clear step, at most about 0.04 kW). Add
the energy sensors under **Settings > Dashboards > Energy**: the blower as an
individual device, the gas one as gas consumption. Both are models, not meters.

After some days, `scripts/shadow_compare.py --zone z4=sensor.shadow_z4_office`
compares the shadow log with the calls the thermostat made.

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
```
