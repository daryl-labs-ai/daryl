"""In-memory agent registry."""
from __future__ import annotations

from ..models.agent import Agent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.agent_id in self._agents:
            raise ValueError(f"agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def list_active(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.status == "active"]

    def update_status(self, agent_id: str, status: str) -> None:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"unknown agent: {agent_id}")
        self._agents[agent_id] = agent.model_copy(update={"status": status})

    def update_reputation(self, agent_id: str, delta: float) -> None:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"unknown agent: {agent_id}")
        self._agents[agent_id] = agent.model_copy(update={"reputation": agent.reputation + delta})

    def rotate_key(self, agent_id: str, new_public_key: str) -> None:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"unknown agent: {agent_id}")
        self._agents[agent_id] = agent.model_copy(update={"public_key": new_public_key})
