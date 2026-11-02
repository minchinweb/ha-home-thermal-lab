Changelog
=========

.. release:: unreleased

  - :feature:`-` Renamed: repository ``ha-home-thermal-lab``, integration domain ``home_thermal_lab`` (was ``house_thermal_lab``); household names replaced by room labels, with real entity ids in ``.env`` (``HA_ENTITY_ALIASES``).
  - :feature:`-` No-fan nights experiment (Home Assistant automations, hypotheses 08 and 10), detected in the fan mixing script.
  - :feature:`-` Office lights on a dimmer as a modelled load (scripts and the contribution sensor's ``lights`` option); HACS "add repository" button in the README.
  - :feature:`-` Package the integration for HACS (``hacs.json``, manifest version and issue tracker, HACS and hassfest validation workflow); no ``async_setup`` needed.
  - :feature:`-` New sensors: heating-call statistics per zone, modelled furnace energy (blower and gas) for the energy dashboard, and per-zone contribution split for a stacked chart.
  - :feature:`-` Contribution split (history and forecast) and its fitting script; furnace energy meter; heating-call analysis (lag, rise, overshoot, dip, rebound).
  - :feature:`-` Fan mixing test and its review (hypothesis 08), door-edge study at 5-minute bins (09), room network fit (10), furnace lag (13), plug-load heat and blower power (14), plug terms in the occupancy fit (15), shower log from bathroom humidity (18).
  - :feature:`-` Tampa, Sherbrooke and Victoria (city, not the airport) as example locations; retry the Open-Meteo archive when it is overloaded.
  - :feature:`-` Shadow-controller sensors for Home Assistant, forecast loader and log-versus-thermostat comparison.
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
