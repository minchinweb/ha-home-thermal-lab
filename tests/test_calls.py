"""Tests for heating-call detection and response."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.house_thermal_lab.calls import (
    Call,
    calls_from_states,
    respond,
    summarise,
)

T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)


def _row(minute: float, action: str, equipment: str = "", temp: float = 20.0):
    return {
        "last_updated": (T0 + timedelta(minutes=minute)).isoformat(),
        "attributes": {
            "hvac_action": action,
            "equipment_running": equipment,
            "current_temperature": temp,
        },
    }


def test_calls_and_stages():
    states = [
        _row(0, "idle"),
        _row(10, "heating", "auxHeat1,fan"),
        _row(20, "idle", "fan"),
        _row(40, "heating", "auxHeat1,fan"),
        _row(70, "heating", "auxHeat2,fan"),
        _row(85, "idle"),
    ]
    calls = calls_from_states(states, T0 + timedelta(hours=2))
    assert [c.minutes for c in calls] == [10, 45]
    assert [c.stage for c in calls] == ["low", "stepped"]
    assert calls[1].high_minutes == pytest.approx(15)


def test_response_lag_dip_rebound():
    call = Call(T0, T0 + timedelta(minutes=20), 0.0)
    series = [
        (T0 - timedelta(minutes=5), 20.0),
        (T0 + timedelta(minutes=4), 20.0),
        (T0 + timedelta(minutes=6), 20.1),
        (T0 + timedelta(minutes=20), 20.8),
        (T0 + timedelta(minutes=23), 20.9),
        (T0 + timedelta(minutes=35), 20.4),
        (T0 + timedelta(minutes=60), 20.6),
    ]
    r = respond(call, series)
    assert r.lag == pytest.approx(6)
    assert r.rise == pytest.approx(0.8)
    assert r.overshoot == pytest.approx(0.1)
    assert r.dip == pytest.approx(-0.4)
    assert r.dip_minutes == pytest.approx(15)
    assert r.rebound == pytest.approx(0.2)
    s = summarise([r])
    assert s["low"]["calls"] == 1
    assert s["stepped"]["calls"] == 0
    assert s["low"]["median_rise"] == pytest.approx(0.8)
