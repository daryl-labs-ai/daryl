"""Tests for IndexDB."""
from __future__ import annotations

import pytest

from agent_mesh.dsm import factory as ev_factory
from agent_mesh.index.db import IndexDB


@pytest.mark.asyncio
async def test_init_and_close(tmp_path):
    db = IndexDB(tmp_path)
    await db.init()
    await db.close()


@pytest.mark.asyncio
async def test_index_and_get_event(tmp_path):
    db = IndexDB(tmp_path)
    await db.init()
    ev = ev_factory.server_started("s1", {"server_id": "s1"})
    await db.index_event(ev, "abc123")
    got = await db.get_event(ev["event_id"])
    assert got is not None
    assert got["entry_hash"] == "abc123"
    assert got["event_type"] == "server_started"
    await db.close()


@pytest.mark.asyncio
async def test_get_event_missing(tmp_path):
    db = IndexDB(tmp_path)
    await db.init()
    assert await db.get_event("missing") is None
    await db.close()


@pytest.mark.asyncio
async def test_create_and_close_mission(tmp_path):
    db = IndexDB(tmp_path)
    await db.init()
    await db.create_mission("m1", "2026-04-14T00:00:00Z")
    m = await db.get_mission("m1")
    assert m["status"] == "open"
    await db.close_mission("m1", "2026-04-14T01:00:00Z")
    m2 = await db.get_mission("m1")
    assert m2["status"] == "closed"
    await db.close()


@pytest.mark.asyncio
async def test_update_agent_runtime(tmp_path):
    db = IndexDB(tmp_path)
    await db.init()
    await db.update_agent_runtime("a1", "2026-04-14T00:00:00Z", "active", None)
    await db.close()
