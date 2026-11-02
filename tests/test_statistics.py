"""Tests for the websocket statistics client (fake socket)."""

import asyncio
from datetime import UTC, datetime

import pytest

from custom_components.home_thermal_lab import ha_statistics
from custom_components.home_thermal_lab.readings import Reading


class FakeSocket:
    """Plays back replies and records what was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_json(self):
        return self.replies.pop(0)


def test_websocket_url():
    assert (
        ha_statistics.websocket_url("http://ha:8123/") == "ws://ha:8123/api/websocket"
    )
    assert (
        ha_statistics.websocket_url("https://ha.example")
        == "wss://ha.example/api/websocket"
    )


def test_authenticate_ok_and_failure():
    ok = FakeSocket([{"type": "auth_required"}, {"type": "auth_ok"}])
    asyncio.run(ha_statistics.authenticate(ok, "tok"))
    assert ok.sent == [{"type": "auth", "access_token": "tok"}]
    bad = FakeSocket([{"type": "auth_required"}, {"type": "auth_invalid"}])
    with pytest.raises(ha_statistics.HomeAssistantError, match="authentication"):
        asyncio.run(ha_statistics.authenticate(bad, "tok"))


def test_statistics_to_readings_handles_epoch_and_iso():
    rows = [
        {"start": 1_748_736_000_000, "mean": 5.0},  # 2025-06-01T00:00Z in ms
        {"start": "2025-06-01T01:00:00+00:00", "mean": 6.0},
        {"start": 1_748_746_800, "mean": 7.0},  # seconds, 03:00Z
        {"start": 1_748_743_200_000, "mean": None},
    ]
    out = ha_statistics.statistics_to_readings(rows)
    assert out == [
        Reading(datetime(2025, 6, 1, 0), 5.0),
        Reading(datetime(2025, 6, 1, 1), 6.0),
        Reading(datetime(2025, 6, 1, 3), 7.0),
    ]


def test_fetch_statistics_skips_unrelated_messages_and_empty_entities():
    ws = FakeSocket(
        [
            {"type": "event", "id": 99},
            {
                "id": 1,
                "type": "result",
                "success": True,
                "result": {
                    "sensor.a": [{"start": 1_748_736_000_000, "mean": 1.5}],
                    "sensor.b": [],
                },
            },
        ]
    )
    when = datetime(2025, 6, 1, tzinfo=UTC)
    out = asyncio.run(
        ha_statistics.fetch_statistics(ws, ["sensor.a", "sensor.b"], when, when)
    )
    assert out == {"sensor.a": [Reading(datetime(2025, 6, 1, 0), 1.5)]}
    sent = ws.sent[0]
    assert sent["type"] == "recorder/statistics_during_period"
    assert sent["statistic_ids"] == ["sensor.a", "sensor.b"]
    assert sent["period"] == "hour"


def test_command_error():
    ws = FakeSocket([{"id": 1, "success": False, "error": {"message": "nope"}}])
    with pytest.raises(ha_statistics.HomeAssistantError, match="nope"):
        asyncio.run(ha_statistics.command(ws, 1, {"type": "x"}))
