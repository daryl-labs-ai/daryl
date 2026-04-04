"""
Tests for verify.py — targeting remaining uncovered lines (79% → 90%+).

Covers:
  - verify_shard with tampered hash, chain break, empty hash
  - verify_shard with corrupt event data (KeyError/TypeError)
  - verify_all with multiple shards including failures
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.verify import verify_shard, verify_all
from dsm.status import VerifyStatus


def _make_entry(shard="v_shard", content="hello", idx=0):
    return Entry(
        id=f"e-{idx}",
        timestamp=datetime.now(timezone.utc),
        session_id="sess-1",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


@pytest.fixture
def storage(tmp_path):
    return Storage(data_dir=str(tmp_path / "data"))


class TestVerifyShardDetailed:
    def test_valid_chain(self, storage):
        for i in range(5):
            storage.append(_make_entry(idx=i))
        result = verify_shard(storage, "v_shard")
        assert result["status"] == VerifyStatus.OK
        assert result["verified"] == 5
        assert result["tampered"] == 0
        assert result["chain_breaks"] == 0

    def test_empty_shard(self, storage):
        result = verify_shard(storage, "nonexistent")
        assert result["total_entries"] == 0
        assert result["status"] == VerifyStatus.OK

    def test_tampered_hash(self, storage, tmp_path):
        for i in range(3):
            storage.append(_make_entry(idx=i))

        # Tamper with a hash in the segment file
        shard_dir = tmp_path / "data" / "shards" / "v_shard"
        for seg in shard_dir.glob("*.jsonl"):
            lines = seg.read_text().strip().split("\n")
            if len(lines) >= 2:
                data = json.loads(lines[1])
                data["hash"] = "TAMPERED_HASH"
                lines[1] = json.dumps(data)
                seg.write_text("\n".join(lines) + "\n")

        result = verify_shard(storage, "v_shard")
        assert result["tampered"] >= 1
        assert result["status"] == VerifyStatus.TAMPERED

    def test_chain_break(self, storage, tmp_path):
        for i in range(3):
            storage.append(_make_entry(idx=i))

        # Break the chain by modifying prev_hash
        shard_dir = tmp_path / "data" / "shards" / "v_shard"
        for seg in shard_dir.glob("*.jsonl"):
            lines = seg.read_text().strip().split("\n")
            if len(lines) >= 3:
                data = json.loads(lines[2])
                data["prev_hash"] = "WRONG_PREV_HASH"
                lines[2] = json.dumps(data)
                seg.write_text("\n".join(lines) + "\n")

        result = verify_shard(storage, "v_shard")
        assert result["chain_breaks"] >= 1

    def test_empty_hash_entry(self, storage, tmp_path):
        for i in range(2):
            storage.append(_make_entry(idx=i))

        # Clear a hash
        shard_dir = tmp_path / "data" / "shards" / "v_shard"
        for seg in shard_dir.glob("*.jsonl"):
            lines = seg.read_text().strip().split("\n")
            if lines:
                data = json.loads(lines[0])
                data["hash"] = ""
                lines[0] = json.dumps(data)
                seg.write_text("\n".join(lines) + "\n")

        result = verify_shard(storage, "v_shard")
        assert result["tampered"] >= 1

    def test_corrupt_event_data(self, storage, tmp_path):
        storage.append(_make_entry(idx=0))

        # Inject corrupt event data
        shard_dir = tmp_path / "data" / "shards" / "v_shard"
        for seg in shard_dir.glob("*.jsonl"):
            content = seg.read_text()
            seg.write_text(content + '{"bad": "missing_required_fields"}\n')

        result = verify_shard(storage, "v_shard")
        # Should handle gracefully (skip corrupt entry)
        assert result["total_entries"] >= 1


class TestVerifyAllDetailed:
    def test_multiple_shards(self, storage):
        storage.append(_make_entry(shard="s1", idx=0))
        storage.append(_make_entry(shard="s1", idx=1))
        storage.append(_make_entry(shard="s2", idx=2))
        results = verify_all(storage)
        assert len(results) >= 2
        shard_ids = [r["shard_id"] for r in results]
        assert "s1" in shard_ids
        assert "s2" in shard_ids

    def test_all_ok(self, storage):
        for i in range(3):
            storage.append(_make_entry(shard="ok_shard", idx=i))
        results = verify_all(storage)
        assert all(r["status"] == VerifyStatus.OK for r in results)
