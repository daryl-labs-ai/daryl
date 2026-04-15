"""
workers/backends/ollama_backend.py
----------------------------------
Ollama local backend.

Calls a local Ollama server via HTTP. No external SDK required — just httpx.
"""
from __future__ import annotations

from typing import Any

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5"


class OllamaBackend:
    """Backend for a local Ollama daemon.

    Parameters
    ----------
    model:
        Model name as pulled by Ollama (e.g. "qwen2.5", "llama3.1").
    base_url:
        Ollama server URL.
    client:
        Optional pre-built `httpx.Client` instance. Tests inject a fake client
        here to avoid real network calls.
    timeout:
        HTTP timeout in seconds.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        client: Any | None = None,
        timeout: float = 60.0,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            import httpx  # lazy import

            self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._model = model
        self._base_url = base_url

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        response = self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["response"]
