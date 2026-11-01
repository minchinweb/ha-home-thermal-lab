"""Tests for locations, loader and experiments (offline, fake fetcher)."""

import math
import unittest
from datetime import date, datetime, timedelta

from custom_components.house_thermal_lab import experiments, open_meteo, solar
from custom_components.house_thermal_lab.locations import (
    Location,
    locations_from_config,
)


def _fake_body(lon, start, days, peak_after_noon=3.0, amp=5.0, mean=10.0):
    """Hourly UTC data whose true peak is `peak_after_noon` h after solar noon."""
    times, temps = [], []
    t = datetime.combine(start, datetime.min.time())
    for _ in range(days * 24):
        solar_dt = t + timedelta(hours=lon / 15.0)
        hour = solar_dt.hour + solar_dt.minute / 60
        noon = solar.solar_noon_hour(solar_dt.date())
        temps.append(
            mean + amp * math.cos(2 * math.pi * (hour - noon - peak_after_noon) / 24)
        )
        times.append(t.strftime("%Y-%m-%dT%H:%M"))
        t += timedelta(hours=1)
    return {"hourly": {"time": times, "temperature_2m": temps}}


class LocationTests(unittest.TestCase):
    def test_from_config(self):
        locs = locations_from_config(
            [{"name": "A", "latitude": "1", "longitude": 2, "kind": "paradise"},
             {"name": "B", "latitude": 3, "longitude": 4}]
        )
        self.assertEqual([l.kind for l in locs], ["paradise", "other"])

    def test_invalid_latitude(self):
        with self.assertRaises(ValueError):
            Location("X", 95, 0)


class LoaderTests(unittest.TestCase):
    def test_url(self):
        url = open_meteo.build_url(Location("X", 1.5, -2.5), date(2025, 1, 1), date(2025, 1, 2))
        for part in ("latitude=1.5", "longitude=-2.5", "start_date=2025-01-01",
                     "hourly=temperature_2m", "timezone=GMT"):
            self.assertIn(part, url)

    def test_skips_missing_values(self):
        body = {"hourly": {"time": ["2025-01-01T00:00", "2025-01-01T01:00"],
                           "temperature_2m": [None, 3.0]}}
        out = open_meteo.fetch_hourly(Location("X", 0, 0), date(2025, 1, 1),
                                      date(2025, 1, 1), lambda url: body)
        self.assertEqual(len(out), 1)

    def test_solar_day_shift(self):
        # 15 degrees east is +1 h: 23:00 UTC falls on the next solar day at 00:00.
        days = open_meteo.to_solar_days([(datetime(2025, 1, 1, 23), 1.0)], 15.0)
        self.assertEqual(days, {date(2025, 1, 2): [(0.0, 1.0)]})


class SolarTests(unittest.TestCase):
    def test_equation_of_time_known_extremes(self):
        self.assertAlmostEqual(solar.equation_of_time_minutes(date(2025, 11, 3)), 16.4, delta=1.0)
        self.assertAlmostEqual(solar.equation_of_time_minutes(date(2025, 2, 11)), -14.2, delta=1.0)


class ExperimentTests(unittest.TestCase):
    def test_recovers_known_lag_at_any_longitude(self):
        for lon in (-113.5, 1.1, -149.4):
            loc = Location("T", 10.0, lon)
            body = _fake_body(lon, date(2025, 6, 1), 10)
            (s,) = experiments.run([loc], date(2025, 6, 1), date(2025, 6, 10),
                                   lambda url: body)
            self.assertAlmostEqual(s.median_fitted_peak_offset_h, 3.0, delta=0.05)
            self.assertAlmostEqual(s.median_observed_peak_offset_h, 3.0, delta=1.0)
            self.assertAlmostEqual(s.mean_amplitude, 5.0, delta=0.05)
            self.assertGreater(s.days, 7)

    def test_no_complete_days(self):
        body = {"hourly": {"time": ["2025-06-01T00:00"], "temperature_2m": [1.0]}}
        with self.assertRaises(ValueError):
            experiments.run([Location("T", 0, 0)], date(2025, 6, 1), date(2025, 6, 1),
                            lambda url: body)

    def test_table(self):
        body = _fake_body(0.0, date(2025, 6, 1), 5)
        text = experiments.format_table(
            experiments.run([Location("Tahiti", 0, 0, "paradise")], date(2025, 6, 1),
                            date(2025, 6, 5), lambda url: body))
        self.assertIn("Tahiti", text)
        self.assertIn("paradise", text)


if __name__ == "__main__":
    unittest.main()
