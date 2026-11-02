"""Tests for the contribution split."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.house_thermal_lab.contributions import (
    Inputs,
    ZoneTerms,
    chart_points,
    dimmer_kw,
    forecast,
    history,
)

MODEL = ZoneTerms(a=0.02, c=0.1, g=0.001, h=2.0)


def test_history_adds_up_to_the_measured_temperature():
    temps = [20.0, 20.4, 20.3, 20.5]
    steps = [Inputs(0.0, 100.0, 0.5), Inputs(0.0), Inputs(-5.0, 200.0)]
    past = history(MODEL, temps, steps, 0.5)
    assert past[-1]["furnace"] == 0.0
    for t, c in zip(temps, past, strict=True):
        assert temps[-1] + sum(c.values()) == pytest.approx(t)
    assert past[0]["furnace"] < 0  # heat that came in is "taken away" going back


def test_history_stops_at_a_gap():
    past = history(MODEL, [20.0, None, 20.1], [Inputs(0.0), Inputs(0.0)], 1.0)
    assert past[0] is None
    assert past[1] is None
    assert past[2] is not None


def test_forecast_thermostat_turns_heat_on_and_off():
    steps = [Inputs(-20.0)] * 40
    temps, cum = forecast(MODEL, 20.0, steps, 0.25, setpoint=20.0, deadband=0.3)
    assert min(temps) >= 19.5
    assert cum[-1]["furnace"] > 0
    assert cum[-1]["outdoor"] < 0
    assert temps[-1] == pytest.approx(20.0 + sum(cum[-1].values()))


def test_dimmer_power_follows_brightness():
    rows = [
        {
            "state": "on",
            "last_updated": "2026-11-02T10:00:00+00:00",
            "attributes": {"brightness": 255},
        },
        {
            "state": "on",
            "last_updated": "2026-11-02T11:00:00+00:00",
            "attributes": {"brightness": 51},
        },
        {"state": "off", "last_updated": "2026-11-02T12:00:00+00:00", "attributes": {}},
    ]
    kw = [v for _, v in dimmer_kw(rows, 105.0)]
    assert kw == pytest.approx([0.105, 0.021, 0.0])


def test_chart_points_thins_and_marks_forecast():
    now = datetime(2026, 11, 2, 12, tzinfo=UTC)
    past = history(MODEL, [20.0, 20.1, 20.2], [Inputs(0.0), Inputs(0.0)], 0.5)
    temps, cum = forecast(MODEL, 20.2, [Inputs(0.0)] * 4, 0.5)
    pts = chart_points(
        now, timedelta(minutes=30), past, [20.0, 20.1, 20.2], cum, temps, every=2
    )
    assert [p.get("forecast", 0) for p in pts] == [0, 0, 1, 1]
    assert pts[1]["t"] == now.isoformat()
