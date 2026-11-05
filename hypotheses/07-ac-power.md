# 07 AC cooling power from room temperature gradient

**Status:** untested

**Claim:** Same as 05, for the AC: temperature fall during cooling gives effective cooling power.

**Data:** Room temperatures, AC/zone call states, outdoor temperature, solar data.

**Method:** As 03, but cooling windows coincide with solar gain, so 11 results are needed to separate them. Prefer evening/night cooling runs first.

**Caveats:** AC electrical draw is not separately metered; derive runtime from call state.

**Zone board:** the AC runs whenever any zone calls for cooling, and it alternates with heat when both are requested. See the zone-board note in 05.

**From the prior-art review (4 November 2026; see `docs/prior-art-review.md`):**
- The hot roof is a heat source the method above leaves out. Manual J's `cooling_load` (`manual_j.py` in ha-manual-j) gives opaque surfaces no sun, so the upstairs rooms (Z3) will look like they need more cooling power than the AC delivers. Eldr models it as a sol-air attic temperature, outdoor + about 28 K × 0.85 (3.66 times the outdoor ΔT on its test house), and calls that its least certain number. Prefer a measured attic temperature: an attic sensor before the cooling season would replace the estimate.
- `cooling_load` clips every surface's gain at zero. That is right for the basement in summer but hides a surface that cools the room at night. Fit 07 on unclipped terms, and decide the clipping for the design load separately.
- Use the configured supply-air drop (`cool_rise_k`), not a fixed 20 °F as Eldr does.

## Results

_none yet_
