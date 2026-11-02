"""Tests for forecasting a house's zones together."""

from datetime import UTC, datetime, timedelta
import math

import pytest

from custom_components.home_thermal_lab.house import (
    ZoneAhead,
    ZoneHistory,
    ZoneNow,
    forecast_house,
    hub_neighbours,
    neighbour_inputs,
)
from custom_components.home_thermal_lab.shadow import ZoneModel

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
STEPS = 24
PER_DAY = 96


def _zone(model, room=20.0, plan=21.0, neighbours=(), history=None) -> ZoneNow:
    return ZoneNow(
        model,
        room,
        False,
        [plan] * STEPS,
        0.1,
        [0.0] * STEPS,
        [0.0] * STEPS,
        neighbours=neighbours,
        history=history,
    )


def _history(days: int = 8, outdoor: float = -5.0) -> ZoneHistory:
    bins = days * PER_DAY
    start = NOW - timedelta(minutes=15 * bins)
    room = [20.0 + 0.5 * math.sin(2 * math.pi * i / PER_DAY) for i in range(bins)]
    return ZoneHistory(
        start,
        room,
        [outdoor] * bins,
        [0.0] * bins,
        [0.0] * bins,
        [-50.0] * bins,
        8.0,
    )


def test_unheated_zone_follows_its_heated_neighbour():
    hub = _zone(ZoneModel(a=0.03, c=0.0, h=3.0), room=19.0, plan=21.0)
    open_room = _zone(
        ZoneModel(a=0.02, c=0.0, n=0.3), room=19.0, plan=-50.0, neighbours=(0,)
    )
    alone = _zone(ZoneModel(a=0.02, c=0.0), room=19.0, plan=-50.0)
    out = forecast_house(NOW, [hub, open_room, alone], [-10.0] * STEPS, 0.25)
    assert [a.method for a in out] == ["model", "model", "model"]
    assert sum(out[0].duty) > 0
    assert out[1].temps[-1] > out[2].temps[-1] + 0.5


def test_zone_without_a_model_is_held_or_profiled():
    out = forecast_house(NOW, [_zone(None, room=18.0)], [-10.0] * STEPS, 0.25)
    assert out[0].method == "held"
    assert out[0].temps == pytest.approx([18.0] * (STEPS + 1))
    profiled = forecast_house(
        NOW, [_zone(None, room=20.0, history=_history())], [-5.0] * STEPS, 0.25
    )
    assert profiled[0].method == "profile"
    assert len(profiled[0].temps) == STEPS + 1


def test_hybrid_moves_with_a_colder_day_than_usual():
    model = ZoneModel(a=0.05, c=1.25)  # settles at 20 C with -5 C outdoors
    history = _history(outdoor=-5.0)
    usual = forecast_house(
        NOW, [_zone(model, plan=-50.0, history=history)], [-5.0] * STEPS, 0.25
    )[0]
    cold = forecast_house(
        NOW, [_zone(model, plan=-50.0, history=history)], [-25.0] * STEPS, 0.25
    )[0]
    assert usual.method == cold.method == "hybrid"
    assert cold.temps[-1] < usual.temps[-1] - 0.5
    # on a usual day the hybrid is D: the departure is zero
    d_only = forecast_house(
        NOW, [_zone(None, plan=-50.0, history=history)], [-5.0] * STEPS, 0.25
    )[0]
    assert usual.temps == pytest.approx(d_only.temps)


def test_hub_rule():
    near = hub_neighbours({"z1": 0.0, "z2": 3.0, "z4": 40.0})
    assert near == {"z1": ("z4",), "z2": ("z4",), "z4": ("z1", "z2")}
    chosen = hub_neighbours({"z1": 0.0, "z4": 40.0}, {"z1": ["z4", "z9", "z1"]})
    assert chosen["z1"] == ("z4",)
    assert hub_neighbours({"z1": 0.0, "z2": 0.0})["z2"] == ()


def test_neighbour_inputs():
    a = ZoneAhead([20.0, 21.0, 22.0], [1.0, 0.0], "model")
    b = ZoneAhead([18.0, 19.0, 20.0], [0.5, 0.5], "model")
    temps, duty = neighbour_inputs([a, b, a], (0, 1))
    assert temps == pytest.approx([19.0, 20.0])
    assert duty == pytest.approx([1.5, 0.5])
    assert neighbour_inputs([a], ()) is None
