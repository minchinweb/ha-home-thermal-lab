"""Read long-term statistics from Home Assistant over its websocket API.

Home Assistant keeps hourly mean/min/max for sensors with a ``state_class``
indefinitely (5-minute values for about as long as the recorder keeps
states), which is far longer than the state history the REST API serves. The
websocket commands used are ``recorder/statistics_during_period`` and
``recorder/list_statistic_ids``.

Inside Home Assistant itself, call the recorder's statistics functions directly
instead; this module is for running the experiments from outside.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from .readings import Reading

if TYPE_CHECKING:
    from collections.abc import Iterable


class WebSocket(Protocol):
    """The slice of an aiohttp websocket this module needs."""

    async def send_json(self, data: Any) -> None:
        """Send a JSON message."""

    async def receive_json(self) -> Any:
        """Receive a JSON message."""


class HomeAssistantError(RuntimeError):
    """Home Assistant refused a request."""


def websocket_url(base_url: str) -> str:
    """Convert a Home Assistant base URL to its websocket endpoint.

    Args:
        base_url: e.g. ``http://homeassistant.local:8123``.

    Returns:
        e.g. ``ws://homeassistant.local:8123/api/websocket``.
    """
    base = base_url.rstrip("/")
    scheme, _, rest = base.partition("://")
    return f"{'wss' if scheme == 'https' else 'ws'}://{rest}/api/websocket"


async def authenticate(ws: WebSocket, token: str) -> None:
    """Complete the websocket authentication handshake.

    Args:
        ws: An open websocket.
        token: Long-lived access token.

    Raises:
        HomeAssistantError: If Home Assistant rejects the token.
    """
    first = await ws.receive_json()
    if first.get("type") != "auth_required":
        raise HomeAssistantError(f"unexpected greeting: {first.get('type')}")
    await ws.send_json({"type": "auth", "access_token": token})
    reply = await ws.receive_json()
    if reply.get("type") != "auth_ok":
        raise HomeAssistantError("authentication failed (check HA_TOKEN)")


async def command(ws: WebSocket, message_id: int, payload: dict) -> Any:
    """Send one command and wait for its result.

    Args:
        ws: An authenticated websocket.
        message_id: A number unique within the connection.
        payload: The command, including its ``type``.

    Returns:
        The ``result`` field of the reply.

    Raises:
        HomeAssistantError: If the command fails.
    """
    await ws.send_json({"id": message_id, **payload})
    while True:
        reply = await ws.receive_json()
        if reply.get("id") != message_id:
            continue  # an event or an unrelated reply
        if not reply.get("success", False):
            error = reply.get("error", {})
            raise HomeAssistantError(
                f"{payload['type']} failed: {error.get('message', reply)}"
            )
        return reply.get("result")


def _to_datetime(value: float | str) -> datetime:
    """Parse a statistics timestamp (epoch milliseconds, seconds or ISO text)."""
    if isinstance(value, str):
        return datetime.fromisoformat(value).astimezone(UTC)
    seconds = value / 1000.0 if value > 1e11 else value
    return datetime.fromtimestamp(seconds, tz=UTC)


def statistics_to_readings(rows: Iterable[dict]) -> list[Reading]:
    """Turn statistics rows into hourly readings.

    Args:
        rows: Rows with ``start`` and ``mean`` (rows without a mean are skipped).

    Returns:
        Naive-UTC readings, oldest first.
    """
    out = [
        Reading(_to_datetime(r["start"]).replace(tzinfo=None), float(r["mean"]))
        for r in rows
        if r.get("mean") is not None
    ]
    return sorted(out, key=lambda r: r.time)


async def fetch_statistics(
    ws: WebSocket,
    entity_ids: list[str],
    start: datetime,
    end: datetime,
    period: str = "hour",
) -> dict[str, list[Reading]]:
    """Fetch mean statistics for several entities on an authenticated socket.

    Args:
        ws: An authenticated websocket.
        entity_ids: Statistic ids (normally entity ids).
        start: Start of the period (timezone-aware).
        end: End of the period (timezone-aware).
        period: ``5minute``, ``hour``, ``day``, ``week`` or ``month``.

    Returns:
        Readings for each entity that has statistics.
    """
    result = await command(
        ws,
        1,
        {
            "type": "recorder/statistics_during_period",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "statistic_ids": entity_ids,
            "period": period,
            "types": ["mean"],
        },
    )
    return {
        entity_id: statistics_to_readings(rows)
        for entity_id, rows in (result or {}).items()
        if rows
    }


async def fetch_statistics_from_url(
    base_url: str,
    token: str,
    entity_ids: list[str],
    start: datetime,
    end: datetime,
    period: str = "hour",
) -> dict[str, list[Reading]]:
    """Connect, authenticate and fetch statistics (needs ``aiohttp``).

    Args:
        base_url: Home Assistant URL.
        token: Long-lived access token.
        entity_ids: Statistic ids (normally entity ids).
        start: Start of the period (timezone-aware).
        end: End of the period (timezone-aware).
        period: ``5minute``, ``hour``, ``day``, ``week`` or ``month``.

    Returns:
        Readings for each entity that has statistics.
    """
    import aiohttp

    async with (
        aiohttp.ClientSession() as session,
        session.ws_connect(websocket_url(base_url), max_msg_size=0) as ws,
    ):
        await authenticate(ws, token)
        return await fetch_statistics(ws, entity_ids, start, end, period)
