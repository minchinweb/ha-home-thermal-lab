"""Tests for the zone outlook (hypothesis 16, revised)."""

from datetime import UTC, datetime

import pytest

from custom_components.home_thermal_lab.outlook import (
    band_at,
    build_outlook,
    outlook_points,
)
from custom_components.home_thermal_lab.shadow import ZoneModel
from custom_components.home_thermal_lab.target import TargetWave

NOW = datetime(2026, 11, 2, 6, tzinfo=UTC)


def _outlook(model, room=20.0, steps=96, **kwargs):
    return build_outlook(
        NOW,
        room,
        model,
        [-15.0] * steps,
        [0.0] * steps,
        0.25,
        20.0,
        [(k * 0.25) % 24 for k in range(steps + 1)],
        **kwargs,
    )


def test_outlook_heats_and_holds_near_the_setpoint():
    out = _outlook(ZoneModel(a=0.02, c=0.0, h=1.5))
    assert len(out.times) == len(out.temps) == len(out.duty) == 97
    assert min(out.temps) > 19.5
    assert max(out.temps) <= 20.0 + 1e-9
    assert 0 < sum(out.duty) < 96
    assert out.at(0) == 20.0
    assert out.at(3) == out.temps[12]
    assert out.at(30) is None


def test_outlook_without_a_heating_rate_drifts_down():
    out = _outlook(ZoneModel(a=0.02, c=0.0))
    assert sum(out.duty) == 0
    assert out.temps[-1] < 17.0


def test_band_follows_the_wave_or_the_setpoint():
    wave = TargetWave(20.0, 1.0, 15.0, 0.5)
    assert band_at(wave, 22.0, 0.5, 15.0).upper == pytest.approx(21.5)
    assert band_at(None, 22.0, 0.5, 15.0).lower == pytest.approx(21.5)


def test_points_average_the_duty():
    out = _outlook(ZoneModel(a=0.02, c=0.0, h=1.5), wave=TargetWave(20.0))
    points = outlook_points(out, every=2)
    assert len(points) == 49
    assert points[0]["t"] == NOW.isoformat()
    assert {"temp", "outdoor", "heat", "lower", "upper"} <= set(points[0])
    assert all(0.0 <= p["heat"] <= 1.0 for p in points)
    assert points[0]["lower"] == pytest.approx(19.5)


def test_schedule_by_slot_reads_the_last_day():
    from datetime import timedelta

    from custom_components.home_thermal_lab.outlook import schedule_by_slot, slot_of

    end = datetime(2026, 11, 2, 9, 7)
    changes = [
        (datetime(2026, 10, 31, 22, 0), 19.0),
        (datetime(2026, 11, 1, 6, 0), 21.0),
        (datetime(2026, 11, 1, 22, 0), 19.0),
        (datetime(2026, 11, 2, 6, 0), 21.5),
    ]
    got = schedule_by_slot(changes, end)
    assert len(got) == 96
    assert got[slot_of(datetime(2026, 11, 2, 5, 45))] == 19.0  # this morning
    assert got[slot_of(datetime(2026, 11, 2, 7, 0))] == 21.5  # this morning
    assert got[slot_of(datetime(2026, 11, 2, 12, 0))] == 21.0  # yesterday noon
    assert got[slot_of(datetime(2026, 11, 2, 23, 0))] == 19.0  # yesterday night
    assert schedule_by_slot([], end) == [None] * 96
    assert slot_of(end - timedelta(minutes=7)) == 36


def test_setpoints_follow_the_program_after_its_next_change():
    from custom_components.home_thermal_lab.outlook import setpoints_ahead

    schedule = [19.0] * 24 + [21.0] * 64 + [19.0] * 8
    slots = list(range(20, 30))
    got = setpoints_ahead(20.0, schedule, slots)
    assert got[:4] == [20.0] * 4  # a hand-set 20 holds until 06:00
    assert got[4:] == [21.0] * 6
    assert setpoints_ahead(20.0, None, [1, 2]) == [20.0, 20.0]
    assert setpoints_ahead(20.0, [None] * 96, [1, 2]) == [20.0, 20.0]


def test_outlook_takes_a_setpoint_per_step():
    plan = [18.0] * 48 + [21.0] * 48
    out = build_outlook(
        NOW,
        18.0,
        ZoneModel(a=0.02, c=0.0, h=3.0),
        [-15.0] * 96,
        [0.0] * 96,
        0.25,
        plan,
        [(k * 0.25) % 24 for k in range(97)],
    )
    assert out.temps[48] < 18.1
    assert out.temps[-1] > 20.5
    assert out.bands[0].centre == 18.0
    assert out.bands[60].centre == 21.0
