"""
workers/backends/anthropic_backend.py
-------------------------------------
Anthropic (Claude) backend.

Uses the official `anthropic` SDK. No streaming, no tool use.
"""
from __future__ import annotations

from typing import Any

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 1200


class AnthropicBackend:
    """Claude backend via the Anthropic SDK.

    Parameters
    ----------
    api_key:
        Anthropic API key. Required unless `client` is provided.
    model:
        Model identifier. Defaults to Claude Sonnet 4.
    max_tokens:
        Default max_tokens for each call.
    client:
        Optional pre-built `anthropic.Anthropic` instance. Tests inject a fake
        client here to avoid requiring the real SDK.
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
            import anthropic  # lazy import so module is importable without SDK

            self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        message = self._client.messages.create(**kwargs)
        # Anthropic returns a list of content blocks; the first one is text.
        return message.content[0].text
