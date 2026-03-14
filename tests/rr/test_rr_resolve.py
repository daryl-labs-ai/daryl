# -*- coding: utf-8 -*-
"""
Tests for RR resolve_entries and query(resolve=True). Uses temporary DSM storage only.
"""

import pytest

from dsm.core.models import Entry
from dsm.rr.navigator import RRNavigator
from dsm.rr.query import RRQueryEngine


def test_resolve_entries_returns_entries(navigator):
    """resolve_entries(records) returns list of Entry objects."""
    records = navigator.navigate_session("s1")
    if not records:
        pytest.skip("no session s1 records in index")
    entries = navigator.resolve_entries(records)
    assert isinstance(entries, list)
    for e in entries:
        assert isinstance(e, Entry)
        assert getattr(e, "id", None) is not None
        assert getattr(e, "content", None) is not None


def test_resolve_entries_with_limit(navigator):
    """resolve_entries(records, limit=N) returns at most N entries."""
    records = navigator.navigate_shard("sessions")
    if not records:
        pytest.skip("no shard records")
    entries = navigator.resolve_entries(records, limit=2)
    assert len(entries) <= 2
    for e in entries:
        assert isinstance(e, Entry)


def test_query_resolve_true_returns_entries(query_engine):
    """query(..., resolve=True) returns Entry objects."""
    result = query_engine.query(session_id="s1", resolve=True)
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, Entry), f"expected Entry, got {type(item)}"


def test_query_resolve_false_returns_records(query_engine):
    """query(..., resolve=False) returns metadata records (dicts)."""
    result = query_engine.query(session_id="s1", resolve=False)
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, dict), f"expected dict, got {type(item)}"
        assert "session_id" in item or "entry_id" in item


def test_query_resolve_true_with_limit(query_engine):
    """query(..., resolve=True, limit=N) returns at most N entries."""
    result = query_engine.query(shard_id="sessions", resolve=True, limit=2)
    assert len(result) <= 2
    for e in result:
        assert isinstance(e, Entry)
