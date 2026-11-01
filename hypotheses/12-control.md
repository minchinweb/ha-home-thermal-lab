# 12 Use the forecast to decide whether to run furnace/AC

**Status:** untested

**Claim:** A forecast lets us decide to run or skip the furnace/AC now to avoid later overshoot (e.g. skip heating in the morning if afternoon sun will warm the kitchen).

**Method:**
- Rule or model-predictive controller on top of 11, minimising comfort deviation from the wave target and energy use.
- First run in shadow mode: log what it would have done and compare with what the thermostat did.
- Only then let it actuate.

**Depends on:** 11, and the wave component as the target.

## Results

_none yet_
