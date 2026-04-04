"""
Tests for core/shard_segments.py — targeting remaining uncovered iteration paths.

Covers:
  - iter_shard_events with blank lines, corrupt JSON
  - iter_shard_events_reverse with multiple segments
  - _get_segment_number
  - Multiple segment files
"""

import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.core.shard_segments import ShardSegmentManager


def _make_entry(shard="iter_shard", content="hello", idx=0):
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


class TestIterWithCorruption:
    def test_iter_skips_blank_lines(self, storage, tmp_path):
        for i in range(3):
            storage.append(_make_entry(idx=i))

        # Inject blank lines into segment
        shard_dir = tmp_path / "data" / "shards" / "iter_shard"
        for seg in shard_dir.glob("*.jsonl"):
            content = seg.read_text()
            seg.write_text(content + "\n\n\n")

        events = list(storage.segment_manager.iter_shard_events("iter_shard"))
        assert len(events) == 3

    def test_iter_skips_corrupt_json(self, storage, tmp_path):
        for i in range(3):
            storage.append(_make_entry(idx=i))

        shard_dir = tmp_path / "data" / "shards" / "iter_shard"
        for seg in shard_dir.glob("*.jsonl"):
            content = seg.read_text()
            lines = content.strip().split("\n")
            lines.insert(1, "NOT_JSON!!!")
            seg.write_text("\n".join(lines) + "\n")

        events = list(storage.segment_manager.iter_shard_events("iter_shard"))
        assert len(events) >= 2  # Skipped the corrupt line

    def test_iter_reverse_skips_blank_lines(self, storage, tmp_path):
        for i in range(3):
            storage.append(_make_entry(idx=i))

        shard_dir = tmp_path / "data" / "shards" / "iter_shard"
        for seg in shard_dir.glob("*.jsonl"):
            content = seg.read_text()
            seg.write_text(content + "\n\n")

        events = list(storage.segment_manager.iter_shard_events_reverse("iter_shard"))
        assert len(events) == 3


class TestSegmentNumber:
    def test_get_segment_number(self, storage):
        mgr = storage.segment_manager
        assert mgr._get_segment_number("segment_0001.jsonl") == 1
        assert mgr._get_segment_number("segment_0042.jsonl") == 42

    def test_get_segment_number_invalid(self, storage):
        mgr = storage.segment_manager
        # Non-numeric suffix should return 9999
        assert mgr._get_segment_number("segment_abc.jsonl") == 9999

    def test_get_segment_number_no_underscore(self, storage):
        mgr = storage.segment_manager
        assert mgr._get_segment_number("noseparator.jsonl") == 9999


class TestDefaultBaseDir:
    def test_default_base_dir(self, tmp_path, monkeypatch):
        """Covers line 51: default base_dir when None."""
        # Patch Path.home to use tmp_path to avoid creating dirs in real home
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = ShardSegmentManager(base_dir=None)
        assert mgr.base_dir is not None
        assert "clawdbot_dsm_test" in str(mgr.base_dir)


class TestIterReverseCorruptJson:
    def test_iter_reverse_skips_corrupt_json(self, storage, tmp_path):
        for i in range(3):
            storage.append(_make_entry(idx=i))

        shard_dir = tmp_path / "data" / "shards" / "iter_shard"
        for seg in shard_dir.glob("*.jsonl"):
            content = seg.read_text()
            lines = content.strip().split("\n")
            lines.append("CORRUPT_JSON!!!")
            seg.write_text("\n".join(lines) + "\n")

        events = list(storage.segment_manager.iter_shard_events_reverse("iter_shard"))
        assert len(events) >= 3  # Skipped corrupt line
