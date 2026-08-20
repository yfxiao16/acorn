"""Tiny stdlib .env loader (no python-dotenv dependency).

Existing environment variables always win; blank values are ignored.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> bool:
    p = Path(path) if path else Path.cwd() / ".env"
    if not p.exists():
        return False
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if value and key not in os.environ:
            os.environ[key] = value
    return True
