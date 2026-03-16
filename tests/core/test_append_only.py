#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test append-only storage with segmented shard format.

Uses only the public Storage API. Verifies that entries are appended
in order and read back correctly from shards/<shard_id>/*.jsonl segments.
"""

import uuid
from datetime import datetime, timezone

from dsm.core.storage import Storage
from dsm.core.models import Entry


def _make_entry(content: str, shard: str = "test") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def test_append_only(tmp_path):
    """
    Append entries to segmented shard "test", read back, verify order and content.
    Verifies that at least one segment file exists under shards/test/.
    """
    storage = Storage(data_dir=str(tmp_path))

    # Append 3 entries
    for content in ("first", "second", "third"):
        entry = _make_entry(content)
        storage.append(entry)

    # Read back (Storage returns newest first)
    entries = storage.read("test", limit=10)
    assert len(entries) == 3

    # Chronological order = reverse of read order
    chronological = list(reversed(entries))
    assert chronological[0].content == "first"
    assert chronological[1].content == "second"
    assert chronological[2].content == "third"

    # At least one segment file exists under shards/test/
    segment_dir = tmp_path / "shards" / "test"
    assert segment_dir.is_dir()
    segment_files = list(segment_dir.glob("*.jsonl"))
    assert len(segment_files) >= 1

    # Append 2 more entries
    for content in ("fourth", "fifth"):
        entry = _make_entry(content)
        storage.append(entry)

    # Final read: 5 entries, order and content intact
    entries = storage.read("test", limit=10)
    assert len(entries) == 5

    chronological = list(reversed(entries))
    assert chronological[0].content == "first"
    assert chronological[1].content == "second"
    assert chronological[2].content == "third"
    assert chronological[3].content == "fourth"
    assert chronological[4].content == "fifth"
