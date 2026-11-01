# 02 Peak at solar noon, trough at solar midnight

**Status:** in progress

**Claim:** Daily temperature peaks at solar noon and bottoms out at solar midnight.

**Prior expectation:** Likely refuted. Air temperature typically peaks about 2-4 h after solar noon and bottoms near sunrise. Expect the lag to vary by season, cloud and wind.

**Data:** Same as 01, plus solar position (HA `sun` integration) for each site.

**Method:**
- Per day, find the time of max and min temperature and measure the offset from solar noon / solar midnight.
- Look at the distribution of offsets by season and location.

**Feeds back to:** phase offset parameter in the wave component.

## Results

Run with `python scripts/run_h01_h02.py START END [--location "name,lat,lon,kind"]`. Locations are configurable; day boundaries use local mean solar time.

Full year 2025, by season (medians; "range" is the mean warmest-minus-coolest reading):

| Location | Season | Range C | RMSE C | Fitted peak after solar noon (h) |
|---|---|---|---|---|
| Edmonton | winter / summer | 9.0 / 9.6 | 1.22 / 0.76 | 2.8 / 3.2 |
| Dieppe | winter / summer | 5.1 / 6.9 | 0.82 / 0.68 | 2.4 / 1.9 |
| Tahiti | winter / summer | 8.1 / 8.4 | 1.14 / 1.07 | 0.9 / 0.7 |

By weather, Edmonton's range is 11.9 C on sunny days against 7.9 C on rainy ones, and Dieppe's is 9.1 C against 5.3 C. Snow days at Edmonton peak earlier (0.8 h after noon).

Early reading: the sine fit is decent (RMSE about 1 C on a range of 5-12 C), the peak is reliably after solar noon rather than at it, and the lag varies by place, season and weather. Winter at Edmonton fits worst. Not yet compared with a skewed wave or a second harmonic.

Own data, January-October 2026 (Home Assistant long-term statistics, hourly; Edmonton sensor `sensor.edmonton_temperature`, indoor sensors `sensor.z1..z4_temperature`). Fitted peak after solar noon, median hours, with the daily range in brackets:

| Source | Winter | Spring | Summer | Autumn |
|---|---|---|---|---|
| Outdoor (Edmonton sensor) | 3.3 (9.1 C) | 3.0 (10.9) | 2.9 (10.0) | 2.8 (10.9) |
| Open-Meteo (same place) | 3.7 (8.3 C) | 2.9 (10.1) | 2.6 (9.1) | 3.2 (9.2) |
| Kitchen (z1) | 2.1 (4.8 C) | 2.6 (4.3) | 4.0 (3.8) | 3.5 (3.6) |
| Master bedroom (z3) | 1.7 (1.7 C) | 3.9 (2.1) | 4.8 (2.6) | 6.2 (1.8) |

The measured outdoor sensor agrees with Open-Meteo to within about 0.5 h on the peak, with a slightly larger range. Indoor rooms show a damped (1-5 C) and later wave (2-6 h after noon), more so in summer.

