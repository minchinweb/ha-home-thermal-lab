"""Fit a 24 h sinusoid to a day of temperature samples (hypotheses 01 and 02).

Pure standard library, so it runs inside Home Assistant without extra
requirements. ``T(t) = mean + amplitude * cos(w * (t - peak_hour))`` with a
fixed 24 h period, which is linear in (mean, sin, cos) and solved exactly by
least squares.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

_OMEGA = 2 * math.pi / 24.0  # radians per hour


@dataclass(frozen=True)
class WaveFit:
    """Result of fitting one day."""

    mean: float
    amplitude: float
    peak_hour: float  # hours after local midnight, in [0, 24)
    rmse: float
    n: int

    @property
    def trough_hour(self) -> float:
        """Hour of the fitted minimum (always 12 h after the peak)."""
        return (self.peak_hour + 12.0) % 24.0


def _solve3(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve a 3x3 linear system by Gaussian elimination with pivoting."""
    m = [[*row, rhs] for row, rhs in zip(a, b, strict=True)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-12:
            raise ValueError("samples do not span enough of the day to fit")
        m[i], m[p] = m[p], m[i]
        for r in range(i + 1, 3):
            f = m[r][i] / m[i][i]
            for c in range(i, 4):
                m[r][c] -= f * m[i][c]
    x = [0.0] * 3
    for i in (2, 1, 0):
        x[i] = (m[i][3] - sum(m[i][c] * x[c] for c in range(i + 1, 3))) / m[i][i]
    return x


def fit_day(samples: list[tuple[float, float]]) -> WaveFit:
    """Fit ``samples`` of ``(hour_of_day, temperature)`` with a 24 h sinusoid."""
    if len(samples) < 4:
        raise ValueError("need at least 4 samples")
    rows = [(1.0, math.sin(_OMEGA * h), math.cos(_OMEGA * h)) for h, _ in samples]
    ys = [t for _, t in samples]
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    aty = [sum(r[i] * y for r, y in zip(rows, ys, strict=True)) for i in range(3)]
    mean, s, c = _solve3(ata, aty)
    amplitude = math.hypot(s, c)
    peak_hour = (math.atan2(s, c) / _OMEGA) % 24.0
    sse = sum(
        (y - (mean + s * r[1] + c * r[2])) ** 2 for r, y in zip(rows, ys, strict=True)
    )
    return WaveFit(mean, amplitude, peak_hour, math.sqrt(sse / len(ys)), len(ys))


def signed_offset_hours(hour: float, reference: float) -> float:
    """Offset ``hour - reference`` wrapped to [-12, 12) hours."""
    return (hour - reference + 12.0) % 24.0 - 12.0
