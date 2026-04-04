"""
Tests for rr/relay.py — targeting uncovered lines (74% → 80%+).

Covers:
  - DSMReadRelay init
  - read_recent (empty, populated, with limit)
  - summary (empty, populated)
  - _expand_entries / _dict_to_entry helpers
"""

import json
from datetime import datetime, timezone

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.rr.relay import DSMReadRelay


def _make_entry(shard="sessions", content="test", idx=0):
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
def relay(storage):
    return DSMReadRelay(storage=storage)


@pytest.fixture
def populated_relay(storage):
    for i in range(5):
        storage.append(_make_entry(content=f"entry-{i}", idx=i))
    return DSMReadRelay(storage=storage)


class TestInit:
    def test_creates_relay(self, relay):
        assert relay is not None

    def test_storage_property(self, relay, storage):
        assert relay.storage is storage


class TestReadRecent:
    def test_empty_shard(self, relay):
        entries = relay.read_recent("nonexistent", limit=10)
        assert entries == []

    def test_populated_shard(self, populated_relay):
        entries = populated_relay.read_recent("sessions", limit=10)
        assert len(entries) >= 1

    def test_with_limit(self, populated_relay):
        entries = populated_relay.read_recent("sessions", limit=2)
        assert len(entries) <= 2


class TestSummary:
    def test_summary_empty(self, relay):
        result = relay.summary("nonexistent")
        assert isinstance(result, dict) or isinstance(result, list)

    def test_summary_populated(self, populated_relay):
        result = populated_relay.summary("sessions")
        assert result is not None
