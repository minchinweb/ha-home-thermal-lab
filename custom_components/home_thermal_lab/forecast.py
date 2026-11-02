"""Hourly outdoor temperature and sunlight forecast from Open-Meteo (hypothesis 17)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import urllib.parse

from .irradiance import Irradiance
from .open_meteo import Fetcher, urllib_fetch
from .wind import FORECAST_URL

HOURLY = "temperature_2m,direct_normal_irradiance,diffuse_radiation,cloud_cover"


@dataclass(frozen=True)
class ForecastHour:
    """One forecast hour (UTC, the hour it ends at, as for ``Irradiance``)."""

    time: datetime
    temperature: float
    light: Irradiance


def build_url(
    latitude: float, longitude: float, days: int = 2, past_days: int = 0
) -> str:
    """Build the forecast URL for the coming hours (and ``past_days``) in GMT."""
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "forecast_days": days,
            "past_days": past_days,
            "hourly": HOURLY,
            "timezone": "GMT",
        }
    )
    return f"{FORECAST_URL}?{query}"


def parse_forecast(body: dict) -> list[ForecastHour]:
    """Turn the API body into forecast hours, skipping incomplete ones."""
    hourly = body.get("hourly", {})
    out = []
    keys = (
        "time",
        "temperature_2m",
        "direct_normal_irradiance",
        "diffuse_radiation",
        "cloud_cover",
    )
    columns = [hourly.get(k) or [] for k in keys]
    for stamp, temp, direct, diffuse, cloud in zip(*columns, strict=False):
        if temp is None or direct is None or diffuse is None:
            continue
        when = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        out.append(
            ForecastHour(
                when,
                float(temp),
                Irradiance(when, float(direct), float(diffuse), float(cloud or 0.0)),
            )
        )
    return out


def fetch_forecast(
    latitude: float,
    longitude: float,
    days: int = 2,
    fetch: Fetcher = urllib_fetch,
    past_days: int = 0,
) -> list[ForecastHour]:
    """Fetch the forecast (blocking); ``past_days`` adds the recent past."""
    return parse_forecast(fetch(build_url(latitude, longitude, days, past_days)))
