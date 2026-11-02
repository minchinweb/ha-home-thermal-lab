# ha-targeting-temperature-wave

Home Assistant custom components for modelling a target daily temperature
wave, and for testing hypotheses about how a house behaves thermally.

- `custom_components/house_thermal_lab/`: runs the experiments inside Home
  Assistant, using data already in its recorder.
- `hypotheses/`: one file per hypothesis (claim, data, method, results).
- `scripts/`: command-line runners and reports. Copy `.env.example` to `.env` (git-ignored) and fill in your Home Assistant URL, token and sensor.

## Shadow controller (hypothesis 17)

`house_thermal_lab` provides a `sensor` platform that logs, for each zone, whether
a heat call starting now could be skipped (`skip`) or not (`heat`). It never
switches anything. Fit each zone's model with `scripts/shadow_control.py`
(it prints the `model:` line), copy `custom_components/house_thermal_lab/` to
your Home Assistant `custom_components/` folder, and add to `configuration.yaml`
(see the top of `custom_components/house_thermal_lab/sensor.py` for every option):

```yaml
sensor:
  - platform: house_thermal_lab
    outdoor_entity: sensor.edmonton_temperature
    zones:
      - name: Z4 office
        climate_entity: climate.z4
        room_entity: sensor.z4_temperature
        model: {a: 0.0, c: 0.0, g: 0.0}   # paste the fitted values
        walls: [E]
        rotation: 10.4
```

After some days, `scripts/shadow_compare.py --zone z4=sensor.shadow_z4_office`
compares the log with the heating calls the thermostat made. The sensor module
needs Home Assistant and has not yet been run inside it.

## Development

```
uv sync
uv run invoke check     # lint, formatting and tests
uv run invoke format    # apply fixes
```
