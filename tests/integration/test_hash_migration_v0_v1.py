"""Integration test: V4-A.2 migration v0 → v1 hash format.

Proves that:
1. A v0 hash (bare hex, pre-ADR-0002) can still be verified post-migration.
2. A new v1 hash can chain off a v0 prev_hash and the chain stays verifiable.
3. The wrapper _compute_canonical_entry_hash now produces v1 format.
"""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from dsm_primitives import hash_canonical, verify_hash


# ---------- Helpers ----------

def _legacy_v0_hash(canonical_entry: dict) -> str:
    """Reproduce the pre-V4-A.2 hash exactly: json.dumps with the same
    parameters as the legacy implementation in storage.py before V4-A.2.

    Explicit ensure_ascii=True and allow_nan=False to lock the format
    against future Python default changes.
    """
    serialized = json.dumps(
        canonical_entry,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _make_canonical(session_id, source, timestamp, metadata, content, prev_hash):
    return {
        "session_id": session_id,
        "source": source,
        "timestamp": timestamp,
        "metadata": metadata,
        "content": content,
        "prev_hash": prev_hash,
    }


# ---------- Tests ----------

def test_v0_hash_still_verifiable():
    """A bare-hex v0 hash from pre-V4-A.2 must verify after migration."""
    canonical = _make_canonical(
        "s1", "test", "2026-01-01T00:00:00Z", {}, {"msg": "hello"}, None
    )
    h0 = _legacy_v0_hash(canonical)
    assert ":" not in h0
    assert len(h0) == 64
    assert verify_hash(canonical, h0) is True


def test_v1_hash_produced_by_hash_canonical():
    """Post-migration, hash_canonical produces v1 prefixed format."""
    canonical = _make_canonical(
        "s1", "test", "2026-01-01T00:00:00Z", {}, {"msg": "hello"}, None
    )
    h1 = hash_canonical(canonical)
    assert h1.startswith("v1:")
    assert len(h1) == 67


def test_chain_v0_then_v1():
    """Critical: an entry with prev_hash = <v0 hex> can be hashed
    in v1 and the chain remains verifiable end-to-end."""
    entry1 = _make_canonical(
        "s1", "test", "2026-01-01T00:00:00Z", {}, {"msg": "first"}, None
    )
    h0 = _legacy_v0_hash(entry1)
    assert verify_hash(entry1, h0) is True

    entry2 = _make_canonical(
        "s1", "test", "2026-01-01T00:01:00Z", {}, {"msg": "second"}, h0
    )
    h1 = hash_canonical(entry2)
    assert verify_hash(entry2, h1) is True

    assert verify_hash(entry1, h0) and verify_hash(entry2, h1)


def test_chain_v1_then_v1():
    """Pure v1 chain — sanity check that verify_hash routes both ends."""
    entry1 = _make_canonical(
        "s1", "test", "2026-01-01T00:00:00Z", {}, {"msg": "a"}, None
    )
    h1 = hash_canonical(entry1)

    entry2 = _make_canonical(
        "s1", "test", "2026-01-01T00:01:00Z", {}, {"msg": "b"}, h1
    )
    h2 = hash_canonical(entry2)

    assert verify_hash(entry1, h1) is True
    assert verify_hash(entry2, h2) is True


def test_storage_wrapper_produces_v1():
    """The internal wrapper must now produce v1 format."""
    from dsm.core.storage import _compute_canonical_entry_hash
    from dsm.core.models import Entry

    entry = Entry(
        id="test-id",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        session_id="s1",
        source="test",
        content="hello",
        shard="default",
        hash="",
        prev_hash=None,
        metadata={},
        version="1.0",
    )
    h = _compute_canonical_entry_hash(entry, None)
    assert h.startswith("v1:"), f"wrapper must produce v1, got: {h}"
