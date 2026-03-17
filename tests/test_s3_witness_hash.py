"""
Tests for S-3 fix: witness hash canonical JSON serialization.
"""

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.witness import ShardWitness


@pytest.fixture
def witness_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def storage_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _make_entry(shard, content="test"):
    return Entry(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="s3_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


class TestCanonicalHash:
    def test_hash_uses_json_canonical(self, witness_dir):
        """Witness hash must use JSON canonical serialization, not f-string."""
        w = ShardWitness(witness_dir, witness_key="secret")
        result = w._compute_witness_hash(
            "shard_a", "2026-03-17T00:00:00+00:00", 42, "abc123"
        )

        expected_payload = json.dumps(
            {
                "shard_id": "shard_a",
                "timestamp": "2026-03-17T00:00:00+00:00",
                "entry_count": 42,
                "tip_hash": "abc123",
                "witness_key": "secret",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        expected_hash = hashlib.sha256(
            expected_payload.encode("utf-8")
        ).hexdigest()
        assert result == expected_hash

    def test_hash_not_vulnerable_to_colon_collision(self, witness_dir):
        """Shard IDs containing ':' must not collide with other field combinations."""
        w = ShardWitness(witness_dir)

        hash1 = w._compute_witness_hash("a:b", "ts", 1, "h")
        hash2 = w._compute_witness_hash("a", "b:ts", 1, "h")
        assert hash1 != hash2, "Colon in shard_id caused hash collision"

    def test_hash_deterministic(self, witness_dir):
        """Same inputs always produce the same hash."""
        w = ShardWitness(witness_dir, witness_key="k")
        h1 = w._compute_witness_hash("s", "t", 10, "h")
        h2 = w._compute_witness_hash("s", "t", 10, "h")
        assert h1 == h2

    def test_hash_changes_with_any_field(self, witness_dir):
        """Changing any single field changes the hash."""
        w = ShardWitness(witness_dir, witness_key="k")
        base = w._compute_witness_hash("s", "t", 10, "h")

        assert w._compute_witness_hash("x", "t", 10, "h") != base
        assert w._compute_witness_hash("s", "x", 10, "h") != base
        assert w._compute_witness_hash("s", "t", 11, "h") != base
        assert w._compute_witness_hash("s", "t", 10, "x") != base

    def test_hash_changes_with_witness_key(self, witness_dir):
        """Different witness keys produce different hashes."""
        w1 = ShardWitness(witness_dir, witness_key="key1")
        w2 = ShardWitness(witness_dir, witness_key="key2")
        h1 = w1._compute_witness_hash("s", "t", 10, "h")
        h2 = w2._compute_witness_hash("s", "t", 10, "h")
        assert h1 != h2


class TestTimestamp:
    def test_timestamp_is_valid_iso8601(self, witness_dir, storage_dir):
        """Captured timestamp must be valid ISO 8601 (no trailing Z after +00:00)."""
        storage = Storage(data_dir=storage_dir)
        storage.append(_make_entry("ts_test"))

        w = ShardWitness(witness_dir)
        record = w.capture(storage, "ts_test")
        ts = record["timestamp"]

        assert not ts.endswith("+00:00Z"), f"Invalid timestamp: {ts}"

        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None


class TestFsync:
    def test_witness_log_persisted_with_fsync(self, witness_dir, storage_dir):
        """Witness log file should exist and contain valid JSON after capture."""
        storage = Storage(data_dir=storage_dir)
        storage.append(_make_entry("fsync_test"))

        w = ShardWitness(witness_dir)
        w.capture(storage, "fsync_test")

        log_path = Path(witness_dir) / "witness_log.jsonl"
        assert log_path.exists()

        content = log_path.read_text()
        lines = [line for line in content.strip().split("\n") if line.strip()]
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["shard_id"] == "fsync_test"


class TestBackwardCompatibility:
    def test_existing_records_still_verify(self, witness_dir, storage_dir):
        """Records captured with new hash method verify correctly."""
        storage = Storage(data_dir=storage_dir)
        for i in range(3):
            storage.append(_make_entry("compat_test", f"entry_{i}"))

        w = ShardWitness(witness_dir, witness_key="mykey")
        record = w.capture(storage, "compat_test")

        assert w.verify_record(record) is True

        tampered = dict(record)
        tampered["entry_count"] = 999
        assert w.verify_record(tampered) is False

    def test_verify_shard_ok_with_new_hash(self, witness_dir, storage_dir):
        """Full shard verification still works with the new hash format."""
        storage = Storage(data_dir=storage_dir)
        for i in range(5):
            storage.append(_make_entry("verify_new", f"e_{i}"))

        w = ShardWitness(witness_dir)
        w.capture(storage, "verify_new")

        result = w.verify_shard_against_witness(storage, "verify_new")
        status = getattr(result["status"], "value", result["status"])
        assert status == "OK"
        assert result["witness_valid"] is True
        assert result["current_count"] == 5
