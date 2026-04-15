"""
workers/backends/zhipu_backend.py
---------------------------------
Zhipu AI (GLM family) backend.

Zhipu exposes two distinct OpenAI-compatible endpoints depending on the model:

  - General API   (glm-4, glm-4-flash, glm-4-plus, glm-4-air, glm-zero, …)
      https://api.z.ai/api/paas/v4
  - Coding API    (glm-code, glm-coding, codegeex, codegeex-4, …)
      https://api.z.ai/api/coding/paas/v4

The backend automatically picks the correct endpoint from the model name, or
accepts an explicit `base_url` override. Under the hood it uses the standard
`openai>=1.x` SDK — Zhipu is OpenAI-compatible for chat completions.
"""
from __future__ import annotations

from typing import Any

CODING_API_URL = "https://api.z.ai/api/coding/paas/v4"
GENERAL_API_URL = "https://api.z.ai/api/paas/v4"

DEFAULT_MODEL = "glm-4"
DEFAULT_MAX_TOKENS = 1200

# Model-name heuristics. A model is routed to the coding endpoint iff its
# identifier matches one of the exact strings below OR starts with a known
# coding prefix. Everything else goes to the general endpoint.
CODING_MODELS: frozenset[str] = frozenset(
    {
        "glm-code",
        "glm-coding",
        "codegeex",
        "codegeex-4",
        "codegeex2",
        "codegeex2-6b",
    }
)

CODING_MODEL_PREFIXES: tuple[str, ...] = (
    "codegeex",
    "glm-code",
    "glm-coding",
)


def is_coding_model(model: str) -> bool:
    """Return True if `model` targets Zhipu's coding endpoint."""
    if not model:
        return False
    if model in CODING_MODELS:
        return True
    low = model.lower()
    return any(low.startswith(p) for p in CODING_MODEL_PREFIXES)


def resolve_base_url(model: str) -> str:
    """Auto-pick the correct Zhipu endpoint from a model name."""
    return CODING_API_URL if is_coding_model(model) else GENERAL_API_URL


class ZhipuBackend:
    """Backend for Zhipu AI (GLM family).

    Parameters
    ----------
    api_key:
        Zhipu API key. Required unless `client` is provided.
    model:
        GLM model identifier (e.g. "glm-4", "glm-4-flash", "glm-code").
    base_url:
        Optional explicit endpoint. When omitted, the backend picks
        CODING_API_URL or GENERAL_API_URL based on the model name.
    max_tokens:
        Default max_tokens per call.
    client:
        Optional pre-built `openai.OpenAI` instance. Tests inject a fake
        client here to avoid requiring the real SDK or real network.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: Any | None = None,
    ) -> None:
        if not model:
            raise ValueError("model is required")

        resolved_base_url = base_url if base_url else resolve_base_url(model)

        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ValueError("api_key is required when client is not provided")
            import openai  # lazy import — same pattern as the other backends

            self._client = openai.OpenAI(api_key=api_key, base_url=resolved_base_url)

        self._model = model
        self._base_url = resolved_base_url
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
