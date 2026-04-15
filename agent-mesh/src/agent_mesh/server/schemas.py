"""HTTP request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterAgentRequest(BaseModel):
    agent_id: str
    agent_type: str
    capabilities: list[str]
    public_key: str


class RegisterAgentResponse(BaseModel):
    agent_id: str
    key_id: str
    registered_at: str
    event_id: str


class CreateMissionRequest(BaseModel):
    title: str
    description: str
    metadata: dict = Field(default_factory=dict)


class CreateMissionResponse(BaseModel):
    mission_id: str
    event_id: str
    created_at: str


class CreateTaskRequest(BaseModel):
    mission_id: str
    task_type: str
    payload: dict


class CreateTaskResponse(BaseModel):
    task_id: str
    mission_id: str
    event_id: str
    assigned_to: str | None


class SubmitTaskResultRequest(BaseModel):
    agent_id: str
    contribution_id: str
    content: dict
    self_reported_confidence: float
    signature: str
    created_at: str
    # Optional — explicit signing metadata carried at the top level of the
    # submission envelope (per V0 contract). key_id, when present, is used to
    # cross-check against the registry's recorded key_id for this agent;
    # payload_hash is stored in the emitted event for auditability. Neither
    # field is required for verification — the server can reconstruct both.
    key_id: str | None = None
    payload_hash: str | None = None


class SubmitTaskResultResponse(BaseModel):
    task_id: str
    event_id: str
    receipt_id: str
    entry_hash: str
