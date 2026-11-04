"""Tests for ``predict_rc.py --archive`` (the issued outdoor forecast)."""

from datetime import UTC, datetime, timedelta

import pytest

np = pytest.importorskip("numpy")
predict_rc = pytest.importorskip("predict_rc")

from custom_components.home_thermal_lab import archive  # noqa: E402

START = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)  # local midnight in UTC-6
WIDTH = timedelta(minutes=15)
PER_DAY = 96


def outdoor(at, temps_by_end):
    return {
        "v": 1,
        "kind": "outdoor",
        "at": at.isoformat(),
        "hours": [[end.isoformat(), t, 0.0, 0.0, 0.0] for end, t in temps_by_end],
    }


def hour_ends(first, n):
    return [first + timedelta(hours=k + 1) for k in range(n)]


def test_each_day_uses_the_forecast_issued_at_its_midnight(tmp_path):
    bins = 2 * PER_DAY
    measured = np.full(bins, 10.0)
    # issued the evening before day 1: -5 for its hours; issued 30 minutes
    # after day 2's midnight (too late to use): 99
    day1, day2 = START, START + timedelta(days=1)
    archive.append(
        tmp_path,
        outdoor(day1 - timedelta(hours=3), [(e, -5.0) for e in hour_ends(day1, 24)]),
    )
    archive.append(
        tmp_path,
        outdoor(day2 + timedelta(minutes=30), [(e, 99.0) for e in hour_ends(day2, 24)]),
    )
    got = predict_rc._issued_outdoor(tmp_path, measured, START, bins, WIDTH)
    assert list(got[:PER_DAY]) == [-5.0] * PER_DAY
    # day 2: the day 1 forecast covers day 1 only, so measured stays
    assert list(got[PER_DAY:]) == [10.0] * PER_DAY
    assert list(measured) == [10.0] * bins  # the input is not changed


def test_a_later_issue_before_midnight_wins_and_gaps_fall_back(tmp_path):
    bins = PER_DAY
    measured = np.full(bins, 10.0)
    ends = hour_ends(START, 12)  # only the first 12 hours
    archive.append(
        tmp_path, outdoor(START - timedelta(hours=6), [(e, 1.0) for e in ends])
    )
    archive.append(
        tmp_path, outdoor(START - timedelta(hours=1), [(e, 2.0) for e in ends])
    )
    got = predict_rc._issued_outdoor(tmp_path, measured, START, bins, WIDTH)
    assert list(got[: 12 * 4]) == [2.0] * 48
    assert list(got[12 * 4 :]) == [10.0] * 48


def test_no_archive_leaves_the_measured_series(tmp_path):
    measured = np.full(PER_DAY, 10.0)
    got = predict_rc._issued_outdoor(tmp_path / "none", measured, START, PER_DAY, WIDTH)
    assert list(got) == list(measured)
