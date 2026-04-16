"""
Production startup script.
Starts agent-mesh server + workers in the same process.
Workers run as background threads.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# Ensure both src/ (for agent_mesh) and the repo root (for workers/) are importable
_ROOT = Path(__file__).resolve().parent
for p in (_ROOT, _ROOT / "src"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import uvicorn


def start_worker(
    provider: str, agent_id: str, model: str, api_key: str, port: int, cap_suffix: str,
):
    """Start a single LLM worker in a background thread."""
    try:
        from workers.backends import create_backend
        from workers.generic_worker.worker import GenericLLMWorker
        from workers.protocol import WorkerConfig, generate_keypair

        print(f"[worker:{agent_id}] initializing (provider={provider}, cap=analysis_{cap_suffix})")

        priv, pub = generate_keypair()
        config = WorkerConfig(
            agent_id=agent_id,
            capabilities=["analysis", f"analysis_{cap_suffix}"],
            server_url=f"http://localhost:{port}",
            private_key_b64=priv,
            public_key_b64=pub,
            key_id=f"key_{provider}_v1",
            poll_interval_s=2.0,
            max_output_tokens=800,
        )
        backend = create_backend({
            "provider": provider,
            "model": model,
            "api_key": api_key,
        })
        worker = GenericLLMWorker(config=config, backend=backend)

        print(f"[worker:{agent_id}] waiting 10s for server startup...")
        time.sleep(10)
        print(f"[worker:{agent_id}] registering and starting poll loop")
        worker.run()
    except Exception as exc:
        print(f"[worker:{agent_id}] FATAL: {type(exc).__name__}: {exc}", flush=True)
        import traceback
        traceback.print_exc()


def main():
    port = int(os.environ.get("PORT", 8000))
    os.environ.setdefault("AGENT_MESH_DATA_DIR", str(_ROOT / "data"))

    threads = []

    workers_spec = [
        ("ANTHROPIC_API_KEY", "anthropic", "agent_claude_prod", "claude-sonnet-4-20250514", "claude"),
        ("OPENAI_API_KEY", "openai", "agent_gpt4_prod", "gpt-4o-mini", "gpt4"),
        ("ZHIPU_API_KEY", "zhipu", "agent_glm_prod", "glm-4", "glm"),
    ]

    for env_var, provider, agent_id, model, cap_suffix in workers_spec:
        api_key = os.environ.get(env_var)
        if not api_key:
            print(f"[main] {env_var} not set — skipping {agent_id}")
            continue
        try:
            t = threading.Thread(
                target=start_worker,
                args=(provider, agent_id, model, api_key, port, cap_suffix),
                daemon=True,
            )
            t.start()
            threads.append(t)
            print(f"[main] launched {agent_id} thread")
        except Exception as exc:
            print(f"[main] FAILED to launch {agent_id}: {exc}", flush=True)

    print(f"[main] Starting agent-mesh server on port {port} with {len(threads)} worker(s)")

    uvicorn.run(
        "agent_mesh.server.app:create_app",
        host="0.0.0.0",
        port=port,
        factory=True,
    )


if __name__ == "__main__":
    main()
