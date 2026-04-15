"""Regression tests for the `workers.protocol.MeshWorker` submission path.

These tests pin three invariants that broke the V0 server contract until today:

  1. `sign_result()` signs with `contribution_type = "task_result"` (literal),
     NOT the task's own `task_type`. The server rebuilds the canonical payload
     with the literal — any other value makes the signature mismatch.

  2. `sign_result()` computes `content_hash` from the CANONICALIZED content
     DICT, matching what the server's `compute_content_hash(body.content)` call
     produces. Hashing the raw string breaks verification.

  3. `submit()` POSTs the exact V0 schema shape (`agent_id`, `contribution_id`,
     `content`, `self_reported_confidence`, `signature`, `created_at`, plus the
     optional `key_id` / `payload_hash` envelope fields). The legacy shape
     (`result_type`, `answer.full`, `meta.agent_id`, …) is pydantic-422 bait.

A fourth end-to-end test drives a standard `MeshWorker` subclass through a
real `TestClient` against the real `/tasks/{id}/result` route and checks that
the persisted event carries `auth.signature_verified == true`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent_mesh.config import Config  # noqa: E402
from agent_mesh.server.app import create_app  # noqa: E402
from workers.protocol import (  # noqa: E402
    MeshWorker,
    SignedResult,
    Task,
    WorkerConfig,
    _canonical,
    generate_keypair,
)


# ── Fake MeshWorker subclass (returns a fixed string) ────────────────────────


class _FakeMeshWorker(MeshWorker):
    def __init__(self, config: WorkerConfig, response: str = "fake answer"):
        super().__init__(config)
        self._response = response

    def call_llm(self, objective: str, constraints: dict) -> str:  # noqa: D401
        return self._response


def _build_worker(agent_id: str = "w_proto", caps=None):
    sk, pk = generate_keypair()
    return _FakeMeshWorker(
        WorkerConfig(
            agent_id=agent_id,
            capabilities=caps or ["analyze"],
            server_url="http://test",
            private_key_b64=sk,
            public_key_b64=pk,
            key_id=f"key_{agent_id}",
            poll_interval_s=0.01,
        )
    ), sk, pk


def _fake_task() -> Task:
    return Task(
        task_id="task_abc",
        mission_id="mission_xyz",
        task_type="analysis",
        objective="anything",
        constraints={},
    )


# ── Unit tests on sign_result ────────────────────────────────────────────────


def test_sign_result_uses_contribution_type_literal():
    """The signable's contribution_type must be the LITERAL 'task_result',
    never the task's task_type — otherwise the server rebuild won't match."""
    worker, _sk, _pk = _build_worker()
    task = _fake_task()
    signed = worker.sign_result(task, "hello", "contrib_1")

    # We can't read the signable directly (it's hashed), but we can rebuild it
    # with the known-good literal and check the signature verifies. If the
    # literal ever regresses back to task.task_type="analysis", verification
    # against this expected signable will fail.
    from workers.protocol import _sign  # noqa: PLC0415

    expected = {
        "schema_version": "signing.v1",
        "agent_id": worker.config.agent_id,
        "key_id": worker.config.key_id,
        "mission_id": task.mission_id,
        "task_id": task.task_id,
        "contribution_id": "contrib_1",
        "contribution_type": "task_result",
        "content_hash": signed.content_hash,
        "created_at": signed.created_at,
    }
    expected_sig = _sign(_canonical(expected), worker.config.private_key_b64)
    assert signed.signature == expected_sig


def test_sign_result_content_hash_is_over_canonical_dict():
    """content_hash must hash the canonicalized dict bytes, not the raw string."""
    worker, _sk, _pk = _build_worker()
    task = _fake_task()
    signed = worker.sign_result(task, "hello world", "c_h")

    from agent_mesh.adapters.daryl_adapter.signing import compute_content_hash

    expected_dict = {"text": "hello world", "agent_id": worker.config.agent_id}
    assert signed.content_hash == compute_content_hash(expected_dict)
    assert signed.content_dict == expected_dict


def test_sign_result_carries_created_at_for_submit():
    """SignedResult must expose the exact created_at used inside the signable,
    otherwise submit() cannot echo it back to the server."""
    worker, _sk, _pk = _build_worker()
    signed = worker.sign_result(_fake_task(), "content", "c_ts")
    assert signed.created_at  # non-empty
    assert signed.created_at.endswith("Z")


# ── Unit test on submit() payload shape ──────────────────────────────────────


class _CapturingClient:
    """Captures the last POST to emulate httpx.Client."""

    def __init__(self) -> None:
        self.last_url: str | None = None
        self.last_json: dict | None = None

    def post(self, url: str, json: dict):
        self.last_url = url
        self.last_json = json
        return httpx.Response(201, json={"task_id": "task_abc"})


def test_submit_payload_shape_matches_v0_schema():
    """Every key required by `SubmitTaskResultRequest` must be present and
    typed correctly; legacy keys (`result_type`, `answer`, `meta`) must be gone.
    """
    worker, _sk, _pk = _build_worker()
    task = _fake_task()
    signed = worker.sign_result(task, "hi", "c_shape")

    cap = _CapturingClient()
    worker._client = cap  # type: ignore[assignment]

    ok = worker.submit(task, signed, "c_shape", self_reported_confidence=0.77)
    assert ok is True
    assert cap.last_url == f"/tasks/{task.task_id}/result"

    body = cap.last_json
    assert body is not None

    # Required V0 schema fields
    assert body["agent_id"] == worker.config.agent_id
    assert body["contribution_id"] == "c_shape"
    assert isinstance(body["content"], dict)
    assert body["content"] == signed.content_dict
    assert body["self_reported_confidence"] == 0.77
    assert body["signature"] == signed.signature
    assert body["created_at"] == signed.created_at

    # Optional-but-explicit V0 fields
    assert body["key_id"] == worker.config.key_id
    assert body["payload_hash"] == signed.payload_hash

    # Legacy keys that must no longer appear
    for legacy in ("result_type", "status", "answer", "meta"):
        assert legacy not in body, f"legacy key {legacy!r} leaked back into submit()"


def test_submit_payload_shape_validates_against_pydantic_schema():
    """Round-trip the actual body through the real pydantic schema."""
    from agent_mesh.server.schemas import SubmitTaskResultRequest

    worker, _sk, _pk = _build_worker()
    task = _fake_task()
    signed = worker.sign_result(task, "hi", "c_pyd")

    cap = _CapturingClient()
    worker._client = cap  # type: ignore[assignment]
    worker.submit(task, signed, "c_pyd")

    # This raises if any required field is missing or mis-typed
    parsed = SubmitTaskResultRequest.model_validate(cap.last_json)
    assert parsed.agent_id == worker.config.agent_id
    assert parsed.key_id == worker.config.key_id
    assert parsed.payload_hash == signed.payload_hash


# ── End-to-end: MeshWorker.submit() against the real server route ────────────


@pytest.fixture
def live_app(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config = Config(data_dir=data_dir, server_id="server_test_proto", log_level="INFO")
    app = create_app(config)
    with TestClient(app) as client:
        yield app, client, data_dir


def _read_events(data_dir, event_type: str | None = None) -> list[dict]:
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


def test_mesh_worker_submit_triggers_verified_auth_block(live_app):
    """Full round-trip: a standard MeshWorker signs and submits, the server
    verifies, and the persisted event's auth block reports signature_verified=true."""
    app, client, data_dir = live_app

    # 1. Register agent directly (mirror what e2e_mission does)
    worker, _sk, pk = _build_worker(agent_id="mw_e2e", caps=["analyze"])
    reg = client.post(
        "/agents/register",
        json={
            "agent_id": "mw_e2e",
            "agent_type": "test",
            "capabilities": ["analyze"],
            "public_key": pk,
        },
    )
    assert reg.status_code == 201, reg.text
    server_key_id = reg.json()["key_id"]
    worker.config.key_id = server_key_id  # adopt the server's key_id

    # 2. Create mission + task (create_task will auto-assign to our registered agent)
    m = client.post("/missions", json={"title": "t", "description": "d"})
    assert m.status_code == 201
    mission_id = m.json()["mission_id"]

    tcreate = client.post(
        "/tasks",
        json={"mission_id": mission_id, "task_type": "analyze", "payload": {}},
    )
    assert tcreate.status_code == 201
    task_id = tcreate.json()["task_id"]

    # 3. Drive the worker's own sign + submit path against the server route
    task = Task(
        task_id=task_id,
        mission_id=mission_id,
        task_type="analyze",
        objective="",
        constraints={},
    )
    signed = worker.sign_result(task, "mesh worker verified answer", "c_mw_e2e")

    # Reuse the TestClient transport instead of httpx.Client().
    worker._client = client
    ok = worker.submit(task, signed, "c_mw_e2e", self_reported_confidence=0.88)
    assert ok is True

    # 4. Inspect the persisted event — auth block must be populated
    events = _read_events(data_dir, event_type="task_result_submitted")
    assert len(events) >= 1
    ev = events[-1]
    auth = ev["auth"]
    assert auth["signature_present"] is True
    assert auth["signature_verified"] is True
    assert auth["key_id"] == server_key_id
    assert auth["signature_algorithm"] == "ed25519"
    assert ev["payload"]["agent_id"] == "mw_e2e"
    assert ev["payload"]["content_hash"] == signed.content_hash
    # The optional payload_hash we sent at the envelope level is echoed into
    # the event payload for auditability.
    assert ev["payload"]["payload_hash"] == signed.payload_hash
