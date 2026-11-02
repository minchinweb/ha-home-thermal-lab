"""Learn a house's numbers from its own history (standard library only).

Two fits the web setup can run on the recorder instead of asking for numbers:

* ``fit_no_heat``: a zone's no-heat model ``dT/dt = a * (outdoor - room) +
  b * (ground - room) + c + g * light + w * wall_light`` (hypothesis 17; the
  ground and wall terms only when the room has them), by least squares on the
  bins where the furnace was idle. ``scripts/shadow_control.py`` does the same
  with numpy.
* ``edge_steps`` and ``blower_kw``: the electrical power of the blower, from the
  steps in whole-house power when the furnace changes state
  (``scripts/blower_power.py`` prints the same steps).
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import statistics

from .hvac import Run

Series = list[tuple[datetime, float]]

WALL_TAU_HOURS = 3.0  # a sunlit wall soaks up the sun and gives it up slowly


def lag(
    values: list[float],
    step_hours: float,
    tau_hours: float,
    start: float | None = None,
) -> list[float]:
    """Smooth a series as a wall would: a first-order lag.

    It starts from ``start``, or from the first value when that is None.
    """
    if not values:
        return []
    alpha = 1.0 - math.exp(-step_hours / tau_hours)
    held = values[0] if start is None else start
    out = []
    for value in values:
        held += alpha * (value - held)
        out.append(held)
    return out


def bin_held(series: Series, start: datetime, bins: int, width: timedelta) -> list:
    """Time-weighted mean of a held-value series in each bin (None if no data).

    Each reading holds until the next one, so a sensor that only reports on a
    change still fills the bins in between.
    """
    seconds = width.total_seconds()
    sums = [0.0] * bins
    covered = [0.0] * bins
    ordered = sorted(series)
    for k, (when, value) in enumerate(ordered):
        until = ordered[k + 1][0] if k + 1 < len(ordered) else start + bins * width
        first = max(int((when - start) / width), 0)
        last = min(int((until - start) / width), bins - 1)
        for i in range(first, last + 1):
            lo = max(when, start + i * width)
            hi = min(until, start + (i + 1) * width)
            span = (hi - lo).total_seconds()
            if span > 0:
                sums[i] += value * span
                covered[i] += span
    return [
        sums[i] / covered[i] if covered[i] >= 0.5 * seconds else None
        for i in range(bins)
    ]


def bin_fraction(
    runs: list[Run], start: datetime, bins: int, width: timedelta
) -> list[float]:
    """Fraction of each bin covered by ``runs``."""
    out = [0.0] * bins
    seconds = width.total_seconds()
    for run in runs:
        first = max(int((run.start - start) / width), 0)
        last = min(int((run.end - start) / width), bins - 1)
        for i in range(first, last + 1):
            lo = start + i * width
            overlap = (min(run.end, lo + width) - max(run.start, lo)).total_seconds()
            if overlap > 0:
                out[i] += overlap / seconds
    return [min(v, 1.0) for v in out]


def least_squares(columns: list[list[float]], y: list[float]) -> list[float] | None:
    """Solve ``y ~ sum(beta_k * columns[k])`` by the normal equations.

    Returns None when the columns are linearly dependent.
    """
    n = len(columns)
    a = [
        [
            sum(p * q for p, q in zip(columns[i], columns[j], strict=True))
            for j in range(n)
        ]
        + [sum(p * q for p, q in zip(columns[i], y, strict=True))]
        for i in range(n)
    ]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(n):
            if r != col:
                factor = a[r][col] / a[col][col]
                a[r] = [x - factor * y_ for x, y_ in zip(a[r], a[col], strict=True)]
    return [a[i][n] / a[i][i] for i in range(n)]


@dataclass(frozen=True)
class NoHeatFit:
    """A fitted no-heat model and how much data it rests on.

    Attributes:
        a: Cooling rate toward the outdoor temperature, per hour.
        c: Constant heat gain or loss, C per hour.
        g: Warming per W/m2 of light on the room's windows and roof, C per hour.
        bins: Idle bins used.
        b: Coupling to the ground, per hour (0 for a room above ground).
        w: Warming per W/m2 of (lagged) light on sunlit solid walls, C per hour.
    """

    a: float
    c: float
    g: float
    bins: int
    b: float = 0.0
    w: float = 0.0


def fit_no_heat(
    room: list,
    outdoor: list,
    light: list[float],
    heating: list[float],
    hours: float,
    min_bins: int = 60,
    wall: list[float] | None = None,
    ground: list | None = None,
) -> NoHeatFit | None:
    """Fit the no-heat model on idle bins.

    Args:
        room: Room temperature per bin (None when unknown).
        outdoor: Outdoor temperature per bin (None when unknown).
        light: Light on the room's windows and roof per bin.
        heating: Fraction of each bin the furnace heated this zone.
        hours: Bin width in hours.
        min_bins: Fewest idle bins to trust a fit.
        wall: Lagged light on the room's sunlit solid walls per bin, if any.
        ground: Ground temperature per bin (None when unknown), for a room
            below ground.

    Returns:
        The fit, or None if there is too little idle data.
    """
    rows = []
    for i in range(len(room) - 1):
        if (
            room[i] is None
            or room[i + 1] is None
            or outdoor[i] is None
            or heating[i] > 0
            or (i > 0 and heating[i - 1] > 0)
            or (ground is not None and ground[i] is None)
        ):
            continue
        rows.append(
            (
                outdoor[i] - room[i],
                (room[i + 1] - room[i]) / hours,
                light[i],
                0.0 if wall is None else wall[i],
                0.0 if ground is None else ground[i] - room[i],
            )
        )
    if len(rows) < min_bins:
        return None
    y = [r[1] for r in rows]
    cols = [[r[0] for r in rows], [1.0] * len(rows)]
    names = []
    for name, index, wanted in (
        ("g", 2, any(r[2] > 0 for r in rows)),
        ("w", 3, any(r[3] > 0 for r in rows)),
        ("b", 4, ground is not None),
    ):
        if wanted:
            names.append(name)
            cols.append([r[index] for r in rows])
    beta = least_squares(cols, y)
    if beta is None:
        return None
    got = dict(zip(names, beta[2:], strict=True))
    return NoHeatFit(
        beta[0],
        beta[1],
        got.get("g", 0.0),
        len(rows),
        got.get("b", 0.0),
        got.get("w", 0.0),
    )


def _window(
    times: list[datetime], values: list[float], lo: datetime, hi: datetime
) -> list[float]:
    return values[bisect_left(times, lo) : bisect_left(times, hi)]


def edge_steps(
    power: Series,
    heat: list[Run],
    fan: list[Run],
    high: list[Run],
    edge_minutes: float = 2.0,
    noise_kw: float = 0.3,
) -> dict[str, list[float]]:
    """Steps in whole-house power (kW) when the furnace changes state.

    Each is the median power in ``edge_minutes`` after minus before. The kinds:
    ``fan on`` and ``fan off`` (the blower alone), ``heat on`` and ``heat off``
    (heating while the blower already runs) and ``to high stage``. Edges near
    another edge, or where power moved more than ``noise_kw`` on either side
    (another appliance), are skipped.

    Args:
        power: Whole-house power readings, (UTC time, kW), oldest first.
        heat: Merged runs of any zone heating.
        fan: Merged runs of the blower.
        high: Merged runs of the high stage.
        edge_minutes: Window either side of an edge.
        noise_kw: Largest spread allowed in either window.
    """
    edge = timedelta(minutes=edge_minutes)
    ordered = sorted(power)
    times = [t for t, _ in ordered]
    values = [v for _, v in ordered]

    def heating_near(t: datetime) -> bool:
        return any(r.start - edge <= t <= r.end + edge for r in heat)

    def blower_on(t: datetime) -> bool:
        return any(r.start <= t < r.end for r in fan)

    events = {
        "fan on": [r.start for r in fan if not heating_near(r.start)],
        "fan off": [r.end for r in fan if not heating_near(r.end)],
        "heat on": [r.start for r in heat if blower_on(r.start - edge)],
        "heat off": [r.end for r in heat if blower_on(r.end + edge)],
        "to high stage": [r.start for r in high],
    }
    everything = sorted(t for ts in events.values() for t in ts)
    out: dict[str, list[float]] = {}
    for kind, moments in events.items():
        steps = []
        for t in moments:
            if any(
                0 < abs((o - t).total_seconds()) < edge_minutes * 60 for o in everything
            ):
                continue
            before = _window(times, values, t - edge, t)
            after = _window(times, values, t, t + edge)
            if len(before) < 2 or len(after) < 2:
                continue
            if (
                max(before) - min(before) > noise_kw
                or max(after) - min(after) > noise_kw
            ):
                continue
            steps.append(statistics.median(after) - statistics.median(before))
        out[kind] = steps
    return out


def blower_kw(
    steps: dict[str, list[float]], min_edges: int = 5
) -> tuple[dict[str, float], dict[str, int]]:
    """Powers per furnace state (kW) from the edge steps.

    The fan-only power is the median ``fan on`` step (``fan off`` reversed, if
    that has more edges). Heating adds the median ``heat on`` / ``heat off``
    step on top of the fan, and the high stage adds the median ``to high stage``
    step on top of that. A power is left out when its step has fewer than
    ``min_edges`` clean edges.

    Returns:
        The powers learned, and the number of edges behind each step.
    """
    counts = {kind: len(v) for kind, v in steps.items()}

    def median(*kinds: str) -> float | None:
        values: list[float] = []
        for kind in kinds:
            sign = -1.0 if kind.endswith("off") else 1.0
            values += [sign * v for v in steps.get(kind, [])]
        return statistics.median(values) if len(values) >= min_edges else None

    out: dict[str, float] = {}
    fan = median("fan on", "fan off")
    heat = median("heat on", "heat off")
    high = median("to high stage")
    if fan is not None:
        out["fan"] = fan
    if heat is not None:
        out["heat_low"] = (fan or 0.0) + heat
        if high is not None:
            out["heat_high"] = out["heat_low"] + high
    return out, counts
