"""Tests for TaskScheduler."""
from __future__ import annotations

from datetime import datetime, timezone

from agent_mesh.models.agent import Agent
from agent_mesh.models.task import Task
from agent_mesh.registry.agent_registry import AgentRegistry
from agent_mesh.scheduler.task_scheduler import TaskScheduler


def _agent(agent_id, caps):
    return Agent(
        agent_id=agent_id,
        agent_type="worker",
        capabilities=caps,
        public_key="pk",
        status="active",
        registered_at=datetime.now(timezone.utc),
    )


def _task(task_type="analyze"):
    return Task(
        task_id="t1",
        mission_id="m1",
        task_type=task_type,
        payload={},
        status="pending",
        created_at=datetime.now(timezone.utc),
    )


def test_no_agent_returns_none():
    r = AgentRegistry()
    s = TaskScheduler()
    assert s.assign_task(_task(), r) is None


def test_no_capable_agent_returns_none():
    r = AgentRegistry()
    r.register(_agent("a1", ["other"]))
    s = TaskScheduler()
    assert s.assign_task(_task(), r) is None


def test_single_capable_agent_assigned():
    r = AgentRegistry()
    r.register(_agent("a1", ["analyze"]))
    s = TaskScheduler()
    assert s.assign_task(_task(), r) == "a1"


def test_round_robin_multiple_agents():
    r = AgentRegistry()
    r.register(_agent("a1", ["analyze"]))
    r.register(_agent("a2", ["analyze"]))
    s = TaskScheduler()
    assigned = [s.assign_task(_task(), r) for _ in range(4)]
    assert assigned[0] != assigned[1]
    assert set(assigned) == {"a1", "a2"}
