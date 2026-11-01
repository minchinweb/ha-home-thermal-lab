"""Load settings from a ``.env`` file (standard library only)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / ".env"


def parse_env(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines.

    Blank lines and ``#`` comments are skipped, a leading ``export`` is
    allowed, and a value may be wrapped in single or double quotes. An
    unquoted value ends at a `` #`` comment.

    Args:
        text: The file contents.

    Returns:
        The settings found.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = line.removeprefix("export ").lstrip()
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in {'"', "'"} and value.endswith(value[0]) and len(value) > 1:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key.strip()] = value
    return values


def load_env(path: Path = DEFAULT_PATH) -> dict[str, str]:
    """Load ``path`` into ``os.environ``, keeping variables already set.

    A real environment variable wins over the file, so a one-off override
    still works. A missing file is fine.

    Args:
        path: The ``.env`` file.

    Returns:
        The settings read from the file.
    """
    if not path.is_file():
        return {}
    values = parse_env(path.read_text(encoding="utf-8"))
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values
