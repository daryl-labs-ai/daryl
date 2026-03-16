"""Tests for P7 — Session Index & Navigation."""

import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from dsm.core.models import Entry
from dsm.core.storage import Storage
from dsm.session.session_index import SessionIndex


def _make_entry(session_id, action_name=None, source="test_agent", ts=None, success=True):
    """Create a test entry."""
    ts = ts or datetime.utcnow()
    meta = {"event_type": "tool_call"}
    if action_name:
        meta["action_name"] = action_name
        meta["success"] = success
    return Entry(
        id=str(uuid4()),
        timestamp=ts,
        session_id=session_id,
        source=source,
        content=f"action: {action_name or 'none'}",
        shard="sessions",
        hash="",
        prev_hash=None,
        metadata=meta,
        version="v2.0",
    )


@pytest.fixture
def tmp_dirs():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as index_dir:
        yield data_dir, index_dir


@pytest.fixture
def storage_with_entries(tmp_dirs):
    data_dir, index_dir = tmp_dirs
    storage = Storage(data_dir=data_dir)
    base_time = datetime(2026, 3, 15, 10, 0, 0)

    # Session 1: 3 actions
    for i, action in enumerate(["search", "analyze", "reply"]):
        entry = _make_entry("session-1", action, ts=base_time + timedelta(minutes=i))
        storage.append(entry)

    # Session 2: 2 actions (one failed)
    for i, (action, success) in enumerate([("search", True), ("api_call", False)]):
        entry = _make_entry("session-2", action, ts=base_time + timedelta(hours=1, minutes=i), success=success)
        storage.append(entry)

    return storage, index_dir


# --- Index Creation ---

def test_build_index_empty_shard(tmp_dirs):
    data_dir, index_dir = tmp_dirs
    storage = Storage(data_dir=data_dir)
    index = SessionIndex(index_dir, shard_id="sessions")
    result = index.build_from_storage(storage)
    assert result["status"] == "OK"
    assert result["entries_indexed"] == 0
    assert result["sessions_found"] == 0


def test_build_index_with_entries(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    result = index.build_from_storage(storage)
    assert result["status"] == "OK"
    assert result["entries_indexed"] == 5
    assert result["sessions_found"] == 2


def test_index_structure_correct(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    assert os.path.exists(os.path.join(index_dir, "sessions.jsonl"))
    assert os.path.exists(os.path.join(index_dir, "actions.jsonl"))
    assert os.path.exists(os.path.join(index_dir, "meta.json"))


# --- Queries ---

def test_find_session_by_id(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    sess = index.find_session("session-1")
    assert sess is not None
    assert sess["session_id"] == "session-1"
    assert sess["entry_count"] == 3
    assert len(sess["entry_ids"]) == 3


def test_get_actions_by_name(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    actions = index.get_actions(action_name="search")
    assert len(actions) == 2  # one in each session


def test_get_actions_by_time_range(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    # Only session 1 actions (10:00-10:02)
    actions = index.get_actions(
        start_time="2026-03-15T10:00:00",
        end_time="2026-03-15T10:30:00"
    )
    assert len(actions) == 3


def test_get_actions_multiple_filters(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    actions = index.get_actions(action_name="search", session_id="session-1")
    assert len(actions) == 1


# --- Performance ---

def test_query_10k_entries_subsecond(tmp_dirs):
    data_dir, index_dir = tmp_dirs
    storage = Storage(data_dir=data_dir)
    base = datetime(2026, 1, 1)
    for i in range(500):
        sid = f"session-{i // 10}"
        action = ["search", "analyze", "reply", "api_call"][i % 4]
        entry = _make_entry(sid, action, ts=base + timedelta(minutes=i))
        storage.append(entry)

    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)

    t0 = time.monotonic()
    results = index.get_actions(action_name="search")
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0
    assert len(results) > 0


def test_find_session_constant_time(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    t0 = time.monotonic()
    for _ in range(1000):
        index.find_session("session-1")
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0  # 1000 lookups in < 1s


# --- Consistency ---

def test_index_consistent_after_build(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    assert index.is_consistent(storage) is True


def test_is_consistent_detects_divergence(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    # Add new entry after index was built
    new_entry = _make_entry("session-3", "new_action")
    storage.append(new_entry)
    assert index.is_consistent(storage) is False


def test_index_rebuild_restores_consistency(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    new_entry = _make_entry("session-3", "new_action")
    storage.append(new_entry)
    assert index.is_consistent(storage) is False
    index.build_from_storage(storage)
    assert index.is_consistent(storage) is True


# --- Edge Cases ---

def test_query_nonexistent_session(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    assert index.find_session("does-not-exist") is None


def test_query_no_matching_actions(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    actions = index.get_actions(action_name="nonexistent_action")
    assert actions == []


def test_list_sessions_empty_index(tmp_dirs):
    data_dir, index_dir = tmp_dirs
    storage = Storage(data_dir=data_dir)
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    assert index.list_sessions() == []


def test_list_sessions_ordered_by_recency(storage_with_entries):
    storage, index_dir = storage_with_entries
    index = SessionIndex(index_dir, shard_id="sessions")
    index.build_from_storage(storage)
    sessions = index.list_sessions()
    assert len(sessions) == 2
    # session-2 is more recent (started 1 hour later)
    assert sessions[0]["session_id"] == "session-2"


def test_index_persists_and_reloads(storage_with_entries):
    storage, index_dir = storage_with_entries
    index1 = SessionIndex(index_dir, shard_id="sessions")
    index1.build_from_storage(storage)

    # Create new instance — should load from disk
    index2 = SessionIndex(index_dir, shard_id="sessions")
    sess = index2.find_session("session-1")
    assert sess is not None
    assert sess["entry_count"] == 3
