"""Tests for the panel's series builders."""

from datetime import UTC, datetime, timedelta

from custom_components.home_thermal_lab.panel_data import (
    archive,
    future,
    heating_spans,
    ms,
    series,
)

T0 = datetime(2026, 11, 2, tzinfo=UTC)


def _row(minutes: float, state, **attrs) -> dict:
    when = (T0 + timedelta(minutes=minutes)).isoformat()
    return {
        "state": state,
        "last_changed": when,
        "last_updated": when,
        "attributes": attrs,
    }


def test_series_reads_state_or_attribute_and_drops_repeats():
    rows = [_row(0, "20.0"), _row(5, "20.0"), _row(10, "unavailable"), _row(15, "21")]
    assert series(rows) == [
        [ms(T0), 20.0],
        [ms(T0 + timedelta(minutes=10)), None],
        [ms(T0 + timedelta(minutes=15)), 21.0],
    ]
    rows = [_row(0, "heat", temperature=21), _row(5, "heat", temperature=20.5)]
    assert [p[1] for p in series(rows, "temperature")] == [21.0, 20.5]


def test_archive_places_each_forecast_at_its_due_time():
    issued = (T0 + timedelta(minutes=15)).isoformat()
    rows = [
        _row(15, "20.4", issued=issued),
        _row(16, "20.4", issued=issued),  # same forecast again
        _row(30, "unknown", issued=(T0 + timedelta(minutes=30)).isoformat()),
    ]
    assert archive(rows) == [[ms(T0 + timedelta(hours=3, minutes=15)), 20.4]]


def test_heating_spans_from_hvac_action():
    rows = [
        _row(0, "heat", hvac_action="idle"),
        _row(10, "heat", hvac_action="heating"),
        _row(25, "heat", hvac_action="idle"),
    ]
    spans = heating_spans(rows, T0 + timedelta(hours=1))
    assert spans == [[ms(T0 + timedelta(minutes=10)), ms(T0 + timedelta(minutes=25))]]


def test_future_splits_points():
    points = [
        {"t": T0.isoformat(), "temp": 20.0, "outdoor": -5.0, "heat": 0.5},
        {"t": (T0 + timedelta(minutes=30)).isoformat(), "temp": 20.1, "lower": 19.5},
    ]
    got = future(points)
    assert got["temp"] == [[ms(T0), 20.0], [ms(T0 + timedelta(minutes=30)), 20.1]]
    assert got["heat"] == [[ms(T0), 0.5]]
    assert got["lower"] == [[ms(T0 + timedelta(minutes=30)), 19.5]]
    assert got["upper"] == []
