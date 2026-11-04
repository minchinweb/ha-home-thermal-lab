"""Tests for the forecast archive (standard library and ``tmp_path``)."""

from datetime import UTC, date, datetime, timedelta
import gzip
import json

import pytest

from custom_components.home_thermal_lab import archive
from custom_components.home_thermal_lab.archive import ReadCounts, append, read

T = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
WIDE = (datetime(2020, 1, 1, tzinfo=UTC), datetime(2030, 1, 1, tzinfo=UTC))


def room(at, zone="climate.a", **extra):
    return {"v": 1, "kind": "room", "at": at.isoformat(), "zone": zone, **extra}


def outdoor(at):
    return {"v": 1, "kind": "outdoor", "at": at.isoformat(), "hours": []}


def test_append_and_read_back_keeps_null(tmp_path):
    append(tmp_path, room(T, setpoint=None, leads={"1": 20.5}))
    append(tmp_path, outdoor(T))
    (got,) = list(read(tmp_path, "room", *WIDE))
    assert got["setpoint"] is None
    assert got["leads"] == {"1": 20.5}
    assert len(list(read(tmp_path, "outdoor", *WIDE))) == 1


def test_nan_cannot_be_written(tmp_path):
    with pytest.raises(ValueError):
        append(tmp_path, room(T, start=float("nan")))
    assert not list(tmp_path.glob("*.jsonl"))


def test_bad_records_are_rejected(tmp_path):
    for bad in (
        {"v": 2, "kind": "room", "at": T.isoformat()},
        {"v": 1, "kind": "nope", "at": T.isoformat()},
        {"v": 1, "kind": "room", "at": "2026-11-04T12:00:00"},
    ):
        with pytest.raises(ValueError):
            append(tmp_path, bad)


def test_month_boundary_in_utc(tmp_path):
    a = datetime(2026, 10, 31, 23, 45, tzinfo=UTC)
    b = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    append(tmp_path, room(a))
    append(tmp_path, room(b))
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "room-2026-10.jsonl",
        "room-2026-11.jsonl",
    ]
    got = [
        r["at"]
        for r in read(tmp_path, "room", a - timedelta(hours=1), b + timedelta(hours=1))
    ]
    assert got == [a.isoformat(), b.isoformat()]


def test_writer_skips_repeat_and_reader_merges_instants(tmp_path):
    assert append(tmp_path, room(T))
    assert not append(tmp_path, room(T))
    other = tmp_path / "other"
    append(other, room(T, zone="climate.b"))
    # same instant written two ways (as by two writers) is one record
    path = tmp_path / "room-2026-11.jsonl"
    with path.open("a", newline="\n") as f:
        f.write(json.dumps(room(T).copy() | {"at": "2026-11-04T12:00:00Z"}) + "\n")
    counts = ReadCounts()
    assert len(list(read(tmp_path, "room", *WIDE, counts=counts))) == 1
    assert counts.duplicates == 1


def test_truncated_last_line(tmp_path):
    append(tmp_path, room(T))
    path = tmp_path / "room-2026-11.jsonl"
    with path.open("a", newline="\n") as f:
        f.write('{"v":1,"kind":"room","at":"2026-11')
    counts = ReadCounts()
    assert len(list(read(tmp_path, "room", *WIDE, counts=counts))) == 1
    assert counts.malformed == 1
    append(tmp_path, room(T + timedelta(minutes=15)))
    assert len(list(read(tmp_path, "room", *WIDE))) == 2


def test_no_crlf(tmp_path):
    append(tmp_path, room(T))
    assert b"\r" not in (tmp_path / "room-2026-11.jsonl").read_bytes()


def test_compress_old(tmp_path):
    old = datetime(2026, 8, 30, tzinfo=UTC)
    append(tmp_path, room(old))
    append(tmp_path, room(T))
    before = list(read(tmp_path, "room", *WIDE))
    done = archive.compress_old(tmp_path, T)
    assert [p.name for p in done] == ["room-2026-08.jsonl.gz"]
    assert (tmp_path / "room-2026-11.jsonl").exists()
    assert list(read(tmp_path, "room", *WIDE)) == before


def fill(tmp_path):
    for month, day in ((9, 15), (10, 5), (10, 25), (11, 3)):
        for zone in ("climate.a", "climate.b"):
            append(tmp_path, room(datetime(2026, month, day, tzinfo=UTC), zone=zone))
        append(tmp_path, outdoor(datetime(2026, month, day, tzinfo=UTC)))


def test_clear_dry_run_changes_nothing(tmp_path):
    fill(tmp_path)
    names = sorted(p.name for p in tmp_path.iterdir())
    got = archive.clear(tmp_path)
    assert got["dry_run"] and got["lines"] == 12
    assert sorted(p.name for p in tmp_path.iterdir()) == names
    assert len(list(read(tmp_path, "room", *WIDE))) == 8


def test_clear_by_zone_keeps_others(tmp_path):
    fill(tmp_path)
    archive.clear(tmp_path, zones=["climate.a"], dry_run=False)
    zones = {r["zone"] for r in read(tmp_path, "room", *WIDE)}
    assert zones == {"climate.b"}
    assert len(list(read(tmp_path, "outdoor", *WIDE))) == 4


def test_clear_before_deletes_and_rewrites(tmp_path):
    fill(tmp_path)
    got = archive.clear(tmp_path, before=date(2026, 10, 10), dry_run=False)
    assert got["files_deleted"] == 2  # room and outdoor of September
    assert got["files_rewritten"] == 2  # October is split
    left = [r["at"][:10] for r in read(tmp_path, "room", *WIDE)]
    assert sorted(set(left)) == ["2026-10-25", "2026-11-03"]
    assert not list(tmp_path.glob("*.tmp"))


def test_clear_rewrites_gzip_as_gzip(tmp_path):
    append(tmp_path, room(datetime(2026, 8, 1, tzinfo=UTC)))
    append(tmp_path, room(datetime(2026, 8, 20, tzinfo=UTC)))
    archive.compress_old(tmp_path, T)
    archive.clear(tmp_path, before=date(2026, 8, 10), dry_run=False)
    path = tmp_path / "room-2026-08.jsonl.gz"
    with gzip.open(path, "rt") as f:
        assert len(f.read().splitlines()) == 1


def test_clear_unknown_scope_is_an_error(tmp_path):
    fill(tmp_path)
    for bad in ({"kinds": ["nope"]}, {"kinds": []}, {"zones": []}):
        with pytest.raises(ValueError):
            archive.clear(tmp_path, dry_run=False, **bad)
    assert len(list(read(tmp_path, "room", *WIDE))) == 8
    # a zone that matches nothing removes nothing
    assert archive.clear(tmp_path, zones=["climate.zz"], dry_run=False)["lines"] == 0


def test_stats(tmp_path):
    fill(tmp_path)
    s = archive.stats(tmp_path)
    assert s["room"]["2026-10"]["lines"] == 4
    assert s["room"]["2026-10"]["zones"] == ["climate.a", "climate.b"]
    assert s["outdoor"]["2026-09"]["malformed"] == 0


def test_room_record_shares_the_sensors_names():
    from custom_components.home_thermal_lab.archive_records import (
        room_record,
        shared,
    )

    common = shared(20.123, 21.0, "hybrid", ["Hall"], {1: 20.4, 3: None, 6: 22.0})
    record = room_record(
        at=T,
        zone="sensor.forecast_a",
        name="A",
        shared_fields=common,
        fallback=None,
        outdoor_at=T,
        outdoor_shift=0.0,
        fit_at=None,
        params={},
        leads={1: 20.4, 3: None, 6: 22.0},
        leads_d={1: None, 3: None, 6: None},
    )
    for name in ("start", "setpoint", "method", "neighbours"):
        assert record[name] == common[name]
    assert record["leads"]["1"] == common["predicted_1h"]
    assert record["leads"]["6"] == common["predicted_6h"]
    assert record["leads"]["3"] is None
    assert "path" not in record
    assert all(v is None for v in record["params"].values())
    assert json.dumps(record, allow_nan=False)


def test_d_leads():
    from custom_components.home_thermal_lab.archive_records import d_leads

    d = [float(k) for k in range(1, 5)] + [None] * 8  # steps 1..12 of 15 minutes
    got = d_leads(20.0, d, (1, 3, 6), 0.25)
    assert got == {1: 4.0, 3: None, 6: None}
    assert d_leads(20.0, None, (1,), 0.25) == {1: None}
