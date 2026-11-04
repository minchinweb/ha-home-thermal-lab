"""Tests for the panel's series builders."""

from datetime import UTC, datetime, timedelta

from custom_components.home_thermal_lab.panel_data import (
    archive,
    future,
    heating_spans,
    merge_spans,
    ms,
    same_thermostat,
    series,
    setpoints,
    span,
    statistic_values,
    subtract_spans,
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


def test_span_rounds_out_to_whole_steps_and_skips_gaps():
    assert span([19.4, None, 22.6, float("nan")]) == [19.0, 23.0]
    assert span([-31.2, 28.9], 5.0) == [-35.0, 30.0]
    assert span([20.0]) == [20.0, 21.0]
    assert span([None]) is None


def test_statistic_values_and_setpoints():
    assert statistic_values([{"min": -3.0, "max": 4.5}, {"min": None, "max": 6}]) == [
        -3.0,
        4.5,
        6.0,
    ]
    rows = [
        _row(0, "heat", temperature=21),
        _row(5, "heat_cool", target_temp_low=19.5, target_temp_high="24"),
        _row(10, "off", temperature=None),
    ]
    assert setpoints(rows) == [21.0, 19.5, 24.0]


def test_same_thermostat_finds_the_other_rooms_on_a_climate():
    rooms = {
        "office": {
            "temperature_entity": "sensor.office",
            "registers": [{"climate": "climate.up"}],
        },
        "bedroom": {
            "temperature_entity": "sensor.bedroom",
            "registers": [{"climate": "climate.up"}, {"climate": None}],
        },
        "hall": {"temperature_entity": None, "registers": [{"climate": "climate.up"}]},
        "den": {
            "temperature_entity": "sensor.den",
            "registers": [{"climate": "climate.down"}],
        },
        "bath": {"temperature_entity": "sensor.bath", "registers": []},
    }
    assert same_thermostat(rooms, "climate.up", {"sensor.office"}) == [
        ("bedroom", "sensor.bedroom")
    ]


def test_merge_spans_joins_overlaps_and_touches():
    assert merge_spans([[5, 9], [0, 3], [3, 4], [8, 12]]) == [[0, 4], [5, 12]]
    assert merge_spans([]) == []


def test_subtract_spans_keeps_only_what_the_cover_does_not_reach():
    spans = [[0, 10], [20, 30]]
    cover = [[2, 4], [6, 7], [9, 25]]
    assert subtract_spans(spans, cover) == [[0, 2], [4, 6], [7, 9], [25, 30]]
    assert subtract_spans(spans, []) == [[0, 10], [20, 30]]
    assert subtract_spans(spans, [[-5, 50]]) == []


def test_future_carries_cooling_and_fan():
    points = [
        {"t": "2026-11-02T12:00:00+00:00", "temp": 20.0, "cool": 0.5, "fan": 0.25}
    ]
    got = future(points)
    assert got["cool"][0][1] == 0.5
    assert got["fan"][0][1] == 0.25
