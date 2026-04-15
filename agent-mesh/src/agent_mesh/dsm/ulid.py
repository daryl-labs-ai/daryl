"""ULID helpers."""
from __future__ import annotations

from ulid import ULID


def new_event_id() -> str:
    return str(ULID())


def is_valid_ulid(s: str) -> bool:
    if not isinstance(s, str):
        return False
    try:
        ULID.from_str(s)
        return True
    except Exception:
        return False
