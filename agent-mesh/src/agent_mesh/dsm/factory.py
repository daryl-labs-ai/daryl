"""Event factory functions. One per event type."""
from __future__ import annotations

from .event import build_event

_VERSION = "1.0"


# ---------- System events ----------

def _system(
    event_type: str,
    scope_id: str,
    server_id: str,
    payload: dict,
    parent_event_id: str | None = None,
    causal_refs: list[str] | None = None,
) -> dict:
    return build_event(
        event_type=event_type,
        event_version=_VERSION,
        scope_type="system",
        scope_id=scope_id,
        source_type="server",
        source_id=server_id,
        writer_type="server",
        writer_id=server_id,
        payload=payload,
        parent_event_id=parent_event_id,
        causal_refs=causal_refs,
    )


def server_started(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system("server_started", "system.server.lifecycle", server_id, payload, parent_event_id)


def server_stopped(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system("server_stopped", "system.server.lifecycle", server_id, payload, parent_event_id)


def server_recovered(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system("server_recovered", "system.server.lifecycle", server_id, payload, parent_event_id)


def agent_registered(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system("agent_registered", "system.agent_registry", server_id, payload, parent_event_id)


def agent_registration_rejected(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system(
        "agent_registration_rejected", "system.agent_registry", server_id, payload, parent_event_id
    )


def agent_status_changed(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system("agent_status_changed", "system.agent_registry", server_id, payload, parent_event_id)


def agent_key_rotated(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system("agent_key_rotated", "system.agent_registry", server_id, payload, parent_event_id)


def reputation_updated(server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _system("reputation_updated", "system.reputation", server_id, payload, parent_event_id)


# ---------- Mission events ----------

def _mission_server_authored(
    event_type: str,
    mission_id: str,
    server_id: str,
    payload: dict,
    parent_event_id: str | None = None,
    causal_refs: list[str] | None = None,
) -> dict:
    return build_event(
        event_type=event_type,
        event_version=_VERSION,
        scope_type="mission",
        scope_id=f"mission_{mission_id}",
        source_type="server",
        source_id=server_id,
        writer_type="server",
        writer_id=server_id,
        payload=payload,
        parent_event_id=parent_event_id,
        causal_refs=causal_refs,
    )


def _mission_agent_authored(
    event_type: str,
    mission_id: str,
    server_id: str,
    agent_id: str,
    payload: dict,
    parent_event_id: str | None = None,
    causal_refs: list[str] | None = None,
) -> dict:
    return build_event(
        event_type=event_type,
        event_version=_VERSION,
        scope_type="mission",
        scope_id=f"mission_{mission_id}",
        source_type="agent",
        source_id=agent_id,
        writer_type="server",
        writer_id=server_id,
        payload=payload,
        parent_event_id=parent_event_id,
        causal_refs=causal_refs,
    )


def mission_created(mission_id: str, server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _mission_server_authored("mission_created", mission_id, server_id, payload, parent_event_id)


def task_created(mission_id: str, server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _mission_server_authored("task_created", mission_id, server_id, payload, parent_event_id)


def task_assigned(mission_id: str, server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _mission_server_authored("task_assigned", mission_id, server_id, payload, parent_event_id)


def task_started(
    mission_id: str, server_id: str, agent_id: str, payload: dict, parent_event_id: str | None = None
) -> dict:
    return _mission_agent_authored(
        "task_started", mission_id, server_id, agent_id, payload, parent_event_id
    )


def task_result_submitted(
    mission_id: str, server_id: str, agent_id: str, payload: dict, parent_event_id: str | None = None
) -> dict:
    return _mission_agent_authored(
        "task_result_submitted", mission_id, server_id, agent_id, payload, parent_event_id
    )


def task_result_rejected(
    mission_id: str, server_id: str, payload: dict, parent_event_id: str | None = None
) -> dict:
    return _mission_server_authored(
        "task_result_rejected", mission_id, server_id, payload, parent_event_id
    )


def critique_submitted(
    mission_id: str, server_id: str, agent_id: str, payload: dict, parent_event_id: str | None = None
) -> dict:
    return _mission_agent_authored(
        "critique_submitted", mission_id, server_id, agent_id, payload, parent_event_id
    )


def validation_completed(
    mission_id: str, server_id: str, agent_id: str, payload: dict, parent_event_id: str | None = None
) -> dict:
    return _mission_agent_authored(
        "validation_completed", mission_id, server_id, agent_id, payload, parent_event_id
    )


def mission_closed(mission_id: str, server_id: str, payload: dict, parent_event_id: str | None = None) -> dict:
    return _mission_server_authored("mission_closed", mission_id, server_id, payload, parent_event_id)
