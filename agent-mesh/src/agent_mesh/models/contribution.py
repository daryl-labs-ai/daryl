"""Contribution domain model."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Contribution(BaseModel):
    contribution_id: str
    task_id: str
    mission_id: str
    agent_id: str
    contribution_type: Literal["task_result", "critique", "validation"]
    content: dict
    content_hash: str
    signature: str
    self_reported_confidence: float
    created_at: datetime
