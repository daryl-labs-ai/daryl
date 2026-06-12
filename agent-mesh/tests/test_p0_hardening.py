"""
P0 hardening — adversarial tests for agent-mesh (C2 / H6 / H7).

These prove the production guards added after the institutional audit:
  * C2  — sensitive endpoints require an API key when one is configured, and
          a production deployment refuses to start without one.
  * H6  — a task result can only be submitted by the assigned agent.
  * H7  — the append-only events.jsonl writer refuses oversized / overflowing
          writes (disk-DoS guard).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_mesh.adapters.daryl_adapter.signing import (
    canonicalize_payload,
    compute_content_hash,
    generate_keypair,
    sign_bytes,
)
from agent_mesh.config import Config
from agent_mesh.dsm.writer import DSMWriter
from agent_mesh.server.app import create_app

API_KEY = "test-secret-key-123"


def _config(tmp_path: Path, **overrides) -> Config:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    base = dict(data_dir=data_dir, server_id="server_test", log_level="WARNING")
    base.update(overrides)
    return Config(**base)


def _sign(sk, agent_id, key_id, mission_id, task_id, contribution_id, content, created_at):
    payload = {
        "schema_version": "signing.v1",
        "agent_id": agent_id,
        "key_id": key_id,
        "mission_id": mission_id,
        "task_id": task_id,
        "contribution_id": contribution_id,
        "contribution_type": "task_result",
        "content_hash": compute_content_hash(content),
        "created_at": created_at,
    }
    return sign_bytes(canonicalize_payload(payload), sk)


# ----------------------------- C2: authentication -----------------------------


class TestApiKeyAuth:
    def test_missions_unauthenticated_is_rejected(self, tmp_path):
        app = create_app(_config(tmp_path, api_key=API_KEY))
        with TestClient(app) as client:
            r = client.post("/missions", json={"title": "t", "description": "d"})
            assert r.status_code == 401

    def test_register_unauthenticated_is_rejected(self, tmp_path):
        app = create_app(_config(tmp_path, api_key=API_KEY))
        _, pk = generate_keypair()
        with TestClient(app) as client:
            r = client.post(
                "/agents/register",
                json={"agent_id": "a", "agent_type": "worker",
                      "capabilities": ["analyze"], "public_key": pk},
            )
            assert r.status_code == 401

    def test_valid_api_key_is_accepted(self, tmp_path):
        app = create_app(_config(tmp_path, api_key=API_KEY))
        with TestClient(app) as client:
            r = client.post(
                "/missions",
                json={"title": "t", "description": "d"},
                headers={"X-API-Key": API_KEY},
            )
            assert r.status_code == 201

    def test_bearer_scheme_is_accepted(self, tmp_path):
        app = create_app(_config(tmp_path, api_key=API_KEY))
        with TestClient(app) as client:
            r = client.post(
                "/missions",
                json={"title": "t", "description": "d"},
                headers={"Authorization": f"Bearer {API_KEY}"},
            )
            assert r.status_code == 201

    def test_no_key_configured_allows_dev_mode(self, tmp_path):
        """Backward compatibility: with no key configured, enforcement is off."""
        app = create_app(_config(tmp_path))  # api_key=None
        with TestClient(app) as client:
            r = client.post("/missions", json={"title": "t", "description": "d"})
            assert r.status_code == 201

    def test_production_without_key_refuses_to_start(self, tmp_path):
        with pytest.raises(RuntimeError, match="AGENT_MESH_API_KEY"):
            create_app(_config(tmp_path, app_env="production", api_key=None))


# ----------------------------- H6: assignee check -----------------------------


class TestSubmitOnlyByAssignee:
    def test_non_assignee_result_is_forbidden(self, tmp_path):
        app = create_app(_config(tmp_path, api_key=API_KEY))
        h = {"X-API-Key": API_KEY}
        with TestClient(app) as client:
            keys = {}
            for aid in ("w1", "w2"):
                sk, pk = generate_keypair()
                r = client.post(
                    "/agents/register",
                    json={"agent_id": aid, "agent_type": "worker",
                          "capabilities": ["analyze"], "public_key": pk},
                    headers=h,
                )
                assert r.status_code == 201, r.text
                keys[aid] = (sk, r.json()["key_id"])

            mission_id = client.post(
                "/missions", json={"title": "t", "description": "d"}, headers=h
            ).json()["mission_id"]
            tr = client.post(
                "/tasks",
                json={"mission_id": mission_id, "task_type": "analyze", "payload": {}},
                headers=h,
            )
            assert tr.status_code == 201, tr.text
            task_id = tr.json()["task_id"]
            assignee = tr.json()["assigned_to"]
            attacker = "w2" if assignee == "w1" else "w1"

            sk, key_id = keys[attacker]
            content = {"result": "forged"}
            created_at = "2026-04-14T10:00:00Z"
            sig = _sign(sk, attacker, key_id, mission_id, task_id, "c1", content, created_at)

            r = client.post(
                f"/tasks/{task_id}/result",
                json={"agent_id": attacker, "contribution_id": "c1", "content": content,
                      "self_reported_confidence": 0.9, "signature": sig, "created_at": created_at},
                headers=h,
            )
            assert r.status_code == 403, r.text
            assert "agent_not_assignee" in r.json()["detail"]

    def test_assignee_result_still_succeeds(self, tmp_path):
        app = create_app(_config(tmp_path, api_key=API_KEY))
        h = {"X-API-Key": API_KEY}
        with TestClient(app) as client:
            sk, pk = generate_keypair()
            reg = client.post(
                "/agents/register",
                json={"agent_id": "w1", "agent_type": "worker",
                      "capabilities": ["analyze"], "public_key": pk},
                headers=h,
            )
            key_id = reg.json()["key_id"]
            mission_id = client.post(
                "/missions", json={"title": "t", "description": "d"}, headers=h
            ).json()["mission_id"]
            tr = client.post(
                "/tasks",
                json={"mission_id": mission_id, "task_type": "analyze", "payload": {}},
                headers=h,
            )
            task_id = tr.json()["task_id"]
            assert tr.json()["assigned_to"] == "w1"

            content = {"result": "ok"}
            created_at = "2026-04-14T10:00:00Z"
            sig = _sign(sk, "w1", key_id, mission_id, task_id, "c1", content, created_at)
            r = client.post(
                f"/tasks/{task_id}/result",
                json={"agent_id": "w1", "contribution_id": "c1", "content": content,
                      "self_reported_confidence": 0.9, "signature": sig, "created_at": created_at},
                headers=h,
            )
            assert r.status_code == 201, r.text


# ----------------------------- H7: write bounds -------------------------------


class TestWriterBounds:
    def test_oversized_event_is_refused(self, tmp_path):
        writer = DSMWriter(tmp_path, max_event_bytes=512)
        big = {"event_id": "e1", "blob": "x" * 5000}
        assert writer.write(big) is None
        assert not writer.path.exists() or writer.path.stat().st_size == 0

    def test_log_ceiling_refuses_further_writes(self, tmp_path):
        writer = DSMWriter(tmp_path, max_log_bytes=300)
        accepted = 0
        for i in range(50):
            if writer.write({"event_id": f"e{i}", "n": i}) is not None:
                accepted += 1
        # Some writes succeed until the ceiling, then all are refused.
        assert 0 < accepted < 50
        assert writer.path.stat().st_size <= 300

    def test_unbounded_by_default(self, tmp_path):
        writer = DSMWriter(tmp_path)  # no limits
        assert writer.write({"event_id": "e1", "n": 1}) is not None
