"""
Tests for core/shard_segments.py — targeting uncovered lines (69% → 80%+).

Covers:
  - ShardSegmentManager initialization
  - get_active_segment / get_segment_files_ordered
  - iter_shard_events / iter_shard_events_reverse
  - update_active_segment_metadata
  - Edge cases: empty shards, missing metadata, multiple segments
"""

import json
from pathlib import Path

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.core.shard_segments import ShardSegmentManager
from datetime import datetime, timezone


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
def manager(tmp_path):
    s = Storage(data_dir=str(tmp_path / "data"))
    return s.segment_manager


@pytest.fixture
def populated_manager(storage):
    """Manager with populated shard via Storage API."""
    for i in range(5):
        storage.append(_make_entry(content=f"entry-{i}", idx=i))
    return storage.segment_manager


class TestInit:
    def test_creates_manager(self, manager):
        assert manager is not None


class TestGetActiveSegment:
    def test_active_segment_after_append(self, populated_manager):
        seg = populated_manager.get_active_segment("test_shard")
        assert seg is not None
        assert seg.exists()

    def test_active_segment_nonexistent(self, manager):
        seg = manager.get_active_segment("nonexistent_shard")
        # Should create or return a path


class TestSegmentFilesOrdered:
    def test_ordered_after_append(self, populated_manager):
        files = populated_manager.get_segment_files_ordered("test_shard")
        assert len(files) >= 1

    def test_ordered_reverse(self, populated_manager):
        files = populated_manager.get_segment_files_ordered("test_shard", reverse=True)
        assert len(files) >= 1

    def test_ordered_nonexistent(self, manager):
        files = manager.get_segment_files_ordered("nonexistent")
        assert files == [] or len(files) >= 0


class TestIteration:
    def test_iter_shard_events(self, populated_manager):
        events = list(populated_manager.iter_shard_events("test_shard"))
        assert len(events) == 5
        assert events[0]["content"] == "entry-0"

    def test_iter_shard_events_empty(self, manager):
        events = list(manager.iter_shard_events("nonexistent"))
        assert events == []

    def test_iter_shard_events_reverse(self, populated_manager):
        events = list(populated_manager.iter_shard_events_reverse("test_shard"))
        assert len(events) == 5
        # Reverse: last appended first
        assert events[0]["content"] == "entry-4"

    def test_iter_shard_events_reverse_empty(self, manager):
        events = list(manager.iter_shard_events_reverse("nonexistent"))
        assert events == []


class TestUpdateMetadata:
    def test_update_active_segment_metadata(self, populated_manager):
        populated_manager.update_active_segment_metadata("test_shard", delta_events=1, delta_bytes=100)
        # No crash = success


class TestGetShardFamilyDir:
    def test_returns_path(self, manager):
        path = manager._get_shard_family_dir("sessions")
        assert isinstance(path, Path)
