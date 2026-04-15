"""Shared test fixtures."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agent_mesh.adapters.daryl_adapter.signing import generate_keypair
from agent_mesh.config import Config
from agent_mesh.server.app import create_app


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def config(tmp_data_dir: Path) -> Config:
    os.environ["AGENT_MESH_DATA_DIR"] = str(tmp_data_dir)
    return Config(data_dir=tmp_data_dir, server_id="server_test", log_level="INFO")


@pytest_asyncio.fixture
async def app(config: Config):
    app = create_app(config)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as _client:
        # enter lifespan via a dummy request? The lifespan isn't triggered by ASGITransport alone;
        # use LifespanManager via asgi-lifespan if available, otherwise trigger manually.
        yield app


@pytest_asyncio.fixture
async def client(config: Config):
    app = create_app(config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Manually trigger lifespan
        async with LifespanContext(app):
            yield c


class LifespanContext:
    def __init__(self, app):
        self.app = app
        self._shutdown = None

    async def __aenter__(self):
        import asyncio

        self._queue_in = asyncio.Queue()
        self._queue_out = asyncio.Queue()
        self._startup_complete = asyncio.Event()
        self._shutdown_complete = asyncio.Event()

        async def receive():
            return await self._queue_in.get()

        async def send(message):
            if message["type"] == "lifespan.startup.complete":
                self._startup_complete.set()
            elif message["type"] == "lifespan.shutdown.complete":
                self._shutdown_complete.set()
            await self._queue_out.put(message)

        self._task = asyncio.create_task(self.app({"type": "lifespan"}, receive, send))
        await self._queue_in.put({"type": "lifespan.startup"})
        await self._startup_complete.wait()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._queue_in.put({"type": "lifespan.shutdown"})
        await self._shutdown_complete.wait()
        await self._task


@pytest.fixture
def keypair():
    return generate_keypair()


@pytest_asyncio.fixture
async def registered_client(client, keypair):
    sk, pk = keypair
    resp = await client.post(
        "/agents/register",
        json={
            "agent_id": "agent_test_1",
            "agent_type": "worker",
            "capabilities": ["analyze"],
            "public_key": pk,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    yield {
        "client": client,
        "agent_id": "agent_test_1",
        "key_id": data["key_id"],
        "private_key": sk,
        "public_key": pk,
    }
