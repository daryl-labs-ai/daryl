"""Event envelope builder."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .ulid import is_valid_ulid, new_event_id

_DEFAULT_AUTH = {
    "transport_authenticated": False,
    "signature_present": False,
    "signature_verified": False,
    "key_id": None,
    "signature_algorithm": None,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build_event(
    event_type: str,
    event_version: str,
    scope_type: str,
    scope_id: str,
    source_type: str,
    source_id: str,
    writer_type: str,
    writer_id: str,
    payload: dict,
    parent_event_id: str | None = None,
    causal_refs: list[str] | None = None,
    auth: dict | None = None,
) -> dict[str, Any]:
    refs = list(causal_refs or [])
    if len(refs) > 8:
        raise ValueError("causal_refs cannot exceed 8 items")
    if len(set(refs)) != len(refs):
        raise ValueError("causal_refs must be unique")
    for r in refs:
        if not is_valid_ulid(r):
            raise ValueError(f"causal_refs contains invalid ULID: {r}")

    return {
        "event_id": new_event_id(),
        "schema_version": "1.0",
        "event_type": event_type,
        "event_version": event_version,
        "timestamp": _iso_now(),
        "scope_type": scope_type,
        "scope_id": scope_id,
        "source_type": source_type,
        "source_id": source_id,
        "writer_type": writer_type,
        "writer_id": writer_id,
        "payload": payload,
        "links": {
            "parent_event_id": parent_event_id,
            "causal_refs": refs,
        },
        "auth": dict(auth) if auth is not None else dict(_DEFAULT_AUTH),
    }
