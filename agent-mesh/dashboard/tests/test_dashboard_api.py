"""Dashboard API tests.

Drives the readers with a handcrafted events.jsonl in a temp data dir, then
exercises every endpoint via FastAPI's TestClient. SQLite is mocked to the
minimum schema so the reader's sqlite probe doesn't explode.

Signature verification is tested both ways:
  - A valid signature (produced with the real signing module) must verify.
  - A garbage signature must NOT verify.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_mesh.adapters.daryl_adapter.signing import (
    canonicalize_payload,
    compute_content_hash,
    generate_keypair,
    sign_bytes,
)
from dashboard.app import create_app
from dashboard.readers import DashboardReader


def _make_event(
    event_id: str,
    event_type: str,
    timestamp: str,
    scope_type: str,
    scope_id: str,
    source_type: str,
    source_id: str,
    payload: dict,
) -> dict:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "event_type": event_type,
        "event_version": "1.0",
        "timestamp": timestamp,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "source_type": source_type,
        "source_id": source_id,
        "writer_type": "server",
        "writer_id": "server_test",
        "payload": payload,
        "auth": {
            "transport_authenticated": False,
            "signature_present": False,
            "signature_verified": False,
            "key_id": None,
            "signature_algorithm": None,
        },
        "links": {"parent_event_id": None, "causal_refs": []},
    }


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    # Minimal SQLite schema matching the real index.sqlite3
    conn = sqlite3.connect(d / "index.sqlite3")
    conn.executescript(
        """
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT,
            scope_type TEXT,
            scope_id TEXT,
            source_id TEXT,
            timestamp TEXT,
            payload_json TEXT,
            entry_hash TEXT
        );
        CREATE TABLE agent_runtime (
            agent_id TEXT PRIMARY KEY,
            last_heartbeat TEXT,
            status TEXT,
            current_task_id TEXT
        );
        CREATE TABLE missions (
            mission_id TEXT PRIMARY KEY,
            status TEXT,
            created_at TEXT,
            closed_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return d


@pytest.fixture
def sample_events(data_dir: Path) -> dict:
    """Populate events.jsonl with a realistic scenario:

    1 mission, 2 tasks, 2 agents registered, 2 results:
      - task_001 result: signed correctly by agent_alpha
      - task_002 result: bogus signature from agent_beta
    """
    sk_alpha, pk_alpha = generate_keypair()
    _, pk_beta = generate_keypair()
    mission_id = "mission_test_001"
    events: list[dict] = []

    events.append(
        _make_event(
            "ev_001",
            "server_started",
            "2026-04-14T10:00:00Z",
            "system",
            "system.server.lifecycle",
            "server",
            "server_test",
            {"server_id": "server_test"},
        )
    )
    events.append(
        _make_event(
            "ev_002",
            "mission_created",
            "2026-04-14T10:01:00Z",
            "mission",
            f"mission_{mission_id}",
            "server",
            "server_test",
            {
                "mission_id": mission_id,
                "title": "Test mission",
                "description": "dashboard test scenario",
                "metadata": {},
            },
        )
    )
    events.append(
        _make_event(
            "ev_003",
            "agent_registered",
            "2026-04-14T10:02:00Z",
            "system",
            "system.agent_registry",
            "server",
            "server_test",
            {
                "agent_id": "agent_alpha",
                "agent_type": "test",
                "capabilities": ["analysis", "review"],
                "public_key": pk_alpha,
                "key_id": "key_alpha",
            },
        )
    )
    events.append(
        _make_event(
            "ev_004",
            "agent_registered",
            "2026-04-14T10:02:30Z",
            "system",
            "system.agent_registry",
            "server",
            "server_test",
            {
                "agent_id": "agent_beta",
                "agent_type": "test",
                "capabilities": ["analysis"],
                "public_key": pk_beta,
                "key_id": "key_beta",
            },
        )
    )
    events.append(
        _make_event(
            "ev_005",
            "task_created",
            "2026-04-14T10:03:00Z",
            "mission",
            f"mission_{mission_id}",
            "server",
            "server_test",
            {
                "task_id": "task_001",
                "mission_id": mission_id,
                "task_type": "analysis",
                "payload": {
                    "objective": "Analyze X",
                    "required_capabilities": ["analysis"],
                },
            },
        )
    )
    events.append(
        _make_event(
            "ev_006",
            "task_assigned",
            "2026-04-14T10:03:05Z",
            "mission",
            f"mission_{mission_id}",
            "server",
            "server_test",
            {
                "task_id": "task_001",
                "mission_id": mission_id,
                "assigned_to": "agent_alpha",
            },
        )
    )
    events.append(
        _make_event(
            "ev_007",
            "task_created",
            "2026-04-14T10:04:00Z",
            "mission",
            f"mission_{mission_id}",
            "server",
            "server_test",
            {
                "task_id": "task_002",
                "mission_id": mission_id,
                "task_type": "analysis",
                "payload": {"objective": "Analyze Y"},
            },
        )
    )

    # ── Valid signature for task_001 ─────────────────────────────────────
    content1 = {"text": "Alpha's answer", "agent_id": "agent_alpha"}
    ch1 = compute_content_hash(content1)
    created_at_1 = "2026-04-14T10:05:00Z"
    signable1 = {
        "schema_version": "signing.v1",
        "agent_id": "agent_alpha",
        "key_id": "key_alpha",
        "mission_id": mission_id,
        "task_id": "task_001",
        "contribution_id": "c1",
        "contribution_type": "task_result",
        "content_hash": ch1,
        "created_at": created_at_1,
    }
    sig1 = sign_bytes(canonicalize_payload(signable1), sk_alpha)
    events.append(
        _make_event(
            "ev_008",
            "task_result_submitted",
            "2026-04-14T10:05:01Z",
            "mission",
            f"mission_{mission_id}",
            "agent",
            "agent_alpha",
            {
                "task_id": "task_001",
                "mission_id": mission_id,
                "agent_id": "agent_alpha",
                "contribution_id": "c1",
                "content_hash": ch1,
                "signature": sig1,
                "self_reported_confidence": 0.9,
                "created_at": created_at_1,
                "content": content1,
            },
        )
    )

    # ── Bogus signature for task_002 ─────────────────────────────────────
    content2 = {"text": "Beta's (fake) answer", "agent_id": "agent_beta"}
    ch2 = compute_content_hash(content2)
    events.append(
        _make_event(
            "ev_009",
            "task_result_submitted",
            "2026-04-14T10:05:30Z",
            "mission",
            f"mission_{mission_id}",
            "agent",
            "agent_beta",
            {
                "task_id": "task_002",
                "mission_id": mission_id,
                "agent_id": "agent_beta",
                "contribution_id": "c2",
                "content_hash": ch2,
                "signature": "AAAAaaaa" * 10,  # garbage base64 — will not verify
                "self_reported_confidence": 0.5,
                "created_at": "2026-04-14T10:05:25Z",
                "content": content2,
            },
        )
    )

    events_path = data_dir / "events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    return {
        "mission_id": mission_id,
        "sk_alpha": sk_alpha,
        "pk_alpha": pk_alpha,
        "event_count": len(events),
    }


@pytest.fixture
def client(data_dir, sample_events):
    app = create_app(data_dir=data_dir)
    with TestClient(app) as c:
        yield c


# ── HTML index ──────────────────────────────────────────────────────────────


def test_index_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text.lower()
    assert "agent-mesh dashboard" in body
    assert "missions" in body
    assert "agents" in body


# ── /api/missions ───────────────────────────────────────────────────────────


def test_missions_list(client, sample_events):
    r = client.get("/api/missions")
    assert r.status_code == 200
    missions = r.json()
    assert len(missions) == 1
    m = missions[0]
    assert m["mission_id"] == sample_events["mission_id"]
    assert m["title"] == "Test mission"
    assert m["status"] == "open"
    assert m["task_count"] == 2
    assert m["result_count"] == 2
    assert m["closed_at"] is None


# ── /api/missions/{id} ──────────────────────────────────────────────────────


def test_mission_detail(client, sample_events):
    r = client.get(f"/api/missions/{sample_events['mission_id']}")
    assert r.status_code == 200
    m = r.json()
    assert m["mission_id"] == sample_events["mission_id"]
    assert m["title"] == "Test mission"
    assert m["status"] == "open"

    assert len(m["tasks"]) == 2
    tasks = {t["task_id"]: t for t in m["tasks"]}

    # task_001 — assigned to alpha, valid signature
    t1 = tasks["task_001"]
    assert t1["assigned_to"] == "agent_alpha"
    assert t1["objective"] == "Analyze X"
    assert len(t1["results"]) == 1
    r1 = t1["results"][0]
    assert r1["agent_id"] == "agent_alpha"
    assert r1["signature_valid"] is True
    assert r1["content_hash"].startswith("sha256:")
    assert r1["content"] == {"text": "Alpha's answer", "agent_id": "agent_alpha"}

    # task_002 — bogus signature
    t2 = tasks["task_002"]
    assert t2["objective"] == "Analyze Y"
    assert len(t2["results"]) == 1
    r2 = t2["results"][0]
    assert r2["agent_id"] == "agent_beta"
    assert r2["signature_valid"] is False

    # Mission-scoped events: mission_created + 2 task_created + task_assigned + 2 task_result_submitted
    assert len(m["events"]) == 6


def test_mission_detail_404(client):
    r = client.get("/api/missions/does_not_exist")
    assert r.status_code == 404
    assert r.json()["detail"] == "mission not found"


# ── /api/agents ─────────────────────────────────────────────────────────────


def test_agents_list(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    agents = r.json()
    assert len(agents) == 2
    ids = {a["agent_id"] for a in agents}
    assert ids == {"agent_alpha", "agent_beta"}

    alpha = next(a for a in agents if a["agent_id"] == "agent_alpha")
    assert alpha["agent_type"] == "test"
    assert "analysis" in alpha["capabilities"]
    assert "review" in alpha["capabilities"]
    assert alpha["key_id"] == "key_alpha"
    assert alpha["status"] == "active"
    assert alpha["public_key"]  # non-empty


# ── /api/events ─────────────────────────────────────────────────────────────


def test_events_list_default_newest_first(client, sample_events):
    r = client.get("/api/events")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == sample_events["event_count"]  # 9
    # newest first
    assert events[0]["event_type"] == "task_result_submitted"
    # oldest last
    assert events[-1]["event_type"] == "server_started"


def test_events_limit(client):
    r = client.get("/api/events?limit=3")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 3
    # still newest-first within the 3 most recent
    assert events[0]["event_type"] == "task_result_submitted"


def test_events_limit_clamped_high(client, sample_events):
    r = client.get("/api/events?limit=9999")
    assert r.status_code == 200
    events = r.json()
    # server clamps to 500, but there are only 9 events total
    assert len(events) == sample_events["event_count"]


def test_events_limit_clamped_low(client):
    r = client.get("/api/events?limit=0")
    assert r.status_code == 200
    events = r.json()
    # limit=0 clamped up to 1
    assert len(events) == 1


# ── Empty data dir ──────────────────────────────────────────────────────────


def test_empty_data_dir(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    app = create_app(data_dir=empty)
    with TestClient(app) as c:
        assert c.get("/api/missions").json() == []
        assert c.get("/api/agents").json() == []
        assert c.get("/api/events").json() == []
        assert c.get("/api/missions/whatever").status_code == 404


# ── Reader unit checks ──────────────────────────────────────────────────────


def test_reader_direct(data_dir, sample_events):
    reader = DashboardReader(data_dir)
    missions = reader.list_missions()
    assert len(missions) == 1

    detail = reader.get_mission_detail(sample_events["mission_id"])
    assert detail is not None
    assert detail["mission_id"] == sample_events["mission_id"]

    assert reader.get_agent("agent_alpha") is not None
    assert reader.get_agent("ghost") is None

    # SQLite probe works (empty table returns 0)
    assert reader.sqlite_event_count() == 0


def test_reader_verify_signature_returns_none_for_unknown_agent(data_dir):
    """If the signing payload references an agent we never registered, verification
    returns None (cannot verify), not False."""
    reader = DashboardReader(data_dir)
    result = reader._verify_result_signature(
        {
            "agent_id": "ghost_agent",
            "signature": "AAAA",
            "task_id": "t",
            "mission_id": "m",
            "contribution_id": "c",
            "content_hash": "sha256:deadbeef",
            "created_at": "2026-04-14T10:00:00Z",
        }
    )
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Rich fixture for tasks / compare / event-detail endpoints
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def rich_data_dir(tmp_path: Path) -> Path:
    """A richer scenario that exercises every new endpoint.

    1 mission with 3 tasks:
      - task_r1: PENDING  (no submissions)
      - task_r2: SUBMITTED (1 submission, carries a receipt_id in the payload)
      - task_r3: VALIDATED (2 submissions + a validation_completed event)

    2 agents registered with real Ed25519 keypairs so signatures verify.
    """
    d = tmp_path / "rich"
    d.mkdir()

    # Empty sqlite (not used directly but kept to match prod layout)
    conn = sqlite3.connect(d / "index.sqlite3")
    conn.executescript(
        """
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT, scope_type TEXT, scope_id TEXT,
            source_id TEXT, timestamp TEXT,
            payload_json TEXT, entry_hash TEXT
        );
        CREATE TABLE agent_runtime (
            agent_id TEXT PRIMARY KEY,
            last_heartbeat TEXT, status TEXT, current_task_id TEXT
        );
        CREATE TABLE missions (
            mission_id TEXT PRIMARY KEY,
            status TEXT, created_at TEXT, closed_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    sk_a, pk_a = generate_keypair()
    sk_b, pk_b = generate_keypair()
    mid = "mission_rich_001"
    events: list[dict] = []

    events.append(
        _make_event(
            "erv_001", "server_started", "2026-04-14T09:00:00Z",
            "system", "system.server.lifecycle", "server", "srv",
            {"server_id": "srv"},
        )
    )
    events.append(
        _make_event(
            "erv_002", "mission_created", "2026-04-14T09:01:00Z",
            "mission", f"mission_{mid}", "server", "srv",
            {
                "mission_id": mid,
                "title": "Rich mission",
                "description": "compare/tasks/event-detail scenario",
                "metadata": {"priority": "high"},
            },
        )
    )
    events.append(
        _make_event(
            "erv_003", "agent_registered", "2026-04-14T09:02:00Z",
            "system", "system.agent_registry", "server", "srv",
            {
                "agent_id": "agent_a",
                "agent_type": "test",
                "capabilities": ["analysis"],
                "public_key": pk_a,
                "key_id": "ka",
            },
        )
    )
    events.append(
        _make_event(
            "erv_004", "agent_registered", "2026-04-14T09:02:30Z",
            "system", "system.agent_registry", "server", "srv",
            {
                "agent_id": "agent_b",
                "agent_type": "test",
                "capabilities": ["analysis"],
                "public_key": pk_b,
                "key_id": "kb",
            },
        )
    )

    # ── task_r1 (pending) ────────────────────────────────────────────
    events.append(
        _make_event(
            "erv_005", "task_created", "2026-04-14T09:03:00Z",
            "mission", f"mission_{mid}", "server", "srv",
            {
                "task_id": "task_r1",
                "mission_id": mid,
                "task_type": "analysis",
                "payload": {
                    "objective": "Task 1 (pending)",
                    "required_capabilities": ["analysis"],
                },
            },
        )
    )

    # ── task_r2 (1 submission, with receipt_id) ──────────────────────
    events.append(
        _make_event(
            "erv_006", "task_created", "2026-04-14T09:03:30Z",
            "mission", f"mission_{mid}", "server", "srv",
            {
                "task_id": "task_r2",
                "mission_id": mid,
                "task_type": "analysis",
                "payload": {
                    "objective": "Task 2 (single submission)",
                    "required_capabilities": ["analysis"],
                },
            },
        )
    )
    events.append(
        _make_event(
            "erv_007", "task_assigned", "2026-04-14T09:03:35Z",
            "mission", f"mission_{mid}", "server", "srv",
            {
                "task_id": "task_r2",
                "mission_id": mid,
                "assigned_to": "agent_a",
            },
        )
    )
    content_r2 = {"text": "Agent A's solo answer", "agent_id": "agent_a"}
    ch_r2 = compute_content_hash(content_r2)
    sig_r2 = sign_bytes(
        canonicalize_payload(
            {
                "schema_version": "signing.v1",
                "agent_id": "agent_a",
                "key_id": "ka",
                "mission_id": mid,
                "task_id": "task_r2",
                "contribution_id": "cr2",
                "contribution_type": "task_result",
                "content_hash": ch_r2,
                "created_at": "2026-04-14T09:04:00Z",
            }
        ),
        sk_a,
    )
    events.append(
        _make_event(
            "erv_008", "task_result_submitted", "2026-04-14T09:04:01Z",
            "mission", f"mission_{mid}", "agent", "agent_a",
            {
                "task_id": "task_r2",
                "mission_id": mid,
                "agent_id": "agent_a",
                "contribution_id": "cr2",
                "content_hash": ch_r2,
                "signature": sig_r2,
                "self_reported_confidence": 0.8,
                "created_at": "2026-04-14T09:04:00Z",
                "content": content_r2,
                "receipt_id": "receipt_r2",  # present in payload → should be extracted
            },
        )
    )

    # ── task_r3 (2 submissions + validation_completed) ───────────────
    events.append(
        _make_event(
            "erv_009", "task_created", "2026-04-14T09:05:00Z",
            "mission", f"mission_{mid}", "server", "srv",
            {
                "task_id": "task_r3",
                "mission_id": mid,
                "task_type": "analysis",
                "payload": {
                    "objective": "Task 3 (comparable)",
                    "required_capabilities": ["analysis"],
                },
            },
        )
    )
    content_a3 = {"text": "A's view on r3", "agent_id": "agent_a"}
    ch_a3 = compute_content_hash(content_a3)
    sig_a3 = sign_bytes(
        canonicalize_payload(
            {
                "schema_version": "signing.v1",
                "agent_id": "agent_a",
                "key_id": "ka",
                "mission_id": mid,
                "task_id": "task_r3",
                "contribution_id": "ca3",
                "contribution_type": "task_result",
                "content_hash": ch_a3,
                "created_at": "2026-04-14T09:06:00Z",
            }
        ),
        sk_a,
    )
    events.append(
        _make_event(
            "erv_010", "task_result_submitted", "2026-04-14T09:06:01Z",
            "mission", f"mission_{mid}", "agent", "agent_a",
            {
                "task_id": "task_r3",
                "mission_id": mid,
                "agent_id": "agent_a",
                "contribution_id": "ca3",
                "content_hash": ch_a3,
                "signature": sig_a3,
                "self_reported_confidence": 0.9,
                "created_at": "2026-04-14T09:06:00Z",
                "content": content_a3,
            },
        )
    )
    content_b3 = {"text": "B's view on r3", "agent_id": "agent_b"}
    ch_b3 = compute_content_hash(content_b3)
    sig_b3 = sign_bytes(
        canonicalize_payload(
            {
                "schema_version": "signing.v1",
                "agent_id": "agent_b",
                "key_id": "kb",
                "mission_id": mid,
                "task_id": "task_r3",
                "contribution_id": "cb3",
                "contribution_type": "task_result",
                "content_hash": ch_b3,
                "created_at": "2026-04-14T09:07:00Z",
            }
        ),
        sk_b,
    )
    events.append(
        _make_event(
            "erv_011", "task_result_submitted", "2026-04-14T09:07:01Z",
            "mission", f"mission_{mid}", "agent", "agent_b",
            {
                "task_id": "task_r3",
                "mission_id": mid,
                "agent_id": "agent_b",
                "contribution_id": "cb3",
                "content_hash": ch_b3,
                "signature": sig_b3,
                "self_reported_confidence": 0.7,
                "created_at": "2026-04-14T09:07:00Z",
                "content": content_b3,
            },
        )
    )
    events.append(
        _make_event(
            "erv_012", "validation_completed", "2026-04-14T09:08:00Z",
            "mission", f"mission_{mid}", "server", "srv",
            {"task_id": "task_r3", "mission_id": mid, "winner": "agent_a"},
        )
    )

    events_path = d / "events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    return d


@pytest.fixture
def rich_client(rich_data_dir):
    app = create_app(data_dir=rich_data_dir)
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# /api/tasks + /api/tasks/{id}
# ═══════════════════════════════════════════════════════════════════════════


def test_tasks_list(rich_client):
    r = rich_client.get("/api/tasks")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 3
    # newest first by created_at
    ids = [t["task_id"] for t in tasks]
    assert ids == ["task_r3", "task_r2", "task_r1"]


def test_tasks_list_empty(tmp_path: Path):
    empty = tmp_path / "empty_tasks"
    empty.mkdir()
    app = create_app(data_dir=empty)
    with TestClient(app) as c:
        assert c.get("/api/tasks").json() == []


def test_task_status_pending(rich_client):
    tasks = {t["task_id"]: t for t in rich_client.get("/api/tasks").json()}
    assert tasks["task_r1"]["status"] == "pending"
    assert tasks["task_r1"]["submissions_count"] == 0
    assert tasks["task_r1"]["last_submission_at"] is None


def test_task_status_submitted(rich_client):
    tasks = {t["task_id"]: t for t in rich_client.get("/api/tasks").json()}
    assert tasks["task_r2"]["status"] == "submitted"
    assert tasks["task_r2"]["submissions_count"] == 1
    assert tasks["task_r2"]["assigned_to"] == "agent_a"


def test_task_status_validated(rich_client):
    tasks = {t["task_id"]: t for t in rich_client.get("/api/tasks").json()}
    assert tasks["task_r3"]["status"] == "validated"
    assert tasks["task_r3"]["submissions_count"] == 2


def test_task_receipt_id_extracted_when_present(rich_client):
    tasks = {t["task_id"]: t for t in rich_client.get("/api/tasks").json()}
    assert tasks["task_r2"]["receipt_id"] == "receipt_r2"
    # task_r3 submissions didn't include receipt_id in payload → None
    assert tasks["task_r3"]["receipt_id"] is None
    assert tasks["task_r1"]["receipt_id"] is None


def test_task_detail_pending_has_no_submissions(rich_client):
    r = rich_client.get("/api/tasks/task_r1")
    assert r.status_code == 200
    t = r.json()
    assert t["status"] == "pending"
    assert t["submissions"] == []
    assert t["objective"] == "Task 1 (pending)"
    assert t["mission_id"] == "mission_rich_001"


def test_task_detail_single_submission(rich_client):
    r = rich_client.get("/api/tasks/task_r2")
    assert r.status_code == 200
    t = r.json()
    assert t["status"] == "submitted"
    assert len(t["submissions"]) == 1
    sub = t["submissions"][0]
    assert sub["agent_id"] == "agent_a"
    assert sub["signature_valid"] is True
    assert sub["receipt_id"] == "receipt_r2"
    assert sub["content"] == {"text": "Agent A's solo answer", "agent_id": "agent_a"}


def test_task_detail_multi_submissions(rich_client):
    r = rich_client.get("/api/tasks/task_r3")
    assert r.status_code == 200
    t = r.json()
    assert t["status"] == "validated"
    assert len(t["submissions"]) == 2
    agents = {s["agent_id"] for s in t["submissions"]}
    assert agents == {"agent_a", "agent_b"}
    # Both submissions are cryptographically valid
    for s in t["submissions"]:
        assert s["signature_valid"] is True


def test_task_detail_404(rich_client):
    r = rich_client.get("/api/tasks/ghost_task")
    assert r.status_code == 404
    assert r.json()["detail"] == "task not found"


# ═══════════════════════════════════════════════════════════════════════════
# /api/missions/{id}/compare
# ═══════════════════════════════════════════════════════════════════════════


def test_mission_compare(rich_client):
    r = rich_client.get("/api/missions/mission_rich_001/compare")
    assert r.status_code == 200
    data = r.json()
    assert data["mission_id"] == "mission_rich_001"
    assert data["title"] == "Rich mission"
    tasks = {t["task_id"]: t for t in data["tasks"]}

    assert tasks["task_r1"]["submissions_count"] == 0
    assert tasks["task_r1"]["comparable"] is False

    assert tasks["task_r2"]["submissions_count"] == 1
    assert tasks["task_r2"]["comparable"] is False  # single sub → "waiting for more"

    assert tasks["task_r3"]["submissions_count"] == 2
    assert tasks["task_r3"]["comparable"] is True
    assert len(tasks["task_r3"]["submissions"]) == 2


def test_mission_compare_404(rich_client):
    r = rich_client.get("/api/missions/ghost_mission/compare")
    assert r.status_code == 404
    assert r.json()["detail"] == "mission not found"


def test_mission_compare_includes_signature_validity(rich_client):
    data = rich_client.get("/api/missions/mission_rich_001/compare").json()
    tasks = {t["task_id"]: t for t in data["tasks"]}
    r3_subs = tasks["task_r3"]["submissions"]
    for s in r3_subs:
        assert s["signature_valid"] is True


# ═══════════════════════════════════════════════════════════════════════════
# /api/events/{event_id}
# ═══════════════════════════════════════════════════════════════════════════


def test_event_detail(rich_client):
    r = rich_client.get("/api/events/erv_002")
    assert r.status_code == 200
    ev = r.json()
    assert ev["event_id"] == "erv_002"
    assert ev["event_type"] == "mission_created"
    assert ev["scope_id"] == "mission_mission_rich_001"
    assert "payload" in ev
    assert "auth" in ev
    assert "links" in ev
    assert ev["payload"]["title"] == "Rich mission"


def test_event_detail_for_submission_has_full_payload(rich_client):
    r = rich_client.get("/api/events/erv_008")
    assert r.status_code == 200
    ev = r.json()
    assert ev["event_type"] == "task_result_submitted"
    assert ev["source_type"] == "agent"
    assert ev["source_id"] == "agent_a"
    # Full payload is present (with content, signature, etc.)
    assert ev["payload"]["agent_id"] == "agent_a"
    assert ev["payload"]["receipt_id"] == "receipt_r2"
    assert "content" in ev["payload"]
    assert "signature" in ev["payload"]


def test_event_detail_404(rich_client):
    r = rich_client.get("/api/events/does_not_exist")
    assert r.status_code == 404
    assert r.json()["detail"] == "event not found"


# ═══════════════════════════════════════════════════════════════════════════
# Enhanced missions list (agents_count + last_event_at)
# ═══════════════════════════════════════════════════════════════════════════


def test_mission_list_has_agents_count(rich_client):
    r = rich_client.get("/api/missions")
    assert r.status_code == 200
    missions = r.json()
    assert len(missions) == 1
    m = missions[0]
    # 2 distinct agents submitted (agent_a and agent_b)
    assert m["agents_count"] == 2
    assert m["task_count"] == 3
    assert m["result_count"] == 3  # 1 in task_r2 + 2 in task_r3


def test_mission_list_has_last_event_at(rich_client):
    m = rich_client.get("/api/missions").json()[0]
    assert m.get("last_event_at") is not None
    # Last mission-scoped event is validation_completed at 09:08:00
    assert m["last_event_at"] == "2026-04-14T09:08:00Z"


def test_mission_list_backward_compatible_fields(rich_client):
    """Adding agents_count / last_event_at must not drop the existing fields."""
    m = rich_client.get("/api/missions").json()[0]
    for key in (
        "mission_id", "title", "description", "status",
        "created_at", "closed_at", "task_count", "result_count",
    ):
        assert key in m, f"missing field {key}"


# ═══════════════════════════════════════════════════════════════════════════
# Reader-level coverage for new methods
# ═══════════════════════════════════════════════════════════════════════════


def test_reader_list_tasks_direct(rich_data_dir):
    reader = DashboardReader(rich_data_dir)
    tasks = reader.list_tasks()
    assert len(tasks) == 3
    ids = {t["task_id"] for t in tasks}
    assert ids == {"task_r1", "task_r2", "task_r3"}


def test_reader_get_task_detail_unknown(rich_data_dir):
    reader = DashboardReader(rich_data_dir)
    assert reader.get_task_detail("nope") is None


def test_reader_compare_unknown_mission(rich_data_dir):
    reader = DashboardReader(rich_data_dir)
    assert reader.compare_mission_results("nope") is None


def test_reader_get_event_empty_string(rich_data_dir):
    reader = DashboardReader(rich_data_dir)
    assert reader.get_event("") is None
    assert reader.get_event("missing") is None
