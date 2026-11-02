"""Tests for forecast scoring, the outdoor bias and the target wave."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.home_thermal_lab.scoring import (
    Issued,
    apply_bias,
    held_at,
    outdoor_bias,
    score,
)
from custom_components.home_thermal_lab.target import (
    TargetWave,
    setpoint_band,
    target_at,
)

T0 = datetime(2026, 11, 2, tzinfo=UTC)
H = timedelta(hours=1)


def test_held_at_takes_the_last_reading_within_age():
    series = [(T0, 20.0), (T0 + H, 21.0)]
    assert held_at(series, T0 + 0.5 * H, timedelta(hours=6)) == 20.0
    assert held_at(series, T0 + 2 * H, timedelta(hours=6)) == 21.0
    assert held_at(series, T0 - H, timedelta(hours=6)) is None
    assert held_at(series, T0 + 9 * H, timedelta(hours=6)) is None


def test_score_groups_by_lead_and_skips_the_future():
    actual = [(T0 + k * H, 20.0 + 0.1 * k) for k in range(10)]
    issued = [
        Issued(T0, 3.0, 20.5, 20.0),  # actual 20.3: +0.2, change +0.5 vs +0.3
        Issued(T0 + H, 3.0, 20.2, 20.1),  # actual 20.4: -0.2
        Issued(T0, 1.0, 20.1),  # actual 20.1: 0, no start
        Issued(T0 + 8 * H, 3.0, 25.0, 20.8),  # not due yet
    ]
    got = score(issued, actual, T0 + 9 * H)
    assert set(got) == {1.0, 3.0}
    three = got[3.0]
    assert three.n == 2
    assert three.mae == pytest.approx(0.2)
    assert three.bias == pytest.approx(0.0)
    assert three.rmse == pytest.approx(0.2)
    assert three.change_mae == pytest.approx(0.2)
    assert got[1.0].change_mae is None
    assert got[1.0].mae == pytest.approx(0.0)


def test_outdoor_bias_compares_hourly_means():
    measured = [(T0 + k * timedelta(minutes=30), -4.0) for k in range(20)]
    forecast = [(T0 + k * H, -5.0) for k in range(1, 12)]
    bias, n = outdoor_bias(measured, forecast, T0, T0 + 8 * H)
    assert n == 8
    assert bias == pytest.approx(1.0)
    assert outdoor_bias([], forecast, T0, T0 + 8 * H) == (0.0, 0)


def test_apply_bias_needs_enough_hours_and_is_capped():
    assert apply_bias([1.0, 2.0], 1.0, 5) == ([1.0, 2.0], 0.0)
    assert apply_bias([1.0, 2.0], 0.1, 48) == ([1.0, 2.0], 0.0)
    assert apply_bias([1.0, 2.0], -1.0, 48) == ([0.0, 1.0], -1.0)
    assert apply_bias([0.0], 9.0, 48) == ([4.0], 4.0)


def test_target_wave_peaks_at_its_hour():
    wave = TargetWave(mean=20.0, swing=1.0, peak_hour=15.0, band=0.5)
    peak = target_at(wave, 15.0)
    assert peak.centre == pytest.approx(21.0)
    assert (peak.lower, peak.upper) == pytest.approx((20.5, 21.5))
    assert target_at(wave, 3.0).centre == pytest.approx(19.0)
    assert target_at(wave, 9.0).centre == pytest.approx(20.0)
    flat = setpoint_band(21.0, 0.5)
    assert (flat.lower, flat.centre, flat.upper) == (20.5, 21.0, 21.0)


def test_issued_from_rows_reads_each_forecast_once():
    from custom_components.home_thermal_lab.scoring import issued_from_rows

    stamp = T0.isoformat()
    attrs = {"issued": stamp, "start": 20.0, "predicted_1h": 20.1}
    rows = [
        {"state": "20.3", "attributes": attrs | {"predicted_6h": None}},
        {"state": "20.3", "attributes": attrs},
        {"state": "20.5", "attributes": {}},
    ]
    got = issued_from_rows(rows)
    assert sorted((f.lead_hours, f.predicted) for f in got) == [
        (1.0, 20.1),
        (3.0, 20.3),
    ]
    assert all(f.issued == T0 and f.start == 20.0 for f in got)
