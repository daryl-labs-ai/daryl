"""
workers/generic_worker/worker.py
--------------------------------
Backend-agnostic mesh worker.

The worker holds a reference to a `LLMBackend` and delegates the single LLM
call to it. Everything else — registration, signing, submission, poll loop —
is inherited from `MeshWorker`.

Principle: backend libre, protocole strict.

Usage::

    from workers.backends import create_backend
    from workers.generic_worker.worker import GenericLLMWorker
    from workers.protocol import WorkerConfig

    backend = create_backend({
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-...",
    })
    worker = GenericLLMWorker(config=WorkerConfig(...), backend=backend)
    worker.run()
"""
from __future__ import annotations

import logging
import os
from typing import Any

from workers.backends.base import LLMBackend
from workers.protocol import MeshWorker, WorkerConfig

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are a precise analytical agent working inside a multi-agent coordination system.

Your role:
- Analyze the task objective carefully
- Produce a clear, structured, factual response
- Be concise but complete
- Do not hallucinate — if you don't know, say so explicitly

Your output will be cryptographically signed and stored in an append-only provable memory system.
Every claim you make becomes a permanent, auditable fact."""


class GenericLLMWorker(MeshWorker):
    """Mesh worker that delegates LLM calls to a pluggable backend.

    Parameters
    ----------
    config:
        `WorkerConfig` describing agent_id, capabilities, keypair, server URL…
    backend:
        Any object implementing `LLMBackend.generate(prompt, system_prompt) -> str`.
    system_prompt:
        Optional default system prompt. Overridden by `constraints["system_prompt"]`
        when present in a task's constraints.
    """

    def __init__(
        self,
        config: WorkerConfig,
        backend: LLMBackend,
        system_prompt: str | None = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        super().__init__(config)
        self.backend = backend
        self.system_prompt = system_prompt

    def call_llm(self, objective: str, constraints: dict) -> str:
        """Delegate to the backend. Kept synchronous — matches MeshWorker."""
        task_system_prompt = constraints.get("system_prompt") if constraints else None
        system_prompt = task_system_prompt or self.system_prompt
        output_format = (constraints or {}).get("output_format")

        prompt = objective
        if output_format == "json":
            prompt = f"{objective}\n\nRespond in valid JSON only."

        logger.debug(
            "GenericLLMWorker.call_llm — backend=%s format=%s",
            type(self.backend).__name__,
            output_format,
        )
        return self.backend.generate(prompt, system_prompt=system_prompt)


# ── Convenience env-based builder (used by workers/run_worker.py) ──────────────

def build_worker_from_env() -> GenericLLMWorker:
    """Build a GenericLLMWorker from environment variables.

    Required env:
        MESH_SERVER_URL      default: http://localhost:8000
        AGENT_ID             default: agent_generic
        AGENT_PRIVATE_KEY    (generated if absent — printed once)
        AGENT_PUBLIC_KEY     (generated if absent — printed once)
        AGENT_KEY_ID         default: key_generic_v1
        LLM_PROVIDER         one of: anthropic | openai | ollama | openai_compatible
        LLM_MODEL            model id (provider-specific default if absent)
        LLM_API_KEY          required for anthropic / openai / openai_compatible
        LLM_BASE_URL         required for openai_compatible, optional for ollama
        AGENT_CAPABILITIES   comma-separated list (default: analysis,summarization)
        POLL_INTERVAL        float seconds (default 2.0)
        MAX_OUTPUT_TOKENS    int (default 1200)
    """
    from workers.backends import create_backend
    from workers.protocol import generate_keypair

    provider = os.environ.get("LLM_PROVIDER")
    if not provider:
        raise ValueError("LLM_PROVIDER is required (anthropic|openai|ollama|openai_compatible)")

    priv = os.environ.get("AGENT_PRIVATE_KEY")
    pub = os.environ.get("AGENT_PUBLIC_KEY")
    if not (priv and pub):
        logger.warning("No keypair found in env — generating new one")
        priv, pub = generate_keypair()
        print("\n⚠️  Save these in your .env — they identify this agent:\n")
        print(f"AGENT_PRIVATE_KEY={priv}")
        print(f"AGENT_PUBLIC_KEY={pub}\n")

    backend_config: dict[str, Any] = {"provider": provider}
    if os.environ.get("LLM_MODEL"):
        backend_config["model"] = os.environ["LLM_MODEL"]
    if os.environ.get("LLM_API_KEY"):
        backend_config["api_key"] = os.environ["LLM_API_KEY"]
    if os.environ.get("LLM_BASE_URL"):
        backend_config["base_url"] = os.environ["LLM_BASE_URL"]
    if os.environ.get("MAX_OUTPUT_TOKENS"):
        backend_config["max_tokens"] = int(os.environ["MAX_OUTPUT_TOKENS"])

    backend = create_backend(backend_config)

    caps_raw = os.environ.get("AGENT_CAPABILITIES", "analysis,summarization")
    capabilities = [c.strip() for c in caps_raw.split(",") if c.strip()]

    config = WorkerConfig(
        agent_id=os.environ.get("AGENT_ID", "agent_generic"),
        capabilities=capabilities,
        server_url=os.environ.get("MESH_SERVER_URL", "http://localhost:8000"),
        private_key_b64=priv,
        public_key_b64=pub,
        key_id=os.environ.get("AGENT_KEY_ID", "key_generic_v1"),
        poll_interval_s=float(os.environ.get("POLL_INTERVAL", "2.0")),
        max_output_tokens=int(os.environ.get("MAX_OUTPUT_TOKENS", "1200")),
    )
    return GenericLLMWorker(config=config, backend=backend)
