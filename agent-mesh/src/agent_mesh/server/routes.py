"""HTTP routes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from ulid import ULID

from ..adapters.daryl_adapter.signing import compute_content_hash
from ..dsm import factory as ev_factory
from ..models.agent import Agent
from ..models.task import Task
from ..bridge.models import ContextQuery
from .schemas import (
    CreateMissionRequest,
    CreateMissionResponse,
    CreateTaskRequest,
    CreateTaskResponse,
    RegisterAgentRequest,
    RegisterAgentResponse,
    SubmitTaskResultRequest,
    SubmitTaskResultResponse,
)
from .state import AppState

router = APIRouter()


def _state(req: Request) -> AppState:
    return req.app.state.mesh


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/health", tags=["diagnostic"])
async def health(request: Request):
    state = _state(request)
    agents = state.registry.list_active()
    return {
        "status": "ok",
        "agents_registered": len(agents),
        "agents": [{"id": a.agent_id, "capabilities": a.capabilities} for a in agents],
    }


@router.get("/agents", tags=["diagnostic"])
async def list_agents(request: Request):
    state = _state(request)
    agents = state.registry.list_active()
    return [
        {"id": a.agent_id, "capabilities": a.capabilities, "status": a.status}
        for a in agents
    ]


@router.get("/debug/tasks", tags=["diagnostic"])
async def debug_tasks(request: Request):
    state = _state(request)
    return [
        {
            "task_id": t.task_id,
            "mission_id": t.mission_id,
            "task_type": t.task_type,
            "status": t.status,
            "assigned_to": t.assigned_to,
            "payload_keys": list((t.payload or {}).keys()),
            "required_caps": (t.payload or {}).get("required_capabilities"),
        }
        for t in state.tasks.values()
    ]


@router.post("/agents/register", status_code=201)
async def register_agent(body: RegisterAgentRequest, request: Request) -> RegisterAgentResponse:
    state = _state(request)
    if state.registry.get(body.agent_id) is not None:
        raise HTTPException(status_code=409, detail="agent already registered")

    now = datetime.now(timezone.utc)
    agent = Agent(
        agent_id=body.agent_id,
        agent_type=body.agent_type,
        capabilities=body.capabilities,
        public_key=body.public_key,
        status="active",
        reputation=1.0,
        registered_at=now,
    )
    state.registry.register(agent)
    reg = state.signing_adapter.register_agent_key(body.agent_id, body.public_key)

    event = ev_factory.agent_registered(
        state.config.server_id,
        {
            "agent_id": body.agent_id,
            "agent_type": body.agent_type,
            "capabilities": body.capabilities,
            "key_id": reg.key_id,
            "public_key": body.public_key,
        },
    )
    written = state.dsm_writer.write(event)
    if written is None:
        raise HTTPException(status_code=500, detail="dsm_write_failed")
    await state.index_db.index_event(event, written.entry_hash)

    return RegisterAgentResponse(
        agent_id=body.agent_id,
        key_id=reg.key_id,
        registered_at=reg.registered_at,
        event_id=event["event_id"],
    )


@router.post("/missions", status_code=201)
async def create_mission(body: CreateMissionRequest, request: Request) -> CreateMissionResponse:
    state = _state(request)
    mission_id = str(ULID())
    created_at = _now_iso()

    event = ev_factory.mission_created(
        mission_id,
        state.config.server_id,
        {
            "mission_id": mission_id,
            "title": body.title,
            "description": body.description,
            "metadata": body.metadata,
        },
    )
    written = state.dsm_writer.write(event)
    if written is None:
        raise HTTPException(status_code=500, detail="dsm_write_failed")
    await state.index_db.index_event(event, written.entry_hash)
    await state.index_db.create_mission(mission_id, created_at)

    state.missions[mission_id] = {
        "mission_id": mission_id,
        "title": body.title,
        "description": body.description,
        "status": "open",
        "created_at": created_at,
    }
    return CreateMissionResponse(mission_id=mission_id, event_id=event["event_id"], created_at=created_at)


@router.post("/tasks", status_code=201)
async def create_task(body: CreateTaskRequest, request: Request) -> CreateTaskResponse:
    state = _state(request)
    if body.mission_id not in state.missions:
        raise HTTPException(status_code=404, detail="mission not found")

    task_id = str(ULID())
    now = datetime.now(timezone.utc)
    task = Task(
        task_id=task_id,
        mission_id=body.mission_id,
        task_type=body.task_type,
        payload=body.payload,
        status="pending",
        created_at=now,
    )
    state.tasks[task_id] = task

    created_event = ev_factory.task_created(
        body.mission_id,
        state.config.server_id,
        {
            "task_id": task_id,
            "mission_id": body.mission_id,
            "task_type": body.task_type,
            "payload": body.payload,
        },
    )
    written = state.dsm_writer.write(created_event)
    if written is None:
        raise HTTPException(status_code=500, detail="dsm_write_failed")
    await state.index_db.index_event(created_event, written.entry_hash)

    assigned_to = state.scheduler.assign_task(task, state.registry)
    if assigned_to is None:
        raise HTTPException(status_code=503, detail="no_capable_agent_available")

    task = task.model_copy(
        update={"assigned_to": assigned_to, "status": "assigned", "assigned_at": datetime.now(timezone.utc)}
    )
    state.tasks[task_id] = task

    assigned_event = ev_factory.task_assigned(
        body.mission_id,
        state.config.server_id,
        {
            "task_id": task_id,
            "mission_id": body.mission_id,
            "assigned_to": assigned_to,
        },
        parent_event_id=created_event["event_id"],
    )
    written2 = state.dsm_writer.write(assigned_event)
    if written2 is None:
        raise HTTPException(status_code=500, detail="dsm_write_failed")
    await state.index_db.index_event(assigned_event, written2.entry_hash)

    return CreateTaskResponse(
        task_id=task_id,
        mission_id=body.mission_id,
        event_id=assigned_event["event_id"],
        assigned_to=assigned_to,
    )


@router.get("/tasks/next")
async def get_next_task(
    request: Request,
    agent_id: str = Query(...),
    capabilities: str = Query(...),
) -> Response:
    state = _state(request)
    caps = [c.strip() for c in capabilities.split(",") if c.strip()]
    state.scheduler.set_tasks_source(state.tasks)
    tr = state.scheduler.next_for_agent(agent_id, caps)
    if tr is None:
        return Response(status_code=204)
    return JSONResponse(
        status_code=200,
        content={
            "task_id": tr.task_id,
            "mission_id": tr.mission_id,
            "task_type": tr.task_type,
            "objective": tr.objective,
            "constraints": tr.constraints,
        },
    )


@router.post("/tasks/{task_id}/result", status_code=201)
async def submit_task_result(
    task_id: str, body: SubmitTaskResultRequest, request: Request
) -> SubmitTaskResultResponse:
    state = _state(request)
    task = state.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    key_id = state.signing_adapter._key_ids.get(body.agent_id)
    if key_id is None:
        raise HTTPException(status_code=422, detail="agent_unknown")

    content_hash = compute_content_hash(body.content)
    canonical_payload = {
        "schema_version": "signing.v1",
        "agent_id": body.agent_id,
        "key_id": key_id,
        "mission_id": task.mission_id,
        "task_id": task_id,
        "contribution_id": body.contribution_id,
        "contribution_type": "task_result",
        "content_hash": content_hash,
        "created_at": body.created_at,
    }

    verify = state.signing_adapter.verify_contribution(body.agent_id, canonical_payload, body.signature)
    if not verify.valid:
        raise HTTPException(status_code=422, detail=f"signature_invalid:{verify.reason}")

    # If the submission envelope carried an explicit key_id, cross-check it
    # against the one the registry actually has on file for this agent.
    if body.key_id is not None and body.key_id != key_id:
        raise HTTPException(status_code=422, detail="key_id_mismatch")

    # Build event
    event_payload = {
        "task_id": task_id,
        "mission_id": task.mission_id,
        "agent_id": body.agent_id,
        "contribution_id": body.contribution_id,
        "content_hash": content_hash,
        "signature": body.signature,
        "self_reported_confidence": body.self_reported_confidence,
        "created_at": body.created_at,
        "content": body.content,
    }
    if body.payload_hash is not None:
        event_payload["payload_hash"] = body.payload_hash

    event = ev_factory.task_result_submitted(
        task.mission_id,
        state.config.server_id,
        body.agent_id,
        event_payload,
    )

    # Propagate the verification result into the event's auth block BEFORE the
    # writer persists it. The factory returned the event with the default
    # (all-false) auth block; the route is the authoritative layer that knows
    # the signature was just successfully verified, so it owns this update.
    event["auth"] = {
        "transport_authenticated": False,
        "signature_present": True,
        "signature_verified": True,
        "key_id": key_id,
        "signature_algorithm": "ed25519",
    }

    written = state.dsm_writer.write(event)
    if written is None:
        raise HTTPException(status_code=500, detail="dsm_write_failed")

    await state.index_db.index_event(event, written.entry_hash)
    receipt = state.exchange_adapter.issue_receipt(written, body.agent_id, task_id, task.mission_id)

    task = task.model_copy(update={"status": "completed", "result": body.content})
    state.tasks[task_id] = task

    return SubmitTaskResultResponse(
        task_id=task_id,
        event_id=event["event_id"],
        receipt_id=receipt["receipt_id"],
        entry_hash=written.entry_hash,
    )


# ---------- Bridge ----------


@router.get("/bridge/context", tags=["bridge"])
async def get_context(
    request: Request,
    consumer_agent_id: str = Query(...),
    scope: str = Query(...),
    limit: int = Query(20),
):
    import dataclasses

    state = _state(request)

    if state.context_builder is None:
        raise HTTPException(
            status_code=500,
            detail="ContextBuilder not initialized — check server startup logs",
        )

    if scope.startswith("mission:"):
        mission_id = scope.split(":", 1)[1]
        mission = await state.index_db.get_mission(mission_id)
        if mission is None and mission_id not in state.missions:
            raise HTTPException(status_code=404, detail="mission_not_found")
    elif scope.startswith("agent:"):
        agent_id = scope.split(":", 1)[1]
        if state.registry.get(agent_id) is None:
            raise HTTPException(status_code=404, detail="agent_not_found")

    query = ContextQuery(
        consumer_agent_id=consumer_agent_id,
        scope=scope,
        limit=limit,
    )
    context_pack = await state.context_builder.build(query)

    event = ev_factory.context_pack_issued(
        context_id=context_pack.context_id,
        agent_id=consumer_agent_id,
        scope=scope,
        source_event_ids=context_pack.source_event_ids,
        server_id=state.config.server_id,
    )
    written = state.dsm_writer.write(event)
    if written is None:
        raise HTTPException(status_code=500, detail="dsm_write_failed")
    await state.index_db.index_event(event, written.entry_hash)

    context_pack.dsm_event_id = event["event_id"]

    return JSONResponse(content=dataclasses.asdict(context_pack))
