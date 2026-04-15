"""
workers/backends/openai_backend.py
----------------------------------
OpenAI (GPT) backend.

Uses the `openai>=1.x` SDK via `client.chat.completions.create`.
"""
from __future__ import annotations

from typing import Any

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 1200


class OpenAIBackend:
    """OpenAI backend via the openai SDK (>=1.x).

    Parameters
    ----------
    api_key:
        OpenAI API key. Required unless `client` is provided.
    model:
        Model identifier (e.g. "gpt-4o-mini", "gpt-4o").
    max_tokens:
        Default max_tokens per call.
    client:
        Optional pre-built `openai.OpenAI` instance. Tests inject a fake client
        here to avoid requiring the real SDK.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ValueError("api_key is required when client is not provided")
            import openai  # lazy import

            self._client = openai.OpenAI(api_key=api_key)
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
