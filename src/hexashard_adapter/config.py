"""Adapter config. Usable Ollama limits come from LIVE 001-L, not the spec sheet."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .errors import InvalidProviderConfiguration

ProviderName = Literal["mock", "ollama"]
ProjectMode = Literal["NORMAL", "READ_ONLY"]

# LIVE 001-L empirical usable prompt with num_ctx=262144. Not a global constant
# of HexaShard; copied into defaults so a caller can override.
OLLAMA_001L_NUM_CTX = 262144
OLLAMA_001L_USABLE_PROMPT = 131072
OLLAMA_001L_MODEL = "qwen3.6:35b-a3b"
OLLAMA_001L_ENDPOINT = "http://127.0.0.1:11434/api/generate"


@dataclass
class AdapterConfig:
    provider: ProviderName = "mock"
    model: str = OLLAMA_001L_MODEL
    endpoint: str = OLLAMA_001L_ENDPOINT
    num_ctx: int = OLLAMA_001L_NUM_CTX
    #: Tokens the provider actually accepts as prompt. For Ollama v0.1 this is
    #: the 001-L measured usable window, not num_ctx.
    provider_context_limit: int = OLLAMA_001L_USABLE_PROMPT
    #: Tokens Adapter is allowed to send (system+user+project working set).
    model_context_budget: int = 8000
    retrieval_budget: int = 1500
    max_output_tokens: int = 256
    temperature: float = 0.0
    seed: int = 0
    think: bool = False
    timeout_s: int = 120
    mode: ProjectMode = "NORMAL"
    #: Optional organisational hint. Never used as an exclusive retrieval filter.
    home_hex_id: str | None = None
    keep_alive: str = "10m"

    def validate(self) -> None:
        if self.model_context_budget <= 0 or self.provider_context_limit <= 0:
            raise InvalidProviderConfiguration("context limits must be positive")
        if self.model_context_budget > self.provider_context_limit:
            raise InvalidProviderConfiguration(
                f"model_context_budget {self.model_context_budget} exceeds "
                f"provider_context_limit {self.provider_context_limit}"
            )
        if self.provider == "ollama" and self.num_ctx < 1:
            raise InvalidProviderConfiguration("ollama num_ctx must be positive")
        if self.mode not in ("NORMAL", "READ_ONLY"):
            raise InvalidProviderConfiguration(f"unknown mode {self.mode}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AdapterConfig":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        cfg = cls(**known)
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, path: str | Path) -> "AdapterConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
