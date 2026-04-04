"""
Tests for session/session_limits_manager.py — targeting uncovered lines.

Covers:
  - can_poll_home / mark_home_polled
  - can_execute_action / mark_action_executed
  - Daily budget management
  - State persistence / reload
  - Sidecar files
  - agent_defaults factory
  - mark_home_poll_skipped / mark_action_skipped_cooldown
  - get_state / print_state
"""

import json
import time
from pathlib import Path

import pytest

from dsm.session.session_limits_manager import SessionLimitsManager


@pytest.fixture
def limits(tmp_path):
    return SessionLimitsManager(base_dir=str(tmp_path))


@pytest.fixture
def limits_agent(tmp_path):
    return SessionLimitsManager.agent_defaults(str(tmp_path))


class TestInit:
    def test_default_creation(self, limits):
        assert limits is not None
        assert limits.HOME_POLL_COOLDOWN == 30

    def test_agent_defaults(self, limits_agent):
        assert limits_agent.ACTION_COOLDOWN == 0


class TestHomePolling:
    def test_can_poll_initially(self, limits):
        can, remaining = limits.can_poll_home()
        assert can is True
        assert remaining == 0

    def test_cannot_poll_after_mark(self, limits):
        now = time.time()
        limits.mark_home_polled(now_ts=now)
        can, remaining = limits.can_poll_home(now_ts=now + 1)
        assert can is False
        assert remaining > 0

    def test_can_poll_after_cooldown(self, limits):
        now = time.time()
        limits.mark_home_polled(now_ts=now)
        can, remaining = limits.can_poll_home(now_ts=now + 60)
        assert can is True
        assert remaining == 0


class TestActionExecution:
    def test_can_execute_initially(self, limits):
        can, reason = limits.can_execute_action()
        assert can is True
        assert reason is None

    def test_cooldown_blocks_action(self, limits):
        now = time.time()
        limits.mark_action_executed(now_ts=now)
        can, reason = limits.can_execute_action(now_ts=now + 1)
        assert can is False
        assert reason == "cooldown"

    def test_can_execute_after_cooldown(self, limits):
        now = time.time()
        limits.mark_action_executed(now_ts=now)
        can, reason = limits.can_execute_action(now_ts=now + 200)
        assert can is True

    def test_daily_budget_enforced(self, limits):
        now = time.time()
        for i in range(limits.DAILY_ACTION_BUDGET):
            # Space out actions to avoid cooldown
            ts = now + (i * (limits.ACTION_COOLDOWN + 1))
            limits.mark_action_executed(now_ts=ts)
        # After exhausting budget, next check should fail
        final_ts = now + (limits.DAILY_ACTION_BUDGET * (limits.ACTION_COOLDOWN + 1))
        can, reason = limits.can_execute_action(now_ts=final_ts)
        assert can is False
        # reason should indicate daily_limit or both
        assert reason in ("daily_limit", "both")


class TestSkipMarkers:
    def test_mark_home_poll_skipped(self, limits):
        result = limits.mark_home_poll_skipped()
        assert result is True
        state = limits.get_state()
        assert state["skipped_home_polls"] >= 1

    def test_mark_action_skipped_cooldown(self, limits):
        result = limits.mark_action_skipped_cooldown("cooldown")
        assert result is True
        state = limits.get_state()
        assert state["skipped_actions_cooldown"] >= 1

    def test_mark_action_skipped_daily_limit(self, limits):
        result = limits.mark_action_skipped_cooldown("daily_limit")
        assert result is True
        state = limits.get_state()
        assert state["skipped_actions_daily_limit"] >= 1


class TestStatePersistence:
    def test_state_saved_and_loaded(self, tmp_path):
        lm1 = SessionLimitsManager(base_dir=str(tmp_path))
        now = time.time()
        lm1.mark_home_polled(now_ts=now)
        lm1.mark_action_executed(now_ts=now)

        lm2 = SessionLimitsManager(base_dir=str(tmp_path))
        state = lm2.get_state()
        assert state["last_home_poll_ts"] == now
        assert state["last_action_ts"] == now

    def test_get_state_returns_dict(self, limits):
        state = limits.get_state()
        assert isinstance(state, dict)
        assert "last_home_poll_ts" in state


class TestSidecarFiles:
    def test_write_and_read_hash_sidecar(self, limits):
        limits._write_hash_to_sidecar("abc123")
        result = limits._read_hash_from_sidecar()
        assert result == "abc123"

    def test_read_missing_sidecar(self, limits):
        result = limits._read_sidecar_file("nonexistent.txt")
        assert result is None

    def test_write_sidecar(self, limits):
        result = limits._write_sidecar_file("test.txt", "content")
        assert result is True
        val = limits._read_sidecar_file("test.txt")
        assert val == "content"


class TestPrintState:
    def test_print_state(self, limits, capsys):
        limits.mark_home_polled()
        limits.mark_action_executed()
        limits.print_state()
        captured = capsys.readouterr()
        assert "SESSION LIMITS STATE" in captured.out
        assert "Daily Budget" in captured.out
