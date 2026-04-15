"""
workers.backends — Pluggable LLM backends for the generic worker.

Every backend implements the `LLMBackend` protocol:

    def generate(self, prompt: str, system_prompt: str | None = None) -> str

Backends are imported lazily so the package can be imported even when specific
SDKs (`anthropic`, `openai`) are not installed.

Factory usage::

    from workers.backends import create_backend

    backend = create_backend({
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-...",
    })
    text = backend.generate("Hello", system_prompt="Be concise.")
"""
from __future__ import annotations

from typing import Any

from .base import LLMBackend

__all__ = [
    "LLMBackend",
    "create_backend",
    "AnthropicBackend",
    "OpenAIBackend",
    "OllamaBackend",
    "OpenAICompatibleBackend",
    "ZhipuBackend",
]


def __getattr__(name: str):
    # Lazy re-export of backend classes so the subpackage is importable even
    # when the underlying SDK is missing.
    if name == "AnthropicBackend":
        from .anthropic_backend import AnthropicBackend

        return AnthropicBackend
    if name == "OpenAIBackend":
        from .openai_backend import OpenAIBackend

        return OpenAIBackend
    if name == "OllamaBackend":
        from .ollama_backend import OllamaBackend

        return OllamaBackend
    if name == "OpenAICompatibleBackend":
        from .openai_compatible_backend import OpenAICompatibleBackend

        return OpenAICompatibleBackend
    if name == "ZhipuBackend":
        from .zhipu_backend import ZhipuBackend

        return ZhipuBackend
    raise AttributeError(f"module 'workers.backends' has no attribute {name!r}")


def create_backend(config: dict[str, Any]) -> LLMBackend:
    """Build a backend from a config dict.

    Required keys:
        provider: one of "anthropic", "openai", "ollama",
                  "openai_compatible", "zhipu"

    Provider-specific keys:
        anthropic         → api_key, model?, max_tokens?
        openai            → api_key, model?, max_tokens?
        ollama            → model?, base_url?
        openai_compatible → base_url, api_key, model, max_tokens?
        zhipu             → api_key, model?, base_url?, max_tokens?

    An optional `client` key is passed through (used by tests).
    """
    provider = config.get("provider")
    if not provider:
        raise ValueError("config.provider is required")

    client = config.get("client")

    if provider == "anthropic":
        from .anthropic_backend import AnthropicBackend, DEFAULT_MAX_TOKENS, DEFAULT_MODEL

        return AnthropicBackend(
            api_key=config.get("api_key"),
            model=config.get("model", DEFAULT_MODEL),
            max_tokens=config.get("max_tokens", DEFAULT_MAX_TOKENS),
            client=client,
        )

    if provider == "openai":
        from .openai_backend import OpenAIBackend, DEFAULT_MAX_TOKENS, DEFAULT_MODEL

        return OpenAIBackend(
            api_key=config.get("api_key"),
            model=config.get("model", DEFAULT_MODEL),
            max_tokens=config.get("max_tokens", DEFAULT_MAX_TOKENS),
            client=client,
        )

    if provider == "ollama":
        from .ollama_backend import OllamaBackend, DEFAULT_BASE_URL, DEFAULT_MODEL

        return OllamaBackend(
            model=config.get("model", DEFAULT_MODEL),
            base_url=config.get("base_url", DEFAULT_BASE_URL),
            client=client,
        )

    if provider == "openai_compatible":
        from .openai_compatible_backend import OpenAICompatibleBackend, DEFAULT_MAX_TOKENS

        base_url = config.get("base_url")
        if not base_url:
            raise ValueError("openai_compatible requires base_url")
        return OpenAICompatibleBackend(
            base_url=base_url,
            api_key=config.get("api_key"),
            model=config.get("model", ""),
            max_tokens=config.get("max_tokens", DEFAULT_MAX_TOKENS),
            client=client,
        )

    if provider == "zhipu":
        from .zhipu_backend import ZhipuBackend, DEFAULT_MODEL, DEFAULT_MAX_TOKENS

        return ZhipuBackend(
            api_key=config.get("api_key"),
            model=config.get("model", DEFAULT_MODEL),
            base_url=config.get("base_url"),
            max_tokens=config.get("max_tokens", DEFAULT_MAX_TOKENS),
            client=client,
        )

    raise ValueError(f"unknown provider: {provider!r}")
