# 7 Heat flux of running the furnace fan

**Status:** untested

**Claim:** Temperature gradients across several rooms while the fan runs (without heating/cooling) reveal the heat flux the fan moves between rooms.

**Data:** Multi-room temperatures, fan state per zone, furnace/AC call state.

**Method:**
- Isolate fan-only periods.
- Measure how quickly inter-room differences collapse versus the no-fan baseline (09).
- Estimate per-zone fan flux coefficients.

**Caveats:** Fan-only periods may be rare; may need to schedule deliberate experiments.

**Zone board:** fan-only calls only take effect when no zone calls for heat or AC, and then all zones are active, so fan periods are whole-house, not per zone. See the zone-board note in 05.

## Results

_none yet_
