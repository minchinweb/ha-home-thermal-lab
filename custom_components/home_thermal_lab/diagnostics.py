"""Diagnostics download: what the forecast archive holds (needs Home Assistant)."""

from __future__ import annotations

from .archive_store import get_store


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    """The archive's files, lines, bytes and zones, before the user clears it."""
    store = get_store(hass)
    return {
        "archive": {
            "directory": str(store.directory),
            "keep_days": entry.options.get("archive_keep_days", 0),
            "files": await store.stats(),
        }
    }
