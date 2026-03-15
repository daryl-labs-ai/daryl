"""
SessionGraph lifecycle tests.
Uses tmp_path for storage; does not modify existing scripts in tests/session/.
"""

import logging
import uuid
from datetime import datetime
from io import StringIO

import pytest

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.session.session_graph import SessionGraph
from dsm.session.session_limits_manager import SessionLimitsManager


def _make_limits_permissive(base_dir: str) -> SessionLimitsManager:
    """Limits manager that allows immediate poll and actions for tests."""
    m = SessionLimitsManager(base_dir=base_dir)
    m.HOME_POLL_COOLDOWN = 0
    m.ACTION_COOLDOWN = 0
    m.DAILY_ACTION_BUDGET = 100
    return m


def test_start_session_end_session(tmp_path):
    """start_session then end_session."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    e1 = sg.start_session("test")
    assert e1 is not None
    assert sg.is_session_active()
    e2 = sg.end_session()
    assert e2 is not None
    assert not sg.is_session_active()
    entries = storage.read("sessions", limit=10)
    assert len(entries) >= 2


def test_record_snapshot_in_session(tmp_path):
    """record_snapshot within an active session."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    sg.start_session("test")
    e = sg.record_snapshot({"screen": "home", "items": []})
    assert e is not None
    sg.end_session()


def test_execute_action_in_session(tmp_path):
    """execute_action within an active session."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    sg.start_session("test")
    e = sg.execute_action("post_reply", {"text": "hello"})
    assert e is not None
    sg.end_session()


def test_double_start_session(tmp_path):
    """Double start_session auto-closes previous session."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    e1 = sg.start_session("first")
    assert e1 is not None
    first_id = sg.get_session_id()
    e2 = sg.start_session("second")
    assert e2 is not None
    assert sg.get_session_id() != first_id
    entries = storage.read("sessions", limit=10)
    # session_start, session_end (auto), session_start
    assert len(entries) >= 3


def test_end_session_without_session(tmp_path):
    """end_session with no active session returns None."""
    storage = Storage(data_dir=str(tmp_path))
    limits = SessionLimitsManager(base_dir=str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    e = sg.end_session()
    assert e is None


def test_snapshot_outside_session(tmp_path):
    """record_snapshot with no active session returns None."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    e = sg.record_snapshot({"x": 1})
    assert e is None


def test_action_outside_session(tmp_path):
    """execute_action with no active session returns None."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    e = sg.execute_action("foo", {})
    assert e is None


def test_no_print_on_stdout(tmp_path, capsys):
    """SessionGraph uses logging only; no print() to stdout."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    sg.start_session("test")
    sg.record_snapshot({"a": 1})
    sg.execute_action("act", {})
    sg.end_session()
    out, err = capsys.readouterr()
    # No session-related print (we use logger; default root logger may still print to stderr)
    assert "Session started" not in out
    assert "Snapshot recorded" not in out
    assert "Action executed" not in out
    assert "Session ended" not in out
    assert "📌" not in out and "📦" not in out and "⚡" not in out and "🏁" not in out


def test_full_cycle_multiple_actions(tmp_path):
    """Full cycle: start, multiple snapshots/actions, end."""
    storage = Storage(data_dir=str(tmp_path))
    limits = _make_limits_permissive(str(tmp_path))
    sg = SessionGraph(storage=storage, limits_manager=limits)
    sg.start_session("cycle_test")
    sg.record_snapshot({"step": 1})
    sg.execute_action("a1", {"x": 1})
    sg.record_snapshot({"step": 2})
    sg.execute_action("a2", {"y": 2})
    e = sg.end_session()
    assert e is not None
    entries = storage.read("sessions", limit=20)
    assert len(entries) >= 5
