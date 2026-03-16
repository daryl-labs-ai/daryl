"""
Tests for S-5 fix: automatic integrity verification at startup.
Tests Storage.startup_check() and reconcile vs full verify.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage, _compute_canonical_entry_hash
from dsm import verify


def _make_entry(content: str, shard: str = "startup_test") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="startup_test",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={},
        version="v2.0",
    )


def _write_orphan_entry(storage, shard, content="orphan"):
    """Write entry to segment without updating metadata (simulate K-2 crash)."""
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


class TestStartupCheck:
    def test_startup_check_clean_storage(self, tmp_path):
        """On clean storage, startup_check returns OK."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(5):
            storage.append(_make_entry(f"clean_{i}"))

        result = storage.startup_check()
        assert result["status"] == "OK"
        assert result["shards_reconciled"] == 0

    def test_startup_check_detects_and_reconciles(self, tmp_path):
        """startup_check reconciles orphan entries (K-2 scenario)."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(3):
            storage.append(_make_entry(f"pre_{i}"))

        _write_orphan_entry(storage, "startup_test")

        result = storage.startup_check()
        assert result["status"] == "RECONCILED"
        assert result["shards_reconciled"] >= 1

        v = verify.verify_shard(storage, "startup_test")
        assert v["status"] == "OK"

    def test_startup_check_full_verify_clean(self, tmp_path):
        """Full verify on clean storage returns OK with verify results."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(5):
            storage.append(_make_entry(f"full_{i}"))

        result = storage.startup_check(full_verify=True)
        assert result["status"] == "OK"
        assert result["shards_with_errors"] == 0
        assert len(result["verified"]) >= 1

    def test_startup_check_full_verify_detects_tampering(self, tmp_path):
        """Full verify detects tampered entry on disk."""
        storage = Storage(data_dir=str(tmp_path))
        for i in range(5):
            storage.append(_make_entry(f"tamper_{i}", shard="tamper_shard"))

        seg_dir = tmp_path / "shards" / "tamper_shard"
        seg_files = list(seg_dir.glob("*.jsonl"))
        assert len(seg_files) >= 1
        with open(seg_files[0], "r", encoding="utf-8") as f:
            lines = f.readlines()
        modified = []
        for i, line in enumerate(lines):
            if not line.strip():
                modified.append(line)
                continue
            data = json.loads(line.strip())
            if i == 2:
                data["content"] = "TAMPERED"
            modified.append(
                json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
            )
        with open(seg_files[0], "w", encoding="utf-8") as f:
            f.writelines(modified)

        result = storage.startup_check(full_verify=True)
        assert result["status"] == "INTEGRITY_ERROR"
        assert result["shards_with_errors"] >= 1

    def test_startup_check_empty_storage(self, tmp_path):
        """startup_check on empty storage is safe."""
        storage = Storage(data_dir=str(tmp_path))
        result = storage.startup_check()
        assert result["status"] == "OK"
        assert result["shards_reconciled"] == 0

    def test_startup_check_multiple_shards(self, tmp_path):
        """startup_check handles multiple shards, reconciles only divergent ones."""
        storage = Storage(data_dir=str(tmp_path))

        for i in range(3):
            storage.append(_make_entry(f"a_{i}", shard="shard_a"))
        for i in range(3):
            storage.append(_make_entry(f"b_{i}", shard="shard_b"))

        _write_orphan_entry(storage, "shard_b", "orphan_b")

        result = storage.startup_check()
        assert result["shards_reconciled"] >= 1
        reconciled_ids = [r["shard_id"] for r in result["reconciled"] if r.get("reconciled")]
        assert "shard_b" in reconciled_ids
