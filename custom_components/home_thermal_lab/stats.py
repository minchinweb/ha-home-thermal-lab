"""Small statistics helpers (standard library only)."""

from __future__ import annotations


def percentile(values: list[float], q: float) -> float:
    """Percentile by linear interpolation between closest ranks.

    Args:
        values: Non-empty sample.
        q: Percentile, from 0 to 100.

    Returns:
        The interpolated value.

    Raises:
        ValueError: If ``values`` is empty or ``q`` is out of range.
    """
    if not values:
        raise ValueError("no values")
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
