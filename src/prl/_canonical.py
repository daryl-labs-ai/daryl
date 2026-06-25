"""Canonical serialization + hash/timestamp helpers for PRL (P0).

Repo-adaptation note
--------------------
The PRL reference implementation (Daryl DSM staging) composed a ``dcp.canonical``
module (RFC 8785 / JCS via the ``rfc8785`` package) for canonical bytes,
``sha256_uri``, and ``utc_now_ms``. **Neither ``dcp`` nor ``rfc8785`` exists in
this repository.** The repository's canonical layer is
:mod:`dsm_primitives` (``canonical_json`` / ``hash_canonical``, ADR-0002 v1).

To preserve the ADR/ROADMAP contract — ``content = canonical_bytes(payload)``
inline UTF-8 JSON, and ``content_hash = sha256_uri(bytes)`` as the universal
join key — this module exposes exactly the narrow surface PRL needs and
**composes** :func:`dsm_primitives.canonical_json` for the dict (Entry payload)
path. The byte form is deterministic (``sort_keys`` + tight separators +
``ensure_ascii``), so ``to_entry`` / ``from_entry`` round-trips are byte-stable —
the property hashes and signatures rely on.

Scope: bytes, hashes, and ISO-8601 timestamps only. No DSM, no RR, no I/O.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from dsm_primitives import canonical_json

_SHA256_PREFIX = "sha256:"

# Settings kept byte-identical to dsm_primitives.canonical_json so the non-dict
# path (e.g. hashing a bare path string for project_id) matches the dict path.
_JSON_KWARGS = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": True,
    "allow_nan": False,
}


def canonical_bytes(obj: Any) -> bytes:
    """Serialize *obj* to deterministic canonical UTF-8 bytes.

    Pydantic models are dumped first (``mode='json'``, ``by_alias=True``,
    ``exclude_none=True``). A dict payload is canonicalized through the
    repository primitive :func:`dsm_primitives.canonical_json`; other
    JSON-native shapes (e.g. a bare path string used for ``project_id``) take an
    identically-configured ``json.dumps`` path.
    """
    payload = (
        obj.model_dump(mode="json", by_alias=True, exclude_none=True)
        if hasattr(obj, "model_dump")
        else obj
    )
    if isinstance(payload, dict):
        return canonical_json(payload)
    return json.dumps(payload, **_JSON_KWARGS).encode("utf-8")


def sha256_uri(data: bytes) -> str:
    """Return the SHA-256 of *data* as a ``"sha256:<hex>"`` URI string.

    This is the PRL content-addressing / join-key representation (ADR: the join
    key stays ``content_hash = sha256_uri(bytes)``). The ``sha256:`` scheme is
    distinct from the kernel's ``v1:`` entry-hash format produced by
    :func:`dsm_primitives.hash_canonical`, which addresses a different concern.
    """
    return _SHA256_PREFIX + hashlib.sha256(data).hexdigest()


def utc_now_ms() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:mm:ss.sssZ``.

    Always three millisecond digits, always a trailing ``Z``, never an offset.
    """
    now = datetime.now(timezone.utc)
    return f"{now:%Y-%m-%dT%H:%M:%S}.{now.microsecond // 1000:03d}Z"


__all__ = ["canonical_bytes", "sha256_uri", "utc_now_ms"]
