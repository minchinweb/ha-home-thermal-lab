"""Read a temperature sensor's history from a Home Assistant instance.

Uses the REST API (``/api/config`` and ``/api/history/period``), so the same
analysis can run against sensors at home as against Open-Meteo. Inside Home
Assistant itself, read the recorder directly instead.

Limits:
    * The history endpoint only reaches back as far as the recorder keeps
      states (10 days by default), so a year needs a longer
      ``purge_keep_days`` or an export.
    * Sensor values are taken as degrees Celsius; set Home Assistant to metric
      or convert beforehand.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
import json
import statistics
import urllib.parse
import urllib.request

from .readings import Reading

# A fetcher takes a URL and a bearer token and returns the decoded JSON body.
AuthFetcher = Callable[[str, str], object]

_BAD_STATES = frozenset({"unknown", "unavailable", ""})


def urllib_fetch_auth(url: str, token: str) -> object:
    """Fetch JSON with a bearer token, blocking.

    Args:
        url: The URL to fetch.
        token: A Home Assistant long-lived access token.

    Returns:
        The decoded JSON body.
    """
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=120) as resp:
        return json.load(resp)


def fetch_home_position(
    base_url: str, token: str, fetch: AuthFetcher = urllib_fetch_auth
) -> tuple[float, float]:
    """Read the home latitude and longitude from ``/api/config``.

    Args:
        base_url: Home Assistant URL, e.g. ``http://homeassistant.local:8123``.
        token: Long-lived access token.
        fetch: Function that fetches a URL as JSON (replaceable in tests).

    Returns:
        ``(latitude, longitude)``.
    """
    config = fetch(f"{base_url.rstrip('/')}/api/config", token)
    return float(config["latitude"]), float(config["longitude"])


def hourly_means(states: list[dict]) -> list[Reading]:
    """Average irregular sensor states into hourly UTC readings.

    Args:
        states: Home Assistant state dicts with ``state`` and ``last_changed``.

    Returns:
        One reading per hour that has numeric states, oldest first.
    """
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for s in states:
        if s.get("state") in _BAD_STATES:
            continue
        try:
            value = float(s["state"])
        except (TypeError, ValueError):
            continue
        when = datetime.fromisoformat(s["last_changed"]).astimezone(UTC)
        hour = when.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        buckets[hour].append(value)
    return [Reading(h, statistics.fmean(v)) for h, v in sorted(buckets.items())]


def fetch_sensor_history(
    base_url: str,
    token: str,
    entity_id: str,
    start: datetime,
    end: datetime,
    fetch: AuthFetcher = urllib_fetch_auth,
) -> list[Reading]:
    """Fetch an entity's history as hourly readings.

    Args:
        base_url: Home Assistant URL.
        token: Long-lived access token.
        entity_id: A temperature sensor, e.g. ``sensor.outdoor_temperature``.
        start: Start of the period (timezone-aware).
        end: End of the period (timezone-aware).
        fetch: Function that fetches a URL as JSON (replaceable in tests).

    Returns:
        Hourly mean readings in UTC.
    """
    query = urllib.parse.urlencode(
        {
            "filter_entity_id": entity_id,
            "end_time": end.isoformat(),
            "minimal_response": "",
            "no_attributes": "",
        }
    )
    url = (
        f"{base_url.rstrip('/')}/api/history/period/"
        f"{urllib.parse.quote(start.isoformat())}?{query}"
    )
    body = fetch(url, token)
    return hourly_means(body[0] if body else [])
