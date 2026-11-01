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

_No full-year results recorded yet. June 2025 smoke run: median fitted peak was 3.0 h after solar noon (Edmonton), 1.9 h (Dieppe) and 0.9 h (Tahiti), so the solar-noon peak looks refuted, and the lag varies by location._
