"""
Tests for rr/relay.py — targeting remaining uncovered lines (75% → 85%+).

Covers:
  - _expand_entries with block format, non-block, empty content, corrupt JSON
  - _dict_to_entry with various timestamp formats
  - DSMReadRelay init from data_dir (no storage)
  - summary with actions, errors, sessions
"""

import json
from datetime import datetime, timezone

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.rr.relay import DSMReadRelay, _expand_entries, _dict_to_entry


def _make_entry(shard="sessions", content="test", idx=0, metadata=None):
    return Entry(
        id=f"e-{idx}",
        timestamp=datetime.now(timezone.utc),
        session_id=f"sess-{idx % 3}",
        source="test",
        content=content,
        shard=shard,
        hash="",
        prev_hash=None,
        metadata=metadata or {},
        version="v2.0",
    )


# ---------------------------------------------------------------------------
# _dict_to_entry
# ---------------------------------------------------------------------------

class TestDictToEntry:
    def test_valid_timestamp(self):
        e = _dict_to_entry({"id": "1", "timestamp": "2026-01-01T00:00:00+00:00"})
        assert e.id == "1"

    def test_invalid_timestamp(self):
        e = _dict_to_entry({"id": "2", "timestamp": "not-a-date"})
        assert e.id == "2"
        # Should fallback to now()

    def test_missing_timestamp(self):
        e = _dict_to_entry({"id": "3"})
        assert e.id == "3"

    def test_numeric_timestamp(self):
        e = _dict_to_entry({"id": "4", "timestamp": 12345})
        assert e.id == "4"


# ---------------------------------------------------------------------------
# _expand_entries
# ---------------------------------------------------------------------------

class TestExpandEntries:
    def test_non_block_passthrough(self):
        e = _make_entry(content='{"key": "value"}')
        result = _expand_entries([e])
        assert len(result) == 1

    def test_empty_content_passthrough(self):
        e = _make_entry(content="")
        result = _expand_entries([e])
        assert len(result) == 1

    def test_block_expansion(self):
        block_data = {
            "block": True,
            "entries": [
                {"id": "b1", "timestamp": "2026-01-01T00:00:00+00:00", "content": "a"},
                {"id": "b2", "timestamp": "2026-01-01T00:01:00+00:00", "content": "b"},
            ],
            "count": 2,
        }
        e = _make_entry(content=json.dumps(block_data))
        result = _expand_entries([e])
        assert len(result) == 2
        assert result[0].id == "b1"

    def test_corrupt_json(self):
        e = _make_entry(content="NOT_JSON{{{")
        result = _expand_entries([e])
        assert len(result) == 1  # Passthrough on error


# ---------------------------------------------------------------------------
# DSMReadRelay init
# ---------------------------------------------------------------------------

class TestRelayInit:
    def test_init_from_data_dir(self, tmp_path):
        relay = DSMReadRelay(data_dir=str(tmp_path / "data"))
        assert relay.storage is not None

    def test_init_from_storage(self, tmp_path):
        s = Storage(data_dir=str(tmp_path / "data"))
        relay = DSMReadRelay(storage=s)
        assert relay.storage is s


# ---------------------------------------------------------------------------
# summary with rich data
# ---------------------------------------------------------------------------

class TestSummaryRichData:
    def test_summary_with_actions_and_errors(self, tmp_path):
        s = Storage(data_dir=str(tmp_path / "data"))
        s.append(_make_entry(idx=0, metadata={"action_name": "search"}))
        s.append(_make_entry(idx=1, metadata={"action_name": "search"}))
        s.append(_make_entry(idx=2, metadata={"action_name": "reply", "error": "timeout"}))
        s.append(_make_entry(idx=3, metadata={"action_name": "reply"}))

        relay = DSMReadRelay(storage=s)
        result = relay.summary("sessions")
        assert result["entry_count"] == 4
        assert result["errors"] >= 1
        assert result["unique_sessions"] >= 1
        assert len(result["top_actions"]) >= 1

    def test_summary_empty_shard(self, tmp_path):
        s = Storage(data_dir=str(tmp_path / "data"))
        relay = DSMReadRelay(storage=s)
        result = relay.summary("nonexistent")
        assert result["entry_count"] == 0
        assert result["errors"] == 0
