"""The forecast archive inside Home Assistant (needs Home Assistant).

``archive.py`` does the file work; this holds one directory, one lock and the
executor calls, the ``clear_archive`` service and the daily housekeeping.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
import logging
from pathlib import Path

from . import DOMAIN, archive

_LOGGER = logging.getLogger(__name__)

KEEP_DAYS = "archive_keep_days"


class ArchiveStore:
    """One archive directory, written one executor call at a time."""

    def __init__(self, hass) -> None:
        self.hass = hass
        self.directory = Path(hass.config.path("home_thermal_lab", "archive"))
        self._lock = asyncio.Lock()

    async def _run(self, func, *args, **kwargs):
        async with self._lock:
            return await self.hass.async_add_executor_job(
                partial(func, *args, **kwargs)
            )

    async def append(self, record: dict) -> bool:
        """Append a record (raises on a bad record or a file error)."""
        return await self._run(archive.append, self.directory, record)

    async def read(
        self,
        kind: str,
        start: datetime,
        end: datetime,
        zone: str | None = None,
    ) -> list[dict]:
        """The records of ``kind`` with ``start <= at < end``."""
        return await self._run(
            lambda: list(archive.read(self.directory, kind, start, end, zone))
        )

    async def first_at(self, kind: str) -> datetime | None:
        """When the archive's first ``kind`` record was issued, if any."""

        def first():
            found = archive.stats(self.directory).get(kind, {})
            firsts = [m["first"] for m in found.values() if m["first"]]
            return min(archive.parse_instant(f) for f in firsts) if firsts else None

        return await self._run(first)

    async def stats(self) -> dict:
        return await self._run(archive.stats, self.directory)

    async def clear(self, **kwargs) -> dict:
        return await self._run(archive.clear, self.directory, **kwargs)

    async def housekeeping(self, keep_days: int = 0, now: datetime | None = None):
        """Gzip old months and apply the retention rule (0 keeps everything)."""
        now = now or datetime.now(UTC)
        packed = await self._run(archive.compress_old, self.directory, now)
        if packed:
            _LOGGER.info("Archive: compressed %s", ", ".join(p.name for p in packed))
        if keep_days > 0:
            cut = (now - timedelta(days=keep_days)).date()
            got = await self.clear(before=cut, dry_run=False)
            if got["lines"]:
                _LOGGER.info(
                    "Archive: removed %d lines before %s (%d bytes freed)",
                    got["lines"],
                    cut,
                    got["bytes_freed"],
                )


def get_store(hass) -> ArchiveStore:
    """The one archive store of this Home Assistant instance."""
    data = hass.data.setdefault(DOMAIN, {})
    if "archive" not in data:
        data["archive"] = ArchiveStore(hass)
    return data["archive"]
