"""Tests for the bridge module — DSMContextReader, MeshStateReader, ContextBuilder, factory, route."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agent_mesh.bridge.context_builder import ContextBuilder
from agent_mesh.bridge.dsm_reader import DSMContextReader
from agent_mesh.bridge.mesh_reader import MeshStateReader
from agent_mesh.bridge.models import ContextFact, ContextPack, ContextQuery, LiveState, ProvenMemory
from agent_mesh.config import Config
from agent_mesh.dsm import factory as ev_factory
from agent_mesh.dsm.event import build_event
from agent_mesh.index.db import IndexDB
from agent_mesh.registry.agent_registry import AgentRegistry
from agent_mesh.server.app import create_app


class LifespanContext:
    def __init__(self, app):
        self.app = app

    async def __aenter__(self):
        import asyncio
        self._startup_complete = asyncio.Event()
        self._shutdown_complete = asyncio.Event()
        self._queue_in = asyncio.Queue()

        async def receive():
            return await self._queue_in.get()

        async def send(message):
            if message["type"] == "lifespan.startup.complete":
                self._startup_complete.set()
            elif message["type"] == "lifespan.shutdown.complete":
                self._shutdown_complete.set()

        self._task = asyncio.create_task(self.app({"type": "lifespan"}, receive, send))
        await self._queue_in.put({"type": "lifespan.startup"})
        await self._startup_complete.wait()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._queue_in.put({"type": "lifespan.shutdown"})
        await self._shutdown_complete.wait()
        await self._task


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest_asyncio.fixture
async def index_db(tmp_data_dir: Path) -> IndexDB:
    db = IndexDB(tmp_data_dir)
    await db.init()
    yield db
    await db.close()


async def _insert_event(index_db: IndexDB, event: dict) -> None:
    await index_db.index_event(event, f"hash_{event['event_id']}")


def _make_event(
    event_type: str,
    scope_id: str,
    source_id: str = "server_test",
    payload: dict | None = None,
) -> dict:
    return build_event(
        event_type=event_type,
        event_version="1.0",
        scope_type="mission" if scope_id.startswith("mission_") else "system",
        scope_id=scope_id,
        source_type="agent" if not source_id.startswith("server") else "server",
        source_id=source_id,
        writer_type="server",
        writer_id="server_test",
        payload=payload or {},
    )


def _make_submission_event(
    scope_id: str,
    agent_id: str,
    text: str = "some output",
) -> dict:
    return _make_event(
        "task_result_submitted",
        scope_id,
        source_id=agent_id,
        payload={
            "agent_id": agent_id,
            "content": {"text": text, "agent_id": agent_id},
            "task_id": "task_1",
            "mission_id": scope_id.replace("mission_", ""),
        },
    )


# ── DSMContextReader ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dsm_reader_filters_mission_scope(index_db):
    ev1 = _make_event("task_created", "mission_M1")
    ev2 = _make_event("task_created", "mission_M2")
    await _insert_event(index_db, ev1)
    await _insert_event(index_db, ev2)

    reader = DSMContextReader(index_db)
    results = await reader.fetch_events("mission:M1", limit=10)
    assert all(r["scope_id"] == "mission_M1" for r in results)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_dsm_reader_filters_agent_scope(index_db):
    ev1 = _make_event("task_result_submitted", "mission_M1", source_id="agent_A")
    ev2 = _make_event("task_result_submitted", "mission_M1", source_id="agent_B")
    await _insert_event(index_db, ev1)
    await _insert_event(index_db, ev2)

    reader = DSMContextReader(index_db)
    results = await reader.fetch_events("agent:agent_A", limit=10)
    assert all(r["source_id"] == "agent_A" for r in results)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_dsm_reader_unknown_scope_returns_recent(index_db):
    ev1 = _make_event("server_started", "system.server.lifecycle")
    ev2 = _make_event("task_created", "mission_M1")
    await _insert_event(index_db, ev1)
    await _insert_event(index_db, ev2)

    reader = DSMContextReader(index_db)
    results = await reader.fetch_events("system", limit=10)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_dsm_reader_returns_newest_first(index_db):
    import time
    ev1 = _make_event("task_created", "mission_M1")
    time.sleep(0.01)
    ev2 = _make_event("task_assigned", "mission_M1")
    await _insert_event(index_db, ev1)
    await _insert_event(index_db, ev2)

    reader = DSMContextReader(index_db)
    results = await reader.fetch_events("mission:M1", limit=10)
    assert len(results) == 2
    assert results[0]["timestamp"] >= results[1]["timestamp"]


@pytest.mark.asyncio
async def test_dsm_reader_respects_limit(index_db):
    for i in range(5):
        await _insert_event(index_db, _make_event("task_created", "mission_M1"))

    reader = DSMContextReader(index_db)
    results = await reader.fetch_events("mission:M1", limit=3)
    assert len(results) == 3


# ── MeshStateReader ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mesh_reader_counts_open_tasks(index_db):
    await index_db.create_mission("M1")
    await _insert_event(index_db, _make_event("task_created", "mission_M1"))
    await _insert_event(index_db, _make_event("task_created", "mission_M1"))
    await _insert_event(index_db, _make_submission_event("mission_M1", "agent_A"))

    reader = MeshStateReader(AgentRegistry(), index_db)
    state = await reader.get_state("mission:M1")
    assert state["open_tasks"] == 1


@pytest.mark.asyncio
async def test_mesh_reader_extracts_assigned_agents(index_db):
    await index_db.create_mission("M1")
    ev = _make_event(
        "task_assigned", "mission_M1",
        payload={"assigned_to": "agent_A", "task_id": "t1", "mission_id": "M1"},
    )
    await _insert_event(index_db, ev)

    reader = MeshStateReader(AgentRegistry(), index_db)
    state = await reader.get_state("mission:M1")
    assert "agent_A" in state["assigned_agents"]


@pytest.mark.asyncio
async def test_mesh_reader_status_open_when_no_close(index_db):
    await index_db.create_mission("M1")

    reader = MeshStateReader(AgentRegistry(), index_db)
    state = await reader.get_state("mission:M1")
    assert state["status"] == "open"


@pytest.mark.asyncio
async def test_mesh_reader_status_closed_when_mission_closed(index_db):
    await index_db.create_mission("M1")
    await index_db.close_mission("M1")

    reader = MeshStateReader(AgentRegistry(), index_db)
    state = await reader.get_state("mission:M1")
    assert state["status"] == "closed"


@pytest.mark.asyncio
async def test_mesh_reader_unknown_scope_returns_defaults(index_db):
    reader = MeshStateReader(AgentRegistry(), index_db)
    state = await reader.get_state("system")
    assert state["mission_id"] is None
    assert state["open_tasks"] == 0
    assert state["assigned_agents"] == []
    assert state["status"] == "unknown"


# ── ContextBuilder ────────────────────────────────────────────────────────────


def _mock_readers(events: list[dict] | None = None, state: dict | None = None):
    dsm_reader = AsyncMock(spec=DSMContextReader)
    dsm_reader.fetch_events = AsyncMock(return_value=events or [])
    mesh_reader = AsyncMock(spec=MeshStateReader)
    mesh_reader.get_state = AsyncMock(return_value=state or {
        "mission_id": None,
        "open_tasks": 0,
        "assigned_agents": [],
        "status": "unknown",
    })
    return dsm_reader, mesh_reader


@pytest.mark.asyncio
async def test_context_builder_empty_returns_no_activity():
    dr, mr = _mock_readers(events=[])
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "system"))
    assert pack.proven_memory.summary == "No recent activity."
    assert pack.proven_memory.facts == []


@pytest.mark.asyncio
async def test_context_builder_extracts_facts_from_submissions():
    ev = _make_submission_event("mission_M1", "agent_A", text="hello world")
    dr, mr = _mock_readers(events=[ev])
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "mission:M1"))
    assert len(pack.proven_memory.facts) == 1
    assert pack.proven_memory.facts[0].type == "submission"


@pytest.mark.asyncio
async def test_context_builder_facts_include_agent_id():
    ev = _make_submission_event("mission_M1", "agent_A")
    dr, mr = _mock_readers(events=[ev])
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "mission:M1"))
    assert pack.proven_memory.facts[0].agent_id == "agent_A"


@pytest.mark.asyncio
async def test_context_builder_truncates_content_to_200():
    long_text = "x" * 500
    ev = _make_submission_event("mission_M1", "agent_A", text=long_text)
    dr, mr = _mock_readers(events=[ev])
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "mission:M1"))
    assert len(pack.proven_memory.facts[0].text) == 200


@pytest.mark.asyncio
async def test_context_builder_context_id_has_ctx_prefix():
    dr, mr = _mock_readers()
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "system"))
    assert pack.context_id.startswith("ctx_")


@pytest.mark.asyncio
async def test_context_builder_summary_counts_unique_agents():
    ev1 = _make_submission_event("mission_M1", "agent_A", text="a")
    ev2 = _make_submission_event("mission_M1", "agent_B", text="b")
    ev3 = _make_submission_event("mission_M1", "agent_A", text="c")
    dr, mr = _mock_readers(events=[ev1, ev2, ev3])
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "mission:M1"))
    assert pack.proven_memory.summary == "3 submissions from 2 agents."


@pytest.mark.asyncio
async def test_context_builder_dsm_event_id_none_before_write():
    dr, mr = _mock_readers()
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "system"))
    assert pack.dsm_event_id is None


@pytest.mark.asyncio
async def test_context_builder_source_event_ids_is_master_list():
    ev1 = _make_submission_event("mission_M1", "agent_A")
    ev2 = _make_event("task_created", "mission_M1")
    dr, mr = _mock_readers(events=[ev1, ev2])
    cb = ContextBuilder(dr, mr)
    pack = await cb.build(ContextQuery("agent_X", "mission:M1"))
    assert ev1["event_id"] in pack.source_event_ids
    assert ev2["event_id"] in pack.source_event_ids
    assert len(pack.source_event_ids) == 2


# ── Factory ───────────────────────────────────────────────────────────────────


def test_factory_context_pack_issued_mission_scope():
    ev = ev_factory.context_pack_issued(
        context_id="ctx_TEST", agent_id="agent_A", scope="mission:M1",
        source_event_ids=["e1"], server_id="srv",
    )
    assert ev["event_type"] == "context_pack_issued"
    assert ev["scope_type"] == "mission"
    assert ev["scope_id"] == "mission_M1"


def test_factory_context_pack_issued_agent_scope():
    ev = ev_factory.context_pack_issued(
        context_id="ctx_TEST", agent_id="agent_A", scope="agent:agent_B",
        source_event_ids=["e1"], server_id="srv",
    )
    assert ev["scope_type"] == "system"
    assert ev["scope_id"] == "system.agent_context"


def test_factory_context_pack_issued_system_scope():
    ev = ev_factory.context_pack_issued(
        context_id="ctx_TEST", agent_id="agent_A", scope="system",
        source_event_ids=["e1"], server_id="srv",
    )
    assert ev["scope_type"] == "system"
    assert ev["scope_id"] == "system.context"


def test_factory_context_pack_issued_payload_has_dsm_event_id():
    ev = ev_factory.context_pack_issued(
        context_id="ctx_TEST", agent_id="agent_A", scope="system",
        source_event_ids=["e1"], server_id="srv", dsm_event_id="DSM_123",
    )
    assert ev["payload"]["dsm_event_id"] == "DSM_123"


# ── Route integration ─────────────────────────────────────────────────────────

import os

@pytest_asyncio.fixture
async def bridge_client(tmp_data_dir: Path):
    os.environ["AGENT_MESH_DATA_DIR"] = str(tmp_data_dir)
    cfg = Config(data_dir=tmp_data_dir, server_id="server_test", log_level="INFO")
    app = create_app(cfg)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with LifespanContext(app):
            yield c


async def _setup_mission(client: AsyncClient, agent_id: str = "agent_test") -> tuple[str, str]:
    """Register an agent and create a mission, return (mission_id, agent_id)."""
    from agent_mesh.adapters.daryl_adapter.signing import generate_keypair
    sk, pk = generate_keypair()
    r = await client.post("/agents/register", json={
        "agent_id": agent_id, "agent_type": "worker",
        "capabilities": ["test"], "public_key": pk,
    })
    assert r.status_code == 201, r.text

    r = await client.post("/missions", json={"title": "Test Mission", "description": "test"})
    assert r.status_code == 201, r.text
    return r.json()["mission_id"], agent_id


@pytest.mark.asyncio
async def test_route_get_context_returns_200(bridge_client):
    mission_id, agent_id = await _setup_mission(bridge_client)
    r = await bridge_client.get(
        "/bridge/context",
        params={"consumer_agent_id": agent_id, "scope": f"mission:{mission_id}"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_route_get_context_404_unknown_mission(bridge_client):
    r = await bridge_client.get(
        "/bridge/context",
        params={"consumer_agent_id": "agent_X", "scope": "mission:NONEXISTENT"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_route_get_context_404_unknown_agent(bridge_client):
    r = await bridge_client.get(
        "/bridge/context",
        params={"consumer_agent_id": "agent_X", "scope": "agent:NONEXISTENT"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_route_get_context_writes_dsm_event(bridge_client):
    mission_id, agent_id = await _setup_mission(bridge_client)
    r = await bridge_client.get(
        "/bridge/context",
        params={"consumer_agent_id": agent_id, "scope": f"mission:{mission_id}"},
    )
    data = r.json()
    assert data["dsm_event_id"] is not None


@pytest.mark.asyncio
async def test_route_get_context_response_has_dsm_event_id(bridge_client):
    mission_id, agent_id = await _setup_mission(bridge_client)
    r = await bridge_client.get(
        "/bridge/context",
        params={"consumer_agent_id": agent_id, "scope": f"mission:{mission_id}"},
    )
    data = r.json()
    assert "dsm_event_id" in data
    assert data["dsm_event_id"] is not None
    assert data["context_id"].startswith("ctx_")


@pytest.mark.asyncio
async def test_route_get_context_dsm_event_id_links_to_written_entry(bridge_client):
    mission_id, agent_id = await _setup_mission(bridge_client)
    r = await bridge_client.get(
        "/bridge/context",
        params={"consumer_agent_id": agent_id, "scope": f"mission:{mission_id}"},
    )
    data = r.json()
    dsm_event_id = data["dsm_event_id"]
    assert dsm_event_id is not None
    assert len(dsm_event_id) == 26  # ULID length
