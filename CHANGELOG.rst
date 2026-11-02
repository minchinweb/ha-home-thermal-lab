Changelog
=========

.. release:: unreleased

  - :feature:`-` Shadow-mode furnace controller: which calls could have been skipped, with a no-heat forecast check (hypothesis 17).
  - :feature:`-` Next-day room temperature backtest against persistence, yesterday and profile baselines, with outdoor and sun terms (hypothesis 16).
  - :feature:`-` Horizon-profile (shading) fit per room with leave-one-day-out validation.
  - :feature:`-` Per-room window and roof solar model with clear-sky term, tilted-plane irradiance and house rotation from OpenStreetMap.
  - :feature:`-` Irradiance loader, sun azimuth and solar-gain test by window face (hypothesis 11).
  - :feature:`-` Ground-temperature test (hypothesis 03) and occupancy test (hypothesis 15).
  - :feature:`-` Door-state test against the S basement bedroom door contact (hypothesis 09).
  - :feature:`-` Wind loader and wind-loss test (hypothesis 12).
  - :feature:`-` Furnace stage (W1/W2) summary from Ecobee equipment state.
  - :feature:`-` Thermal momentum script: cool-down tau, wave lag, static flux.
  - :feature:`-` Hypothesis tracker, Open-Meteo loader and sine-wave fit.
  - :feature:`-` Year-long analysis by season and weather, daily range, percentile-band plots and a Home Assistant history loader.
  - :feature:`-` Furnace run detection, room response, crossover bleed, room regression, bleed matrix, appliance and stove-proxy regressions, labelled-event response and whole-house power checks; Home Assistant long-term statistics over the websocket API, several entities per run, time-weighted hourly history; settings from a git-ignored `.env` file; ground temperature and envelope flux hypotheses.
