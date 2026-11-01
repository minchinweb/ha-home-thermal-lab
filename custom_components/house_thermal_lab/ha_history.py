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
from datetime import UTC, datetime, timedelta
import itertools
import json
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


def hourly_means(
    states: list[dict],
    attribute: str | None = None,
    until: datetime | None = None,
) -> list[Reading]:
    """Turn irregular sensor states into time-weighted hourly UTC readings.

    Home Assistant only records a state when it changes, so a value holds until
    the next row. Each hour is the time-weighted mean of the held values;
    stretches where the sensor was unavailable (or not numeric) are left out.

    Args:
        states: Home Assistant state dicts with ``state`` and ``last_changed``
            (or ``last_updated``, used when reading an attribute).
        attribute: Read this attribute instead of the state, as for the
            ``temperature`` of a ``weather`` entity (whose state is a
            condition such as ``cloudy``).
        until: The last value holds until this time (timezone-aware). Defaults
            to the end of the hour of the last state.

    Returns:
        One reading per hour that has any valid time, oldest first.
    """
    events: list[tuple[datetime, float | None]] = []
    for s in states:
        raw = (
            s.get("state")
            if attribute is None
            else s.get("attributes", {}).get(attribute)
        )
        try:
            value = None if raw is None or raw in _BAD_STATES else float(raw)
        except (TypeError, ValueError):
            value = None
        stamp = s["last_changed"] if attribute is None else s["last_updated"]
        events.append((datetime.fromisoformat(stamp).astimezone(UTC), value))
    if not events:
        return []
    events.sort(key=lambda e: e[0])
    last = events[-1][0].replace(minute=0, second=0, microsecond=0)
    end = until.astimezone(UTC) if until is not None else last + timedelta(hours=1)
    events.append((end, None))

    weighted: dict[datetime, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for (t0, value), (t1, _) in itertools.pairwise(events):
        if value is None:
            continue
        cursor = t0
        while cursor < t1:
            hour = cursor.replace(minute=0, second=0, microsecond=0)
            stop = min(t1, hour + timedelta(hours=1))
            seconds = (stop - cursor).total_seconds()
            weighted[hour][0] += value * seconds
            weighted[hour][1] += seconds
            cursor = stop
    return [
        Reading(h.replace(tzinfo=None), total / seconds)
        for h, (total, seconds) in sorted(weighted.items())
        if seconds > 0
    ]


def fetch_sensor_history(
    base_url: str,
    token: str,
    entity_id: str,
    start: datetime,
    end: datetime,
    fetch: AuthFetcher = urllib_fetch_auth,
    attribute: str | None = None,
) -> list[Reading]:
    """Fetch an entity's history as hourly readings.

    A ``weather.*`` entity keeps its temperature in the ``temperature``
    attribute, so that attribute is read automatically for those.

    Args:
        base_url: Home Assistant URL.
        token: Long-lived access token.
        entity_id: A temperature sensor, e.g. ``sensor.outdoor_temperature``.
        start: Start of the period (timezone-aware).
        end: End of the period (timezone-aware).
        fetch: Function that fetches a URL as JSON (replaceable in tests).
        attribute: Read this attribute instead of the state.

    Returns:
        Hourly mean readings in UTC.
    """
    if attribute is None and entity_id.startswith("weather."):
        attribute = "temperature"
    params = {"filter_entity_id": entity_id, "end_time": end.isoformat()}
    if attribute is None:
        # states only; attributes make the response much bigger
        params |= {"minimal_response": "", "no_attributes": ""}
    query = urllib.parse.urlencode(params)
    url = (
        f"{base_url.rstrip('/')}/api/history/period/"
        f"{urllib.parse.quote(start.isoformat())}?{query}"
    )
    body = fetch(url, token)
    return hourly_means(body[0] if body else [], attribute, end)


def list_temperature_sensors(
    base_url: str, token: str, fetch: AuthFetcher = urllib_fetch_auth
) -> list[tuple[str, str, str]]:
    """List entities that report a temperature, to find the ids to analyse.

    Includes ``sensor.*`` entities with the temperature device class, and
    ``weather.*`` entities (which report it as an attribute).

    Args:
        base_url: Home Assistant URL.
        token: Long-lived access token.
        fetch: Function that fetches a URL as JSON (replaceable in tests).

    Returns:
        ``(entity_id, friendly_name, current_temperature)`` sorted by id.
    """
    states = fetch(f"{base_url.rstrip('/')}/api/states", token)
    found = []
    for s in states:
        attrs = s.get("attributes", {})
        entity_id = s["entity_id"]
        if (
            entity_id.startswith("sensor.")
            and attrs.get("device_class") == "temperature"
        ):
            value = s["state"]
        elif entity_id.startswith("weather.") and "temperature" in attrs:
            value = str(attrs["temperature"])
        else:
            continue
        found.append((entity_id, attrs.get("friendly_name", ""), value))
    return sorted(found)


def fetch_states(
    base_url: str,
    token: str,
    entity_id: str,
    start: datetime,
    end: datetime,
    fetch: AuthFetcher = urllib_fetch_auth,
    with_attributes: bool = False,
) -> list[dict]:
    """Fetch an entity's raw state history.

    By default only the state and ``last_changed`` come back, which is small.
    With ``with_attributes`` each row also has ``attributes`` and
    ``last_updated`` (needed for attributes such as a climate entity's
    ``hvac_action``), and the response is much larger.

    Args:
        base_url: Home Assistant URL.
        token: Long-lived access token.
        entity_id: Any entity, e.g. ``binary_sensor.z1_furnace_heating``.
        start: Start of the period (timezone-aware).
        end: End of the period (timezone-aware).
        fetch: Function that fetches a URL as JSON (replaceable in tests).
        with_attributes: Include attributes and ``last_updated``.

    Returns:
        State dicts, oldest first.
    """
    params = {"filter_entity_id": entity_id, "end_time": end.isoformat()}
    if not with_attributes:
        params |= {"minimal_response": "", "no_attributes": ""}
    query = urllib.parse.urlencode(params)
    url = (
        f"{base_url.rstrip('/')}/api/history/period/"
        f"{urllib.parse.quote(start.isoformat())}?{query}"
    )
    body = fetch(url, token)
    return body[0] if body else []


def fetch_time_zone(
    base_url: str, token: str, fetch: AuthFetcher = urllib_fetch_auth
) -> str:
    """Read the home time zone name (e.g. ``America/Edmonton``) from ``/api/config``.

    Args:
        base_url: Home Assistant URL.
        token: Long-lived access token.
        fetch: Function that fetches a URL as JSON (replaceable in tests).

    Returns:
        The IANA time zone name.
    """
    return fetch(f"{base_url.rstrip('/')}/api/config", token)["time_zone"]
