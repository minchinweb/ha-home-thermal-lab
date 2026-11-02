"""Fetch historical hourly weather from the Open-Meteo archive API.

Data is requested in GMT and converted to local *mean solar time* (UTC plus
longitude / 15 h). That avoids daylight-saving jumps and makes "solar noon"
comparable across places (see :mod:`solar`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
import json
import time
from typing import TYPE_CHECKING
import urllib.error
import urllib.parse
import urllib.request

from .readings import Reading, SolarReading

if TYPE_CHECKING:
    from .locations import Location

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARIABLES = "temperature_2m,weather_code,cloud_cover"
RETRIES = 4
RETRY_SECONDS = 20.0

# A fetcher takes a URL and returns the decoded JSON body.
Fetcher = Callable[[str], dict]


def urllib_fetch(url: str) -> dict:
    """Fetch JSON, blocking; run in an executor when called from Home Assistant.

    Args:
        url: The URL to fetch.

    Returns:
        The decoded JSON body.
    """
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            # 429 (rate limit) and 5xx are usually transient on the free API
            if (err.code != 429 and err.code < 500) or attempt == RETRIES - 1:
                raise
        time.sleep(RETRY_SECONDS * (attempt + 1))
    raise RuntimeError("unreachable")


def build_url(location: Location, start: date, end: date) -> str:
    """Build the archive API URL for hourly weather in GMT.

    Args:
        location: Where to fetch.
        start: First day, inclusive.
        end: Last day, inclusive.

    Returns:
        The request URL.
    """
    query = urllib.parse.urlencode(
        {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": HOURLY_VARIABLES,
            "timezone": "GMT",
        }
    )
    return f"{ARCHIVE_URL}?{query}"


def _optional(values: list | None, index: int) -> float | None:
    if values is None or index >= len(values):
        return None
    return values[index]


def fetch_hourly(
    location: Location,
    start: date,
    end: date,
    fetch: Fetcher = urllib_fetch,
) -> list[Reading]:
    """Fetch hourly readings, skipping hours with no temperature.

    Args:
        location: Where to fetch.
        start: First day, inclusive.
        end: Last day, inclusive.
        fetch: Function that fetches a URL as JSON (replaceable in tests).

    Returns:
        Readings in UTC, oldest first.
    """
    hourly = fetch(build_url(location, start, end))["hourly"]
    codes = hourly.get("weather_code")
    clouds = hourly.get("cloud_cover")
    out = []
    for i, (t, temp) in enumerate(
        zip(hourly["time"], hourly["temperature_2m"], strict=True)
    ):
        if temp is None:
            continue
        code = _optional(codes, i)
        out.append(
            Reading(
                datetime.fromisoformat(t),
                float(temp),
                None if code is None else int(code),
                _optional(clouds, i),
            )
        )
    return out


def to_solar_days(
    readings: list[Reading], longitude: float
) -> dict[date, list[SolarReading]]:
    """Group UTC readings into local-mean-solar-time days.

    Args:
        readings: Readings in UTC.
        longitude: Longitude in degrees east.

    Returns:
        Readings for each solar day.
    """
    shift = timedelta(hours=longitude / 15.0)
    days: dict[date, list[SolarReading]] = {}
    for r in readings:
        solar = r.time + shift
        hour = solar.hour + solar.minute / 60.0
        days.setdefault(solar.date(), []).append(
            SolarReading(hour, r.temperature, r.weather_code, r.cloud_cover)
        )
    return days
