"""Fetch historical hourly temperatures from the Open-Meteo archive API.

Data is requested in GMT and converted to local *mean solar time* (UTC plus
longitude / 15 h). That avoids daylight-saving jumps and makes "solar noon"
comparable across places (see :mod:`solar`).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta

from .locations import Location

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# A fetcher takes a URL and returns the decoded JSON body.
Fetcher = Callable[[str], dict]


def urllib_fetch(url: str) -> dict:
    """Blocking fetch; run in an executor when called from Home Assistant."""
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        return json.load(resp)


def build_url(location: Location, start: date, end: date) -> str:
    """Archive API URL for hourly 2 m temperature in GMT."""
    query = urllib.parse.urlencode(
        {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": "temperature_2m",
            "timezone": "GMT",
        }
    )
    return f"{ARCHIVE_URL}?{query}"


def fetch_hourly(
    location: Location,
    start: date,
    end: date,
    fetch: Fetcher = urllib_fetch,
) -> list[tuple[datetime, float]]:
    """Return ``(utc_time, temperature_c)`` pairs, skipping missing values."""
    body = fetch(build_url(location, start, end))
    hourly = body["hourly"]
    return [
        (datetime.fromisoformat(t), float(v))
        for t, v in zip(hourly["time"], hourly["temperature_2m"])
        if v is not None
    ]


def to_solar_days(
    samples: list[tuple[datetime, float]], longitude: float
) -> dict[date, list[tuple[float, float]]]:
    """Group UTC samples into local-mean-solar-time days.

    Returns ``{date: [(solar_hour, temperature), ...]}``.
    """
    shift = timedelta(hours=longitude / 15.0)
    days: dict[date, list[tuple[float, float]]] = {}
    for t, v in samples:
        solar = t + shift
        hour = solar.hour + solar.minute / 60.0
        days.setdefault(solar.date(), []).append((hour, v))
    return days
