"""Agent domain model."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Agent(BaseModel):
    agent_id: str
    agent_type: str
    capabilities: list[str]
    public_key: str
    status: Literal["active", "inactive", "suspended"] = "active"
    reputation: float = 1.0
    registered_at: datetime
    last_heartbeat: datetime | None = None
