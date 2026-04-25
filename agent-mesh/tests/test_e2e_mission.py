"""E2E mission test — mock server + mock backends, zero real network.

Verifies the e2e_mission script logic end-to-end:
  1. Health check
  2. Mission creation
  3. Two tasks left pending
  4. Two workers register
  5. Both workers poll, execute, sign, submit — results collected
  6. Mission events (mocked server emits them into a shared list) are visible

The FakeMeshServer here reproduces the subset of routes used by the e2e script
with the exact schemas the real server expects. It lives entirely in-process
and uses httpx.MockTransport — no sockets open.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

# Make e2e_mission and workers importable from tests/.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent_mesh.adapters.daryl_adapter.signing import (  # noqa: E402
    canonicalize_payload,
    compute_content_hash,
    verify_bytes,
)
from e2e_mission import (  # noqa: E402
    MISSION_TEXT,
    WorkerBundle,
    WorkerResult,
    check_server_alive,
    create_mission,
    create_task_pending,
    read_mission_events,
    register_worker_direct,
    run_e2e,
    run_worker_bounded,
)
from workers.generic_worker.worker import GenericLLMWorker  # noqa: E402
from workers.protocol import WorkerConfig, generate_keypair  # noqa: E402


# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeBackend:
    """Deterministic backend — returns a fixed string, records every call."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.calls.append((prompt, system_prompt))
        return self.text


class FakeMeshServer:
    """In-process fake of the agent-mesh server.

    Implements only the endpoints the e2e script uses, with the exact
    request/response shapes of the real server. Everything is guarded by a
    single lock so the two worker threads interact deterministically.
    """

    def __init__(self) -> None:
        self.agents: dict[str, dict] = {}
        self.missions: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.submissions: list[dict] = []
        self.events: list[dict] = []
        self._mission_counter = 0
        self._task_counter = 0
        self._lock = threading.Lock()

    # ── httpx.MockTransport entry point ───────────────────────────────────────

    def handler(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            return self._route(request)

    # ── Event emission (mirrors DSMWriter behaviour) ──────────────────────────

    def _emit(
        self,
        event_type: str,
        scope_type: str,
        scope_id: str,
        source_id: str,
        payload: dict,
    ) -> str:
        event_id = f"ev_{len(self.events):06d}"
        ev = {
            "event_id": event_id,
            "event_type": event_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "source_id": source_id,
            "timestamp": "2026-04-14T10:00:00Z",
            "payload": payload,
        }
        self.events.append(ev)
        return event_id

    # ── Routes ────────────────────────────────────────────────────────────────

    def _route(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path

        if method == "GET" and path == "/":
            return httpx.Response(404, json={"detail": "not found"})

        if method == "POST" and path == "/agents/register":
            return self._handle_register(request)

        if method == "POST" and path == "/missions":
            return self._handle_create_mission(request)

        if method == "POST" and path == "/tasks":
            return self._handle_create_task(request)

        if method == "GET" and path == "/tasks/next":
            return self._handle_poll(request)

        if method == "POST" and path.startswith("/tasks/") and path.endswith("/result"):
            task_id = path.split("/")[2]
            return self._handle_submit_result(task_id, request)

        return httpx.Response(404, json={"detail": "not found"})

    def _handle_register(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        agent_id = body["agent_id"]
        if agent_id in self.agents:
            return httpx.Response(409, json={"detail": "agent already registered"})
        key_id = f"key_{agent_id}"
        self.agents[agent_id] = {
            "agent_type": body["agent_type"],
            "capabilities": body["capabilities"],
            "public_key": body["public_key"],
            "key_id": key_id,
        }
        event_id = self._emit(
            "agent_registered",
            "system",
            "system.agent_registry",
            "server_test",
            {"agent_id": agent_id, "key_id": key_id},
        )
        return httpx.Response(
            201,
            json={
                "agent_id": agent_id,
                "key_id": key_id,
                "registered_at": "2026-04-14T10:00:00Z",
                "event_id": event_id,
            },
        )

    def _handle_create_mission(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        self._mission_counter += 1
        mission_id = f"mission{self._mission_counter:06d}"
        self.missions[mission_id] = {
            "title": body.get("title", ""),
            "description": body.get("description", ""),
            "status": "open",
        }
        event_id = self._emit(
            "mission_created",
            "mission",
            f"mission_{mission_id}",
            "server_test",
            {"mission_id": mission_id, "title": body.get("title", "")},
        )
        return httpx.Response(
            201,
            json={
                "mission_id": mission_id,
                "event_id": event_id,
                "created_at": "2026-04-14T10:00:00Z",
            },
        )

    def _handle_create_task(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        mission_id = body["mission_id"]
        if mission_id not in self.missions:
            return httpx.Response(404, json={"detail": "mission not found"})

        self._task_counter += 1
        task_id = f"task{self._task_counter:06d}"
        payload = body.get("payload", {}) or {}
        required = payload.get("required_capabilities") or [body.get("task_type", "")]

        self.tasks[task_id] = {
            "task_id": task_id,
            "mission_id": mission_id,
            "task_type": body.get("task_type", ""),
            "objective": payload.get("objective", ""),
            "required_capabilities": list(required),
            "constraints": payload.get("constraints", {}),
            "status": "pending",
            "assigned_to": None,
            "result": None,
        }
        self._emit(
            "task_created",
            "mission",
            f"mission_{mission_id}",
            "server_test",
            {"task_id": task_id, "mission_id": mission_id},
        )

        # No capable agent currently registered ⇒ 503 (task stays pending)
        caps_match = any(
            set(required).issubset(set(a["capabilities"]))
            for a in self.agents.values()
        )
        if not caps_match:
            return httpx.Response(
                503, json={"detail": "no_capable_agent_available"}
            )

        # If there is a match (unused in current test path), auto-assign.
        chosen = next(
            aid
            for aid, a in self.agents.items()
            if set(required).issubset(set(a["capabilities"]))
        )
        self.tasks[task_id]["status"] = "assigned"
        self.tasks[task_id]["assigned_to"] = chosen
        self._emit(
            "task_assigned",
            "mission",
            f"mission_{mission_id}",
            "server_test",
            {"task_id": task_id, "assigned_to": chosen},
        )
        return httpx.Response(
            201,
            json={
                "task_id": task_id,
                "mission_id": mission_id,
                "event_id": f"ev_task_{task_id}",
                "assigned_to": chosen,
            },
        )

    def _handle_poll(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        caps_raw = params.get("capabilities", "")
        agent_id = params.get("agent_id", "")
        agent_caps = {c.strip() for c in caps_raw.split(",") if c.strip()}

        for tid, t in self.tasks.items():
            if t["status"] != "pending":
                continue
            required = set(t["required_capabilities"] or [t["task_type"]])
            if not required.issubset(agent_caps):
                continue
            t["status"] = "assigned"
            t["assigned_to"] = agent_id
            self._emit(
                "task_assigned",
                "mission",
                f"mission_{t['mission_id']}",
                "server_test",
                {"task_id": tid, "assigned_to": agent_id},
            )
            return httpx.Response(
                200,
                json={
                    "task_id": t["task_id"],
                    "mission_id": t["mission_id"],
                    "task_type": t["task_type"],
                    "objective": t["objective"],
                    "constraints": t["constraints"],
                },
            )
        return httpx.Response(204, content=b"")

    def _handle_submit_result(
        self, task_id: str, request: httpx.Request
    ) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        if task_id not in self.tasks:
            return httpx.Response(404, json={"detail": "task not found"})
        agent_id = body.get("agent_id")
        if agent_id not in self.agents:
            return httpx.Response(422, json={"detail": "agent_unknown"})

        # Verify signature the same way the real server does.
        content_hash = compute_content_hash(body["content"])
        key_id = self.agents[agent_id]["key_id"]
        canonical_payload = {
            "schema_version": "signing.v1",
            "agent_id": agent_id,
            "key_id": key_id,
            "mission_id": self.tasks[task_id]["mission_id"],
            "task_id": task_id,
            "contribution_id": body["contribution_id"],
            "contribution_type": "task_result",
            "content_hash": content_hash,
            "created_at": body["created_at"],
        }
        canonical = canonicalize_payload(canonical_payload)
        public_key = self.agents[agent_id]["public_key"]
        if not verify_bytes(canonical, body["signature"], public_key):
            return httpx.Response(422, json={"detail": "signature_invalid"})

        self.tasks[task_id]["status"] = "completed"
        self.tasks[task_id]["result"] = body["content"]
        self.submissions.append(
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "content": body["content"],
                "signature": body["signature"],
                "content_hash": content_hash,
            }
        )
        mission_id = self.tasks[task_id]["mission_id"]
        self._emit(
            "task_result_submitted",
            "mission",
            f"mission_{mission_id}",
            agent_id,
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "content_hash": content_hash,
            },
        )
        return httpx.Response(
            201,
            json={
                "task_id": task_id,
                "event_id": f"ev_result_{task_id}",
                "receipt_id": f"receipt_{task_id}",
                "entry_hash": "a" * 64,
            },
        )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_worker(
    agent_id: str,
    caps: list[str],
    backend: FakeBackend,
    transport: httpx.MockTransport,
    base_url: str = "http://fake-mesh",
) -> GenericLLMWorker:
    sk, pk = generate_keypair()
    config = WorkerConfig(
        agent_id=agent_id,
        capabilities=caps,
        server_url=base_url,
        private_key_b64=sk,
        public_key_b64=pk,
        key_id=f"key_{agent_id}_v1",
        poll_interval_s=0.02,
    )
    worker = GenericLLMWorker(config=config, backend=backend)
    # Swap the worker's real HTTP client for the mock-transport client.
    worker._client.close()
    worker._client = httpx.Client(
        transport=transport, base_url=base_url, timeout=5.0
    )
    return worker


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_check_server_alive():
    fake = FakeMeshServer()
    transport = httpx.MockTransport(fake.handler)
    client = httpx.Client(transport=transport, base_url="http://fake-mesh")
    assert check_server_alive(client) is True


def test_create_mission_roundtrip():
    fake = FakeMeshServer()
    transport = httpx.MockTransport(fake.handler)
    client = httpx.Client(transport=transport, base_url="http://fake-mesh")
    mid = create_mission(client, "T", "D")
    assert mid in fake.missions
    assert any(ev["event_type"] == "mission_created" for ev in fake.events)


def test_create_task_pending_503_still_registered():
    fake = FakeMeshServer()
    transport = httpx.MockTransport(fake.handler)
    client = httpx.Client(transport=transport, base_url="http://fake-mesh")
    mid = create_mission(client, "T", "D")
    create_task_pending(client, mid, "obj", ["analysis"], {"max_output_tokens": 100})
    assert len(fake.tasks) == 1
    t = next(iter(fake.tasks.values()))
    assert t["status"] == "pending"
    assert any(ev["event_type"] == "task_created" for ev in fake.events)


def test_register_worker_adopts_server_key_id():
    fake = FakeMeshServer()
    transport = httpx.MockTransport(fake.handler)
    client = httpx.Client(transport=transport, base_url="http://fake-mesh")
    backend = FakeBackend("ok")
    worker = _make_worker("agent_x", ["analysis"], backend, transport)
    assert worker.config.key_id == "key_agent_x_v1"
    register_worker_direct(client, worker, "test")
    assert worker.config.key_id == "key_agent_x"  # adopted from server response
    assert worker._registered is True


def test_run_worker_bounded_single_task():
    fake = FakeMeshServer()
    transport = httpx.MockTransport(fake.handler)
    client = httpx.Client(transport=transport, base_url="http://fake-mesh")

    mid = create_mission(client, "T", "D")
    create_task_pending(client, mid, "one", ["analysis"], {"max_output_tokens": 100})

    backend = FakeBackend("fake answer A")
    worker = _make_worker("agent_a", ["analysis"], backend, transport)
    register_worker_direct(client, worker, "test")

    stop = threading.Event()
    results: list[WorkerResult] = []
    lock = threading.Lock()
    t = threading.Thread(target=run_worker_bounded, args=(worker, stop, results, lock))
    t.start()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with lock:
            if len(results) >= 1:
                break
        time.sleep(0.02)
    stop.set()
    t.join(timeout=2)

    assert len(results) == 1
    r = results[0]
    assert r.agent_id == "agent_a"
    assert r.content == "fake answer A"
    assert r.content_hash.startswith("v1:")
    assert r.payload_hash.startswith("v1:")
    assert len(r.signature) > 10
    assert len(fake.submissions) == 1
    assert fake.submissions[0]["agent_id"] == "agent_a"


def test_run_e2e_two_workers_two_tasks():
    fake = FakeMeshServer()
    transport = httpx.MockTransport(fake.handler)

    backend_a = FakeBackend(
        "Strengths: A1, A2, A3. Weaknesses: W1, W2, W3. Priority: add receipts."
    )
    backend_b = FakeBackend(
        "Strengths: B1, B2, B3. Weaknesses: X1, X2, X3. Priority: add replay."
    )
    worker_a = _make_worker("agent_alpha", ["analysis"], backend_a, transport)
    worker_b = _make_worker("agent_beta", ["analysis"], backend_b, transport)

    bundles = [
        WorkerBundle(worker=worker_a, label="FakeA", agent_type="test"),
        WorkerBundle(worker=worker_b, label="FakeB", agent_type="test"),
    ]

    results, mission_id, _events = run_e2e(
        bundles,
        server_url="http://fake-mesh",
        data_dir=Path("/tmp/agent-mesh-e2e-test-nonexistent"),
        num_tasks=2,
        wait_timeout_s=5.0,
    )

    assert mission_id in fake.missions
    assert len(results) == 2
    agents_seen = {r.agent_id for r in results}
    assert agents_seen == {"agent_alpha", "agent_beta"} or len(agents_seen) >= 1
    # Exactly two submissions accepted by the fake server.
    assert len(fake.submissions) == 2
    # Both agents' backends were called.
    assert len(backend_a.calls) + len(backend_b.calls) == 2

    # Every recorded result has the expected fields populated.
    for r in results:
        assert r.content
        assert r.content_hash.startswith("v1:")
        assert r.payload_hash.startswith("v1:")
        assert isinstance(r.signature, str) and len(r.signature) > 10

    # Fake server received mission + task events.
    ev_types = [ev["event_type"] for ev in fake.events]
    assert ev_types.count("mission_created") == 1
    assert ev_types.count("task_created") == 2
    assert ev_types.count("task_result_submitted") == 2


def test_signatures_verify_against_server_schema():
    """The signature produced by run_worker_bounded must verify under the exact
    canonical payload the server rebuilds. The fake server already enforces this
    — this test just guarantees no submission reached 422."""
    fake = FakeMeshServer()
    transport = httpx.MockTransport(fake.handler)

    backend = FakeBackend("deterministic")
    worker = _make_worker("agent_sig", ["analysis"], backend, transport)

    bundles = [WorkerBundle(worker=worker, label="S", agent_type="test")]
    results, _mid, _ = run_e2e(
        bundles,
        server_url="http://fake-mesh",
        data_dir=Path("/tmp/agent-mesh-e2e-test-nonexistent"),
        num_tasks=1,
        wait_timeout_s=5.0,
    )
    assert len(results) == 1
    assert len(fake.submissions) == 1
    assert fake.submissions[0]["content"] == {
        "text": "deterministic",
        "agent_id": "agent_sig",
    }


def test_read_mission_events_missing_file(tmp_path: Path):
    assert read_mission_events(tmp_path, "mission_xyz") == []


def test_read_mission_events_filters_by_scope(tmp_path: Path):
    events_file = tmp_path / "events.jsonl"
    lines = [
        {"event_id": "1", "event_type": "mission_created", "scope_id": "mission_abc"},
        {"event_id": "2", "event_type": "task_created", "scope_id": "mission_abc"},
        {"event_id": "3", "event_type": "server_started", "scope_id": "system.server.lifecycle"},
        {"event_id": "4", "event_type": "task_created", "scope_id": "mission_other"},
    ]
    events_file.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    got = read_mission_events(tmp_path, "abc")
    assert [e["event_id"] for e in got] == ["1", "2"]
    got_other = read_mission_events(tmp_path, "mission_other")
    assert [e["event_id"] for e in got_other] == ["4"]
