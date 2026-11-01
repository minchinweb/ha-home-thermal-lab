# ha-targeting-temperature-wave

Home Assistant custom components for modelling a target daily temperature
wave, and for testing hypotheses about how a house behaves thermally.

- `custom_components/house_thermal_lab/`: runs the experiments inside Home
  Assistant, using data already in its recorder.
- `hypotheses/`: one file per hypothesis (claim, data, method, results).
- `scripts/`: command-line runners and reports.

## Development

```
uv sync
uv run invoke check     # lint, formatting and tests
uv run invoke format    # apply fixes
```
