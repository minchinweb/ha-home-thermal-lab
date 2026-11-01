# 5 Furnace heating power from room temperature gradient

**Status:** untested

**Claim:** Observing the temperature rise in a room while the furnace runs lets us estimate the furnace's effective heating power.

**Data:** Room temperature sensors, furnace/zone call states, outdoor temperature, electricity use.

**Method:**
- Select clean windows: overnight, no solar gain, one zone calling.
- Fit `C * dT/dt = P_furnace*duty - UA*(T_in - T_out) + coupling terms`.
- Estimate effective power per zone, including spillover into non-calling zones.

**Caveats:** Zone valve leakage; unknown thermal mass C (fit jointly, or from cooldown periods).

## Results

_none yet_
