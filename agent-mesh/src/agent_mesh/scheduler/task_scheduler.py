"""Simple round-robin task scheduler."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..models.task import Task
from ..registry.agent_registry import AgentRegistry


@dataclass
class TaskRequest:
    """Pull-model task envelope returned by `next_for_agent`."""

    task_id: str
    mission_id: str
    task_type: str
    objective: str
    constraints: dict


class TaskScheduler:
    def __init__(self) -> None:
        self._cursor = 0
        self._tasks_ref: dict[str, Task] | None = None

    def set_tasks_source(self, tasks: dict[str, Task]) -> None:
        """Wire the scheduler to the live tasks dict (mutated in place on assignment)."""
        self._tasks_ref = tasks

    def assign_task(self, task: Task, registry: AgentRegistry) -> str | None:
        candidates = [a for a in registry.list_active() if task.task_type in a.capabilities]
        if not candidates:
            return None
        candidates.sort(key=lambda a: a.agent_id)
        agent = candidates[self._cursor % len(candidates)]
        self._cursor += 1
        return agent.agent_id

    def next_for_agent(
        self, agent_id: str, capabilities: list[str]
    ) -> Optional[TaskRequest]:
        """Return the earliest pending task whose required_capabilities are all
        present in the agent's capabilities, marking it assigned in place.

        Returns None if no tasks source is wired or no eligible task is found.
        """
        if self._tasks_ref is None:
            return None
        agent_caps = set(capabilities)

        for task_id, task in self._tasks_ref.items():
            if task.status != "pending":
                continue
            required = task.payload.get("required_capabilities") or [task.task_type]
            if not set(required).issubset(agent_caps):
                continue

            self._tasks_ref[task_id] = task.model_copy(
                update={
                    "assigned_to": agent_id,
                    "status": "assigned",
                    "assigned_at": datetime.now(timezone.utc),
                }
            )

            payload = task.payload or {}
            objective = payload.get("objective", "")
            constraints_raw = payload.get("constraints") or {}
            constraints = {
                "deadline_ms": constraints_raw.get("deadline_ms"),
                "max_output_tokens": constraints_raw.get("max_output_tokens", 1200),
                "output_format": constraints_raw.get("output_format"),
            }

            return TaskRequest(
                task_id=task.task_id,
                mission_id=task.mission_id,
                task_type=task.task_type,
                objective=objective,
                constraints=constraints,
            )
        return None
