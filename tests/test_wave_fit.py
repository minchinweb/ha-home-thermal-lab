"""Tests for the wave fit."""

import math

import pytest

from custom_components.home_thermal_lab import wave_fit


def _day(mean, amp, peak, step=1.0):
    w = 2 * math.pi / 24
    return [
        (h * step, mean + amp * math.cos(w * (h * step - peak)))
        for h in range(int(24 / step))
    ]


def test_recovers_parameters():
    fit = wave_fit.fit_day(_day(10.0, 6.0, 15.0))
    assert fit.mean == pytest.approx(10.0)
    assert fit.amplitude == pytest.approx(6.0)
    assert fit.peak_hour == pytest.approx(15.0)
    assert fit.trough_hour == pytest.approx(3.0)
    assert fit.rmse < 1e-9


def test_peak_wraps_past_midnight():
    fit = wave_fit.fit_day(_day(0.0, 3.0, 1.0))
    assert fit.peak_hour == pytest.approx(1.0)


def test_non_sinusoidal_day_has_residual():
    samples = [(h, 20.0 if 10 <= h < 16 else 10.0) for h in range(24)]
    assert wave_fit.fit_day(samples).rmse > 1.0


def test_too_few_samples():
    with pytest.raises(ValueError, match="at least 4"):
        wave_fit.fit_day([(0, 1.0), (6, 2.0)])


def test_offset_wraps():
    assert wave_fit.signed_offset_hours(23.0, 1.0) == pytest.approx(-2.0)
    assert wave_fit.signed_offset_hours(15.0, 12.5) == pytest.approx(2.5)
