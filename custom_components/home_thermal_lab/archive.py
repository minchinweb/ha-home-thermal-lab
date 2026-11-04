"""Archive of the forecasts as issued, in files the recorder does not purge.

Standard library only (like ``scoring.py``), so it can be tested without Home
Assistant. One JSON Lines file per kind and UTC month (``room-2026-11.jsonl``);
a month is gzipped once it is old (``room-2026-09.jsonl.gz``). Every line has
``v`` (the schema version), ``kind`` and ``at`` (the issue time, a UTC instant).
A missing value is JSON ``null``, never 0.

The writer decides what counts as new (a record whose ``(kind, zone, at)``
matches the last one written for that zone is skipped); the reader also drops
duplicates as a safeguard. Locking is the caller's job (one writer per
directory at a time).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
import gzip
import json
import os
from pathlib import Path
import re

SCHEMA = 1
KINDS = ("room", "outdoor")

_NAME = re.compile(r"^(?P<kind>[a-z]+)-(?P<y>\d{4})-(?P<m>\d{2})\.jsonl(?P<gz>\.gz)?$")

# The last (kind, zone, at) written, per directory, to skip a repeat.
_last: dict[tuple[str, str, str | None], datetime] = {}


def parse_instant(text: str) -> datetime:
    """Parse an ISO 8601 instant with an offset into UTC; naive text is an error."""
    when = datetime.fromisoformat(text)
    if when.tzinfo is None:
        raise ValueError(f"instant without an offset: {text!r}")
    return when.astimezone(UTC)


def _month_of(when: datetime) -> tuple[int, int]:
    return when.year, when.month


def _months_between(start: datetime, end: datetime) -> Iterator[tuple[int, int]]:
    y, m = _month_of(start.astimezone(UTC))
    last = _month_of(end.astimezone(UTC))
    while (y, m) <= last:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _files(directory: Path) -> list[tuple[str, int, int, Path]]:
    """The archive files as ``(kind, year, month, path)``, oldest first."""
    out = []
    if not directory.is_dir():
        return out
    for path in directory.iterdir():
        found = _NAME.match(path.name)
        if found and found["kind"] in KINDS:
            out.append((found["kind"], int(found["y"]), int(found["m"]), path))
    return sorted(out)


def _open_read(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _check(record: dict) -> datetime:
    if record.get("v") != SCHEMA:
        raise ValueError(f"unsupported schema version: {record.get('v')!r}")
    if record.get("kind") not in KINDS:
        raise ValueError(f"unknown kind: {record.get('kind')!r}")
    if not isinstance(record.get("at"), str):
        raise ValueError("record has no 'at' instant")  # noqa: TRY004
    return parse_instant(record["at"])


def append(directory: Path, record: dict) -> bool:
    """Append one record to its month's file; returns False if it was a repeat.

    Raises:
        ValueError: The record has no valid ``v``, ``kind`` or ``at``, or holds
            a NaN or infinity.
    """
    when = _check(record)
    line = json.dumps(record, allow_nan=False, separators=(",", ":"))
    key = (str(directory), record["kind"], record.get("zone"))
    if _last.get(key) == when:
        return False
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['kind']}-{when.year:04d}-{when.month:02d}.jsonl"
    lead = ""
    if path.exists() and path.stat().st_size:
        with path.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                lead = "\n"  # a crash left a partial last line
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(lead + line + "\n")
    _last[key] = when
    return True


@dataclass
class ReadCounts:
    """What ``read`` skipped; pass one in to see it."""

    malformed: int = 0
    duplicates: int = 0


def _lines(path: Path, counts: ReadCounts | None) -> Iterator[dict]:
    try:
        with _open_read(path) as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    rec = json.loads(text)
                    if not isinstance(rec, dict):
                        raise TypeError
                    rec["_when"] = _check(rec)
                except (ValueError, TypeError, EOFError, OSError):
                    if counts is not None:
                        counts.malformed += 1
                    continue
                yield rec
    except (EOFError, OSError):  # a truncated gzip
        if counts is not None:
            counts.malformed += 1


def read(
    directory: Path,
    kind: str,
    start: datetime,
    end: datetime,
    zone: str | None = None,
    counts: ReadCounts | None = None,
) -> Iterator[dict]:
    """Records of ``kind`` with ``start <= at < end``, in file order.

    Only the month files overlapping the range are opened. A malformed line is
    skipped and counted in ``counts``, never raised.
    """
    seen: set[tuple] = set()
    wanted = set(_months_between(start, end))
    for k, y, m, path in _files(directory):
        if k != kind or (y, m) not in wanted:
            continue
        for rec in _lines(path, counts):
            when = rec.pop("_when")
            if not start <= when < end:
                continue
            if zone is not None and rec.get("zone") != zone:
                continue
            ident = (kind, rec.get("zone"), when)
            if ident in seen:
                if counts is not None:
                    counts.duplicates += 1
                continue
            seen.add(ident)
            yield rec


def compress_old(
    directory: Path, now: datetime, keep_plain_months: int = 2
) -> list[Path]:
    """Gzip month files that are ``keep_plain_months`` or more months old."""
    ny, nm = _month_of(now.astimezone(UTC))
    done = []
    for _, y, m, path in _files(directory):
        if path.suffix == ".gz":
            continue
        if (ny * 12 + nm) - (y * 12 + m) < keep_plain_months:
            continue
        target = path.with_name(path.name + ".gz")
        temp = path.with_name(path.name + ".gz.tmp")
        with path.open("rb") as src, gzip.open(temp, "wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
        temp.replace(target)
        path.unlink()
        done.append(target)
    return done


def stats(directory: Path) -> dict:
    """Per kind and month: lines, bytes, malformed, first and last ``at``, zones."""
    out: dict[str, dict[str, dict]] = {}
    for kind, y, m, path in _files(directory):
        counts = ReadCounts()
        lines, first, last, zones = 0, None, None, set()
        for rec in _lines(path, counts):
            lines += 1
            when = rec["_when"]
            first = when if first is None or when < first else first
            last = when if last is None or when > last else last
            if rec.get("zone"):
                zones.add(rec["zone"])
        out.setdefault(kind, {})[f"{y:04d}-{m:02d}"] = {
            "file": path.name,
            "lines": lines,
            "bytes": path.stat().st_size,
            "malformed": counts.malformed,
            "first": None if first is None else first.isoformat(),
            "last": None if last is None else last.isoformat(),
            "zones": sorted(zones),
        }
    return out


@dataclass
class ClearResult:
    """What ``clear`` removed (or would remove, in a dry run)."""

    files_deleted: int = 0
    files_rewritten: int = 0
    lines: int = 0
    bytes_freed: int = 0
    dry_run: bool = True
    paths: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "files_deleted": self.files_deleted,
            "files_rewritten": self.files_rewritten,
            "lines": self.lines,
            "bytes_freed": self.bytes_freed,
            "files": self.paths,
        }


def clear(
    directory: Path,
    *,
    kinds=None,
    zones=None,
    before: datetime | date | None = None,
    dry_run: bool = True,
) -> dict:
    """Remove records by kind, zone and date; a dry run (the default) reads only.

    Args:
        kinds: Kinds to clear (default all).
        zones: Zones to clear (default all; only room records have a zone, so
            giving zones leaves other kinds alone).
        before: Remove records with ``at`` before this (default no limit). A
            plain date means midnight UTC.
        dry_run: Report only.

    Raises:
        ValueError: An unknown kind, or an empty ``kinds`` or ``zones`` (a
            scope that matches nothing must not mean everything).
    """
    if kinds is not None:
        kinds = list(kinds)
        if not kinds or any(k not in KINDS for k in kinds):
            raise ValueError(f"unknown or empty kinds: {kinds!r}")
    if zones is not None:
        zones = set(zones)
        if not zones:
            raise ValueError("empty zones")
    if isinstance(before, date) and not isinstance(before, datetime):
        before = datetime(before.year, before.month, before.day, tzinfo=UTC)
    result = ClearResult(dry_run=dry_run)
    if not dry_run:  # what was written last may be gone
        for key in [k for k in _last if k[0] == str(directory)]:
            del _last[key]
    for kind, _y, _m, path in _files(directory):
        if kinds is not None and kind not in kinds:
            continue
        if zones is not None and kind != "room":
            continue
        keep, drop = [], 0
        for line in _raw_lines(path):
            rec = _parse_line(line)
            if rec is not None and _matches(rec, zones, before):
                drop += 1
            else:
                keep.append(line)  # malformed lines are kept, not guessed at
        if not drop:
            continue
        size = path.stat().st_size
        result.lines += drop
        result.paths.append(path.name)
        if not keep:
            result.files_deleted += 1
            result.bytes_freed += size
            if not dry_run:
                path.unlink()
            continue
        result.files_rewritten += 1
        if dry_run:
            result.bytes_freed += max(0, size - _estimated(path, keep))
            continue
        temp = path.with_name(path.name + ".tmp")
        if path.suffix == ".gz":
            with gzip.open(temp, "wt", encoding="utf-8", newline="\n") as f:
                f.writelines(keep)
        else:
            with temp.open("w", encoding="utf-8", newline="\n") as f:
                f.writelines(keep)
        temp.replace(path)
        result.bytes_freed += max(0, size - path.stat().st_size)
    return result.as_dict()


def _raw_lines(path: Path) -> list[str]:
    try:
        with _open_read(path) as f:
            return [ln if ln.endswith("\n") else ln + "\n" for ln in f if ln.strip()]
    except (EOFError, OSError):
        return []


def _parse_line(line: str) -> dict | None:
    try:
        rec = json.loads(line)
        rec["_when"] = _check(rec)
    except (ValueError, TypeError):
        return None
    return rec


def _matches(rec: dict, zones: set | None, before: datetime | None) -> bool:
    if zones is not None and rec.get("zone") not in zones:
        return False
    return before is None or rec["_when"] < before


def _estimated(path: Path, keep: list[str]) -> int:
    return sum(len(ln.encode("utf-8")) for ln in keep)
