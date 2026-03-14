# -*- coding: utf-8 -*-
"""
Tests for RR Index Builder. Uses temporary DSM storage only.
"""

import pytest
from pathlib import Path

from dsm.core.storage import Storage
from dsm.rr.index import RRIndexBuilder


def test_build_empty_storage(tmp_path):
    """build() with no shards produces empty indexes."""
    storage = Storage(data_dir=str(tmp_path))
    index_dir = tmp_path / "index"
    builder = RRIndexBuilder(storage=storage, index_dir=str(index_dir))
    builder.build()
    assert builder.session_index == {}
    assert builder.agent_index == {}
    assert builder.timeline_index == []
    assert builder.shard_index == {}


def test_build_with_data(storage, index_builder, temp_data_dir):
    """build() populates session_index, agent_index, timeline_index, shard_index."""
    index_builder.build()
    assert isinstance(index_builder.session_index, dict)
    assert isinstance(index_builder.agent_index, dict)
    assert isinstance(index_builder.timeline_index, list)
    assert isinstance(index_builder.shard_index, dict)
    # We have sessions shard with 5 entries (s1, s2, agent_a, agent_b)
    assert len(index_builder.session_index) >= 1
    assert len(index_builder.agent_index) >= 1
    assert len(index_builder.timeline_index) >= 1
    assert len(index_builder.shard_index) >= 1
    for rec in index_builder.timeline_index:
        assert "timestamp" in rec
        assert "session_id" in rec
        assert "agent" in rec or "entry_id" in rec
        assert "shard_id" in rec


def test_session_index_has_sessions(index_builder):
    """session_index maps session_id to list of records."""
    index_builder.build()
    for sid, records in index_builder.session_index.items():
        assert isinstance(sid, str)
        assert isinstance(records, list)
        for r in records:
            assert r.get("session_id") == sid or sid == "none"


def test_agent_index_has_agents(index_builder):
    """agent_index maps agent to list of records."""
    index_builder.build()
    for agent, records in index_builder.agent_index.items():
        assert isinstance(agent, str)
        assert isinstance(records, list)
        for r in records:
            assert r.get("agent") == agent or agent == "unknown"


def test_timeline_sorted(index_builder):
    """timeline_index is sorted by timestamp."""
    index_builder.build()
    if len(index_builder.timeline_index) < 2:
        return
    prev = index_builder.timeline_index[0].get("timestamp")
    for r in index_builder.timeline_index[1:]:
        ts = r.get("timestamp")
        assert prev is not None and ts is not None
        assert float(ts) >= float(prev)
        prev = ts


def test_shard_index_has_shards(index_builder):
    """shard_index maps shard_id to list of records."""
    index_builder.build()
    for shard_id, records in index_builder.shard_index.items():
        assert isinstance(shard_id, str)
        assert isinstance(records, list)
        for r in records:
            assert r.get("shard_id") == shard_id


def test_ensure_index_loads_or_builds(index_builder, temp_data_dir):
    """ensure_index() loads from disk if present, else builds."""
    index_builder.build()
    path = Path(index_builder._index_dir) / "sessions.idx"
    assert path.exists()
    builder2 = RRIndexBuilder(storage=index_builder.storage, index_dir=str(index_builder._index_dir))
    loaded = builder2.load()
    assert loaded is True
    assert len(builder2.session_index) == len(index_builder.session_index)
