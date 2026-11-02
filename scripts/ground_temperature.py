"""Does a damped, lagged annual wave of air temperature predict soil? (hypothesis 03)

Downloads daily means of air temperature and ERA5-Land modelled soil
temperature at four depth bands from the Open-Meteo archive, then:

1. fits the annual wave to air (``Tm - A cos(w (t - t0))``);
2. for each soil band, fits its own annual wave and reports the amplitude ratio
   and lag against air (the data say how much damping and delay there is);
3. predicts each band from the air wave alone with the Kusuda-Achenbach
   solution, searching soil diffusivity ``alpha``, and reports the error with and
   without a free offset (snow cover and similar keep soil warmer than air).

Usage::

    uv run python scripts/ground_temperature.py --years 3
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
import math
import os
from pathlib import Path
import sys
import urllib.parse

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from envfile import load_env

from custom_components.home_thermal_lab.ha_history import fetch_home_position
from custom_components.home_thermal_lab.open_meteo import ARCHIVE_URL, urllib_fetch

BANDS = {
    "soil_temperature_0_to_7cm": 0.035,
    "soil_temperature_7_to_28cm": 0.175,
    "soil_temperature_28_to_100cm": 0.64,
    "soil_temperature_100_to_255cm": 1.775,
}
OMEGA = 2 * math.pi / 365.25


def fetch_daily(
    lat: float, lon: float, start: date, end: date
) -> dict[str, np.ndarray]:
    """Daily means of air and soil temperature; days with gaps are NaN."""
    variables = ["temperature_2m", *BANDS]
    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(variables),
            "timezone": "GMT",
        }
    )
    hourly = urllib_fetch(f"{ARCHIVE_URL}?{query}")["hourly"]
    days = (end - start).days + 1
    out = {}
    for name in variables:
        values = np.array(
            [np.nan if v is None else v for v in hourly[name]], dtype=float
        )[: days * 24]
        out[name] = np.nanmean(values.reshape(days, 24), axis=1)
    return out


def fit_wave(t: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float]:
    """Fit ``mean - amp cos(w (t - t0))``; return (mean, amp, t0 days, rmse)."""
    ok = ~np.isnan(y)
    x = np.column_stack(
        [np.ones(ok.sum()), np.cos(OMEGA * t[ok]), np.sin(OMEGA * t[ok])]
    )
    beta, *_ = np.linalg.lstsq(x, y[ok], rcond=None)
    # y = m + c cos(wt) + s sin(wt) = m + R cos(wt - phi); minimum at phi + pi
    amp = math.hypot(beta[1], beta[2])
    phi = math.atan2(beta[2], beta[1])
    t0 = ((phi / OMEGA) + 365.25 / 2) % 365.25  # day of the coldest point
    rmse = float(np.sqrt(np.mean((y[ok] - x @ beta) ** 2)))
    return float(beta[0]), amp, t0, rmse


def kusuda(t, mean, amp, t0, depth, alpha) -> np.ndarray:
    """Soil temperature at ``depth`` (m) for diffusivity ``alpha`` (m2/day)."""
    d = math.sqrt(2 * alpha / OMEGA)
    return mean - amp * math.exp(-depth / d) * np.cos(OMEGA * (t - t0) - depth / d)


def main() -> None:
    """Print the fits."""
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--years", type=int, default=3)
    p.add_argument("--ha-url", default=os.environ.get("HA_URL"))
    args = p.parse_args()

    lat, lon = fetch_home_position(args.ha_url, os.environ["HA_TOKEN"])
    end = datetime.now(UTC).date() - timedelta(days=7)
    start = end - timedelta(days=int(365.25 * args.years))
    data = fetch_daily(lat, lon, start, end)
    t = np.arange(len(data["temperature_2m"]), dtype=float)
    doy0 = start.timetuple().tm_yday

    am, aa, at0, arm = fit_wave(t, data["temperature_2m"])
    print(
        f"{start} to {end} ({len(t)} days) at {lat:.2f}, {lon:.2f}\n"
        f"air annual wave: mean {am:.1f} C, amplitude {aa:.1f} C, coldest day "
        f"{(at0 + doy0 - 1) % 365.25 + 1:.0f} of year, daily RMSE {arm:.1f} C\n"
    )

    print("each band's own annual wave (the data):")
    print(f"{'band':<32}{'depth m':>8}{'mean':>7}{'amp':>6}{'ratio':>7}{'lag d':>7}")
    for name, depth in BANDS.items():
        m, a, t0, _ = fit_wave(t, data[name])
        lag = (t0 - at0 + 182.6) % 365.25 - 182.6
        print(f"{name:<32}{depth:>8.2f}{m:>7.1f}{a:>6.1f}{a / aa:>7.2f}{lag:>7.0f}")

    print("\nprediction from the air wave alone (Kusuda-Achenbach):")
    print(
        f"{'band':<32}{'alpha':>7}{'RMSE':>6}{'offset':>8}{'RMSE':>6}"
        f"  (alpha m2/day; second pair has a free offset)"
    )
    alphas = np.arange(0.002, 0.30, 0.002)
    for name, depth in BANDS.items():
        y = data[name]
        ok = ~np.isnan(y)
        best = None
        for alpha in alphas:
            pred = kusuda(t, am, aa, at0, depth, alpha)
            err = y[ok] - pred[ok]
            plain = float(np.sqrt(np.mean(err**2)))
            off = float(err.mean())
            shifted = float(np.sqrt(np.mean((err - off) ** 2)))
            if best is None or shifted < best[3]:
                best = (alpha, plain, off, shifted)
        alpha, plain, off, shifted = best
        print(f"{name:<32}{alpha:>7.3f}{plain:>6.2f}{off:>+8.1f}{shifted:>6.2f}")
    print(
        "\nbest alpha is chosen on the offset-free fit; plain RMSE is that alpha "
        "with no offset"
    )


if __name__ == "__main__":
    main()
