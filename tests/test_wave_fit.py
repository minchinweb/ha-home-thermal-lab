"""Tests for the wave fit (run with ``python -m unittest`` or pytest)."""

import importlib.util
import math
import pathlib
import unittest

_PATH = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "house_thermal_lab"
    / "wave_fit.py"
)
_SPEC = importlib.util.spec_from_file_location("wave_fit", _PATH)
wave_fit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wave_fit)


def _day(mean, amp, peak, step=1.0):
    w = 2 * math.pi / 24
    return [
        (h * step, mean + amp * math.cos(w * (h * step - peak)))
        for h in range(int(24 / step))
    ]


class FitDayTests(unittest.TestCase):
    def test_recovers_parameters(self):
        fit = wave_fit.fit_day(_day(10.0, 6.0, 15.0))
        self.assertAlmostEqual(fit.mean, 10.0, places=6)
        self.assertAlmostEqual(fit.amplitude, 6.0, places=6)
        self.assertAlmostEqual(fit.peak_hour, 15.0, places=6)
        self.assertAlmostEqual(fit.trough_hour, 3.0, places=6)
        self.assertLess(fit.rmse, 1e-9)

    def test_peak_wraps_past_midnight(self):
        fit = wave_fit.fit_day(_day(0.0, 3.0, 1.0))
        self.assertAlmostEqual(fit.peak_hour, 1.0, places=6)

    def test_non_sinusoidal_day_has_residual(self):
        samples = [(h, 20.0 if 10 <= h < 16 else 10.0) for h in range(24)]
        self.assertGreater(wave_fit.fit_day(samples).rmse, 1.0)

    def test_too_few_samples(self):
        with self.assertRaises(ValueError):
            wave_fit.fit_day([(0, 1.0), (6, 2.0)])

    def test_offset_wraps(self):
        self.assertAlmostEqual(wave_fit.signed_offset_hours(23.0, 1.0), -2.0)
        self.assertAlmostEqual(wave_fit.signed_offset_hours(15.0, 12.5), 2.5)


if __name__ == "__main__":
    unittest.main()
