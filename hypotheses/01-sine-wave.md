# 01 Daily temperature is roughly a sine wave

**Status:** untested

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

_none yet_
