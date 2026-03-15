"""Tests for dsm.coverage — Memory Coverage Check (P2b)."""

import uuid
from datetime import datetime

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.coverage import check_coverage, check_all, CoverageGap


def _make_entry(storage, shard_id, content="test", event_type="action"):
    """Helper: append an entry and return it."""
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        session_id="sess-1",
        source="test",
        content=content,
        shard=shard_id,
        hash="",
        prev_hash=None,
        metadata={"event_type": event_type},
        version="v2.0",
    )
    return storage.append(entry)


# --- Core coverage tests ---


def test_full_coverage(tmp_path):
    """All entries indexed by ID => FULLY_COVERED."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e1 = _make_entry(storage, "shard-a", "action 1")
    e2 = _make_entry(storage, "shard-a", "action 2")
    e3 = _make_entry(storage, "shard-a", "action 3")

    result = check_coverage(storage, indexed_ids={e1.id, e2.id, e3.id})
    assert result["status"] == "FULLY_COVERED"
    assert result["coverage_percent"] == 100.0
    assert result["missing_entries"] == 0
    assert result["gaps"] == []


def test_partial_coverage(tmp_path):
    """96% coverage => PARTIAL_COVERAGE."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    entries = [_make_entry(storage, "shard-a", f"item {i}") for i in range(25)]

    # Index 24 out of 25 = 96%
    indexed = {e.id for e in entries[:24]}
    result = check_coverage(storage, indexed_ids=indexed)
    assert result["status"] == "PARTIAL_COVERAGE"
    assert result["coverage_percent"] == 96.0
    assert result["missing_entries"] == 1
    assert len(result["gaps"]) == 1


def test_critical_gaps(tmp_path):
    """< 95% coverage => CRITICAL_GAPS."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    entries = [_make_entry(storage, "shard-a", f"item {i}") for i in range(10)]

    # Index only 5 out of 10 = 50%
    indexed = {e.id for e in entries[:5]}
    result = check_coverage(storage, indexed_ids=indexed)
    assert result["status"] == "CRITICAL_GAPS"
    assert result["coverage_percent"] == 50.0
    assert result["missing_entries"] == 5


def test_no_index_provided(tmp_path):
    """No index provided at all => NO_INDEX."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    _make_entry(storage, "shard-a")

    result = check_coverage(storage)
    assert result["status"] == "NO_INDEX"
    assert result["total_entries"] == 0


def test_empty_storage(tmp_path):
    """Empty storage with index => FULLY_COVERED (nothing to miss)."""
    storage = Storage(data_dir=str(tmp_path / "data"))

    result = check_coverage(storage, indexed_ids={"some-id"})
    assert result["status"] == "FULLY_COVERED"
    assert result["total_entries"] == 0


def test_coverage_by_hash(tmp_path):
    """Coverage check using entry hashes instead of IDs."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e1 = _make_entry(storage, "shard-a", "hash-check-1")
    e2 = _make_entry(storage, "shard-a", "hash-check-2")

    result = check_coverage(storage, indexed_hashes={e1.hash, e2.hash})
    assert result["status"] == "FULLY_COVERED"
    assert result["indexed_entries"] == 2


def test_mixed_id_and_hash(tmp_path):
    """Coverage check using a mix of IDs and hashes."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e1 = _make_entry(storage, "shard-a", "mixed-1")
    e2 = _make_entry(storage, "shard-a", "mixed-2")

    # e1 found by ID, e2 found by hash
    result = check_coverage(storage, indexed_ids={e1.id}, indexed_hashes={e2.hash})
    assert result["status"] == "FULLY_COVERED"
    assert result["indexed_entries"] == 2
    assert result["missing_entries"] == 0


def test_multi_shard_coverage(tmp_path):
    """Coverage spans multiple shards, per_shard breakdown is correct."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    a1 = _make_entry(storage, "shard-a", "a-1")
    a2 = _make_entry(storage, "shard-a", "a-2")
    b1 = _make_entry(storage, "shard-b", "b-1")

    # Index all of shard-a, miss shard-b
    result = check_coverage(storage, indexed_ids={a1.id, a2.id})
    assert result["total_entries"] == 3
    assert result["missing_entries"] == 1
    assert result["per_shard"]["shard-a"]["missing"] == 0
    assert result["per_shard"]["shard-b"]["missing"] == 1


def test_specific_shard_filter(tmp_path):
    """When shard_ids is specified, only those shards are checked."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    a1 = _make_entry(storage, "shard-a", "a-only")
    _make_entry(storage, "shard-b", "b-ignored")

    result = check_coverage(
        storage, indexed_ids={a1.id}, shard_ids=["shard-a"]
    )
    assert result["shards_checked"] == 1
    assert result["total_entries"] == 1
    assert result["status"] == "FULLY_COVERED"


def test_gap_details(tmp_path):
    """Gaps contain entry_id, shard_id, content_preview, event_type."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    _make_entry(storage, "shard-a", "missing action", event_type="action_intent")

    result = check_coverage(storage, indexed_ids=set())
    assert len(result["gaps"]) == 1
    gap = result["gaps"][0]
    assert gap["shard_id"] == "shard-a"
    assert "missing action" in gap["content_preview"]
    assert gap["event_type"] == "action_intent"
    assert gap["entry_id"]  # non-empty


def test_max_gaps_truncation(tmp_path):
    """When more gaps than max_gaps, gaps_truncated is True."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    for i in range(10):
        _make_entry(storage, "shard-a", f"entry-{i}")

    result = check_coverage(storage, indexed_ids=set(), max_gaps=3)
    assert result["missing_entries"] == 10
    assert len(result["gaps"]) == 3
    assert result["gaps_truncated"] is True


def test_check_all_convenience(tmp_path):
    """check_all() works as convenience wrapper."""
    storage = Storage(data_dir=str(tmp_path / "data"))
    e1 = _make_entry(storage, "shard-a", "all-1")
    e2 = _make_entry(storage, "shard-b", "all-2")

    result = check_all(storage, indexed_ids={e1.id, e2.id})
    assert result["status"] == "FULLY_COVERED"
    assert result["shards_checked"] == 2


def test_coverage_gap_to_dict():
    """CoverageGap.to_dict() returns proper dictionary."""
    gap = CoverageGap(
        entry_id="abc-123",
        shard_id="shard-x",
        timestamp="2026-03-15T00:00:00",
        content_preview="preview text",
        entry_hash="deadbeef",
        event_type="action_intent",
        session_id="sess-1",
    )
    d = gap.to_dict()
    assert d["entry_id"] == "abc-123"
    assert d["shard_id"] == "shard-x"
    assert d["entry_hash"] == "deadbeef"
    assert d["event_type"] == "action_intent"
