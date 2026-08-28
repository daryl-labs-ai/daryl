"""Adapter-owned result types. Project records stay in Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatTurnResult:
    response_text: str
    model_input_tokens: int
    model_output_tokens: int
    active_state_tokens: int
    retrieved_context_tokens: int
    total_context_tokens: int
    retrieved_source_ids: list[str]
    pin_warnings: list[dict[str, Any]]
    authority_warnings: list[str]
    epoch: int
    latency_ms: int
    retrieval_latency_ms: int
    adapter_overhead_ms: int
    state_update_summary: dict[str, Any]
    truncated: bool = False
    dropped_sections: list[str] = field(default_factory=list)
    provider: str = "mock"
    mode: str = "NORMAL"
    retrieval_count: int = 0
    project_store_tokens: int = 0
    turn: int = 0
    no_source_retrieved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_text": self.response_text,
            "model_input_tokens": self.model_input_tokens,
            "model_output_tokens": self.model_output_tokens,
            "active_state_tokens": self.active_state_tokens,
            "retrieved_context_tokens": self.retrieved_context_tokens,
            "total_context_tokens": self.total_context_tokens,
            "retrieved_source_ids": list(self.retrieved_source_ids),
            "pin_warnings": list(self.pin_warnings),
            "authority_warnings": list(self.authority_warnings),
            "epoch": self.epoch,
            "latency_ms": self.latency_ms,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "adapter_overhead_ms": self.adapter_overhead_ms,
            "state_update_summary": dict(self.state_update_summary),
            "truncated": self.truncated,
            "dropped_sections": list(self.dropped_sections),
            "provider": self.provider,
            "mode": self.mode,
            "retrieval_count": self.retrieval_count,
            "project_store_tokens": self.project_store_tokens,
            "turn": self.turn,
            "no_source_retrieved": self.no_source_retrieved,
        }


@dataclass
class AssembledContext:
    system: str
    user: str
    project_block: str
    sections: dict[str, str]
    tokens: int
    truncated: bool
    dropped_sections: list[str]
    retrieved_source_ids: list[str]
    authority_warnings: list[str]
    no_source_retrieved: bool
