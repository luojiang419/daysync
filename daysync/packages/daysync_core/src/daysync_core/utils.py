from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_uuid() -> str:
    return str(uuid4())


def ensure_parent_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
