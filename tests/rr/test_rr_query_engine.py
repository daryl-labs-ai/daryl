# -*- coding: utf-8 -*-
"""
Tests for RR Query Engine. Uses temporary DSM storage and index only.
"""

import pytest

from dsm.rr.query import RRQueryEngine


def test_query_empty_returns_empty(query_engine):
    """query() with no filters returns [] (empty query safety)."""
    result = query_engine.query()
    assert result == []


def test_query_single_filter_session(query_engine):
    """query(session_id=...) returns records for that session."""
    records = query_engine.query(session_id="s1")
    assert isinstance(records, list)
    for r in records:
        assert r.get("session_id") == "s1"


def test_query_single_filter_agent(query_engine):
    """query(agent=...) returns records for that agent."""
    records = query_engine.query(agent="agent_a")
    assert isinstance(records, list)
    for r in records:
        assert r.get("agent") == "agent_a"


def test_query_single_filter_shard(query_engine):
    """query(shard_id=...) returns records for that shard."""
    records = query_engine.query(shard_id="sessions")
    assert isinstance(records, list)
    for r in records:
        assert r.get("shard_id") == "sessions"


def test_query_multi_filter_intersection(query_engine):
    """query(session_id=X, agent=Y) returns records matching both."""
    records = query_engine.query(session_id="s1", agent="agent_a")
    assert isinstance(records, list)
    for r in records:
        assert r.get("session_id") == "s1"
        assert r.get("agent") == "agent_a"


def test_query_limit(query_engine):
    """query(..., limit=N) returns at most N records."""
    records = query_engine.query(shard_id="sessions", limit=2)
    assert len(records) <= 2


def test_query_sort_asc(query_engine):
    """query(..., sort='asc') returns records sorted by timestamp ascending."""
    records = query_engine.query(shard_id="sessions", sort="asc")
    assert isinstance(records, list)
    if len(records) >= 2:
        for i in range(len(records) - 1):
            a = records[i].get("timestamp")
            b = records[i + 1].get("timestamp")
            if a is not None and b is not None:
                assert float(a) <= float(b)


def test_query_sort_desc(query_engine):
    """query(..., sort='desc') returns records sorted by timestamp descending."""
    records = query_engine.query(shard_id="sessions", sort="desc")
    assert isinstance(records, list)
    if len(records) >= 2:
        for i in range(len(records) - 1):
            a = records[i].get("timestamp")
            b = records[i + 1].get("timestamp")
            if a is not None and b is not None:
                assert float(a) >= float(b)


def test_query_limit_after_sort(query_engine):
    """limit is applied after sorting."""
    all_records = query_engine.query(shard_id="sessions", sort="asc")
    limited = query_engine.query(shard_id="sessions", sort="asc", limit=2)
    assert len(limited) <= 2
    if len(all_records) >= 2 and len(limited) == 2:
        assert limited[0] == all_records[0]
        assert limited[1] == all_records[1]
