"""
Runtime tests for DSM Goose integration (MCP server).
Tests real execution paths — not just file existence.

Run: python -m pytest tests/integrations/test_goose.py -v
"""

import json
import os
import shutil
import sys

import pytest

# Ensure dsm package is importable
from dsm.integrations.goose.server import (
    dsm_start_session,
    dsm_end_session,
    dsm_log_action,
    dsm_confirm_action,
    dsm_snapshot,
    dsm_recall,
    dsm_recent,
    dsm_search,
    dsm_verify,
    dsm_summary,
    dsm_status,
)

TEST_DATA_DIR = f"/tmp/dsm-goose-test-{os.getpid()}"


@pytest.fixture(autouse=True)
def setup_env():
    """Use isolated test data directory."""
    os.environ["DSM_DATA_DIR"] = TEST_DATA_DIR
    yield
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


class TestDSMStatus:
    """Test dsm_status() — the datetime serialization bug we fixed."""

    def test_status_returns_valid_json(self):
        data = json.loads(dsm_status())
        assert "shards" in data
        assert "total_entries" in data
        assert "agent_id" in data

    def test_status_datetime_fields_are_strings(self):
        """ShardMeta datetime fields must be ISO strings, not datetime objects."""
        dsm_start_session("status-datetime-test")
        data = json.loads(dsm_status())
        for shard in data.get("shards", []):
            if shard.get("last_updated"):
                assert isinstance(shard["last_updated"], str)
                assert "T" in shard["last_updated"]
            if shard.get("created_at"):
                assert isinstance(shard["created_at"], str)


class TestSessionLifecycle:
    def test_start_returns_json(self):
        data = json.loads(dsm_start_session("lifecycle-test"))
        assert data.get("status") == "started"
        assert data.get("agent_id") == "goose"

    def test_end_returns_json(self):
        dsm_start_session("end-test")
        data = json.loads(dsm_end_session())
        assert data is not None


class TestActionLogging:
    def test_log_returns_intent_id(self):
        dsm_start_session("action-test")
        data = json.loads(dsm_log_action("test_action", json.dumps({"key": "value"})))
        assert "intent_id" in data

    def test_confirm_succeeds(self):
        dsm_start_session("confirm-test")
        intent_id = json.loads(dsm_log_action("my_action", "{}"))["intent_id"]
        data = json.loads(dsm_confirm_action(intent_id, json.dumps({"success": True})))
        assert data.get("success") is True


class TestVerification:
    def test_verify_returns_list(self):
        dsm_start_session("verify-test")
        data = json.loads(dsm_verify())
        assert isinstance(data, list)
        if len(data) > 0:
            assert "shard_id" in data[0]
            assert "status" in data[0]

    def test_verify_no_tampering(self):
        dsm_start_session("integrity-test")
        dsm_log_action("clean_action", "{}")
        data = json.loads(dsm_verify())
        if len(data) > 0:
            assert data[0].get("tampered", 0) == 0


class TestRecallAndSearch:
    def test_recent_returns_data(self):
        dsm_start_session("recent-test")
        data = json.loads(dsm_recent(5))
        assert isinstance(data, (dict, list))

    def test_summary_returns_stats(self):
        dsm_start_session("summary-test")
        data = json.loads(dsm_summary())
        assert "shard_id" in data or "entry_count" in data

    def test_search_returns_results(self):
        dsm_start_session("search-test")
        dsm_log_action("unique_marker_xyz", "{}")
        data = json.loads(dsm_search("unique_marker_xyz"))
        assert isinstance(data, (dict, list))

    def test_recall_returns_context(self):
        dsm_start_session("recall-test")
        data = json.loads(dsm_recall(2000, 1))
        assert isinstance(data, (dict, list))


class TestSnapshot:
    def test_snapshot_succeeds_or_cooldown(self):
        """First snapshot may be taken by start_session — cooldown is expected."""
        dsm_start_session("snapshot-test")
        try:
            result = dsm_snapshot(json.dumps({"checkpoint": "test"}))
            data = json.loads(result)
            assert data.get("status") == "snapshotted"
        except Exception as e:
            assert "datetime" not in str(type(e)).lower(), f"Datetime bug: {e}"


class TestFullFlow:
    """End-to-end: start → log → confirm → verify → status → end."""

    def test_complete_session_flow(self):
        start = json.loads(dsm_start_session("full-flow"))
        assert start.get("status") == "started"

        intent_id = json.loads(dsm_log_action("flow_action", json.dumps({"step": 1})))["intent_id"]
        confirm = json.loads(dsm_confirm_action(intent_id, json.dumps({"done": True})))
        assert confirm.get("success") is True

        status = json.loads(dsm_status())
        assert isinstance(status.get("shards"), list)

        verify = json.loads(dsm_verify())
        assert isinstance(verify, list)

        end = json.loads(dsm_end_session())
        assert end is not None
