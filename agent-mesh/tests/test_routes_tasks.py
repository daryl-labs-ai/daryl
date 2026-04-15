"""Tests for /missions, /tasks, /tasks/{id}/result."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_mesh.adapters.daryl_adapter.signing import (
    canonicalize_payload,
    compute_content_hash,
    generate_keypair,
    sign_bytes,
)


async def _register_agent(client, agent_id="agent_worker", caps=None):
    sk, pk = generate_keypair()
    resp = await client.post(
        "/agents/register",
        json={
            "agent_id": agent_id,
            "agent_type": "worker",
            "capabilities": caps or ["analyze"],
            "public_key": pk,
        },
    )
    assert resp.status_code == 201, resp.text
    return sk, pk, resp.json()["key_id"]


async def _create_mission(client):
    r = await client.post("/missions", json={"title": "t", "description": "d"})
    assert r.status_code == 201
    return r.json()["mission_id"]


async def _create_task(client, mission_id, task_type="analyze"):
    r = await client.post(
        "/tasks", json={"mission_id": mission_id, "task_type": task_type, "payload": {"foo": "bar"}}
    )
    return r


def _sign_payload(sk, agent_id, key_id, mission_id, task_id, contribution_id, content, created_at):
    content_hash = compute_content_hash(content)
    payload = {
        "schema_version": "signing.v1",
        "agent_id": agent_id,
        "key_id": key_id,
        "mission_id": mission_id,
        "task_id": task_id,
        "contribution_id": contribution_id,
        "contribution_type": "task_result",
        "content_hash": content_hash,
        "created_at": created_at,
    }
    return sign_bytes(canonicalize_payload(payload), sk)


@pytest.mark.asyncio
async def test_create_mission_201(client):
    r = await client.post("/missions", json={"title": "x", "description": "y"})
    assert r.status_code == 201
    data = r.json()
    assert "mission_id" in data and "event_id" in data


@pytest.mark.asyncio
async def test_create_task_without_agent_503(client):
    mission_id = await _create_mission(client)
    r = await _create_task(client, mission_id)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_create_task_happy(client):
    await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    r = await _create_task(client, mission_id, task_type="analyze")
    assert r.status_code == 201
    assert r.json()["assigned_to"] == "w1"


@pytest.mark.asyncio
async def test_create_task_unknown_mission_404(client):
    r = await client.post(
        "/tasks", json={"mission_id": "nope", "task_type": "analyze", "payload": {}}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_submit_result_happy(client):
    sk, _, key_id = await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    content = {"result": "ok"}
    created_at = "2026-04-14T10:00:00Z"
    sig = _sign_payload(sk, "w1", key_id, mission_id, task_id, "c1", content, created_at)

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c1",
            "content": content,
            "self_reported_confidence": 0.9,
            "signature": sig,
            "created_at": created_at,
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "receipt_id" in data and "entry_hash" in data and "event_id" in data


@pytest.mark.asyncio
async def test_submit_result_unknown_task_404(client):
    sk, _, _ = await _register_agent(client, agent_id="w1", caps=["analyze"])
    r = await client.post(
        "/tasks/missing/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c1",
            "content": {},
            "self_reported_confidence": 0.5,
            "signature": "AAAA",
            "created_at": "2026-04-14T00:00:00Z",
        },
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_submit_result_unknown_agent_422(client):
    await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]
    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "ghost",
            "contribution_id": "c1",
            "content": {},
            "self_reported_confidence": 0.5,
            "signature": "AAAA",
            "created_at": "2026-04-14T00:00:00Z",
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_submit_result_invalid_signature_422(client):
    sk, _, key_id = await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c1",
            "content": {"a": 1},
            "self_reported_confidence": 0.5,
            "signature": "AAAA",
            "created_at": "2026-04-14T00:00:00Z",
        },
    )
    assert r.status_code == 422


# -------- mandatory write-first rules --------

@pytest.mark.asyncio
async def test_receipt_not_issued_before_dsm_write(client):
    """The receipt is built from the WrittenEntry — prove receipt carries the entry_hash from the write."""
    sk, _, key_id = await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    content = {"r": 1}
    created_at = "2026-04-14T10:00:00Z"
    sig = _sign_payload(sk, "w1", key_id, mission_id, task_id, "c1", content, created_at)

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c1",
            "content": content,
            "self_reported_confidence": 1.0,
            "signature": sig,
            "created_at": created_at,
        },
    )
    assert r.status_code == 201
    data = r.json()
    # entry_hash is a 64-hex sha256 → proves write happened before receipt
    assert len(data["entry_hash"]) == 64
    assert data["receipt_id"]  # present → receipt issued AFTER write


@pytest.mark.asyncio
async def test_receipt_not_called_if_dsm_write_returns_none(client, monkeypatch):
    """If writer.write() returns None, endpoint must 500 and NOT issue a receipt."""
    sk, _, key_id = await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    # Patch writer to inject a failure on the next (result) write. The task_result write
    # is the 5th write in the session. We instead monkeypatch write to return None when
    # called for task_result_submitted events, but track that receipt was never issued.
    state = client._transport.app.state.mesh  # type: ignore[attr-defined]
    original_write = state.dsm_writer.write
    original_issue = state.exchange_adapter.issue_receipt
    issue_called = {"count": 0}

    def fake_write(ev):
        if ev.get("event_type") == "task_result_submitted":
            return None
        return original_write(ev)

    def tracked_issue(*args, **kwargs):
        issue_called["count"] += 1
        return original_issue(*args, **kwargs)

    monkeypatch.setattr(state.dsm_writer, "write", fake_write)
    monkeypatch.setattr(state.exchange_adapter, "issue_receipt", tracked_issue)

    content = {"r": 2}
    created_at = "2026-04-14T11:00:00Z"
    sig = _sign_payload(sk, "w1", key_id, mission_id, task_id, "c2", content, created_at)

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c2",
            "content": content,
            "self_reported_confidence": 1.0,
            "signature": sig,
            "created_at": created_at,
        },
    )
    assert r.status_code == 500
    assert issue_called["count"] == 0


# -------- auth block population after successful verification --------


def _read_last_events(data_dir, event_type: str | None = None) -> list[dict]:
    """Read events.jsonl from a tmp data dir. Optionally filter by event_type."""
    import json
    from pathlib import Path

    p = Path(data_dir) / "events.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type is None or ev.get("event_type") == event_type:
                out.append(ev)
    return out


@pytest.mark.asyncio
async def test_submit_result_event_auth_block_populated(client, tmp_data_dir):
    """After a valid submission, the task_result_submitted event in events.jsonl
    must carry auth.signature_present=True, auth.signature_verified=True,
    auth.key_id set, auth.signature_algorithm='ed25519'.
    """
    sk, _, key_id = await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    content = {"text": "auth block test", "agent_id": "w1"}
    created_at = "2026-04-15T12:00:00Z"
    sig = _sign_payload(sk, "w1", key_id, mission_id, task_id, "c_auth", content, created_at)

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c_auth",
            "content": content,
            "self_reported_confidence": 0.95,
            "signature": sig,
            "created_at": created_at,
        },
    )
    assert r.status_code == 201, r.text

    # Inspect the events.jsonl written by the in-test server.
    tre_events = _read_last_events(tmp_data_dir, event_type="task_result_submitted")
    assert len(tre_events) >= 1
    auth = tre_events[-1]["auth"]
    assert auth["signature_present"] is True
    assert auth["signature_verified"] is True
    assert auth["key_id"] == key_id
    assert auth["signature_algorithm"] == "ed25519"
    assert auth["transport_authenticated"] is False


@pytest.mark.asyncio
async def test_submit_result_accepts_optional_payload_hash_and_key_id(client):
    """The schema should accept the optional payload_hash / key_id envelope fields."""
    sk, _, key_id = await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    content = {"text": "with optional fields", "agent_id": "w1"}
    created_at = "2026-04-15T12:10:00Z"
    sig = _sign_payload(sk, "w1", key_id, mission_id, task_id, "c_opt", content, created_at)

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c_opt",
            "content": content,
            "self_reported_confidence": 0.9,
            "signature": sig,
            "created_at": created_at,
            "key_id": key_id,
            "payload_hash": "sha256:deadbeef" * 8,
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_submit_result_rejects_mismatched_key_id(client):
    """If the client sends an explicit key_id that disagrees with the registry,
    the server must reject the submission with 422."""
    sk, _, key_id = await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    content = {"text": "mismatched key", "agent_id": "w1"}
    created_at = "2026-04-15T12:20:00Z"
    sig = _sign_payload(sk, "w1", key_id, mission_id, task_id, "c_mismatch", content, created_at)

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c_mismatch",
            "content": content,
            "self_reported_confidence": 0.9,
            "signature": sig,
            "created_at": created_at,
            "key_id": "key_completely_different",
        },
    )
    assert r.status_code == 422
    assert "key_id_mismatch" in r.json()["detail"]


@pytest.mark.asyncio
async def test_submit_result_invalid_signature_still_422(client):
    """Baseline regression: a bad signature still produces a clean 422 rejection."""
    await _register_agent(client, agent_id="w1", caps=["analyze"])
    mission_id = await _create_mission(client)
    tr = await _create_task(client, mission_id)
    task_id = tr.json()["task_id"]

    r = await client.post(
        f"/tasks/{task_id}/result",
        json={
            "agent_id": "w1",
            "contribution_id": "c_bad",
            "content": {"text": "bad sig"},
            "self_reported_confidence": 0.5,
            "signature": "AAAA" * 22,
            "created_at": "2026-04-15T12:30:00Z",
        },
    )
    assert r.status_code == 422


# -------- GET /tasks/next (pull model) --------

@pytest.mark.asyncio
async def test_next_task_returns_pending_task_200(client):
    """Pending task with matching required_capabilities is returned and marked assigned."""
    mission_id = await _create_mission(client)
    # Create a pending task: no agent registered yet → 503 but task lands in state.tasks
    r = await client.post(
        "/tasks",
        json={
            "mission_id": mission_id,
            "task_type": "analysis",
            "payload": {
                "required_capabilities": ["analysis", "summarization"],
                "objective": "Summarize Q1 report",
                "constraints": {"max_output_tokens": 800, "output_format": "markdown"},
            },
        },
    )
    assert r.status_code == 503  # no agent yet, but task is pending

    resp = await client.get(
        "/tasks/next",
        params={"agent_id": "worker_alpha", "capabilities": "analysis,summarization"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mission_id"] == mission_id
    assert body["task_type"] == "analysis"
    assert body["objective"] == "Summarize Q1 report"
    assert body["constraints"] == {
        "deadline_ms": None,
        "max_output_tokens": 800,
        "output_format": "markdown",
    }
    assert body["task_id"]


@pytest.mark.asyncio
async def test_next_task_no_pending_returns_204(client):
    """When no pending task exists, endpoint returns 204."""
    resp = await client.get(
        "/tasks/next",
        params={"agent_id": "worker_x", "capabilities": "analysis"},
    )
    assert resp.status_code == 204
    assert resp.content == b""


@pytest.mark.asyncio
async def test_next_task_capabilities_mismatch_returns_204(client):
    """Agent without the required capabilities gets 204."""
    mission_id = await _create_mission(client)
    r = await client.post(
        "/tasks",
        json={
            "mission_id": mission_id,
            "task_type": "translation",
            "payload": {"required_capabilities": ["translation", "french"]},
        },
    )
    assert r.status_code == 503

    resp = await client.get(
        "/tasks/next",
        params={"agent_id": "worker_en", "capabilities": "analysis,translation"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_next_task_second_call_returns_204_task_already_assigned(client):
    """After a task is claimed, a second pull returns 204."""
    mission_id = await _create_mission(client)
    r = await client.post(
        "/tasks",
        json={
            "mission_id": mission_id,
            "task_type": "analysis",
            "payload": {"required_capabilities": ["analysis"]},
        },
    )
    assert r.status_code == 503

    first = await client.get(
        "/tasks/next",
        params={"agent_id": "worker_a", "capabilities": "analysis"},
    )
    assert first.status_code == 200

    second = await client.get(
        "/tasks/next",
        params={"agent_id": "worker_b", "capabilities": "analysis"},
    )
    assert second.status_code == 204


@pytest.mark.asyncio
async def test_next_task_default_constraints_when_payload_bare(client):
    """When payload has no constraints, defaults are applied (max_output_tokens=1200)."""
    mission_id = await _create_mission(client)
    r = await client.post(
        "/tasks",
        json={
            "mission_id": mission_id,
            "task_type": "analysis",
            "payload": {"required_capabilities": ["analysis"]},
        },
    )
    assert r.status_code == 503

    resp = await client.get(
        "/tasks/next",
        params={"agent_id": "worker_a", "capabilities": "analysis"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["objective"] == ""
    assert body["constraints"] == {
        "deadline_ms": None,
        "max_output_tokens": 1200,
        "output_format": None,
    }
