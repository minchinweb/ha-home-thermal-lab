# 09 Door open/closed from inter-room gradients

**Status:** untested

**Claim:** The temperature difference between two connected rooms, and how fast it decays, indicates whether the door between them is open or closed.

**Data:** Paired room temperatures; ground truth from door contact sensors if any, otherwise manual logging for a labelled set.

**Method:**
- Classification problem. Features: gradient, decay rate of the gradient, rate-of-change correlation.
- Needs labelled examples; collect by logging door state for a few weeks.

**Feeds:** 10 (coupling depends on door state).

## Results

_none yet_
