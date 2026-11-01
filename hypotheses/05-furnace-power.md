# 5 Furnace heating power from room temperature gradient

**Status:** untested

**Claim:** Observing the temperature rise in a room while the furnace runs lets us estimate the furnace's effective heating power.

**Data:** Room temperature sensors, furnace/zone call states, outdoor temperature, electricity use.

**Our entities:** four zones (`z1` kitchen, `z2` basement, `z3` master bedroom, `z4` office). The call state is the `hvac_action` attribute of `climate.z1`..`z4` (`heating`, `cooling`, `fan`, `idle`); the `binary_sensor.zN_furnace_heating` sensors never turned on in the history we could read, so don't rely on them. Whole-house power is `sensor.eagle_00bb9c_power_demand`. Run `scripts/hvac_overview.py` for run counts and durations.

**Method:**
- Select clean windows: overnight, no solar gain, one zone calling.
- Fit `C * dT/dt = P_furnace*duty - UA*(T_in - T_out) + coupling terms`.
- Estimate effective power per zone, including spillover into non-calling zones.

**Caveats:** Zone valve leakage; unknown thermal mass C (fit jointly, or from cooldown periods).

## Results

First look (9 days, late October 2026; `scripts/hvac_overview.py`): z4 (office) heated 3.2 h/day in about 11 runs (median 9 min, longest 84 min) on every day. z2 (basement) heated 0.8 h/day in 6 runs (median 6 min). z1 and z3 never called for heat. No cooling. Every zone also shows long fan-only periods (5-14 h/day), including runs of 6-12 h, which will matter for 07 (fan flux).
