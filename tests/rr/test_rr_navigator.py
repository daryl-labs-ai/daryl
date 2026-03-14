# -*- coding: utf-8 -*-
"""
Tests for RR Navigator. Uses temporary DSM storage and index only.
"""

import pytest

from dsm.rr.navigator import RRNavigator


def test_navigate_session(navigator):
    """navigate_session returns records for that session."""
    records = navigator.navigate_session("s1")
    assert isinstance(records, list)
    for r in records:
        assert r.get("session_id") == "s1"


def test_navigate_agent(navigator):
    """navigate_agent returns records for that agent."""
    records = navigator.navigate_agent("agent_a")
    assert isinstance(records, list)
    for r in records:
        assert r.get("agent") == "agent_a"


def test_navigate_shard(navigator):
    """navigate_shard returns records for that shard."""
    records = navigator.navigate_shard("sessions")
    assert isinstance(records, list)
    for r in records:
        assert r.get("shard_id") == "sessions"


def test_navigate_session_unknown(navigator):
    """navigate_session with unknown id returns empty list."""
    records = navigator.navigate_session("unknown_session_xyz")
    assert records == []


def test_navigate_agent_unknown(navigator):
    """navigate_agent with unknown agent returns empty list."""
    records = navigator.navigate_agent("unknown_agent_xyz")
    assert records == []


def test_timeline_no_bounds(navigator):
    """timeline() with no start/end returns all records in order."""
    records = navigator.timeline()
    assert isinstance(records, list)
    if len(records) >= 2:
        a, b = records[0].get("timestamp"), records[1].get("timestamp")
        assert a is not None and b is not None
        assert float(a) <= float(b)


def test_timeline_with_end(navigator):
    """timeline(end_time=...) filters to records before end."""
    import time
    end_ts = time.time() + 3600
    records = navigator.timeline(end_time=end_ts)
    assert isinstance(records, list)
    for r in records:
        ts = r.get("timestamp")
        if ts is not None:
            assert float(ts) <= end_ts


def test_timeline_with_start(navigator):
    """timeline(start_time=...) filters to records after start."""
    start_ts = 0.0
    records = navigator.timeline(start_time=start_ts)
    assert isinstance(records, list)
    for r in records:
        ts = r.get("timestamp")
        if ts is not None:
            assert float(ts) >= start_ts
