"""
workers/backends/base.py
------------------------
LLM backend interface.

Every backend (Anthropic, OpenAI, Ollama, OpenAI-compatible) implements the same
minimal contract. The worker code does not care which backend is in use — it only
calls `backend.generate(prompt, system_prompt)`.

Principle: backend libre, protocole strict.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    """Minimal LLM backend contract.

    A backend is any object that can turn a prompt into a string response.
    No streaming, no tool use, no retries — just a single synchronous call.
    """

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        ...
