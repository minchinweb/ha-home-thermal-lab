"""Draw average daily temperature profiles with percentile bands.

Each panel shows, for one group of days, the temperature relative to each
day's mean by hour of the solar day: the 10-90 and 25-75 percentile bands, the
median, and the average fitted sinusoid. Needs matplotlib (``analysis`` group).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from custom_components.home_thermal_lab.experiments import (
    average_fit,
    group_results,
    profile_bands,
)

if TYPE_CHECKING:
    from pathlib import Path

    from custom_components.home_thermal_lab.experiments import DayResult
    from custom_components.home_thermal_lab.locations import Location


def plot_location(
    location: Location, results: list[DayResult], by: str, path: Path
) -> None:
    """Write a figure with one panel per group of days.

    Args:
        location: The place.
        results: Per-day results.
        by: ``all``, ``season`` or ``weather``.
        path: PNG file to write.
    """
    groups = group_results(results, by)
    cols = min(len(groups), 4)
    rows = math.ceil(len(groups) / cols)
    fig, axes = plt.subplots(
        rows, cols, figsize=(4.2 * cols, 3.2 * rows), sharey=True, squeeze=False
    )
    hours = [h / 4 for h in range(97)]
    for ax, (label, group) in zip(axes.flat, groups.items(), strict=False):
        bands = profile_bands(group)
        xs = sorted(bands[50])
        centre = [x + 0.5 for x in xs]  # hourly bucket midpoints
        ax.fill_between(
            centre,
            [bands[10][x] for x in xs],
            [bands[90][x] for x in xs],
            alpha=0.2,
            label="10-90%",
        )
        ax.fill_between(
            centre,
            [bands[25][x] for x in xs],
            [bands[75][x] for x in xs],
            alpha=0.4,
            label="25-75%",
        )
        ax.plot(centre, [bands[50][x] for x in xs], lw=1, label="median")
        amp, peak = average_fit(group)
        ax.plot(
            hours,
            [amp * math.cos(2 * math.pi * (h - peak) / 24) for h in hours],
            "k--",
            lw=1.2,
            label=f"avg fit (peak {peak:.1f} h)",
        )
        ax.axvline(12, color="orange", lw=0.8, ls=":")
        ax.set_title(f"{label} ({len(group)} days)", fontsize=10)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 6))
        ax.set_xlabel("solar hour (orange = noon)")
    for ax in axes.flat[len(groups) :]:
        ax.set_visible(False)
    axes[0][0].set_ylabel("temperature vs day mean (°C)")
    axes[0][0].legend(fontsize=7, loc="upper left")
    fig.suptitle(f"{location.name} ({location.kind}), grouped by {by}")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
