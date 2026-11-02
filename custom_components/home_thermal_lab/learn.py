"""Learn a house's numbers from its own history (standard library only).

Two fits the web setup can run on the recorder instead of asking for numbers:

* ``fit_no_heat``: a zone's no-heat model ``dT/dt = a * (outdoor - room) +
  b * (ground - room) + c + g * light + w * wall_light`` (hypothesis 17; the
  ground and wall terms only when the room has them), by least squares on the
  bins where the furnace was idle, optionally over hour-long blocks.
  ``scripts/shadow_control.py`` does the same with numpy. ``problem`` refuses
  unphysical fits, ``refine_multistep`` refines a fit on simulated paths,
  ``fit_heat_rate`` learns the heating rate from the calls, ``skill`` compares
  the model with holding the temperature, and ``grade`` sums that up.
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
from .shadow import ZoneModel, step

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
        r2: Share of the variance in the (block) rates the fit explains.
        method: ``one-step`` (rates over single bins), ``block`` (rates over
            blocks of bins) or ``multi-step`` (refined on simulated paths).
    """

    a: float
    c: float
    g: float
    bins: int
    b: float = 0.0
    w: float = 0.0
    r2: float = 0.0
    method: str = "one-step"


# A plausible cooling rate: at 0 or below heat flows the wrong way; above 0.5
# per hour a room would lose most of its difference with outdoors in two hours.
A_MAX = 0.5


def _block_rows(
    room: list,
    outdoor: list,
    light: list[float],
    heating: list[float],
    hours: float,
    wall: list[float] | None,
    ground: list | None,
    block: int,
) -> list[tuple[float, float, float, float, float]]:
    """(outdoor - room, rate, light, wall light, ground - room) per idle block."""
    rows = []
    i = 0
    n = len(room)
    while i + block < n:
        span = range(i, i + block)
        if (
            any(room[j] is None or outdoor[j] is None for j in span)
            or room[i + block] is None
            or any(heating[j] > 0 for j in span)
            or (i > 0 and heating[i - 1] > 0)
            or (ground is not None and any(ground[j] is None for j in span))
        ):
            i += 1
            continue
        mean_room = sum(room[j] for j in span) / block
        rows.append(
            (
                sum(outdoor[j] for j in span) / block - mean_room,
                (room[i + block] - room[i]) / (hours * block),
                sum(light[j] for j in span) / block,
                0.0 if wall is None else sum(wall[j] for j in span) / block,
                0.0
                if ground is None
                else sum(ground[j] for j in span) / block - mean_room,
            )
        )
        i += block
    return rows


def fit_no_heat(
    room: list,
    outdoor: list,
    light: list[float],
    heating: list[float],
    hours: float,
    min_bins: int = 60,
    wall: list[float] | None = None,
    ground: list | None = None,
    block: int = 1,
) -> NoHeatFit | None:
    """Fit the no-heat model on idle bins.

    With ``block`` above 1 each rate is taken over ``block`` bins in a row (and
    the drivers averaged over them), the way ClimateAdvisor averages its
    readings into hour blocks: a thermostat that reports in 0.1 C steps hides a
    0.02 C change over 15 minutes, but much less of a 0.08 C change over an hour.

    A sun, wall or ground term that comes out negative is not physical; it is
    dropped and the rest refitted.

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
        block: Bins per rate.

    Returns:
        The fit, or None if there is too little idle data.
    """
    rows = _block_rows(room, outdoor, light, heating, hours, wall, ground, block)
    if len(rows) * block < min_bins:
        return None
    y = [r[1] for r in rows]
    wanted = {
        "g": any(r[2] > 0 for r in rows),
        "w": any(r[3] > 0 for r in rows),
        "b": ground is not None,
    }
    index = {"g": 2, "w": 3, "b": 4}
    while True:
        names = [k for k, on in wanted.items() if on]
        cols = [[r[0] for r in rows], [1.0] * len(rows)]
        cols += [[r[index[k]] for r in rows] for k in names]
        beta = least_squares(cols, y)
        if beta is None:
            return None
        got = dict(zip(names, beta[2:], strict=True))
        negative = [k for k, v in got.items() if v < 0]
        if not negative:
            break
        wanted[negative[0]] = False
    fitted = [
        sum(b * col[j] for b, col in zip(beta, cols, strict=True))
        for j in range(len(y))
    ]
    mean_y = sum(y) / len(y)
    total = sum((v - mean_y) ** 2 for v in y)
    sse = sum((v - f) ** 2 for v, f in zip(y, fitted, strict=True))
    return NoHeatFit(
        beta[0],
        beta[1],
        got.get("g", 0.0),
        len(rows) * block,
        got.get("b", 0.0),
        got.get("w", 0.0),
        r2=1.0 - sse / total if total > 0 else 0.0,
        method="one-step" if block == 1 else "block",
    )


def problem(fit: NoHeatFit | None) -> str | None:
    """Why a fit cannot be used (as ClimateAdvisor rejects its fits), or None.

    ``too little idle data`` when there is no fit; ``wrong sign`` when the room
    would warm toward a colder outdoors (a <= 0, as fitted for zones whose
    thermostat is off and that are driven by the rest of the house); ``out of
    range`` when a or b is implausibly large.
    """
    if fit is None:
        return "too little idle data"
    if fit.a <= 0:
        return "wrong sign"
    if fit.a > A_MAX or fit.b > A_MAX:
        return "out of range"
    return None


def fit_with_wall_lag(
    room: list,
    outdoor: list,
    light: list[float],
    heating: list[float],
    hours: float,
    raw_wall: list[float],
    taus: tuple[float, ...] = (1.5, 3.0, 6.0),
    **kwargs,
) -> tuple[NoHeatFit | None, float]:
    """Fit with each wall lag in ``taus`` and keep the one that fits best.

    ClimateAdvisor learns the lag of its sun term from the hour the room peaks;
    here the sunlit walls' lag (a first-order delay of the light on them) is
    chosen by the fit itself. Returns the fit and its lag in hours.
    """
    best: tuple[NoHeatFit | None, float] = (None, taus[0])
    for tau in taus:
        fit = fit_no_heat(
            room,
            outdoor,
            light,
            heating,
            hours,
            wall=lag(raw_wall, hours, tau),
            **kwargs,
        )
        if fit is not None and (best[0] is None or fit.r2 > best[0].r2):
            best = (fit, tau)
    return best


@dataclass(frozen=True)
class ZoneData:
    """A zone's binned history, for the checks and fits that simulate.

    Attributes:
        room: Room temperature per bin (None when unknown).
        outdoor: Outdoor temperature per bin (None when unknown).
        light: Light on the windows and roof per bin.
        heating: Fraction of each bin the zone's furnace call ran.
        hours: Bin width in hours.
        wall: Lagged light on sunlit solid walls per bin, if any.
        ground: Ground temperature per bin, for a room below ground.
    """

    room: list
    outdoor: list
    light: list[float]
    heating: list[float]
    hours: float
    wall: list[float] | None = None
    ground: list | None = None


def _usable(data: ZoneData, j: int) -> bool:
    return data.outdoor[j] is not None and (
        data.ground is None or data.ground[j] is not None
    )


def idle_starts(data: ZoneData, steps: int, every: int = 1) -> list[int]:
    """Bins from which the room was idle and its drivers known for ``steps`` bins."""
    out = []
    n = len(data.room)
    for i in range(1, n - steps, every):
        if data.room[i] is None:
            continue
        if any(data.heating[j] > 0 for j in range(i - 1, i + steps)):
            continue
        if all(_usable(data, j) for j in range(i, i + steps)):
            out.append(i)
    return out


def simulate_from(model: ZoneModel, data: ZoneData, i: int, steps: int) -> list:
    """The model's no-heat path from bin ``i`` over ``steps`` bins."""
    path = [data.room[i]]
    for j in range(i, i + steps):
        path.append(
            step(
                path[-1],
                data.outdoor[j],
                data.light[j],
                model,
                data.hours,
                0.0 if data.wall is None else data.wall[j],
                0.0 if data.ground is None else data.ground[j],
            )
        )
    return path


@dataclass(frozen=True)
class Skill:
    """Forecast error of a model at one lead, against holding the temperature.

    Attributes:
        model: RMSE of the model's no-heat path, C.
        hold: RMSE of holding the starting temperature, C.
        n: Starts compared.
    """

    model: float
    hold: float
    n: int


def skill(
    model: ZoneModel, data: ZoneData, leads: tuple[int, ...] = (4, 12)
) -> dict[int, Skill]:
    """RMSE at each lead (in bins) from every idle start (hypothesis 17's check)."""
    longest = max(leads)
    errs: dict[int, list[float]] = {k: [] for k in leads}
    holds: dict[int, list[float]] = {k: [] for k in leads}
    for i in idle_starts(data, longest):
        path = simulate_from(model, data, i, longest)
        for k in leads:
            actual = data.room[i + k]
            if actual is None:
                continue
            errs[k].append(path[k] - actual)
            holds[k].append(data.room[i] - actual)
    out = {}
    for k in leads:
        if errs[k]:
            out[k] = Skill(
                math.sqrt(sum(e * e for e in errs[k]) / len(errs[k])),
                math.sqrt(sum(e * e for e in holds[k]) / len(holds[k])),
                len(errs[k]),
            )
    return out


def model_of(fit: NoHeatFit, h: float = 0.0) -> ZoneModel:
    """The simulation model for a fit (with a heating rate, if known)."""
    return ZoneModel(fit.a, fit.c, fit.g, fit.b, fit.w, h)


def refine_multistep(
    fit: NoHeatFit,
    data: ZoneData,
    steps: int = 12,
    every: int = 4,
    iterations: int = 12,
) -> NoHeatFit:
    """Refine a fit to minimise the error of whole simulated paths.

    The one-step (or block) fit minimises the error of each rate; what the
    shadow controller and the day forecast need is the error hours ahead.
    Starting from the fit, a damped Gauss-Newton search (Levenberg-Marquardt)
    adjusts the terms to minimise the squared error of the no-heat path at every
    lead up to ``steps`` bins, from idle starts ``every`` bins apart. A step that
    would make a term unphysical (a <= 0 or above ``A_MAX``, or a negative sun,
    wall or ground term) is refused, so an unphysical fit is returned as it is.

    Returns the refined fit (``method="multi-step"``), or the fit unchanged if
    there are too few starts or nothing improves.
    """
    starts = idle_starts(data, steps, every)
    if len(starts) < 10:
        return fit
    names = ["a", "c"]
    if any(v > 0 for v in data.light):
        names.append("g")
    if data.wall is not None and any(v > 0 for v in data.wall):
        names.append("w")
    if data.ground is not None:
        names.append("b")
    theta = [getattr(fit, k) for k in names]

    def residuals(values: list[float]) -> list[float]:
        model = ZoneModel(**dict(zip(names, values, strict=True)))
        out = []
        for i in starts:
            path = simulate_from(model, data, i, steps)
            for k in range(1, steps + 1):
                actual = data.room[i + k]
                if actual is not None:
                    out.append(path[k] - actual)
        return out

    def physical(values: list[float]) -> bool:
        got = dict(zip(names, values, strict=True))
        return 0 < got["a"] <= A_MAX and all(
            got.get(k, 0.0) >= 0 for k in ("g", "w", "b")
        )

    if not physical(theta):
        return fit
    r = residuals(theta)
    sse = sum(v * v for v in r)
    damping = 1e-3
    improved = False
    for _ in range(iterations):
        jac = []
        for p in range(len(theta)):
            eps = 1e-6 + 1e-3 * abs(theta[p])
            moved = list(theta)
            moved[p] += eps
            jac.append(
                [(q - v) / eps for q, v in zip(residuals(moved), r, strict=True)]
            )
        jtj = [
            [sum(x * y for x, y in zip(jp, jq, strict=True)) for jq in jac]
            for jp in jac
        ]
        jtr = [sum(x * y for x, y in zip(jp, r, strict=True)) for jp in jac]
        accepted = False
        for _try in range(8):
            damped = [list(row) for row in jtj]
            for p in range(len(theta)):
                damped[p][p] += damping * jtj[p][p]
            delta = least_squares_matrix(damped, [-v for v in jtr])
            if delta is None:
                break
            trial = [t + d for t, d in zip(theta, delta, strict=True)]
            if physical(trial):
                r_trial = residuals(trial)
                sse_trial = sum(v * v for v in r_trial)
                if sse_trial < sse:
                    theta, r, sse = trial, r_trial, sse_trial
                    damping = max(damping / 3, 1e-9)
                    accepted = improved = True
                    break
            damping *= 4
        if not accepted:
            break
    if not improved:
        return fit
    got = dict(zip(names, theta, strict=True))
    return NoHeatFit(
        got["a"],
        got["c"],
        got.get("g", 0.0),
        fit.bins,
        got.get("b", 0.0),
        got.get("w", 0.0),
        r2=fit.r2,
        method="multi-step",
    )


def least_squares_matrix(matrix: list[list[float]], rhs: list[float]) -> list | None:
    """Solve a small square linear system (Gaussian elimination with pivoting)."""
    n = len(rhs)
    m = [[*row, b] for row, b in zip(matrix, rhs, strict=True)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-15:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col], strict=True)]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_heat_rate(model: ZoneModel, data: ZoneData, min_calls: int = 5) -> float:
    """The zone's heating rate h (C per hour of furnace call), or 0 if unknown.

    As ClimateAdvisor learns ``k_active``: what the room gained beyond the
    no-heat model over each call and the bin after it (the heat still arriving
    from the ducts), divided by the hours the call ran.
    """
    gained = 0.0
    on_hours = 0.0
    calls = 0
    n = len(data.room)
    i = 1
    while i < n - 1:
        if data.heating[i] <= 0 or data.heating[i - 1] > 0:
            i += 1
            continue
        end = i
        while end < n - 1 and data.heating[end] > 0:
            end += 1
        end = min(end + 1, n - 1)  # include the bin after the call
        span = range(i, end)
        if (
            data.room[i] is None
            or data.room[end] is None
            or not all(_usable(data, j) for j in span)
        ):
            i = end
            continue
        t = data.room[i]
        for j in span:
            t = step(
                t,
                data.outdoor[j],
                data.light[j],
                model,
                data.hours,
                0.0 if data.wall is None else data.wall[j],
                0.0 if data.ground is None else data.ground[j],
            )
        gained += data.room[end] - t
        on_hours += sum(data.heating[j] for j in span) * data.hours
        calls += 1
        i = end
    if calls < min_calls or on_hours <= 0:
        return 0.0
    return max(gained / on_hours, 0.0)


def grade(fit: NoHeatFit | None, skills: dict[int, Skill], lead: int = 12) -> str:
    """How far to trust a fit, as ClimateAdvisor's "Calibration" label.

    ``none``: no usable fit (see ``problem``), or no idle history to check it
    on. ``low``: the model does not beat holding the temperature ``lead`` bins
    ahead. ``medium``: it does, on at least 150 idle bins. ``high``: it beats
    holding by a fifth or more, on at least 400 idle bins.
    """
    s = skills.get(lead)
    if fit is None or problem(fit) is not None or s is None:
        return "none"
    if s.model >= s.hold:
        return "low"
    if fit.bins >= 400 and s.model <= 0.8 * s.hold:
        return "high"
    if fit.bins >= 150:
        return "medium"
    return "low"


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
