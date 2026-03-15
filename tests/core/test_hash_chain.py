"""
Tests for DSM hash-chain verification (verify_shard).

Uses only public Storage API and dsm.verify; does not modify core.
"""

import json
import uuid
from datetime import datetime

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm import verify


def _make_entry(content: str, shard: str) -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        session_id="test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def test_hash_chain_valid(tmp_path):
    """Append 10 entries, verify chain is valid."""
    storage = Storage(data_dir=str(tmp_path))
    for i in range(10):
        entry = _make_entry(f"content_{i}", shard="test")
        storage.append(entry)

    result = verify.verify_shard(storage, "test")
    assert result["status"] == "OK"
    assert result["verified"] == 10
    assert result["tampered"] == 0
    assert result["chain_breaks"] == 0
    assert result["total_entries"] == 10


def test_hash_chain_detects_tampering(tmp_path):
    """Append 5 entries, corrupt one line on disk, verify detects tampering."""
    storage = Storage(data_dir=str(tmp_path))
    for i in range(5):
        entry = _make_entry(f"content_{i}", shard="tamper_test")
        storage.append(entry)

    segment_dir = tmp_path / "shards" / "tamper_test"
    assert segment_dir.is_dir()
    segment_files = list(segment_dir.glob("*.jsonl"))
    assert len(segment_files) >= 1
    segment_path = segment_files[0]

    with open(segment_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Corrupt one line: change content of the second entry (index 1)
    modified = []
    for i, line in enumerate(lines):
        if not line.strip():
            modified.append(line)
            continue
        try:
            data = json.loads(line.strip())
            if i == 1:
                data["content"] = "tampered_content"
            modified.append(json.dumps(data, ensure_ascii=False) + "\n")
        except (json.JSONDecodeError, KeyError):
            modified.append(line)

    with open(segment_path, "w", encoding="utf-8") as f:
        f.writelines(modified)

    result = verify.verify_shard(storage, "tamper_test")
    assert result["status"] != "OK"
    assert result["tampered"] > 0 or result["chain_breaks"] > 0
