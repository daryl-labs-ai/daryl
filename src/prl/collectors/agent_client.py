"""Agent clients — the real-model boundary (R-consult v3, ADR-PRL-0008 / 0007).

v3 proves exactly one thing: *a real agent can produce a DSM-certified Knowledge Act
without knowing PRL.* This module is the only place that talks to a real model. The
model returns its **native answer**; the ConsultationAdapter then maps it to a
Knowledge Act. The mapping stays provider-independent because it depends on this
``AgentClient`` interface, not on any SDK.

Heavy SDKs are imported **lazily** (like ``LocalEmbedder``), so importing this module
never requires a provider SDK. Tests inject a fake client; no network.

Scope (v3): the interface + OpenAIClient only. ClaudeClient / LocalClient are future
implementations of the same interface — out of scope until needed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..exceptions import PRLError


class AgentClientError(PRLError):
    """Raised for a missing provider SDK or a failed model call."""


@runtime_checkable
class AgentClient(Protocol):
    """A real-agent client. Returns the model's native answer for a prompt."""

    provider: str

    def complete(self, prompt: str, *, model: str) -> str: ...


class OpenAIClient:
    """OpenAI provider via the **Responses API** (the v3 default).

    Lazy-imports the ``openai`` SDK at construction so this module imports cleanly
    without it; raises :class:`AgentClientError` with an actionable message if absent.
    """

    provider = "openai"

    def __init__(self, *, api_key: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover (env-dependent)
            raise AgentClientError(
                "OpenAIClient needs the 'agents' extra: pip install daryl-dsm[agents]"
            ) from exc
        self._client = OpenAI(api_key=api_key) if api_key else OpenAI()

    def complete(self, prompt: str, *, model: str) -> str:  # pragma: no cover (needs network)
        resp = self._client.responses.create(model=model, input=prompt)
        return str(getattr(resp, "output_text", "") or "")
