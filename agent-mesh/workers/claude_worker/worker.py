"""
workers/claude_worker/worker.py
--------------------------------
Claude worker for agent-mesh.

Calls Anthropic API, signs result, submits to mesh server.
The LLM knows nothing about agent-mesh — the wrapper handles everything.

Usage:
    python -m workers.claude_worker.worker

Env vars:
    ANTHROPIC_API_KEY      required
    MESH_SERVER_URL        default: http://localhost:8000
    AGENT_ID               default: agent_claude_sonnet
    AGENT_PRIVATE_KEY      base64 Ed25519 private key (generated if absent)
    AGENT_PUBLIC_KEY       base64 Ed25519 public key  (generated if absent)
    AGENT_KEY_ID           default: key_claude_v1
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import anthropic

# Add parent dir to path so `workers.protocol` resolves
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from workers.protocol import MeshWorker, WorkerConfig, generate_keypair

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a precise analytical agent working inside a multi-agent coordination system.

Your role:
- Analyze the task objective carefully
- Produce a clear, structured, factual response
- Be concise but complete
- Do not hallucinate — if you don't know, say so explicitly

Your output will be cryptographically signed and stored in an append-only provable memory system.
Every claim you make becomes a permanent, auditable fact."""


class ClaudeWorker(MeshWorker):
    """
    Worker backed by Claude (Anthropic API).
    Implements only call_llm() — protocol is inherited.
    """

    def __init__(self, config: WorkerConfig) -> None:
        super().__init__(config)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self._anthropic = anthropic.Anthropic(api_key=api_key)
        self._model = "claude-sonnet-4-20250514"

    def call_llm(self, objective: str, constraints: dict) -> str:
        """Call Claude with the task objective. Returns raw text response."""
        max_tokens = constraints.get("max_output_tokens", self.config.max_output_tokens)
        output_format = constraints.get("output_format", "text")

        user_message = objective
        if output_format == "json":
            user_message += "\n\nRespond in valid JSON only."

        logger.debug("Calling Claude — model=%s max_tokens=%d", self._model, max_tokens)

        message = self._anthropic.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        return message.content[0].text


# ── Entry point ────────────────────────────────────────────────────────────────

def load_or_generate_keypair() -> tuple[str, str]:
    """Load keys from env or generate a new pair (printed for saving)."""
    priv = os.environ.get("AGENT_PRIVATE_KEY")
    pub = os.environ.get("AGENT_PUBLIC_KEY")

    if priv and pub:
        return priv, pub

    logger.warning("No keypair found in env — generating new one")
    priv, pub = generate_keypair()
    print("\n⚠️  Save these in your .env — they identify this agent:\n")
    print(f"AGENT_PRIVATE_KEY={priv}")
    print(f"AGENT_PUBLIC_KEY={pub}\n")
    return priv, pub


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )

    priv, pub = load_or_generate_keypair()

    config = WorkerConfig(
        agent_id=os.environ.get("AGENT_ID", "agent_claude_sonnet"),
        capabilities=["analysis", "summarization", "reasoning", "code.review"],
        server_url=os.environ.get("MESH_SERVER_URL", "http://localhost:8000"),
        private_key_b64=priv,
        public_key_b64=pub,
        key_id=os.environ.get("AGENT_KEY_ID", "key_claude_v1"),
        poll_interval_s=float(os.environ.get("POLL_INTERVAL", "2.0")),
        max_output_tokens=int(os.environ.get("MAX_OUTPUT_TOKENS", "1200")),
    )

    worker = ClaudeWorker(config)
    worker.run()


if __name__ == "__main__":
    main()
