# 12 Predict heat loss from wind speed and direction

**Status:** untested

**Claim:** Heat loss (and infiltration) of a room depends on wind speed and direction relative to its exposed faces.

**Data:** Wind speed/direction from weather, room temperatures, outdoor temperature.

**Method:** Fit `UA` as a function of wind on each face: `UA = UA0 + k * v^n * f(angle)`. Use night windows to avoid solar gain.

## Results

_none yet_
