"""
workers/protocol.py
--------------------
Shared worker protocol — agnostic to the LLM backend.

Every worker (Claude, GPT-4, Qwen, etc.) uses this base.
The LLM is just a detail — the protocol is what makes a mesh citizen.

Sequence:
  1. register()     → POST /agents/register
  2. poll_task()    → GET  /tasks/next?agent_id=...&capabilities=...
  3. execute()      → LLM call (implemented by subclass)
  4. sign_result()  → local Ed25519
  5. submit()       → POST /tasks/{task_id}/result
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from nacl.signing import SigningKey  # type: ignore[import]

logger = logging.getLogger(__name__)


# ── Signing primitives (local — no daryl import) ───────────────────────────────

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

def _sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return "sha256:" + hashlib.sha256(content).hexdigest()

def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def _sign(canonical_bytes: bytes, private_key_b64: str) -> str:
    sk = SigningKey(base64.b64decode(private_key_b64))
    return _b64(sk.sign(canonical_bytes).signature)

def generate_keypair() -> tuple[str, str]:
    sk = SigningKey.generate()
    return _b64(bytes(sk)), _b64(bytes(sk.verify_key))


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class WorkerConfig:
    agent_id: str
    capabilities: list[str]
    server_url: str          # e.g. "http://localhost:8000"
    private_key_b64: str
    public_key_b64: str
    key_id: str
    poll_interval_s: float = 2.0
    max_output_tokens: int = 1200


@dataclass
class Task:
    task_id: str
    mission_id: str
    task_type: str
    objective: str
    constraints: dict


@dataclass
class SignedResult:
    content: str             # raw LLM answer (string, for display/preview)
    content_dict: dict       # content wrapped as a dict — what the server hashes
    content_hash: str        # sha256:... of canonical content_dict bytes
    payload_hash: str        # sha256:... of canonical signed payload
    signature: str           # base64 Ed25519
    created_at: str          # ISO timestamp used inside the signed payload


# ── Base worker ────────────────────────────────────────────────────────────────

class MeshWorker:
    """
    Base class for all LLM workers.
    Subclasses implement only `call_llm(objective, constraints) -> str`.
    Everything else — registration, signing, submission — is here.
    """

    def __init__(self, config: WorkerConfig) -> None:
        self.config = config
        self._client = httpx.Client(base_url=config.server_url, timeout=30.0)
        self._registered = False

    # ── Protocol steps ─────────────────────────────────────────────────────────

    def register(self) -> None:
        """Step 1 — Register with the mesh server."""
        payload = {
            "agent_id": self.config.agent_id,
            "agent_type": "worker",
            "capabilities": self.config.capabilities,
            "public_key": self.config.public_key_b64,
        }
        r = self._client.post("/agents/register", json=payload)
        if r.status_code == 409:
            logger.info("Agent already registered — continuing")
        elif r.status_code == 201:
            logger.info("Registered as %s", self.config.agent_id)
        else:
            r.raise_for_status()
        data = r.json() if r.status_code in (201, 409) else {}
        if "key_id" in data:
            self.config.key_id = data["key_id"]
        self._registered = True

    def poll_task(self) -> Optional[Task]:
        """
        Step 2 — Pull next available task from server.
        Returns None if no task available.

        Note: agent-mesh V0 needs a GET /tasks/next endpoint.
        See endpoint spec below — add to routes.py if missing.
        """
        params = {
            "agent_id": self.config.agent_id,
            "capabilities": ",".join(self.config.capabilities),
        }
        try:
            r = self._client.get("/tasks/next", params=params)
            if r.status_code == 204:
                return None  # no task available
            if r.status_code == 200:
                data = r.json()
                return Task(
                    task_id=data["task_id"],
                    mission_id=data["mission_id"],
                    task_type=data["task_type"],
                    objective=data["objective"],
                    constraints=data.get("constraints", {}),
                )
            return None
        except Exception as exc:
            logger.warning("Poll failed: %s", exc)
            return None

    def call_llm(self, objective: str, constraints: dict) -> str:
        """Step 3 — Call the LLM. Must be implemented by subclass."""
        raise NotImplementedError

    def sign_result(self, task: Task, content: str, contribution_id: str) -> SignedResult:
        """Step 4 — Sign the result locally with the exact V0 server canonicalization.

        The server's submit_task_result route rebuilds the canonical payload with:
          - contribution_type = "task_result"  (literal, NOT the task's task_type)
          - content_hash      = compute_content_hash(body.content)  where body.content
                                is a dict, canonicalized JSON, SHA-256
        Both invariants must be honored by the worker or verification will fail.
        """
        # 1. Wrap the raw LLM string in a dict — this is what the server will hash.
        content_dict: dict = {"text": content, "agent_id": self.config.agent_id}
        content_hash = _sha256(_canonical(content_dict))

        signed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 2. Build the canonical signable the server will reconstruct verbatim.
        signable = {
            "schema_version": "signing.v1",
            "agent_id": self.config.agent_id,
            "key_id": self.config.key_id,
            "mission_id": task.mission_id,
            "task_id": task.task_id,
            "contribution_id": contribution_id,
            "contribution_type": "task_result",  # literal — matches the server
            "content_hash": content_hash,
            "created_at": signed_at,
        }
        canonical = _canonical(signable)
        payload_hash = _sha256(canonical)
        signature = _sign(canonical, self.config.private_key_b64)

        return SignedResult(
            content=content,
            content_dict=content_dict,
            content_hash=content_hash,
            payload_hash=payload_hash,
            signature=signature,
            created_at=signed_at,
        )

    def submit(
        self,
        task: Task,
        result: SignedResult,
        contribution_id: str,
        self_reported_confidence: float = 0.9,
    ) -> bool:
        """Step 5 — Submit signed result to server using the V0 schema.

        Payload shape matches `SubmitTaskResultRequest` exactly:
          - agent_id, contribution_id, content (dict), self_reported_confidence,
            signature, created_at  (required)
          - key_id, payload_hash                                 (optional but
            explicit transport of signing metadata, per V0 schema)

        The server will recompute content_hash from `content`, rebuild the
        canonical signable with `key_id` from the registry, and verify the
        signature. Because we signed the exact same canonical form, verification
        must succeed and the emitted `task_result_submitted` event will carry
        `auth.signature_verified = true`.
        """
        payload = {
            "agent_id": self.config.agent_id,
            "contribution_id": contribution_id,
            "content": result.content_dict,
            "self_reported_confidence": self_reported_confidence,
            "signature": result.signature,
            "created_at": result.created_at,
            # Optional but explicit signing metadata (per V0 schema):
            "key_id": self.config.key_id,
            "payload_hash": result.payload_hash,
        }
        r = self._client.post(f"/tasks/{task.task_id}/result", json=payload)
        if r.status_code == 201:
            logger.info("Result submitted — task=%s", task.task_id)
            return True
        logger.warning("Submit failed %d: %s", r.status_code, r.text)
        return False

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Register once, then poll → execute → sign → submit in a loop."""
        if not self._registered:
            self.register()

        logger.info(
            "Worker %s polling %s every %.1fs",
            self.config.agent_id, self.config.server_url, self.config.poll_interval_s
        )

        while True:
            task = self.poll_task()
            if task is None:
                time.sleep(self.config.poll_interval_s)
                continue

            logger.info("Task received: %s — %s", task.task_id, task.objective[:80])

            try:
                content = self.call_llm(task.objective, task.constraints)
                from ulid import ULID
                contribution_id = str(ULID())
                signed = self.sign_result(task, content, contribution_id)
                self.submit(task, signed, contribution_id)
            except Exception as exc:
                logger.error("Task %s failed: %s", task.task_id, exc)

            time.sleep(self.config.poll_interval_s)
