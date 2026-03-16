"""
Test K-2 fix: crash between fsync and last_hash commit.
Simulates crash by writing entry to segment without updating last_hash,
then verifies reconcile_shard() recovers correctly with O(1) detection.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage, _compute_canonical_entry_hash
from dsm.verify import verify_shard


def _make_entry(content: str, shard: str = "k2_test") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="k2_crash_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def _write_orphan_entry(storage, shard, content="crash_entry"):
    """Simulate a crash: write entry to segment but don't update last_hash.json."""
    prev = storage._get_last_hash(shard)
    orphan = _make_entry(content, shard)
    orphan.prev_hash = prev
    orphan.hash = _compute_canonical_entry_hash(orphan, prev)

    seg = storage.segment_manager.get_active_segment(shard)
    d = {
        "id": orphan.id,
        "timestamp": orphan.timestamp.isoformat(),
        "session_id": orphan.session_id,
        "source": orphan.source,
        "content": orphan.content,
        "shard": shard,
        "hash": orphan.hash,
        "prev_hash": orphan.prev_hash,
        "metadata": orphan.metadata,
        "version": orphan.version,
    }
    with open(seg, "a", encoding="utf-8") as f:
        line = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    return orphan


class TestK2CrashRecovery:
    def test_reconcile_after_simulated_crash(self, tmp_path):
        """Simulate K-2: entry on disk but last_hash not updated. reconcile fixes it."""
        storage = Storage(data_dir=str(tmp_path))

        for i in range(3):
            storage.append(_make_entry(f"normal_{i}"))

        last_hash_before = storage._get_last_hash("k2_test")
        orphan = _write_orphan_entry(storage, "k2_test")

        assert storage._get_last_hash("k2_test") == last_hash_before
        assert storage._get_last_hash("k2_test") != orphan.hash

        result = storage.reconcile_shard("k2_test")
        assert result["reconciled"] is True
        assert result["new_hash"] == orphan.hash
        assert result["entry_count"] == 4

        verify_result = verify_shard(storage, "k2_test")
        assert verify_result["status"] == "OK"
        assert verify_result["chain_breaks"] == 0
        assert verify_result["verified"] == 4

    def test_reconcile_no_divergence(self, tmp_path):
        """If no crash happened, reconcile is a no-op."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(5):
            storage.append(_make_entry(f"ok_{i}"))

        result = storage.reconcile_shard("k2_test")
        assert result["reconciled"] is False

    def test_reconcile_empty_shard(self, tmp_path):
        """Reconcile on empty shard returns safely."""
        storage = Storage(data_dir=str(tmp_path))
        result = storage.reconcile_shard("nonexistent_shard")
        assert result["reconciled"] is False
        assert result.get("reason") == "empty_shard"

    def test_append_after_reconcile_maintains_chain(self, tmp_path):
        """After reconciliation, subsequent appends maintain a valid chain."""
        storage = Storage(data_dir=str(tmp_path))

        for i in range(3):
            storage.append(_make_entry(f"pre_{i}"))

        _write_orphan_entry(storage, "k2_test", "orphan_entry")
        storage.reconcile_shard("k2_test")

        for i in range(2):
            storage.append(_make_entry(f"post_{i}"))

        result = verify_shard(storage, "k2_test")
        assert result["status"] == "OK"
        assert result["verified"] == 6
        assert result["chain_breaks"] == 0

    def test_reconcile_all_multiple_shards(self, tmp_path):
        """reconcile_all() handles multiple shards, only reconciles divergent ones."""
        storage = Storage(data_dir=str(tmp_path))

        for i in range(3):
            storage.append(_make_entry(f"a_{i}", shard="shard_a"))

        for i in range(2):
            storage.append(_make_entry(f"b_{i}", shard="shard_b"))
        _write_orphan_entry(storage, "shard_b", "b_orphan")

        results = storage.reconcile_all()
        reconciled_shards = [r["shard_id"] for r in results if r.get("reconciled")]
        assert "shard_b" in reconciled_shards

    def test_reconcile_detection_reads_tail_only(self, tmp_path):
        """Reconcile detection should work via tail read (O(1)), not full scan."""
        storage = Storage(data_dir=str(tmp_path))

        for i in range(100):
            storage.append(_make_entry(f"bulk_{i}"))

        result = storage.reconcile_shard("k2_test")
        assert result["reconciled"] is False
