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
    from workers.backends import create_backend
    from workers.generic_worker.worker import GenericLLMWorker
    from workers.protocol import WorkerConfig, generate_keypair

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

    time.sleep(10)
    worker.run()


def main():
    port = int(os.environ.get("PORT", 8000))
    os.environ.setdefault("AGENT_MESH_DATA_DIR", str(_ROOT / "data"))

    threads = []

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        t = threading.Thread(
            target=start_worker,
            args=("anthropic", "agent_claude_prod", "claude-sonnet-4-20250514", anthropic_key, port, "claude"),
            daemon=True,
        )
        t.start()
        threads.append(t)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        t = threading.Thread(
            target=start_worker,
            args=("openai", "agent_gpt4_prod", "gpt-4o-mini", openai_key, port, "gpt4"),
            daemon=True,
        )
        t.start()
        threads.append(t)

    zhipu_key = os.environ.get("ZHIPU_API_KEY")
    if zhipu_key:
        t = threading.Thread(
            target=start_worker,
            args=("zhipu", "agent_glm_prod", "glm-4", zhipu_key, port, "glm"),
            daemon=True,
        )
        t.start()
        threads.append(t)

    print(f"Starting agent-mesh server on port {port} with {len(threads)} workers")

    uvicorn.run(
        "agent_mesh.server.app:create_app",
        host="0.0.0.0",
        port=port,
        factory=True,
    )


if __name__ == "__main__":
    main()
