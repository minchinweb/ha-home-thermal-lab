# 01 Daily temperature is roughly a sine wave

**Status:** in progress

**Claim:** Outdoor temperature over a day is well approximated by a sinusoid with a 24 h period.

**Data:**
- Home Assistant outdoor/local weather sensor history.
- Open-Meteo historical hourly data for comparison sites: Tahiti, Edmonton, Dieppe (France), plus others across latitudes and seasons.

**Method:**
- Fit `T(t) = mean + A*sin(2*pi*(t - phase)/24h)` per day.
- Compare against alternatives (skewed/two-segment wave, sine plus second harmonic).
- Metrics: RMSE, residual structure, and how fit varies by season, latitude and cloud cover.

**Feeds back to:** the wave component's target shape.

## Results

Run with `python scripts/run_h01_h02.py START END [--location "name,lat,lon,kind"]`. Locations are configurable; day boundaries use local mean solar time.

_No full-year results recorded yet. June 2025 smoke run: median fitted peak was 3.0 h after solar noon (Edmonton), 1.9 h (Dieppe) and 0.9 h (Tahiti), so the solar-noon peak looks refuted, and the lag varies by location._
