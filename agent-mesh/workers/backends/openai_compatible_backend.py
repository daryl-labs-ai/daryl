"""
workers/backends/openai_compatible_backend.py
---------------------------------------------
OpenAI-compatible backend for vLLM, LM Studio, OpenRouter, Groq, Together, etc.

Uses the `openai>=1.x` SDK with a custom `base_url`. Any provider that exposes
the OpenAI Chat Completions schema works.
"""
from __future__ import annotations

from typing import Any

DEFAULT_MAX_TOKENS = 1200


class OpenAICompatibleBackend:
    """OpenAI-compatible backend.

    Parameters
    ----------
    base_url:
        Custom API endpoint (e.g. "https://openrouter.ai/api/v1",
        "http://localhost:8000/v1", "https://api.groq.com/openai/v1").
    api_key:
        API key for the provider. Required unless `client` is provided.
    model:
        Model identifier for the target provider.
    max_tokens:
        Default max_tokens per call.
    client:
        Optional pre-built `openai.OpenAI` instance. Tests inject a fake client
        here to avoid requiring the real SDK.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: Any | None = None,
    ) -> None:
        if not model:
            raise ValueError("model is required")
        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ValueError("api_key is required when client is not provided")
            import openai  # lazy import

            self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self._base_url = base_url
        self._model = model
        self._max_tokens = max_tokens

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=messages,
        )
        return response.choices[0].message.content
