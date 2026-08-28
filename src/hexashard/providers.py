"""Model adapter boundary.

HexaShard core never calls a model.  ``Project.handle_turn`` assembles bounded
context and returns it; the caller owns the actual model interaction, the chat
UI, authentication and tool execution.

This module exists so a caller that *wants* HexaShard to make the call has one
tiny interface to implement, and so the test suite can exercise the turn flow
without any provider-specific code.  v0.1 ships exactly one adapter: a
deterministic mock.  No vendor SDK is imported anywhere in this package.
"""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ModelResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = "unknown"


class ModelProvider(Protocol):
    name: str

    def generate(
        self,
        system: str,
        messages: list[dict[str, str]],
        context: dict[str, Any],
        token_budget: int,
    ) -> ModelResult: ...


@dataclass
class MockModelProvider:
    """Deterministic adapter.

    Echoes a stable digest of what it was given.  Its only jobs are to prove
    the turn flow is provider-independent and to make model-side token counts
    observable in tests without network access or nondeterminism.
    """

    name: str = "mock"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate(
        self,
        system: str,
        messages: list[dict[str, str]],
        context: dict[str, Any],
        token_budget: int,
    ) -> ModelResult:
        payload = json.dumps(
            {"system": system, "messages": messages, "context": context},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        digest = format(zlib.crc32(payload.encode('utf-8')), '08x')
        pins = [p.get("key") for p in context.get("active_pins", [])]
        cited = [f.get("source_id") for f in context.get("retrieved", [])]
        text = (
            f"[mock:{digest}] objective={context.get('current_objective', '')!r} "
            f"pins={pins} sources={cited}"
        )
        from .tokens import estimate_tokens

        result = ModelResult(
            text=text,
            input_tokens=estimate_tokens(payload) + estimate_tokens(system),
            output_tokens=estimate_tokens(text),
            provider=self.name,
        )
        self.calls.append({"budget": token_budget, "digest": digest})
        return result
