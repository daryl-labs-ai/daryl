"""Task domain model."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Task(BaseModel):
    task_id: str
    mission_id: str
    task_type: str
    payload: dict
    assigned_to: str | None = None
    status: Literal["pending", "assigned", "in_progress", "completed", "failed"] = "pending"
    created_at: datetime
    assigned_at: datetime | None = None
    result: dict | None = None
