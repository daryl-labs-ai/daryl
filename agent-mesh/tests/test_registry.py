"""Tests for AgentRegistry."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_mesh.models.agent import Agent
from agent_mesh.registry.agent_registry import AgentRegistry


def _make(agent_id: str, capabilities=None, status="active") -> Agent:
    return Agent(
        agent_id=agent_id,
        agent_type="worker",
        capabilities=capabilities or ["analyze"],
        public_key="pk_" + agent_id,
        status=status,
        registered_at=datetime.now(timezone.utc),
    )


def test_register_and_get():
    r = AgentRegistry()
    a = _make("a1")
    r.register(a)
    assert r.get("a1").agent_id == "a1"


def test_register_duplicate_raises():
    r = AgentRegistry()
    r.register(_make("a1"))
    with pytest.raises(ValueError):
        r.register(_make("a1"))


def test_list_active_only_returns_active():
    r = AgentRegistry()
    r.register(_make("a1", status="active"))
    r.register(_make("a2", status="suspended"))
    active = r.list_active()
    assert len(active) == 1
    assert active[0].agent_id == "a1"


def test_update_status():
    r = AgentRegistry()
    r.register(_make("a1"))
    r.update_status("a1", "suspended")
    assert r.get("a1").status == "suspended"


def test_update_status_unknown_raises():
    r = AgentRegistry()
    with pytest.raises(ValueError):
        r.update_status("ghost", "suspended")


def test_update_reputation():
    r = AgentRegistry()
    r.register(_make("a1"))
    r.update_reputation("a1", 0.5)
    assert r.get("a1").reputation == 1.5


def test_rotate_key():
    r = AgentRegistry()
    r.register(_make("a1"))
    r.rotate_key("a1", "new_pk")
    assert r.get("a1").public_key == "new_pk"


def test_get_unknown_returns_none():
    r = AgentRegistry()
    assert r.get("nope") is None
