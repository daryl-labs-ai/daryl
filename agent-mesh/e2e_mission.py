#!/usr/bin/env python3
"""
e2e_mission.py
--------------
First real end-to-end test of agent-mesh with GenericLLMWorker + pluggable backends.

Flow:
  1. Check the server is reachable (GET /)
  2. Create mission + two tasks (both PENDING because no worker is registered yet)
  3. Register two workers with different backends
  4. Run workers in parallel threads: poll → call LLM → sign → submit
  5. Print the results (task_id, content_hash, payload_hash, signature, answer preview)
  6. Print DSM events for the mission (read from events.jsonl)

Modes:
  default          → Claude solo (requires ANTHROPIC_API_KEY)
  --two-backends   → Claude + GPT-4  (requires ANTHROPIC_API_KEY and OPENAI_API_KEY)
  --local          → Claude + Ollama (requires ANTHROPIC_API_KEY; Ollama running locally)

Env:
  MESH_SERVER_URL       default http://localhost:8000
  AGENT_MESH_DATA_DIR   default ./data
  ANTHROPIC_API_KEY     required
  OPENAI_API_KEY        optional — for --two-backends
  OLLAMA_MODEL          optional — for --local (default qwen2.5)
  OLLAMA_BASE_URL       optional — for --local (default http://localhost:11434)

Design notes:
  - We do NOT call MeshWorker.register() or MeshWorker.submit() because the versions
    bundled in workers/protocol.py send payload shapes that do not match the V0
    server schema. We bypass both with direct httpx calls, signed locally with the
    exact canonical payload the server expects.
  - We DO call MeshWorker.poll_task() — its GET /tasks/next shape matches the server.
  - Nothing in src/agent_mesh/ or workers/protocol.py is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Make `workers.*` and `agent_mesh.*` importable when this script is run directly.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import httpx  # noqa: E402

from agent_mesh.adapters.daryl_adapter.signing import (  # noqa: E402
    canonicalize_payload,
    compute_content_hash,
    sign_bytes,
)
from workers.backends import create_backend  # noqa: E402
from workers.backends.base import LLMBackend  # noqa: E402
from workers.generic_worker.worker import GenericLLMWorker  # noqa: E402
from workers.protocol import MeshWorker, WorkerConfig, generate_keypair  # noqa: E402

logger = logging.getLogger("e2e_mission")


# ── Constants ──────────────────────────────────────────────────────────────────

MISSION_TEXT = (
    "Analyze DSM (Daryl Sharding Memory) and list 3 strengths, "
    "3 weaknesses, and 1 priority improvement."
)
MISSION_TITLE = "DSM self-assessment"
MISSION_DESCRIPTION = "End-to-end mesh test — two workers, one mission."
DEFAULT_TASK_TYPE = "analysis"
DEFAULT_REQUIRED_CAPS = ["analysis"]
DEFAULT_CONSTRAINTS = {"max_output_tokens": 600, "output_format": "text"}
POLL_INTERVAL_S = 0.5
RESULT_WAIT_TIMEOUT_S = 180


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class WorkerResult:
    agent_id: str
    task_id: str
    content: str
    content_hash: str
    payload_hash: str
    signature: str


@dataclass
class WorkerBundle:
    worker: GenericLLMWorker
    label: str
    agent_type: str


# ── Utilities ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_of_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ── Server helpers ─────────────────────────────────────────────────────────────


def check_server_alive(client: httpx.Client) -> bool:
    """Return True if the server answers any HTTP request.

    The server has no /health endpoint; a 404 on GET / still proves it is alive.
    """
    try:
        r = client.get("/")
        return 0 < r.status_code < 600
    except Exception as exc:  # pragma: no cover — real network errors
        logger.warning("Server not reachable: %s", exc)
        return False


def register_worker_direct(
    client: httpx.Client, worker: MeshWorker, agent_type: str
) -> None:
    """Register a worker using the V0 server schema.

    Bypasses MeshWorker.register() which uses an older payload shape.
    """
    payload = {
        "agent_id": worker.config.agent_id,
        "agent_type": agent_type,
        "capabilities": worker.config.capabilities,
        "public_key": worker.config.public_key_b64,
    }
    r = client.post("/agents/register", json=payload)
    if r.status_code == 409:
        logger.info("Agent %s already registered — continuing", worker.config.agent_id)
    elif r.status_code == 201:
        data = r.json()
        # The server mints its own key_id; adopt it so submissions line up.
        worker.config.key_id = data.get("key_id", worker.config.key_id)
        logger.info("Registered %s (key_id=%s)", worker.config.agent_id, worker.config.key_id)
    else:
        r.raise_for_status()
    worker._registered = True


def create_mission(client: httpx.Client, title: str, description: str) -> str:
    r = client.post("/missions", json={"title": title, "description": description})
    r.raise_for_status()
    data = r.json()
    mission_id = data["mission_id"]
    logger.info("Mission created: %s", mission_id)
    return mission_id


def create_task_pending(
    client: httpx.Client,
    mission_id: str,
    objective: str,
    required_capabilities: list[str],
    constraints: dict,
) -> None:
    """Create a task expected to remain PENDING.

    When no worker is registered yet, the server auto-assign step fails with 503,
    but the task is still persisted in pending state — discoverable via
    GET /tasks/next once a worker registers.
    """
    body = {
        "mission_id": mission_id,
        "task_type": DEFAULT_TASK_TYPE,
        "payload": {
            "objective": objective,
            "required_capabilities": required_capabilities,
            "constraints": constraints,
        },
    }
    r = client.post("/tasks", json=body)
    if r.status_code in (201, 503):
        logger.info("Task posted (status=%d) — mission=%s", r.status_code, mission_id)
        return
    r.raise_for_status()


# ── Worker bounded runner ──────────────────────────────────────────────────────


def run_worker_bounded(
    worker: GenericLLMWorker,
    stop_event: threading.Event,
    results: list[WorkerResult],
    lock: threading.Lock,
) -> None:
    """Run a worker until stop_event is set.

    Polls `/tasks/next`. On each task:
      - calls the backend
      - builds the canonical signing payload that the server will re-verify
      - signs it and POSTs to `/tasks/{id}/result`
      - appends a `WorkerResult` to the shared list
    """
    poll_interval = max(0.05, float(worker.config.poll_interval_s))
    client = worker._client

    while not stop_event.is_set():
        try:
            task = worker.poll_task()
        except Exception as exc:
            logger.warning("%s poll failed: %s", worker.config.agent_id, exc)
            stop_event.wait(poll_interval)
            continue

        if task is None:
            stop_event.wait(poll_interval)
            continue

        logger.info(
            "%s picked task %s — %s",
            worker.config.agent_id,
            task.task_id,
            task.objective[:60],
        )

        try:
            content = worker.call_llm(task.objective, task.constraints)
        except Exception as exc:
            logger.error("%s call_llm failed: %s", worker.config.agent_id, exc)
            stop_event.wait(poll_interval)
            continue

        try:
            from ulid import ULID

            contribution_id = str(ULID())
        except Exception:
            contribution_id = f"ctr_{int(time.time() * 1000)}_{worker.config.agent_id}"

        created_at = _now_iso()
        result_content = {"text": content, "agent_id": worker.config.agent_id}
        content_hash = compute_content_hash(result_content)

        signable = {
            "schema_version": "signing.v1",
            "agent_id": worker.config.agent_id,
            "key_id": worker.config.key_id,
            "mission_id": task.mission_id,
            "task_id": task.task_id,
            "contribution_id": contribution_id,
            "contribution_type": "task_result",
            "content_hash": content_hash,
            "created_at": created_at,
        }
        canonical = canonicalize_payload(signable)
        signature = sign_bytes(canonical, worker.config.private_key_b64)
        payload_hash = _sha256_of_bytes(canonical)

        wr = WorkerResult(
            agent_id=worker.config.agent_id,
            task_id=task.task_id,
            content=content,
            content_hash=content_hash,
            payload_hash=payload_hash,
            signature=signature,
        )
        with lock:
            results.append(wr)

        submit_payload = {
            "agent_id": worker.config.agent_id,
            "contribution_id": contribution_id,
            "content": result_content,
            "self_reported_confidence": 0.9,
            "signature": signature,
            "created_at": created_at,
        }
        try:
            r = client.post(f"/tasks/{task.task_id}/result", json=submit_payload)
            if r.status_code == 201:
                logger.info(
                    "%s submitted task %s — receipt=%s",
                    worker.config.agent_id,
                    task.task_id,
                    r.json().get("receipt_id", "?"),
                )
            else:
                logger.warning(
                    "%s submit %s got %d: %s",
                    worker.config.agent_id,
                    task.task_id,
                    r.status_code,
                    r.text,
                )
        except Exception as exc:
            logger.error("%s submit failed: %s", worker.config.agent_id, exc)


# ── Worker factories ───────────────────────────────────────────────────────────


def _new_worker(
    agent_id: str,
    capabilities: list[str],
    server_url: str,
    backend: LLMBackend,
    poll_interval_s: float = POLL_INTERVAL_S,
) -> GenericLLMWorker:
    sk, pk = generate_keypair()
    config = WorkerConfig(
        agent_id=agent_id,
        capabilities=capabilities,
        server_url=server_url,
        private_key_b64=sk,
        public_key_b64=pk,
        key_id=f"key_{agent_id}_v1",
        poll_interval_s=poll_interval_s,
        max_output_tokens=DEFAULT_CONSTRAINTS["max_output_tokens"],
    )
    return GenericLLMWorker(config=config, backend=backend)


def build_claude_worker(server_url: str, agent_id: str = "agent_claude") -> WorkerBundle:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required")
    backend = create_backend(
        {
            "provider": "anthropic",
            "api_key": api_key,
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            "max_tokens": DEFAULT_CONSTRAINTS["max_output_tokens"],
        }
    )
    worker = _new_worker(agent_id, DEFAULT_REQUIRED_CAPS, server_url, backend)
    return WorkerBundle(worker=worker, label="Claude", agent_type="anthropic")


def build_openai_worker(server_url: str, agent_id: str = "agent_gpt4") -> WorkerBundle:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for --two-backends")
    backend = create_backend(
        {
            "provider": "openai",
            "api_key": api_key,
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "max_tokens": DEFAULT_CONSTRAINTS["max_output_tokens"],
        }
    )
    worker = _new_worker(agent_id, DEFAULT_REQUIRED_CAPS, server_url, backend)
    return WorkerBundle(worker=worker, label="GPT-4", agent_type="openai")


def build_ollama_worker(server_url: str, agent_id: str = "agent_ollama") -> WorkerBundle:
    backend = create_backend(
        {
            "provider": "ollama",
            "model": os.environ.get("OLLAMA_MODEL", "qwen2.5"),
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        }
    )
    worker = _new_worker(agent_id, DEFAULT_REQUIRED_CAPS, server_url, backend)
    return WorkerBundle(worker=worker, label="Ollama", agent_type="ollama")


def build_workers(mode: str, server_url: str) -> list[WorkerBundle]:
    """Return the list of workers to run for a given mode."""
    if mode == "default":
        return [build_claude_worker(server_url, "agent_claude_1")]
    if mode == "two-backends":
        return [
            build_claude_worker(server_url, "agent_claude"),
            build_openai_worker(server_url, "agent_gpt4"),
        ]
    if mode == "local":
        return [
            build_claude_worker(server_url, "agent_claude"),
            build_ollama_worker(server_url, "agent_ollama"),
        ]
    if mode == "openai-only":
        return [build_openai_worker(server_url, "agent_gpt4_1")]
    raise ValueError(f"unknown mode: {mode}")


# ── Event reader ───────────────────────────────────────────────────────────────


def read_mission_events(data_dir: Path, mission_id: str) -> list[dict]:
    """Read events.jsonl and return the events whose scope_id matches this mission."""
    events_file = data_dir / "events.jsonl"
    if not events_file.exists():
        return []
    target = f"mission_{mission_id}" if not mission_id.startswith("mission_") else mission_id
    out: list[dict] = []
    with events_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = ev.get("scope_id") or ""
            if sid == target or sid == f"mission_{mission_id}":
                out.append(ev)
    return out


# ── Orchestration ──────────────────────────────────────────────────────────────


def run_e2e(
    bundles: list[WorkerBundle],
    server_url: str,
    data_dir: Path,
    num_tasks: int = 2,
    wait_timeout_s: float = RESULT_WAIT_TIMEOUT_S,
) -> tuple[list[WorkerResult], str, list[dict]]:
    """Run the full e2e flow and return (results, mission_id, mission_events)."""
    if not bundles:
        raise ValueError("at least one worker bundle is required")

    # Each worker brings its own httpx client (wired by MeshWorker.__init__).
    # For orchestration we use any of them — they all point to the same server.
    orchestrator_client = bundles[0].worker._client

    if not check_server_alive(orchestrator_client):
        raise RuntimeError(f"Server at {server_url} is not reachable")

    mission_id = create_mission(orchestrator_client, MISSION_TITLE, MISSION_DESCRIPTION)

    for i in range(num_tasks):
        objective = f"[Task {i + 1}/{num_tasks}] {MISSION_TEXT}"
        create_task_pending(
            orchestrator_client,
            mission_id,
            objective,
            DEFAULT_REQUIRED_CAPS,
            DEFAULT_CONSTRAINTS,
        )

    for b in bundles:
        register_worker_direct(orchestrator_client, b.worker, b.agent_type)

    stop_event = threading.Event()
    results: list[WorkerResult] = []
    lock = threading.Lock()

    threads: list[threading.Thread] = []
    for b in bundles:
        t = threading.Thread(
            target=run_worker_bounded,
            args=(b.worker, stop_event, results, lock),
            name=f"worker-{b.worker.config.agent_id}",
            daemon=True,
        )
        t.start()
        threads.append(t)

    deadline = time.monotonic() + wait_timeout_s
    while time.monotonic() < deadline:
        with lock:
            if len(results) >= num_tasks:
                break
        time.sleep(0.1)

    stop_event.set()
    for t in threads:
        t.join(timeout=3.0)

    events = read_mission_events(data_dir, mission_id)
    return results, mission_id, events


# ── Pretty-printing ────────────────────────────────────────────────────────────


def print_banner(text: str) -> None:
    print()
    print("─" * 70)
    print(f"  {text}")
    print("─" * 70)


def print_results(results: list[WorkerResult]) -> None:
    print_banner(f"RESULTS — {len(results)} submitted")
    if not results:
        print("  (no results)")
        return
    for r in results:
        preview = r.content.strip().replace("\n", " ")
        if len(preview) > 180:
            preview = preview[:180] + "…"
        print(f"  agent         : {r.agent_id}")
        print(f"  task_id       : {r.task_id}")
        print(f"  content_hash  : {r.content_hash}")
        print(f"  payload_hash  : {r.payload_hash}")
        print(f"  signature     : {r.signature[:48]}… ({len(r.signature)} chars)")
        print(f"  answer (180c) : {preview}")
        print()


def print_events(events: list[dict]) -> None:
    print_banner(f"DSM EVENTS — {len(events)}")
    if not events:
        print("  (no events found — data dir may be different)")
        return
    for ev in events:
        et = ev.get("event_type", "?")
        eid = ev.get("event_id", "?")
        src = ev.get("source_id", "?")
        ts = ev.get("timestamp", "?")
        print(f"  [{ts}] {et:<24} src={src:<18} id={eid}")


# ── Main ───────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="agent-mesh end-to-end mission demo")
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--two-backends",
        action="store_true",
        help="Run Claude + GPT-4 in parallel",
    )
    g.add_argument(
        "--local",
        action="store_true",
        help="Run Claude + Ollama in parallel",
    )
    g.add_argument(
        "--openai-only",
        action="store_true",
        help="Run GPT-4 alone (requires OPENAI_API_KEY)",
    )
    p.add_argument(
        "--num-tasks",
        type=int,
        default=2,
        help="Number of tasks to create (default 2)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=RESULT_WAIT_TIMEOUT_S,
        help="Max wait for results in seconds",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    args = parse_args(argv)

    if args.two_backends:
        mode = "two-backends"
    elif args.local:
        mode = "local"
    elif args.openai_only:
        mode = "openai-only"
    else:
        mode = "default"

    server_url = os.environ.get("MESH_SERVER_URL", "http://localhost:8000")
    data_dir = Path(os.environ.get("AGENT_MESH_DATA_DIR", "./data")).resolve()

    print_banner(f"agent-mesh e2e — mode={mode}  server={server_url}")
    print(f"  Mission: {MISSION_TEXT}")
    print(f"  Data dir: {data_dir}")

    try:
        bundles = build_workers(mode, server_url)
    except Exception as exc:
        logger.error("Failed to build workers: %s", exc)
        return 2

    print("  Workers:")
    for b in bundles:
        print(f"    - {b.label} ({b.worker.config.agent_id})")

    try:
        results, mission_id, events = run_e2e(
            bundles,
            server_url=server_url,
            data_dir=data_dir,
            num_tasks=args.num_tasks,
            wait_timeout_s=args.timeout,
        )
    except Exception as exc:
        logger.error("E2E run failed: %s", exc)
        return 1

    print_banner(f"mission_id = {mission_id}")
    print_results(results)
    print_events(events)

    if len(results) < args.num_tasks:
        print_banner(f"INCOMPLETE — got {len(results)}/{args.num_tasks} results")
        return 1
    print_banner("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
