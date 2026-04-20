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


def test_navigate_action_order_preserved_under_limit(navigator):
    """Phase N+1A order contract — Phase 7a Amendement A invariant.

    navigate_action(name, limit=k) must return the exact same records (in the
    exact same order) as navigate_action(name) truncated to [:k]. The `limit`
    parameter is a performance optimisation that does not change result order
    or set — slicing the head of a build-time-sorted bucket preserves timestamp-
    ascending order by construction.
    """
    # Pick an action_name that the conftest fixture actually populates. If none
    # has multiple records the test is trivially satisfied but the invariant
    # still must hold.
    builder = navigator.index_builder
    idx = getattr(builder, "action_index", {}) or {}
    assert idx, "conftest fixture should populate action_index for this test"

    # Pick a non-empty bucket.
    target = next(iter(idx.keys()))

    full = navigator.navigate_action(target)
    assert isinstance(full, list)

    # limit=0 is an edge case but is documented — should return empty list.
    empty = navigator.navigate_action(target, limit=0)
    assert empty == []

    # limit=1 should match first element of full result.
    if full:
        one = navigator.navigate_action(target, limit=1)
        assert one == full[:1], "limit=1 must equal full[:1]"

    # limit >= len(full) should return the full bucket in the same order.
    over = navigator.navigate_action(target, limit=len(full) + 10)
    assert over == full, "limit above bucket size must equal full result"

    # limit in the middle — order AND identity invariance.
    if len(full) >= 2:
        mid = len(full) // 2
        half = navigator.navigate_action(target, limit=mid)
        assert half == full[:mid], "limit=k must equal full[:k] (order preserved)"

    # And the returned list must still be a fresh list — a caller mutating it
    # should not corrupt the underlying action_index bucket.
    stolen = navigator.navigate_action(target, limit=1)
    if stolen:
        stolen.clear()
        again = navigator.navigate_action(target, limit=1)
        assert again == full[:1], "mutating the returned list must not affect the index"
