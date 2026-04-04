"""
Tests for block_layer/manager.py — targeting uncovered lines.

Covers:
  - BlockManager init, append, flush, read
  - Block serialization / deserialization
  - Auto-flush on reaching block_size
  - Multi-shard buffering
  - Reading expanded blocks
  - iter_entries
"""

import json
from datetime import datetime, timezone

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.block_layer.manager import BlockManager, _entry_to_dict, _dict_to_entry


def _make_entry(shard="test_shard", content="hello", idx=0):
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


@pytest.fixture
def manager(storage):
    return BlockManager(storage=storage, block_size=3)


class TestBlockManagerInit:
    def test_init_defaults(self, storage):
        mgr = BlockManager(storage=storage)
        assert mgr.block_size == 32

    def test_init_custom_block_size(self, storage):
        mgr = BlockManager(storage=storage, block_size=10)
        assert mgr.block_size == 10

    def test_init_creates_storage_if_none(self, tmp_path):
        mgr = BlockManager(data_dir=str(tmp_path / "auto"))
        assert mgr.storage is not None


class TestBlockManagerAppend:
    def test_append_single_entry(self, manager):
        e = _make_entry()
        result = manager.append(e)
        assert result is e
        assert len(manager._buffers.get("test_shard", [])) == 1

    def test_append_auto_generates_hash(self, manager):
        e = _make_entry()
        assert e.hash == ""
        manager.append(e)
        assert e.hash != ""

    def test_append_triggers_flush_at_block_size(self, manager):
        for i in range(3):
            manager.append(_make_entry(idx=i))
        # After reaching block_size=3, buffer should be flushed (empty)
        assert len(manager._buffers.get("test_shard", [])) == 0

    def test_append_multiple_shards(self, manager):
        manager.append(_make_entry(shard="shard_a"))
        manager.append(_make_entry(shard="shard_b"))
        assert "shard_a" in manager._buffers
        assert "shard_b" in manager._buffers


class TestBlockManagerFlush:
    def test_flush_writes_to_storage(self, manager, storage):
        manager.append(_make_entry(idx=0))
        manager.append(_make_entry(idx=1))
        manager.flush()
        entries = storage.read(manager._block_shard_id("test_shard"))
        assert len(entries) >= 1

    def test_flush_clears_buffer(self, manager):
        manager.append(_make_entry())
        manager.flush()
        assert len(manager._buffers.get("test_shard", [])) == 0

    def test_flush_empty_buffers_noop(self, manager):
        manager.flush()  # Should not raise


class TestBlockManagerRead:
    def test_read_after_auto_flush(self, manager):
        for i in range(3):
            manager.append(_make_entry(content=f"item-{i}", idx=i))
        entries = manager.read("test_shard")
        assert isinstance(entries, list)
        assert len(entries) == 3

    def test_read_empty_shard(self, manager):
        entries = manager.read("nonexistent")
        assert entries == []

    def test_read_after_manual_flush(self, manager):
        manager.append(_make_entry(content="buffered", idx=0))
        manager.flush()
        entries = manager.read("test_shard")
        assert len(entries) >= 1


class TestBlockManagerIterEntries:
    def test_iter_entries(self, manager):
        for i in range(3):
            manager.append(_make_entry(content=f"iter-{i}", idx=i))
        entries = list(manager.iter_entries("test_shard"))
        assert len(entries) == 3


class TestSerializationHelpers:
    def test_entry_to_dict_roundtrip(self):
        e = _make_entry()
        d = _entry_to_dict(e)
        assert isinstance(d, dict)
        assert d["id"] == e.id
        e2 = _dict_to_entry(d)
        assert e2.id == e.id
        assert e2.source == e.source

    def test_dict_to_entry_defaults(self):
        e = _dict_to_entry({"timestamp": "2026-01-01T00:00:00+00:00"})
        assert e.id == ""
        assert e.shard == "default"


class TestBlockShardId:
    def test_block_shard_id(self, manager):
        assert manager._block_shard_id("sessions") == "sessions_block"

    def test_block_shard_id_strips_prefix(self, manager):
        assert manager._block_shard_id("shard_sessions") == "sessions_block"
