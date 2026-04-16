"""Bridge data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContextQuery:
    consumer_agent_id: str
    scope: str  # "mission:<id>" | "agent:<id>" | "system"
    limit: int = 20


@dataclass
class ContextFact:
    type: str  # "submission"
    agent_id: str
    text: str  # content truncated to 200 chars
    source_event_ids: list[str]


@dataclass
class ProvenMemory:
    summary: str
    facts: list[ContextFact]


@dataclass
class LiveState:
    mission_id: Optional[str]
    open_tasks: int
    assigned_agents: list[str]
    status: str  # "open" | "closed" | "unknown"


@dataclass
class ContextPack:
    context_id: str  # "ctx_<ULID>"
    consumer_agent_id: str
    scope: str
    generated_at: str  # ISO 8601 UTC
    proven_memory: ProvenMemory
    live_state: LiveState
    source_event_ids: list[str]  # MASTER — single source of truth
    raw_event_count: int
    dsm_event_id: Optional[str] = None  # populated after DSM write
