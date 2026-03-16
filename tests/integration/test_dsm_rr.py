#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration test for DSM Read Relay (DSM-RR).

Example usage (with real data):
    Set DSM_TEST_DATA_DIR to your data path, or use default tmp_path in pytest.
    from dsm.rr import DSMReadRelay
    rr = DSMReadRelay(data_dir=data_dir)
    summary = rr.summary("clawdbot_sessions")
    print(summary)
"""

import os
import pytest
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.rr import DSMReadRelay


@pytest.fixture
def data_dir(tmp_path):
    """Use DSM_TEST_DATA_DIR for real data, else tmp_path."""
    return os.environ.get("DSM_TEST_DATA_DIR", str(tmp_path))


def test_read_relay_init(data_dir):
    """DSMReadRelay initializes with data_dir."""
    rr = DSMReadRelay(data_dir=data_dir)
    assert rr is not None


def test_read_recent_empty():
    """read_recent on empty shard returns empty list."""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        rr = DSMReadRelay(data_dir=data_dir)
        entries = rr.read_recent("test_shard", limit=100)
        assert entries == [], entries
    print("  ✓ read_recent empty shard")


def test_read_recent_classic():
    """read_recent returns entries from classic shard."""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        storage = Storage(data_dir=data_dir)
        for i in range(5):
            e = Entry(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                session_id="s1",
                source="test",
                content=f"content_{i}",
                shard="test_shard",
                hash="",
                prev_hash=None,
                metadata={"action_name": f"action_{i % 2}"},
                version="v2.0",
            )
            storage.append(e)
        rr = DSMReadRelay(storage=storage)
        entries = rr.read_recent("test_shard", limit=10)
        assert len(entries) == 5, len(entries)
        assert entries[0].content.startswith("content_"), entries[0].content
    print("  ✓ read_recent classic shard")


def test_summary():
    """summary returns entry_count, unique_sessions, errors, top_actions."""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        storage = Storage(data_dir=data_dir)
        for i in range(6):
            e = Entry(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                session_id="s1" if i % 2 == 0 else "s2",
                source="test",
                content=f"c{i}",
                shard="clawdbot_sessions",
                hash="",
                prev_hash=None,
                metadata={
                    "action_name": "tool_call" if i % 2 == 0 else "snapshot",
                    "error": "oops" if i == 3 else None,
                },
                version="v2.0",
            )
            storage.append(e)
        rr = DSMReadRelay(storage=storage)
        summary = rr.summary("clawdbot_sessions", limit=500)
        assert summary["shard_id"] == "clawdbot_sessions"
        assert summary["entry_count"] == 6
        assert summary["unique_sessions"] == 2
        assert summary["errors"] == 1
        assert len(summary["top_actions"]) <= 10
        assert any(a[0] == "tool_call" for a in summary["top_actions"])
    print("  ✓ summary")


def test_example_usage():
    """Example from spec: DSMReadRelay(data_dir=...).summary(...)."""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        rr = DSMReadRelay(data_dir=data_dir)
        summary = rr.summary("clawdbot_sessions")
        assert "entry_count" in summary
        assert "unique_sessions" in summary
        assert "errors" in summary
        assert "top_actions" in summary
    print("  ✓ example usage (summary)")


def main():
    print("DSM-RR integration tests")
    print("=" * 50)
    test_read_recent_empty()
    test_read_recent_classic()
    test_summary()
    test_example_usage()
    print("=" * 50)
    print("All DSM-RR tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
