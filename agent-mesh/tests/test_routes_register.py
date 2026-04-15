"""Tests for /agents/register."""
from __future__ import annotations

import pytest

from agent_mesh.adapters.daryl_adapter.signing import generate_keypair


@pytest.mark.asyncio
async def test_register_happy_path(client):
    _, pk = generate_keypair()
    resp = await client.post(
        "/agents/register",
        json={
            "agent_id": "a_happy",
            "agent_type": "worker",
            "capabilities": ["x"],
            "public_key": pk,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "a_happy"
    assert data["key_id"].startswith("key_")
    assert "event_id" in data


@pytest.mark.asyncio
async def test_register_duplicate_409(client):
    _, pk = generate_keypair()
    body = {
        "agent_id": "a_dup",
        "agent_type": "worker",
        "capabilities": ["x"],
        "public_key": pk,
    }
    r1 = await client.post("/agents/register", json=body)
    assert r1.status_code == 201
    r2 = await client.post("/agents/register", json=body)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_payload_422(client):
    resp = await client.post("/agents/register", json={"agent_id": "x"})
    assert resp.status_code == 422
